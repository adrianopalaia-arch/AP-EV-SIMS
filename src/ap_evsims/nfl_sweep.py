"""Canonical full-slate NFL research. No betting authorization or wager placement.

python -m ap_evsims.nfl_sweep --date 2026-10-18 --collect --daily-cap 96
"""
import argparse,json,math,statistics
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter,defaultdict
from .integrity import digest,utc
from .publication import atomic_json,atomic_text
from .research_store import ResearchStore
from .product import card_lock
from .nfl_schedule import discover,match_odds
from .nfl_game_model import train,freeze,margin_mass
from .prop_prices import collect_priority,event_price_records,normalize_props
from .prop_availability import capture
from .challenger_delivery import run as prop_run
from .prop_market_research import comparison,freeze_comparison
from .identity import normalized_name
from .odds import american_to_implied,devig_two_way
from .display_pricing import outcome_ev

def now():return datetime.now(timezone.utc).isoformat()

def price_age(observed,captured,at,kickoff):
    if not utc(observed)<=utc(captured)<=utc(at)<utc(kickoff):raise ValueError('INVALID_PREGAME_QUOTE_ORDER')
    age=(utc(at)-utc(observed)).total_seconds()
    return age,age<=180

def featured_quotes(store,access,game,forecast,at,model_status):
    r=access.get('featured') or {};out=[];rejected=[]
    if r.get('status')!=200:return out,rejected
    manifest=store.manifest(r['snapshot_id']);events=store.payload(manifest)
    event,reason=match_odds(game,events)
    if event is None:return [],[dict(event_id=game['event_id'],reason=reason)]
    for book in event.get('bookmakers',[]):
        for market in book.get('markets',[]):
            kind=market['key'];sides=market.get('outcomes',[])
            if kind not in ('h2h','spreads','totals') or market.get('period','full_game')!='full_game':continue
            stamp=market.get('last_update',book.get('last_update'))
            expected={'Over','Under'} if kind=='totals' else {game['home_team'],game['away_team']}
            paired=len(sides)==2 and {s['name'] for s in sides}==expected
            if paired and kind!='h2h':
                points=[s.get('point') for s in sides]
                paired=all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and (x*2)%1==0 for x in points)
                if paired:paired=points[0]==(-points[1] if kind=='spreads' else points[1])
            for s in sides:
                try:
                    if s['name'] not in expected:raise ValueError('MARKET_SELECTION_MISMATCH')
                    age,fresh=price_age(stamp,manifest['fetched_at'],at,game['kickoff']);implied=american_to_implied(s['price'])
                    line=0 if kind=='h2h' else s.get('point')
                    if line is None or not isinstance(line,(int,float)) or isinstance(line,bool) or not math.isfinite(line) or (line*2)%1:raise ValueError('INVALID_MARKET_LINE')
                    opposite=next((o for o in sides if o is not s),None) if paired else None
                    fair=devig_two_way(s['price'],opposite['price'])[0] if opposite else None
                    reasons=['MODEL_NOT_CALIBRATED','PROSPECTIVE_VALIDATION_PENDING','BOOK_SETTLEMENT_RULE_UNVERIFIED','QB_AND_INJURY_ADJUSTMENTS_UNAVAILABLE']
                    if not fresh:reasons.append('STALE_PRICE')
                    if not paired:reasons.append('MISSING_EXACT_OPPOSITE_SIDE')
                    if not model_status['beats_both_baselines']:reasons.append('FAILED_ELO_BENCHMARK')
                    mass=None
                    if forecast and kind in ('h2h','spreads'):
                        mass=margin_mass(forecast['projected_home_margin'],forecast['margin_sd'],line,s['name']==game['home_team'])
                    if kind=='totals':reasons.append('NO_TRAINED_TOTAL_MODEL')
                    ev=outcome_ev(mass['p_win'],mass['p_loss'],mass['p_push'],s['price']) if mass else None
                    row=dict(event_id=game['event_id'],odds_event_id=event['id'],event_start=game['kickoff'],book=book['key'],market=kind,period='full_game',
                        line=line,line_semantics='NOT_APPLICABLE_ZERO_CONTRACT_SENTINEL' if kind=='h2h' else 'exact_offered_line',
                        selection=s['name'],american_odds=s['price'],opposite_odds=opposite['price'] if opposite else None,
                        observed_at=stamp,captured_at=manifest['fetched_at'],decision_timestamp=at,quote_age_seconds=age,price_fresh=fresh,
                        snapshot_id=manifest['snapshot_id'],payload_hash=manifest['payload_hash'],break_even_probability=implied,
                        market_no_vig=fair,market_probability_basis='conditional_on_non_push',raw_model_outcome_mass=mass,
                        raw_probability_conditional_on_non_push=mass['p_win']/(1-mass['p_push']) if mass else None,
                        conditional_model_ev=ev,ev_assumptions='Research margin distribution, settled standard payout; ties/pushes retained, void rules unverified',
                        forecast_hash=forecast['forecast_hash'] if forecast else None,
                        predictive_margin_interval=forecast['predictive_interval_10_90'] if forecast else None,
                        calibrated_probability=None,p_low=None,conservative_ev=None,decision='PASS',pass_reasons=reasons,recommendations_enabled=False)
                    row['quote_id']=digest(row);out.append(row)
                except (ValueError,TypeError,KeyError) as e:
                    rejected.append(dict(event_id=game['event_id'],book=book['key'],market=kind,reason=str(e)))
    for q in out:
        peers=[p for p in out if p['book']!=q['book'] and p['market']==q['market'] and p['selection']==q['selection']
            and p['line']==q['line'] and p['price_fresh'] and p['market_no_vig'] is not None
            and abs((utc(p['observed_at'])-utc(q['observed_at'])).total_seconds())<=60]
        bybook={p['book']:p for p in peers};q['independent_consensus']=dict(probability=statistics.median(p['market_no_vig'] for p in bybook.values()) if len(bybook)>=2 else None,
            book_count=len(bybook),books=sorted(bybook),basis='same-line contemporaneous non-push normalization; book rules unverified')
    return out,rejected

