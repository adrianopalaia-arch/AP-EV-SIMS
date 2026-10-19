"""NFL availability policy. Changes assumptions/eligibility, never invents an adjustment.

Roster active != game active != starter != known workload. All times are UTC.
Policy reviews preserve the numerical baseline and never create a new scored cohort.
"""
from copy import deepcopy
from pathlib import Path
import json

from .integrity import digest, utc
from .research_store import ResearchStore

VERSION = 'nfl-availability-policy-v1'
MAX_REPORT_AGE_SECONDS = 48 * 3600
MAX_CAPTURE_AGE_SECONDS = 6 * 3600
OUT_STATES = {'CONFIRMED_OUT', 'REPORTED_OUT', 'REPORTED_UNAVAILABLE'}


def _state(status, official=False):
    value = str(status or '').strip().lower().replace('_', ' ').replace('-', ' ')
    if value in {'out', 'inactive', 'injured reserve', 'suspended', 'reserve/pup'}:
        return 'CONFIRMED_OUT' if official else 'REPORTED_OUT'
    if value == 'questionable':
        return 'QUESTIONABLE'
    if value in {'doubtful', 'day to day'}:
        return 'DOUBTFUL' if value == 'doubtful' else 'QUESTIONABLE'
    if value in {'active', 'available'}:
        return 'CONFIRMED_ACTIVE' if official else 'REPORTED_ACTIVE'
    return 'UNKNOWN'


def _source(manifest):
    return dict(source_manifest=manifest['manifest_id'], source_hash=manifest['hash'],
                available_at=manifest['captured_at'])


def interpret_nfl(event, players, payload, manifest):
    """Bind each ESPN injury to its event, team, player and actual source capture.

    ESPN is a secondary report, not an official gameday active/starter feed.
    Old medical updates remain visible but do not establish a current status.
    """
    from .nfl_schedule import team
    at = manifest['captured_at']
    if utc(at) >= utc(event['event_start']):
        raise ValueError('AVAILABILITY_NOT_PREGAME')
    header = payload.get('header', {})
    competitions = header.get('competitions', [])
    if (str(header.get('id')) != str(event['availability_event_id']) or len(competitions) != 1
            or utc(competitions[0]['date']) != utc(event['event_start'])):
        raise ValueError('AVAILABILITY_EVENT_MISMATCH')
    competitors = competitions[0]['competitors']
    if {c['team']['displayName'] for c in competitors} != {event['home_team'], event['away_team']}:
        raise ValueError('AVAILABILITY_TEAM_MISMATCH')
    team_ids = {str(c['team']['id']): event[c['homeAway'] + '_code'] for c in competitors}
    injuries = {}
    for group in payload.get('injuries', []):
        tid = str(group.get('team', {}).get('id'))
        if tid not in team_ids:
            raise ValueError('INJURY_TEAM_MISMATCH')
        for item in group.get('injuries', []):
            pid = str(item.get('athlete', {}).get('id'))
            if pid == 'None':
                continue
            athlete_team = item.get('athlete', {}).get('team', {}).get('id')
            if athlete_team is not None and str(athlete_team) != tid:
                raise ValueError('INJURY_TEAM_MISMATCH')
            injuries.setdefault((team_ids[tid], pid), []).append(item)
    result = []
    seen = set()
    for person in players:
        if person['player_id'] in seen:
            raise ValueError('DUPLICATE_ROSTER_PLAYER_IDENTITY')
        seen.add(person['player_id'])
        tid = team(person['team_id'])
        if tid not in team_ids.values():
            raise ValueError('ROSTER_TEAM_MISMATCH')
        pid = str(person['provider_player_id'])
        if any(p == pid and t != tid for t, p in injuries):
            raise ValueError('INJURY_PLAYER_TEAM_MISMATCH')
        roster_source = person.get('roster_source')
        evidence = []
        bound = [(x, manifest, 'EVENT_INJURY_REPORT') for x in injuries.get((tid, pid), [])]
        if roster_source:
            bound += [(x, roster_source, 'ROSTER_INJURY_REPORT') for x in person.get('injuries', [])]
        for item, source, kind in bound:
            observed = item.get('date')
            reason = None
            try:
                if utc(source['captured_at']) > utc(at):
                    reason = 'LOOKAHEAD_RISK'
                elif not observed:
                    reason = 'HISTORICAL_AVAILABILITY_UNVERIFIED'
                elif utc(observed) > utc(source['captured_at']):
                    reason = 'LOOKAHEAD_RISK'
                elif (utc(at) - utc(observed)).total_seconds() > MAX_REPORT_AGE_SECONDS:
                    reason = 'STALE_INJURY_REPORT'
            except (ValueError, TypeError):
                reason = 'INVALID_INJURY_TIMESTAMP'
            evidence.append(dict(event_id=event['event_id'], event_start=event['event_start'],
                player_id=person['player_id'], team_id=tid, status=item.get('status'),
                state=_state(item.get('status')), observed_at=observed, source_kind=kind,
                source_authority='SECONDARY_AGGREGATOR', usable=reason is None, reason=reason,
                **_source(source)))
        usable = [e for e in evidence if e['usable']]
        latest = max((utc(e['observed_at']) for e in usable), default=None)
        states = {e['state'] for e in usable if utc(e['observed_at']) == latest}
        state = next(iter(states)) if len(states) == 1 else 'UNKNOWN'
        reasons = ['ROLE_NOT_CONFIRMED', 'NEWS_ADJUSTMENT_UNAVAILABLE']
        if len(states) > 1:
            reasons.append('CONFLICTING_AVAILABILITY_REPORTS')
        reasons.extend(e['reason'] for e in evidence if e['reason'])
        if state in OUT_STATES:
            reasons.append('PLAYER_REPORTED_OUT')
        if state in {'QUESTIONABLE', 'DOUBTFUL'}:
            reasons.append('PARTICIPATION_UNCERTAIN')
        if state != 'CONFIRMED_ACTIVE':
            reasons.append('PARTICIPATION_NOT_CONFIRMED')
        if header.get('season', {}).get('type') != 2:
            reasons.append('MODEL_COMPETITION_DOMAIN_MISMATCH')
        result.append(dict(sport='NFL', event_id=event['event_id'], event_start=event['event_start'],
            player_id=person['player_id'], provider_player_id=pid, player_name=person['name'], team_id=tid,
            position=person['position'], availability_state=state, injury_evidence=evidence,
            injury_coverage='REPORTED_ITEMS_ONLY_NOT_COMPLETE_MEDICAL_CLEARANCE',
            roster_status=person.get('status'), roster_membership_verified=bool(roster_source),
            roster_source=roster_source, role_confirmed=False, confirmed_starter=None,
            confirmed_minutes=None, confirmed_ice_time=None, batting_order=None,
            **_source(manifest), reasons=sorted(set(reasons))))
    return result


