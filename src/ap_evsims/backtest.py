"""Expanding, event-disjoint folds; independent model/calibration/evaluation windows."""
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
import json
import math
import statistics
from collections import defaultdict
from .historical import partition,validate_dataset,settle,unit_profit
from .models.cfb import CFBSpreadModel,CFBTotalModel,CFBWinModel
from .models.probability_calibration import CalibrationObservation,select_calibration
from .models.artifacts import save_model
from .calibration import brier_score,log_loss,calibration_bins
from .integrity import utc,digest,ValidationRegistry
from .odds import devig_two_way,american_to_implied
from .market import closing_line_value
from .exposure import ExposureLedger,ExposureLimits
from .ledger import Ledger
from .model_bridge import decide_prediction,pipeline_version

def calibration_observations(model,rows):
    out=[]
    for r in rows:
        p=model.predict(r.features,r.context)
        if p.raw_probability is None: raise ValueError('INVALID_CALIBRATION_FEATURES: '+','.join(p.reasons))
        outcome=settle(r)
        if outcome=='PUSH': continue
        out.append(CalibrationObservation(r.context.event_id,p.raw_probability,int(outcome=='WIN'),model.model_version,
            model.artifact_id,model.training_cutoff,r.context.prediction_timestamp,r.features.timestamp,r.result_available_at))
    return out

def make_record(row,prediction,decision):
    c=row.context; settlement=settle(row)
    market_p=devig_two_way(c.odds,c.opposite_odds)[0]
    clv=closing_line_value(c,row.closing_context)
    return dict(observation_id=row.observation_id,sport=c.sport,event_id=c.event_id,market=c.market_type,selection=c.selection,
        book=c.book,line=c.line,odds=c.odds,opposite_odds=c.opposite_odds,quote_timestamp=c.quote_timestamp,
        prediction_timestamp=c.prediction_timestamp,event_timestamp=c.event_timestamp,feature_timestamp=row.features.timestamp,
        result_available_at=row.result_available_at,training_cutoff=prediction.training_cutoff,model_version=prediction.model_version,
        pipeline_version=pipeline_version(prediction),calibration_version=prediction.calibration_version,model_artifact_id=prediction.model_artifact_id,
        data_fingerprint=prediction.data_fingerprint,raw_probability=prediction.raw_probability,
        calibrated_probability=prediction.calibrated_probability,lower_bound=prediction.uncertainty_lower_bound,
        implied_probability=american_to_implied(c.odds),no_vig_probability=market_p,
        edge=None if prediction.uncertainty_lower_bound is None else prediction.uncertainty_lower_bound-market_p,
        conservative_ev=decision.get('ev_conservative'),fair_odds=prediction.fair_american_odds,max_acceptable_price=decision.get('max_acceptable_price'),
        data_age_seconds=(utc(c.prediction_timestamp)-utc(row.features.timestamp)).total_seconds(),
        status=decision['status'],pass_reasons=decision['reasons'],stake_usd=decision['stake_usd'],
        settlement=settlement,outcome=None if settlement=='PUSH' else int(settlement=='WIN'),
        unit_profit=unit_profit(settlement,c.odds),closing_line=None if not row.closing_context else row.closing_context.line,
        closing_odds=None if not row.closing_context else row.closing_context.odds,clv=clv,
        explanation=prediction.explanation)

