"""Score-only CFB research. Reconstructed results never prove historical availability.

No odds, plays, injuries, or retrospective ratings enter this model. Policy is fixed
before evaluation; no coefficient or sample threshold grants betting authority.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import timedelta
import math
import numpy as np

from .integrity import digest, utc

VERSION = 'cfb-score-ridge-v1.1'
RECONSTRUCTED = 'RECONSTRUCTED_HISTORY_UNVERIFIED_AS_OF'
POLICY = dict(version=VERSION, ridge=20., home_prior=2.5, home_prior_weight=20.,
              lookback_days=730, embargo_days=7, previous_season_weight=.5,
              minimum_training_games=80, minimum_team_games=3, minimum_residuals=80,
              warmup_season=2024, evaluation_start_season=2025,
              fold='Monday 00:00 UTC; previous games only; seven-day completion embargo',
              distribution='rounded predicted margin plus rounded prior out-of-fold residuals, conditional on nonzero final margin (CFB overtime)',
              unknown_team_policy='PASS; no zero-filled team rating')


@dataclass(frozen=True)
class CompletedGameScoreObservation:
    event_id: str
    home_id: str
    away_id: str
    kickoff: str
    season: int
    home_score: int
    away_score: int
    final_status: str
    neutral: bool
    source_id: str
    source_hash: str
    captured_at: str
    available_at: str
    revision_hashes: tuple[str, ...]
    provenance: str = RECONSTRUCTED

    @property
    def margin(self): return self.home_score-self.away_score

    def validate(self):
        if not self.event_id or not self.home_id or not self.away_id or self.home_id == self.away_id:
            raise ValueError('INVALID_GAME_IDENTITY')
        if self.final_status != 'final' or any(type(v) is not int or v < 0 for v in (self.home_score,self.away_score)):
            raise ValueError('UNVERIFIED_FINAL_SCORE')
        if type(self.neutral) is not bool or type(self.season) is not int:
            raise ValueError('INVALID_GAME_METADATA')
        if not utc(self.kickoff) < utc(self.captured_at) == utc(self.available_at):
            raise ValueError('UNPROVEN_HISTORICAL_AVAILABILITY')
        if any(len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in (self.source_id,self.source_hash,*self.revision_hashes)):
            raise ValueError('MISSING_SOURCE_HASH')
        if self.provenance != RECONSTRUCTED: raise ValueError('UNPROVEN_HISTORICAL_AVAILABILITY')


def unique_games(rows):
    ids=set()
    for r in rows:
        r.validate()
        if r.event_id in ids: raise ValueError('DUPLICATE_SCORE_GAME')
        ids.add(r.event_id)
    return sorted(rows,key=lambda r:(utc(r.kickoff),r.event_id))


def score_observations(sources, at):
    """Sources must be hash-verified CFBD manifests/payloads from verified_sources.

    Newer final-score revisions replace earlier versions, with all content hashes
    retained. Duplicate rows or simultaneous conflicting versions fail closed.
    """
    latest={}; histories=defaultdict(list); conflicts=set(); raw=0
    for m,games in sorted(sources,key=lambda x:(utc(x[0]['available_at']),x[0]['snapshot_id'])):
        if m['provider']!='cfbd' or m['endpoint']!='games' or m['availability_basis']!='recorded_response' or not utc(m['fetched_at'])==utc(m['available_at'])<=utc(at):
            raise ValueError('SOURCE_PROVENANCE_MISMATCH')
        seen=set()
        for g in games:
            raw+=1;key=str(g['id']);old=latest.get(key)
            if key in seen or old and utc(old[1]['available_at'])==utc(m['available_at']) and old[0]!=g:conflicts.add(key)
            seen.add(key);latest[key]=(g,m)
            h=digest(g)
            if h not in histories[key]:histories[key].append(h)
    out=[];excluded=Counter();future=[]
    for key,(g,m) in sorted(latest.items()):
        reason=None
        if key in conflicts:reason='CONFLICTING_OR_DUPLICATE_GAME'
        elif g.get('homeClassification')!='fbs' or g.get('awayClassification')!='fbs':reason='OUTSIDE_FBS_VS_FBS_SCOPE'
        elif any(type(g.get(k)) is not int or g[k]<=0 for k in ('homeId','awayId')) or g['homeId']==g['awayId']:reason='INVALID_GAME_IDENTITY'
        elif g.get('startTimeTBD') is not False:reason='EVENT_START_UNCONFIRMED'
        elif type(g.get('neutralSite')) is not bool:reason='UNKNOWN_VENUE'
        elif g.get('completed') is not True:
            reason='NOT_FINAL'
            if utc(g['startDate'])>utc(at):future.append((g,m))
        elif utc(g['startDate'])>=utc(m['available_at']):reason='IMPOSSIBLE_FINAL_TIMESTAMP'
        elif any(type(g.get(k)) is not int or g[k]<0 for k in ('homePoints','awayPoints')):reason='MISSING_OR_INVALID_FINAL_SCORE'
        if reason:excluded[reason]+=1;continue
        r=CompletedGameScoreObservation(key,str(g['homeId']),str(g['awayId']),utc(g['startDate']).isoformat(),g['season'],
            g['homePoints'],g['awayPoints'],'final',g['neutralSite'],m['snapshot_id'],m['payload_hash'],m['fetched_at'],m['available_at'],tuple(histories[key]))
        r.validate();out.append(r)
    return unique_games(out),future,dict(raw_rows=raw,unique_game_ids=len(latest),completed_scores=len(out),
        seasons=dict(sorted(Counter(r.season for r in out).items())),exclusions=dict(excluded),
        revised_game_ids=sum(len(h)>1 for h in histories.values()),
        earliest_kickoff=min((r.kickoff for r in out),default=None),latest_kickoff=max((r.kickoff for r in out),default=None))


def eligible_training(rows, at, *, prospective=False):
    end=utc(at)-timedelta(days=POLICY['embargo_days']);start=utc(at)-timedelta(days=POLICY['lookback_days'])
    return [r for r in unique_games(rows) if start<=utc(r.kickoff)<end and (not prospective or utc(r.available_at)<=utc(at))]


class ScoreMarginModel:
    """Penalized home advantage + difference of regularized team strengths.

    Older seasons have half weight per season (shrink toward zero); home effect
    has a 2.5 point prior worth 20 games. Neutral venues have zero home effect.
    """
    def fit(self,rows,at,season,*,prospective=False):
        rows=eligible_training(rows,at,prospective=prospective)
        if len(rows)<POLICY['minimum_training_games']:raise ValueError('INSUFFICIENT_SCORE_TRAINING')
        teams=sorted({t for r in rows for t in (r.home_id,r.away_id)});index={t:i+1 for i,t in enumerate(teams)}
        x=np.zeros((len(rows),len(teams)+1));y=np.array([r.margin for r in rows],dtype=float)
        for i,r in enumerate(rows):
            x[i,0]=not r.neutral;x[i,index[r.home_id]]=1;x[i,index[r.away_id]]=-1
        weights=np.array([POLICY['previous_season_weight']**max(0,season-r.season) for r in rows])
        penalty=np.eye(len(teams)+1)*POLICY['ridge'];penalty[0,0]=POLICY['home_prior_weight']
        target=x.T@(weights*y);target[0]+=POLICY['home_prior']*POLICY['home_prior_weight']
        coef=np.linalg.solve(x.T@(weights[:,None]*x)+penalty,target)
        self.counts=Counter(t for r in rows for t in (r.home_id,r.away_id))
        self.state=dict(model_version=VERSION,policy=POLICY,training_cutoff=utc(at).isoformat(),season=season,
            training_n=len(rows),training_ids=[r.event_id for r in rows],training_fingerprint=digest([asdict(r) for r in rows]),
            source_ids=sorted({r.source_id for r in rows}),source_hashes=sorted({r.source_hash for r in rows}),
            latest_source_capture=max(r.captured_at for r in rows),home_advantage=float(coef[0]),
            team_strengths={t:float(coef[index[t]]) for t in teams},team_counts=dict(self.counts),
            baseline_home_advantage=float(sum(r.margin for r in rows if not r.neutral)/max(1,sum(not r.neutral for r in rows))),
            provenance=RECONSTRUCTED,prospective_capture_verified=prospective)
        return self

    def predict(self,home,away,neutral):
        if type(neutral) is not bool or home==away:raise ValueError('INVALID_GAME_METADATA')
        if min(self.counts[home],self.counts[away])<POLICY['minimum_team_games']:raise ValueError('UNKNOWN_OR_SPARSE_TEAM')
        s=self.state
        return s['home_advantage']*(not neutral)+s['team_strengths'][home]-s['team_strengths'][away]


def margin_distribution(mean,residuals):
    if len(residuals)<POLICY['minimum_residuals']:return None
    if not math.isfinite(mean) or any(not math.isfinite(x) for x in residuals):raise ValueError('INVALID_RESIDUAL')
    counts=Counter(int(round(mean+x)) for x in residuals)
    # Modern completed CFB games cannot tie after overtime. This is a support
    # restriction, not a confidence boost. Nonzero integer spread pushes remain.
    counts.pop(0,None)
    if not counts:return None
    return {k:n/sum(counts.values()) for k,n in sorted(counts.items())}


def market_mass(pmf,line=0.,selection='home'):
    if selection not in ('home','away') or not math.isfinite(line):raise ValueError('INVALID_MARGIN_MARKET')
    if not pmf or any(type(k) is not int or not math.isfinite(v) or v<0 for k,v in pmf.items()) or abs(sum(pmf.values())-1)>1e-10:
        raise ValueError('INVALID_MARGIN_DISTRIBUTION')
    win=push=loss=0.
    for margin,p in pmf.items():
        value=(margin if selection=='home' else -margin)+line
        if value>0:win+=p
        elif value<0:loss+=p
        else:push+=p
    return dict(p_win=win,p_push=push,p_loss=loss)


def crps(pmf,observed):
    """CRPS = E|X-y| - 0.5 E|X-X'|, exact for the empirical discrete PMF."""
    total=sum(p*abs(x-observed) for x,p in pmf.items());mass=moment=0.
    for x,p in sorted(pmf.items()):
        total-=p*(x*mass-moment);mass+=p;moment+=p*x
    return total


