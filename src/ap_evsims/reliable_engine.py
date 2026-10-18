"""Unattended local research cycle. No wagers, simulation draws or model promotion.

python -m ap_evsims.reliable_engine --root . --collect
"""
import argparse,json,math,statistics
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path
from .integrity import digest,utc
from .publication import atomic_json,atomic_text
from .providers.security import load_credentials
from .providers.validation import ProviderValidator
from .providers.quota import QuotaLedger
from .research_store import ResearchStore
from .warehouse import Warehouse
from .operations import collect_odds
from .prop_prices import collect_priority
from .challenger_delivery import run as forecast_props
from .reliable_results import run as settle
from .cfb_frozen_board import run as cfb_board
from .product import card_lock
from .book_rule_evidence import capture as capture_rule_sources

SPORTS=('CFB','NHL','NBA','NFL','MLB')


def evidence_policy(store,at):
    path=store.root/'evaluations/reliable-evidence-policy.json'
    if path.exists():
        p=json.loads(path.read_text())
        if digest({k:v for k,v in p.items() if k!='policy_hash'})!=p['policy_hash']:raise ValueError('EVIDENCE_POLICY_CHANGED')
        return p
    start=utc(at);p=dict(version='prospective-separated-phases-v1',registered_at=at,training_end=at,
        calibration_start=at,calibration_end=(start+timedelta(days=28)).isoformat(),
        selection_start=(start+timedelta(days=28)).isoformat(),selection_end=(start+timedelta(days=56)).isoformat(),
        untouched_holdout_start=(start+timedelta(days=56)).isoformat(),untouched_holdout_end=(start+timedelta(days=98)).isoformat(),
        inspected_retrospective_period='EXPLORATORY_NOT_UNTOUCHED',minimum_distinct_event_clusters=100,
        power_requirement='Clustered paired proper-score confidence interval must exclude zero and have half-width <=0.01; the 100-game floor alone is not sufficient power.',
        selection_rule='No promotion unless both Brier and log loss beat baseline and independent consensus on identical holdout observations; multiplicity correction required.',
        probability_calibrator='Fit only on calibration partition; freeze before selection and holdout. No fit exists yet.',
        uncertainty='No p_low until coverage-tested uncertainty on untouched data. No arbitrary shrinkage multiplier.',
        paper_direction='Over for props and home for CFB; first fresh identity-matched book/line observation only.',
        cash_authority=False,automatic_promotion=False)
    p['policy_hash']=digest(p);store._immutable(path,json.dumps(p,sort_keys=True).encode());return p


def current_candidate(c,at):
    result=dict(c);age=(utc(at)-utc(c['quote_timestamp'])).total_seconds();reasons=set(c['pass_reasons'])
    if age>180:reasons.add('STALE_PRICE')
    if age<0 or utc(c['quote_captured_at'])>utc(at):reasons.add('LOOKAHEAD_RISK')
    if utc(at)>=utc(c['event_start']):reasons.add('EVENT_STARTED')
    result.update(quote_age_seconds=age,status='RESEARCH_ONLY',decision='PASS',pass_reasons=sorted(reasons),
        current_price_fresh=0<=age<=180 and utc(at)<utc(c['event_start']),published_at=at,
        calibrated_probability=None,p_low=None,conservative_ev=None,approved=False,recommendations_enabled=False)
    if result.get('raw_fair_decimal_odds') is None:
        mass=c.get('raw_model_outcome_mass')
        if mass and mass['p_win']>0:result['raw_fair_decimal_odds']=1+mass['p_loss']/mass['p_win']
    result['conservative_price_threshold']=None
    result['rank']=None # No validated conservative EV => no validated ranking.
    return result


