"""Append-only pregame research updates; model/price/availability gates stay separate.

python -m ap_evsims.prop_market_research --root . [--refresh-prices]
Research rankings are conditional estimates, never cash-authorized selections.
"""
from collections import Counter,defaultdict
from datetime import datetime,timezone,timedelta,date
import hashlib,json,math
from pathlib import Path
import statistics
import numpy as np
from .integrity import digest,utc
from .identity import normalized_name
from .research_store import ResearchStore
from .prop_prices import normalize_props,collect_priority
from .prop_prospective import prop_mass,freeze_prop
from .prop_availability import capture
from .prop_research import summarize
from .display_pricing import outcome_ev
from .odds import american_to_implied
from .publication import atomic_json,atomic_text

VERSION='prospective-market-research-v1'
PRIORITY={'NFL':{'receptions','rushing_attempts','receiving_yards','passing_yards','rushing_yards'},
          'NBA':{'rebounds','assists'},'NHL':{'shots_on_goal','goalie_saves'},'MLB':{'hitter_hits','total_bases'}}


def benchmark_gate(e):
    if e.get('n',0)<100:return 'INSUFFICIENT_BENCHMARK_SAMPLE'
    keys=('mae','rmse','baseline_mae','baseline_rmse')
    if any(not isinstance(e.get(k),(int,float)) or not math.isfinite(e[k]) for k in keys):return 'INVALID_BENCHMARK_METRICS'
    if e['mae']>=e['baseline_mae'] or e['rmse']>=e['baseline_rmse']:return 'FAILED_SIMPLE_BASELINE'
    ci=e.get('paired_mae_difference_95_week_bootstrap')
    if not ci or len(ci)!=2 or not all(math.isfinite(v) for v in ci) or ci[0]>ci[1] or ci[1]>=0:return 'BENCHMARK_ADVANTAGE_INCONCLUSIVE'
    return 'RESEARCH_BENCHMARK_ADVANTAGE'


def verified_evaluations(root,sport):
    root=Path(root);data=root/'data';status=json.loads((root/'outputs'/(sport.lower()+'_prop_research_status.json')).read_text())
    result={}
    for market,v in status['markets'].items():
        p=(data/v['evaluation_table']['path']).resolve()
        if data.resolve() not in p.parents:raise ValueError('EVALUATION_PATH_ESCAPE')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=v['evaluation_table']['fingerprint']:raise ValueError('EVALUATION_HASH_MISMATCH')
        rows=[json.loads(line) for line in raw.splitlines()]
        if len(rows)!=v['evaluation_table']['n']:raise ValueError('EVALUATION_COUNT_MISMATCH')
        artifact=json.loads((data/'models'/(sport.lower()+'-'+market+'-'+v['artifact_hash']+'.json')).read_text())
        if digest(artifact)!=v['artifact_hash'] or (artifact['sport'],artifact['market'])!=(sport,market):raise ValueError('ARTIFACT_HASH_MISMATCH')
        e=summarize(rows)
        result[market]=dict(sport=sport,market=market,model_version=status['model_version'],artifact_hash=v['artifact_hash'],
            dataset_fingerprint=v['evaluation_table']['fingerprint'],training_n=v['training_n'],evaluation=e,admission=benchmark_gate(e),
            betting_validated=False,calibrated_probability=None,p_low=None,
            selection_caveat='Existing evaluation informed this research shortlist; new prospective outcomes are required. Multiple comparisons are not adjusted.')
    return result