def frozen_lookup(store):
    result={}
    for p in (store.root/'predictions/props').glob('*.json'):
        body=json.loads(p.read_text())
        if digest({k:v for k,v in body.items() if k!='forecast_hash'})!=body['forecast_hash']:raise ValueError('FROZEN_FORECAST_HASH_MISMATCH')
        result[body['forecast_hash']]=body
    return result

def price_props(root,game,delivery,availability,lookup,at):
    store=ResearchStore(Path(root)/'data');quotes=[];rejects=[];comparisons=[];aliases=defaultdict(set)
    for r in event_price_records(root,'NFL',game):
        qs,rs=normalize_props(store,store.manifest(r['snapshot_id']),'NFL',at);quotes.extend(qs)
        rejects.extend(dict(event_id=game['event_id'],reason=k,count=v) for k,v in rs.items())
    for person in availability['identities']:
        for n in person['aliases']:aliases[normalized_name(n)].add(person['player_id'])
    people={p['player_id']:p for p in availability['records']};matched=set()
    for fsummary in delivery['predictions']:
        f=lookup[fsummary['forecast_hash']];person=people[f['player_id']]
        for q in quotes:
            if q['market']!=f['market'] or q['book'] not in ('draftkings','fanduel') or aliases.get(normalized_name(q['player_name']))!={f['player_id']}:continue
            # An older freeze may legitimately have no price mapping. Never rewrite it.
            if f['event_mapping'].get('odds_event_id')!=game.get('odds_event_id'):
                rejects.append(dict(event_id=game['event_id'],forecast_hash=f['forecast_hash'],reason='FROZEN_BOOK_IDENTITY_MISMATCH'));continue
            try:
                for c in comparison(f,q,person,delivery['benchmarks'][f['market']],at,quotes,identity_store=store):
                    c['research_rank_eligible']=c['research_rank_eligible'] and c['price_fresh']
                    # Large raw discrepancies with even the paired entry book need
                    # review, especially when cross-book consensus is unavailable.
                    if abs(c['raw_probability_conditional_on_non_push']-c['market_no_vig'])>=.15:
                        c['pass_reasons']=sorted(set(c['pass_reasons']+['MODEL_BOOK_DISAGREEMENT']))
                        c['research_rank_eligible']=False
                    if 'LONG_LAYOFF_ROLE_UNVERIFIED' in c['pass_reasons']:c['research_rank_eligible']=False
                    comparisons.append(freeze_comparison(store,c));matched.add(q['quote_id'])
            except (ValueError,KeyError) as e:rejects.append(dict(event_id=game['event_id'],quote_id=q['quote_id'],reason=str(e)))
    for q in quotes:
        if q['book'] in ('draftkings','fanduel') and q['quote_id'] not in matched:
            rejects.append(dict(event_id=game['event_id'],player_name=q['player_name'],market=q['market'],quote_id=q['quote_id'],reason='NO_MATCHED_TRAINED_PLAYER_FORECAST'))
    evidence=[]
    for q in quotes:
        if q['odds_event_id']!=game.get('odds_event_id') or utc(q['event_start'])!=utc(game['kickoff']):
            rejects.append(dict(event_id=game['event_id'],quote_id=q['quote_id'],reason='EVENT_IDENTITY_MISMATCH'));continue
        for side in ('Over','Under'):
            evidence.append(dict(event_id=game['event_id'],book=q['book'],market=q['provider_market'],line=q['line'],selection=side,
                player_name=q['player_name'],american_odds=q['over_odds' if side=='Over' else 'under_odds'],observed_at=q['quote_timestamp'],
                captured_at=q['captured_at'],snapshot_id=q['snapshot_id'],payload_hash=q['payload_hash'],
                quote_age_seconds=(utc(at)-utc(q['quote_timestamp'])).total_seconds(),price_fresh='STALE_PRICE' not in q['reasons']))
    return comparisons,evidence,rejects

