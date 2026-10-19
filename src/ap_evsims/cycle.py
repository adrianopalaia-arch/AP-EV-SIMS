"""Research orchestration. All historical work runs under a network prohibition."""
from datetime import datetime,timezone
from pathlib import Path
import json
from .offline import offline_mode
from .integrity import digest
from .publication import atomic_json
from .operations import import_local_archive,data_health,collect_odds
from .handoff import publish_handoff

def research_cycle(repo,store,warehouse, *, offline=False,dataset_path=None,folds_path=None,market='spread',source_commit=None):
    repo=Path(repo);now=datetime.now(timezone.utc).isoformat()
    report=dict(started_at=now,offline=offline,action='KEEP_CHAMPION',automatic_promotion=False,
        real_model_sample=0,synthetic_model_sample=0,steps=[],blockers=[])
    with offline_mode():
        report['local_import']=import_local_archive(store,warehouse)
        from .results import reconcile_cfbd_replay
        from .replay import ReplayLedger
        report['settlement']=reconcile_cfbd_replay(store,warehouse,ReplayLedger(store.root/'predictions/replay.sqlite'),now)
        report['steps'].append('VERIFIED_RESULT_REVISIONS_RECONCILED')
        warehouse.close_events(now)
        report['data_health']=data_health(store,warehouse,repo/'reports/DATA_HEALTH.md')
        report['steps']+=['LOCAL_HASH_AND_SCHEMA_VALIDATION','CLOSING_PRICES_REVEALED_AFTER_START','LOCAL_DATA_HEALTH']
        if dataset_path is not None:
            if folds_path is None or not Path(dataset_path).is_file() or not Path(folds_path).is_file():raise ValueError('MISSING_LOCAL_DATA')
            from .historical import load_dataset,FoldWindow
            from .backtest import run_walk_forward
            rows=load_dataset(dataset_path)
            folds=[FoldWindow(**f) for f in json.loads(Path(folds_path).read_text())]
            evaluation=store.root/'evaluations'/('walk-forward-'+digest([now,market,str(dataset_path)]))
            report['evaluation']=run_walk_forward(rows,folds,market_type=market,output_dir=evaluation,provenance_store=store)
            report['real_model_sample']=report['evaluation']['summary']['historical_sample_size']
        else:
            report['blockers'].append('MISSING_LOCAL_DATA: no qualifying joined historical feature/price dataset')
            report['steps'].append('TRAINING_SKIPPED_NO_QUALIFYING_DATA')
        report['steps'].append('NO_CHAMPION_CHANGE')
    if not offline:
        report['current_refresh']=collect_odds(store,warehouse,sports=('CFB',))
    else:report['current_refresh']={'status':'OFFLINE_NO_NETWORK'}
    from .product import daily_card
    report['handoff']=daily_card(repo,offline=True)
    report['cycle_id']=digest(report)
    atomic_json(store.root/'evaluations'/('cycle-'+report['cycle_id']+'.json'),report)
    return report