def summarize(records):
    raw=[r for r in records if r['outcome'] is not None and r['raw_probability'] is not None]
    calibrated=[r for r in records if r['outcome'] is not None and r['calibrated_probability'] is not None]
    selected=[r for r in records if r['status']=='RESEARCH_CANDIDATE' and r['stake_usd']>0]
    def score(rows,key):
        if not rows: return dict(n=0,brier=None,logloss=None,market_brier=None,market_logloss=None,calibration_curve=[])
        p=[r[key] for r in rows]; y=[r['outcome'] for r in rows]; market=[r['no_vig_probability'] for r in rows]
        return dict(n=len(rows),brier=brier_score(p,y),logloss=log_loss(p,y),market_brier=brier_score(market,y),
            market_logloss=log_loss(market,y),calibration_curve=calibration_bins(p,y))
    profit=sum(r['unit_profit']*r['stake_usd'] for r in selected); amount=sum(r['stake_usd'] for r in selected)
    # Settle in result-availability order, not prediction order.
    balance=peak=drawdown=0.
    for r in sorted(selected,key=lambda r:(utc(r['result_available_at']),r['observation_id'])):
        balance+=r['unit_profit']*r['stake_usd']; peak=max(peak,balance); drawdown=max(drawdown,peak-balance)
    points=[r['clv']['point_clv'] for r in selected if r['clv']['point_clv'] is not None]
    prices=[r['clv']['price_clv'] for r in selected if r['clv']['price_clv'] is not None]
    buckets=[]
    for lo,hi in ((-1,0),(0,.02),(.02,.05),(.05,.1),(.1,1.01)):
        rows=[r for r in records if r['edge'] is not None and lo<=r['edge']<hi]
        bets=[r for r in rows if r in selected]; stake=sum(r['stake_usd'] for r in bets)
        buckets.append(dict(edge_low=lo,edge_high=hi,forecast_n=len(rows),bet_count=len(bets),
            roi=None if not stake else sum(r['unit_profit']*r['stake_usd'] for r in bets)/stake))
    by_market={}; by_sport={}
    for field,output in (('market',by_market),('sport',by_sport)):
        for value in sorted({r[field] for r in records}):
            group=[r for r in records if r[field]==value and r['outcome'] is not None and r['calibrated_probability'] is not None]
            output[value]=score(group,'calibrated_probability')
    return dict(historical_sample_size=len({r['event_id'] for r in records}),prediction_count=len(records),
        raw=score(raw,'raw_probability'),calibrated=score(calibrated,'calibrated_probability'),
        push_count=sum(r['settlement']=='PUSH' for r in records),bet_count=len(selected),staked=amount,profit=profit if selected else None,
        roi=profit/amount if amount else None,max_drawdown=drawdown if selected else None,
        point_clv_mean=statistics.mean(points) if points else None,point_clv_n=len(points),
        price_clv_mean=statistics.mean(prices) if prices else None,price_clv_n=len(prices),
        performance_by_edge_bucket=buckets,performance_by_market=by_market,performance_by_sport=by_sport,
        reliability_diagram_data=score(calibrated,'calibrated_probability')['calibration_curve'])

