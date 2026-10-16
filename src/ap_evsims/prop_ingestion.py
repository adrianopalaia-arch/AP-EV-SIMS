"""Independent, bounded public player-history jobs. Raw bytes stay local.

python -m ap_evsims.prop_ingestion --root . --sport NFL (or NBA/NHL/MLB/all)
The first MLB slice is a predeclared Detroit 2024-roster cohort, not all MLB.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from .providers.public_stats import PublicStatsArchive
from .integrity import digest


def ingest(root,sport,*,refresh_current=False):
    root=Path(root);a=PublicStatsArchive(root/'data');sources=[];failures=[]
    def get(url,fmt='json'):
        current=str(datetime.now(timezone.utc).year)
        refresh=refresh_current and (current in url or sport=='NBA' and str(int(current)+1) in url or url.endswith('games.csv'))
        m=a.capture(sport,url,format=fmt,refresh=refresh);sources.append(m)
        if m['status']!=200:failures.append(dict(url=url,status=m['status']));return None
        return a.read(m)
    if sport=='NFL':
        get('https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv','csv')
        for season in range(2024,datetime.now(timezone.utc).year+1):get(f'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.parquet','parquet')
    elif sport=='NBA':
        for season in range(2024,datetime.now(timezone.utc).year+2):
            get(f'https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-data/main/nba/player_box/parquet/player_box_{season}.parquet','parquet')
    elif sport=='NHL':
        # Month partitions avoid the API's 10,000 row cap. A saturated partition
        # fails explicitly; no partial response is reported as complete coverage.
        for season in [y*10000+y+1 for y in range(2023,datetime.now(timezone.utc).year+1)]:
            start_year=season//10000
            for year,month in [(start_year,m) for m in (10,11,12)]+[(start_year+1,m) for m in (1,2,3,4)]:
                if datetime(year,month,1,tzinfo=timezone.utc)>datetime.now(timezone.utc):continue
                next_year,next_month=(year+1,1) if month==12 else (year,month+1)
                expr=f'gameTypeId=2 and gameDate>="{year}-{month:02d}-01" and gameDate<"{next_year}-{next_month:02d}-01"'
                for role in ('skater','goalie'):
                    url=f'https://api.nhle.com/stats/rest/en/{role}/summary?'+urlencode(dict(isAggregate='false',isGame='true',start=0,limit=-1,cayenneExp=expr))
                    p=get(url)
                    if p is not None and (len(p.get('data',[]))>=10000 or p.get('total',0)>len(p.get('data',[]))):
                        failures.append(dict(url=url,status='TRUNCATED_SOURCE_PARTITION'))
    elif sport=='MLB':
        roster=get('https://statsapi.mlb.com/api/v1/teams/116/roster?rosterType=fullSeason&season=2024')
        if roster is not None:
            for group,pitcher in (('pitching',True),('hitting',False)):
                people=sorted({r['person']['id'] for r in roster['roster'] if (r['position']['abbreviation']=='P')==pitcher})[:12]
                for identity in people:
                    for season in range(2024,datetime.now(timezone.utc).year+1):
                        get(f'https://statsapi.mlb.com/api/v1/people/{identity}/stats?'+urlencode(dict(stats='gameLog',group=group,season=season)))
    else:raise ValueError('UNSUPPORTED_SPORT')
    report=dict(sport=sport,generated_at=datetime.now(timezone.utc).isoformat(),sources=sources,failures=failures,
        source_selection='Detroit 2024 fullSeason roster; first 12 sorted pitcher IDs and 12 nonpitcher IDs' if sport=='MLB' else 'all returned rows in explicit season/regular-game queries',
        real_source_count=sum(s['status']==200 for s in sources),status='INGESTED_WITH_GAPS' if failures else 'INGESTED',
        historical_as_of_verified=False,redistribution_permission='NOT_ASSUMED; raw data local only')
    folder=root/'data/evaluations/prop-ingestion';folder.mkdir(exist_ok=True)
    (folder/(sport+'.json')).write_text(json.dumps(report,sort_keys=True,indent=2),encoding='utf-8')
    return {k:v for k,v in report.items() if k!='sources'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--sport',choices=['NFL','NBA','NHL','MLB','all'],default='all');p.add_argument('--refresh-current',action='store_true');p.add_argument('--extend-mlb-quoted-hitters',action='store_true');args=p.parse_args()
    if args.extend_mlb_quoted_hitters:
        print(json.dumps(extend_mlb_quoted_hitters(args.root),indent=2));return
    sports=['NFL','NBA','NHL','MLB'] if args.sport=='all' else [args.sport]
    with ThreadPoolExecutor(max_workers=len(sports)) as executor:
        for r in executor.map(lambda sport:ingest(args.root,sport,refresh_current=args.refresh_current),sports):print(json.dumps(r),flush=True)


def extend_mlb_quoted_hitters(root):
    """Select by captured future quote + current roster, never by past accuracy.

    This cohort is subject to current-roster survivor selection. Retrospective
    metrics must not be described as a random league-wide validation sample.
    """
    from .prop_prospective import current_inputs
    from .prop_prices import normalize_props
    from .research_store import ResearchStore
    from .identity import normalized_name
    from .publication import atomic_json
    from collections import defaultdict
    root=Path(root);store=ResearchStore(root/'data');a=PublicStatsArchive(store.root)
    event,players,identity_sources,reasons=current_inputs(root,'MLB')
    if event is None:raise ValueError('NO_MLB_COHORT_EVENT')
    access=json.loads((store.root/'evaluations/prop-price-access.json').read_text());record=next(r['record'] for r in access['sports'] if r['sport']=='MLB')
    at=datetime.now(timezone.utc).isoformat();quotes,_=normalize_props(store,store.manifest(record['snapshot_id']),'MLB',at)
    aliases=defaultdict(set)
    for p in players:
        if p['position']=='P':continue
        for name in p['aliases']:aliases[normalized_name(name)].add(p['player_id'])
    ids=set()
    for q in quotes:
        candidates=aliases[normalized_name(q['player_name'])]
        if q['market'] in ('hitter_hits','total_bases') and len(candidates)==1:ids.update(candidates)
    if len(ids)>40:raise ValueError('COHORT_REQUEST_BOUND_EXCEEDED')
    # Save selection before acquiring outcomes. This does not prove that the
    # retrospective population was selected at its historical prediction time.
    selection=dict(selected_at=at,event_id=event['event_id'],odds_snapshot=record['snapshot_id'],player_ids=sorted(ids),
        selection_rule='Unique name-to-current-roster match for captured hits/total-bases quotes, irrespective of price or outcome',
        retrospective_selection_bias='CURRENT_ROSTER_SURVIVOR_SELECTION',event_identity_reasons=reasons,
        identity_source_hashes=[m['hash'] for m in identity_sources])
    ResearchStore._immutable(store.root/'evaluations'/('mlb-quote-cohort-'+digest(selection)+'.json'),json.dumps(selection,sort_keys=True,indent=2).encode())
    path=store.root/'evaluations/prop-ingestion/MLB.json';prior=json.loads(path.read_text());sources={m['url']:m for m in prior['sources']}
    failures=list(prior['failures']);jobs=[(pid,y) for pid in sorted(ids) for y in range(2024,datetime.now(timezone.utc).year+1)]
    def fetch(job):
        pid,y=job;return a.capture('MLB',f'https://statsapi.mlb.com/api/v1/people/{pid}/stats?'+urlencode(dict(stats='gameLog',group='hitting',season=y)))
    with ThreadPoolExecutor(max_workers=3) as executor:
        for m in executor.map(fetch,jobs):
            sources[m['url']]=m
            if m['status']!=200:failures.append(dict(url=m['url'],status=m['status']))
    prior.update(generated_at=datetime.now(timezone.utc).isoformat(),sources=list(sources.values()),failures=failures,
        base_source_selection=prior.get('base_source_selection',prior['source_selection']),current_quote_cohort=selection,
        source_selection='Original Detroit 2024 cohort plus current captured hits/TB quoted-roster cohort; current-roster survivor selection, not league-wide random coverage',
        real_source_count=sum(m['status']==200 for m in sources.values()),status='INGESTED_WITH_GAPS' if failures else 'INGESTED')
    atomic_json(path,prior)
    result=dict(selected_hitter_ids=len(ids),source_jobs=len(jobs),total_sources=len(sources),failures=len(failures),selection=selection)
    atomic_json(store.root/'evaluations/mlb-quote-cohort-result.json',result);return result


if __name__=='__main__':main()
