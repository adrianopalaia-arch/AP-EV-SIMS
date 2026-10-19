"""Fixed-policy, rolling-origin NFL score-margin ridge; no sportsbook inputs.

Historical revisions are reconstructed, not authenticated historical snapshots.
Raw Gaussian margins are research distributions, not calibrated betting edges.
"""
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from pathlib import Path
import json, math
import numpy as np
from .nfl_schedule import kickoff, team
from .integrity import digest, utc
from .research_store import ResearchStore
from .publication import atomic_json

VERSION='nfl-team-strength-ridge-v1'
POLICY=dict(alpha=20.,history_days=1096,half_life_days=365.,result_embargo_hours=48,
            evaluation_first_season=2019,warmup_first_season=2017,minimum_training_games=400,
            elo_k=20.,elo_home_points=55.,elo_points_per_margin=25.,season_retention=2/3)

def outcomes(rows,at):
    out=[];seen=set()
    for r in rows:
        if r['game_type']!='REG' or not r['home_score'] or not r['away_score'] or not r['gametime']:continue
        k=kickoff(r)
        if k+timedelta(hours=48)>=utc(at):continue
        if int(r['season'])<2014:continue
        if r['game_id'] in seen:raise ValueError('DUPLICATE_GAME_OUTCOME')
        seen.add(r['game_id'])
        hs,aws=float(r['home_score']),float(r['away_score'])
        if not all(math.isfinite(v) and v>=0 and v.is_integer() for v in (hs,aws)):raise ValueError('INVALID_FINAL_SCORE')
        out.append(dict(event_id=r['game_id'],kickoff=k.isoformat(),season=int(r['season']),week=int(r['week']),
            home_code=team(r['home_team']),away_code=team(r['away_team']),neutral_site=r['location']=='Neutral',margin=hs-aws))
    out=sorted(out,key=lambda r:(r['kickoff'],r['event_id']));last={}
    for g in out:
        rest=[min(14.,(utc(g['kickoff'])-last[t]).total_seconds()/86400) if t in last else 7. for t in (g['home_code'],g['away_code'])]
        g['prior_rest_difference']=(rest[0]-rest[1])/7.
        for s in ('home_code','away_code'):last[g[s]]=utc(g['kickoff'])
    return out

def prior_games(rows,at):
    t=utc(at)
    return [r for r in rows if t-timedelta(days=POLICY['history_days'])<=utc(r['kickoff'])
            and utc(r['kickoff'])+timedelta(hours=48)<t]

def rest_feature(g,history):
    dates={}
    for r in history:
        if utc(r['kickoff'])+timedelta(hours=48)>=utc(g['kickoff']):continue
        for side in ('home_code','away_code'):dates[r[side]]=max(dates.get(r[side],utc(r['kickoff'])),utc(r['kickoff']))
    rest=[min(14.,(utc(g['kickoff'])-dates[t]).total_seconds()/86400) if t in dates else 7. for t in (g['home_code'],g['away_code'])]
    return (rest[0]-rest[1])/7.

def vector(g,teams,history):
    x=np.zeros(len(teams)+2);x[teams.index(g['home_code'])]=1;x[teams.index(g['away_code'])]=-1
    x[-2]=0 if g['neutral_site'] else 1
    x[-1]=g['prior_rest_difference'] if 'prior_rest_difference' in g else rest_feature(g,history)
    return x

def fit(history,at):
    train=prior_games(history,at)
    if len(train)<POLICY['minimum_training_games']:raise ValueError('INSUFFICIENT_GAME_HISTORY')
    teams=sorted({g[s] for g in train for s in ('home_code','away_code')})
    # Rest dates derive from prior outcomes only; no final QB, weather or odds fields enter X.
    x=np.array([vector(g,teams,train[:i]) for i,g in enumerate(train)])
    y=np.array([g['margin'] for g in train]);age=np.array([(utc(at)-utc(g['kickoff'])).total_seconds()/86400 for g in train])
    w=2**(-age/POLICY['half_life_days']);penalty=np.eye(x.shape[1])*POLICY['alpha'];penalty[-2,-2]=1.
    coef=np.linalg.solve(x.T@(x*w[:,None])+penalty,x.T@(y*w))
    return dict(teams=teams,coefficients=coef.tolist(),training_n=len(train),training_ids=[g['event_id'] for g in train],
        data_cutoff=max(g['kickoff'] for g in train),training_fingerprint=digest(train),
        home_baseline=float(np.mean([g['margin'] for g in train if not g['neutral_site']])),
        training_residual_sd=float(np.std(y-x@coef,ddof=1)))

def mean(model,g,history):
    if any(g[s] not in model['teams'] for s in ('home_code','away_code')):raise ValueError('UNKNOWN_TEAM_HISTORY')
    return float(vector(g,model['teams'],history)@np.asarray(model['coefficients']))

