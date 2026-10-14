"""Local-first entry points. Offline research prohibits network operations."""
import argparse,json
from pathlib import Path

def main(argv=None):
    parser=argparse.ArgumentParser(prog='python -m ap_evsims')
    parser.add_argument('command',choices=('collect_odds','sync_data','data_health','research_cycle','publish_handoff'))
    parser.add_argument('--store',type=Path,default=Path('data'))
    parser.add_argument('--sports',default='CFB')
    parser.add_argument('--daily-credit-cap',type=int,default=24)
    parser.add_argument('--reserve-credits',type=int,default=50)
    parser.add_argument('--cfbd-year',type=int)
    parser.add_argument('--cfbd-week',type=int)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--folds',type=Path)
    parser.add_argument('--market',choices=('spread','total','win'),default='spread')
    args=parser.parse_args(argv)
    if args.offline and args.command=='collect_odds':parser.error('collect_odds requires network access')
    if args.offline and args.command=='sync_data' and args.cfbd_year is not None:parser.error('offline sync imports local archives only')
    from .research_store import ResearchStore
    from .warehouse import Warehouse
    from .operations import collect_odds,sync_data,data_health
    store=ResearchStore(args.store);warehouse=Warehouse(args.store)
    if args.command in ('collect_odds','sync_data','research_cycle','publish_handoff') and not args.offline:
        from .providers.security import load_credentials
        load_credentials()
    if args.command=='collect_odds':
        result=collect_odds(store,warehouse,sports=tuple(args.sports.split(',')),daily_credit_cap=args.daily_credit_cap,reserve_credits=args.reserve_credits)
    elif args.command=='sync_data':result=sync_data(store,warehouse,cfbd_year=args.cfbd_year,cfbd_week=args.cfbd_week)
    elif args.command=='data_health':result=data_health(store,warehouse,args.store.parent/'reports/DATA_HEALTH.md')
    elif args.command=='research_cycle':
        from .cycle import research_cycle
        result=research_cycle(args.store.parent,store,warehouse,offline=args.offline,dataset_path=args.dataset,folds_path=args.folds,market=args.market)
    else:
        from .handoff import publish_handoff
        if not args.offline:collect_odds(store,warehouse,sports=tuple(args.sports.split(',')),daily_credit_cap=args.daily_credit_cap,reserve_credits=args.reserve_credits)
        result=publish_handoff(args.store.parent,store,warehouse)
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
