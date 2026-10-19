"""Bounded, additive historical ingestion. Old bytes/manifests are never replaced.

python -m ap_evsims.history_expansion --root . --sport all
The fixed MLB cohort uses 2023 rosters, independent of current quotes/results.
It remains a deliberately sampled roster cohort, not league-wide coverage.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from .integrity import digest
from .publication import atomic_json
from .providers.public_stats import PublicStatsArchive
from .research_store import ResearchStore


POLICY = dict(version='historical-expansion-v1', nfl_first_season=2022,
              nba_first_season=2022, nhl_first_season=2021, mlb_cohort_season=2023,
              mlb_hitters_per_team=2, mlb_pitchers_per_team=1,
              selection='Lowest SHA256(sport, cohort season, team, player) per role; chosen before outcomes',
              retrospective_as_of_verified=False)


def roster_cohort(roster, team):
    selected = []
    for group, count in [('hitting', 2), ('pitching', 1)]:
        ids = {r['person']['id'] for r in roster['roster']
               if (r['position']['abbreviation'] == 'P') == (group == 'pitching')}
        selected.extend((pid, group) for pid in sorted(ids, key=lambda p: digest(['MLB', 2023, team, p]))[:count])
    return selected


def expand(root, sport):
    root = Path(root); store = ResearchStore(root/'data'); archive = PublicStatsArchive(store.root)
    path = store.root/'evaluations/prop-ingestion'/(sport+'.json')
    prior = json.loads(path.read_text()); sources = {m['url']: m for m in prior['sources']}
    failures = {f['url']: f for f in prior['failures']}; jobs = []; new = []
    policy = dict(POLICY, declared_at=datetime.now(timezone.utc).isoformat(), sport=sport)
    store._immutable(store.root/'evaluations'/('expansion-policy-'+digest(policy)+'.json'), json.dumps(policy, sort_keys=True).encode())
    if sport == 'NFL':
        jobs = [(f'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{y}.parquet', 'parquet') for y in (2022, 2023)]
    elif sport == 'NBA':
        jobs = [(f'https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-data/main/nba/player_box/parquet/player_box_{y}.parquet', 'parquet') for y in (2022, 2023)]
    elif sport == 'NHL':
        for start in (2021, 2022):
            for y, month in [(start, m) for m in (10, 11, 12)]+[(start+1, m) for m in (1, 2, 3, 4)]:
                ny, nm = (y+1, 1) if month == 12 else (y, month+1)
                expr = f'gameTypeId=2 and gameDate>="{y}-{month:02d}-01" and gameDate<"{ny}-{nm:02d}-01"'
                for role in ('skater', 'goalie'):
                    jobs.append((f'https://api.nhle.com/stats/rest/en/{role}/summary?'+urlencode(dict(isAggregate='false', isGame='true', start=0, limit=-1, cayenneExp=expr)), 'json'))
    elif sport == 'MLB':
        tm = archive.capture('MLB', 'https://statsapi.mlb.com/api/v1/teams?sportId=1&season=2023')
        if tm['status'] != 200: return dict(sport=sport, status='BLOCKED_TEAM_COHORT', http_status=tm['status'])
        teams = sorted(t['id'] for t in archive.read(tm)['teams'] if t['sport']['id'] == 1)
        if len(teams) != 30: raise ValueError('MLB_TEAM_COHORT_INCOMPLETE')
        selected = set(); cohort_sources = [tm]; cohort_failures = []
        for team in teams:
            m = archive.capture('MLB', f'https://statsapi.mlb.com/api/v1/teams/{team}/roster?rosterType=fullSeason&season=2023')
            cohort_sources.append(m)
            if m['status'] != 200: cohort_failures.append(dict(team=team, status=m['status'])); continue
            selected.update(roster_cohort(archive.read(m), team))
        cohort = dict(policy=policy, selected_players=sorted(selected), sources=[m['manifest_id'] for m in cohort_sources],
                      failures=cohort_failures, limitation='2023 full-season membership is retrospective cohort selection; appearances only, not population validation')
        store._immutable(store.root/'evaluations'/('mlb-historical-cohort-'+digest(cohort)+'.json'), json.dumps(cohort, sort_keys=True).encode())
        for pid, group in sorted(selected):
            for y in range(2023, datetime.now(timezone.utc).year+1):
                jobs.append((f'https://statsapi.mlb.com/api/v1/people/{pid}/stats?'+urlencode(dict(stats='gameLog', group=group, season=y)), 'json'))
        prior['historical_cohort'] = {k:v for k,v in cohort.items() if k != 'sources'}
    else: raise ValueError('UNSUPPORTED_SPORT')
    def fetch(job): return archive.capture(sport, job[0], format=job[1])
    with ThreadPoolExecutor(max_workers=2) as executor:
        for m in executor.map(fetch, jobs):
            new.append(m); sources[m['url']] = m
            failure = None
            if m['status'] != 200: failure = m['status']
            elif sport == 'NHL':
                p = archive.read(m)
                if len(p.get('data', [])) >= 10000 or p.get('total', 0) > len(p.get('data', [])): failure = 'TRUNCATED_SOURCE_PARTITION'
            if failure is not None: failures[m['url']] = dict(url=m['url'], status=failure)
            else: failures.pop(m['url'], None)
    prior.update(sources=list(sources.values()), failures=list(failures.values()), generated_at=datetime.now(timezone.utc).isoformat(),
                 expansion_policy=POLICY, real_source_count=sum(m['status']==200 for m in sources.values()))
    if sport == 'MLB': prior['source_selection'] += '; additive deterministic 2023 full-season roster cohort across 30 teams'
    prior['status'] = 'INGESTED_WITH_GAPS' if failures else 'INGESTED'
    atomic_json(path, prior)
    result = dict(sport=sport, jobs=len(jobs), successful_jobs=sum(m['status']==200 for m in new),
                  total_sources=len(sources), failures=len(failures), status=prior['status'], historical_as_of_verified=False)
    atomic_json(store.root/'evaluations'/('history-expansion-'+sport+'.json'), result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--sport',default='all',choices=['all','NFL','NBA','NHL','MLB']);a=p.parse_args()
    sports=['NFL','NBA','NHL','MLB'] if a.sport=='all' else [a.sport]
    def safe(sport):
        try:return expand(a.root,sport)
        except Exception as e:return dict(sport=sport,status='INGESTION_FAILED',error_category=type(e).__name__)
    with ThreadPoolExecutor(max_workers=len(sports)) as executor:
        for result in executor.map(safe,sports):print(json.dumps(result),flush=True)


if __name__=='__main__':main()
