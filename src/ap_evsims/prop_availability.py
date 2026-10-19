"""Capture pregame availability without turning a roster into a confirmed role."""
from datetime import datetime,timezone
import json
from pathlib import Path
from .integrity import digest,utc
from .prop_prospective import current_inputs
from .providers.public_stats import PublicStatsArchive
from .publication import atomic_json
from .research_store import ResearchStore


def injury_evidence(items,captured_at):
    records=[]
    for item in items or []:
        observed=item.get('date');reason=None
        if observed:
            try:
                if utc(observed)>utc(captured_at):reason='LOOKAHEAD_RISK'
            except ValueError:reason='INVALID_INJURY_TIMESTAMP'
        records.append(dict(status=item.get('status'),observed_at=observed,available_at=captured_at,
            body_part=item.get('details',{}).get('type'),usable=reason is None,reason=reason))
    return records


def interpret(sport,event,players,payload,manifest):
    """Only explicit pregame source fields may establish a listed lineup.

    Missing injury rows mean unknown coverage, not healthy. Goalie leaders and
    probable pitchers do not establish a confirmed starter. Expected workload
    remains a separate model projection rather than sourced participation proof.
    """
    if sport=='NFL':
        from .nfl_forecast_news import interpret_nfl
        return interpret_nfl(event,players,payload,manifest)
    at=manifest['captured_at']
    if utc(at)>=utc(event['event_start']):raise ValueError('AVAILABILITY_NOT_PREGAME')
    if sport in ('NBA','NFL'):
        header=payload.get('header',{})
        if str(header.get('id'))!=str(event['availability_event_id']):raise ValueError('AVAILABILITY_EVENT_MISMATCH')
        cs=header.get('competitions',[])
        if len(cs)!=1 or utc(cs[0]['date'])!=utc(event['event_start']):raise ValueError('AVAILABILITY_EVENT_MISMATCH')
        if {c['team']['displayName'] for c in cs[0]['competitors']}!={event['home_team'],event['away_team']}:raise ValueError('AVAILABILITY_TEAM_MISMATCH')
        groups=payload.get('injuries',[]);injuries={str(i['athlete']['id']):i for g in groups for i in g.get('injuries',[]) if i.get('athlete',{}).get('id')}
        expected_regular=header.get('season',{}).get('type')==2
    elif sport=='NHL':
        if str(payload.get('id'))!=event['event_id'] or utc(payload['startTimeUTC'])!=utc(event['event_start']):raise ValueError('AVAILABILITY_EVENT_MISMATCH')
        injuries={};expected_regular=payload.get('gameType')==2
    else:
        # Official boxscore URLs bind the canonical game ID; both team names
        # must independently match. A full listed batting order is required.
        teams=payload.get('teams',{})
        if {t.get('team',{}).get('name') for t in teams.values()}!={event['home_team'],event['away_team']}:raise ValueError('AVAILABILITY_TEAM_MISMATCH')
        injuries={};expected_regular=event.get('competition_type')=='R' if event.get('competition_type') is not None else None
    out=[]
    for person in players:
        evidence=injury_evidence([injuries[person.get('provider_player_id',person['player_id'])]] if person.get('provider_player_id',person['player_id']) in injuries else person.get('injuries'),at)
        state='UNKNOWN';order=None;reason=['PARTICIPATION_NOT_CONFIRMED','ROLE_NOT_CONFIRMED']
        if evidence:reason.append('INJURY_OR_RESTRICTION_REPORTED')
        if any(not r['usable'] for r in evidence):reason.append('INJURY_TIMESTAMP_INVALID')
        if any(str(r['status']).lower() in ('out','injured reserve','suspended') for r in evidence if r['usable']):state='REPORTED_UNAVAILABLE';reason.append('PLAYER_REPORTED_OUT')
        if sport=='MLB':
            t=next((t for t in teams.values() if str(t['team']['id'])==person['team_id']),None)
            batting=[str(i) for i in (t or {}).get('battingOrder',[])]
            if len(batting)==9 and len(set(batting))==9 and person['player_id'] in batting:
                if state!='REPORTED_UNAVAILABLE':state='OFFICIAL_BATTING_ORDER_LISTED'
                order=batting.index(person['player_id'])+1
                reason=[r for r in reason if r not in ('PARTICIPATION_NOT_CONFIRMED','ROLE_NOT_CONFIRMED')]+['LATE_SCRATCH_RECHECK_REQUIRED'];role=True
            else:role=False
        else:role=False
        if sport=='NHL' and person['position']=='G':reason.append('STARTING_GOALIE_NOT_CONFIRMED')
        if expected_regular is False:reason.append('MODEL_COMPETITION_DOMAIN_MISMATCH')
        out.append(dict(sport=sport,event_id=event['event_id'],event_start=event['event_start'],player_id=person['player_id'],player_name=person['name'],team_id=person['team_id'],position=person['position'],
            availability_state=state,injury_evidence=evidence,injury_coverage='REPORTED_ITEMS_ONLY_NOT_COMPLETE_MEDICAL_CLEARANCE',
            role_confirmed=role,batting_order=order,confirmed_minutes=None,confirmed_ice_time=None,confirmed_starter=None,
            source_manifest=manifest['manifest_id'],source_hash=manifest['hash'],available_at=at,reasons=reason))
    return out


