"""Fitted CFB score forecasts, with empirical discrete key-number mass.

This is a transparent research baseline, not an empirically approved betting model.
No training rows, team-specific coefficients, winners or key-number boosts are baked in.
"""
from collections import Counter, defaultdict
from dataclasses import asdict
import math
import random
import hashlib
from pathlib import Path
from .base import PredictionResult
from .numerics import Ridge, quantile, clip
from ..integrity import utc, digest
from ..historical import validate_dataset
from ..odds import probability_to_american

# Canonical matchup engineering is explicit: *_diff = home minus away;
# defensive EPA/success are conceded values, so lower is stronger.
CFB_FEATURE_CATALOG = tuple('''offensive_epa_diff defensive_epa_diff passing_epa_diff rushing_epa_diff
success_rate_diff passing_success_rate_diff rushing_success_rate_diff explosiveness_diff
explosive_generated_diff explosive_allowed_diff early_down_efficiency_diff standard_down_efficiency_diff
passing_down_efficiency_diff line_yards_diff stuff_rate_diff sack_rate_diff pressure_rate_diff
havoc_rate_diff tackles_for_loss_diff ol_performance_diff dl_performance_diff qb_epa_diff
qb_accuracy_diff qb_pressure_performance_diff turnover_worthy_proxy_diff sack_avoidance_diff
explosive_pass_rate_diff qb_starter_diff backup_uncertainty pace_sum plays_sum neutral_pace_sum
projected_possessions scoring_opportunities_sum points_per_opportunity_sum red_zone_td_rate_sum
third_down_efficiency_diff fourth_down_efficiency_diff turnover_regression_diff home_field rest_diff
travel_diff altitude wind temperature precipitation injury_depth_diff coaching_change_diff rivalry
neutral_site prior_workload_diff opening_spread current_spread opening_total current_total juice
line_movement consensus_line dk_line fanduel_line no_vig_market_probability ppa_diff success_rate_sum
offensive_epa_sum defensive_epa_sum passing_epa_sum rushing_epa_sum'''.split())

SPREAD_FEATURES=('offensive_epa_diff','defensive_epa_diff','success_rate_diff','line_yards_diff',
                 'pressure_rate_diff','qb_epa_diff','home_field','rest_diff','travel_diff')
TOTAL_FEATURES=('offensive_epa_sum','defensive_epa_sum','success_rate_sum','pace_sum',
                'projected_possessions','points_per_opportunity_sum','wind','injury_depth_diff')

class DiscreteTilt:
    def __init__(self,values, *, total=False,prior_strength=1):
        if not values or any(not isinstance(x,int) for x in values): raise ValueError('integer score target required')
        self.total=total
        low=0 if total else min(-100,min(values)-30)
        high=max(200 if total else 100,max(values)+60)
        self.support=list(range(low,high+1)); counts=Counter(values)
        self.base=[(counts[k]+prior_strength/len(self.support))/(len(values)+prior_strength) for k in self.support]
    def pmf(self,mean):
        mean=min(self.support[-1]-.01,max(self.support[0]+.01,mean))
        def weights(theta):
            logs=[math.log(p)+theta*k for p,k in zip(self.base,self.support)]; largest=max(logs)
            values=[math.exp(v-largest) for v in logs]; total=sum(values)
            return [v/total for v in values]
        lo,hi=-10.,10.
        for _ in range(60):
            theta=(lo+hi)/2; p=weights(theta); moment=sum(k*v for k,v in zip(self.support,p))
            if moment<mean: lo=theta
            else: hi=theta
        return dict(zip(self.support,weights((lo+hi)/2)))
    def state(self): return dict(total=self.total,support=self.support,base=self.base)
    @classmethod
    def from_state(cls,state):
        obj=cls.__new__(cls); obj.total=state['total']; obj.support=state['support']; obj.base=state['base']; return obj

def market_mass(pmf,market):
    def value(k):
        if market.market_type=='spread': return (k if market.selection=='home' else -k)+market.line
        if market.market_type=='total': return k-market.line if market.selection=='over' else market.line-k
        return k if market.selection=='home' else -k
    win=sum(p for k,p in pmf.items() if value(k)>0)
    push=sum(p for k,p in pmf.items() if value(k)==0)
    loss=max(0,1-win-push)
    return win,push,loss

