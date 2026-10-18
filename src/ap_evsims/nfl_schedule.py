"""Odds-independent NFL slate with explicit source and identity disagreements."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytz
from .providers.public_stats import PublicStatsArchive
from .integrity import utc, digest
from .identity import normalized_name

GAMES_URL = 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/'
ALIASES = {'LAR':'LA', 'STL':'LA', 'SD':'LAC', 'OAK':'LV', 'WSH':'WAS'}

def team(code):
    return ALIASES.get(code, code)

def kickoff(row):
    # nflverse's gameday/gametime are Eastern, including international fixtures.
    naive = datetime.fromisoformat(row['gameday']+'T'+row['gametime'])
    return pytz.timezone('America/New_York').localize(naive, is_dst=None).astimezone(timezone.utc)

def source(archive, url, fmt='json', refresh=False):
    m = archive.capture('NFL', url, format=fmt)
    if refresh and (datetime.now(timezone.utc)-utc(m['captured_at'])).total_seconds()>300:
        m = archive.capture('NFL', url, format=fmt, refresh=True)
    return m, archive.read(m)

def reconcile(rows, scoreboard, target_date):
    nfl = [r for r in rows if r['gameday']==target_date and r['game_type']=='REG']
    if len({r['game_id'] for r in nfl}) != len(nfl):
        raise ValueError('DUPLICATE_CANONICAL_EVENT')
    espn = scoreboard.get('events', [])
    if len({str(e['id']) for e in espn}) != len(espn):
        raise ValueError('DUPLICATE_SCHEDULE_EVENT')
    by_id = {str(e['id']):e for e in espn}; games=[]; used=set()
    for r in nfl:
        e=by_id.get(str(r['espn'])); reasons=[]; cs={}
        if e:
            used.add(str(e['id']))
            cs={c['homeAway']:c['team'] for c in e['competitions'][0]['competitors']}
            if any(team(cs[s]['abbreviation'])!=team(r[s+'_team']) for s in ('home','away')):
                reasons.append('SCHEDULE_TEAM_MISMATCH')
            if utc(e['date'])!=kickoff(r):reasons.append('SCHEDULE_REVISION_MISMATCH')
            if e.get('season',{}).get('type')!=2 or e.get('season',{}).get('year')!=int(r['season']):
                reasons.append('SCHEDULE_SEASON_MISMATCH')
            if e.get('week',{}).get('number')!=int(r['week']):reasons.append('SCHEDULE_WEEK_MISMATCH')
        else:reasons.append('SCHEDULE_CROSSCHECK_MISSING')
        games.append(dict(event_id=r['game_id'],event_start=kickoff(r).isoformat(),kickoff=kickoff(r).isoformat(),
            home_team=cs.get('home',{}).get('displayName',r['home_team']),away_team=cs.get('away',{}).get('displayName',r['away_team']),
            home_code=team(r['home_team']),away_code=team(r['away_team']),availability_event_id=str(r['espn']),
            season=int(r['season']),week=int(r['week']),game_stage=r['game_type'],stadium=r['stadium'],
            neutral_site=r['location']=='Neutral',espn_teams=cs,schedule_reasons=reasons,
            identity_verified=not reasons,odds_event_id=None,odds_event_start=None,market_identity_verified=False))
    # A missing counterpart is represented, never silently excluded.
    for e in espn:
        if str(e['id']) in used:continue
        cs={c['homeAway']:c['team'] for c in e['competitions'][0]['competitors']}
        games.append(dict(event_id='espn:'+str(e['id']),event_start=utc(e['date']).isoformat(),kickoff=utc(e['date']).isoformat(),
            home_team=cs['home']['displayName'],away_team=cs['away']['displayName'],home_code=team(cs['home']['abbreviation']),
            away_code=team(cs['away']['abbreviation']),availability_event_id=str(e['id']),espn_teams=cs,
            identity_verified=False,schedule_reasons=['NFLVERSE_CANONICAL_EVENT_MISSING'],odds_event_id=None,
            odds_event_start=None,market_identity_verified=False,season=e['season']['year'],week=e.get('week',{}).get('number')))
    return sorted(games,key=lambda g:(g['kickoff'],g['event_id']))

def discover(root, target_date, refresh=True):
    a=PublicStatsArchive(Path(root)/'data')
    m,rows=source(a,GAMES_URL,'csv',refresh)
    em,board=source(a,ESPN+'scoreboard?dates='+target_date.replace('-',''),refresh=refresh)
    games=reconcile(rows,board,target_date)
    at=max(m['captured_at'],em['captured_at'])
    for g in games:
        g['schedule_source_ids']=[m['manifest_id'],em['manifest_id']]
        g['schedule_source_hashes']=[m['hash'],em['hash']];g['schedule_available_at']=at
        if utc(at)>=utc(g['kickoff']):g['schedule_reasons'].append('SCHEDULE_CAPTURE_NOT_PREGAME');g['identity_verified']=False
    report=dict(source='nflverse schedule cross-checked against ESPN NFL fixtures (secondary sources)',
        authority='CROSS_CHECKED_SECONDARY_SOURCES',captured_at=at,target_date=target_date,games=games,
        manifests=[m,em],schedule_fingerprint=digest(games))
    return report, rows

def match_odds(game, events):
    same=[e for e in events if normalized_name(e['home_team'])==normalized_name(game['home_team'])
          and normalized_name(e['away_team'])==normalized_name(game['away_team'])]
    exact=[e for e in same if utc(e['commence_time'])==utc(game['kickoff'])]
    if not game['identity_verified']:return None,'BLOCKED_IDENTITY'
    if len(exact)!=1:return None,('BOOK_CANONICAL_START_MISMATCH' if same else 'NO_MARKET')
    return exact[0],None

def current_rosters(root, game):
    if not game.get('identity_verified'):return None,[],[],game['schedule_reasons']
    a=PublicStatsArchive(Path(root)/'data');sources=[];crosswalk={};players=[]
    url='https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_'+str(game['season'])+'.parquet'
    m,roster=source(a,url,'parquet',True);sources.append(m)
    for r in roster:
        if r.get('espn_id') and r.get('gsis_id'):crosswalk.setdefault(str(r['espn_id']),set()).add(r['gsis_id'])
    for side,t in game['espn_teams'].items():
        m,p=source(a,ESPN+'teams/'+str(t['id'])+'/roster',refresh=True);sources.append(m)
        if str(p['team']['id'])!=str(t['id']):raise ValueError('ROSTER_TEAM_MISMATCH')
        for person in [p for group in p['athletes'] for p in group['items']]:
            ids=crosswalk.get(str(person['id']),set())
            if len(ids)!=1:continue
            players.append(dict(player_id=next(iter(ids)),provider_player_id=str(person['id']),name=person['displayName'],
                aliases=list({person.get('fullName',''),person['displayName']}),team_id=game[side+'_code'],team_name=t['displayName'],
                position=person.get('position',{}).get('abbreviation'),injuries=person.get('injuries',[]),
                status=person.get('status',{}).get('type'),role_confirmed=False))
    for sid in game['schedule_source_ids']:
        import json
        m=json.loads((a.folder/(sid+'.json')).read_text());a.read(m);sources.append(m)
    reasons=[] if game.get('market_identity_verified') else ['NO_VERIFIED_BOOK_EVENT']
    return game,players,sources,reasons

def next_slate(root):
    """Default NFL paths choose a complete schedule date, never an odds event."""
    import json
    root=Path(root);a=PublicStatsArchive(root/'data');_,rows=source(a,GAMES_URL,'csv',True)
    at=datetime.now(timezone.utc)
    dates=sorted({r['gameday'] for r in rows if r['game_type']=='REG' and r['gametime'] and kickoff(r)>at})
    if not dates:raise ValueError('NO_UPCOMING_CANONICAL_NFL_SCHEDULE')
    schedule,_=discover(root,dates[0]);games=schedule['games']
    path=root/'data/evaluations/nfl-slate-price-access.json'
    events=[v['event'] for v in json.loads(path.read_text()).get('events',{}).values() if v.get('event')] if path.exists() else []
    # Legacy capture can help bind one game's ID, but never defines the inventory.
    old=root/'data/evaluations/prop-price-access.json'
    if old.exists():
        events += [v['event'] for v in json.loads(old.read_text()).get('sports',[]) if v['sport']=='NFL' and v.get('event') and v['event']['id'] not in {e['id'] for e in events}]
    for game in games:
        e,_=match_odds(game,events)
        if e:game.update(odds_event_id=e['id'],odds_event_start=e['commence_time'],market_identity_verified=True)
    return games
