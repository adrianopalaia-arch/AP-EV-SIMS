"""Run independent score research and freeze future CFB forecasts, without bets.

python -m ap_evsims.cfb_score_research --root .
Offline by default. Newly captured historical outcomes keep their actual clocks.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import numpy as np

from .cfb_scores import (POLICY, VERSION, RECONSTRUCTED, ScoreMarginModel, score_observations,
                         chronological_evaluation, metrics, margin_distribution, market_mass)
from .cfb_universe import verified_sources
from .identity import map_cfb_events
from .integrity import digest, utc
from .research_store import ResearchStore
from .warehouse import Warehouse
from .paper_market import archived_quotes, fresh, consensus, closing_evidence
from .display_pricing import opposite_side, market_calculations


def immutable_json(store,path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    store._immutable(path,json.dumps(body,sort_keys=True,allow_nan=False,indent=2).encode())


def freeze(store,record):
    """One first-issued forecast per event/version; reruns cannot rewrite it."""
    # JSON object keys are strings. Canonicalize before hashing (integer PMF
    # support would otherwise sort differently after a JSON round trip).
    record=json.loads(json.dumps(record,allow_nan=False))
    if not utc(record['latest_source_capture'])<=utc(record['generated_at'])<utc(record['event_start']):
        raise ValueError('FORECAST_LOOKAHEAD_RISK')
    if record['model_status']!='UNVALIDATED' or record['recommendations_enabled'] is not False or record['p_low'] is not None or record['calibrated_probability'] is not None:
        raise ValueError('UNVALIDATED_AUTHORITY_ESCALATION')
    path=store.root/'predictions'/'cfb-score'/ (digest([record['event_id'],record['model_version']])+'.json')
    if path.exists():
        old=json.loads(path.read_text(encoding='utf-8'))
        if digest({k:v for k,v in old.items() if k!='forecast_hash'})!=old['forecast_hash']:raise ValueError('FORECAST_HASH_MISMATCH')
        return old,False
    record=dict(record,forecast_hash=digest(record));immutable_json(store,path,record)
    return record,True


def settle_forecasts(store,rows,quotes,at):
    latest={r.event_id:r for r in rows};settled=[]
    for path in sorted((store.root/'predictions'/'cfb-score').glob('*.json')):
        f=json.loads(path.read_text(encoding='utf-8'))
        if digest({k:v for k,v in f.items() if k!='forecast_hash'})!=f['forecast_hash']:raise ValueError('FORECAST_HASH_MISMATCH')
        if f['model_version']!=VERSION:continue
        r=latest.get(f['event_id'])
        if r is None:continue
        if (r.home_id,r.away_id,utc(r.kickoff))!=(f['home_id'],f['away_id'],utc(f['event_start'])):
            continue # Rescheduled/wrong identity cannot be graded as the original event.
        if not utc(f['generated_at'])<utc(r.kickoff)<utc(r.available_at)<=utc(at):raise ValueError('SETTLEMENT_LOOKAHEAD_RISK')
        pmf={int(k):v for k,v in f['margin_distribution'].items()};prices=[]
        for entry in f['priced_markets']:
            q=entry['quote'];mass=entry['model_mass'];value=r.margin+(q['line'] or 0)
            result='WIN' if value>0 else 'LOSS' if value<0 else 'PUSH'
            p=mass['p_win']/(1-mass['p_push']) if mass['p_push']<1 else None
            c=entry['consensus']['probability'];scored=result!='PUSH' and p is not None
            from .historical import unit_profit
            prices.append(dict(quote_id=q['quote_id'],result=result,model_probability=p,market_probability=c,
                model_brier=(p-(result=='WIN'))**2 if scored else None,
                market_brier=(c-(result=='WIN'))**2 if scored and c is not None else None,
                hypothetical_unit_profit=unit_profit(result,q['american_odds']),
                closing=closing_evidence(store,q,quotes,at)))
        body=dict(forecast_hash=f['forecast_hash'],event_id=r.event_id,model_version=f['model_version'],
            result_snapshot=r.source_id,result_hash=r.source_hash,result_available_at=r.available_at,
            actual_margin=r.margin,absolute_error=abs(f['expected_home_margin']-r.margin),
            squared_error=(f['expected_home_margin']-r.margin)**2,prices=prices,
            status='RESEARCH_ONLY',cash_staked=0,revision_policy='append source revision; never overwrite forecast')
        identity=digest(body);immutable_json(store,store.root/'settlements'/'cfb-score'/(identity+'.json'),body)
        settled.append(body)
    paired=[p for r in settled for p in r['prices'] if p['model_brier'] is not None and p['market_brier'] is not None]
    return dict(settled_forecasts=len(settled),mae=float(np.mean([r['absolute_error'] for r in settled])) if settled else None,
        rmse=float(np.sqrt(np.mean([r['squared_error'] for r in settled]))) if settled else None,
        matched_consensus_n=len(paired),model_brier=float(np.mean([r['model_brier'] for r in paired])) if paired else None,
        consensus_brier=float(np.mean([r['market_brier'] for r in paired])) if paired else None,
        validated=False,real_cash_roi=None,records=settled)


def run(root):
    root=Path(root);store=ResearchStore(root/'data');warehouse=Warehouse(store.root)
    started=datetime.now(timezone.utc).isoformat()
    sources=verified_sources(store,warehouse,'games',started)
    rows,future,coverage=score_observations(sources,started)
    table=store.write_table('cfb-completed-score-observations',[asdict(r) for r in rows])
    # Save the exact fixed experiment before fitting or examining metric values.
    immutable_json(store,store.root/'evaluations'/('cfb-score-policy-'+digest(POLICY)+'.json'),POLICY)
    records,folds=chronological_evaluation(rows)
    evaluation=[r for r in records if r['season']>=POLICY['evaluation_start_season']]
    evaluated_table=store.write_table('cfb-score-chronological-forecasts',records)
    model=ScoreMarginModel().fit(rows,started,utc(started).year,prospective=True)
    residual_rows=[r for r in records if utc(r['kickoff'])<utc(started)-timedelta(days=POLICY['embargo_days'])]
    residuals=[r['actual_margin']-r['predicted_margin'] for r in residual_rows]
    artifact=dict(model=model.state,residuals=residuals,residual_fingerprint=digest(residual_rows),
                  model_status='UNVALIDATED',betting_authority=False)
    artifact_hash=digest(artifact);immutable_json(store,store.root/'models'/('cfb-score-'+artifact_hash+'.json'),artifact)
    at=datetime.now(timezone.utc).isoformat()
    quotes=archived_quotes(store,warehouse,at)
    teams=verified_sources(store,warehouse,'teams',at)
    events={q['event_id']:dict(id=q['event_id'],home_team=q['home_team'],away_team=q['away_team'],commence_time=q['event_start']) for q in quotes}
    mapping={};identity_rejections=[]
    if teams:
        tm,t=teams[-1];mapping,identity_rejections=map_cfb_events(t,[g for g,m in future],list(events.values()),
            alias_snapshot=tm['snapshot_id'],game_snapshot=digest([m['snapshot_id'] for m,p in sources]),available_at=at)
    mapped={}
    for key,m in mapping.items():mapped.setdefault(m['event_id'],[]).append(key)
    # Only the latest full current response can authorize an executable price;
    # older offers omitted/suspended in it are not resurrected.
    snapshots=[m for m in (store.manifest(q['snapshot_id']) for q in {q['snapshot_id']:q for q in quotes}.values()) if m['endpoint']=='sports/americanfootball_ncaaf/odds']
    latest_sid=max(snapshots,key=lambda m:utc(m['available_at']))['snapshot_id'] if snapshots else None
    current=[q for q in quotes if q['snapshot_id']==latest_sid]
    predictions=[];rejections=Counter();new_count=0
    for g,m in future:
        if not utc(at)<utc(g['startDate'])<=utc(at)+timedelta(days=7):continue
        try:mean=model.predict(str(g['homeId']),str(g['awayId']),g['neutralSite'])
        except ValueError as error:rejections[str(error)]+=1;continue
        pmf=margin_distribution(mean,residuals)
        if pmf is None:rejections['INSUFFICIENT_OOF_RESIDUALS']+=1;continue
        priced=[]
        for q in current:
            if q['event_id'] not in mapped.get(str(g['id']),[]) or q['book']!='draftkings' or q['market'] not in ('spreads','h2h') or q['period']!='full_game' or q['selection']!=q['home_team'] or not fresh(q,at):continue
            other=opposite_side(q,[v for v in current if v['pair_id']==q['pair_id']]);calc=market_calculations(q,other)
            if calc['market_no_vig_probability'] is None:continue
            priced.append(dict(quote=q,opposite_quote=other,model_mass=market_mass(pmf,q['line'] or 0),
                               market=calc,consensus=consensus(q,current,at),executable_model_ev=None))
        samples=sorted(int(round(mean+x)) for x in residuals)
        record=dict(event_id=str(g['id']),home_id=str(g['homeId']),away_id=str(g['awayId']),
            home_team=g['homeTeam'],away_team=g['awayTeam'],event_start=utc(g['startDate']).isoformat(),
            generated_at=at,model_version=VERSION,artifact_hash=artifact_hash,feature_cutoff=started,
            training_n=model.state['training_n'],training_fingerprint=model.state['training_fingerprint'],
            source_hashes=sorted(set(model.state['source_hashes']+[m['payload_hash']])),schedule_snapshot=m['snapshot_id'],
            latest_source_capture=max(model.state['latest_source_capture'],m['fetched_at']),
            expected_home_margin=mean,margin_distribution=pmf,home_moneyline_mass=market_mass(pmf),
            predictive_margin_interval_80=[float(np.quantile(samples,.1)),float(np.quantile(samples,.9))],
            uncertainty_basis='prior out-of-fold residual dispersion; not calibrated probability confidence',
            training_provenance=RECONSTRUCTED,prediction_provenance='FROZEN_BEFORE_KICKOFF',
            calibrated_probability=None,p_low=None,model_status='UNVALIDATED',mode='RESEARCH_ONLY',
            recommendations_enabled=False,cash_staked=0,reference_unit=22,priced_markets=priced,
            matched_odds_event_ids=mapped.get(str(g['id']),[]),
            pass_reasons=['MODEL_NOT_CALIBRATED','PROSPECTIVE_EVIDENCE_INSUFFICIENT','UNVERIFIED_LINEUP']+([] if priced else ['MISSING_FRESH_MATCHED_PRICE']))
        frozen,is_new=freeze(store,record);predictions.append(frozen);new_count+=is_new
    prospective=settle_forecasts(store,rows,quotes,at)
    report=dict(generated_at=at,model_version=VERSION,model_status='UNVALIDATED',recommendations_enabled=False,
        real_source_coverage=coverage,score_training_table=table,current_training_n=model.state['training_n'],
        artifact_hash=artifact_hash,evaluation_table=evaluated_table,synthetic_performance_sample=0,
        retrospective_provenance=RECONSTRUCTED,strict_historical_as_of_qualified_n=0,
        warmup_forecast_n=sum(r['season']<2025 for r in records),evaluation=metrics(evaluation),
        by_season={str(y):metrics([r for r in evaluation if r['season']==y]) for y in sorted({r['season'] for r in evaluation})},
        folds=folds,policy=POLICY,new_frozen_predictions=new_count,available_frozen_predictions=len(predictions),
        prospective=prospective,matched_future_events=sum(bool(r['matched_odds_event_ids']) for r in predictions),
        fresh_priced_future_predictions=sum(bool(r['priced_markets']) for r in predictions),
        future_rejections=dict(rejections),identity_rejections=dict(Counter(r['reason'] for r in identity_rejections)),
        blockers=['HISTORICAL_ODDS_ACCESS','HISTORICAL_REVISION_TIMING_UNVERIFIED','PROSPECTIVE_CALIBRATION_PENDING',
                  'CRITICAL_ROLE_AND_AVAILABILITY_UNVERIFIED'],
        limitations=['Regular-season FBS vs FBS only; captured coverage is not a complete all-competition schedule.',
                    'Past final-score reconstruction uses later captured provider revisions; it is not timestamp-authentic betting evidence.',
                    'Weekly seven-day embargo approximates prior completion, not original historical publication.',
                    'Fixed priors/settings; 2024 residual warm-up, 2025/2026 expanding evaluation; no tuning after results.',
                    'Raw probabilities are uncalibrated; log loss uses a numerical 1e-12 floor.',
                    'Week bootstrap describes correlated-sample uncertainty, not immunity to regime changes.'])
    immutable_json(store,store.root/'evaluations'/('cfb-score-run-'+digest(report)+'.json'),report)
    out=root/'outputs';out.mkdir(exist_ok=True)
    (out/'cfb_score_research_status.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (out/'cfb_score_research_predictions.json').write_text(json.dumps(dict(generated_at=at,mode='RESEARCH_ONLY',
        recommendations_enabled=False,predictions=predictions),indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',default='.')
    report=run(parser.parse_args().root)
    print(json.dumps({k:v for k,v in report.items() if k not in ('folds','policy','limitations','prospective')},indent=2))


if __name__=='__main__':main()
