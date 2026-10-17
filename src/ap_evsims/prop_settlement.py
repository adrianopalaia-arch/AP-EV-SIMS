"""Append-only prospective statistic settlement; never infer DNP or book rules.

Reuses hash-verified, refreshed player history. Non-final/absent outcomes stay
pending. Historical reconstruction cannot be retroactively called prospective.
"""
import argparse
from collections import defaultdict
import json,math
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from .integrity import digest,utc
from .prop_research import normalize
from .cfb_scores import crps
from .prop_prospective import prop_mass
from .research_store import ResearchStore


def settlement(f,row):
    if digest({k:v for k,v in f.items() if k!='forecast_hash'})!=f['forecast_hash']:raise ValueError('FROZEN_FORECAST_HASH_MISMATCH')
    row.validate()
    if (row.sport,row.market,row.event_id,row.player_id,row.team_id)!=(f['sport'],f['market'],f['event_id'],f['player_id'],f['team_id']):raise ValueError('SETTLEMENT_IDENTITY_MISMATCH')
    if not utc(f['latest_source_capture'])<=utc(f['generated_at'])<utc(f['event_start'])<utc(row.captured_at):raise ValueError('SETTLEMENT_LOOKAHEAD')
    p=f['projection'];pmf={int(k):v for k,v in p['distribution'].items()};priced=[]
    for entry in f['priced_markets']:
        q=entry['quote'];mass=prop_mass(p['distribution'],q['line']);result='WIN' if row.outcome>q['line'] else 'LOSS' if row.outcome<q['line'] else 'PUSH'
        probability=mass['p_win']/(1-mass['p_push']) if mass['p_push']<1 and result!='PUSH' else None
        comparable=entry['settlement_verified'] and entry['price_executable'] and entry.get('qualified_consensus_probability') is not None
        market=entry['qualified_consensus_probability'] if comparable else None
        priced.append(dict(quote_id=q['quote_id'],statistic_result=result,raw_model_probability=probability,
            raw_brier=(probability-(result=='WIN'))**2 if probability is not None else None,
            raw_logloss=-math.log(max(1e-12,probability if result=='WIN' else 1-probability)) if probability is not None else None,
            qualified_consensus=market,market_brier=(market-(result=='WIN'))**2 if market is not None and probability is not None else None,
            actual_cash_roi=None,hypothetical_roi=None,clv=None,reason='BOOK_RULES_AND_EXECUTION_UNVERIFIED' if not comparable else 'NEAR_START_CLOSE_REQUIRED'))
    return dict(sport=f['sport'],market=f['market'],event_id=f['event_id'],player_id=f['player_id'],forecast_hash=f['forecast_hash'],
        model_version=f['model_version'],artifact_hash=f['artifact_hash'],observed_stat=row.outcome,observed_opportunity=row.opportunity,
        outcome_snapshot=row.source_id,outcome_hash=row.source_hash,outcome_captured_at=row.captured_at,
        absolute_error=abs(p['projection']-row.outcome),squared_error=(p['projection']-row.outcome)**2,
        baseline_absolute_error=abs(p['baseline']-row.outcome),crps=crps(pmf,row.outcome),prices=priced,
        mode='RESEARCH_ONLY',cash_committed=0,revision_policy='append source revision without altering forecast')


def cohort_metrics(records,pending):
    """Never pool unlike markets or a challenger with its reference model."""
    groups=defaultdict(lambda:{'records':[],'pending':[]})
    for r in records:groups[(r['model_version'],r['market'])]['records'].append(r)
    for r in pending:groups[(r['model_version'],r['market'])]['pending'].append(r)
    cohorts=[]
    for (version,market),g in sorted(groups.items()):
        rs=g['records'];cohorts.append(dict(model_version=version,market=market,settled_n=len(rs),pending_n=len(g['pending']),
            mae=float(np.mean([r['absolute_error'] for r in rs])) if rs else None,
            rmse=float(np.sqrt(np.mean([r['squared_error'] for r in rs]))) if rs else None,
            baseline_mae=float(np.mean([r['baseline_absolute_error'] for r in rs])) if rs else None,
            crps=float(np.mean([r['crps'] for r in rs])) if rs else None,
            artifact_hashes=sorted({r['artifact_hash'] for r in rs})))
    return cohorts


def run(root,sport):
    root=Path(root);s=ResearchStore(root/'data');at=datetime.now(timezone.utc).isoformat()
    rows,_=normalize(root,sport);outcomes={(r.event_id,r.player_id,r.market):r for r in rows};records=[];pending=[]
    for p in sorted((s.root/'predictions/props').glob('*.json')):
        f=json.loads(p.read_text())
        if f['sport']!=sport:continue
        if digest({k:v for k,v in f.items() if k!='forecast_hash'})!=f['forecast_hash']:raise ValueError('FROZEN_FORECAST_HASH_MISMATCH')
        unresolved=dict(forecast_hash=f['forecast_hash'],model_version=f['model_version'],market=f['market'],event_id=f['event_id'],player_id=f['player_id'])
        if utc(f['event_start'])>=utc(at):pending.append(dict(unresolved,reason='EVENT_NOT_STARTED'));continue
        row=outcomes.get((f['event_id'],f['player_id'],f['market']))
        if row is None:pending.append(dict(unresolved,reason='OUTCOME_OR_DNP_UNVERIFIED'));continue
        try:r=settlement(f,row)
        except ValueError as error:pending.append(dict(unresolved,reason=str(error)));continue
        folder=s.root/'settlements/props';folder.mkdir(exist_ok=True);s._immutable(folder/(digest(r)+'.json'),json.dumps(r,sort_keys=True,indent=2).encode());records.append(r)
    cohorts=cohort_metrics(records,pending);one=cohorts[0] if len(cohorts)==1 else {}
    report=dict(sport=sport,generated_at=at,settled_n=len(records),pending_n=len(pending),pending=pending,cohorts=cohorts,
        mae=one.get('mae'),rmse=one.get('rmse'),baseline_mae=one.get('baseline_mae'),crps=one.get('crps'),
        aggregate_metric_scope='No pooled accuracy across markets/model versions; inspect cohorts',
        qualified_market_comparison_n=sum(p['market_brier'] is not None for r in records for p in r['prices']),
        real_cash_roi=None,hypothetical_roi=None,clv=None,recommendations_enabled=False,records=records)
    (root/'outputs'/(sport.lower()+'_prop_settlement.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return {k:v for k,v in report.items() if k not in ('records','pending')}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--sport',choices=['NFL','NBA','NHL','MLB','all'],default='all');args=p.parse_args()
    for sport in ['NFL','NBA','NHL','MLB'] if args.sport=='all' else [args.sport]:print(json.dumps(run(args.root,sport)),flush=True)
