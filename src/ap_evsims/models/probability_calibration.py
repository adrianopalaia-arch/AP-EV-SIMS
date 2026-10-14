"""Chronological OOS calibration selection; evaluation labels never choose a map.

Candidates: identity audit, monotone Platt, monotone beta, and PAVA isotonic.
Beta form follows Kull et al., PMLR 54 (2017). Uncertainty is a conservative
diagnostic bound with explicit dependence adjustment, not guaranteed coverage.
"""
from dataclasses import dataclass,asdict
from collections import defaultdict
import math
import hashlib
from pathlib import Path
from .numerics import sigmoid,clip,solve,quantile,wilson_lower
from ..integrity import utc,digest
from ..calibration import brier_score,log_loss

@dataclass(frozen=True)
class CalibrationObservation:
    event_id: str
    raw_probability: float
    outcome: int
    model_version: str
    model_artifact_id: str
    training_cutoff: str
    prediction_timestamp: str
    feature_timestamp: str
    result_available_at: str

def check_observations(rows,version,artifact):
    seen=set()
    for r in rows:
        if r.event_id in seen: raise ValueError('DUPLICATE_CALIBRATION_EVENT')
        seen.add(r.event_id)
        if (r.model_version,r.model_artifact_id)!=(version,artifact): raise ValueError('CALIBRATION_MODEL_VERSION_MISMATCH')
        if not utc(r.training_cutoff)<utc(r.feature_timestamp)<=utc(r.prediction_timestamp)<utc(r.result_available_at):
            raise ValueError('CALIBRATION_LOOKAHEAD_RISK')
        if not math.isfinite(r.raw_probability) or not 0<r.raw_probability<1 or r.outcome not in (0,1): raise ValueError('INVALID_CALIBRATION_OBSERVATION')

class CalibrationMap:
    def __init__(self,kind):
        if kind not in ('identity','platt','beta','isotonic'): raise ValueError('unsupported calibrator')
        self.kind=kind; self.parameters=[]; self.blocks=[]
    def _design(self,p):
        p=clip(p)
        return [1,math.log(p/(1-p))] if self.kind=='platt' else [1,math.log(p),-math.log(1-p)]
    def fit(self,probabilities,outcomes):
        if self.kind=='identity': return self
        if self.kind=='isotonic':
            grouped=defaultdict(lambda:[0,0])
            for p,y in zip(probabilities,outcomes): grouped[p][0]+=y; grouped[p][1]+=1
            blocks=[]
            for p,(wins,n) in sorted(grouped.items()):
                blocks.append([p,p,wins,n])
                while len(blocks)>1 and blocks[-2][2]/blocks[-2][3]>blocks[-1][2]/blocks[-1][3]:
                    b=blocks.pop(); a=blocks.pop(); blocks.append([a[0],b[1],a[2]+b[2],a[3]+b[3]])
            self.blocks=blocks; return self
        x=[self._design(p) for p in probabilities]
        beta=[0,1] if self.kind=='platt' else [0,1,1]; prior=list(beta); penalty=.1
        def objective(b):
            return sum(-y*math.log(clip(sigmoid(sum(v*w for v,w in zip(row,b)))))-(1-y)*math.log(1-clip(sigmoid(sum(v*w for v,w in zip(row,b))))) for row,y in zip(x,outcomes))+penalty/2*sum((v-q)**2 for v,q in zip(b,prior))
        for _ in range(80):
            pred=[sigmoid(sum(v*w for v,w in zip(row,beta))) for row in x]; d=len(beta)
            g=[sum(row[j]*(p-y) for row,p,y in zip(x,pred,outcomes))+penalty*(beta[j]-prior[j]) for j in range(d)]
            h=[[sum(row[j]*row[k]*p*(1-p) for row,p in zip(x,pred))+(penalty if j==k else 0) for k in range(d)] for j in range(d)]
            delta=solve(h,g); rate=1; old=objective(beta)
            while rate>1e-6:
                candidate=[v-rate*s for v,s in zip(beta,delta)]
                candidate[1:]=[max(0,v) for v in candidate[1:]]
                if objective(candidate)<=old: break
                rate/=2
            if rate<=1e-6: break
            change=max(abs(a-b) for a,b in zip(beta,candidate)); beta=candidate
            if change<1e-7: break
        self.parameters=beta; return self
    def transform(self,p):
        if self.kind=='identity': return clip(p)
        if self.kind=='isotonic':
            for lo,hi,wins,n in self.blocks:
                if p<=hi: return clip(wins/n)
            return clip(self.blocks[-1][2]/self.blocks[-1][3])
        return clip(sigmoid(sum(v*w for v,w in zip(self._design(p),self.parameters))))
    def state(self): return dict(kind=self.kind,parameters=self.parameters,blocks=self.blocks)
    @classmethod
    def from_state(cls,state):
        obj=cls(state['kind']); obj.parameters=state['parameters']; obj.blocks=state['blocks']; return obj

