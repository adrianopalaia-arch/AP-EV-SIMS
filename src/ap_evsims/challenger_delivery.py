"""Freeze new-version research, simulate it, and compare authentic exact quotes.

python -m ap_evsims.challenger_delivery --root . --sport all --draws 20000
No automatic promotion, cash commitment or shared-game/parlay claim.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib, json, math
from pathlib import Path
import numpy as np
from .integrity import digest, utc
from .identity import normalized_name
from .prop_challenger import VERSION, POLICY, features, distribution, metrics
from .prop_research import PlayerOutcome
from .prop_availability import capture
from .prop_prices import normalize_props
from .prop_prospective import freeze_prop
from .prop_market_research import comparison, freeze_comparison, benchmark_gate
from .providers.public_stats import PublicStatsArchive
from .research_store import ResearchStore
from .publication import atomic_json


def verified_model(root,sport,market,entry,at):
    data=Path(root)/'data';h=entry['artifact_hash']
    a=json.loads((data/'models'/(sport.lower()+'-'+market+'-'+h+'.json')).read_text())
    if digest(a)!=h or (a['sport'],a['market'],a['version'])!=(sport,market,VERSION) or a['policy']!=POLICY:raise ValueError('MODEL_ARTIFACT_MISMATCH')
    if utc(a['latest_source_capture'])>utc(at):raise ValueError('MODEL_SOURCE_LOOKAHEAD')
    table=entry['evaluation_table'];p=(data/table['path']).resolve()
    if data.resolve() not in p.parents:raise ValueError('EVALUATION_PATH_ESCAPE')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=table['fingerprint']:raise ValueError('EVALUATION_HASH_MISMATCH')
    e=metrics([json.loads(line) for line in raw.splitlines()]);gate=benchmark_gate(e)
    if gate=='RESEARCH_BENCHMARK_ADVANTAGE' and any(e.get(k) is None or e[k]>=e['baseline_'+k] for k in ('crps','nll','brier','binary_logloss')):
        gate='FAILED_DISTRIBUTION_BASELINE'
    return a,dict(sport=sport,market=market,model_version=VERSION,artifact_hash=h,training_n=a['training_n'],
        dataset_fingerprint=table['fingerprint'],evaluation=e,admission=gate,betting_validated=False,
        selection_caveat='Retrospective research evidence only; multiple comparisons and appearance selection remain; no promotion')


def project(artifact,player,at):
    if utc(artifact['latest_source_capture'])>utc(at):raise ValueError('MODEL_SOURCE_LOOKAHEAD')
    history=[PlayerOutcome(**r) for r in artifact['player_histories'].get(player,[])]
    x=features(history,utc(at).date().isoformat())
    if artifact['coefficients'] is None:raise ValueError('NO_TRAINED_MODEL')
    mean,workload=map(float,x@np.asarray(artifact['coefficients'])+artifact['intercept'])
    if 'yards' not in artifact['market']:mean=max(0.,mean)
    d=distribution(mean,artifact['residuals'],artifact['market'])
    if d is None:raise ValueError('INSUFFICIENT_OOF_RESIDUALS')
    return dict(projection=mean,projected_opportunity=max(0.,workload),baseline=float(x[3]),
        distribution={str(int(k)):float(p) for k,p in zip(*d)},training_n=artifact['training_n'],
        player_history_n=len(history),last_team_id=history[-1].team_id,last_observed_date=history[-1].played_on,
        calibrated_probability=None,p_low=None,model_status='UNVALIDATED',recommendations_enabled=False)


def simulate(forecast,draws):
    if draws<1000:raise ValueError('INSUFFICIENT_SIMULATION_DRAWS')
    pmf=forecast['projection']['distribution'];x=np.array([int(k) for k in pmf]);p=np.array(list(pmf.values()))
    ix=np.argsort(x);x=x[ix];p=p[ix]
    if abs(p.sum()-1)>1e-10 or np.any(p<0):raise ValueError('INVALID_SIMULATION_DISTRIBUTION')
    seed=int(forecast['forecast_hash'][:8],16);runs=[];exact_mean=float(x@p);sd=float(np.sqrt(((x-exact_mean)**2)@p));cdf=np.cumsum(p)
    tolerance=math.sqrt(math.log(2000)/(2*draws))
    for offset in (0,1):
        values=np.random.default_rng(seed+offset).choice(x,size=draws,p=p);ordered=np.sort(values)
        distance=float(np.max(abs(np.searchsorted(ordered,x,side='right')/draws-cdf)))
        runs.append(dict(seed=seed+offset,draws=draws,mean=float(values.mean()),cdf_max_error=distance,
            quantiles_10_50_90=list(map(float,np.quantile(values,[.1,.5,.9]))),
            within_sampling_tolerance=bool(distance<=tolerance and abs(values.mean()-exact_mean)<=6*sd/math.sqrt(draws)+1e-9)))
    return dict(forecast_hash=forecast['forecast_hash'],sport=forecast['sport'],market=forecast['market'],
        exact_distribution_mean=exact_mean,pmf_hash=digest(pmf),runs=runs,cdf_tolerance=tolerance,
        convergence_passed=all(r['within_sampling_tolerance'] for r in runs),
        scope='Independent marginal statistic simulation; shared game-state dependence not modeled; never a joint parlay probability')


def run(root,sport,draws=20000,*,simulate_forecasts=True):
    root=Path(root);store=ResearchStore(root/'data');status_path=root/'outputs'/(sport.lower()+'_challenger_status.json');status=json.loads(status_path.read_text())
    verified_completion=datetime.fromtimestamp(status_path.stat().st_mtime,timezone.utc).isoformat()
    availability=capture(root,sport);event=availability['event'];at=datetime.now(timezone.utc).isoformat()
    if utc(at)>=utc(event['event_start']):raise ValueError('EVENT_STARTED')
    access=json.loads((store.root/'evaluations/prop-price-access.json').read_text());qrecord=next(r for r in access['sports'] if r['sport']==sport).get('record',{})
    qs,_=normalize_props(store,store.manifest(qrecord['snapshot_id']),sport,at) if qrecord.get('status')==200 else ([],{})
    aliases=defaultdict(set)
    for person in availability['identities']:
        for name in person['aliases']:aliases[normalized_name(name)].add(person['player_id'])
    archive=PublicStatsArchive(store.root);manifests={}
    for p in archive.folder.glob('*.json'):
        m=json.loads(p.read_text());manifests[m['manifest_id']]=m
    verified=set();records=[];comparisons=[];rejected=[];simulations=[];new_count=0;benchmarks={}
    for market,entry in status['markets'].items():
        artifact,benchmark=verified_model(root,sport,market,entry,at);benchmarks[market]=benchmark
        for sid in artifact['source_ids']:
            if sid not in verified:archive.read(manifests[sid]);verified.add(sid)
        for person in availability['records']:
            if sport=='NHL' and (market=='goalie_saves')!=(person['position']=='G'):continue
            if sport=='MLB' and market.startswith(('pitcher_','hits_allowed'))!=(person['position']=='P'):continue
            try:p=project(artifact,person['player_id'],at)
            except ValueError as e:rejected.append(dict(player_id=person['player_id'],market=market,reason=str(e)));continue
            reasons=person['reasons']+availability['event_identity_reasons']+['PROSPECTIVE_CALIBRATION_PENDING','BOOK_SETTLEMENT_RULE_UNVERIFIED']
            if benchmark['admission']!='RESEARCH_BENCHMARK_ADVANTAGE':reasons.append(benchmark['admission'])
            if p['last_team_id']!=person['team_id']:reasons.append('TEAM_CHANGE_ROLE_UNVERIFIED')
            body=dict(sport=sport,market=market,event_id=event['event_id'],event_start=event['event_start'],event_mapping=event,
                player_id=person['player_id'],player_name=person['player_name'],team_id=person['team_id'],
                model_version=VERSION,artifact_hash=entry['artifact_hash'],generated_at=at,model_training_finished_at=verified_completion,
                completion_timestamp_basis='Completed model report filesystem write time, checked before freezing',
                latest_source_capture=max(artifact['latest_source_capture'],availability['latest_source_capture']),
                training_source_hashes=artifact['source_hashes'],availability_snapshot=availability['snapshot_hash'],projection=p,
                conditional_on='Player appears; workload is projected, not confirmed',role_confirmed=person['role_confirmed'],
                model_status='UNVALIDATED',recommendations_enabled=False,calibrated_probability=None,p_low=None,priced_markets=[],
                mode='RESEARCH_ONLY',reference_unit=22,cash_committed=0,pass_reasons=sorted(set(reasons)))
            f,new=freeze_prop(store,body);new_count+=new
            if simulate_forecasts:
                simulation=simulate(f,draws);simulations.append(simulation)
                store._immutable(store.root/'evaluations'/('simulation-'+digest(simulation)+'.json'),json.dumps(simulation,sort_keys=True).encode())
            compact={k:v for k,v in f.items() if k not in ('projection','training_source_hashes')}
            compact['projection']={k:v for k,v in f['projection'].items() if k!='distribution'}
            compact['distribution_hash']=digest(f['projection']['distribution']);compact['distribution_location']='immutable local forecast referenced by forecast_hash'
            compact['forecast_hash_semantics']='Hash of full immutable record including local PMF; this published record is a summary'
            records.append(compact)
            for q in qs:
                if q['book'] not in ('draftkings','fanduel') or q['market']!=market or aliases.get(normalized_name(q['player_name']))!={person['player_id']}:continue
                try:
                    for c in comparison(f,q,person,benchmark,at,qs,identity_store=store):
                        mass=c['raw_model_outcome_mass'];fair=None
                        if mass and mass['p_win']>0:fair=1+mass['p_loss']/mass['p_win']
                        c.update(raw_fair_decimal_odds=fair,zero_ev_decimal_threshold=fair,
                            conservative_ev=None,conservative_price_threshold=None,
                            threshold_semantics='Raw break-even conditional on participation/standard payout; no conservative threshold without calibrated uncertainty',
                            simulation_basis='Frozen ridge prior-OOF residual mixture; exact quantiles, separately verified by Monte Carlo')
                        saved=freeze_comparison(store,c);comparisons.append(saved)
                except ValueError as e:rejected.append(dict(quote_id=q['quote_id'],reason=str(e)))
    report=dict(sport=sport,generated_at=at,model_version=VERSION,new_frozen=new_count,frozen_forecasts=len(records),
        predictions=records,comparisons=comparisons,rejections=rejected,benchmarks=benchmarks,
        simulations=simulations,simulation_draws=sum(sum(r['draws'] for r in s['runs']) for s in simulations),
        convergence_failures=sum(not s['convergence_passed'] for s in simulations),
        qualified_market_comparisons=0,prospective_settled=0,validated_edges=0,recommendations_enabled=False,
        event=event,availability_snapshot=availability['snapshot_hash'])
    atomic_json(root/'outputs'/(sport.lower()+'_challenger_prospective.json'),report)
    return {k:v for k,v in report.items() if k not in ('predictions','comparisons','rejections','simulations','benchmarks')}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--sport',default='all',choices=['all','NFL','NBA','NHL','MLB']);p.add_argument('--draws',type=int,default=20000);a=p.parse_args()
    for sport in ['NFL','NBA','NHL','MLB'] if a.sport=='all' else [a.sport]:
        try:result=run(a.root,sport,a.draws)
        except Exception as e:result=dict(sport=sport,status='DELIVERY_BLOCKED',error_category=type(e).__name__)
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
