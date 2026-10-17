"""Reproducible week-block intervals; they do not remove selection/model bias."""
from collections import defaultdict
import math,random
from .integrity import utc
from .models.numerics import quantile,clip

def paired_score_intervals(records, *, replicates=300,seed=709):
    eligible=[r for r in records if r['outcome'] is not None and r['calibrated_probability'] is not None]
    blocks=defaultdict(list)
    for r in eligible:
        d=utc(r['event_timestamp']); blocks[(d.isocalendar().year,d.isocalendar().week)].append(r)
    if len(blocks)<8:
        return dict(week_blocks=len(blocks),brier_improvement_95=None,logloss_improvement_95=None,reason='INSUFFICIENT_INDEPENDENT_EVALUATION_BLOCKS')
    values=list(blocks.values()); rng=random.Random(seed); brier=[]; logs=[]
    for _ in range(replicates):
        sample=[r for block in rng.choices(values,k=len(values)) for r in block]
        brier.append(sum((r['no_vig_probability']-r['outcome'])**2-(r['calibrated_probability']-r['outcome'])**2 for r in sample)/len(sample))
        def loss(p,y): p=clip(p); return -y*math.log(p)-(1-y)*math.log(1-p)
        logs.append(sum(loss(r['no_vig_probability'],r['outcome'])-loss(r['calibrated_probability'],r['outcome']) for r in sample)/len(sample))
    return dict(week_blocks=len(blocks),brier_improvement_95=[quantile(brier,.025),quantile(brier,.975)],
        logloss_improvement_95=[quantile(logs,.025),quantile(logs,.975)],reason=None)