def publish(root,week,candidates,results,activity,policy,at):
    root=Path(root);out=root/'outputs';candidates=[current_candidate(c,at) for c in candidates]
    sports={}
    for sport in SPORTS:
        status=json.loads((out/('cfb_score_research_status.json' if sport=='CFB' else sport.lower()+'_challenger_status.json')).read_text())
        cs=[c for c in candidates if c['sport']==sport];cohorts=[c for c in results['cohorts'] if c['sport']==sport]
        futures=week['forecasts'] if sport=='CFB' else json.loads((out/(sport.lower()+'_challenger_prospective.json')).read_text())['predictions']
        futures=[f for f in futures if utc(at)<utc(f['event_start'])<=utc(at)+timedelta(days=7)]
        future_report={} if sport=='CFB' else json.loads((out/(sport.lower()+'_challenger_prospective.json')).read_text())
        availability={} if sport=='CFB' else json.loads((out/(sport.lower()+'_availability.json')).read_text())
        failures=week['rejections'] if sport=='CFB' else future_report.get('rejections',[])
        source_blocks=sorted({reason for row in availability.get('records',[]) for reason in row['reasons']})
        price_attempt=next((r.get('latest_attempt',{}) for r in activity.get('prop_collection',{}).get('sports',[]) if r['sport']==sport),{})
        sports[sport]=dict(future_forecasts=len(futures),exact_line_comparisons=len(cs),fresh_comparisons=sum(c['current_price_fresh'] for c in cs),
            approved_edges=0,rejected_candidates=len(cs),prospective_cohorts=cohorts,
            failed_forecast_count=len(failures),failed_forecast_reasons=dict(Counter(r['reason'] for r in failures)),
            availability_blockers=source_blocks,source_identity_warnings=availability.get('event_identity_reasons',[]),
            current_collection_status=price_attempt.get('status'),unverified_price_identity_count=sum(c.get('price_identity_verified') is False for c in cs),
            priced_settled=sum(r['sport']==sport for r in results['priced_records']),
            independent_consensus_settled=sum(r['sport']==sport and r['independent_consensus_scores'] is not None for r in results['priced_records']),
            prospective_distinct_games=len({r['event_id'] for r in results['records'] if r['sport']==sport}),
            historical_evaluation_n=status['evaluation']['n'] if sport=='CFB' else {m:r['evaluation']['n'] for m,r in status['markets'].items()},
            historical_status='RECONSTRUCTED_PREVIOUSLY_INSPECTED',model_status='RESEARCH_ONLY_PROSPECTIVE_GATE_PENDING',
            reasons=dict(Counter(reason for c in cs for reason in c['pass_reasons'])),qualified_roi=None,qualified_clv=None)
    bodies={
        'week_ahead_game_probabilities.json':dict(generated_at=at,forecast_horizon_days=7,game_forecasts=week['forecasts'],sports={s:dict(game_model_available=s=='CFB',future_forecasts=v['future_forecasts'],scope='game margins and moneylines' if s=='CFB' else 'player-stat distributions only') for s,v in sports.items()},rejections=week['rejections'],recommendations_enabled=False),
        'live_research_candidates.json':dict(generated_at=at,mode='PREGAME_RESEARCH_NOT_IN_PLAY',candidates=candidates,sports=sports,validated_ranking=[],recommendations_enabled=False),
        'validated_edges.json':dict(generated_at=at,edges=[],decision='PASS',reason='NO_PROSPECTIVELY_VALIDATED_PRICE_MATCHED_MODEL',core_enabled=False),
        'prospective_settlements.json':results,
        'reliability_status.json':dict(generated_at=at,activity=activity,evidence_policy=policy,model_training_runs=0,monte_carlo_draws=0,
            sports=sports,quota=QuotaLedger(root/'data/quota.sqlite').summary(),core_enabled=False,automatic_wagers=False)
    }
    for name,body in bodies.items():atomic_json(out/name,body)
    atomic_json(out/'reliability_manifest.json',dict(generated_at=at,hashes={n:digest(b) for n,b in bodies.items()}))
    lines=['# Model performance scoreboard','',f'Generated UTC: {at}. Actual frozen prospective outcomes; no model promoted.',
        '', '| Sport / market / model | Settled forecasts | Distinct games | MAE | Frozen simple baseline MAE | RMSE |', '|---|---:|---:|---:|---:|---:|']
    for c in results['cohorts']:lines.append(f"| {c['sport']} / {c['market']} / {c['model_version']} | {c['n']} | {c['distinct_games']} | {c['mae']:.4f} | {c['baseline_mae']:.4f} | {c['rmse']:.4f} |")
    lines+=['','Model versions are separate cohorts. CFB versions can score the same game; player outcomes within a game are correlated. Do not sum these rows as independent games.',
        '', '| Priced model | N (Over only) | Distinct games | Model Brier / log loss | Entry-book Brier / log loss | Independent consensus N |', '|---|---:|---:|---|---|---:|']
    for c in results['priced_cohorts']:
        lines.append(f"| {c['model_version']} | {c['n']} | {c['distinct_games']} | {c['raw_brier']:.4f} / {c['raw_log_loss']:.4f} | {c['entry_book_brier']:.4f} / {c['entry_book_log_loss']:.4f} | {c['independent_consensus_n']} |")
    lines+=['','The initial forecasts were frozen before play, but the current reporting/selection policy was registered after those games. These results are exploratory, not an untouched confirmatory holdout.',
        'The entry sportsbook is a descriptive baseline, not independent consensus. Calibration-band counts are in prospective_settlements.json. No calibrated probability or p_low is fitted from these small samples.',
        'Qualified CLV, hypothetical ROI, return uncertainty and drawdown remain unavailable: pre-entry rule evidence and authentic near-start closing captures are missing. Unknown DNP/void outcomes are not zero-valued losses.',
        '', 'Historical training/evaluation counts are retained in each challenger_status.json and P0_MEASURED_RESULTS.md. No training run or extra simulation draws occurred in this cycle.',
        '', 'Separate future calibration, selection and untouched holdout windows are fixed by the immutable evidence policy. Existing inspected seasons remain exploratory. Power and multiplicity requirements remain unmet.','']
    atomic_text(root/'reports/MODEL_PERFORMANCE_SCOREBOARD.md','\n'.join(lines))
    lines=['# Daily betting decisions','',f'Generated UTC: {at}. **PASS — CORE disabled.** Reference unit $22; no stakes authorized.',
        '', '| Sport | Future forecasts | Exact side comparisons | Fresh | Priced settled | Distinct prospective games | Approved |','|---|---:|---:|---:|---:|---:|---:|']
    for sport,v in sports.items():lines.append(f"| {sport} | {v['future_forecasts']} | {v['exact_line_comparisons']} | {v['fresh_comparisons']} | {v['priced_settled']} | {v['prospective_distinct_games']} | 0 |")
    lines+=['','## Failures and missing evidence','']+['- '+s+': '+json.dumps(dict(candidate_rejections=v['reasons'],availability=v['availability_blockers'],identity_warnings=v['source_identity_warnings'],missing_history=v['failed_forecast_reasons'],collection=v['current_collection_status']),sort_keys=True) for s,v in sports.items()]+[
        '- Missing confirmed participation, current opportunities and complete injury coverage continue to block wagering.',
        '- MLB postponement and postseason-domain conflicts remain blocked when sources disagree.',
        '- No verified pre-entry bookmaker terms or independent multi-book NHL consensus for the settled cohort.',
        '- Missing historical sportsbook entitlement is not replaced with closing prices or fabricated history.',
        '- Prices expire after 180 seconds. A cached schedule run does not refresh quote timestamps.',
        '', 'See reliability_status.json for actual source/cadence failures and quota metadata, and MODEL_PERFORMANCE_SCOREBOARD.md for measured results.','']
    atomic_text(root/'reports/DAILY_BETTING_DECISIONS.md','\n'.join(lines));return sports


