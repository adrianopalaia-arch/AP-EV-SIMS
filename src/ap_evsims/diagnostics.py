"""Local research diagnostics. Null means evidence is absent, never success."""
from collections import defaultdict
import math,random,statistics
from .integrity import utc,digest
from .calibration import brier_score,log_loss
from .models.numerics import quantile

def latency_report(rows):
    values=[];rejected=0
    fields=('published_at','available_at','ingested_at','feature_at','prediction_at','publication_at')
    for row in rows:
        try:
            stamps=[utc(row[k]) for k in fields]
            if stamps!=sorted(stamps):raise ValueError('LOOKAHEAD_RISK')
            values.append((stamps[-1]-stamps[0]).total_seconds())
        except (KeyError,ValueError,TypeError):rejected+=1
    return dict(n=len(values),invalid_order_or_missing=rejected,p50=quantile(values,.5) if values else None,
        p90=quantile(values,.9) if values else None,p99=quantile(values,.99) if values else None,
        unit='seconds',clock_synchronized=None)

def inclusion_report(universe,included):
    by_id={r['event_id']:r for r in universe}
    if len(by_id)!=len(universe):raise ValueError('DUPLICATE_UNIVERSE_EVENT')
    included=set(included)
    if included-set(by_id):raise ValueError('UNKNOWN_INCLUDED_EVENT')
    groups={}
    for row in universe:
        group=row.get('stratum','unknown');g=groups.setdefault(group,dict(eligible=0,included=0))
        g['eligible']+=1;g['included']+=row['event_id'] in included
    rates=[g['included']/g['eligible'] for g in groups.values()]
    return dict(eligible=len(universe),included=len(included),excluded=len(universe)-len(included),strata=groups,
        selection_bias_flag='SAMPLE_SELECTION_BIAS' if len(rates)>1 and max(rates)-min(rates)>.2 else 'NOT_ESTABLISHED',
        reason='No qualifying universe' if not universe else None)

def proper_score_report(rows):
    if not rows:return dict(n=0,brier=None,log_loss=None,market_brier=None,market_log_loss=None,beats_market=False)
    keys=[(r['event_id'],r['market'],r['selection']) for r in rows]
    if len(keys)!=len(set(keys)):raise ValueError('DUPLICATE_DIAGNOSTIC_OBSERVATION')
    if any(r.get('dataset_kind')!='provider_history' for r in rows):raise ValueError('NON_EMPIRICAL_EVIDENCE')
    y=[r['outcome'] for r in rows];p=[r['probability'] for r in rows];m=[r['market_probability'] for r in rows]
    b,l=brier_score(p,y),log_loss(p,y);mb,ml=brier_score(m,y),log_loss(m,y)
    return dict(n=len(rows),brier=b,log_loss=l,market_brier=mb,market_log_loss=ml,beats_market=b<mb and l<ml)

def grouped_diagnostics(rows,field):
    groups=defaultdict(list)
    for row in rows:groups[str(row.get(field,'UNKNOWN'))].append(row)
    return {group:proper_score_report(values) for group,values in groups.items()}

def p_low_diagnostic(rows):
    """Tests aggregate conservatism; outcomes cannot identify individual true probabilities."""
    if not rows:return dict(n=0,blocks=0,observed_rate=None,mean_p_low=None,aggregate_margin=None,coverage_validated=False)
    if any(r.get('dataset_kind')!='provider_history' for r in rows):raise ValueError('NON_EMPIRICAL_EVIDENCE')
    if any(not math.isfinite(r['p_low']) or not 0<=r['p_low']<=r['probability']<=1 for r in rows):raise ValueError('INVALID_UNCERTAINTY_BOUND')
    blocks={r['block'] for r in rows};observed=statistics.mean(r['outcome'] for r in rows);low=statistics.mean(r['p_low'] for r in rows)
    return dict(n=len(rows),blocks=len(blocks),observed_rate=observed,mean_p_low=low,aggregate_margin=observed-low,
        coverage_validated=False,note='Aggregate realized rate is a diagnostic, not individual-probability coverage proof.')

def ablation_comparison(baseline,challenger, *, hypothesis,feature_or_source,cost,experiment_id):
    if not hypothesis or not feature_or_source or not experiment_id:raise ValueError('UNREGISTERED_ABLATION')
    index=lambda rows:{(r['event_id'],r['market'],r['selection']):r for r in rows}
    a,b=index(baseline),index(challenger)
    if set(a)!=set(b) or any(a[k]['outcome']!=b[k]['outcome'] for k in a):raise ValueError('UNMATCHED_ABLATION_ROWS')
    left,right=proper_score_report(baseline),proper_score_report(challenger)
    improvements=None if not baseline else dict(brier=left['brier']-right['brier'],log_loss=left['log_loss']-right['log_loss'])
    return dict(experiment_id=experiment_id,hypothesis=hypothesis,feature_or_source=feature_or_source,cost=cost,
        baseline=left,challenger=right,improvement=improvements,decision='REVIEW_UNTOUCHED_EVIDENCE' if improvements and min(improvements.values())>0 else 'KEEP_SIMPLE_BASELINE',
        automatic_feature_change=False,requires=['matched CLV','clustered intervals','season stability','prospective evidence'])