def compact_prop(f):
    keys=('event_id','event_start','player_id','player_name','team_id','market','generated_at','forecast_hash','artifact_hash','model_version',
          'role_confirmed','availability_snapshot','pass_reasons','model_status','calibrated_probability','p_low')
    return dict({k:f[k] for k in keys},projection=f['projection'],decision='PASS',recommendations_enabled=False,
                distribution_hash=f['distribution_hash'],distribution_location=f['distribution_location'],
                forecast_hash_semantics='Hash of full immutable local forecast, not this compact public summary')

def compact_comparison(c):
    keys=('event_id','event_start','player_id','player_name','market','selection','line','book','odds','break_even_probability','market_no_vig',
          'raw_model_outcome_mass','conditional_model_ev','raw_probability_conditional_on_non_push','projected_opportunity','simulation_interval_10_50_90',
          'forecast_hash','forecast_generated_at','comparison_hash','quote_timestamp','quote_captured_at','quote_age_seconds','quote_snapshot','quote_payload_hash',
          'decision_timestamp','price_identity_verified','price_fresh','pass_reasons','research_rank_eligible','independent_consensus')
    result={k:c[k] for k in keys};result.update(decision='PASS',calibrated_probability=None,p_low=None,conservative_ev=None,recommendations_enabled=False,
        comparison_hash_semantics='Hash of full immutable local comparison, not this compact public summary',
        availability_state=c['availability']['availability_state'],role_confirmed=c['availability']['role_confirmed'],
        benchmark_admission=c['benchmark']['admission'],ev_assumptions=c['ev_assumptions'])
    return result

