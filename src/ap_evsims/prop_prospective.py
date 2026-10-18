"""Freeze conditional player research from current source-backed rosters/schedules.

No listed roster proves participation, minutes, batting order or goalie confirmation.
Exact schedule conflicts block market joins; they never shift canonical kickoff.
"""
from collections import defaultdict,Counter,deque
from datetime import datetime,timezone,timedelta
import json,math
from pathlib import Path
import statistics
import pytz
from .prop_research import OpportunityModel,PlayerOutcome,MARKETS,VERSION
from .prop_prices import normalize_props
from .providers.public_stats import PublicStatsArchive
from .research_store import ResearchStore
from .integrity import digest,utc
from .identity import normalized_name
from .display_pricing import outcome_ev


def current_inputs(root,sport,canonical_event=None):
    """Bounded first-event cohort; roster IDs, not guessed name matches."""
    if canonical_event is not None and sport=='NFL':
        from .nfl_schedule import current_rosters
        return current_rosters(root,canonical_event)
    root=Path(root);a=PublicStatsArchive(root/'data');sources=[]
    report=json.loads((root/'data/evaluations/prop-price-access.json').read_text())
    priced=next(r for r in report['sports'] if r['sport']==sport)
    event=priced.get('event');players=[]
    if event is None:return None,[],[],['NO_UPCOMING_PROVIDER_EVENT']
    def get(url,format='json'):
        m=a.capture(sport,url,format=format)
        if (datetime.now(timezone.utc)-utc(m['captured_at'])).total_seconds()>3600:
            m=a.capture(sport,url,format=format,refresh=True)
        sources.append(m);return a.read(m)
    day=utc(event['commence_time']).date().isoformat();start=event['commence_time'];eid=None;teams={}
    # Scope URLs derive from captured event metadata. The known first-event
    # cohort is checked against actual names, and is not silently generalized.
    if sport in ('NBA','NFL'):
        league='basketball/nba' if sport=='NBA' else 'football/nfl'
        p=get('https://site.api.espn.com/apis/site/v2/sports/'+league+'/scoreboard?dates='+day.replace('-',''))
        matches=[]
        for e in p['events']:
            cs={c['homeAway']:c['team'] for c in e['competitions'][0]['competitors']}
            if {normalized_name(cs[x]['displayName']) for x in ('home','away')}=={normalized_name(event['home_team']),normalized_name(event['away_team'])}:matches.append((e,cs))
        if len(matches)!=1:return None,[],sources,['EVENT_IDENTITY_UNVERIFIED']
        e,cs=matches[0];eid=e['id'];start=e['date'];teams=cs
        crosswalk={};schedule=None
        if sport=='NFL':
            roster=get('https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_2026.parquet','parquet')
            for r in roster:
                if r.get('espn_id') and r.get('gsis_id'):crosswalk.setdefault(str(r['espn_id']),set()).add(r['gsis_id'])
            schedule=get('https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv','csv')
            matches=[r for r in schedule if r.get('espn')==eid]
            if len(matches)!=1:return None,[],sources,['NFL_CANONICAL_EVENT_UNVERIFIED']
            ng=matches[0];kick=pytz.timezone('America/New_York').localize(datetime.fromisoformat(ng['gameday']+'T'+ng['gametime']),is_dst=None)
            if utc(kick)!=utc(start):return None,[],sources,['SCHEDULE_REVISION_MISMATCH']
            eid=ng['game_id']
        for side,team in teams.items():
            r=get('https://site.api.espn.com/apis/site/v2/sports/'+league+'/teams/'+team['id']+'/roster')
            if str(r['team']['id'])!=str(team['id']):raise ValueError('ROSTER_TEAM_MISMATCH')
            people=r['athletes'] if sport=='NBA' else [p for group in r['athletes'] for p in group['items']]
            for person in people:
                identity=str(person['id'])
                if sport=='NFL':
                    ids=crosswalk.get(identity,set())
                    if len(ids)!=1:continue
                    identity=next(iter(ids))
                team_id=str(team['id']) if sport=='NBA' else ng[side+'_team']
                players.append(dict(player_id=identity,provider_player_id=str(person['id']),name=person['displayName'],aliases=list({person.get('fullName',''),person['displayName']}),
                    team_id=team_id,team_name=team['displayName'],position=person.get('position',{}).get('abbreviation'),
                    injuries=person.get('injuries',[]),status=person.get('status',{}).get('type'),role_confirmed=False))
    elif sport=='NHL':
        # NHL schedules use venue calendar dates. Include the previous UTC date
        # so a North American evening game after midnight UTC is not omitted.
        p=get('https://api-web.nhle.com/v1/schedule/'+(utc(start)-timedelta(days=1)).date().isoformat())
        matches=[]
        for d in p['gameWeek']:
            for g in d['games']:
                home=g['homeTeam'];away=g['awayTeam']
                hn=home['placeName']['default']+' '+home['commonName']['default'];an=away['placeName']['default']+' '+away['commonName']['default']
                if normalized_name(hn)==normalized_name(event['home_team']) and normalized_name(an)==normalized_name(event['away_team']):matches.append((g,hn,an))
        if not matches:return None,[],sources,['EVENT_IDENTITY_UNVERIFIED']
        g,hn,an=min(matches,key=lambda x:utc(x[0]['startTimeUTC']));eid=str(g['id']);start=g['startTimeUTC']
        for key,name in (('homeTeam',hn),('awayTeam',an)):
            team=g[key]['abbrev'];r=get('https://api-web.nhle.com/v1/roster/'+team+'/current')
            for group in ('forwards','defensemen','goalies'):
                for person in r[group]:
                    namep=person['firstName']['default']+' '+person['lastName']['default']
                    players.append(dict(player_id=str(person['id']),name=namep,aliases=[namep],team_id=team,team_name=name,
                        position='G' if group=='goalies' else person['positionCode'],injuries=None,status='rostered',role_confirmed=False))
    else:
        p=get('https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate='+day+'&endDate='+(utc(event['commence_time'])+timedelta(days=2)).date().isoformat()+'&hydrate=probablePitcher')
        matches=[g for d in p['dates'] for g in d['games'] if g['teams']['home']['team']['name']==event['home_team'] and g['teams']['away']['team']['name']==event['away_team']]
        if not matches:return None,[],sources,['EVENT_IDENTITY_UNVERIFIED']
        g=min(matches,key=lambda g:utc(g['gameDate']));eid=str(g['gamePk']);start=g['gameDate']
        for side in ('home','away'):
            team=g['teams'][side]['team'];r=get(f"https://statsapi.mlb.com/api/v1/teams/{team['id']}/roster?rosterType=active")
            if r['teamId']!=team['id']:raise ValueError('ROSTER_TEAM_MISMATCH')
            for p in r['roster']:
                person=p['person'];players.append(dict(player_id=str(person['id']),name=person['fullName'],aliases=[person['fullName']],
                    team_id=str(team['id']),team_name=team['name'],position=p['position']['abbreviation'],injuries=None,
                    status=p.get('status',{}).get('code'),role_confirmed=False))
    reasons=[] if utc(start)==utc(event['commence_time']) else ['BOOK_CANONICAL_START_MISMATCH']
    canonical=dict(event_id=eid,event_start=utc(start).isoformat(),odds_event_id=event['id'],odds_event_start=event['commence_time'],
                   home_team=event['home_team'],away_team=event['away_team'],market_identity_verified=not reasons)
    if sport in ('NFL','NBA'):canonical['availability_event_id']=e['id']
    if sport=='MLB':
        canonical.update(competition_type=g.get('gameType'),rescheduled_from=g.get('rescheduledFrom'),
                         schedule_revision=g.get('description'),schedule_status=g.get('status'))
        if g.get('rescheduledFrom') and reasons:reasons.append('POSTPONED_SCHEDULE_REVISION')
    return canonical,players,sources,reasons


