"""Opt-in, source-verified existing CFB artifacts for descriptive dashboard EV.

No model is trained from prices or from a flag saying observations are real.
The existing prediction/approval pipeline remains authoritative and unchanged.
"""
import json, math
from dataclasses import asdict, replace
from .integrity import digest, utc
from .models.base import FeatureSnapshot, FeatureValue, MarketContext
from .models.artifacts import load_model
from .historical import load_dataset
from .canonical import verify_provider_dataset, verify_feature_sources
from .display_pricing import probability, outcome_ev, conditional_ev


class ResearchQuoteContext(MarketContext):
    """Current research inference occurs after quote capture, before event start.

    The historical context also supports forecasts frozen before later quotes.
    Keep that contract unchanged; do not backdate this display's prediction time.
    """
    def validate(self):
        MarketContext.validate(replace(self,prediction_timestamp=self.quote_timestamp))
        if self.snapshot_available_at is None or not utc(self.quote_timestamp)<=utc(self.snapshot_available_at)<=utc(self.prediction_timestamp)<utc(self.event_timestamp):
            raise ValueError('LOOKAHEAD_RISK')


def _local_file(store,name):
    path=(store.root/name).resolve()
    if store.root.resolve() not in path.parents or not path.is_file():raise ValueError('MISSING_LOCAL_MODEL_EVIDENCE')
    return path


def verified_models(store, at):
    registry=store.root/'models/dashboard-models.json'
    if not registry.is_file():return {},['NO_TRAINED_RESEARCH_MODEL']
    models={};issues=[]
    try:
        entries=json.loads(registry.read_text(encoding='utf-8'))['models']
        if not isinstance(entries,list):raise ValueError()
    except (ValueError,KeyError,TypeError,OSError):return {},['INVALID_RESEARCH_MODEL_REGISTRY']
    for entry in entries:
        try:
            model=load_model(_local_file(store,entry['artifact']))
            rows=load_dataset(_local_file(store,entry['training_dataset']))
            verify_provider_dataset(store,rows)
            if len(rows)!=model.training_n or len(rows)<model.minimum_train:raise ValueError()
            if digest([asdict(r)|{'closing_context':None} for r in rows])!=model.training_fingerprint:raise ValueError()
            if len({r.context.event_id for r in rows})!=len(rows):raise ValueError()
            if utc(model.training_cutoff)>=utc(at):raise ValueError()
            for r in rows:
                if r.context.sport!='CFB' or r.context.market_type!=model.market_type:raise ValueError()
                if not utc(r.context.event_timestamp)<utc(model.training_cutoff) or utc(r.result_available_at)>utc(model.training_cutoff):raise ValueError()
                r.features.validate(r.context.prediction_timestamp,model.feature_keys)
            # A self-consistent hash plus a claimed dataset does not prove the
            # coefficients were fitted from it. Reproduce the existing recipe.
            reproduced=type(model)(**{k:model.spec[k] for k in
                ('feature_keys','minimum_train','ridge_penalty','bootstrap_samples','seed')})
            reproduced.fit(rows,training_cutoff=model.training_cutoff)
            if reproduced.artifact_id!=model.artifact_id:raise ValueError('MODEL_TRAINING_REPRODUCTION_MISMATCH')
            saved_calibration=model.calibrator;model.calibrator=None
            if saved_calibration is not None:
                try:
                    from .backtest import calibration_observations
                    from .models.probability_calibration import select_calibration
                    fit=load_dataset(_local_file(store,entry['calibration_fit_dataset']))
                    select=load_dataset(_local_file(store,entry['calibration_selection_dataset']))
                    verify_provider_dataset(store,fit+select)
                    event_groups=[{r.context.event_id for r in group} for group in (rows,fit,select)]
                    if any(event_groups[a]&event_groups[b] for a,b in ((0,1),(0,2),(1,2))):raise ValueError()
                    regenerated=select_calibration(calibration_observations(model,fit),calibration_observations(model,select),
                        model_version=model.model_version,model_artifact_id=model.artifact_id,selection_end=saved_calibration.selection_end)
                    if regenerated.version!=saved_calibration.version:raise ValueError()
                    model.attach_calibration(regenerated)
                except (ValueError,KeyError,TypeError,OSError):issues.append('CALIBRATION_PROVENANCE_UNVERIFIED')
            if model.market_type in models:raise ValueError('AMBIGUOUS_RESEARCH_MODEL')
            models[model.market_type]=model
        except (ValueError,KeyError,TypeError,OSError,AttributeError):
            # Errors may contain local/private paths; publish only fixed codes.
            return {},issues+['RESEARCH_MODEL_PROVENANCE_UNVERIFIED']
    return models,issues