class CFBScoreModel:
    market_type='spread'
    default_features=SPREAD_FEATURES
    def __init__(self, *, feature_keys=None,minimum_train=80,ridge_penalty=10,bootstrap_samples=32,seed=1701):
        self.feature_keys=tuple(feature_keys or self.default_features)
        if not self.feature_keys or any(k not in CFB_FEATURE_CATALOG for k in self.feature_keys): raise ValueError('UNSUPPORTED_FEATURE')
        if minimum_train<20 or bootstrap_samples<10: raise ValueError('INSUFFICIENT_MODEL_POLICY')
        self.minimum_train,self.ridge_penalty,self.bootstrap_samples,self.seed=minimum_train,ridge_penalty,bootstrap_samples,seed
        self.spec=dict(algorithm='ridge-empirical-discrete-tilt-v1',market_type=self.market_type,feature_keys=self.feature_keys,
            minimum_train=minimum_train,ridge_penalty=ridge_penalty,bootstrap_samples=bootstrap_samples,seed=seed)
        self.spec['implementation_fingerprint']=digest({name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('cfb.py','numerics.py','base.py')})
        self.model_version='cfb-'+self.market_type+'-v1-'+digest(self.spec)[:12]
        self.training_cutoff=None; self.calibrator=None

    def fit(self,rows, *, training_cutoff):
        rows=validate_dataset(rows)
        if len(rows)<self.minimum_train: raise ValueError('INSUFFICIENT_TRAINING_SAMPLE')
        events=set()
        for r in rows:
            if r.context.sport!='CFB' or r.context.market_type!=self.market_type: raise ValueError('MODEL_MARKET_MISMATCH')
            if r.context.event_id in events: raise ValueError('DUPLICATE_TRAINING_EVENT')
            events.add(r.context.event_id)
            if utc(r.result_available_at)>utc(training_cutoff) or utc(r.context.event_timestamp)>=utc(training_cutoff): raise ValueError('TRAINING_LOOKAHEAD_RISK')
            r.features.validate(r.context.prediction_timestamp,self.feature_keys)
        self.training_cutoff=utc(training_cutoff).isoformat()
        self.training_fingerprint=digest([asdict(r) | {'closing_context':None} for r in rows])
        x=[[r.features.values[k].value for k in self.feature_keys] for r in rows]
        self.training_ranges={k:[min(row[j] for row in x),max(row[j] for row in x)] for j,k in enumerate(self.feature_keys)}
        y=[r.total if self.market_type=='total' else r.margin for r in rows]
        self.regressor=Ridge(self.ridge_penalty).fit(x,y)
        self.distribution=DiscreteTilt(y,total=self.market_type=='total')
        blocks=defaultdict(list)
        for i,r in enumerate(rows):
            d=utc(r.context.event_timestamp); blocks[(d.isocalendar().year,d.isocalendar().week)].append(i)
        self.training_blocks=len(blocks)
        block_values=list(blocks.values()); rng=random.Random(self.seed); self.bootstrap=[]
        for _ in range(self.bootstrap_samples):
            indices=[i for block in rng.choices(block_values,k=len(block_values)) for i in block]
            regression=Ridge(self.ridge_penalty).fit([x[i] for i in indices],[y[i] for i in indices])
            distribution=DiscreteTilt([y[i] for i in indices],total=self.market_type=='total')
            self.bootstrap.append((regression,distribution))
        self.training_n=len(rows)
        self.artifact_id=digest(self.fitted_state())
        self.calibrator=None
        return self

    def fitted_state(self):
        return dict(spec=self.spec,training_cutoff=self.training_cutoff,training_fingerprint=self.training_fingerprint,
            training_n=self.training_n,training_blocks=self.training_blocks,training_ranges=self.training_ranges,
            regression=self.regressor.state(),distribution=self.distribution.state(),
            bootstrap=[dict(regression=r.state(),distribution=d.state()) for r,d in self.bootstrap])

    def attach_calibration(self,calibrator):
        if self.training_cutoff is None or calibrator.model_version!=self.model_version or calibrator.model_artifact_id!=self.artifact_id:
            raise ValueError('CALIBRATION_MODEL_VERSION_MISMATCH')
        self.calibrator=calibrator

    def predict(self,features,market_context):
        c=market_context
        base=dict(model_version=self.model_version,training_cutoff=self.training_cutoff,
            feature_snapshot_timestamp=features.timestamp,data_fingerprint=features.fingerprint,market_type=c.market_type,
            calibration_version=getattr(self.calibrator,'version',None),model_artifact_id=getattr(self,'artifact_id',None))
        try:
            if self.training_cutoff is None: raise ValueError('MODEL_NOT_TRAINED')
            c.validate(); features.validate(c.prediction_timestamp,self.feature_keys)
            if c.sport!='CFB' or c.market_type!=self.market_type or features.event_id!=c.event_id or features.sport!='CFB': raise ValueError('MODEL_MARKET_MISMATCH')
            if not utc(self.training_cutoff)<utc(features.timestamp): raise ValueError('LOOKAHEAD_RISK')
            if c.selection not in (('over','under') if self.market_type=='total' else ('home','away')): raise ValueError('INVALID_SELECTION')
        except ValueError as e:
            return PredictionResult(None,None,None,None,None,**base,reasons=(str(e),))
        x=[features.values[k].value for k in self.feature_keys]
        mean=self.regressor.predict(x); pmf=self.distribution.pmf(mean)
        cumulative=0; median=self.distribution.support[-1]
        for score,mass in pmf.items():
            cumulative+=mass
            if cumulative>=.5: median=score; break
        win,push,loss=market_mass(pmf,c); raw=clip(win/(1-push))
        samples=[]
        for reg,dist in self.bootstrap:
            bw,bp,_=market_mass(dist.pmf(reg.predict(x)),c); samples.append(clip(bw/(1-bp)))
        explanation=dict(features_used=self.regressor.contributions(self.feature_keys,x),feature_sources={k:asdict(features.values[k]) for k in self.feature_keys},
            expected_margin=mean if self.market_type!='total' else None,expected_total=mean if self.market_type=='total' else None,
            model_fair_spread=(-median if c.selection=='home' else median) if self.market_type!='total' else None,
            mean_based_projected_spread=(-mean if c.selection=='home' else mean) if self.market_type!='total' else None,
            model_fair_total=median if self.market_type=='total' else None,market_line=c.line,
            fair_line_definition='raw predictive median; discrete scoring prevents an exact continuous 50% cover line',
            fair_line_difference=(c.line+median if c.selection=='home' else c.line-median) if self.market_type=='spread' else None,
            raw_win_probability=win,push_probability=push,raw_loss_probability=loss,
            probability_basis='conditional_on_non_push',training_n=self.training_n,training_week_blocks=self.training_blocks,
            bootstrap_raw_05=quantile(samples,.05),bootstrap_raw_95=quantile(samples,.95),
            key_number_mass={str(k):pmf.get(k,0)+pmf.get(-k,0) for k in (3,7,10,14)} if self.market_type!='total' else {},
            key_number_distance={str(k):abs(abs(c.line)-k) for k in (3,7,10,14)} if self.market_type=='spread' else {})
        reasons=[]; calibrated=None; lower=None
        if any(v<self.training_ranges[k][0] or v>self.training_ranges[k][1] for k,v in zip(self.feature_keys,x)):
            reasons.append('OUT_OF_DISTRIBUTION')
        if self.calibrator is None: reasons.append('MODEL_NOT_CALIBRATED')
        elif utc(self.calibrator.selection_end)>=utc(features.timestamp): reasons.append('CALIBRATION_LOOKAHEAD_RISK')
        else:
            calibrated=self.calibrator.transform(raw)
            lower=self.calibrator.lower_bound(raw,samples)
            explanation['uncertainty_components']=self.calibrator.uncertainty_components(raw,samples)
        if self.training_blocks<8: reasons.append('INSUFFICIENT_INDEPENDENT_TRAINING_BLOCKS')
        fair=1/calibrated if calibrated is not None else None
        return PredictionResult(raw,calibrated,lower,fair,probability_to_american(calibrated) if calibrated is not None else None,
            **base,explanation=explanation,reasons=tuple(reasons))

class CFBSpreadModel(CFBScoreModel): pass

class CFBTotalModel(CFBScoreModel):
    market_type='total'
    default_features=TOTAL_FEATURES

class CFBWinModel(CFBScoreModel):
    market_type='win'