def cdf(x,mu,sd):
    if not math.isfinite(sd) or sd<=0:raise ValueError('INVALID_MARGIN_UNCERTAINTY')
    return (1+math.erf((x-mu)/(sd*math.sqrt(2))))/2

def margin_mass(mu,sd,line=0.,home=True):
    # Distribution is on integer scores. Exact integers have an explicit push.
    threshold=-line if home else line
    if float(threshold).is_integer():
        below=cdf(threshold-.5,mu,sd);push=cdf(threshold+.5,mu,sd)-below
    else:below=cdf(math.floor(threshold)+.5,mu,sd);push=0.
    return dict(p_win=1-below-push if home else below,p_push=push,p_loss=below if home else 1-below-push)

def game_probs(mu,sd):
    mass=margin_mass(mu,sd)
    return dict(p_home_win=mass['p_win']/(1-mass['p_push']),p_away_win=mass['p_loss']/(1-mass['p_push']),
        p_tie=mass['p_push'],p_home_win_unconditional=mass['p_win'],p_away_win_unconditional=mass['p_loss'],
        probability_basis='conditional_on_non_tie; unconditional win/tie/loss retained separately')

def scores(records,name):
    if not records:return dict(n=0)
    errors=[r['margin']-r[name]['mean'] for r in records];binary=[r for r in records if r['margin']!=0]
    ps=[min(1-1e-12,max(1e-12,r[name]['p_home_win'])) for r in binary];ys=[int(r['margin']>0) for r in binary]
    return dict(n=len(records),non_tie_n=len(binary),mae=float(np.mean(np.abs(errors))),rmse=float(np.sqrt(np.mean(np.square(errors)))),
        brier=float(np.mean([(p-y)**2 for p,y in zip(ps,ys)])),log_loss=float(np.mean([-y*math.log(p)-(1-y)*math.log(1-p) for p,y in zip(ps,ys)])),
        accuracy=float(np.mean([(p>=.5)==bool(y) for p,y in zip(ps,ys)])))

def train(root,rows,manifest,at):
    history=outcomes(rows,at);folds=defaultdict(list)
    for g in history:folds[(g['season'],g['week'])].append(g)
    residuals={k:[] for k in ('ridge','home_field','elo')};ratings=defaultdict(lambda:1500.);elo_done=set();elo_season=None;records=[]
    for (season,week),games in sorted(folds.items()):
        fold_at=min(g['kickoff'] for g in games)
        # Update Elo only with outcomes available before this fold. Same-week games never leak.
        available=[r for r in history if utc(r['kickoff'])+timedelta(hours=48)<utc(fold_at) and r['event_id'] not in elo_done]
        for r in available:
            if elo_season is not None and r['season']!=elo_season:
                ratings=defaultdict(lambda:1500.,{k:1500+(v-1500)*POLICY['season_retention'] for k,v in ratings.items()})
            elo_season=r['season'];h,a=r['home_code'],r['away_code'];d=ratings[h]-ratings[a]+(0 if r['neutral_site'] else 55)
            p=1/(1+10**(-d/400));y=.5 if r['margin']==0 else float(r['margin']>0);delta=20*(y-p)
            ratings[h]+=delta;ratings[a]-=delta;elo_done.add(r['event_id'])
        if season<2017:continue
        model=fit(history,fold_at);prior=prior_games(history,fold_at);fold_records=[]
        for g in games:
            predictions={'ridge':mean(model,g,prior),'home_field':0. if g['neutral_site'] else model['home_baseline'],
                'elo':(ratings[g['home_code']]-ratings[g['away_code']]+(0 if g['neutral_site'] else 55))/25.}
            row=dict(event_id=g['event_id'],kickoff=g['kickoff'],season=season,week=week,margin=g['margin'],
                training_n=model['training_n'],training_cutoff=model['data_cutoff'],fold_at=fold_at)
            for k,m in predictions.items():
                sd=float(np.std(residuals[k][-1500:],ddof=1)) if len(residuals[k])>=100 else model['training_residual_sd']
                row[k]=dict(mean=m,sd=sd,**game_probs(m,sd))
            fold_records.append(row)
        for row in fold_records:
            for k in residuals:residuals[k].append(row['margin']-row[k]['mean'])
        if season>=2019:records.extend(fold_records)
    model=fit(history,at);sd=float(np.std(residuals['ridge'][-1500:],ddof=1))
    artifact=dict(version=VERSION,policy=POLICY,model=model,residual_sd=sd,outcome_games=len(history),
        generated_at=at,latest_source_capture=manifest['captured_at'],source_manifest=manifest['manifest_id'],source_hash=manifest['hash'])
    h=digest(artifact);data=Path(root)/'data';ResearchStore._immutable(data/'models'/('nfl-game-'+h+'.json'),json.dumps(artifact,sort_keys=True).encode())
    raw='\n'.join(json.dumps(r,sort_keys=True) for r in records)+'\n';fp=digest(records)
    folder=data/'evaluations/nfl-game';folder.mkdir(exist_ok=True)
    ResearchStore._immutable(folder/(fp+'.jsonl'),raw.encode())
    metrics={k:scores(records,k) for k in residuals}
    report=dict(model_version=VERSION,artifact_hash=h,generated_at=at,training_n=model['training_n'],available_outcome_games=len(history),
        training_cutoff=model['data_cutoff'],seasons=sorted({g['season'] for g in history}),evaluation=metrics,
        evaluation_by_season={str(y):{k:scores([r for r in records if r['season']==y],k) for k in residuals} for y in sorted({r['season'] for r in records})},
        evaluation_fingerprint=fp,evaluation_path='evaluations/nfl-game/'+fp+'.jsonl',source_manifest=manifest,
        historical_provenance='RECONSTRUCTED_HISTORY_UNVERIFIED_AS_OF',policy=POLICY,calibrated_probability=None,p_low=None,
        status='RESEARCH_ONLY',betting_validated=False,features=['regular-season opponent-adjusted ridge team strengths','neutral-aware home field','prior-game rest differential'],
        excluded_features=['QB availability','injuries','weather','travel distance','sportsbook lines'],
        limitations=['Current source revisions are not historical publication proof','Gaussian integer margin misses football key-number structure',
                    'No QB or injury adjustment; roster news retained separately','No prospective or price-relative validation'],
        beats_both_baselines=all(metrics['ridge'][k]<metrics[b][k] for b in ('home_field','elo') for k in ('mae','rmse','brier','log_loss')))
    atomic_json(Path(root)/'outputs/nfl_game_model_status.json',report)
    return artifact,h,history,report

