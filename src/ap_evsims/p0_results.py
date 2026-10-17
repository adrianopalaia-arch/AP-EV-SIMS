"""Publish measured historical expansion/challenger evidence, never bet approval.

python -m ap_evsims.p0_results --root . [--nfl-control]
Existing versioned forecasts, source archives, and prior reports remain intact.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib, json
from pathlib import Path
import numpy as np
from .integrity import digest, utc
from .publication import atomic_json, atomic_text
from .prop_research import normalize, evaluate, summarize
from .prop_prices import normalize_props
from .prop_challenger import VERSION
from .challenger_delivery import simulate
from .research_store import ResearchStore


def table_rows(data, table):
    p=(data/table['path']).resolve()
    if data.resolve() not in p.parents:raise ValueError('TABLE_PATH_ESCAPE')
    body=p.read_bytes()
    if hashlib.sha256(body).hexdigest()!=table['fingerprint']:raise ValueError('EVALUATION_HASH_MISMATCH')
    return [json.loads(line) for line in body.splitlines()]


def paired_comparison(old,new):
    key=lambda r:(r['event_id'],r['player_id'])
    a={key(r):r for r in old};b={key(r):r for r in new}
    if len(a)!=len(old) or len(b)!=len(new):raise ValueError('DUPLICATE_EVALUATION_IDENTITY')
    same=[k for k in sorted(a.keys()&b.keys()) if a[k]['outcome']==b[k]['outcome']]
    def score(rows):
        if not rows:return dict(n=0,mae=None,rmse=None)
        e=np.array([r['projection']-r['outcome'] for r in rows])
        return dict(n=len(rows),mae=float(np.abs(e).mean()),rmse=float(np.sqrt((e*e).mean())))
    return dict(common_sample_n=len(same),before=score([a[k] for k in same]),after=score([b[k] for k in same]),
        revised_outcome_exclusions=len(a.keys()&b.keys())-len(same),
        before_only=len(a.keys()-b.keys()),after_only=len(b.keys()-a.keys()),
        scope='Identical event/player/outcome rows; combined effect of history expansion and new algorithm, not a randomized causal attribution')


def price_inventory(store):
    counts=Counter();snapshots=Counter();distinct=set();historical=[]
    for p in store.root.joinpath('manifests').glob('*.json'):
        m=json.loads(p.read_text())
        if m.get('provider')!='odds' or m.get('parameters',{}).get('endpoint_status',200)!=200:continue
        if m.get('availability_basis')=='historical_odds_snapshot':
            m=store.manifest(m['snapshot_id']);historical.append(dict(snapshot_id=m['snapshot_id'],observed_at=m['observed_at']))
        if '/events/' not in m.get('endpoint','') or not m['endpoint'].endswith('/odds'):continue
        payload=store.payload(store.manifest(m['snapshot_id']))
        from .providers.validation import SPORTS
        sport=next((s for s,v in SPORTS.items() if v==payload.get('sport_key')),None)
        if sport not in ('NFL','NBA','NHL','MLB'):continue
        qs,_=normalize_props(store,m,sport,m['fetched_at']);snapshots[sport]+=1
        for q in qs:
            if utc(q['captured_at'])>=utc(q['event_start']):continue
            counts[sport]+=1;distinct.add((sport,q['odds_event_id'],q['player_name'],q['market'],q['line'],q['book'],q['quote_timestamp'],q['over_odds'],q['under_odds']))
    return dict(historical_provider_snapshots=len(historical),historical_snapshots=historical,
        historical_price_backtest_qualified_rows=0,prospective_paired_offer_snapshots=dict(counts),prop_payload_snapshots=dict(snapshots),
        distinct_timestamped_paired_offers=len(distinct),
        distinction='Recorded pregame quote observations are real archive data, not proof of settlement terms, player identity or a qualified historical backtest')


def publication_base(root):
    """Read the last committed local generation while new feeds are being built.

    Consumers keep read_card's strict mixed-generation rejection. The publisher
    can resume from hash-checked immutable snapshots after a partial write.
    """
    from .product import read_card
    root=Path(root)
    try:return read_card(root)
    except ValueError as error:
        if str(error)!='PUBLICATION_IN_PROGRESS_OR_HASH_MISMATCH':raise
    summary=json.loads((root/'outputs/last_update.json').read_text())
    generation=summary.get('publication_generation','')
    if len(generation)!=64 or any(c not in '0123456789abcdef' for c in generation):raise ValueError('INVALID_GENERATION')
    expected=dict(summary['feed_hashes'])
    if summary.get('local_comparison_hash'):expected['comparison_markets.json']=summary['local_comparison_hash']
    values={}
    for name,h in expected.items():
        if Path(name).name!=name:raise ValueError('INVALID_FEED_PATH')
        value=json.loads((root/'data/snapshots'/(generation+'-'+name)).read_text())
        if digest(value)!=h:raise ValueError('PUBLICATION_SNAPSHOT_HASH_MISMATCH')
        values[name]=value
    return summary,values


def publish(root, report):
    """Publish new version alongside existing models without changing dashboard code."""
    from .product import read_card,card_lock
    root=Path(root);out=root/'outputs';data=root/'data';at=datetime.now(timezone.utc).isoformat()
    with card_lock(data):
        summary,values=publication_base(root);local=values.pop('comparison_markets.json',[])
        predictions=[f for f in values['latest_predictions.json'] if f.get('model_version')!=VERSION and utc(f['event_start'])>utc(at)]
        # Reconcile preserved CFB forecast output (including newly frozen games).
        predictions=[f for f in predictions if f.get('sport')!='CFB']
        predictions += [dict(f,sport='CFB',market='game_margin',decision='PASS',phase1_eligible=False) for f in json.loads((out/'cfb_score_research_predictions.json').read_text())['predictions'] if utc(f['event_start'])>utc(at)]
        models=[m for m in values['model_status.json'] if m.get('model_version')!=VERSION]
        passes=[];research=[]
        for sport in ('NFL','NBA','NHL','MLB'):
            future=json.loads((out/(sport.lower()+'_challenger_prospective.json')).read_text())
            predictions += [dict(f,decision='PASS',phase1_eligible=False) for f in future['predictions'] if utc(f['event_start'])>utc(at)]
            for market,v in report['sports'][sport]['markets'].items():
                models.append(dict(sport=sport,market=market,model_version=VERSION,status='UNVALIDATED',
                    real_training_sample=v['supervised_pregame_examples_after'],real_evaluation_sample=v['evaluation']['n'],
                    evaluation=v['evaluation'],research_admission=v['research_admission'],betting_validated=False,
                    blocker='PROSPECTIVE_CALIBRATION_PRICE_ROLE_AND_SETTLEMENT_PENDING',recommendations_enabled=False))
            for c in future['comparisons']:
                fresh=utc(at)<utc(c['event_start']) and (utc(at)-utc(c['quote_timestamp'])).total_seconds()<=180
                reasons=set(c['pass_reasons'])
                if not fresh:reasons.add('STALE_PRICE')
                item={k:c.get(k) for k in ('comparison_hash','forecast_hash','sport','game','event_start','player_name','market','selection','line','book','odds','raw_model_outcome_mass','conditional_model_ev','raw_fair_decimal_odds','zero_ev_decimal_threshold','quote_timestamp','model_version','simulation_interval_10_50_90')}
                item.update(decision='PASS',pass_reasons=sorted(reasons),current_price_fresh=fresh,publication_at=at,
                    quote_age_seconds=(utc(at)-utc(c['quote_timestamp'])).total_seconds(),
                    calibrated_probability=None,p_low=None,conservative_ev=None,conservative_price_threshold=None,stake=None)
                passes.append(item)
                if c['research_rank_eligible'] and fresh:research.append(item)
        values['latest_predictions.json']=predictions;values['model_status.json']=models;values['latest_edges.json']=[]
        values['p0_measured_results.json']=report
        values['p0_research_card.json']=dict(generated_at=at,entries=research,recommendations_enabled=False,label='RAW RESEARCH ESTIMATES; NO APPROVED WAGERS')
        values['p0_passes.json']=dict(generated_at=at,decisions=passes)
        for name in ('p0_market_refresh.json','prospective_market_evidence.json','p0_preservation_audit.json'):
            if (out/name).exists():values[name]=json.loads((out/name).read_text())
        values['latest_passes.json']=[p for p in values['latest_passes.json'] if p.get('model_version')!=VERSION]+passes
        provider=values['provider_status.json']
        provider['p0_current_verification']=json.loads((data/'evaluations/p0-provider-check.json').read_text())
        provider['p0_scoped_cfbd_refresh']=json.loads((data/'evaluations/p0-cfbd-scoped-refresh.json').read_text())
        provider['p0_quarantine']=json.loads((data/'evaluations/p0-cfbd-schema-quarantine.json').read_text())
        provider['p0_historical_access']=report['historical_access']
        access=json.loads((data/'evaluations/prop-price-access.json').read_text())
        provider['priority_prop_refresh']={r['sport']:r.get('latest_attempt') for r in access['sports']}
        provider['p0_current_prop_coverage']={r['sport']:{k:r.get(k) for k in ('paired_offers','books','event')} for r in access['sports']}
        provider['current_availability']=report.get('current_market_status',{})
        from .providers.quota import QuotaLedger
        quota=QuotaLedger(data/'quota.sqlite').summary()
        provider['odds_api']['quota_metadata'].update({'x-requests-remaining':quota['requests_remaining'],'x-requests-used':quota['provider_requests_used']})
        summary.update(generated_at=at,checkpoint_at=at,current_task='P0_HISTORICAL_CHALLENGER_EXECUTED',
            real_predictions_published=len(predictions),new_challenger_predictions=report['new_version_frozen_predictions'],
            models_validated=0,qualified_edges=0,simulations_completed=report['marginal_simulations'],simulation_draws=report['simulation_draws'],
            simulation_scope='Current P0 marginal runs: challenger prop forecasts plus preserved CFB forecasts; not joint game/parlay simulations',
            next_task='Resolve MLB postponed schedule and book rules; collect confirmed roles and pre-start closing snapshots, settle frozen cohorts; no additional simulations',
            p0_measured_report='p0_measured_results.json',github_push_status='PENDING_P0_CHECKPOINT',sports_updated=['NFL','NBA','NHL','MLB','CFB'])
        if report.get('current_market_status'):
            summary.update(current_task='P0_FRESH_PRICE_IDENTITY_AND_SETTLEMENT',current_price_age_checked_at=at,
                fresh_priced_research_comparisons=sum(c['current_price_fresh'] and c['raw_model_outcome_mass'] is not None for c in passes),
                additional_forecasts_this_refresh=0,additional_simulation_draws_this_refresh=0)
        generation=digest(dict(at=at,values=values));summary.update(publication_generation=generation,feed_hashes={n:digest(v) for n,v in values.items()},local_comparison_hash=digest(local))
        atomic_json(data/'snapshots'/(generation+'-comparison_markets.json'),local)
        for name,value in values.items():atomic_json(data/'snapshots'/(generation+'-'+name),value);atomic_json(out/name,value)
        atomic_json(out/'last_update.json',summary);read_card(root)
    state=json.loads((root/'TASK_STATE.json').read_text());state.update(updated_at=at,current_task=summary['current_task'],next_task=summary['next_task'])
    state['p0_measured_delivery']=dict(status='IN_PROGRESS',completed_engineering=['history expansion','fixed causal ridge challenger','chronological evaluation','frozen new-version forecasts','marginal simulation verification','same-sample comparisons','NFL model/history ablation'],
        report='reports/P0_MEASURED_RESULTS.md',new_version_frozen_predictions=report['new_version_frozen_predictions'],
        real_sample_size={s:(v.get('after_coverage',{}).get('unique_player_games') or v.get('after_completed_games')) for s,v in report['sports'].items()},
        synthetic_sample_size=0,blocker='Historical odds 401, source-revision timing, schedule conflicts, roles, settlement rules, prospective outcomes/calibration',next_action=summary['next_task'])
    aliases={'SOG':'shots_on_goal','pitcher_K':'pitcher_strikeouts','passing':'passing_yards','receiving':'receiving_yards','rushing':'rushing_yards'}
    for sport in ('NFL','NBA','NHL','MLB'):
        for name,item in state['categories'][sport].items():
            market=aliases.get(name,name);v=report['sports'][sport]['markets'].get(market)
            if v:
                item.update(status='IN_PROGRESS',real_sample_size=v['evaluation']['n'],synthetic_sample_size=0,
                    model_version=VERSION,blocker='PROSPECTIVE_BETTING_VALIDATION_PENDING',next_action=summary['next_task'])
                item['files']=sorted(set(item.get('files',[])+['src/ap_evsims/prop_challenger.py','outputs/'+sport.lower()+'_challenger_status.json']))
    atomic_json(root/'TASK_STATE.json',state)
    text=(root/'PHASE2_PROGRESS.md').read_text(encoding='utf-8')+'\n\nP0 checkpoint '+at+': see reports/P0_MEASURED_RESULTS.md and outputs/p0_market_refresh.json. Existing forecasts and simulation records retained. No CORE approval.\n'
    atomic_text(root/'PHASE2_PROGRESS.md',text)
    for name in ('MORNING_CARD.md','LUNCH_CARD.md','EVENING_CARD.md'):
        atomic_text(root/'reports'/name,'# AP EV/SIMS research card\n\nGenerated UTC: '+at+'\n\nNo approved wagers. See P0_MEASURED_RESULTS.md for executed forecasts and measured historical evidence, and outputs/p0_research_card.json for exact-price conditional research. Quotes have a 180-second execution lifetime; current roles, book rules, calibration and prospective evidence remain gating requirements.\n')


def build(root,nfl_control=False):
    root=Path(root);store=ResearchStore(root/'data');out=root/'outputs';at=datetime.now(timezone.utc).isoformat()
    before=json.loads((store.root/'evaluations/p0-before-bd4a8e5.json').read_text());sports={};control={}
    for sport in ('NFL','NBA','NHL','MLB'):
        old=before['reports'][sport.lower()+'_prop_research_status.json'];new=json.loads((out/(sport.lower()+'_challenger_status.json')).read_text())
        future=json.loads((out/(sport.lower()+'_challenger_prospective.json')).read_text());comparisons={}
        for market,v in new['markets'].items():
            comparisons[market]=paired_comparison(table_rows(store.root,old['markets'][market]['evaluation_table']),table_rows(store.root,v['evaluation_table']))
        sports[sport]=dict(before_coverage=old['coverage'],after_coverage=new['coverage'],
            markets={m:dict(training_outcomes_before=old['markets'][m]['training_n'],training_outcomes_after=v['outcome_n'],
                supervised_pregame_examples_after=v['training_n'],evaluation=v['evaluation'],paired_before_after=comparisons[m],
                research_admission=future['benchmarks'][m]['admission']) for m,v in new['markets'].items()},
            new_version_frozen_forecasts=future['frozen_forecasts'],price_comparison_records=len(future['comparisons']),
            identity_matched_comparisons=sum(c['price_identity_verified'] for c in future['comparisons']),
            fresh_at_comparison=sum(c['price_fresh'] and c['price_identity_verified'] for c in future['comparisons']),
            current_fresh_comparisons=sum(utc(at)<utc(c['event_start']) and (utc(at)-utc(c['quote_timestamp'])).total_seconds()<=180 and c['price_identity_verified'] for c in future['comparisons']),
            pass_reasons=dict(Counter(reason for c in future['comparisons'] for reason in c['pass_reasons'])),
            marginal_simulations=len(future['simulations']),simulation_draws=future['simulation_draws'],convergence_failures=future['convergence_failures'])
    if nfl_control:
        rows,_=normalize(root,'NFL')
        new=json.loads((out/'nfl_challenger_status.json').read_text())
        for m,v in new['markets'].items():
            _,rs,_=evaluate(rows,'NFL',m);table=store.write_table('nfl-'+m+'-v1-expanded-control',rs)
            control[m]=dict(old_algorithm_on_expanded_history=summarize(rs),evaluation_table=table,
                paired_algorithm_effect=paired_comparison(rs,table_rows(store.root,v['evaluation_table'])))
        atomic_json(out/'nfl_history_model_ablation.json',dict(generated_at=at,markets=control,
            scope='Fixed v1 versus v2 on identical expanded outcome history; no algorithm selected or tuned from this comparison'))
    cfb=json.loads((out/'cfb_score_research_status.json').read_text());oldcfb=before['reports']['cfb_score_research_status.json']
    cfbsims=[]
    for f in json.loads((out/'cfb_score_research_predictions.json').read_text())['predictions']:
        if utc(f['event_start'])<=utc(at):continue
        if digest({k:v for k,v in f.items() if k!='forecast_hash'})!=f['forecast_hash']:raise ValueError('CFB_FORECAST_HASH_MISMATCH')
        cfbsims.append(simulate(dict(f,sport='CFB',market='game_margin',projection={'distribution':f['margin_distribution']}),20000))
    atomic_json(out/'cfb_preserved_model_simulations.json',dict(generated_at=at,model_version=cfb['model_version'],simulations=cfbsims,
        scope='Existing CFB model/forecasts preserved; newly executed marginal Monte Carlo draws only'))
    sports['CFB']=dict(before_completed_games=oldcfb['real_source_coverage']['completed_scores'],after_completed_games=cfb['real_source_coverage']['completed_scores'],
        seasons=cfb['real_source_coverage']['seasons'],training_n=cfb['current_training_n'],evaluation=cfb['evaluation'],before_evaluation=oldcfb['evaluation'],
        current_frozen_forecasts=len(cfbsims),marginal_simulations=len(cfbsims),simulation_draws=len(cfbsims)*40000,
        convergence_failures=sum(not s['convergence_passed'] for s in cfbsims),model_version=cfb['model_version'])
    access=json.loads((store.root/'evaluations/p0-historical-access.json').read_text());prices=price_inventory(store)
    report=dict(generated_at=at,baseline_commit='bd4a8e5862e038c7ae77c71e50873f08dc234547',model_version=VERSION,sports=sports,prices=prices,
        historical_access=access,new_version_frozen_predictions=sum(sports[s]['new_version_frozen_forecasts'] for s in ('NFL','NBA','NHL','MLB')),
        marginal_simulations=sum(s['marginal_simulations'] for s in sports.values()),simulation_draws=sum(s['simulation_draws'] for s in sports.values()),
        convergence_failures=sum(s['convergence_failures'] for s in sports.values()),synthetic_performance_sample=0,
        prospective_settled=0,qualified_market_comparisons=0,validated_edges=0,core_enabled=False,reference_unit=22,
        hypothetical_roi=None,clv=None,max_drawdown=None,betting_probability_calibration=None,
        limitations=['Historical outcome revisions captured now are reconstruction, not timestamp-authentic historical features.',
        'Existing evaluation seasons were already inspected; all comparisons remain exploratory and multiply tested.',
        'DNP/role selection, traded-player histories, conditional-on-appearance modeling and sampled MLB cohorts limit generalization.',
        'Probability scores use fixed prior-mean diagnostic lines, not historical sportsbook prices.',
        'Intervals and Monte Carlo convergence are not uncertainty-qualified EV or proof of profitability.',
        'No shared-game joint simulation, verified book settlement terms or prospective price-relative performance yet.'])
    atomic_json(out/'p0_measured_results.json',report)
    lines=['# P0 measured forecasting delivery','',f'Generated UTC: {at}.','',
        'Completed execution, with real data. All CORE and cash recommendations remain disabled. Historical diagnostics are reconstructed and previously inspected; no prospective betting edge is established.',
        '', '| Sport | Before player-game observations | After | Athletes after | Seasons after |', '|---|---:|---:|---:|---|']
    for sport in ('NFL','NBA','NHL','MLB'):
        s=sports[sport];b=s['before_coverage'];a=s['after_coverage'];lines.append(f"| {sport} | {b['unique_player_games']:,} | {a['unique_player_games']:,} | {a['unique_athletes']} | {', '.join(a['seasons'])} |")
    lines+=['',f"CFB completed FBS-vs-FBS games: {sports['CFB']['before_completed_games']:,} → {sports['CFB']['after_completed_games']:,}. Model code/version preserved.",
        '', '## Identical-sample before / after MAE','', '| Sport / market | Paired outcomes | Previous model | Challenger | Current benchmark gate |','|---|---:|---:|---:|---|']
    for sport in ('NFL','NBA','NHL','MLB'):
        for m,s in sports[sport]['markets'].items():
            p=s['paired_before_after'];lines.append(f"| {sport} {m} | {p['common_sample_n']:,} | {p['before']['mae']:.4f} | {p['after']['mae']:.4f} | {s['research_admission']} |")
    lines+=['','## Current chronological evaluation versus recent-average baseline','',
        '| Sport / market | Train examples | Eval outcomes | MAE / baseline | RMSE / baseline | Brier / baseline | Outcome NLL / baseline |','|---|---:|---:|---|---|---|---|']
    for sport in ('NFL','NBA','NHL','MLB'):
        for m,s in sports[sport]['markets'].items():
            e=s['evaluation'];pairs=[' / '.join(f"{e[k]:.4f}" for k in (x,'baseline_'+x)) for x in ('mae','rmse','brier','nll')]
            lines.append(f"| {sport} {m} | {s['supervised_pregame_examples_after']:,} | {e['n']:,} | "+' | '.join(pairs)+' |')
    lines+=['','Brier/log loss above use a fixed pregame-history diagnostic line, not a bookmaker line. See JSON for CRPS, coverage, per-season metrics and week-block uncertainty. NFL history/model ablation separates data expansion from algorithm changes.',
        '',f"New challenger forecasts: {report['new_version_frozen_predictions']}. Marginal simulations executed: {report['marginal_simulations']}; total draws: {report['simulation_draws']:,}; sampling-convergence failures: {report['convergence_failures']}.",
        f"Historical endpoint HTTP {access['status']}; qualified historical price backtest rows: {prices['historical_price_backtest_qualified_rows']}. Real prospective paired-offer snapshots: {sum(prices['prospective_paired_offer_snapshots'].values()):,}.",
        '', '## Remaining blockers','']+[f'- {x}' for x in report['limitations']]+[
        '- NHL bookmaker/league starts differ by 10 minutes; MLB has a larger schedule conflict. No silent time remapping is allowed.',
        '- Official starters/goalies/roles and participation conditions are not fully verified. Quotes expire after 180 seconds.',
        '- Historical odds entitlement still returns 401. Prospective outcomes must elapse before calibration, CLV and ROI can be measured.',
        '- Full league-wide MLB coverage, opponent context, verified historical injuries, role-transition models, calibrated uncertainty and shared-game joint simulations remain unfinished.',
        '', '## Reproduce','', '```powershell', "$env:PYTHONPATH='src'",
        "& '.\\.venv\\Scripts\\python.exe' -m ap_evsims.history_expansion --root . --sport all",
        "& '.\\.venv\\Scripts\\python.exe' -m ap_evsims.prop_challenger --root . --sport all",
        "& '.\\.venv\\Scripts\\python.exe' -m ap_evsims.challenger_delivery --root . --sport all --draws 20000",
        "& '.\\.venv\\Scripts\\python.exe' -m ap_evsims.p0_results --root . --nfl-control", '```','']
    atomic_text(root/'reports/P0_MEASURED_RESULTS.md','\n'.join(lines));publish(root,report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--nfl-control',action='store_true');a=p.parse_args()
    r=build(a.root,a.nfl_control);print(json.dumps({k:v for k,v in r.items() if k not in ('sports','limitations')},indent=2))


if __name__=='__main__':main()