def player_context(forecast, person, at):
    """Reassess evidence at the decision time, including an older frozen forecast."""
    if utc(at) >= utc(forecast['event_start']):
        raise ValueError('PREGAME_AVAILABILITY_REQUIRED')
    if person is None:
        return dict(policy_version=VERSION, availability_state='UNKNOWN',
            adjustment_status='NEWS_ADJUSTMENT_UNAVAILABLE', adjustment_applied=False,
            scoring_recommendation_eligible=False, eligible_projected_opportunity=None,
            reasons=['PLAYER_NOT_ON_VERIFIED_CURRENT_ROSTER', 'NEWS_ADJUSTMENT_UNAVAILABLE'],
            decision_timestamp=at)
    if utc(forecast.get('generated_at', at)) > utc(at):
        raise ValueError('FORECAST_LOOKAHEAD_RISK')
    for key in ('sport', 'event_id', 'player_id', 'team_id'):
        if str(person.get(key)) != str(forecast.get(key)):
            raise ValueError('AVAILABILITY_' + key.upper() + '_MISMATCH')
    if utc(person['event_start']) != utc(forecast['event_start']):
        raise ValueError('AVAILABILITY_EVENT_START_MISMATCH')
    if utc(person['available_at']) > utc(at):
        raise ValueError('AVAILABILITY_LOOKAHEAD_RISK')
    reasons = list(person.get('reasons', [])) + ['NEWS_ADJUSTMENT_UNAVAILABLE', 'WORKLOAD_NOT_CONFIRMED']
    state = person.get('availability_state', 'UNKNOWN')
    if (utc(at) - utc(person['available_at'])).total_seconds() > MAX_CAPTURE_AGE_SECONDS:
        reasons.append('STALE_AVAILABILITY_SNAPSHOT')
        state = 'UNKNOWN'
    if not person.get('roster_membership_verified'):
        reasons.append('ROSTER_MEMBERSHIP_UNVERIFIED')
    roster = person.get('roster_source')
    if roster:
        if utc(roster['captured_at']) > utc(at):
            raise ValueError('ROSTER_LOOKAHEAD_RISK')
        if (utc(at) - utc(roster['captured_at'])).total_seconds() > MAX_CAPTURE_AGE_SECONDS:
            reasons.append('STALE_ROSTER_SNAPSHOT')
    if person.get('roster_status') in {'practice-squad', 'inactive', 'injured-reserve', 'suspended'}:
        reasons.append('ROSTER_NOT_ACTIVE_GAME_ELIGIBLE')
    evidence = person.get('injury_evidence', [])
    valid = []
    for item in evidence:
        for key in ('event_id', 'event_start', 'player_id', 'team_id'):
            if key not in item or (utc(item[key]) != utc(person[key]) if key == 'event_start' else item[key] != person[key]):
                raise ValueError('INJURY_IDENTITY_MISMATCH')
        provenance = bool(item.get('source_manifest') and item.get('source_hash'))
        if not provenance:
            reasons.append('INJURY_PROVENANCE_UNVERIFIED')
        try:
            available = utc(item['available_at'])
            observed = utc(item['observed_at']) if item.get('observed_at') else None
            if available > utc(at) or (observed and observed > available):
                raise ValueError('INJURY_LOOKAHEAD_RISK')
        except (KeyError, TypeError):
            reasons.append('HISTORICAL_AVAILABILITY_UNVERIFIED')
            continue
        if not observed:
            reasons.append('HISTORICAL_AVAILABILITY_UNVERIFIED')
        elif (utc(at) - observed).total_seconds() > MAX_REPORT_AGE_SECONDS:
            reasons.append('STALE_INJURY_REPORT')
        elif provenance and item.get('usable') and all(item.get(k) == person[k] for k in ('event_id', 'player_id', 'team_id')):
            valid.append(item)
        if item.get('reason'):
            reasons.append(item['reason'])
    # No caller-supplied state alone can establish an out/active/starting status.
    latest = max((utc(i['observed_at']) for i in valid), default=None)
    states = {_state(i['status'], i.get('source_authority') == 'LEAGUE_OFFICIAL'
                     and i.get('source_kind') == 'GAME_STATUS')
              for i in valid if utc(i['observed_at']) == latest}
    state = next(iter(states)) if len(states) == 1 else 'UNKNOWN'
    if len(states) > 1:
        reasons.append('CONFLICTING_AVAILABILITY_REPORTS')
    if 'STALE_AVAILABILITY_SNAPSHOT' in reasons:
        state = 'UNKNOWN'
    if state in OUT_STATES:
        reasons.append('PLAYER_REPORTED_OUT')
    elif state != 'CONFIRMED_ACTIVE':
        reasons.append('PARTICIPATION_NOT_CONFIRMED')
    if state in {'QUESTIONABLE', 'DOUBTFUL'}:
        reasons.append('PARTICIPATION_UNCERTAIN')
    if forecast.get('projection', {}).get('last_team_id', forecast['team_id']) != person['team_id']:
        reasons.append('TEAM_CHANGE_ROLE_UNVERIFIED')
    return dict(policy_version=VERSION, availability_state=state, decision_timestamp=at,
        adjustment_status='NEWS_ADJUSTMENT_UNAVAILABLE', adjustment_applied=False,
        scoring_recommendation_eligible=False, eligible_projected_opportunity=None,
        baseline_projected_opportunity=forecast.get('projection', {}).get('projected_opportunity'),
        workload_basis='Historical appearances only; not injury-adjusted or guaranteed',
        role_confirmed=False, roster_status=person.get('roster_status'),
        source_manifest=person.get('source_manifest'), source_hash=person.get('source_hash'),
        available_at=person['available_at'], evidence=evidence,
        reasons=sorted(set(reasons)))