def attach_prediction(row, prediction, at):
    """Research-only projection. Never copies a probability into approval fields."""
    if prediction.raw_probability is None:return row
    expected_market={'spreads':'spread','totals':'total','h2h':'win'}.get(row['market'])
    if (prediction.sport!=row['sport'] or prediction.market_type!=expected_market or
        prediction.event_id!=row.get('canonical_event_id',row['event_id']) or
        not prediction.model_artifact_id or prediction.prediction_timestamp is None or
        utc(prediction.prediction_timestamp)!=utc(at) or
        prediction.explanation.get('market_line')!=row['line'] or row['push_policy']=='UNKNOWN'):
        raise ValueError('PREDICTION_CONTEXT_MISMATCH')
    if not (utc(prediction.training_cutoff)<utc(prediction.feature_snapshot_timestamp)<=utc(at)<utc(row['event_start']) and
        utc(row['quote_timestamp'])<=utc(row['data_timestamps']['provider_available'])<=utc(at)):
        raise ValueError('LOOKAHEAD_RISK')
    raw=probability(prediction.raw_probability)
    cal=prediction.calibrated_probability;lower=prediction.uncertainty_lower_bound
    if cal is not None:probability(cal)
    if lower is not None:
        probability(lower)
        if cal is None or lower>cal:raise ValueError('INVALID_MODEL_INTERVAL')
    e=prediction.explanation
    win,push,loss=(e[k] for k in ('raw_win_probability','push_probability','raw_loss_probability'))
    raw_ev=outcome_ev(win,loss,push,row['odds'])
    if push>=1 or not math.isclose(raw,win/(1-push),abs_tol=1e-6,rel_tol=0):raise ValueError('INVALID_MODEL_OUTCOME_MASS')
    cal_ev=conditional_ev(cal,row['odds'],push) if cal is not None else None
    reasons=list(dict.fromkeys(row['pass_reason']+list(prediction.reasons)+['RESEARCH_ONLY','P_LOW_COVERAGE_UNVERIFIED']))
    if row['push_policy']=='NO_PUSH' and push>1e-9:
        reasons.append('MODEL_SETTLEMENT_MISMATCH');raw_ev=cal_ev=None
    row.update(model_probability=raw,calibrated_probability=cal,p_low=lower,
        ap_raw_ev=raw_ev,ap_calibrated_ev=cal_ev,ap_model_expected_value=cal_ev if cal_ev is not None else raw_ev,
        ap_push_probability=push,ap_win_probability=win,ap_loss_probability=loss,
        ap_probability_basis='CONDITIONAL_ON_NON_PUSH',ap_ev_basis='CALIBRATED_RESEARCH' if cal_ev is not None else 'RAW_RESEARCH',
        p_low_status='UNVALIDATED_DIAGNOSTIC' if lower is not None else 'UNAVAILABLE',
        model_version=prediction.model_version,model_artifact_id=prediction.model_artifact_id,
        training_cutoff=prediction.training_cutoff,calibration_version=prediction.calibration_version,
        feature_fingerprint=prediction.data_fingerprint,model_explanation=e,
        probability_source='UNVALIDATED RESEARCH MODEL',data_quality='RESEARCH_ONLY',pass_reason=reasons,
        # Preliminary positive EV has no authority to emit a pick or stake.
        decision='PASS',phase1_eligible=False,model_status='UNVALIDATED',expected_value=None,stake=None)
    row['data_timestamps'].update(feature_snapshot=prediction.feature_snapshot_timestamp,model_prediction=utc(at).isoformat())
    return row


def add_research_display(store, rows, universe, at):
    models,issues=verified_models(store,at)
    report=dict(status='NO_TRAINED_RESEARCH_MODEL' if not models else 'RESEARCH_ONLY',issues=issues,
        research_predictions=0,validated_models=0,real_evaluation_sample=0,
        trained_research_models={k:dict(model_version=m.model_version,artifact_id=m.artifact_id,training_n=m.training_n,
            training_cutoff=m.training_cutoff) for k,m in models.items()})
    if not models:return report
    matches={}
    for game in universe.get('games',[]):
        for identity in game['matched_odds_event_ids']:matches.setdefault(identity,[]).append(game)
    for row in rows:
        kind={'spreads':'spread','totals':'total','h2h':'win'}.get(row['market'])
        model=models.get(kind)
        if row['sport']!='CFB' or model is None or row.get('period')!='full_game':continue
        try:
            games=matches.get(row['event_id'],[])
            if len(games)!=1 or utc(games[0]['event_start'])!=utc(row['event_start']):raise ValueError()
            game=games[0]
            features=FeatureSnapshot(game['event_id'],'CFB',universe['generated_at'],
                {k:FeatureValue(**v) for k,v in game['verified_features'].items()})
            features.validate(at,model.feature_keys);verify_feature_sources(store,features)
            selection=('over' if row['selection']=='Over' else 'under') if kind=='total' else ('home' if row['selection']==row['home_team'] else 'away')
            c=ResearchQuoteContext(game['event_id'],'CFB',kind,selection,row['book'],row['line'],row['odds'],row['opposite_odds'],
                utc(at).isoformat(),row['quote_timestamp'],row['event_start'],row['source_snapshot_id'],row['line'],row['data_timestamps']['provider_available'])
            p=model.predict(features,c)
            if p.raw_probability is None:raise ValueError()
            row['canonical_event_id']=game['event_id']
            attach_prediction(row,p,at);report['research_predictions']+=1
            row['research_market_context']=asdict(c)
        except (KeyError,ValueError,TypeError,OSError):
            row['pass_reason']=list(dict.fromkeys(row['pass_reason']+['RESEARCH_FEATURES_OR_CONTEXT_UNVERIFIED']))
    return report