class CalibratedProbability:
    def __init__(self,*,model_version,model_artifact_id,map_state,selection_end,bins,
                 sample_sizes,selection_scores,dataset_fingerprint,algorithm_fingerprint=None):
        current=digest({name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('probability_calibration.py','numerics.py')})
        if algorithm_fingerprint is not None and algorithm_fingerprint!=current: raise ValueError('CALIBRATION_ALGORITHM_VERSION_MISMATCH')
        self.algorithm_fingerprint=current
        self.model_version,self.model_artifact_id=model_version,model_artifact_id
        self.map=CalibrationMap.from_state(map_state); self.selection_end=selection_end
        self.bins,self.sample_sizes,self.selection_scores,self.dataset_fingerprint=bins,sample_sizes,selection_scores,dataset_fingerprint
        self.version='calibration-v1-'+digest(self.state())[:16]
    def state(self):
        return dict(model_version=self.model_version,model_artifact_id=self.model_artifact_id,map_state=self.map.state(),
            selection_end=self.selection_end,bins=self.bins,sample_sizes=self.sample_sizes,selection_scores=self.selection_scores,
            dataset_fingerprint=self.dataset_fingerprint,algorithm_fingerprint=self.algorithm_fingerprint)
    def transform(self,p): return self.map.transform(p)
    def uncertainty_components(self,raw,bootstrap):
        p=self.transform(raw); model_lower=min(p,quantile([self.transform(v) for v in bootstrap],.05))
        bucket=min(9,int(p*10)); item=self.bins.get(str(bucket))
        if item is None:
            return dict(model_variance_penalty=p-model_lower,calibration_penalty=p,sample_n=0,independent_week_blocks=0,coverage_validated=False)
        # A week is the resampling/dependence unit, not an independent wager.
        effective_n=min(item['n'],item['week_blocks'])
        adjusted_wins=item['observed']*effective_n
        lower=wilson_lower(adjusted_wins,effective_n)
        penalty=max(0,item['predicted']-lower)
        return dict(model_variance_penalty=p-model_lower,calibration_penalty=penalty,
            sample_n=item['n'],independent_week_blocks=effective_n,coverage_validated=False)
    def lower_bound(self,raw,bootstrap):
        p=self.transform(raw); c=self.uncertainty_components(raw,bootstrap)
        return max(0,min(p,p-c['model_variance_penalty']-c['calibration_penalty']))

def select_calibration(fit_rows,selection_rows, *, model_version,model_artifact_id,selection_end,minimum_fit=300,minimum_selection=100):
    if minimum_fit<20 or minimum_selection<20: raise ValueError('INSUFFICIENT_CALIBRATION_POLICY')
    check_observations(fit_rows+selection_rows,model_version,model_artifact_id)
    if len(fit_rows)<minimum_fit or len(selection_rows)<minimum_selection: raise ValueError('MODEL_NOT_CALIBRATED')
    if len({r.outcome for r in fit_rows})<2: raise ValueError('CALIBRATION_SINGLE_CLASS')
    if max(utc(r.result_available_at) for r in fit_rows)>=min(utc(r.prediction_timestamp) for r in selection_rows): raise ValueError('CALIBRATION_LOOKAHEAD_RISK')
    if any(utc(r.result_available_at)>utc(selection_end) for r in selection_rows): raise ValueError('CALIBRATION_LOOKAHEAD_RISK')
    p=[r.raw_probability for r in fit_rows]; y=[r.outcome for r in fit_rows]
    scored={}; maps={}
    for kind in ('identity','platt','beta','isotonic'):
        mapping=CalibrationMap(kind).fit(p,y); v=[mapping.transform(r.raw_probability) for r in selection_rows]
        scored[kind]=dict(brier=brier_score(v,[r.outcome for r in selection_rows]),logloss=log_loss(v,[r.outcome for r in selection_rows]))
        maps[kind]=mapping
    baseline=scored['identity']
    eligible=[kind for kind,s in scored.items() if s['brier']<=baseline['brier']+1e-12 and s['logloss']<=baseline['logloss']+1e-12]
    chosen=min(eligible,key=lambda kind:(scored[kind]['logloss'],scored[kind]['brier'],kind))
    mapping=maps[chosen]; bins={}; grouped=defaultdict(list)
    for r in selection_rows: grouped[min(9,int(mapping.transform(r.raw_probability)*10))].append(r)
    for k,rows in grouped.items():
        weeks={(utc(r.prediction_timestamp).isocalendar().year,utc(r.prediction_timestamp).isocalendar().week) for r in rows}
        bins[str(k)]=dict(n=len(rows),predicted=sum(mapping.transform(r.raw_probability) for r in rows)/len(rows),
            observed=sum(r.outcome for r in rows)/len(rows),week_blocks=len(weeks))
    return CalibratedProbability(model_version=model_version,model_artifact_id=model_artifact_id,map_state=mapping.state(),
        selection_end=utc(selection_end).isoformat(),bins=bins,sample_sizes=dict(fit=len(fit_rows),selection=len(selection_rows)),
        selection_scores=scored,dataset_fingerprint=digest([asdict(r) for r in fit_rows+selection_rows]))
