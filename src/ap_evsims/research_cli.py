"""Explicit provider access, raw ingestion, prediction and historical evaluation commands."""
import argparse,json
from pathlib import Path
from dataclasses import asdict
from .research_store import ResearchStore
from .providers.live import CFBDClient,OddsAPIClient,probe_access,ProviderAccessError
from .historical import load_dataset,FoldWindow
from .models.base import FeatureSnapshot,MarketContext
from .models.artifacts import load_model
from .backtest import run_walk_forward
from .integrity import digest
from .canonical import materialize_rolling_features,join_canonical
from .providers.security import load_credentials

def main():
    parser=argparse.ArgumentParser(); commands=parser.add_subparsers(dest='command',required=True)
    access=commands.add_parser('access'); access.add_argument('--store',type=Path,default=Path('data')); access.add_argument('--historical-at',default='2025-10-04T16:00:00Z')
    ingest=commands.add_parser('ingest'); ingest.add_argument('--store',type=Path,default=Path('data')); ingest.add_argument('--year',type=int,required=True); ingest.add_argument('--week',type=int); ingest.add_argument('--historical-at')
    backtest=commands.add_parser('backtest'); backtest.add_argument('--dataset',type=Path,required=True); backtest.add_argument('--folds',type=Path,required=True); backtest.add_argument('--market',choices=('spread','total','win'),required=True); backtest.add_argument('--output',type=Path,required=True); backtest.add_argument('--feature-keys'); backtest.add_argument('--bankroll',type=float,default=1000); backtest.add_argument('--store',type=Path,default=Path('data'))
    predict=commands.add_parser('predict'); predict.add_argument('--model',type=Path,required=True); predict.add_argument('--request',type=Path,required=True)
    features=commands.add_parser('build-features'); features.add_argument('--store',type=Path,default=Path('data')); features.add_argument('--plays-snapshot',required=True); features.add_argument('--results-snapshot',required=True); features.add_argument('--event-id',required=True); features.add_argument('--home-team',required=True); features.add_argument('--away-team',required=True); features.add_argument('--as-of',required=True); features.add_argument('--output',type=Path,required=True)
    join=commands.add_parser('join'); join.add_argument('--store',type=Path,default=Path('data')); join.add_argument('--odds-snapshot',required=True); join.add_argument('--results-snapshot',required=True); join.add_argument('--event-map',type=Path,required=True); join.add_argument('--features',type=Path,required=True); join.add_argument('--prediction-at',required=True); join.add_argument('--market',choices=('spread','total','win'),required=True); join.add_argument('--book',default='draftkings')
    args=parser.parse_args()
    if args.command in ('access','ingest'): load_credentials()
    if args.command=='access':
        store=ResearchStore(args.store); payload=probe_access(store,historical_at=args.historical_at)
        (store.root/'evaluations'/'provider-access.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    elif args.command=='ingest':
        store=ResearchStore(args.store); manifests=[]; errors=[]
        tasks=[('cfbd_games',lambda:CFBDClient(store).games(args.year))]
        if args.week is not None: tasks.append(('cfbd_plays',lambda:CFBDClient(store).plays(args.year,args.week)))
        tasks.append(('historical_odds' if args.historical_at else 'current_odds',lambda:OddsAPIClient(store).fetch(historical_at=args.historical_at)))
        for provider,task in tasks:
            try: manifests.append(task())
            except ProviderAccessError as e: errors.append(dict(provider=provider,reason=e.reason,endpoint_status=e.status))
        payload=dict(manifests=manifests,errors=errors,canonical_rows_created=0,
            status='BLOCKED_BY_HISTORICAL_ODDS_ACCESS' if any(e['reason']=='BLOCKED_BY_HISTORICAL_ODDS_ACCESS' for e in errors) else 'RAW_INGESTION_ONLY')
        identity=digest(payload)
        store._immutable(store.root/'manifests'/('ingestion-'+identity+'.json'),json.dumps(payload,sort_keys=True,indent=2).encode())
    elif args.command=='backtest':
        rows=load_dataset(args.dataset)
        windows=[FoldWindow(**r) for r in json.loads(args.folds.read_text(encoding='utf-8'))]
        keys=tuple(args.feature_keys.split(',')) if args.feature_keys else None
        payload=run_walk_forward(rows,windows,market_type=args.market,output_dir=args.output,feature_keys=keys,bankroll=args.bankroll,provenance_store=ResearchStore(args.store))
    elif args.command=='build-features':
        f,rejections=materialize_rolling_features(ResearchStore(args.store),plays_snapshot_id=args.plays_snapshot,results_snapshot_id=args.results_snapshot,
            event_id=args.event_id,home_team=args.home_team,away_team=args.away_team,as_of=args.as_of)
        payload=dict(features=asdict(f),rejections=rejections)
        args.output.write_text(json.dumps(payload,indent=2,allow_nan=False),encoding='utf-8')
    elif args.command=='join':
        raw=json.loads(args.features.read_text(encoding='utf-8'))
        if isinstance(raw,dict): raw=[raw.get('features',raw)]
        snapshots=[FeatureSnapshot.from_dict(r) for r in raw]
        result=join_canonical(ResearchStore(args.store),odds_snapshot_id=args.odds_snapshot,results_snapshot_id=args.results_snapshot,
            event_mapping=json.loads(args.event_map.read_text(encoding='utf-8')),feature_snapshots={s.event_id:s for s in snapshots},
            prediction_at=args.prediction_at,book=args.book,market_type=args.market)
        payload=dict(table=result['table'],rejections=result['rejections'],canonical_rows_created=len(result['rows']))
    else:
        model=load_model(args.model); request=json.loads(args.request.read_text(encoding='utf-8'))
        payload=model.predict(FeatureSnapshot.from_dict(request['features']),MarketContext(**request['market_context'])).to_dict()
    print(json.dumps(payload,indent=2,allow_nan=False))

if __name__=='__main__': main()