def game_context(game, news, at):
    """Retain the margin baseline; never substitute an unsupported QB adjustment."""
    reasons = ['NEWS_ADJUSTMENT_UNAVAILABLE', 'QB_REPLACEMENT_MODEL_UNAVAILABLE']
    qbs = []
    if news is None:
        reasons.append('AVAILABILITY_UNAVAILABLE')
    else:
        if digest({k: v for k, v in news.items() if k != 'snapshot_hash'}) != news['snapshot_hash']:
            raise ValueError('AVAILABILITY_SNAPSHOT_HASH_MISMATCH')
        if news['event']['event_id'] != game['event_id'] or utc(news['event']['event_start']) != utc(game['event_start']):
            raise ValueError('AVAILABILITY_EVENT_MISMATCH')
        if utc(news['latest_source_capture']) > utc(at):
            raise ValueError('AVAILABILITY_LOOKAHEAD_RISK')
        for person in news['records']:
            if person['team_id'] not in {game['home_code'], game['away_code']}:
                raise ValueError('AVAILABILITY_TEAM_MISMATCH')
            f = dict(sport='NFL', event_id=game['event_id'], event_start=game['event_start'],
                     team_id=person['team_id'], player_id=person['player_id'])
            context = player_context(f, person, at)
            if person.get('position') == 'QB':
                # A starter flag must itself have bound, timely game-status evidence.
                starter = any(i.get('source_kind') == 'GAME_STATUS' and i.get('source_authority') == 'LEAGUE_OFFICIAL'
                              and i.get('confirmed_starter') is True and i.get('usable')
                              and i.get('event_id') == game['event_id'] and i.get('player_id') == person['player_id']
                              and i.get('team_id') == person['team_id'] and i.get('observed_at')
                              and 0 <= (utc(at)-utc(i['observed_at'])).total_seconds() <= MAX_REPORT_AGE_SECONDS
                              for i in person.get('injury_evidence', []))
                qbs.append(dict(player_id=person['player_id'], player_name=person['player_name'], team_id=person['team_id'],
                    starter_confirmed=starter, availability_state=context['availability_state'],
                    source_manifest=context.get('source_manifest'), reasons=context['reasons']))
                if context['availability_state'] in OUT_STATES:
                    reasons.append('STARTING_QB_OUT' if starter else 'QB_REPORTED_UNAVAILABLE')
        for side in ('home_code', 'away_code'):
            starters = [q for q in qbs if q['team_id'] == game[side] and q['starter_confirmed']]
            if len(starters) != 1:
                reasons.append('QB_STARTER_UNVERIFIED')
    return dict(policy_version=VERSION, adjustment_status='NEWS_ADJUSTMENT_UNAVAILABLE',
        adjustment_applied=False, baseline_retained=True, quarterbacks=qbs, decision_timestamp=at,
        availability_snapshot=news['snapshot_hash'] if news else None,
        scoring_recommendation_eligible=False, reasons=sorted(set(reasons)),
        numerical_forecast_basis='Team-strength baseline; no supported QB replacement or injury/workload model')


