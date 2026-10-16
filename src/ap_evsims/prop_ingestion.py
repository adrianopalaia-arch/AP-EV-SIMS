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


def ingest(root,sport):
    root=Path(root);a=PublicStatsArchive(root/'data');sources=[];failures=[]
    def get(url,fmt='json'):
        m=a.capture(sport,url,format=fmt);sources.append(m)
        if m['status']!=200:failures.append(dict(url=url,status=m['status']));return None
        return a.read(m)
    if sport=='NFL':
        get('https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv','csv')
        for season in (2024,2025,2026):get(f'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.parquet','parquet')
    elif sport=='NBA':
        for season in (2024,2025,2026):
            get(f'https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-data/main/nba/player_box/parquet/player_box_{season}.parquet','parquet')
    elif sport=='NHL':
        # Month partitions avoid the API's 10,000 row cap. A saturated partition
        # fails explicitly; no partial response is reported as complete coverage.
        for season in (20232024,20242025,20252026,20262027):
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
                    for season in (2024,2025,2026):
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--sport',choices=['NFL','NBA','NHL','MLB','all'],default='all');args=p.parse_args()
    sports=['NFL','NBA','NHL','MLB'] if args.sport=='all' else [args.sport]
    with ThreadPoolExecutor(max_workers=len(sports)) as executor:
        for r in executor.map(lambda sport:ingest(args.root,sport),sports):print(json.dumps(r),flush=True)


if __name__=='__main__':main()
