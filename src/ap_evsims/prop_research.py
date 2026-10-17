"""Real outcome-only opportunity models, separate from executable prop markets.

python -m ap_evsims.prop_research --root . --sport all
Player appearance reconstruction is not proof of pregame participation or roles.
"""
import argparse
from collections import Counter,defaultdict,deque
from dataclasses import asdict,dataclass
from datetime import date,datetime,timedelta,timezone
import json,math
from pathlib import Path
import numpy as np
from .providers.public_stats import PublicStatsArchive
from .integrity import digest,utc
from .research_store import ResearchStore
from .cfb_scores import crps

VERSION='opportunity-partial-pool-v1'
POLICY=dict(version=VERSION,player_history=20,opportunity_recent=10,prior_player_games=2,
    minimum_player_games=5,minimum_population_games=200,minimum_oof_residuals=80,
    residual_window=1000,embargo_days=2,evaluation_first_season=2025,
    baseline='same player last 10 observed appearances mean outcome',
    method='project recent opportunity with two population-prior appearances; pool production per opportunity; empirical prior OOF residual distribution',
    participation='conditional on appearance; DNP excluded, not scored as zero; unverified roles block betting')
MARKETS={
 'NFL':{'receptions':('targets','receptions'), 'receiving_yards':('targets','receiving_yards'),
        'rushing_attempts':('carries','carries'),'rushing_yards':('carries','rushing_yards'),'passing_yards':('attempts','passing_yards')},
 'NBA':{'points':('minutes','points'),'rebounds':('minutes','rebounds'),'assists':('minutes','assists'),'threes':('minutes','three_point_field_goals_made')},
 'NHL':{'shots_on_goal':('minutes','shots'),'goalie_saves':('shotsAgainst','saves')},
 'MLB':{'pitcher_strikeouts':('battersFaced','strikeOuts'),'pitcher_outs':('battersFaced','outs'),
        'hits_allowed':('battersFaced','hits'),'hitter_hits':('plateAppearances','hits'),'total_bases':('plateAppearances','totalBases')}}


@dataclass(frozen=True)
class PlayerOutcome:
    sport:str
    market:str
    event_id:str
    player_id:str
    player_name:str
    team_id:str
    opponent_id:str
    played_on:str
    season:int
    opportunity:float
    outcome:int
    source_id:str
    source_hash:str
    captured_at:str
    provenance:str='RECONSTRUCTED_HISTORY_UNVERIFIED_AS_OF'

    def validate(self):
        if self.sport not in MARKETS or self.market not in MARKETS[self.sport]:raise ValueError('CROSS_SPORT_MARKET_MISMATCH')
        if any(not x for x in (self.event_id,self.player_id,self.team_id,self.opponent_id)) or self.team_id==self.opponent_id:raise ValueError('INVALID_PLAYER_IDENTITY')
        if type(self.outcome)!=int or not math.isfinite(self.opportunity) or self.opportunity<0:raise ValueError('INVALID_PLAYER_OUTCOME')
        if 'yards' not in self.market and self.outcome<0:raise ValueError('INVALID_PLAYER_OUTCOME')
        if date.fromisoformat(self.played_on)>=utc(self.captured_at).date():raise ValueError('OUTCOME_NOT_FINAL_BEFORE_CAPTURE')
        if len(self.source_id)!=64 or len(self.source_hash)!=64 or self.provenance!='RECONSTRUCTED_HISTORY_UNVERIFIED_AS_OF':raise ValueError('SOURCE_PROVENANCE_MISMATCH')