def revise_prop(store, original, person, news, at):
    """Append an eligibility revision; leave the first frozen record byte-identical."""
    if digest({k: v for k, v in original.items() if k != 'forecast_hash'}) != original['forecast_hash']:
        raise ValueError('FROZEN_FORECAST_HASH_MISMATCH')
    if digest({k: v for k, v in news.items() if k != 'snapshot_hash'}) != news['snapshot_hash']:
        raise ValueError('AVAILABILITY_SNAPSHOT_HASH_MISMATCH')
    if news['event']['event_id'] != original['event_id'] or utc(news['event']['event_start']) != utc(original['event_start']):
        raise ValueError('AVAILABILITY_EVENT_MISMATCH')
    if not max(utc(original['generated_at']),utc(news['latest_source_capture'])) <= utc(at) < utc(original['event_start']):
        raise ValueError('PREGAME_REVISION_REQUIRED')
    context = player_context(original, person, at)
    if person is not None and not any(digest(p)==digest(person) for p in news['records']):
        raise ValueError('AVAILABILITY_RECORD_NOT_IN_SNAPSHOT')
    # Short partition keeps Windows paths bounded; full hashes still validate identity.
    folder = store.root / 'predictions/news' / original.get('original_forecast_hash',original['forecast_hash'])[:8]
    folder.mkdir(parents=True,exist_ok=True)
    parent = original['forecast_hash']
    previous = []
    for path in folder.glob('*.json'):
        old = json.loads(path.read_text())
        if old.get('original_forecast_hash') != original.get('original_forecast_hash',original['forecast_hash']):
            continue
        if digest({k:v for k,v in old.items() if k!='forecast_hash'}) != old['forecast_hash']:
            raise ValueError('FROZEN_FORECAST_HASH_MISMATCH')
        if utc(old['generated_at']) <= utc(at):
            previous.append(old)
    if previous:
        prior = max(previous,key=lambda f:(utc(f['generated_at']),f['forecast_hash']))
        if prior.get('availability_snapshot')==news['snapshot_hash'] and prior.get('availability_context')==context:
            return prior
        parent=prior['forecast_hash']
    body = deepcopy(original)
    body.pop('forecast_hash')
    body.update(generated_at=at, latest_source_capture=max(original['latest_source_capture'], news['latest_source_capture']),
        original_forecast_hash=original.get('original_forecast_hash', original['forecast_hash']),
        parent_forecast_hash=parent, baseline_generated_at=original.get('baseline_generated_at', original['generated_at']),
        forecast_policy_version=VERSION, revision_kind='ASSUMPTIONS_AND_ELIGIBILITY_ONLY',
        revision_reasons=context['reasons'], availability_snapshot=news['snapshot_hash'], availability_context=context,
        role_confirmed=False, conditional_on='Historical appearance baseline only; current participation/workload unsupported',
        scoring_recommendation_eligible=False, eligible_projected_opportunity=None,
        decision='PASS', recommendations_enabled=False, calibrated_probability=None, p_low=None,
        pass_reasons=sorted(set(original['pass_reasons'] + context['reasons'])),
        evaluation_cohort='SAME_NUMERICAL_BASELINE_NOT_AN_ADDITIONAL_INDEPENDENT_PREDICTION')
    body['forecast_hash'] = digest(body)
    store._immutable(folder / (body['forecast_hash'] + '.json'), json.dumps(body, sort_keys=True, allow_nan=False).encode())
    return body