def restore_model(root,sport,market,status,at):
    h=status['artifact_hash'];p=Path(root)/'data/models'/(sport.lower()+'-'+market+'-'+h+'.json');body=json.loads(p.read_text())
    if digest(body)!=h or (body['sport'],body['market'],body['version'])!=(sport,market,VERSION):raise ValueError('MODEL_ARTIFACT_MISMATCH')
    if utc(body['latest_source_capture'])>utc(at):raise ValueError('MODEL_SOURCE_LOOKAHEAD')
    m=OpportunityModel(sport,market);m.n=body['training_n'];m.sum_opportunity=body['sum_opportunity'];m.sum_outcome=body['sum_outcome']
    for player,rows in body['player_histories'].items():
        for r in rows:
            v=PlayerOutcome(**r);v.validate();m.players[player].append(v)
    m.residuals.extend(body['residuals'])
    return m,body


def prop_mass(distribution,line,side='Over'):
    if side not in ('Over','Under') or isinstance(line,bool) or not math.isfinite(line):raise ValueError('INVALID_PROP_LINE')
    pmf={int(k):v for k,v in distribution.items()}
    if any(not math.isfinite(p) or p<0 for p in pmf.values()) or abs(sum(pmf.values())-1)>1e-10:raise ValueError('INVALID_PROP_DISTRIBUTION')
    win=sum(p for k,p in pmf.items() if (k>line if side=='Over' else k<line));push=sum(p for k,p in pmf.items() if k==line)
    return dict(p_win=win,p_push=push,p_loss=max(0.,1-win-push))


