"""Multi-query CFB play history, with capture-time provenance and replayable recipes.

This is a small research feature subset, not the complete Phase 1 CFB contract.
Provider wallclock/game dates never stand in for historical publication dates.
"""
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import timedelta
import json

from .cfb_features import adjusted_efficiency, normalize_cfbd_plays
from .integrity import digest, utc
from .models.base import FeatureSnapshot, FeatureValue
from .providers.normalize import require_historical_availability
from .providers.schema import validate_provider_payload

BASELINE_FEATURES = ('ppa_diff', 'success_rate_diff', 'success_rate_sum', 'plays_sum')
VERSION = 'rolling-cfb-multi-v1'


def load_sources(store, identities, endpoint, as_of):
    sources = []
    for identity in sorted(set(identities)):
        m = store.manifest(identity)
        if m['provider'] != 'cfbd' or m['endpoint'] != endpoint or m['parameters'].get('endpoint_status', 200) != 200:
            raise ValueError('SOURCE_PROVENANCE_MISMATCH')
        require_historical_availability(m, as_of)
        payload = store.payload(m)
        validate_provider_payload('cfbd', endpoint, payload)
        sources.append((m, payload))
    return sorted(sources, key=lambda x: (utc(x[0]['available_at']), x[0]['snapshot_id']))


