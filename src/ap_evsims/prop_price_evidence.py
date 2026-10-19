"""Settle frozen challenger comparisons without counting quote refreshes as bets.

Closing evidence must have been archived before kickoff. Unknown book/DNP rules
never become hypothetical cash profits. All revisions are append-only.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json,math
from pathlib import Path
from .integrity import digest,utc
from .prop_challenger import VERSION
from .prop_research import normalize
from .prop_settlement import settlement
from .prop_prices import normalize_props
from .prop_prospective import prop_mass
from .odds import american_to_decimal
from .publication import atomic_json
from .research_store import ResearchStore


def first_comparisons(records,*,eligible_only=False):
    selected={}
    for c in sorted(records,key=lambda c:(utc(c['decision_timestamp']),c['comparison_hash'])):
        if digest({k:v for k,v in c.items() if k!='comparison_hash'})!=c['comparison_hash']:raise ValueError('COMPARISON_HASH_MISMATCH')
        if eligible_only and (not c['price_identity_verified'] or not c['price_fresh']):continue
        key=tuple(c[k] for k in ('forecast_hash','book','selection','line'))
        selected.setdefault(key,c)
    return list(selected.values())


def close_for(c,quotes,at,*,captures=()):
    if utc(at)<utc(c['event_start']):return None
    matches=[q for q in quotes if q['odds_event_id']==c['availability'].get('odds_event_id',c.get('odds_event_id'))]
    series=[q for q in matches if q['book']==c['book'] and q['market']==c['market'] and q['player_name']==c['player_name']
            and q['period']=='full_game' and utc(q['captured_at'])<utc(c['event_start'])]
    latest=max((utc(q['captured_at']) for q in series),default=None)
    # The archived opening quote supplies exact provider event identity; callers
    # pass it explicitly, never guess from display names or date proximity.
    valid=[q for q in matches if q['book']==c['book'] and q['market']==c['market'] and q['line']==c['line']
        and q['player_name']==c['player_name'] and q['period']=='full_game'
        and utc(q['event_start'])==utc(c.get('provider_event_start',c['event_start']))
        and utc(q['quote_timestamp'])<=utc(q['captured_at'])<utc(c['event_start'])
        and 0<=(utc(c['event_start'])-utc(q['quote_timestamp'])).total_seconds()<=300
        and (utc(q['captured_at'])-utc(q['quote_timestamp'])).total_seconds()<=180]
    chosen=max(valid,key=lambda q:(utc(q['quote_timestamp']),utc(q['captured_at']))) if valid else None
    if chosen is None or utc(chosen['captured_at'])!=latest:return None
    for snapshot in captures:
        if snapshot['odds_event_id']!=chosen['odds_event_id'] or chosen.get('provider_market') not in snapshot['markets']:continue
        if snapshot['books'] and chosen['book'] not in snapshot['books']:continue
        if utc(chosen['captured_at'])<utc(snapshot['captured_at'])<utc(c['event_start']):return None
    return chosen


def grade(c,f,row,quotes,at,*,captures=()):
    if digest({k:v for k,v in c.items() if k!='comparison_hash'})!=c['comparison_hash']:raise ValueError('COMPARISON_HASH_MISMATCH')
    if c['forecast_hash']!=f['forecast_hash'] or not c['price_identity_verified']:raise ValueError('PRICE_FORECAST_IDENTITY_UNVERIFIED')
    checked=settlement(f,row)
    if utc(row.captured_at)>utc(at):raise ValueError('OUTCOME_NOT_YET_AVAILABLE')
    if not utc(c['decision_timestamp'])<utc(c['event_start']):raise ValueError('COMPARISON_NOT_PREGAME')
    if not c['price_fresh'] or not 0<=(utc(c['decision_timestamp'])-utc(c['quote_timestamp'])).total_seconds()<=180:raise ValueError('STALE_COMPARISON_PRICE')
    value=row.outcome-c['line'];win=value>0 if c['selection']=='Over' else value<0
    result='PUSH' if value==0 else 'WIN' if win else 'LOSS';mass=c['raw_model_outcome_mass']
    if mass!=prop_mass(f['projection']['distribution'],c['line'],c['selection']):raise ValueError('FROZEN_PROBABILITY_MISMATCH')
    p=mass['p_win']/(1-mass['p_push']) if result!='PUSH' and mass['p_push']<1 else None
    close=close_for(dict(c,odds_event_id=f['event_mapping']['odds_event_id']),quotes,at,captures=captures)
    cp=(close['over_no_vig'] if c['selection']=='Over' else 1-close['over_no_vig']) if close else None
    market=c['market_no_vig'] if p is not None else None
    return dict(comparison_hash=c['comparison_hash'],forecast_hash=f['forecast_hash'],sport=c['sport'],market=c['market'],
        book=c['book'],selection=c['selection'],line=c['line'],observed_stat=row.outcome,statistic_result=result,
        raw_brier=(p-win)**2 if p is not None else None,raw_logloss=-math.log(max(1e-12,p if win else 1-p)) if p is not None else None,
        raw_probability=p,market_probability=market,observed_binary=int(win) if p is not None else None,
        descriptive_market_brier=(market-win)**2 if market is not None else None,
        descriptive_market_logloss=-math.log(max(1e-12,market if win else 1-market)) if market is not None else None,
        qualified_market_brier=None,qualified_market_logloss=None,
        source_outcome_hash=checked['outcome_hash'],source_captured_at=row.captured_at,
        closing_quote_id=close['quote_id'] if close else None,
        descriptive_conditional_price_clv=american_to_decimal(c['odds'])*cp-1 if cp is not None else None,
        qualified_clv=None,hypothetical_roi=None,actual_cash_roi=None,
        qualification='BOOK_RULES_AND_EXECUTION_UNVERIFIED',recommendations_enabled=False)


def run(root):
    root=Path(root);s=ResearchStore(root/'data');at=datetime.now(timezone.utc).isoformat();all_comparisons=[];forecasts={}
    for p in s.root.joinpath('predictions/props').glob('*.json'):
        f=json.loads(p.read_text())
        if f['model_version']==VERSION:forecasts[f['forecast_hash']]=f
    for p in s.root.joinpath('predictions/market-research').glob('*.json'):
        c=json.loads(p.read_text())
        if c['model_version']==VERSION:all_comparisons.append(c)
    first_all=first_comparisons(all_comparisons);first=first_comparisons(all_comparisons,eligible_only=True);records=[];pending=[]
    for sport in ('NFL','NBA','NHL','MLB'):
        rows,_=normalize(root,sport);outcomes={(r.event_id,r.player_id,r.market):r for r in rows};quotes=[];captures=[]
        for p in s.root.joinpath('manifests').glob('*.json'):
            m=json.loads(p.read_text())
            if m.get('provider')!='odds' or '/events/' not in m.get('endpoint','') or not m['endpoint'].endswith('/odds') or m['parameters'].get('endpoint_status')!=200:continue
            try:
                qs,_=normalize_props(s,m,sport,at);quotes.extend(qs);payload=s.payload(s.manifest(m['snapshot_id']))
                captures.append(dict(odds_event_id=payload['id'],captured_at=m['fetched_at'],markets=m['parameters'].get('markets','').split(','),
                    books=list(filter(None,m['parameters'].get('bookmakers','').split(',')))))
            except ValueError:continue
        for c in [c for c in first if c['sport']==sport]:
            f=forecasts[c['forecast_hash']];row=outcomes.get((c['event_id'],c['player_id'],c['market']))
            reason='EVENT_NOT_STARTED' if utc(at)<utc(c['event_start']) else 'OUTCOME_OR_DNP_UNVERIFIED' if row is None else None
            if not c['price_identity_verified']:reason='PRICE_FORECAST_IDENTITY_UNVERIFIED'
            if reason:pending.append(dict(comparison_hash=c['comparison_hash'],sport=sport,reason=reason));continue
            try:r=grade(c,f,row,quotes,at,captures=captures)
            except ValueError as e:pending.append(dict(comparison_hash=c['comparison_hash'],sport=sport,reason=str(e)));continue
            folder=s.root/'settlements/prop-comparisons';folder.mkdir(exist_ok=True)
            s._immutable(folder/(digest(r)+'.json'),json.dumps(r,sort_keys=True).encode());records.append(r)
    cohorts=[];groups=defaultdict(list)
    for r in records:groups[(r['sport'],r['market'],r['book'])].append(r)
    for (sport,market,book),rs in sorted(groups.items()):
        scored=[r for r in rs if r['raw_brier'] is not None];bins=[]
        for lo in range(10):
            bs=[r for r in scored if lo==min(9,int(r['raw_probability']*10))]
            bins.append(dict(lower=lo/10,upper=(lo+1)/10,n=len(bs),
                mean_probability=sum(r['raw_probability'] for r in bs)/len(bs) if bs else None,
                observed_frequency=sum(r['observed_binary'] for r in bs)/len(bs) if bs else None))
        metrics={k:sum(r[k] for r in scored)/len(scored) if scored else None for k in
                 ('raw_brier','raw_logloss','descriptive_market_brier','descriptive_market_logloss')}
        cohorts.append(dict(sport=sport,market=market,book=book,n=len(scored),push_n=len(rs)-len(scored),calibration_bins=bins,**metrics))
    report=dict(generated_at=at,comparison_update_records=len(all_comparisons),first_candidate_comparisons=len(first_all),
        first_fresh_identity_verified_comparisons=len(first),excluded_first_observations=len(first_all)-len(first),cohorts=cohorts,
        settled_comparisons=len(records),pending_comparisons=len(pending),pending_reasons=dict(Counter(p['reason'] for p in pending)),
        records=records,pending=pending,unique_forecast_cohort=len({c['forecast_hash'] for c in first}),
        sample_semantics='First event/player/model/book/side/exact-line observation only; books and opposite sides remain correlated, not independent bets',
        hypothetical_roi=None,clv=None,max_drawdown=None,validated_edges=0,recommendations_enabled=False)
    atomic_json(root/'outputs/prospective_market_evidence.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');a=p.parse_args()
    print(json.dumps({k:v for k,v in run(a.root).items() if k not in ('records','pending')},indent=2))
