"""Offline-first CFB training eligibility and unchanged walk-forward model runner.

Run: python -m ap_evsims.cfb_training --root .
Optional collection requires explicit bounded year/week arguments. No odds calls.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from .backtest import run_walk_forward
from .canonical import verify_provider_dataset
from .cfb_history import RollingCFBHistory, BASELINE_FEATURES
from .cfb_universe import verified_sources, build_cfb_universe
from .historical import HistoricalObservation, FoldWindow, validate_dataset
from .identity import map_cfb_events
from .integrity import digest, utc
from .providers.normalize import odds_contexts
from .research_store import ResearchStore
from .warehouse import Warehouse


def collect_prior_weeks(store, warehouse, validator, *, year, through_week, max_requests=7):
    """Immutable weekly captures reused exactly; cached queries are not refreshed.

    This collects whole queries, not a sample of favorable games. Missing endpoint
    rows remain missing. No entitlement upgrade or automatic historical backfill.
    """
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (year, through_week, max_requests)) or not 2001<=year<=datetime.now(timezone.utc).year or not 1<=through_week<=16 or not 0<=max_requests<=17:
        raise ValueError('BOUNDED_CFB_QUERY_REQUIRED')
    captures=[]
    for path in (store.root/'manifests').glob('*.json'):
        m=json.loads(path.read_text(encoding='utf-8'))
        if m['provider']=='cfbd' and m['parameters'].get('endpoint_status',200)==200: captures.append(m)
    requests=[('games',dict(year=year,seasonType='regular',classification='fbs'))]
    requests += [('plays',dict(year=year,week=w,seasonType='regular')) for w in range(1,through_week+1)]
    used=0; records=[]
    for endpoint,params in requests:
        cached=[m for m in captures if m['endpoint']==endpoint and {k:v for k,v in m['parameters'].items() if k not in ('endpoint_status','error_payload_sanitized')}==params]
        if cached:
            m=max(cached,key=lambda m:utc(m['available_at']));m=store.manifest(m['snapshot_id'])
            r=dict(endpoint=endpoint,parameters=params,status=200,cached=True,snapshot_id=m['snapshot_id'],rows=len(store.payload(m)))
        elif used>=max_requests:
            records.append(dict(endpoint=endpoint,parameters=params,status='REQUEST_BUDGET_LIMIT'));break
        else:
            r,_=validator.request('cfbd',endpoint,params);used+=1
            if r['status']!=200: records.append(r);break
            m=store.manifest(r['snapshot_id'])
        warehouse.ingest_manifest(store,m);records.append(r)
        if r.get('quota',{}).get('x-calllimit-remaining',999999)<50:
            records.append(dict(status='CFBD_QUOTA_RESERVE'));break
    return dict(network_requests=used,records=records)


def latest_games(sources):
    games={}; conflicts=set()
    for m,payload in sources:
        seen=set()
        for g in payload:
            key=str(g['id']);previous=games.get(key)
            if key in seen or previous and utc(previous[1]['available_at'])==utc(m['available_at']) and previous[0]!=g:
                conflicts.add(key)
            seen.add(key);games[key]=(g,m)
    return games,conflicts


def build_training_dataset(store,warehouse,at,*,book='draftkings'):
    """Earliest qualifying fresh full-game home spread per game, never by outcome.

    Identity and features must exist by the quote timestamp; capture/decision must
    precede kickoff with <=180 seconds latency. Every settled FBS game remains in
    the exclusion denominator, even with no quote or insufficient feature history.
    """
    games=verified_sources(store,warehouse,'games',at)
    teams=verified_sources(store,warehouse,'teams',at)
    plays=verified_sources(store,warehouse,'plays',at)
    latest,conflicts=latest_games(games)
    eligible={key:(g,m) for key,(g,m) in latest.items() if g.get('homeClassification')=='fbs' and g.get('awayClassification')=='fbs'
              and g.get('completed') is True and utc(g['startDate'])<utc(at)}
    reasons={key:set() for key in eligible}; candidates=[]; identity_failures=Counter()
    with warehouse.connect() as db:
        ids=db.execute("SELECT snapshot_id FROM snapshots WHERE provider='odds' AND dataset LIKE '%americanfootball_ncaaf/odds' AND available_at<=? ORDER BY available_at,snapshot_id",[at]).fetchall()
    for (sid,) in ids:
        m=store.manifest(sid);payload=store.payload(m)
        if m['parameters'].get('endpoint_status',200)!=200:continue
        events=payload['data'] if m['availability_basis']=='historical_odds_snapshot' else payload
        if not isinstance(events,list):raise ValueError('SCHEMA_DRIFT')
        for event in events:
            for b in event.get('bookmakers',[]):
                if b['key']!=book:continue
                for market in b.get('markets',[]):
                    if market['key']!='spreads' or market.get('period','full_game')!='full_game':continue
                    quote=market.get('last_update',b.get('last_update'))
                    if not quote:continue
                    start=utc(event['commence_time']);cutoff=utc(quote);capture=utc(m['available_at'])
                    if not start-timedelta(days=1)<=cutoff<=capture<start or (capture-cutoff).total_seconds()>180:continue
                    gs=[s for s in games if utc(s[0]['available_at'])<=cutoff]
                    ts=[s for s in teams if utc(s[0]['available_at'])<=cutoff]
                    if not gs or not ts:identity_failures['HISTORICAL_IDENTITY_UNAVAILABLE']+=1;continue
                    known,bad=latest_games(gs);tm,t=ts[-1]
                    mapping,rejections=map_cfb_events(t,[g for key,(g,_) in known.items() if key not in bad],[event],
                        alias_snapshot=tm['snapshot_id'],game_snapshot=digest([m['snapshot_id'] for m,_ in gs]),available_at=cutoff.isoformat())
                    for r in rejections:identity_failures[r['reason']]+=1
                    if event['id'] not in mapping:continue
                    key=mapping[event['id']]['event_id']
                    if key not in eligible:continue
                    sub=[dict(event,bookmakers=[dict(b,markets=[market])])]
                    raw=dict(payload,data=sub) if isinstance(payload,dict) else sub
                    contexts,failures=odds_contexts(raw,m,prediction_at=cutoff.isoformat(),event_mapping=mapping)
                    if not contexts:reasons[key].add('MISSING_OR_INVALID_MARKET_PAIR');continue
                    candidates.append((capture,sid,key,contexts[0],mapping[event['id']],gs))
    rows=[];chosen=set();priced=set();feature_cache={}
    for capture,sid,key,context,mapping,gs in sorted(candidates,key=lambda c:(c[0],c[1],c[2])):
        priced.add(key)
        if key in chosen:continue
        if key in conflicts:reasons[key].add('CONFLICTING_GAME_REVISION');continue
        g,rm=eligible[key];cutoff=context.prediction_timestamp
        if utc(g['startDate'])!=utc(context.event_timestamp):reasons[key].add('EVENT_START_REVISION');continue
        pids=tuple(m['snapshot_id'] for m,_ in plays if utc(m['available_at'])<=utc(cutoff))
        gids=tuple(m['snapshot_id'] for m,_ in gs)
        try:
            if not pids:raise ValueError('HISTORICAL_AVAILABILITY_UNVERIFIED')
            cache_key=(pids,gids,cutoff)
            if cache_key not in feature_cache:
                feature_cache[cache_key]=RollingCFBHistory(store,plays_snapshot_ids=pids,results_snapshot_ids=gids,as_of=cutoff)
            f=feature_cache[cache_key].materialize(event_id=key,home_team=g['homeTeam'],away_team=g['awayTeam'])
            f.validate(cutoff,BASELINE_FEATURES)
            row=HistoricalObservation(digest([key,'spread','home']),f,context,g['homePoints'],g['awayPoints'],
                rm['available_at'],rm['snapshot_id'],rm['payload_hash'],'final',g.get('overtime'),event_mapping=mapping)
            row.validate();rows.append(row);chosen.add(key)
        except ValueError as error:reasons[key].add(str(error))
    rows=validate_dataset(rows);verify_provider_dataset(store,rows)
    audits=[]
    for key,(g,m) in sorted(eligible.items()):
        why=[] if key in chosen else sorted(reasons[key] or {'NO_ELIGIBLE_ARCHIVED_PRICE'})
        audits.append(dict(event_id=key,season=g.get('season'),week=g.get('week'),event_start=g['startDate'],
            home_team=g['homeTeam'],away_team=g['awayTeam'],result_snapshot_id=m['snapshot_id'],
            has_eligible_archived_price=key in priced,included=key in chosen,reasons=why))
    return rows,dict(completed_fbs_game_denominator=len(eligible),games_with_eligible_archived_price=len(priced),
        eligible_real_training_rows=len(rows),synthetic_performance_sample=0,book=book,market='spread',
        selection_policy='earliest qualifying captured full-game home spread within 24h of kickoff; latency <=180s; one row/game',
        rejection_counts=dict(Counter(r for g in audits for r in g['reasons'])),identity_rejections=dict(identity_failures),games=audits)


def research_run(root,*,at=None,windows=None):
    root=Path(root);at=at or datetime.now(timezone.utc).isoformat();store=ResearchStore(root/'data');warehouse=Warehouse(store.root)
    if windows is not None:
        if not windows:raise ValueError('MISSING_EVALUATION_WINDOWS')
        for window in windows:
            window.validate()
            if utc(window.evaluation_end)>utc(at):raise ValueError('FUTURE_EVALUATION_WINDOW')
    universe=build_cfb_universe(store,warehouse,at,[])
    ps=verified_sources(store,warehouse,'plays',at);gs=verified_sources(store,warehouse,'games',at)
    history=RollingCFBHistory(store,plays_snapshot_ids=[m['snapshot_id'] for m,_ in ps],
        results_snapshot_ids=[m['snapshot_id'] for m,_ in gs],as_of=at)
    play_table=store.write_table('cfb-prior-play-facts',[asdict(p) for p in history.plays])
    rows,audit=build_training_dataset(store,warehouse,at)
    table=store.write_table('cfb-verified-spread-training',[asdict(r) for r in rows])
    features=[dict(event_id=g['event_id'],event_start=g['event_start'],features=g['verified_features']) for g in universe['games'] if g['verified_features']]
    feature_table=store.write_table('cfb-prospective-baseline-features',features)
    # Fixed development fold. Minimums remain 80 train / 300 calibration fit /
    # 100 calibration selection. An empty-data run is a blocked attempt, not evidence.
    year=utc(at).year
    if windows is None:
        window=FoldWindow(f'{year-1}-08-01T00:00:00Z',f'{year}-02-01T00:00:00Z',f'{year}-08-01T00:00:00Z',at)
        if utc(at)<=utc(window.selection_end):raise ValueError('EVALUATION_WINDOW_NOT_STARTED')
        windows=[window]
    run_id=digest(dict(at=at,dataset=table['fingerprint'],windows=[asdict(w) for w in windows]))[:20]
    directory=store.root/'evaluations'/('cfb-walk-forward-'+run_id)
    result=run_walk_forward(rows,windows,market_type='spread',output_dir=directory,feature_keys=BASELINE_FEATURES,
                            dataset_kind='provider_history',provenance_store=store)
    report=dict(generated_at=at,source='real immutable provider responses',eligible_training=table,prospective_features=feature_table,
        normalized_prior_plays=play_table,
        prospective_baseline_feature_sets=len(features),complete_phase1_feature_sets=0,play_history=universe['play_history'],
        eligibility={k:v for k,v in audit.items() if k!='games'},folds=result['folds'],summary=result['summary'],
        real_model_predictions=result['summary']['raw']['n'],synthetic_performance_sample=0,models_validated=0,
        evaluation_status='BLOCKED_INSUFFICIENT_VERIFIED_HISTORY' if not result['summary']['raw']['n'] else 'UNVALIDATED_RESEARCH',
        profitability_demonstrated=False,walk_forward_report=str((directory/'summary.json').relative_to(store.root)),
        baseline_features=list(BASELINE_FEATURES),limitations=[
            'Downloaded historical plays are available only at their real capture time, never the game date.',
            'PPA is not EPA; plays per game is volume, not clock-based pace.',
            'A small baseline feature set is not the complete Phase 1 feature/lineup contract.',
            'No first real model can be fitted without enough eligible, settled pregame observations.',
            'Historical odds entitlement last returned HTTP 401; it was not retested or upgraded by this offline run.'])
    (directory/'eligibility.json').write_text(json.dumps(audit,sort_keys=True,indent=2),encoding='utf-8')
    (directory/'research-report.json').write_text(json.dumps(report,sort_keys=True,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='.');parser.add_argument('--collect',action='store_true')
    parser.add_argument('--year',type=int);parser.add_argument('--through-week',type=int)
    parser.add_argument('--max-requests',type=int,default=7)
    parser.add_argument('--folds',type=Path,help='Predeclared chronological FoldWindow JSON array; defaults to a development readiness fold')
    args=parser.parse_args();root=Path(args.root)
    if args.collect:
        if args.year is None or args.through_week is None:parser.error('--collect requires --year and --through-week')
        from .providers.validation import ProviderValidator
        from .providers.security import load_credentials
        load_credentials(root/'.env');store=ResearchStore(root/'data');w=Warehouse(store.root)
        print(json.dumps(collect_prior_weeks(store,w,ProviderValidator(store),year=args.year,through_week=args.through_week,max_requests=args.max_requests)))
    windows=None if args.folds is None else [FoldWindow(**w) for w in json.loads(args.folds.read_text(encoding='utf-8'))]
    print(json.dumps(research_run(root,windows=windows),sort_keys=True,indent=2))


if __name__=='__main__':main()
