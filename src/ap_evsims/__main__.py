"""Local-first entry points. Offline research prohibits network operations."""
import argparse,json
from pathlib import Path

def main(argv=None):
    parser=argparse.ArgumentParser(prog='python -m ap_evsims')
    parser.add_argument('command',choices=('collect_odds','sync_data','data_health','research_cycle','publish_handoff','reconcile_results'))
    parser.add_argument('--store',type=Path,default=Path('data'))
    parser.add_argument('--sports',default='CFB')
    parser.add_argument('--daily-credit-cap',type=int,default=24)
    parser.add_argument('--reserve-credits',type=int,default=50)
    parser.add_argument('--cfbd-year',type=int)
    parser.add_argument('--cfbd-week',type=int)
    parser.add_argument('--refresh-cfbd-games',action='store_true',help='Explicitly capture a new revision of one CFBD year/week query')
    parser.add_argument('--min-refresh-seconds',type=int,default=3600)
    parser.add_argument('--replay-ledger',type=Path,help='Existing frozen-prediction ledger for local result reconciliation')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--folds',type=Path)
    parser.add_argument('--market',choices=('spread','total','win'),default='spread')
    parser.add_argument('--git',help='Git executable for handoff checkpoints')
    parser.add_argument('--author-name')
    parser.add_argument('--author-email')
    args=parser.parse_args(argv)
    if args.offline and args.command=='collect_odds':parser.error('collect_odds requires network access')
    if args.offline and args.command=='sync_data' and args.cfbd_year is not None:parser.error('offline sync imports local archives only')
    if args.refresh_cfbd_games and (args.command!='sync_data' or args.offline or args.cfbd_year is None or args.cfbd_week is None):
        parser.error('CFBD refresh requires online sync_data with an explicit year and week')
    if args.command=='reconcile_results' and (args.replay_ledger is None or not args.replay_ledger.is_file()):
        parser.error('reconcile_results requires an existing --replay-ledger')
    if args.replay_ledger is not None and args.command!='reconcile_results':
        parser.error('--replay-ledger applies only to reconcile_results')
    from .research_store import ResearchStore
    from .warehouse import Warehouse
    from .operations import collect_odds,sync_data,data_health
    store=ResearchStore(args.store);warehouse=Warehouse(args.store)
    if args.command in ('collect_odds','sync_data','research_cycle','publish_handoff') and not args.offline:
        from .providers.security import load_credentials
        load_credentials()
    if args.command=='collect_odds':
        result=collect_odds(store,warehouse,sports=tuple(args.sports.split(',')),daily_credit_cap=args.daily_credit_cap,reserve_credits=args.reserve_credits)
    elif args.command=='sync_data':result=sync_data(store,warehouse,cfbd_year=args.cfbd_year,cfbd_week=args.cfbd_week,
        refresh_cfbd_games=args.refresh_cfbd_games,min_refresh_seconds=args.min_refresh_seconds)
    elif args.command=='data_health':result=data_health(store,warehouse,args.store.parent/'reports/DATA_HEALTH.md')
    elif args.command=='reconcile_results':
        from datetime import datetime,timezone
        from .results import reconcile_cfbd_replay
        from .replay import ReplayLedger
        from .offline import offline_mode
        with offline_mode():
            result=reconcile_cfbd_replay(store,warehouse,ReplayLedger(args.replay_ledger),datetime.now(timezone.utc))
    elif args.command=='research_cycle':
        from .cycle import research_cycle
        result=research_cycle(args.store.parent,store,warehouse,offline=args.offline,dataset_path=args.dataset,folds_path=args.folds,market=args.market)
    else:
        from .handoff import publish_handoff
        from .checkpoint import run_full_tests,commit_and_push,source_head
        from .publication import atomic_json
        repo=args.store.parent
        tests=run_full_tests(repo)
        state=json.loads((repo/'TASK_STATE.json').read_text());state['tests'].update(tests)
        atomic_json(repo/'TASK_STATE.json',state)
        if tests['status']!='PASS':
            print(json.dumps(dict(status='TESTS_FAILED_NO_PUBLICATION',tests=tests)));return
        if not args.offline:collect_odds(store,warehouse,sports=tuple(args.sports.split(',')),daily_credit_cap=args.daily_credit_cap,reserve_credits=args.reserve_credits)
        result=publish_handoff(args.store.parent,store,warehouse,source_commit=source_head(repo,args.git))
        result['tests']=tests
        result['git']=commit_and_push(repo,git=args.git,push=not args.offline,author_name=args.author_name,author_email=args.author_email)
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