def normalize(root,sport):
    root=Path(root);a=PublicStatsArchive(root/'data')
    ingestion=json.loads((root/'data/evaluations/prop-ingestion'/(sport+'.json')).read_text())
    rejected=Counter();rows={};conflicts=set();schedule={}
    sources=ingestion['sources'];bad_urls={r['url'] for r in ingestion['failures']}
    if sport=='NFL':
        m=next(m for m in sources if m['url'].endswith('games.csv'))
        schedule={r['game_id']:r for r in a.read(m)}
    for m in sources:
        if m['status']!=200 or m['url'] in bad_urls:rejected['SOURCE_ACCESS_OR_TRUNCATION']+=1;continue
        p=a.read(m);url=m['url']
        if sport=='NFL' and not url.endswith('.parquet') or sport=='MLB' and '/roster?' in url:continue
        if sport=='NHL':p=p['data']
        if sport=='MLB':p=[r for stat in p.get('stats',[]) for r in stat['splits']]
        for r in p:
            try:
                if sport=='NFL':
                    if r['season_type']!='REG':rejected['NON_REGULAR_SEASON']+=1;continue
                    game=schedule.get(r['game_id'])
                    if not game or game.get('home_score') in ('',None) or game.get('away_score') in ('',None):rejected['NO_CANONICAL_FINAL_RESULT']+=1;continue
                    if r['team'] not in (game['home_team'],game['away_team']) or r['opponent_team'] not in (game['home_team'],game['away_team']):raise ValueError('WRONG_PLAYER_TEAM')
                    played=game['gameday'];season=r['season'];event=r['game_id'];player=r['player_id'];name=r['player_display_name'];team=r['team'];opp=r['opponent_team'];stats=r
                    markets=['passing_yards'] if r['position']=='QB' else ['receptions','receiving_yards','rushing_attempts','rushing_yards'] if r['position'] in ('WR','TE','RB','FB') else []
                elif sport=='NBA':
                    if r['season_type']!=2:rejected['NON_REGULAR_SEASON']+=1;continue
                    if r['did_not_play'] is not False:rejected['DNP_NOT_ZERO']+=1;continue
                    played=r['game_date'].isoformat();season=r['season'];event=r['game_id'];player=r['athlete_id'];name=r['athlete_display_name'];team=r['team_id'];opp=r['opponent_team_id'];stats=r;markets=list(MARKETS[sport])
                elif sport=='NHL':
                    played=r['gameDate'];d=date.fromisoformat(played);season=d.year+int(d.month>=9);event=r['gameId'];player=r['playerId'];team=r['teamAbbrev'];opp=r['opponentTeamAbbrev']
                    goalie='/goalie/' in url;name=r['goalieFullName' if goalie else 'skaterFullName'];stats=dict(r)
                    if not goalie:stats['minutes']=r['timeOnIcePerGame']/60
                    markets=['goalie_saves'] if goalie else ['shots_on_goal']
                else:
                    if r.get('gameType')!='R' or r.get('sport',{}).get('id')!=1:rejected['NON_REGULAR_MLB']+=1;continue
                    played=r['date'];season=int(r['season']);event=r['game']['gamePk'];player=r['player']['id'];name=r['player']['fullName'];team=r['team']['id'];opp=r['opponent']['id'];stats=r['stat']
                    markets=['pitcher_strikeouts','pitcher_outs','hits_allowed'] if 'group=pitching' in url else ['hitter_hits','total_bases']
                if date.fromisoformat(played)>utc(m['captured_at']).date()-timedelta(days=2):rejected['RECENT_FINAL_STATUS_UNCONFIRMED']+=1;continue
                for market in markets:
                    opportunity,outcome=MARKETS[sport][market];v=stats.get(outcome);o=stats.get(opportunity)
                    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v!=int(v) or isinstance(o,bool) or not isinstance(o,(int,float)):
                        rejected['MISSING_STAT_OR_OPPORTUNITY']+=1;continue
                    row=PlayerOutcome(sport,market,str(event),str(player),name,str(team),str(opp),played,int(season),float(o),int(v),m['manifest_id'],m['hash'],m['captured_at']);row.validate()
                    key=(sport,market,str(event),str(player));old=rows.get(key)
                    if old and old!=row:
                        if utc(old.captured_at)==utc(row.captured_at):conflicts.add(key)
                        elif utc(old.captured_at)>utc(row.captured_at):continue
                    rows[key]=row
            except (KeyError,ValueError,TypeError):rejected['SCHEMA_OR_IDENTITY_FAILURE']+=1
    for key in conflicts:rows.pop(key,None)
    rejected['CONFLICTING_DUPLICATE']=len(conflicts)
    observations=sorted(rows.values(),key=lambda r:(r.played_on,r.event_id,r.player_id,r.market))
    return observations,dict(source_selection=ingestion['source_selection'],source_failures=ingestion['failures'],
        outcome_rows=len(observations),unique_player_games=len({(r.event_id,r.player_id) for r in observations}),
        unique_athletes=len({r.player_id for r in observations}),events=len({r.event_id for r in observations}),
        seasons=dict(sorted(Counter(r.season for r in observations).items())),rejections=dict(rejected),
        earliest_date=min((r.played_on for r in observations),default=None),latest_date=max((r.played_on for r in observations),default=None),
        historical_as_of_eligible=0,role_confirmed_opportunities=0)