def run(root,target_date,*,collect=False,daily_cap=24,reserve=50,refresh_sources=True):
    root=Path(root);store=ResearchStore(root/'data');out=root/'outputs';started=now()
    with card_lock(store.root/'reliable-runner'):
        before=frozen_lookup(store);before_hashes=set(before)
        baseline_path=store.root/'evaluations'/('nfl-sweep-baseline-'+target_date+'.json')
        if baseline_path.exists():baseline=json.loads(baseline_path.read_text())
        else:
            previous=out/'nfl_sweep_status.json'
            old=json.loads(previous.read_text()) if previous.exists() else None
            baseline=dict(recorded_at=started,before=old['before'] if old and old['target_date']==target_date else None,
                source_report_hash=digest(old) if old and old['target_date']==target_date else None)
            # On the initial run, baseline counts are filled after independent discovery.
        schedule,rows=discover(root,target_date,refresh=refresh_sources);games=schedule['games']
        if baseline['before'] is None:
            baseline['before']=dict(nfl_scheduled_games_with_forecasts=len({f['event_id'] for f in before.values() if f['sport']=='NFL'
                and f['event_id'] in {g['event_id'] for g in games}}),frozen_prop_records=len(before))
        if not baseline_path.exists():store._immutable(baseline_path,json.dumps(baseline,sort_keys=True).encode())
        artifact,h,history,model_status=train(root,rows,schedule['manifests'][0],now())
        # Free discovery binds book identities before freezing; schedules remain independent.
        from .providers.validation import ProviderValidator
        from .providers.security import load_credentials
        load_credentials(root/'.env');v=ProviderValidator(store,max_odds_credits=0)
        if collect:
            _,book_events=v.request('odds','sports/americanfootball_nfl/events',{'dateFormat':'iso'})
        else:
            cached=store.root/'evaluations/nfl-slate-price-access.json'
            access=json.loads(cached.read_text()) if cached.exists() else {}
            book_events=[r['event'] for r in access.get('events',{}).values() if r.get('event')]
        forecasts={};deliveries={};availability={};errors={};cache={}
        for g in games:
            e,reason=match_odds(g,book_events if isinstance(book_events,list) else [])
            if e:g.update(odds_event_id=e['id'],odds_event_start=e['commence_time'],market_identity_verified=True)
            try:forecasts[g['event_id']]=freeze(root,g,artifact,h,history,now())
            except (ValueError,KeyError) as error:errors.setdefault(g['event_id'],[]).append(dict(component='game_model',reason=str(error)))
            try:
                news=capture(root,'NFL',g);availability[g['event_id']]=news
                deliveries[g['event_id']]=prop_run(root,'NFL',simulate_forecasts=False,canonical_event=g,availability_record=news,model_cache=cache)
            except (ValueError,KeyError,OSError,TypeError) as error:errors.setdefault(g['event_id'],[]).append(dict(component='player_forecasts',reason=type(error).__name__+':'+str(error)))
            print(json.dumps(dict(event_id=g['event_id'],game_forecast=g['event_id'] in forecasts,props=len(deliveries.get(g['event_id'],{}).get('predictions',[])),errors=errors.get(g['event_id'],[]))),flush=True)
        if collect:access=collect_priority(root,canonical_events=games,daily_credit_cap=daily_cap,reserve_credits=reserve)
        else:
            p=store.root/'evaluations/nfl-slate-price-access.json';access=json.loads(p.read_text()) if p.exists() else dict(events={},quota=dict(credits_used=0,daily_cap=daily_cap),featured=None)
        lookup=frozen_lookup(store)
        if not before_hashes<=set(lookup):raise ValueError('ORIGINAL_FORECASTS_LOST')
        at=now();covered=[];props=[];comparisons=[];rejects=[];benchmarks={}
        for g in games:
            eid=g['event_id'];f=forecasts.get(eid);d=deliveries.get(eid);news=availability.get(eid);access_row=access.get('events',{}).get(eid,{})
            quotes,rs=featured_quotes(store,access,g,f,at,model_status);rejects.extend(rs)
            if d:
                pc,pq,pr=price_props(root,g,d,news,lookup,at);comparisons.extend(map(compact_comparison,pc));quotes.extend(pq);rejects.extend(pr)
                props.extend(map(compact_prop,d['predictions']));rejects.extend(dict(event_id=eid,**r) for r in d['rejections']);benchmarks=d['benchmarks']
            main=[q for q in quotes if q['market'] in ('h2h','spreads','totals')];comparisons.extend(main)
            counts=Counter(p['availability_state'] for p in news['records']) if news else {}
            record=dict(event_id=eid,home_team=g['home_team'],away_team=g['away_team'],kickoff=g['kickoff'],
                forecast_status=f['forecast_status'] if f else ('BLOCKED_IDENTITY' if not g['identity_verified'] else 'NO_TRAINED_GAME_MODEL'),
                p_home_win=f['p_home_win'] if f else None,p_away_win=f['p_away_win'] if f else None,
                p_tie=f['p_tie'] if f else None,probability_basis=f['probability_basis'] if f else None,
                projected_home_margin=f['projected_home_margin'] if f else None,model_version=f['model_version'] if f else None,
                model_data_cutoff=f['model_data_cutoff'] if f else None,
                main_market_status=access_row.get('main_market_status','NOT_REQUESTED'),prop_market_status=access_row.get('prop_market_status','NOT_REQUESTED'),
                quotes=quotes,prop_forecasts=len(d['predictions']) if d else 0,availability_counts=dict(counts),
                current_roster_players=len(news['records']) if news else 0,confirmed_roles=sum(p['role_confirmed'] for p in news['records']) if news else 0,
                reported_injuries=sum(bool(p['injury_evidence']) for p in news['records']) if news else 0,
                availability_snapshot=news['snapshot_hash'] if news else None,availability_captured_at=news['latest_source_capture'] if news else None,
                prop_attempts=access_row.get('attempts',{}),deferred_markets=access_row.get('deferred_markets',[]),
                errors=errors.get(eid,[]),schedule_reasons=g['schedule_reasons'],decision='PASS',core_enabled=False)
            covered.append(record)
        # Final publication age can only worsen freshness; never reset quote clocks.
        at=now()
        for c in comparisons:
            stamp=c.get('quote_timestamp',c.get('observed_at'));c['publication_quote_age_seconds']=(utc(at)-utc(stamp)).total_seconds()
            if c['publication_quote_age_seconds']>180:
                c['price_fresh']=False;c['pass_reasons']=sorted(set(c['pass_reasons']+['STALE_PRICE']));c['research_rank_eligible']=False
        for row in covered:
            for q in row['quotes']:
                q['publication_quote_age_seconds']=(utc(at)-utc(q.get('observed_at',q.get('quote_timestamp')))).total_seconds()
                q['price_fresh']=q['publication_quote_age_seconds']<=180
        report=dict(target_date=target_date,generated_at=at,started_at=started,schedule=schedule,games=covered,quota=access['quota'],
            model_evaluation=model_status['evaluation'],game_model_status='RESEARCH_ONLY_FAILED_ELO_BENCHMARK' if not model_status['beats_both_baselines'] else 'RESEARCH_ONLY',
            before=baseline['before'],baseline_provenance=baseline,after=dict(game_forecasts=len(forecasts),prop_forecasts=len(props),
                main_market_games=sum(g['main_market_status']=='FETCHED' for g in covered),prop_scanned_games=sum(g['prop_market_status']=='SCANNED' for g in covered),
                all_frozen_prop_records=len(lookup),new_prop_records=len(lookup)-baseline['before']['frozen_prop_records'],
                new_prop_records_this_execution=len(set(lookup)-before_hashes),price_comparisons=len(comparisons),
                fresh_comparisons=sum(c['price_fresh'] for c in comparisons)),preserved_original_frozen_records=len(before_hashes),
            rejection_counts=dict(Counter(r['reason'] for r in rejects)),validated_edges=0,auto_bets_placed=0,core_enabled=False,
            blockers=['No prospective NFL game-model calibration or price-relative validation','Game ridge does not beat Elo on every metric',
                'Roster membership and reported injuries do not confirm participation or workload','Historical outcome revisions are reconstructed; historical book prices remain unverified',
                'NFL TD and total outcome models unavailable; totals shown as price evidence only','Book settlement rules unverified; conditional EV cannot authorize cash'])
        reports={'nfl_sweep_status.json':report,
            'nfl_game_probabilities.json':dict(generated_at=at,target_date=target_date,model_status=model_status,predictions=list(forecasts.values()),validated_edges=0),
            'nfl_prop_research.json':dict(generated_at=at,target_date=target_date,predictions=props,benchmarks=benchmarks,rejections=rejects,recommendations_enabled=False),
            'nfl_market_comparisons.json':dict(generated_at=at,target_date=target_date,comparisons=comparisons,
                research_rankings=rankings(comparisons),validated_edges=[],core_enabled=False)}
        folder=store.root/'evaluations/nfl-sweeps';folder.mkdir(exist_ok=True)
        for name,body in reports.items():
            encoded=json.dumps(body,sort_keys=True,allow_nan=False).encode();store._immutable(folder/(digest(body)+'.json'),encoded)
            atomic_json(out/name,body)
        atomic_text(root/'reports/NFL_FULL_SLATE_SWEEP.md',markdown(report,benchmarks,comparisons))
        return report

