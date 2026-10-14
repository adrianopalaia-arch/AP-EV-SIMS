"""Atomic local publication. Publication never implies a wager was placed."""
import json,os,tempfile
from pathlib import Path
from .providers.security import redact

def atomic_text(path,body):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if redact(body)!=body:raise ValueError('SECRET_IN_PUBLICATION')
    if path.suffix=='.json':json.loads(body)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='\n',dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as f:
            temporary=Path(f.name);f.write(body);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        if temporary and temporary.exists():temporary.unlink()

def atomic_json(path,value):
    body=json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n'
    atomic_text(path,body)

def write_status_checkpoint(repo, *, source_commit=None):
    from datetime import datetime,timezone
    repo=Path(repo);now=datetime.now(timezone.utc).isoformat()
    state=json.loads((repo/'TASK_STATE.json').read_text(encoding='utf-8'))
    state['updated_at']=now
    provider_path=repo/'data/evaluations/provider-validation-latest.json'
    report=json.loads(provider_path.read_text()) if provider_path.exists() else {}
    providers={}
    for name,internal in [('cfbd','cfbd'),('odds_api','odds')]:
        records=[r for r in report.get('endpoints',[])+report.get('verification_updates',[]) if r['provider']==internal]
        successes=[r for r in records if r['status']==200]
        providers[name]=dict(credential_present=report.get('credential_present',{}).get(name),
            authentication_status='OK' if successes else 'UNVERIFIED',last_success=max((r.get('checked_at','') for r in successes),default=None),
            historical_access=(report.get('HISTORICAL_ODDS_ACCESS')=='YES') if internal=='odds' else bool(report.get('cfbd_seasons_access_verified')),
            historical_feature_availability=report.get('cfbd_historical_feature_availability') if internal=='cfbd' else None,
            relevant_endpoint_status=[dict(endpoint=r['endpoint'],status=r['status'],checked_at=r.get('checked_at'),
                draftkings_returned=r.get('draftkings_returned'),fanduel_returned=r.get('fanduel_returned')) for r in records],
            quota_metadata=next((r['quota'] for r in reversed(records) if r.get('quota')),{}),
            coverage=report.get('cfbd_seasons_access_verified') if internal=='cfbd' else report.get('earliest_usable_historical_date'))
    for p in ('moneypuck','nflverse','statcast','nba','weather','availability'):
        providers[p]=dict(authentication_status='NOT_PROBED',historical_access=None,coverage=None)
    collection_path=repo/'data/evaluations/odds-collection-latest.json'
    if collection_path.exists():
        collection=json.loads(collection_path.read_text())
        providers['odds_api']['latest_collection']=collection
        quota=collection.get('quota',{})
        if quota.get('requests_remaining') is not None:
            providers['odds_api']['quota_metadata'].update({'x-requests-remaining':quota['requests_remaining'],'x-requests-used':quota.get('provider_requests_used')})
        for result in collection.get('results',[]):
            if result.get('status')=='ARCHIVED':
                from .research_store import ResearchStore
                manifest=ResearchStore(repo/'data').manifest(result['snapshot_id'])
                providers['odds_api']['last_success']=max(providers['odds_api']['last_success'] or '',manifest['fetched_at'])
    models=[]
    for sport in ('CFB','NHL','NFL','MLB','NBA'):
        for market,item in state['categories'][sport].items():
            models.append(dict(sport=sport,market=market,champion_model=None,calibration_version=None,training_cutoff=None,
                historical_sample=item['real_sample_size'],prospective_sample=0,brier_score=None,market_brier_score=None,
                log_loss=None,market_log_loss=None,clv=None,roi=None,roi_ci_low=None,roi_ci_high=None,max_drawdown=None,
                status='UNVALIDATED',implementation_status=item['status'],blocker=item['blocker'],last_updated=now))
    last=dict(generated_at=now,branch=state['branch'],git_commit=source_commit,commit_semantics='source HEAD before this publication commit',
        research_cycle_id='progress-'+now,current_task=state['current_task'],completed_tasks=[g+'.'+n for g,items in state['categories'].items() for n,t in items.items() if t['status']=='COMPLETE'],
        tests_passed=state['tests']['passed'],tests_failed=state['tests']['failed'],sports_updated=[],
        providers_ok=all(providers[k]['authentication_status']=='OK' for k in ('cfbd','odds_api')),
        historical_odds_access=report.get('HISTORICAL_ODDS_ACCESS'),next_task=state['next_task'])
    lines=['# AP EV/SIMS Phase 2 progress','',f'Updated: {now}','',
        'This is the single reconciled execution checklist. Scope is frozen. COMPLETE describes tested implementation, not empirical model approval.',
        '',f"Current task: {state['current_task']}. Next dependency: {state['next_task']}.",
        f"Full suite: {state['tests']['passed']} passed; {state['tests']['failed']} failed.",
        '', 'Real model evaluation sample: 0. All sport/market models remain UNVALIDATED.',
        'Historical odds: BLOCKED_BY_HISTORICAL_ODDS_ACCESS. Current CFBD/Odds authentication is verified.',
        'No real wagers, automatic promotions, purchases, or account changes.', '',
        '| Deliverable | Status | Next action / blocker |','|---|---|---|']
    for group,items in state['categories'].items():
        for name,item in items.items():lines.append('| '+group+'.'+name+' | '+item['status']+' | '+item['next_action']+(' Blocker: '+item['blocker'] if item['blocker'] else '')+' |')
    lines += ['', '## Dependency and evidence policy','',
        '1. Preserve the completed Phase 1, access checks, warehouse foundation, and calibration implementation.',
        '2. Finish the owned odds archive and local-only replay/settlement foundation.',
        '3. Complete research governance, holdout, execution and red-team gates, then safe handoff commands.',
        '4. Resume CFB spread, total, moneyline in order; block empirical claims until provenance and prices qualify.',
        '5. Build independently testable sport contracts in NHL, NFL, MLB, NBA order. Do not mark implementations validated from fixtures.',
        '6. Live and parlay eligibility depend on separately validated component markets. Promotions affect payoff only.',
        '7. Run all tests, update this checklist and TASK_STATE, scan safe files, commit and attempt push at major checkpoints.',
        '8. A failed GitHub push does not stop independent local work. Preserve a committed local checkpoint.',
        '', '## Requirements retained from all prior directives','',
        '- Local-first immutable raw archives, DuckDB/Parquet, content hashing, query cache, quota ledger, bounded collection cadence, offline network prohibition.',
        '- Stable event/player/market identities, schedule revisions, exact line plus price, synchronous no-vig pairs, known settlement and executable-quote evidence.',
        '- Chronological training/calibration/selection/test; untouched holdout; experiment count; negative controls; source and feature ablation; no future revisions.',
        '- Derived uncertainty, calibrated tails, simple-model preference, opportunity-first prop families, role stability and explicit disagreement.',
        '- Persistent cash/bonus/exposure accounting, corrected settlement, CLV kept separate, cluster bootstrap, slippage and bankroll stress.',
        '- Champion/challenger and shadow forecasts, no auto-promotion; postmortem hypotheses, drift/regime diagnostics and daily/longitudinal reports.',
        '- Current edges require Phase 1 gates and fresh executable prices; PASS records retained; no fabricated bankroll, price, feature or performance.',
        '- Complete all 50 red-team audit categories before readiness. Untested critical conditions block READY_FOR_SMALL_STAKES.',
        '- Case reconstructions require actual historical snapshots; otherwise INSUFFICIENT_HISTORICAL_SNAPSHOT.',
        '', 'Detailed per-item files, tests, real and synthetic sample sizes are in TASK_STATE.json.']
    atomic_json(repo/'TASK_STATE.json',state)
    atomic_json(repo/'outputs/provider_status.json',providers)
    atomic_json(repo/'outputs/model_status.json',models)
    atomic_json(repo/'outputs/last_update.json',last)
    atomic_text(repo/'PHASE2_PROGRESS.md','\n'.join(lines)+'\n')
    return last