class OpportunityModel:
    def __init__(self,sport,market):
        if market not in MARKETS.get(sport,{}):raise ValueError('CROSS_SPORT_MARKET_MISMATCH')
        self.sport=sport;self.market=market;self.players=defaultdict(lambda:deque(maxlen=POLICY['player_history']))
        self.n=0;self.sum_opportunity=0.;self.sum_outcome=0.;self.ids=set();self.source_ids=set();self.source_hashes=set();self.captures=[]
        self.residuals=deque(maxlen=POLICY['residual_window'])
    def update(self,r):
        r.validate()
        if (r.sport,r.market)!=(self.sport,self.market):raise ValueError('CROSS_SPORT_MARKET_MISMATCH')
        key=(r.event_id,r.player_id)
        if key in self.ids:raise ValueError('DUPLICATE_PLAYER_GAME')
        self.ids.add(key);self.players[r.player_id].append(r);self.n+=1;self.sum_opportunity+=r.opportunity;self.sum_outcome+=r.outcome
        self.source_ids.add(r.source_id);self.source_hashes.add(r.source_hash);self.captures.append(r.captured_at)
    def predict(self,player,as_of_day):
        history=list(self.players.get(player,[]))
        if self.n<POLICY['minimum_population_games'] or len(history)<POLICY['minimum_player_games']:raise ValueError('INSUFFICIENT_PRIOR_PLAYER_HISTORY')
        if any(date.fromisoformat(r.played_on)>date.fromisoformat(as_of_day)-timedelta(days=POLICY['embargo_days']) for r in history):raise ValueError('TARGET_OR_FUTURE_PLAYER_LEAKAGE')
        recent=history[-POLICY['opportunity_recent']:];prior=POLICY['prior_player_games'];global_opportunity=self.sum_opportunity/self.n
        if self.sum_opportunity<=0:raise ValueError('MISSING_OPPORTUNITY_HISTORY')
        global_rate=self.sum_outcome/self.sum_opportunity
        opportunity=(sum(r.opportunity for r in recent)+prior*global_opportunity)/(len(recent)+prior)
        rate=(sum(r.outcome for r in history)+prior*global_opportunity*global_rate)/(sum(r.opportunity for r in history)+prior*global_opportunity)
        mean=opportunity*rate;baseline=sum(r.outcome for r in recent)/len(recent)
        pmf=None
        if len(self.residuals)>=POLICY['minimum_oof_residuals']:
            samples=[int(round(mean+e)) for e in self.residuals]
            if 'yards' not in self.market:samples=[max(0,x) for x in samples]
            c=Counter(samples);pmf={str(k):v/len(samples) for k,v in sorted(c.items())}
        return dict(projected_opportunity=opportunity,production_rate=rate,projection=mean,baseline=baseline,
            distribution=pmf,training_n=self.n,player_history_n=len(history),residual_n=len(self.residuals),
            last_team_id=history[-1].team_id,last_observed_date=history[-1].played_on,
            team_changed=any(r.team_id!=history[-1].team_id for r in recent),calibrated_probability=None,p_low=None,
            model_status='UNVALIDATED',recommendations_enabled=False)
    def artifact(self):
        return dict(version=VERSION,sport=self.sport,market=self.market,policy=POLICY,training_n=self.n,
            sum_opportunity=self.sum_opportunity,sum_outcome=self.sum_outcome,
            player_histories={p:[asdict(r) for r in rows] for p,rows in sorted(self.players.items())},
            residuals=list(self.residuals),source_ids=sorted(self.source_ids),source_hashes=sorted(self.source_hashes),
            latest_source_capture=max(self.captures,default=None),training_ids_hash=digest(sorted(self.ids)),
            model_status='UNVALIDATED',cash_authority=False)