def freeze(root,game,artifact,artifact_hash,history,at,availability=None):
    if not game['identity_verified']:raise ValueError('BLOCKED_IDENTITY')
    if not utc(artifact['latest_source_capture'])<=utc(artifact['generated_at'])<=utc(at)<utc(game['kickoff']):raise ValueError('PREGAME_FREEZE_REQUIRED')
    if utc(game['schedule_available_at'])>utc(at):raise ValueError('SCHEDULE_SOURCE_LOOKAHEAD')
    mu=mean(artifact['model'],game,prior_games(history,at));sd=artifact['residual_sd']
    body=dict(event_id=game['event_id'],home_team=game['home_team'],away_team=game['away_team'],event_start=game['kickoff'],
        generated_at=at,model_version=VERSION,artifact_hash=artifact_hash,model_data_cutoff=artifact['model']['data_cutoff'],
        forecast_status='FORECASTED',projected_home_margin=mu,margin_sd=sd,predictive_interval_10_90=[mu-1.281551566*sd,mu+1.281551566*sd],
        **game_probs(mu,sd),calibrated_probability=None,p_low=None,status='RESEARCH_ONLY',decision='PASS',recommendations_enabled=False,
        source_manifest=artifact['source_manifest'],source_hash=artifact['source_hash'],schedule_fingerprint=digest(game),
        pass_reasons=['MODEL_NOT_CALIBRATED','PROSPECTIVE_VALIDATION_PENDING','QB_AND_INJURY_ADJUSTMENTS_UNAVAILABLE'])
    from .nfl_forecast_news import game_context,VERSION as NEWS_VERSION
    context=game_context(game,availability,at)
    body.update(availability_context=context,forecast_policy_version=NEWS_VERSION,
        scoring_recommendation_eligible=False,revision_kind='BASELINE_WITH_AVAILABILITY_ASSUMPTIONS',
        pass_reasons=sorted(set(body['pass_reasons']+context['reasons'])))
    folder=Path(root)/'data/predictions/nfl-games';folder.mkdir(exist_ok=True)
    previous=[]
    for path in folder.glob('*.json'):
        old=json.loads(path.read_text())
        if digest({k:v for k,v in old.items() if k!='forecast_hash'})!=old['forecast_hash']:raise ValueError('FROZEN_FORECAST_HASH_MISMATCH')
        if old['event_id']==game['event_id'] and utc(old['generated_at'])<=utc(at):previous.append(old)
    if previous:
        parent=max(previous,key=lambda f:(utc(f['generated_at']),f['forecast_hash']))
        body.update(parent_forecast_hash=parent['forecast_hash'],revision_reasons=context['reasons'])
    body['forecast_hash']=digest(body)
    ResearchStore._immutable(folder/(body['forecast_hash']+'.json'),json.dumps(body,sort_keys=True).encode())
    return body