def freeze_prop(store,body):
    body=json.loads(json.dumps(body,allow_nan=False))
    if not utc(body['latest_source_capture'])<=utc(body['generated_at'])<utc(body['event_start']):raise ValueError('PREGAME_FREEZE_REQUIRED')
    if body['model_status']!='UNVALIDATED' or body['recommendations_enabled'] is not False or body['p_low'] is not None or body.get('calibrated_probability') is not None:raise ValueError('UNVALIDATED_AUTHORITY_ESCALATION')
    identity=digest([body[k] for k in ('sport','market','event_id','player_id','model_version')]);folder=store.root/'predictions/props';folder.mkdir(exist_ok=True)
    path=folder/(identity+'.json')
    if path.exists():
        prior=json.loads(path.read_text())
        if digest({k:v for k,v in prior.items() if k!='forecast_hash'})!=prior['forecast_hash']:raise ValueError('FROZEN_FORECAST_HASH_MISMATCH')
        return prior,False
    record=dict(body,forecast_hash=digest(body));store._immutable(path,json.dumps(record,sort_keys=True,indent=2).encode());return record,True


def run(root,sport,*,canonical_event=None):
    root=Path(root);store=ResearchStore(root/'data');a=PublicStatsArchive(store.root)
    status=json.loads((root/'outputs'/(sport.lower()+'_prop_research_status.json')).read_text())
    event,players,sources,identity_reasons=current_inputs(root,sport,canonical_event);at=datetime.now(timezone.utc).isoformat()
    if event is None:return dict(sport=sport,status='BLOCKED_IDENTITY',reasons=identity_reasons,new_frozen=0)
    if utc(at)>=utc(event['event_start']):return dict(sport=sport,status='EVENT_STARTED',new_frozen=0)
    # Recheck every model source's immutable bytes before issuing forecasts.
    manifests={}
    for p in a.folder.glob('*.json'):
        m=json.loads(p.read_text());manifests[m['manifest_id']]=m
    verified=set();models={}
    for market,model_status in status['markets'].items():
        model,body=restore_model(root,sport,market,model_status,at)
        for sid in body['source_ids']:
            if sid not in verified:a.read(manifests[sid]);verified.add(sid)
        models[market]=(model,body)
    from .prop_prices import event_price_records
    access=json.loads((store.root/'evaluations/prop-price-access.json').read_text());r=next(r for r in access['sports'] if r['sport']==sport)
    quotes=[]
    for qr in event_price_records(root,sport,event):
        qs,_=normalize_props(store,store.manifest(qr['snapshot_id']),sport,at);quotes.extend(qs)
    aliases=defaultdict(set)
    for player in players:
        for name in player['aliases']:
            if name:aliases[normalized_name(name)].add(player['player_id'])
    forecasts=[];rejects=[];new_count=0;comparable=0
    for player in players:
        for market,(model,artifact) in models.items():
            try:projection=model.predict(player['player_id'],utc(at).date().isoformat())
            except ValueError as error:
                rejects.append(dict(player_id=player['player_id'],market=market,reason=str(error)));continue
            if projection['distribution'] is None:rejects.append(dict(player_id=player['player_id'],market=market,reason='INSUFFICIENT_OOF_RESIDUALS'));continue
            if sport=='NHL' and (market=='goalie_saves')!=(player['position']=='G'):continue
            if sport=='MLB' and (market in ('pitcher_strikeouts','pitcher_outs','hits_allowed'))!=(player['position']=='P'):continue
            reasons=['MODEL_NOT_CALIBRATED','UNVERIFIED_PARTICIPATION','UNVERIFIED_ROLE','BOOK_SETTLEMENT_RULE_UNVERIFIED']+identity_reasons
            if market=='goalie_saves':reasons.append('UNCONFIRMED_GOALIE')
            if projection['last_team_id']!=player['team_id']:reasons.append('TEAM_CHANGE_ROLE_UNVERIFIED')
            if player['injuries']:reasons.append('INJURY_OR_RESTRICTION_REPORTED')
            if (utc(at).date()-datetime.fromisoformat(projection['last_observed_date']).date()).days>60:reasons.append('LONG_LAYOFF_ROLE_UNVERIFIED')
            attached=[]
            for q in quotes:
                if q['market']!=market or aliases.get(normalized_name(q['player_name']))!={player['player_id']}:continue
                mass=prop_mass(projection['distribution'],q['line'])
                peers=[x for x in quotes if x['book']!='draftkings' and x['market']==market and x['line']==q['line'] and aliases.get(normalized_name(x['player_name']))=={player['player_id']} and 'STALE_PRICE' not in x['reasons']]
                books={x['book']:x for x in peers};fresh='STALE_PRICE' not in q['reasons']
                # Without proven identical book settlement rules this is a
                # descriptive same-line price normalization, not a valid benchmark.
                normalized=statistics.median(x['over_no_vig'] for x in books.values()) if len(books)>=2 and event['market_identity_verified'] and fresh else None
                attached.append(dict(quote=q,raw_model_mass=mass,
                    research_ev_if_standard_settlement=outcome_ev(mass['p_win'],mass['p_loss'],mass['p_push'],q['over_odds']),
                    descriptive_ex_dk_no_vig=normalized,qualified_consensus_probability=None,
                    price_executable=fresh and event['market_identity_verified'],settlement_verified=False,calibrated_probability=None,p_low=None))
            if not attached:reasons.append('NO_MATCHED_PROP_PRICE')
            elif all('STALE_PRICE' in p['quote']['reasons'] for p in attached):reasons.append('STALE_PRICE')
            record=dict(sport=sport,market=market,event_id=event['event_id'],event_start=event['event_start'],player_id=player['player_id'],
                player_name=player['name'],team_id=player['team_id'],generated_at=at,model_version=VERSION,
                artifact_hash=status['markets'][market]['artifact_hash'],model_training_finished_at=status['generated_at'],
                training_source_hashes=artifact['source_hashes'],identity_source_ids=[m['manifest_id'] for m in sources],
                identity_source_hashes=[m['hash'] for m in sources],latest_source_capture=max([artifact['latest_source_capture']]+[m['captured_at'] for m in sources]),
                event_mapping=event,projection=projection,conditional_on='player appears; future workload is projected, never confirmed',
                observed_roster_status=player['status'],reported_injuries=player['injuries'],role_confirmed=False,
                priced_markets=attached,model_status='UNVALIDATED',recommendations_enabled=False,calibrated_probability=None,p_low=None,
                mode='RESEARCH_ONLY',reference_unit=22,cash_committed=0,pass_reasons=sorted(set(reasons)))
            frozen,new=freeze_prop(store,record);forecasts.append(frozen);new_count+=new
    report=dict(sport=sport,generated_at=at,status='RESEARCH_ONLY',canonical_event=event,new_frozen=new_count,
        frozen_forecasts=len(forecasts),unique_athletes=len({f['player_id'] for f in forecasts}),role_confirmed=0,
        matched_prices=sum(bool(f['priced_markets']) for f in forecasts),qualified_market_comparisons=0,
        market_identity_rejections=identity_reasons,rejections=rejects,recommendations_enabled=False,
        snapshot_count=len(sources),predictions=forecasts)
    target=root/'outputs'/(sport.lower()+'_prop_prospective.json') if canonical_event is None else root/'data/evaluations'/('prop-event-'+digest(event['event_id'])+'.json')
    target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return {k:v for k,v in report.items() if k not in ('predictions','rejections')}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--sport',choices=['NFL','NBA','NHL','MLB','all'],default='all');args=p.parse_args()
    for sport in ['NFL','NBA','NHL','MLB'] if args.sport=='all' else [args.sport]:print(json.dumps(run(args.root,sport)),flush=True)