def rankings(comparisons):
    eligible=[c for c in comparisons if c.get('research_rank_eligible') and c.get('price_fresh') and c.get('conditional_model_ev') is not None]
    return [dict(event_id=c['event_id'],player=c.get('player_name'),market=c['market'],selection=c['selection'],line=c['line'],book=c['book'],
        model_probability=c.get('raw_probability_conditional_on_non_push'),break_even_probability=c['break_even_probability'],
        conditional_ev=c['conditional_model_ev'],uncertainty_interval=c.get('simulation_interval_10_50_90'),p_low=None,
        decision='PASS',pass_reasons=c['pass_reasons'],comparison_hash=c['comparison_hash']) for c in sorted(eligible,
        key=lambda c:(not c.get('role_confirmed',False),len(c['pass_reasons']),-c['conditional_model_ev']))[:20]]

def markdown(report,benchmarks,comparisons):
    lines=['# NFL full-slate sweep', '',f"Sunday {report['target_date']}; captured {report['generated_at']}. All selections PASS; CORE disabled.",
        '', 'Schedule: nflverse cross-checked against ESPN, independently of odds. Both are secondary sources; no direct NFL league feed authority is claimed.',
        '', 'Win percentages below are raw research probabilities conditional on no tie; separate tie mass is retained in JSON. They are not betting confidence.', '',
        '| Game | Kickoff UTC | Away / home win | Home margin | Props | Main / prop prices | Fresh / quotes | Availability confirmed / roster |',
        '|---|---|---|---:|---:|---|---:|---:|']
    for g in report['games']:
        ps=f"{100*g['p_away_win']:.1f}% / {100*g['p_home_win']:.1f}%" if g['p_home_win'] is not None else 'Unavailable'
        margin=f"{g['projected_home_margin']:.2f}" if g['projected_home_margin'] is not None else '—'
        lines.append(f"| {g['away_team']} @ {g['home_team']} | {g['kickoff']} | {ps} | {margin} | {g['prop_forecasts']} | {g['main_market_status']} / {g['prop_market_status']} | {sum(q['price_fresh'] for q in g['quotes'])} / {len(g['quotes'])} | {g['confirmed_roles']} / {g['current_roster_players']} |")
    lines+=['','## Chronological game-model evaluation','','| Model | Games | Margin MAE | RMSE | Brier | Log loss |','|---|---:|---:|---:|---:|---:|']
    for k,m in report['model_evaluation'].items():lines.append(f"| {k} | {m['n']} | {m['mae']:.4f} | {m['rmse']:.4f} | {m['brier']:.6f} | {m['log_loss']:.6f} |")
    lines+=['','Regular-season rolling weekly folds; 48-hour outcome embargo. Fixed ridge policy; no odds, target-game QB, weather or final season stats enter features. Historical revisions are reconstructed, not proven as published at each historical kickoff.',
        '','## Existing player challengers','','| Market | Training | OOS | MAE / recent-mean baseline | Admission |','|---|---:|---:|---|---|']
    for k,b in benchmarks.items():
        e=b['evaluation'];lines.append(f"| {k} | {b['training_n']} | {e['n']} | {e['mae']:.3f} / {e['baseline_mae']:.3f} | {b['admission']} |")
    lines+=['','## Coverage and quota','',f"Before: {json.dumps(report['before'])}",f"After: {json.dumps(report['after'])}",f"Quota: {json.dumps(report['quota'])}",
        '','Quotes expire after 180 seconds from the provider timestamp. A successful request does not reset quote age. Each game retains all requested, returned and budget-deferred markets in nfl_sweep_status.json.',
        '','## Research rankings','']
    ranked=rankings(comparisons)
    if not ranked:lines.append('No fresh candidate meets the research ranking gates. This does not remove stale or rejected comparisons from the audit output.')
    for c in ranked[:10]:lines.append(f"- {c['event_id']} — {c['player']} {c['market']} {c['selection']} {c['line']} ({c['book']}): raw non-push probability {c['model_probability']:.3f}, break-even {c['break_even_probability']:.3f}, conditional EV {c['conditional_ev']:.3f}; PASS, {', '.join(c['pass_reasons'])}.")
    lines+=['','## Remaining blockers','']+['- '+b for b in report['blockers']]
    lines+=['',f"Rejections: {json.dumps(report['rejection_counts'],sort_keys=True)}",'', 'Reproduce: `python -m ap_evsims.nfl_sweep --date 2026-10-18 --collect --daily-cap 96 --reserve 50`. This explicitly raises the one-run daily ceiling; the default stays 24. Actual header costs and the shared ledger control requests. No cash is committed.','']
    return '\n'.join(lines)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--date',required=True)
    p.add_argument('--collect',action='store_true');p.add_argument('--daily-cap',type=int,default=24);p.add_argument('--reserve',type=int,default=50)
    a=p.parse_args();r=run(a.root,a.date,collect=a.collect,daily_cap=a.daily_cap,reserve=a.reserve)
    print(json.dumps(dict(games=len(r['games']),after=r['after'],quota=r['quota'],validated_edges=0)))

if __name__=='__main__':main()
