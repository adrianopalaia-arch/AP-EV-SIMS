"""Explicit injury/availability scenarios. No inferred or invented scenario weights."""
from dataclasses import replace
import math

def predict_scenarios(model,scenarios,market_context):
    if not scenarios or any(not math.isfinite(weight) or weight<0 for weight,features in scenarios) or abs(sum(w for w,f in scenarios)-1)>1e-9:
        raise ValueError('INVALID_SCENARIO_WEIGHTS')
    predictions=[(weight,model.predict(features,market_context)) for weight,features in scenarios if weight>0]
    first=predictions[0][1]
    if any(r.raw_probability is None for w,r in predictions):
        return replace(first,raw_probability=None,calibrated_probability=None,uncertainty_lower_bound=None,
            fair_decimal_odds=None,fair_american_odds=None,reasons=('SCENARIO_INPUTS_UNVERIFIED',))
    raw=sum(w*r.raw_probability for w,r in predictions)
    explanation=dict(first.explanation); explanation['scenarios']=[dict(weight=w,prediction=r.to_dict()) for w,r in predictions]
    # Scenario mixtures require their own OOS calibration before decision use.
    return replace(first,raw_probability=raw,calibrated_probability=None,uncertainty_lower_bound=None,
        fair_decimal_odds=None,fair_american_odds=None,explanation=explanation,reasons=('SCENARIO_MIXTURE_NOT_CALIBRATED',))