def capture(root,sport,canonical_event=None):
    if sport=='NFL' and canonical_event is None:
        from .nfl_schedule import next_slate
        reports=[];failures=[];games=next_slate(root)
        for event in games:
            try:reports.append(capture(root,sport,event))
            except (ValueError,KeyError,OSError,TypeError) as e:failures.append(dict(event_id=event['event_id'],status='AVAILABILITY_UNAVAILABLE',error_category=type(e).__name__))
        body=dict(sport=sport,generated_at=datetime.now(timezone.utc).isoformat(),events=games,
            records=[p for r in reports for p in r['records']],event_identity_reasons=sorted({x for r in reports for x in r['event_identity_reasons']}),
            snapshots=[r['snapshot_hash'] for r in reports],failures=failures,recommendations_enabled=False)
        atomic_json(Path(root)/'outputs/nfl_availability.json',body);return body
    root=Path(root);a=PublicStatsArchive(root/'data');event,players,sources,reasons=current_inputs(root,sport,canonical_event)
    if event is None:raise ValueError('CURRENT_EVENT_IDENTITY_UNVERIFIED')
    if sport in ('NBA','NFL'):
        url='https://site.api.espn.com/apis/site/v2/sports/'+('football/nfl' if sport=='NFL' else 'basketball/nba')+'/summary?event='+event['availability_event_id']
    elif sport=='NHL':url='https://api-web.nhle.com/v1/gamecenter/'+event['event_id']+'/landing'
    else:url='https://statsapi.mlb.com/api/v1/game/'+event['event_id']+'/boxscore'
    m=a.capture(sport,url)
    if (datetime.now(timezone.utc)-utc(m['captured_at'])).total_seconds()>300:m=a.capture(sport,url,refresh=True)
    payload=a.read(m);sources.append(m);records=interpret(sport,event,players,payload,m)
    at=datetime.now(timezone.utc).isoformat()
    body=dict(sport=sport,event=event,generated_at=at,latest_source_capture=max(s['captured_at'] for s in sources),
        sources=[dict(manifest_id=s['manifest_id'],hash=s['hash'],captured_at=s['captured_at'],url=s['url']) for s in sources],
        authority='SECONDARY_AGGREGATOR' if sport in ('NBA','NFL') else 'LEAGUE_API',records=records,
        identities=[dict(player_id=p['player_id'],aliases=p['aliases'],team_id=p['team_id']) for p in players],
        event_identity_reasons=reasons,recommendations_enabled=False)
    body['snapshot_hash']=digest(body)
    folder=root/'data/evaluations/availability';folder.mkdir(exist_ok=True)
    ResearchStore._immutable(folder/(body['snapshot_hash']+'.json'),json.dumps(body,sort_keys=True,indent=2).encode())
    if canonical_event is None:atomic_json(root/'outputs'/(sport.lower()+'_availability.json'),body)
    return body
