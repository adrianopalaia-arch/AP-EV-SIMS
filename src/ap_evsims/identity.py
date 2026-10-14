"""Exact, source-backed identity joins. Ambiguous aliases and start revisions fail closed."""
import json,re
from .integrity import digest,utc

def normalized_name(value):
    return re.sub(r'\s+',' ',value.strip()).casefold()

def map_cfb_events(teams,games,events, *, alias_snapshot,game_snapshot,available_at):
    if not alias_snapshot or not game_snapshot:raise ValueError('MISSING_IDENTITY_PROVENANCE')
    aliases={}
    for team in teams:
        school=team.get('school');identity=team.get('id')
        if not school or identity is None:continue
        names=[school]+list(team.get('alternateNames') or [])
        if team.get('mascot'):names += [n+' '+team['mascot'] for n in list(names)]
        for name in names:aliases.setdefault(normalized_name(name),set()).add(identity)
    mapped={};rejected=[]
    for event in events:
        try:
            candidates=[]
            home=aliases.get(normalized_name(event['home_team']),set());away=aliases.get(normalized_name(event['away_team']),set())
            if len(home)!=1 or len(away)!=1:raise ValueError('TEAM_ALIAS_AMBIGUOUS_OR_MISSING')
            if home==away:raise ValueError('EVENT_IDENTITY_COLLISION')
            for game in games:
                if game.get('homeId') in home and game.get('awayId') in away and utc(game['startDate'])==utc(event['commence_time']):
                    candidates.append(game)
            unique={str(g['id']):g for g in candidates}
            if len(unique)!=1:raise ValueError('EVENT_START_OR_IDENTITY_UNVERIFIED')
            game=next(iter(unique.values()))
            if game.get('startTimeTBD') is not False:raise ValueError('EVENT_START_UNCONFIRMED')
            mapping=dict(event_id=str(game['id']),home_team=event['home_team'],away_team=event['away_team'],
                cfbd_home_team=game['homeTeam'],cfbd_away_team=game['awayTeam'],event_start=utc(game['startDate']).isoformat(),
                home_id=game['homeId'],away_id=game['awayId'],alias_source=alias_snapshot,
                game_snapshot=game_snapshot,available_at=available_at,season=game['season'])
            if event['id'] in mapped and mapped[event['id']]!=mapping:raise ValueError('EVENT_IDENTITY_COLLISION')
            mapped[event['id']]=mapping
        except (KeyError,TypeError,ValueError) as error:
            rejected.append(dict(event_id=event.get('id'),reason=str(error)))
            mapped.pop(event.get('id'),None)
    return mapped,rejected

def reconcile_cfb(warehouse,as_of):
    """Current mapping is usable only after its actual sources were available."""
    with warehouse.connect() as db:
        team=db.execute("SELECT snapshot_id,available_at FROM snapshots WHERE provider='cfbd' AND dataset='teams' AND available_at<=? ORDER BY available_at DESC LIMIT 1",[as_of]).fetchone()
        game_sources=db.execute("SELECT snapshot_id,available_at,parameters FROM snapshots WHERE provider='cfbd' AND dataset='games' AND available_at<=? ORDER BY available_at DESC",[as_of]).fetchall()
        event_rows=db.execute("SELECT event_id,event_start,home_team,away_team,min(available_at) FROM odds_quotes WHERE sport='CFB' AND available_at<=? GROUP BY ALL",[as_of]).fetchall()
    if not team or not game_sources:raise ValueError('MISSING_LOCAL_DATA')
    teams=warehouse.local_records('cfbd','teams',as_of,snapshot_id=team[0])
    # Latest revision per query; overlapping queries still reject conflicting identities.
    queries=set();sources=[];games=[]
    for sid,at,parameters in game_sources:
        key=digest(json.loads(parameters))
        if key in queries:continue
        queries.add(key);sources.append((sid,at));games+=warehouse.local_records('cfbd','games',as_of,snapshot_id=sid)
    events=[dict(id=e.removeprefix('odds:'),commence_time=t.isoformat(),home_team=h,away_team=a) for e,t,h,a,_ in event_rows]
    available=max([team[1]]+[at for _,at in sources]).isoformat()
    mapped,rejections=map_cfb_events(teams,games,events,alias_snapshot=team[0],game_snapshot=digest([sid for sid,_ in sources]),available_at=available)
    with warehouse.connect() as db:
        for event_id,m in mapped.items():
            existing=db.execute("SELECT canonical_event_id FROM event_mappings WHERE provider='odds' AND provider_event_id=? AND event_start=?",['odds:'+event_id,m['event_start']]).fetchone()
            if existing and existing[0]!=m['event_id']:raise ValueError('EVENT_MAPPING_MUTATION')
            db.execute('INSERT OR IGNORE INTO event_mappings VALUES (?,?,?,?,?)',['odds','odds:'+event_id,m['event_id'],m['event_start'],digest(m)])
        # Never rewrite earlier quote availability or blindly backfill historical rows.
    return dict(as_of=as_of,source_snapshots=[team[0]]+[sid for sid,_ in sources],matched=len(mapped),unmatched=len(rejections),
        events=len(events),mappings=mapped,rejections=rejections,seasons=sorted({m['season'] for m in mapped.values()}),
        historical_qualification='CURRENT_IDENTITY_PROOF_ONLY; use mapping available_at at decision time')
