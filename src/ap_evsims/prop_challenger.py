"""Causal, opportunity-aware ridge challenger; no sportsbook inputs to fitting.

Two-day embargo on outcomes and residuals. All feature vectors are constructed
before their own outcomes are admitted. Reconstructed evaluation is not an
untouched analyst holdout or proof of historical source availability.
"""
import argparse
from collections import defaultdict, deque, Counter
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json, math
from pathlib import Path
import numpy as np
from .integrity import digest, utc
from .prop_research import normalize, MARKETS, PlayerOutcome, summarize
from .publication import atomic_json
from .research_store import ResearchStore

VERSION='causal-opportunity-ridge-v2'
POLICY=dict(version=VERSION, history=20, minimum_player_history=5, embargo_days=2,
    ridge=200., minimum_examples=200, residual_window=1000, minimum_residuals=80,
    tail_mixture=.01, evaluation_first_season=2025, bootstrap_seed=7341,
    model_selection='One fixed challenger specification for all markets; no parameter search or automatic promotion',
    split='Sequential expanding training; earlier OOF residuals only; 2025+ chronological diagnostic evaluation',
    holdout_status='Previously inspected seasons; NOT a pristine analyst holdout. Future frozen forecasts are separate.',
    feature_names=['last_outcome','mean_3','mean_5','mean_10','mean_20','opportunity_3','opportunity_10',
                   'opportunity_20','production_per_opportunity_20_times_opportunity_3','history_fraction','team_change'])


def features(history, day):
    if len(history)<POLICY['minimum_player_history']:raise ValueError('INSUFFICIENT_PRIOR_PLAYER_HISTORY')
    cutoff=date.fromisoformat(day)-timedelta(days=POLICY['embargo_days'])
    if any(date.fromisoformat(r.played_on)>cutoff for r in history):raise ValueError('TARGET_OR_FUTURE_PLAYER_LEAKAGE')
    y=np.array([r.outcome for r in history],float);o=np.array([r.opportunity for r in history],float)
    rate=float(y.sum()/o.sum()) if o.sum()>0 else 0.
    return np.array([y[-1],*[y[-n:].mean() for n in (3,5,10,20)],o[-3:].mean(),o[-10:].mean(),o.mean(),
                     rate*o[-3:].mean(),len(history)/20,float(any(r.team_id!=history[-1].team_id for r in history[-10:]))])


class Ridge:
    def __init__(self):
        n=len(POLICY['feature_names']);self.n=0;self.sx=np.zeros(n);self.sy=np.zeros(2)
        self.xx=np.zeros((n,n));self.xy=np.zeros((n,2));self.coefficients=None;self.intercept=None
    def update(self,x,outcome,opportunity):
        if not np.isfinite(x).all() or not math.isfinite(outcome) or not math.isfinite(opportunity):raise ValueError('NONFINITE_TRAINING_EXAMPLE')
        y=np.array([outcome,opportunity]);self.n+=1;self.sx+=x;self.sy+=y;self.xx+=np.outer(x,x);self.xy+=np.outer(x,y)
    def fit(self):
        if self.n<POLICY['minimum_examples']:return
        mean=self.sx/self.n;ym=self.sy/self.n;cov=self.xx-np.outer(self.sx,self.sx)/self.n
        scale=np.sqrt(np.maximum(np.diag(cov)/self.n,1e-8));z=cov/np.outer(scale,scale)
        rhs=(self.xy-np.outer(self.sx,self.sy)/self.n)/scale[:,None]
        self.coefficients=np.linalg.solve(z+POLICY['ridge']*np.eye(len(scale)),rhs)/scale[:,None]
        self.intercept=ym-mean@self.coefficients
    def predict(self,x):
        if self.coefficients is None:raise ValueError('INSUFFICIENT_PRIOR_TRAINING_EXAMPLES')
        return x@self.coefficients+self.intercept


def residual_scale(mean,market):
    return max(10.,abs(mean)*.5) if 'yards' in market else math.sqrt(max(1.,abs(mean)))


