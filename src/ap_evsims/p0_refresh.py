"""Refresh prices/news, reprice immutable forecasts, and settle; no simulations.

python -m ap_evsims.p0_refresh --root . [--collect --daily-cap 36]
The default 24-credit daily cap is unchanged. An explicit bounded run override
retains a 350-credit account reserve and the existing request cooldown.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path
from .integrity import digest,utc
from .identity import normalized_name
from .prop_challenger import VERSION
from .prop_availability import capture
from .prop_prices import collect_priority,normalize_props
from .prop_market_research import comparison,freeze_comparison
from .challenger_delivery import verified_model
from .p0_results import publish,price_inventory
from .prop_price_evidence import run as settle_prices
from .research_store import ResearchStore
from .publication import atomic_json


def run(root,collect=False,daily_cap=24,*,nfl_date=None,reserve_credits=50):
    # Explicit NFL refresh uses the schedule inventory, never the singleton sport record.
    if nfl_date is not None:
        from .nfl_sweep import run as sweep
        return sweep(root,nfl_date,collect=collect,daily_cap=daily_cap,reserve=reserve_credits)
    root=Path(root);store=ResearchStore(root/'data');out=root/'outputs'
    if not 0<=daily_cap<=36:raise ValueError('RESEARCH_REFRESH_BUDGET_EXCEEDED')
    if collect:collect_priority(root,daily_credit_cap=daily_cap,reserve_credits=350)
    forecasts={}
    for p in store.root.joinpath('predictions/props').glob('*.json'):
        f=json.loads(p.read_text())
        if digest({k:v for k,v in f.items() if k!='forecast_hash'})!=f['forecast_hash']:raise ValueError('FORECAST_HASH_MISMATCH')
        forecasts[f['forecast_hash']]=f
    access=json.loads((store.root/'evaluations/prop-price-access.json').read_text());sports={}
    for sport in ('NHL','NBA','MLB','NFL'):
        if sport=='NFL':
            from .challenger_delivery import run as full_nfl_delivery
            try:
                result=full_nfl_delivery(root,'NFL',simulate_forecasts=False)
                report_nfl=json.loads((out/'nfl_challenger_prospective.json').read_text());cs=report_nfl['comparisons']
                news=json.loads((out/'nfl_availability.json').read_text());at=datetime.now(timezone.utc).isoformat()
                sports['NFL']=dict(generated_at=at,status='FULL_SLATE_REPRICED',scheduled_games=result['scheduled_games'],coverage=result['coverage'],
                    exact_comparisons=len(cs),identity_matched=sum(c['price_identity_verified'] for c in cs),
                    fresh_identity_matched=sum(c['price_identity_verified'] and c['price_fresh'] for c in cs),
                    reported_injuries=sum(bool(p['injury_evidence']) for p in news['records']),confirmed_roles=sum(p['role_confirmed'] for p in news['records']),
                    pass_reasons=dict(Counter(reason for c in cs for reason in c['pass_reasons'])),rejections=report_nfl['rejections'])
            except (ValueError,KeyError,OSError,TypeError) as e:sports['NFL']=dict(status='REFRESH_BLOCKED',error_category=type(e).__name__)
            continue
        path=out/(sport.lower()+'_challenger_prospective.json');existing=json.loads(path.read_text());old_hashes=[f['forecast_hash'] for f in existing['predictions']]
        try:
            news=capture(root,sport);at=datetime.now(timezone.utc).isoformat();people={p['player_id']:p for p in news['records']}
            aliases=defaultdict(set)
            for p in news['identities']:
                for name in p['aliases']:aliases[normalized_name(name)].add(p['player_id'])
            response=next(r for r in access['sports'] if r['sport']==sport)
            qs,_=normalize_props(store,store.manifest(response['record']['snapshot_id']),sport,at)
            model_status=json.loads((out/(sport.lower()+'_challenger_status.json')).read_text());benchmarks={}
            for market,entry in model_status['markets'].items():_,benchmarks[market]=verified_model(root,sport,market,entry,at)
            comparisons=[];rejects=[]
            previous={(c['forecast_hash'],c['book'],c['selection'],c['line']):c['comparison_hash'] for c in existing['comparisons']}
            for summary in existing['predictions']:
                f=forecasts[summary['forecast_hash']]
                if f['event_id']!=news['event']['event_id'] or utc(f['event_start'])!=utc(news['event']['event_start']):
                    rejects.append(dict(forecast_hash=f['forecast_hash'],reason='FROZEN_SCHEDULE_REVISION_REQUIRES_NEW_COHORT'));continue
                person=people.get(f['player_id'])
                if person is None:rejects.append(dict(forecast_hash=f['forecast_hash'],reason='PLAYER_NOT_IN_CURRENT_ROSTER'));continue
                matching=[q for q in qs if q['book'] in ('draftkings','fanduel') and q['market']==f['market'] and aliases.get(normalized_name(q['player_name']))=={f['player_id']}]
                if not matching:rejects.append(dict(forecast_hash=f['forecast_hash'],reason='NO_CURRENT_EXACT_PLAYER_MARKET'));continue
                for q in matching:
                    try:
                        for c in comparison(f,q,person,benchmarks[f['market']],at,qs,identity_store=store):
                            mass=c['raw_model_outcome_mass'];fair=1+mass['p_loss']/mass['p_win'] if mass and mass['p_win']>0 else None
                            c.update(raw_fair_decimal_odds=fair,zero_ev_decimal_threshold=fair,conservative_ev=None,conservative_price_threshold=None,
                                availability_snapshot=news['snapshot_hash'],provider_schedule_evidence=news['event'])
                            if sport=='MLB' and news['event'].get('rescheduled_from') and not c['price_identity_verified']:
                                c['pass_reasons']=sorted(set(c['pass_reasons']+['POSTPONED_SCHEDULE_REVISION']))
                            key=(c['forecast_hash'],c['book'],c['selection'],c['line'])
                            comparisons.append(freeze_comparison(store,c,previous.get(key)))
                    except (ValueError,KeyError) as e:rejects.append(dict(quote_id=q['quote_id'],reason=str(e)))
            existing.update(comparisons=comparisons,current_price_rejections=rejects,prices_refreshed_at=at,availability_snapshot=news['snapshot_hash'])
            if [f['forecast_hash'] for f in existing['predictions']]!=old_hashes:raise ValueError('FROZEN_FORECAST_OVERWRITE')
            atomic_json(path,existing)
            ages=[max(0.,(utc(at)-utc(q['quote_timestamp'])).total_seconds()) for q in qs]
            sports[sport]=dict(generated_at=at,paired_offers=len(qs),books=dict(Counter(q['book'] for q in qs)),
                markets=dict(Counter(q['market'] for q in qs)),quote_age_seconds_min=min(ages,default=None),quote_age_seconds_max=max(ages,default=None),
                exact_comparisons=len(comparisons),identity_matched=sum(c['price_identity_verified'] for c in comparisons),
                fresh_identity_matched=sum(c['price_identity_verified'] and c['price_fresh'] for c in comparisons),
                evidence_resolved_start_offsets=sum(bool(c['event_identity_resolution']) for c in comparisons),
                reported_injuries=sum(bool(p['injury_evidence']) for p in news['records']),confirmed_roles=sum(p['role_confirmed'] for p in news['records']),
                pass_reasons=dict(Counter(r for c in comparisons for r in c['pass_reasons'])),rejections=rejects,canonical_event=news['event'])
        except (ValueError,KeyError,OSError,TypeError) as e:
            sports[sport]=dict(status='REFRESH_BLOCKED',error_category=type(e).__name__)
    at=datetime.now(timezone.utc).isoformat()
    cfb=json.loads((out/'cfb_score_research_status.json').read_text());cfb_quotes=[]
    current=[]
    for path in store.root.joinpath('manifests').glob('*.json'):
        m=json.loads(path.read_text())
        if m.get('endpoint')=='sports/americanfootball_ncaaf/odds' and m.get('parameters',{}).get('endpoint_status')==200:current.append(m)
    if current:
        m=store.manifest(max(current,key=lambda m:utc(m['fetched_at']))['snapshot_id'])
        for game in store.payload(m):
            if utc(game['commence_time'])<=utc(at):continue
            for book in game.get('bookmakers',[]):
                if book['key'] not in ('draftkings','fanduel'):continue
                for market in book.get('markets',[]):
                    observed=market.get('last_update',book.get('last_update'))
                    if observed:cfb_quotes.append((utc(at)-utc(observed)).total_seconds())
    sports['CFB']=dict(generated_at=at,status='PRESERVED_SCORE_MODEL',
        chronological_evaluation_n=cfb['evaluation']['n'],forecast_records=len(json.loads((out/'cfb_score_research_predictions.json').read_text())['predictions']),
        quote_age_seconds_min=min(cfb_quotes,default=None),quote_age_seconds_max=max(cfb_quotes,default=None),
        exact_comparisons=0,fresh_identity_matched=0,blocker='NO_NEW_FRESH_CFB_PRICE_COMPARISON_IN_PROP_PRIORITY_REFRESH',recommendations_enabled=False)
    report=json.loads((out/'p0_measured_results.json').read_text())
    report.update(pricing_updated_at=at,prices=price_inventory(store),current_market_status=sports,
                  additional_simulation_draws_this_refresh=0,additional_forecasts_this_refresh=0)
    for sport in ('NFL','NBA','NHL','MLB'):
        ss=sports[sport]
        if ss.get('status')=='REFRESH_BLOCKED':report['sports'][sport]['current_refresh_blocker']=ss;continue
        report['sports'][sport].update(price_comparison_records=ss['exact_comparisons'],identity_matched_comparisons=ss['identity_matched'],
            fresh_at_comparison=ss['fresh_identity_matched'],current_fresh_comparisons=ss['fresh_identity_matched'],pass_reasons=ss['pass_reasons'])
    atomic_json(out/'p0_measured_results.json',report)
    evidence=settle_prices(root)
    status=dict(generated_at=at,sports=sports,new_simulation_draws=0,new_forecasts=0,existing_forecasts_preserved=True,
        prospective_settled_comparisons=evidence['settled_comparisons'],validated_edges=0,core_enabled=False,
        quote_expiry_seconds=180,refresh_daily_credit_cap=daily_cap,remaining_credit_reserve=350)
    atomic_json(out/'p0_market_refresh.json',status);publish(root,report)
    return status


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--collect',action='store_true');p.add_argument('--daily-cap',type=int,default=24)
    p.add_argument('--nfl-date');p.add_argument('--reserve',type=int,default=50);a=p.parse_args()
    result=run(a.root,a.collect,a.daily_cap,nfl_date=a.nfl_date,reserve_credits=a.reserve)
    print(json.dumps({k:v for k,v in result.items() if k not in ('games','schedule')},indent=2))