class RollingCFBHistory:
    """Prepare opponent adjustment once per cutoff, then materialize many matchups."""
    def __init__(self, store, *, plays_snapshot_ids, results_snapshot_ids, as_of, lookback_days=365):
        if isinstance(lookback_days, bool) or not isinstance(lookback_days, int) or lookback_days < 1:
            raise ValueError('INVALID_LOOKBACK')
        self.store, self.as_of, self.lookback_days = store, utc(as_of).isoformat(), lookback_days
        self.play_ids, self.result_ids = sorted(set(plays_snapshot_ids)), sorted(set(results_snapshot_ids))
        game_sources = load_sources(store, self.result_ids, 'games', self.as_of)
        play_sources = load_sources(store, self.play_ids, 'plays', self.as_of)
        self.games = {}; game_conflicts = set(); counts = Counter()
        for m, payload in game_sources:
            seen = set()
            for g in payload:
                event = str(g['id'])
                if event in seen: game_conflicts.add(event)
                seen.add(event)
                previous = self.games.get(event)
                if previous and utc(previous[1]['available_at']) == utc(m['available_at']) and previous[0] != g:
                    game_conflicts.add(event)
                self.games[event] = (g, m)
        self.game_conflicts = game_conflicts
        # Query replacement prevents a corrected query resurrecting removed rows.
        latest_queries = {}
        for m, payload in play_sources:
            key = digest({k: v for k, v in m['parameters'].items() if k not in ('endpoint_status', 'error_payload_sanitized')})
            previous = latest_queries.get(key)
            if previous and utc(previous[0]['available_at']) == utc(m['available_at']) and previous[1] != payload:
                raise ValueError('CONFLICTING_PLAY_REVISION')
            latest_queries[key] = (m, payload)
        latest_plays = {}; play_conflicts = set()
        for m, payload in sorted(latest_queries.values(), key=lambda x: (utc(x[0]['available_at']), x[0]['snapshot_id'])):
            seen = set()
            for p in payload:
                counts['source_play_rows'] += 1
                key = (str(p['gameId']), str(p['id']))
                if key in seen: play_conflicts.add(key)
                seen.add(key)
                previous = latest_plays.get(key)
                if previous:
                    counts['overlapping_play_rows'] += 1
                    if utc(previous[1]['available_at']) == utc(m['available_at']) and previous[0] != p:
                        play_conflicts.add(key)
                latest_plays[key] = (p, m)
        # A conflicting duplicate invalidates its game, not just the offending row.
        bad_games = {g for g, p in play_conflicts} | game_conflicts
        self.plays = []
        for (event, play_id), (p, pm) in sorted(latest_plays.items()):
            reason = None; pair = self.games.get(event)
            if event in bad_games: reason = 'CONFLICTING_SOURCE_GAME'
            elif pair is None: reason = 'MISSING_GAME_IDENTITY'
            else:
                g, gm = pair
                start = utc(g['startDate'])
                params = pm['parameters']
                if any(params.get(k) is not None and params[k] != g.get(field) for k, field in (('year', 'season'), ('week', 'week'), ('seasonType', 'seasonType'))):
                    reason = 'PLAY_QUERY_SCOPE_MISMATCH'
                elif g.get('completed') is not True: reason = 'GAME_NOT_COMPLETED'
                elif start >= utc(gm['available_at']): reason = 'LOOKAHEAD_RISK'
                elif not utc(self.as_of) - timedelta(days=lookback_days) <= start < utc(self.as_of): reason = 'OUTSIDE_LOOKBACK'
                elif {p['offense'], p['defense']} != {g['homeTeam'], g['awayTeam']}: reason = 'PLAY_TEAM_IDENTITY_MISMATCH'
                elif any(isinstance(p.get(k), bool) for k in ('down', 'distance', 'yardsGained', 'ppa')): reason = 'INVALID_PLAY_VALUE'
                elif not isinstance(p.get('distance'), (int, float)) or p['distance'] <= 0: reason = 'INVALID_PLAY_DISTANCE'
            if reason:
                counts[reason] += 1; continue
            facts, rejected = normalize_cfbd_plays([p], pm, game_observed_times={event: gm['available_at']})
            if not facts:
                counts['UNSUPPORTED_OR_INCOMPLETE_PLAY'] += 1; continue
            # Provider play IDs are scoped to games; overlaps never count twice.
            self.plays.append(replace(facts[0], play_id=event + ':' + play_id))
        self.by_team = defaultdict(list)
        for p in self.plays: self.by_team[p.offense].append(p)
        self.attack, self.conceded = adjusted_efficiency(self.plays, 'ppa')
        self.counts = dict(counts)
        self.counts.update(eligible_play_rows=len(self.plays), prior_games=len({p.event_id for p in self.plays}),
                           teams=len(self.by_team), ppa_missing=sum(p.ppa is None for p in self.plays),
                           conflicting_games=len(bad_games))
        self.available_at = max((utc(m['available_at']) for m, _ in game_sources + play_sources), default=utc(self.as_of)).isoformat()

    def materialize(self, *, event_id, home_team, away_team, minimum_plays=100, minimum_games=3):
        if any(isinstance(x, bool) or not isinstance(x, int) or x < 1 for x in (minimum_plays, minimum_games)):
            raise ValueError('INVALID_FEATURE_POLICY')
        pair = self.games.get(str(event_id))
        if pair is None or str(event_id) in self.game_conflicts: raise ValueError('EVENT_MAPPING_UNVERIFIED')
        g, _ = pair
        if (home_team, away_team) != (g['homeTeam'], g['awayTeam']): raise ValueError('EVENT_MAPPING_UNVERIFIED')
        if g.get('completed') or utc(g['startDate']) <= utc(self.as_of) or any(p.event_id == str(event_id) for p in self.plays):
            raise ValueError('LOOKAHEAD_RISK')
        if g.get('startTimeTBD') is not False: raise ValueError('EVENT_START_UNCONFIRMED')
        teams = {t: self.by_team[t] for t in (home_team, away_team)}
        if any(len(p) < minimum_plays or len({v.event_id for v in p}) < minimum_games for p in teams.values()):
            raise ValueError('INSUFFICIENT_PRIOR_PLAY_DATA')
        def success(p): return p.yards >= p.distance * (.5 if p.down == 1 else .7 if p.down == 2 else 1)
        rates = {t: sum(success(p) for p in rows) / len(rows) for t, rows in teams.items()}
        values = dict(success_rate_diff=rates[home_team] - rates[away_team], success_rate_sum=rates[home_team] + rates[away_team],
                      plays_sum=sum(len(rows) / len({p.event_id for p in rows}) for rows in teams.values()))
        ppa_coverage = {t: [p for p in rows if p.ppa is not None] for t, rows in teams.items()}
        if all(t in self.attack and t in self.conceded and len(p) >= minimum_plays and len({v.event_id for v in p}) >= minimum_games for t, p in ppa_coverage.items()):
            values['ppa_diff'] = self.attack[home_team] - self.attack[away_team]
        body = dict(algorithm_version=VERSION, home_team=home_team, away_team=away_team, event_id=str(event_id), sport='CFB',
                    as_of=self.as_of, lookback_days=self.lookback_days, minimum_plays=minimum_plays, minimum_games=minimum_games,
                    plays_snapshot_ids=self.play_ids, results_snapshot_ids=self.result_ids,
                    source_snapshots=sorted(set(self.play_ids + self.result_ids)), values=values)
        fingerprint = digest(body)
        self.store._immutable(self.store.root/'features'/(fingerprint+'.json'), json.dumps(body, sort_keys=True, allow_nan=False, indent=2).encode())
        features = FeatureSnapshot(str(event_id), 'CFB', self.as_of,
            {k: FeatureValue(v, VERSION, self.available_at, self.available_at, 'derived-'+fingerprint, fingerprint) for k, v in values.items()})
        features.validate(self.as_of)
        return features


def reproduce_features(store, body):
    history = RollingCFBHistory(store, plays_snapshot_ids=body['plays_snapshot_ids'], results_snapshot_ids=body['results_snapshot_ids'],
                                as_of=body['as_of'], lookback_days=body['lookback_days'])
    return history.materialize(event_id=body['event_id'], home_team=body['home_team'], away_team=body['away_team'],
                               minimum_plays=body['minimum_plays'], minimum_games=body['minimum_games'])