def distribution(mean,residuals,market):
    if len(residuals)<POLICY['minimum_residuals']:return None
    samples=np.rint(mean+residual_scale(mean,market)*np.asarray(residuals)).astype(int)
    nonnegative='yards' not in market
    if nonnegative:samples=np.maximum(0,samples)
    # A predeclared 1% discrete-Laplace tail avoids assigning impossible zero
    # likelihood to unseen counts. It is not fitted to the target outcome.
    center=int(round(mean));scale=max(1.,residual_scale(mean,market));decay=math.exp(-1/scale)
    width=int(math.ceil(-math.log(1e-10)*scale))
    lo=min(int(samples.min()),center-width);hi=max(int(samples.max()),center+width)
    if hi-lo>100000:raise ValueError('UNSTABLE_PREDICTIVE_DISTRIBUTION')
    support=np.arange(lo,hi+1);tail=(1-decay)/(1+decay)*np.power(decay,np.abs(support-center))
    mass=POLICY['tail_mixture']*tail
    np.add.at(mass,samples-lo,(1-POLICY['tail_mixture'])/len(samples))
    if nonnegative and lo<0:
        zero=-lo;mass[zero]+=mass[:zero].sum();mass=mass[zero:];support=support[zero:]
    mass/=mass.sum()
    return support,mass


def distribution_scores(d,actual,line):
    x,p=d;cdf=np.cumsum(p);observed=np.where(x==actual)[0]
    probability=float(p[observed[0]]) if len(observed) else 0.
    below=np.concatenate(([0.],np.cumsum(p)[:-1]));moment=np.concatenate(([0.],np.cumsum(p*x)[:-1]))
    crps=float(np.sum(p*np.abs(x-actual))-np.sum(p*(x*below-moment)))
    over=float(p[x>line].sum());result=float(actual>line)
    quantiles=[int(x[min(len(x)-1,int(np.searchsorted(cdf,q)))]) for q in (.025,.1,.5,.9,.975)]
    return dict(crps=crps,nll=-math.log(max(1e-12,probability)),nll_floored=probability<1e-12,
        diagnostic_line=line,diagnostic_probability=over,brier=(over-result)**2,
        binary_logloss=-math.log(max(1e-12,over if result else 1-over)),
        coverage_80=quantiles[1]<=actual<=quantiles[3],coverage_95=quantiles[0]<=actual<=quantiles[4],
        interval_width_80=quantiles[3]-quantiles[1])