def make_baseline_references(root,forecasts,evaluations):
    """Retire worse NFL estimates from rankings; expose the predefined benchmark.

    Reference forecasts are not a newly discovered edge and cannot outperform
    themselves. They receive their own version, artifacts and prospective cohort.
    """
    root=Path(root);store=ResearchStore(root/'data');status=json.loads((root/'outputs/nfl_prop_research_status.json').read_text())
    by_market={};at=datetime.now(timezone.utc).isoformat();references=[];new_count=0
    for market in PRIORITY['NFL']:
        v=status['markets'][market];table=v['evaluation_table'];raw=(store.root/table['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=table['fingerprint']:raise ValueError('EVALUATION_HASH_MISMATCH')
        rows=[json.loads(line) for line in raw.splitlines()]
        model=json.loads((store.root/'models'/('nfl-'+market+'-'+v['artifact_hash']+'.json')).read_text())
        if digest(model)!=v['artifact_hash']:raise ValueError('ARTIFACT_HASH_MISMATCH')
        residuals=[r['outcome']-r['baseline'] for r in rows][-1000:]
        body=dict(version='player-recent-average-reference-v1',sport='NFL',market=market,parent_artifact=v['artifact_hash'],
            source_capture=model['latest_source_capture'],evaluation_fingerprint=table['fingerprint'],residuals=residuals,
            method='predefined last-ten observed-appearance mean; prior OOF baseline residuals; reference only',recommendations_enabled=False)
        h=digest(body);ResearchStore._immutable(store.root/'models'/('nfl-reference-'+h+'.json'),json.dumps(body,sort_keys=True,indent=2).encode())
        by_market[market]=(model,residuals,h)
    for original in forecasts:
        market=original['market'];model,residuals,h=by_market[market]
        history=model['player_histories'].get(original['player_id'],[])[-10:]
        if len(history)<5 or len(residuals)<80 or utc(at)>=utc(original['event_start']):continue
        if any(date.fromisoformat(r['played_on'])>utc(at).date()-timedelta(days=2) for r in history):raise ValueError('REFERENCE_TARGET_LEAKAGE')
        mean=statistics.mean(r['outcome'] for r in history)
        samples=[round(mean+e) for e in residuals]
        if 'yards' not in market:samples=[max(0,x) for x in samples]
        c=Counter(samples);pmf={str(k):n/len(samples) for k,n in sorted(c.items())}
        record={k:v for k,v in original.items() if k!='forecast_hash'}
        record.update(generated_at=at,model_version='player-recent-average-reference-v1',artifact_hash=h,
            latest_source_capture=max(original['latest_source_capture'],model['latest_source_capture']),training_source_hashes=model['source_hashes'],
            reference_parent_forecast=original['forecast_hash'],reference_only=True,priced_markets=[],
            projection=dict(original['projection'],projection=mean,baseline=mean,distribution=pmf,method='PREDEFINED_RECENT_AVERAGE_REFERENCE'),
            pass_reasons=['REFERENCE_BASELINE_NOT_AN_EDGE','PROSPECTIVE_CALIBRATION_PENDING','PARTICIPATION_NOT_CONFIRMED'],
            benchmark_admission='REFERENCE_ONLY',model_training_finished_at=at)
        frozen,new=freeze_prop(store,record);references.append(frozen);new_count+=new
    report=dict(generated_at=at,new_frozen=new_count,reference_forecasts=len(references),predictions=references,
        correction='Old NFL opportunity models rejected from ranked research after losing MAE to the predefined benchmark.',
        retrospective_reference_metrics={m:dict(n=e['evaluation']['n'],mae=e['evaluation']['baseline_mae'],rmse=e['evaluation']['baseline_rmse'],
            old_model_mae=e['evaluation']['mae'],admission=e['admission']) for m,e in evaluations.items()},
        prospective_settled=0,recommendations_enabled=False)
    atomic_json(root/'outputs/nfl_baseline_reference.json',report);return report


def comparison(f,q,a,e,at,peers=(),*,identity_store=None):
    if f['market']!=q['market'] or f['sport']!=q['sport']:raise ValueError('MARKET_IDENTITY_MISMATCH')
    mapping=f['event_mapping'];reasons=[]
    if q['odds_event_id']!=mapping['odds_event_id']:raise ValueError('EVENT_IDENTITY_MISMATCH')
    if q['period']!='full_game':raise ValueError('PERIOD_MISMATCH')
    if a['player_id']!=f['player_id'] or a['team_id']!=f['team_id']:raise ValueError('PLAYER_IDENTITY_MISMATCH')
    if a['event_id']!=f['event_id'] or a['sport']!=f['sport'] or utc(a['event_start'])!=utc(f['event_start']):raise ValueError('FORECAST_SCHEDULE_CHANGED')
    if f['artifact_hash']!=e['artifact_hash']:raise ValueError('MODEL_EVALUATION_MISMATCH')
    if not utc(f['generated_at'])<=utc(at)<min(utc(f['event_start']),utc(q['event_start'])):raise ValueError('PREGAME_COMPARISON_REQUIRED')
    if max(utc(f['latest_source_capture']),utc(q['captured_at']),utc(a['available_at']))>utc(at):raise ValueError('LOOKAHEAD_RISK')
    identity=utc(f['event_start'])==utc(q['event_start']) and mapping['home_team']==q['home_team'] and mapping['away_team']==q['away_team']
    resolution=None
    if not identity and identity_store is not None and f['sport']=='NHL':
        from .event_resolution import resolve_nhl
        try:resolution=resolve_nhl(identity_store,mapping,q,a,at);identity=bool(resolution)
        except (ValueError,KeyError):pass
    if not identity:reasons.append('BOOK_CANONICAL_START_MISMATCH')
    age=(utc(at)-utc(q['quote_timestamp'])).total_seconds()
    if age<0 or utc(q['quote_timestamp'])>utc(q['captured_at']):raise ValueError('LOOKAHEAD_RISK')
    if age>180:reasons.append('STALE_PRICE')
    reasons+=a['reasons']
    if e['admission']!='RESEARCH_BENCHMARK_ADVANTAGE':reasons.append(e['admission'])
    reasons+=['PROSPECTIVE_CALIBRATION_PENDING','BOOK_SETTLEMENT_RULE_UNVERIFIED']
    if f['projection'].get('last_team_id')!=a['team_id']:reasons.append('TEAM_CHANGE_ROLE_UNVERIFIED')
    last=f['projection'].get('last_observed_date')
    if last and (utc(at).date()-date.fromisoformat(last)).days>60:reasons.append('LONG_LAYOFF_ROLE_UNVERIFIED')
    pmf=f['projection']['distribution'];keys=np.array([int(k) for k in pmf]);prob=np.array(list(pmf.values()))
    ix=np.argsort(keys);keys=keys[ix];prob=prob[ix]
    interval=[int(keys[min(np.searchsorted(np.cumsum(prob),p),len(keys)-1)]) for p in (.1,.5,.9)]
    out=[]
    for side in ('Over','Under'):
        mass=prop_mass(pmf,q['line'],side) if identity else None
        odds=q['over_odds' if side=='Over' else 'under_odds'];fair=q['over_no_vig'] if side=='Over' else 1-q['over_no_vig']
        # Cross-book numbers are descriptive only until common payout terms are proved.
        matches=[p for p in peers if p['book']!=q['book'] and p['market']==q['market'] and p['line']==q['line'] and p['period']==q['period']
                 and p['odds_event_id']==q['odds_event_id'] and p['event_start']==q['event_start']
                 and normalized_name(p['player_name'])==normalized_name(q['player_name']) and abs((utc(p['quote_timestamp'])-utc(q['quote_timestamp'])).total_seconds())<=60]
        peer_books={p['book']:p for p in matches}
        ev=outcome_ev(mass['p_win'],mass['p_loss'],mass['p_push'],odds) if mass else None
        candidate=dict(sport=f['sport'],event_id=f['event_id'],event_start=f['event_start'],game=mapping['away_team']+' @ '+mapping['home_team'],
            market=f['market'],player_id=f['player_id'],player_name=f['player_name'],team_id=f['team_id'],selection=side,line=q['line'],book=q['book'],odds=odds,
            break_even_probability=american_to_implied(odds),market_no_vig=fair,market_probability_basis=q['probability_basis'],
            raw_model_outcome_mass=mass,conditional_model_ev=ev,ev_assumptions='conditional on appearance, projected workload, standard settled payout; ignores void/rule differences',
            raw_probability_conditional_on_non_push=mass['p_win']/(1-mass['p_push']) if mass and mass['p_push']<1 else None,
            calibrated_probability=None,p_low=None,qualified_ev=None,descriptive_other_books=[dict(book=p['book'],line=p['line'],
                odds=p['over_odds' if side=='Over' else 'under_odds'],quote_timestamp=p['quote_timestamp']) for p in peer_books.values()],
            projected_opportunity=f['projection']['projected_opportunity'],model_mean=f['projection']['projection'],simulation_interval_10_50_90=interval,
            simulation_basis='exact quantiles of frozen empirical residual distribution; not confidence bounds',
            model_version=f['model_version'],artifact_hash=f['artifact_hash'],benchmark=e,
            forecast_hash=f['forecast_hash'],forecast_generated_at=f['generated_at'],quote_id=q['quote_id'],quote_timestamp=q['quote_timestamp'],
            quote_captured_at=q['captured_at'],quote_age_seconds=age,quote_snapshot=q['snapshot_id'],quote_payload_hash=q['payload_hash'],
            availability=a,decision_timestamp=at,price_identity_verified=identity,price_fresh=age<=180,
            event_identity_resolution=resolution,provider_event_start=q['event_start'],
            research_status='RESEARCH_ESTIMATE',decision='PASS',pass_reasons=sorted(set(reasons)),recommendations_enabled=False,
            reference_unit=22,stake=None)
        candidate['research_rank_eligible']=bool(identity and ev is not None and ev>0 and e['admission']=='RESEARCH_BENCHMARK_ADVANTAGE'
            and a['availability_state']!='REPORTED_UNAVAILABLE' and not set(reasons)&{'INJURY_TIMESTAMP_INVALID','MODEL_COMPETITION_DOMAIN_MISMATCH','TEAM_CHANGE_ROLE_UNVERIFIED'})
        out.append(candidate)
    return out


def freeze_comparison(store,body,parent=None):
    if body['decision']!='PASS' or body['recommendations_enabled'] or body.get('p_low') is not None or body.get('calibrated_probability') is not None:
        raise ValueError('RESEARCH_AUTHORITY_ESCALATION')
    at=utc(body['decision_timestamp'])
    if max(utc(body['forecast_generated_at']),utc(body['quote_captured_at']),utc(body['availability']['available_at']))>at or at>=utc(body['event_start']):
        raise ValueError('PREGAME_FREEZE_REQUIRED')
    record=dict(body,comparison_version=VERSION,parent_comparison_hash=parent);record['comparison_hash']=digest(record)
    folder=store.root/'predictions/market-research';folder.mkdir(exist_ok=True)
    ResearchStore._immutable(folder/(record['comparison_hash']+'.json'),json.dumps(record,sort_keys=True,indent=2,allow_nan=False).encode())
    return record


def publish_feeds(root,report):
    """Reconcile research feeds without editing or rebuilding dashboard views."""
    from .product import read_card,card_lock
    from .providers.quota import QuotaLedger
    root=Path(root);out=root/'outputs';data=root/'data';at=report['generated_at']
    with card_lock(data):
        summary,values=read_card(root);local=values.pop('comparison_markets.json',[])
        primary=[]
        for sport in ('NFL','NBA','NHL','MLB','CFB'):
            p=out/('cfb_score_research_predictions.json' if sport=='CFB' else sport.lower()+'_prop_prospective.json')
            for f in json.loads(p.read_text())['predictions']:
                if utc(f['event_start'])>utc(at):primary.append(dict(f,sport=sport,market=f.get('market','game_margin'),publication_at=at,
                    status='UNVALIDATED_RESEARCH',decision='PASS',phase1_eligible=False,stake=None))
        values['latest_predictions.json']=primary;values['latest_edges.json']=[]
        names={'Receptions':'receptions','Receiving yards':'receiving_yards','Passing yards':'passing_yards','Rushing attempts':'rushing_attempts',
            'Rushing yards':'rushing_yards','Points':'points','Rebounds':'rebounds','Assists':'assists','Threes':'threes','Shots on goal':'shots_on_goal',
            'Goalie saves':'goalie_saves','Pitcher strikeouts':'pitcher_strikeouts','Pitcher outs':'pitcher_outs','Hits allowed':'hits_allowed','Hitter hits':'hitter_hits','Total bases':'total_bases'}
        for item in values['model_status.json']:
            benchmark=report['benchmark_reports'].get(item['sport'],{}).get(names.get(item['market']))
            if benchmark:item.update(real_training_sample=benchmark['training_n'],real_evaluation_sample=benchmark['evaluation']['n'],
                evaluation=benchmark['evaluation'],artifact_hash=benchmark['artifact_hash'],research_admission=benchmark['admission'],
                blocker=benchmark['admission'] if benchmark['admission']!='RESEARCH_BENCHMARK_ADVANTAGE' else 'PROSPECTIVE_CALIBRATION_AND_EXECUTABLE_PRICE_PENDING')
        for name in ('early_watchlist.json','market_research_status.json','market_research_passes.json','prospective_price_comparisons.json'):
            values[name]=json.loads((out/name).read_text())
        values['provider_status.json']['priority_prop_refresh']={s:r.get('price_refresh') for s,r in report['sports'].items()}
        values['provider_status.json']['current_availability']={s:dict(reported_injuries=r.get('injury_reports'),confirmed_roles=r.get('confirmed_roles'),
            identity_reasons=r.get('event_identity_reasons')) for s,r in report['sports'].items()}
        quota=QuotaLedger(data/'quota.sqlite').summary()
        values['provider_status.json']['odds_api']['quota_metadata'].update({'x-requests-remaining':quota['requests_remaining'],'x-requests-used':quota['provider_requests_used']})
        generation=digest(dict(at=at,values=values))
        summary.update(generated_at=at,checkpoint_at=at,current_task='PROSPECTIVE_PRICE_RESEARCH',next_task='Refresh prices after quota reset, verify roles, settle each frozen model cohort',
            real_predictions_published=len(primary),nfl_reference_predictions=json.loads((out/'nfl_baseline_reference.json').read_text())['reference_forecasts'],ranked_research_candidates=report['ranked_research_candidates'],
            fresh_ranked_candidates=report['fresh_ranked_candidates'],qualified_edges=0,models_validated=0,
            research_status='EARLY_WATCHLIST_WITH_SEPARATE_PASS_DECISIONS',market_research_report='market_research_status.json',
            publication_generation=generation,feed_hashes={n:digest(v) for n,v in values.items()},local_comparison_hash=digest(local))
        # Preserve timestamps on prior Monte Carlo results. Newly frozen MLB
        # forecasts have exact PMFs; no extra draws are claimed by this command.
        summary['simulation_scope']='Previous simulation_execution.json applies to its recorded forecast hashes only; new forecasts are not claimed as newly Monte Carlo simulated.'
        atomic_json(data/'snapshots'/(generation+'-comparison_markets.json'),local)
        for name,value in values.items():atomic_json(data/'snapshots'/(generation+'-'+name),value);atomic_json(out/name,value)
        atomic_json(out/'last_update.json',summary);read_card(root)


def run(root,refresh_prices=False):
    root=Path(root);store=ResearchStore(root/'data')
    if refresh_prices:collect_priority(root)
    access=json.loads((store.root/'evaluations/prop-price-access.json').read_text());records=[];rejections=[];sports={};benchmark_reports={}
    prior={};folder=store.root/'predictions/market-research'
    key=lambda r:(r['sport'],r['event_id'],r['player_id'],r['market'],r['book'],r['selection'])
    for p in sorted(folder.glob('*.json')):
        v=json.loads(p.read_text())
        if digest({k:x for k,x in v.items() if k!='comparison_hash'})!=v['comparison_hash']:raise ValueError('COMPARISON_HASH_MISMATCH')
        if key(v) not in prior or utc(v['decision_timestamp'])>utc(prior[key(v)]['decision_timestamp']):prior[key(v)]=v
    for sport in PRIORITY:
        try:
            benchmarks=verified_evaluations(root,sport);benchmark_reports[sport]=benchmarks;availability=capture(root,sport)
            forecasts=json.loads((root/'outputs'/(sport.lower()+'_prop_prospective.json')).read_text())['predictions']
            for f in forecasts:
                if digest({k:v for k,v in f.items() if k!='forecast_hash'})!=f['forecast_hash']:raise ValueError('FORECAST_HASH_MISMATCH')
            if sport=='NFL':make_baseline_references(root,forecasts,benchmarks)
            access_sport=next(r for r in access['sports'] if r['sport']==sport);record=access_sport.get('record',{})
            at=datetime.now(timezone.utc).isoformat()
            qs,rejected=normalize_props(store,store.manifest(record['snapshot_id']),sport,at) if record.get('status')==200 else ([],{'NO_CAPTURED_PROP_PRICE':1})
            aliases=defaultdict(set)
            for p in availability['identities']:
                for name in p['aliases']:
                    if name:aliases[normalized_name(name)].add(p['player_id'])
            players={p['player_id']:p for p in availability['records']};forecast_by={(f['player_id'],f['market']):f for f in forecasts}
            count=0
            for q in qs:
                if q['book'] not in ('draftkings','fanduel') or q['market'] not in PRIORITY[sport]:continue
                ids=aliases.get(normalized_name(q['player_name']),set())
                if len(ids)!=1:
                    rejections.append(dict(sport=sport,quote_id=q['quote_id'],reason='PLAYER_IDENTITY_AMBIGUOUS_OR_MISSING'));continue
                player_id=next(iter(ids));f=forecast_by.get((player_id,q['market']))
                if not f:
                    rejections.append(dict(sport=sport,quote_id=q['quote_id'],player_id=player_id,market=q['market'],reason='NO_TRAINED_PLAYER_FORECAST'));continue
                try:
                    for c in comparison(f,q,players[player_id],benchmarks[q['market']],at,qs):
                        c['availability_snapshot']=availability['snapshot_hash']
                        saved=freeze_comparison(store,c,(prior.get(key(c)) or {}).get('comparison_hash'));records.append(saved);count+=1
                except ValueError as error:rejections.append(dict(sport=sport,quote_id=q['quote_id'],reason=str(error)))
            sports[sport]=dict(status='RESEARCH_CAPTURED',comparisons=count,paired_quotes=len(qs),price_refresh=access_sport.get('latest_attempt'),
                injury_reports=sum(bool(p['injury_evidence']) for p in availability['records']),confirmed_roles=sum(p['role_confirmed'] for p in availability['records']),
                event_identity_reasons=availability['event_identity_reasons'],normalization_rejections=rejected,
                benchmark_admissions={m:e['admission'] for m,e in benchmarks.items()})
        except (OSError,ValueError,KeyError,TypeError) as error:
            # Fail one sport independently. No raw exception text or request URL
            # is persisted; programmer/data failures remain explicit blockers.
            sports[sport]=dict(status='RESEARCH_BLOCKED',reason=type(error).__name__)
    at=datetime.now(timezone.utc).isoformat()
    ranked=sorted([r for r in records if r['research_rank_eligible']],key=lambda r:(not r['price_fresh'],-r['conditional_model_ev'],r['comparison_hash']))
    # One candidate per player/market/side, with current-price priority. Do not
    # present five books on the same side as five independent opportunities.
    seen=set();shortlist=[]
    for r in ranked:
        k=(r['sport'],r['event_id'],r['player_id'],r['market'],r['selection'])
        if k not in seen:shortlist.append(r);seen.add(k)
    report=dict(generated_at=at,sports=sports,comparison_count=len(records),ranked_research_candidates=len(shortlist),
        fresh_ranked_candidates=sum(r['price_fresh'] for r in shortlist),actionable_betting_recommendations=0,validated_edges=0,
        prospective_settled=0,model_calibration='NOT_DEMONSTRATED',ranking_basis='Conditional raw model EV among models with historical benchmark advantage; not betting confidence',
        cfb_model='PRESERVED_UNCHANGED',recommendations_enabled=False,benchmark_reports=benchmark_reports,rejections=rejections)
    atomic_json(root/'outputs/market_research_status.json',report)
    atomic_json(root/'outputs/early_watchlist.json',dict(generated_at=at,label='EARLY RESEARCH WATCHLIST',entries=shortlist,
        interpretation='Prices and injury information can change. Raw model estimates have not demonstrated a prospective betting edge.',recommendations_enabled=False))
    atomic_json(root/'outputs/prospective_price_comparisons.json',dict(generated_at=at,comparisons=records))
    atomic_json(root/'outputs/market_research_passes.json',dict(generated_at=at,decisions=[dict(comparison_hash=r['comparison_hash'],sport=r['sport'],
        player_id=r['player_id'],market=r['market'],selection=r['selection'],decision='PASS',reasons=r['pass_reasons']) for r in records],unmatched=rejections))
    lines=['# Prospective market research','',f'Generated UTC: {at}.','',
        'Early watchlist entries are conditional research estimates, not locked plays. Calibration and prospective price-relative performance are not established. All betting decisions are PASS.',
        f'{len(records)} side/line/book comparisons; {len(shortlist)} distinct positive conditional-EV research entries; {sum(r["price_fresh"] for r in shortlist)} currently fresh ranked prices.',
        'Both sides are evaluated. Integer lines preserve push mass. No p_low or calibrated probability is manufactured.',
        'Original forecasts are immutable. Each price/news update is separately frozen before kickoff and links to the prior comparison.',
        '', '| Sport | Comparisons | Paired quotes | Reported injuries | Confirmed roles |', '|---|---:|---:|---:|---:|']
    for s,r in sports.items():lines.append(f"| {s} | {r.get('comparisons',0)} | {r.get('paired_quotes',0)} | {r.get('injury_reports',0)} | {r.get('confirmed_roles',0)} |")
    lines+=['','NFL correction: models that lost to their predefined recent-average benchmark are rejected from rankings. New baseline-reference forecasts form a separate prospective cohort; this is not a claim of a newly validated NFL model.',
        'NBA rebounds/assists and NHL shots/saves retain historical benchmark advantages. MLB hitter-hit/total-bases evidence is recomputed from the current expanded cohort; inspect benchmark_reports for counts and confidence intervals. Current-roster survivor selection, multiple comparisons, historical revisions and appearance-only selection remain limitations.',
        'NBA/NFL injury sources are ESPN aggregations, not full official clearance. NHL league goalie leaders are not starter confirmations. MLB requires a full official batting order to mark a listed lineup. No projected minutes or ice time is labeled confirmed.',
        'NHL/MLB bookmaker start conflicts block probability/EV association with those prices. Stale prices remain historical diagnostics and cannot authorize execution.',
        'CFB score-model code and forecasts are preserved. See execution reports for its separate model evidence.','',
        'Machine-readable files: early_watchlist.json, prospective_price_comparisons.json, market_research_passes.json, market_research_status.json, nfl_baseline_reference.json and per-sport availability files.']
    atomic_text(root/'reports/PROSPECTIVE_MARKET_RESEARCH.md','\n'.join(lines)+'\n')
    if (root/'outputs/last_update.json').exists():publish_feeds(root,report)
    return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--refresh-prices',action='store_true');args=p.parse_args()
    result=run(args.root,args.refresh_prices);print(json.dumps({k:v for k,v in result.items() if k not in ('benchmark_reports','rejections')},indent=2))
