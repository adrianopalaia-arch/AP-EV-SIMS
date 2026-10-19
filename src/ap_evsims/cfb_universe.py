"""Schedule-first CFB coverage audit. Missing quotes never remove a scheduled game.

Coverage describes captured queries, not a complete season. Historical revisions
are usable only after their capture; final results cannot authorize past features.
"""
from collections import Counter
from dataclasses import asdict
from .integrity import utc, digest
from .identity import map_cfb_events
from .cfb_history import RollingCFBHistory, BASELINE_FEATURES
from .providers.schema import validate_provider_payload


def verified_sources(store, warehouse, endpoint, at):
    with warehouse.connect() as db:
        ids = db.execute("SELECT snapshot_id FROM snapshots WHERE provider='cfbd' AND dataset=? AND available_at<=? ORDER BY available_at,snapshot_id", [endpoint, at]).fetchall()
    result = []
    for (sid,) in ids:
        m = store.manifest(sid)
        if m['provider'] != 'cfbd' or m['endpoint'] != endpoint or m['parameters'].get('endpoint_status', 200) != 200:
            raise ValueError('SOURCE_PROVENANCE_MISMATCH')
        if not m.get('available_at') or utc(m['available_at']) > utc(at):
            raise ValueError('HISTORICAL_AVAILABILITY_UNVERIFIED')
        payload = store.payload(m)
        validate_provider_payload('cfbd', endpoint, payload)
        result.append((m, payload))
    return result


def build_cfb_universe(store, warehouse, at, quotes, *, feature_lookback_days=365):
    """Retain all latest game observations, including conflicts and excluded games.

    Queries are assembled at the cutoff with verified source identities. The
    four baseline features remain distinct from the full Phase 1 contract.
    """
    clock = utc(at)
    sources = verified_sources(store, warehouse, 'games', at)
    teams = verified_sources(store, warehouse, 'teams', at)
    plays = verified_sources(store, warehouse, 'plays', at)
    history = RollingCFBHistory(store, plays_snapshot_ids=[m['snapshot_id'] for m, _ in plays],
        results_snapshot_ids=[m['snapshot_id'] for m, _ in sources], as_of=at, lookback_days=feature_lookback_days)
    latest = {}; conflicts = set(); queries = {}
    for m, rows in sources:
        queries[digest({k:v for k,v in m['parameters'].items() if k not in ('endpoint_status','error_payload_sanitized')})] = m
        seen = set()
        for row in rows:
            event = str(row['id'])
            if event in seen: conflicts.add(event)
            seen.add(event)
            old = latest.get(event)
            # Different queries captured simultaneously must agree on the game.
            if old and old[1]['available_at'] == m['available_at'] and old[0] != row:
                conflicts.add(event)
            latest[event] = (row, m)
    events = {}
    for q in quotes:
        if q['sport'] == 'CFB':
            events[q['event_id']] = dict(id=q['event_id'],home_team=q['home_team'],away_team=q['away_team'],commence_time=q['event_start'].isoformat())
    mapping = {}; identity_rejections = []
    if teams and latest:
        tm, team_rows = teams[-1]
        mapping, identity_rejections = map_cfb_events(team_rows,[r for r,m in latest.values()],list(events.values()),
            alias_snapshot=tm['snapshot_id'],game_snapshot=digest(sorted(m['snapshot_id'] for r,m in latest.values())),available_at=clock.isoformat())
    mapped = {}
    for odds_id, value in mapping.items(): mapped.setdefault(value['event_id'], []).append(odds_id)
    # Never use season-end aggregates, ratings, later injury status or observed
    # postgame weather as evidence for a historical prediction.
    rows = []
    for event, (g, source) in sorted(latest.items()):
        reasons = []; feature_values = {}; feature_errors = []
        start = utc(g['startDate'])
        if event in conflicts: reasons.append('CONFLICTING_GAME_REVISION')
        if g.get('homeClassification') != 'fbs' or g.get('awayClassification') != 'fbs': reasons.append('OUTSIDE_FBS_VS_FBS_SCOPE')
        if start <= clock: reasons.append('EVENT_STARTED_OR_COMPLETED')
        if g.get('completed') is True and start > clock: reasons.append('LOOKAHEAD_RISK')
        if g.get('startTimeTBD') is not False: reasons.append('EVENT_START_UNCONFIRMED')
        event_quotes = [q for q in quotes if q['event_id'] in mapped.get(event, [])]
        if not event_quotes: reasons.append('NO_MATCHED_MARKET')
        elif not any((clock-utc(q['observed_at'])).total_seconds() <= 180 for q in event_quotes): reasons.append('STALE_PRICE')
        if not any(r in reasons for r in ('EVENT_STARTED_OR_COMPLETED','LOOKAHEAD_RISK','OUTSIDE_FBS_VS_FBS_SCOPE','CONFLICTING_GAME_REVISION')):
            try:
                features = history.materialize(event_id=event,home_team=g['homeTeam'],away_team=g['awayTeam'])
                feature_values = {k:asdict(v) for k,v in features.values.items()}
            except ValueError as error:
                feature_errors.append(str(error))
        if not feature_values: reasons.append('MISSING_FEATURES')
        reasons += ['MODEL_NOT_CALIBRATED','UNVERIFIED_LINEUP']
        rows.append(dict(event_id=event,season=g.get('season'),week=g.get('week'),home_team=g['homeTeam'],away_team=g['awayTeam'],
            event_start=start.isoformat(),schedule_snapshot_id=source['snapshot_id'],schedule_hash=source['payload_hash'],
            schedule_available_at=source['available_at'],matched_odds_event_ids=mapped.get(event,[]),market_sides=len(event_quotes),
            scope_eligible='OUTSIDE_FBS_VS_FBS_SCOPE' not in reasons and start>clock,
            qualified=False,pass_reason=reasons,verified_features=feature_values,feature_blockers=sorted(set(feature_errors)),
            research_baseline_features_complete=all(k in feature_values for k in BASELINE_FEATURES),
            phase1_feature_contract_complete=False,
            missing_feature_contract='Phase 1 CFB contract remains required; rolling PPA is not EPA'))
    return dict(generated_at=clock.isoformat(),coverage='CAPTURED_QUERIES_ONLY_NOT_A_COMPLETE_SEASON',
        query_count=len(queries),query_parameters=[m['parameters'] for m in queries.values()],games_scanned=len(rows),
        upcoming_fbs_games=sum(r['scope_eligible'] for r in rows),matched_games=sum(bool(r['matched_odds_event_ids']) for r in rows),
        unmatched_odds_events=len(events)-len(mapping),identity_rejections=identity_rejections,
        games_with_verified_rolling_features=sum(bool(r['verified_features']) for r in rows),qualified_games=0,
        games_with_research_baseline_features=sum(r['research_baseline_features_complete'] for r in rows),
        games_with_phase1_feature_contract=0, play_history=history.counts,
        qualifying_real_sample=0,synthetic_performance_sample=0,
        exclusions=dict(Counter(reason for r in rows for reason in r['pass_reason'])),games=rows)