def evaluate(rows,sport,market):
    rows=sorted((r for r in rows if r.market==market),key=lambda r:(r.played_on,r.event_id,r.player_id))
    keys=[(r.event_id,r.player_id) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError('DUPLICATE_PLAYER_GAME')
    histories=defaultdict(lambda:deque(maxlen=POLICY['history']));ridge=Ridge();pending=deque();index=0
    residuals=deque(maxlen=POLICY['residual_window']);baseline_residuals=deque(maxlen=POLICY['residual_window'])
    records=[];errors=Counter();last_day=None;feature_hashes=[]
    for target in rows:
        target.validate()
        if target.sport!=sport:raise ValueError('CROSS_SPORT_MARKET_MISMATCH')
        cutoff=date.fromisoformat(target.played_on)-timedelta(days=POLICY['embargo_days'])
        while index<len(rows) and date.fromisoformat(rows[index].played_on)<=cutoff:
            r=rows[index];histories[r.player_id].append(r);index+=1
        while pending and date.fromisoformat(pending[0]['day'])<=cutoff:
            e=pending.popleft();ridge.update(e['x'],e['outcome'],e['opportunity'])
            if e['prediction'] is not None:
                residuals.append((e['outcome']-e['prediction'])/residual_scale(e['prediction'],market))
                baseline_residuals.append((e['outcome']-e['baseline'])/residual_scale(e['baseline'],market))
        if last_day!=target.played_on:ridge.fit();last_day=target.played_on
        try:x=features(list(histories[target.player_id]),target.played_on)
        except ValueError as e:errors[str(e)]+=1;continue
        base=float(x[3]);projection=opportunity=None
        try:
            projection,opportunity=map(float,ridge.predict(x));opportunity=max(0.,opportunity)
            if 'yards' not in market:projection=max(0.,projection)
        except ValueError as e:errors[str(e)]+=1
        pending.append(dict(day=target.played_on,x=x,outcome=target.outcome,opportunity=target.opportunity,prediction=projection,baseline=base))
        fh=digest(dict(player=target.player_id,event=target.event_id,day=target.played_on,cutoff=cutoff.isoformat(),values=x.tolist(),
            sources=[(r.source_id,r.source_hash,r.event_id) for r in histories[target.player_id]]));feature_hashes.append(fh)
        if projection is None or target.season<POLICY['evaluation_first_season']:continue
        d=distribution(projection,residuals,market);bd=distribution(base,baseline_residuals,market)
        line=math.floor(base)+.5
        score=distribution_scores(d,target.outcome,line) if d is not None else {}
        bscore=distribution_scores(bd,target.outcome,line) if bd is not None else {}
        records.append(dict(event_id=target.event_id,player_id=target.player_id,day=target.played_on,season=target.season,
            outcome=target.outcome,actual_opportunity=target.opportunity,projection=projection,baseline=base,
            projected_opportunity=opportunity,training_n=ridge.n,feature_hash=fh,latest_input_day=histories[target.player_id][-1].played_on,
            crps=score.get('crps'),scores=score,baseline_scores=bscore,model_status='UNVALIDATED'))
    while pending:
        e=pending.popleft();ridge.update(e['x'],e['outcome'],e['opportunity'])
        if e['prediction'] is not None:
            residuals.append((e['outcome']-e['prediction'])/residual_scale(e['prediction'],market))
            baseline_residuals.append((e['outcome']-e['baseline'])/residual_scale(e['baseline'],market))
    while index<len(rows):r=rows[index];histories[r.player_id].append(r);index+=1
    ridge.fit()
    artifact=dict(version=VERSION,sport=sport,market=market,policy=POLICY,training_n=ridge.n,outcome_n=len(rows),
        feature_dataset_fingerprint=digest(feature_hashes),coefficients=ridge.coefficients.tolist() if ridge.coefficients is not None else None,
        intercept=ridge.intercept.tolist() if ridge.intercept is not None else None,
        player_histories={k:[asdict(r) for r in v] for k,v in histories.items()},residuals=list(residuals),baseline_residuals=list(baseline_residuals),
        source_ids=sorted({r.source_id for r in rows}),source_hashes=sorted({r.source_hash for r in rows}),
        latest_source_capture=max((r.captured_at for r in rows),default=None),
        training_cutoff=max((r.played_on for r in rows),default=None),model_status='UNVALIDATED',cash_authority=False)
    return artifact,records,dict(errors)


def metrics(records):
    result=summarize(records)
    paired=[r for r in records if r['scores'] and r['baseline_scores']]
    result['distribution_n']=len(paired)
    for field in ('crps','nll','brier','binary_logloss','coverage_80','coverage_95','interval_width_80'):
        for key,prefix in [('scores',''),('baseline_scores','baseline_')]:
            result[prefix+field]=float(np.mean([r[key][field] for r in paired])) if paired else None
    result['nll_floor_count']=sum(r['scores'].get('nll_floored',False) for r in paired)
    result['probability_score_scope']='Predeclared half-line floor(prior last-10 mean)+0.5, NOT a bookmaker line or market benchmark'
    return result


def run(root,sport):
    root=Path(root);s=ResearchStore(root/'data');at=datetime.now(timezone.utc).isoformat()
    s._immutable(s.root/'evaluations'/('challenger-policy-'+digest(POLICY)+'.json'),json.dumps(POLICY,sort_keys=True,indent=2).encode())
    rows,coverage=normalize(root,sport);table=s.write_table(sport.lower()+'-expanded-player-outcomes',[asdict(r) for r in rows]);markets={}
    for market in MARKETS[sport]:
        artifact,records,errors=evaluate(rows,sport,market);h=digest(artifact)
        s._immutable(s.root/'models'/(sport.lower()+'-'+market+'-'+h+'.json'),json.dumps(artifact,sort_keys=True,indent=2).encode())
        evaluated=s.write_table(sport.lower()+'-'+market+'-challenger-oos',records)
        markets[market]=dict(training_n=artifact['training_n'],outcome_n=artifact['outcome_n'],artifact_hash=h,
            evaluation=metrics(records),evaluation_table=evaluated,rejections=errors,
            by_season={str(y):metrics([r for r in records if r['season']==y]) for y in sorted({r['season'] for r in records})},
            selected_for_betting=False,calibrated_probability=None,p_low=None)
        print(json.dumps(dict(sport=sport,market=market,training_n=artifact['training_n'],evaluation=markets[market]['evaluation'])),flush=True)
    report=dict(sport=sport,generated_at=datetime.now(timezone.utc).isoformat(),training_started_at=at,model_version=VERSION,policy=POLICY,coverage=coverage,normalized_table=table,markets=markets,
        synthetic_performance_sample=0,recommendations_enabled=False,reference_unit=22,
        limitations=['Source revisions captured now are not historically timestamp-authentic.',
        'Appearance-only evaluation; unknown DNP and role transitions remain material.',
        'Evaluation seasons were previously inspected; chronological forecasts are retrospective diagnostics, not untouched prospective validation.',
        'Multiple market comparisons are exploratory; no automatic winner selection or CORE approval.'])
    atomic_json(root/'outputs'/(sport.lower()+'_challenger_status.json'),report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--sport',choices=['NFL','NBA','NHL','MLB','all'],default='all');a=p.parse_args()
    for sport in ['NFL','NBA','NHL','MLB'] if a.sport=='all' else [a.sport]:run(a.root,sport)


if __name__=='__main__':main()