def monday(value):
    t=utc(value);return (t-timedelta(days=t.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)


def chronological_evaluation(rows):
    rows=unique_games(rows);folds=defaultdict(list)
    for r in rows:
        if r.season>=POLICY['warmup_season']:folds[monday(r.kickoff)].append(r)
    records=[];rejections=Counter();fold_report=[]
    for origin,targets in sorted(folds.items()):
        try:model=ScoreMarginModel().fit(rows,origin.isoformat(),min(r.season for r in targets))
        except ValueError as e:rejections[str(e)]+=len(targets);continue
        # Distribution uses only earlier OOF errors, with the same completion buffer.
        prior=[r for r in records if utc(r['kickoff'])<origin-timedelta(days=POLICY['embargo_days'])]
        residuals=[r['actual_margin']-r['predicted_margin'] for r in prior]
        baseline_residuals=[r['actual_margin']-r['baseline_margin'] for r in prior]
        fold_report.append(dict(origin=origin.isoformat(),training_n=model.state['training_n'],
            training_fingerprint=model.state['training_fingerprint'],target_games=len(targets),residual_n=len(prior)))
        for target in targets:
            if target.event_id in model.state['training_ids']:raise ValueError('TARGET_RESULT_LEAKAGE')
            try:mean=model.predict(target.home_id,target.away_id,target.neutral)
            except ValueError as e:rejections[str(e)]+=1;continue
            base=0. if target.neutral else model.state['baseline_home_advantage']
            pmf=margin_distribution(mean,residuals);bpmf=margin_distribution(base,baseline_residuals)
            mass=market_mass(pmf) if pmf else None;bm=market_mass(bpmf) if bpmf else None
            p=mass['p_win']/(1-mass['p_push']) if mass and mass['p_push']<1 else None
            bp=bm['p_win']/(1-bm['p_push']) if bm and bm['p_push']<1 else None
            records.append(dict(event_id=target.event_id,kickoff=target.kickoff,season=target.season,origin=origin.isoformat(),
                training_n=model.state['training_n'],training_fingerprint=model.state['training_fingerprint'],
                actual_margin=target.margin,predicted_margin=mean,baseline_margin=base,
                raw_home_win_probability=p,baseline_home_win_probability=bp,
                crps=crps(pmf,target.margin) if pmf else None,baseline_crps=crps(bpmf,target.margin) if bpmf else None,
                residual_n=len(prior),provenance=RECONSTRUCTED,source_capture=target.captured_at))
    return records,dict(folds=fold_report,rejections=dict(rejections))


def metrics(records):
    if not records:return dict(n=0,mae=None,rmse=None,baseline_mae=None,baseline_rmse=None)
    result=dict(n=len(records))
    for key,prefix in (('predicted_margin',''),('baseline_margin','baseline_')):
        errors=np.array([r[key]-r['actual_margin'] for r in records])
        result[prefix+'mae']=float(np.mean(abs(errors)));result[prefix+'rmse']=float(np.sqrt(np.mean(errors**2)))
    for field in ('crps','baseline_crps'):
        vals=[r[field] for r in records if r[field] is not None];result[field]=float(np.mean(vals)) if vals else None
        result[field+'_n']=len(vals)
    paired=[r for r in records if r['actual_margin']!=0 and r['raw_home_win_probability'] is not None and r['baseline_home_win_probability'] is not None]
    result['home_win_probability_n']=len(paired)
    for key,prefix in (('raw_home_win_probability',''),('baseline_home_win_probability','baseline_')):
        result[prefix+'brier']=float(np.mean([(r[key]-(r['actual_margin']>0))**2 for r in paired])) if paired else None
        result[prefix+'logloss']=float(np.mean([-math.log(max(1e-12,min(1-1e-12,r[key] if r['actual_margin']>0 else 1-r[key]))) for r in paired])) if paired else None
    blocks=defaultdict(list)
    for r in records:blocks[r['origin']].append(r)
    rng=np.random.default_rng(7341);samples=[];values=list(blocks.values())
    for _ in range(1000):
        sample=[r for i in rng.integers(0,len(values),len(values)) for r in values[i]]
        samples.append(float(np.mean([abs(r['predicted_margin']-r['actual_margin'])-abs(r['baseline_margin']-r['actual_margin']) for r in sample])))
    result['paired_mae_difference_95_week_bootstrap']=list(map(float,np.quantile(samples,[.025,.975])))
    result['week_blocks']=len(blocks)
    return result
