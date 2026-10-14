"""Keep Phase 1 decision authority, probability, price and exposure checks intact."""
from .decision import ResearchCandidate,decide
from .integrity import digest

def pipeline_version(prediction):
    return prediction.model_version+'|pipeline-'+digest(dict(artifact=prediction.model_artifact_id,calibration=prediction.calibration_version))[:16]

def decide_prediction(row,prediction,evidence, *, registry,exposure,limits,ledger,now):
    c=row.context
    # Evidence is for this frozen model + calibrator, not just an algorithm name.
    values={k:dict(value=v.value,source=v.source,available_at=v.available_at) for k,v in row.features.values.items()}
    usable=not prediction.reasons and prediction.calibrated_probability is not None and prediction.uncertainty_lower_bound is not None
    candidate=ResearchCandidate(candidate_id=row.observation_id+'-'+pipeline_version(prediction),event_id=c.event_id,
        sport=c.sport,market=c.market_type,selection=c.selection,model_version=pipeline_version(prediction),mode='pregame',
        dataset_fingerprint=getattr(evidence,'dataset_fingerprint','unregistered'),training_cutoff=prediction.training_cutoff or row.features.timestamp,
        event_start=c.event_timestamp,quote_time=c.quote_timestamp,opposite_quote_time=c.quote_timestamp,
        availability_time=row.availability_timestamp or row.features.timestamp,feature_time=row.features.timestamp,
        prediction_time=c.prediction_timestamp,p_model=prediction.calibrated_probability if usable else float('nan'),
        p_low=prediction.uncertainty_lower_bound if usable else float('nan'),american_odds=c.odds,opposite_odds=c.opposite_odds,
        book=c.book,market_line=c.line,opposite_market_line=c.opposite_line,lineup_verified=row.lineup_verified,
        live_state_verified=False,binary_settlement_verified=row.binary_settlement_verified,
        exposure_groups=row.risk_groups,features=values)
    ledger.append(dict(record_type='model_prediction',candidate_id=candidate.candidate_id,prediction=prediction.to_dict(),
        phase1_pipeline_version=candidate.model_version,market_context=c.__dict__))
    result=decide(candidate,evidence,registry=registry,exposure=exposure,limits=limits,ledger=ledger,now=now)
    if prediction.reasons:
        # The invalid probability interval already ensured Phase 1 PASS. Retain
        # the model-specific diagnosis in an append-only supplemental record.
        result['reasons']=list(dict.fromkeys(list(prediction.reasons)+result['reasons']))
        ledger.append(dict(record_type='model_rejection',candidate_id=candidate.candidate_id,reasons=result['reasons']))
    return result
