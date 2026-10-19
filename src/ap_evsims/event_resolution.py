"""Evidence-bound research mapping; never change either provider's timestamp.

Only NHL regular-season games with a unique matchup, consistent league schedule
and gamecenter records, and a book start 0--15 minutes later may be linked.
The earlier league start remains the hard prediction/price deadline. This does
not satisfy Phase 1 book-rule, model-calibration or CORE approval requirements.
"""
from datetime import datetime
import json
from .identity import normalized_name
from .integrity import digest,utc
from .providers.public_stats import PublicStatsArchive
from .research_store import ResearchStore


def validate_nhl_records(event,quote,schedule,landing,at):
    if event.get('event_id')!=str(landing.get('id')):raise ValueError('LEAGUE_EVENT_ID_MISMATCH')
    if quote['odds_event_id']!=event['odds_event_id']:raise ValueError('BOOK_EVENT_ID_MISMATCH')
    canonical=utc(event['event_start']);book=utc(quote['event_start']);offset=(book-canonical).total_seconds()
    if not 0<=offset<=900:raise ValueError('UNSUPPORTED_SCHEDULE_OFFSET')
    if utc(at)>=min(canonical,book):raise ValueError('EVENT_STARTED')
    def names(g):
        return {side:normalized_name(g[side+'Team']['placeName']['default']+' '+g[side+'Team']['commonName']['default']) for side in ('home','away')}
    expected={side:normalized_name(event[side+'_team']) for side in ('home','away')}
    if any(normalized_name(quote[side+'_team'])!=expected[side] for side in expected):raise ValueError('BOOK_TEAM_MISMATCH')
    games=[g for day in schedule.get('gameWeek',[]) for g in day.get('games',[])]
    near=[g for g in games if names(g)==expected and abs((utc(g['startTimeUTC'])-book).total_seconds())<=900]
    if len(near)!=1:raise ValueError('AMBIGUOUS_LEAGUE_MATCHUP')
    g=near[0]
    if str(g['id'])!=event['event_id'] or utc(g['startTimeUTC'])!=canonical or utc(landing['startTimeUTC'])!=canonical:raise ValueError('LEAGUE_SCHEDULE_REVISION')
    if g.get('gameScheduleState')!='OK' or g.get('gameState') not in ('FUT','PRE') or landing.get('gameState') not in ('FUT','PRE'):raise ValueError('GAME_NOT_CONFIRMED_PREGAME')
    if g.get('gameType')!=2 or landing.get('gameType')!=2:raise ValueError('COMPETITION_DOMAIN_MISMATCH')
    # Gamecenter uses placeName/commonName in current responses; identity also
    # binds stable numeric league team IDs, avoiding abbreviation heuristics.
    if any(g[side+'Team']['id']!=landing[side+'Team']['id'] for side in ('home','away')):raise ValueError('LEAGUE_TEAM_ID_MISMATCH')
    return dict(policy='NHL_UNIQUE_EVENT_OFFSET_RESEARCH_V1',canonical_event_id=g['id'],
        canonical_start=canonical.isoformat(),book_start=book.isoformat(),offset_seconds=offset,
        pregame_deadline=min(canonical,book).isoformat(),timestamp_override=False,phase1_authority=False)


def resolve_nhl(store,event,quote,availability,at):
    if quote['sport']!='NHL':return None
    archive=PublicStatsArchive(store.root);manifests=[]
    for path in archive.folder.glob('*.json'):
        m=json.loads(path.read_text())
        if m['sport']=='NHL' and m['status']==200 and utc(m['captured_at'])<=utc(at):manifests.append(m)
    lm=next((m for m in manifests if m['manifest_id']==availability['source_manifest']),None)
    if lm is None or lm['url']!='https://api-web.nhle.com/v1/gamecenter/'+event['event_id']+'/landing':raise ValueError('UNVERIFIED_GAMECENTER_SOURCE')
    landing=archive.read(lm)
    schedules=sorted([m for m in manifests if m['url'].startswith('https://api-web.nhle.com/v1/schedule/')],key=lambda m:utc(m['captured_at']),reverse=True)
    if not schedules:raise ValueError('MISSING_LEAGUE_SCHEDULE_SOURCE')
    # Recheck exact immutable book payload; the caller cannot bless a timestamp.
    bm=store.manifest(quote['snapshot_id']);bp=store.payload(bm)
    if bm['provider']!='odds' or bp.get('id')!=quote['odds_event_id'] or utc(bp['commence_time'])!=utc(quote['event_start']):raise ValueError('BOOK_SNAPSHOT_MISMATCH')
    if any(bp[side+'_team']!=quote[side+'_team'] for side in ('home','away')):raise ValueError('BOOK_SNAPSHOT_MISMATCH')
    candidates=[]
    for m in schedules:
        p=archive.read(m)
        if any(str(g['id'])==event['event_id'] for day in p.get('gameWeek',[]) for g in day.get('games',[])):candidates.append((m,p))
    if not candidates:raise ValueError('MISSING_LEAGUE_EVENT')
    sm,schedule=candidates[0]
    if max(utc(sm['captured_at']),utc(lm['captured_at']),utc(bm['fetched_at']))>utc(at):raise ValueError('LOOKAHEAD_RISK')
    proof=validate_nhl_records(event,quote,schedule,landing,at)
    proof.update(verified_at=at,schedule_manifest=sm['manifest_id'],schedule_hash=sm['hash'],gamecenter_manifest=lm['manifest_id'],
        gamecenter_hash=lm['hash'],book_snapshot=bm['snapshot_id'],book_hash=bm['payload_hash'])
    proof['resolution_hash']=digest(proof)
    folder=store.root/'evaluations/event-resolutions';folder.mkdir(exist_ok=True)
    ResearchStore._immutable(folder/(proof['resolution_hash']+'.json'),json.dumps(proof,sort_keys=True).encode())
    return proof