def evaluate(rows,sport,market):
    rows=sorted([r for r in rows if r.market==market],key=lambda r:(r.played_on,r.event_id,r.player_id))
    keys=[(r.event_id,r.player_id) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError('DUPLICATE_PLAYER_GAME')
    model=OpportunityModel(sport,market);records=[];pending=deque();errors=Counter();index=0
    for target in rows:
        cutoff=date.fromisoformat(target.played_on)-timedelta(days=POLICY['embargo_days'])
        while index<len(rows) and date.fromisoformat(rows[index].played_on)<=cutoff:
            model.update(rows[index]);index+=1
        while pending and date.fromisoformat(pending[0][0])<=cutoff:
            _,e=pending.popleft();model.residuals.append(e)
        try:p=model.predict(target.player_id,target.played_on)
        except ValueError as e:errors[str(e)]+=1;continue
        pending.append((target.played_on,target.outcome-p['projection']))
        if target.season<POLICY['evaluation_first_season']:continue
        pmf={int(k):v for k,v in p['distribution'].items()} if p['distribution'] else None
        records.append(dict(event_id=target.event_id,player_id=target.player_id,day=target.played_on,season=target.season,
            outcome=target.outcome,actual_opportunity=target.opportunity,projection=p['projection'],baseline=p['baseline'],
            projected_opportunity=p['projected_opportunity'],training_n=p['training_n'],
            crps=crps(pmf,target.outcome) if pmf else None,model_status='UNVALIDATED'))
    # Current artifact includes all already captured outcomes, not target-time facts.
    while index<len(rows):model.update(rows[index]);index+=1
    for _,e in pending:model.residuals.append(e)
    return model,records,dict(errors)


def summarize(records):
    if not records:return dict(n=0,mae=None,rmse=None,baseline_mae=None,baseline_rmse=None,crps=None)
    result=dict(n=len(records))
    for key,prefix in (('projection',''),('baseline','baseline_')):
        e=np.array([r[key]-r['outcome'] for r in records]);result[prefix+'mae']=float(np.mean(abs(e)));result[prefix+'rmse']=float(np.sqrt(np.mean(e*e)))
    result['opportunity_mae']=float(np.mean([abs(r['projected_opportunity']-r['actual_opportunity']) for r in records]))
    scores=[r['crps'] for r in records if r['crps'] is not None];result['crps_n']=len(scores);result['crps']=float(np.mean(scores)) if scores else None
    # Resample calendar weeks, keeping all correlated player/game rows together.
    blocks=defaultdict(list)
    for r in records:
        d=date.fromisoformat(r['day']);blocks[d-timedelta(days=d.weekday())].append(abs(r['projection']-r['outcome'])-abs(r['baseline']-r['outcome']))
    sums=np.array([sum(b) for b in blocks.values()]);ns=np.array([len(b) for b in blocks.values()]);rng=np.random.default_rng(7341)
    indices=rng.integers(0,len(sums),(1000,len(sums)));samples=sums[indices].sum(axis=1)/ns[indices].sum(axis=1)
    result['paired_mae_difference_95_week_bootstrap']=list(map(float,np.quantile(samples,[.025,.975])));result['week_blocks']=len(sums)
    result['beats_baseline_mae']=result['mae']<result['baseline_mae'];return result


def run(root,sport):
    root=Path(root);s=ResearchStore(root/'data');rows,coverage=normalize(root,sport)
    table=s.write_table(sport.lower()+'-player-outcomes',[asdict(r) for r in rows]);markets={}
    policy_path=s.root/'evaluations'/('props-policy-'+digest(POLICY)+'.json')
    s._immutable(policy_path,json.dumps(POLICY,sort_keys=True,indent=2).encode())
    for market in MARKETS[sport]:
        model,records,rejected=evaluate(rows,sport,market);artifact=model.artifact();h=digest(artifact)
        s._immutable(s.root/'models'/(sport.lower()+'-'+market+'-'+h+'.json'),json.dumps(artifact,sort_keys=True,indent=2).encode())
        evaluated=s.write_table(sport.lower()+'-'+market+'-oos',records)
        markets[market]=dict(training_n=model.n,unique_athletes=len(model.players),artifact_hash=h,evaluation=summarize(records),
            by_season={str(y):summarize([r for r in records if r['season']==y]) for y in sorted({r['season'] for r in records})},
            evaluation_table=evaluated,rejections=rejected,model_status='UNVALIDATED',recommendations_enabled=False,
            prospective_frozen_n=0,prospective_settled_n=0,market_comparison_n=0,calibrated_probability=None,p_low=None,
            roi=None,clv=None,missing_features=['verified injuries','confirmed participation and role','timestamped matching prop prices','book-specific settlement terms'])
    report=dict(sport=sport,generated_at=datetime.now(timezone.utc).isoformat(),model_version=VERSION,coverage=coverage,
        normalized_table=table,markets=markets,synthetic_performance_sample=0,mode='RESEARCH_ONLY',reference_unit=22,cash_committed=0,
        empirical_scope='chronological reconstructed observed appearances; no historical as-of or pregame participation proof',
        limitations=['No target opportunity or actual target role is used as an input.','DNP/absence not zero-filled; appearance-only evaluation is selection-biased relative to full scheduled player universe.',
                    'Source revisions captured now remain unverified historically.','Raw residual distributions are uncalibrated; no p_low or betting authority.',
                    'Multiple markets evaluated; no winner selected or thresholds tuned from these results.'],
        blockers=['PROSPECTIVE_PLAYER_IDENTITY_AND_ROLE_JOIN','CALIBRATION_PENDING','CONTEMPORANEOUS_PROP_MARKET_COMPARISON_PENDING'])
    out=root/'outputs';out.mkdir(exist_ok=True);(out/(sport.lower()+'_prop_research_status.json')).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--sport',choices=['NFL','NBA','NHL','MLB','all'],default='all');args=p.parse_args()
    for sport in ['NFL','NBA','NHL','MLB'] if args.sport=='all' else [args.sport]:
        r=run(args.root,sport);print(json.dumps(dict(sport=sport,coverage=r['coverage'],markets={k:dict(training_n=v['training_n'],**v['evaluation']) for k,v in r['markets'].items()})),flush=True)


if __name__=='__main__':main()
