"""Ensemble diagnostics on an earlier selection set; no agreement-voting signal."""
import math
from .calibration import brier_score,log_loss

def ensemble_diagnostics(base,additional,outcomes, *, baseline_clv,additional_clv,minimum_n=300):
    n=len(base)
    if n<minimum_n or len(additional)!=n or len(outcomes)!=n: raise ValueError('INSUFFICIENT_ENSEMBLE_EVIDENCE')
    brier_score(base,outcomes); brier_score(additional,outcomes)
    a=[p-y for p,y in zip(base,outcomes)]; b=[p-y for p,y in zip(additional,outcomes)]
    mean=lambda values:sum(values)/len(values)
    av,bv=mean(a),mean(b); numerator=sum((x-av)*(y-bv) for x,y in zip(a,b))
    denominator=math.sqrt(sum((x-av)**2 for x in a)*sum((y-bv)**2 for y in b))
    correlation=numerator/denominator if denominator else 1.0
    baseline=dict(brier=brier_score(base,outcomes),logloss=log_loss(base,outcomes))
    candidates=[]
    for weight in (.1,.2,.3,.4,.5):
        p=[(1-weight)*x+weight*y for x,y in zip(base,additional)]
        candidates.append(dict(weight=weight,brier=brier_score(p,outcomes),logloss=log_loss(p,outcomes)))
    clv=None
    if baseline_clv is not None and additional_clv is not None and len(baseline_clv)==n and len(additional_clv)==n:
        if all(math.isfinite(v) for v in baseline_clv+additional_clv): clv=mean(additional_clv)-mean(baseline_clv)
    eligible=[r for r in candidates if r['brier']<baseline['brier'] and r['logloss']<baseline['logloss'] and correlation<.9 and clv is not None and clv>0]
    winner=min(eligible,key=lambda r:r['logloss']) if eligible else dict(weight=0,**baseline)
    return dict(weight=winner['weight'],incremental_brier=baseline['brier']-winner['brier'],
        incremental_logloss=baseline['logloss']-winner['logloss'],prediction_error_correlation=correlation,incremental_clv=clv,
        reasons=[] if eligible else ['NO_INDEPENDENT_INCREMENTAL_VALUE'],deployment_approved=False)