def run_walk_forward(rows,windows, *, market_type,output_dir,feature_keys=None,
                     minimum_train=80,minimum_calibration=300,minimum_selection=100,bootstrap_samples=32,
                     bankroll=1000,minimum_validation=300,dataset_kind='provider_history',provenance_store=None):
    if dataset_kind not in ('provider_history','synthetic_test'): raise ValueError('unknown dataset kind')
    rows=validate_dataset(rows); rows=[r for r in rows if r.context.sport=='CFB' and r.context.market_type==market_type]
    if rows and dataset_kind=='provider_history':
        if provenance_store is None: raise ValueError('PROVIDER_PROVENANCE_REQUIRED')
        from .canonical import verify_provider_dataset
        verify_provider_dataset(provenance_store,rows)
    output=Path(output_dir); output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()): raise ValueError('EVALUATION_DIRECTORY_NOT_EMPTY')
    registry=ValidationRegistry(output/'paper-validation.db'); exposure=ExposureLedger(output/'paper-exposure.db')
    ledger=Ledger(output/'paper-decisions.jsonl'); limits=ExposureLimits(bankroll)
    records=[]; folds=[]; evaluated=set(); pending=[]; used_intervals=[]
    for index,window in enumerate(windows):
        window.validate()
        # Fold evaluation periods must advance without overlapping.
        if used_intervals and utc(window.selection_end)<used_intervals[-1]: raise ValueError('OVERLAPPING_EVALUATION_WINDOWS')
        used_intervals.append(utc(window.evaluation_end))
        train,calibration,selection,evaluation=partition(rows,window)
        model={'spread':CFBSpreadModel,'total':CFBTotalModel,'win':CFBWinModel}[market_type](
            feature_keys=feature_keys,minimum_train=minimum_train,bootstrap_samples=bootstrap_samples)
        fold=dict(index=index,window=asdict(window),train_n=len(train),calibration_n=len(calibration),selection_n=len(selection),evaluation_n=len(evaluation))
        try:
            model.fit(train,training_cutoff=window.training_end)
            fit_obs=calibration_observations(model,calibration); sel_obs=calibration_observations(model,selection)
            fitted=select_calibration(fit_obs,sel_obs,model_version=model.model_version,model_artifact_id=model.artifact_id,
                selection_end=window.selection_end,minimum_fit=minimum_calibration,minimum_selection=minimum_selection)
            model.attach_calibration(fitted)
            fold.update(model_version=model.model_version,model_artifact_id=model.artifact_id,calibration_version=fitted.version,
                calibration_method=fitted.map.kind,calibration_selection_scores=fitted.selection_scores,calibration_sample_sizes=fitted.sample_sizes)
        except ValueError as e:
            fold['reason']=str(e)
            # A failed fit/calibration still produces a PASS record for every
            # evaluation row; it never silently removes a losing candidate.
        if model.training_cutoff: save_model(model,output/f'model-{index}.json')
        prior_validation=[]
        for r in evaluation:
            if r.economic_key in evaluated: raise ValueError('DUPLICATE_EVALUATION_EVENT')
            evaluated.add(r.economic_key)
            now=r.context.snapshot_available_at or r.context.quote_timestamp
            for position_id,available in list(pending):
                if utc(available)<=utc(now):
                    exposure.transition(position_id,'cancelled',available); pending.remove((position_id,available))
            prediction=model.predict(r.features,r.context)
            known=[v for v in prior_validation if utc(v['outcome_time'])<utc(r.features.timestamp)]
            evidence=None
            if len(known)>=minimum_validation:
                evidence=registry.evaluate(sport='CFB',market=market_type,model_version=pipeline_version(prediction),mode='pregame',
                    training_cutoff=model.training_cutoff,expires=(utc(r.context.event_timestamp)+timedelta(days=1)).isoformat(),observations=known)
            decision=decide_prediction(r,prediction,evidence,registry=registry,exposure=exposure,limits=limits,ledger=ledger,now=now)
            if decision['status']=='RESEARCH_CANDIDATE': pending.append((decision['candidate_id'],r.result_available_at))
            record=make_record(r,prediction,decision); records.append(record)
            if record['outcome'] is not None and prediction.calibrated_probability is not None and not prediction.reasons:
                prior_validation.append(dict(id=r.observation_id,sport='CFB',market=market_type,model_version=pipeline_version(prediction),mode='pregame',
                    feature_time=r.features.timestamp,prediction_time=r.context.prediction_timestamp,quote_time=r.context.quote_timestamp,
                    event_start=r.context.event_timestamp,outcome_time=r.result_available_at,p=prediction.calibrated_probability,market_p=record['no_vig_probability'],outcome=record['outcome']))
        folds.append(fold)
    payload=dict(schema_version=1,dataset_kind=dataset_kind,dataset_fingerprint=digest([asdict(r) for r in rows]),
        input_event_count=len({r.context.event_id for r in rows}),market=market_type,folds=folds,summary=summarize(records),
        profitability_demonstrated=False,records_path='predictions.jsonl',limitations=[
            'No empirical profitability conclusion; synthetic tests are not provider data.',
            'Calibration bounds are dependence-adjusted diagnostics, not validated individual coverage.',
            'Phase 1 rejects integer lines, missing availability/features, unvalidated pipelines and excess exposure.',
            'Training/calibration windows are not out-of-sample performance rows.',
            'Point CLV and price CLV are separate; missing or different-line closing prices remain missing.'])
    from .evaluation_intervals import paired_score_intervals
    payload['paired_market_comparison_intervals']=paired_score_intervals(records)
    (output/'predictions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True,allow_nan=False)+'\n' for r in records),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(payload,sort_keys=True,allow_nan=False,indent=2),encoding='utf-8')
    from .reporting import write_ranking
    write_ranking(records,output)
    return payload