def bankroll_stress(positions, *, starting_bankroll,unit,paths=2000,seed=717):
    """Hypothetical grouped Bernoulli paths, explicitly not empirical model performance."""
    if not math.isfinite(starting_bankroll) or starting_bankroll<=0 or not math.isfinite(unit) or unit<=0 or paths<100:raise ValueError('INVALID_STRESS_POLICY')
    groups=defaultdict(list)
    for p in positions:
        if not p.get('group') or not 0<=p['probability']<=1 or not math.isfinite(p['stake']) or p['stake']<0 or not math.isfinite(p['decimal_odds']) or p['decimal_odds']<=1:raise ValueError('INVALID_STRESS_POSITION')
        groups[p['group']].append(p)
    if not positions:return dict(status='MISSING_LOCAL_DATA',n=0,median=None,p05=None,p01=None,max_drawdown=None,probability_ruin=None,empirical_performance=False)
    rng=random.Random(seed);ending=[];drawdowns=[];ruins=ten=twenty=0
    for _ in range(paths):
        balance=peak=starting_bankroll;max_dd=0;ruined=False
        for group in groups.values():
            # Common uniform within a declared risk group intentionally stresses
            # positive dependence; it is not a fitted correlation estimate.
            u=rng.random();total=sum(p['stake'] for p in group)
            if total>balance:
                ruined=True;balance=0;max_dd=max(max_dd,peak);break
            balance+=sum(p['stake']*(p['decimal_odds']-1 if u<p['probability'] else -1) for p in group)
            peak=max(peak,balance);max_dd=max(max_dd,peak-balance)
            if balance<unit:ruined=True
        ending.append(balance-starting_bankroll);drawdowns.append(max_dd)
        ruins+=ruined;ten+=max_dd>=10*unit;twenty+=max_dd>=20*unit
    return dict(status='HYPOTHETICAL_STRESS_ONLY',n=len(positions),paths=paths,median=quantile(ending,.5),p05=quantile(ending,.05),p01=quantile(ending,.01),
        max_drawdown=max(drawdowns),p95_drawdown=quantile(drawdowns,.95),probability_10_unit_drawdown=ten/paths,
        probability_20_unit_drawdown=twenty/paths,probability_ruin=ruins/paths,ruin_definition='balance below one unit or unable to fund fixed scenario stakes',
        empirical_performance=False,correlation_assumption='common uniform within group; independent between declared groups')

def kelly_stress(p_model,p_low,extra_error,decimal_odds, *, fraction=.25,cap=.01):
    if not 0<=p_low<=p_model<=1 or not 0<=extra_error<=1 or not math.isfinite(decimal_odds) or decimal_odds<=1 or not 0<fraction<=.25 or not 0<cap<=.01:raise ValueError('INVALID_STAKING_POLICY')
    b=decimal_odds-1
    fractions=[min(cap,fraction*max(0,(p*decimal_odds-1)/b)) for p in (p_model,p_low,max(0,p_low-extra_error))]
    return dict(model_fraction=fractions[0],p_low_fraction=fractions[1],extra_error_fraction=fractions[2],
        stability_warning=fractions[0]>0 and fractions[2]<fractions[0]/2,authorization_to_bet=False)

def readiness_gate(audit, *, empirical_n,prospective_n,beats_market,coverage_validated):
    reasons=[]
    if any(r['severity']=='CRITICAL' and (r['result']!='PASS' or not r['tested']) for r in audit):reasons.append('CRITICAL_RED_TEAM_UNRESOLVED')
    if len(audit)!=50 or {r['id'] for r in audit}!=set(range(1,51)):reasons.append('INCOMPLETE_RED_TEAM_AUDIT')
    if empirical_n<300:reasons.append('INSUFFICIENT_EMPIRICAL_SAMPLE')
    if prospective_n<100:reasons.append('INSUFFICIENT_PROSPECTIVE_SAMPLE')
    if not beats_market:reasons.append('NO_MARKET_INCREMENTAL_EVIDENCE')
    if not coverage_validated:reasons.append('UNCERTAINTY_COVERAGE_UNVERIFIED')
    if any(r['severity']=='HIGH' and r['result']!='PASS' for r in audit):reasons.append('HIGH_RED_TEAM_UNRESOLVED')
    return dict(status='RESEARCH_ONLY' if reasons else 'MANUAL_READINESS_REVIEW',reasons=reasons,automatic_promotion=False)