def run(root,*,collect=False,daily_cap=24,reserve=50):
    root=Path(root).resolve();s=ResearchStore(root/'data');w=Warehouse(s.root);load_credentials(root/'.env')
    with card_lock(s.root/'reliable-runner'):
        at=datetime.now(timezone.utc).isoformat();policy=evidence_policy(s,at);activity={};deadlines={}
        for p in s.root.joinpath('predictions/props').glob('*.json'):
            f=json.loads(p.read_text());key=f['event_mapping']['odds_event_id'];old=deadlines.get(key)
            if old is None or utc(f['event_start'])<utc(old):deadlines[key]=f['event_start']
        if not collect:
            for key,name in (('prop_collection','prop-price-access.json'),('cfb_collection','odds-collection-latest.json')):
                path=s.root/'evaluations'/name
                if path.exists():activity[key]=json.loads(path.read_text()) # Preserve original collection clocks.
        if collect:
            activity['book_rules']=capture_rule_sources(root)
            activity['prop_collection']=collect_priority(root,daily_credit_cap=daily_cap,reserve_credits=reserve,cadence_aware=True,minimum_lead_seconds=0,canonical_deadlines=deadlines,
                priority_markets={'NHL':['player_shots_on_goal','player_total_saves'],'NBA':['player_rebounds','player_assists'],
                                  'MLB':['batter_hits','batter_total_bases'],'NFL':['player_receptions','player_reception_yds']})
            activity['cfb_collection']=collect_odds(s,w,daily_credit_cap=daily_cap,reserve_credits=reserve,closing_credit_reserve=6)
            latest=[json.loads(p.read_text()) for p in s.root.joinpath('manifests').glob('*.json')]
            last=max((utc(m['fetched_at']) for m in latest if m.get('provider')=='cfbd' and m.get('endpoint')=='games'),default=None)
            cfb_in_result_window=any(0<(utc(at)-utc(json.loads(p.read_text())['event_start'])).total_seconds()<8*3600
                for p in s.root.joinpath('predictions/cfb-score').glob('*.json'))
            if last is None or (utc(at)-last).total_seconds()>(1800 if cfb_in_result_window else 86400):
                r,_=ProviderValidator(s).request('cfbd','games',dict(year=utc(at).year,seasonType='regular',classification='fbs'));activity['cfbd_results']=r
                if r['status']==200:
                    try:w.ingest_manifest(s,s.manifest(r['snapshot_id']))
                    except ValueError as e:activity['cfbd_quarantine']=str(e)
        results=settle(root,refresh=collect);week=cfb_board(root);candidates=list(week['candidates']);activity['new_cfb_forecasts']=week['new_forecasts']
        for sport in ('NHL','NBA','NFL','MLB'):
            path=root/'outputs'/(sport.lower()+'_challenger_prospective.json')
            old=json.loads(path.read_text());folder=s.root/'evaluations/delivery-history';folder.mkdir(exist_ok=True)
            s._immutable(folder/(digest(old)+'.json'),json.dumps(old,sort_keys=True).encode())
            try:activity[sport]=forecast_props(root,sport,simulate_forecasts=False)
            except (ValueError,KeyError,OSError,TypeError) as e:activity[sport]=dict(status='BLOCKED',category=type(e).__name__,reason=str(e) if isinstance(e,ValueError) else type(e).__name__)
            latest=json.loads(path.read_text());candidates+=latest['comparisons']
        at=datetime.now(timezone.utc).isoformat();sports=publish(root,week,candidates,results,activity,policy,at)
        from .reliable_handoff import sync
        sync(root)
        return dict(generated_at=at,sports=sports,settled_forecast_observations=results['settled_forecast_observations'],priced_settled=results['priced_settled_observations'],
                    new_simulation_draws=0,core_enabled=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--collect',action='store_true');p.add_argument('--daily-cap',type=int,default=24);p.add_argument('--reserve',type=int,default=50);a=p.parse_args()
    root=Path(a.root).resolve()
    try:result=run(root,collect=a.collect,daily_cap=a.daily_cap,reserve=a.reserve)
    except Exception as e:
        # Never print provider exceptions/request URLs or process environment.
        atomic_json(root/'outputs/reliability_failure.json',dict(generated_at=datetime.now(timezone.utc).isoformat(),error_category=type(e).__name__,status='RUN_FAILED'))
        raise SystemExit('Research cycle failed; sanitized failure report saved.') from None
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
