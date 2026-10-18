"""Quota-bounded current prop capture and exact within-book market pairing."""
from collections import defaultdict,Counter
from datetime import datetime,timezone,timedelta
import json,math
from pathlib import Path
from .providers.validation import ProviderValidator,SPORTS
from .providers.security import load_credentials
from .research_store import ResearchStore
from .integrity import digest,utc
from .odds import american_to_implied,devig_two_way
from .publication import atomic_json

PROP_KEYS={
 'NFL':{'player_receptions':'receptions','player_reception_yds':'receiving_yards','player_rush_attempts':'rushing_attempts','player_rush_yds':'rushing_yards','player_pass_yds':'passing_yards'},
 'NBA':{'player_points':'points','player_rebounds':'rebounds','player_assists':'assists','player_threes':'threes'},
 'NHL':{'player_shots_on_goal':'shots_on_goal','player_total_saves':'goalie_saves'},
 'MLB':{'pitcher_strikeouts':'pitcher_strikeouts','pitcher_outs':'pitcher_outs','pitcher_hits_allowed':'hits_allowed','batter_hits':'hitter_hits','batter_total_bases':'total_bases'}}


def normalize_props(store,manifest,sport,at):
    m=store.manifest(manifest['snapshot_id']);p=store.payload(m);out=[];rejected=Counter()
    if m['provider']!='odds' or m['parameters'].get('endpoint_status',200)!=200 or p.get('sport_key')!=SPORTS[sport] or not utc(m['available_at'])<=utc(at):
        raise ValueError('PROP_SOURCE_MISMATCH')
    for b in p.get('bookmakers',[]):
        for market in b['markets']:
            key=market['key']
            if key not in PROP_KEYS[sport]:rejected['UNSUPPORTED_PROP_MARKET']+=1;continue
            if market.get('period','full_game')!='full_game':rejected['PROP_PERIOD_MISMATCH']+=1;continue
            groups=defaultdict(list)
            for o in market['outcomes']:groups[(o.get('description'),o.get('point'))].append(o)
            quote=market.get('last_update',b.get('last_update'))
            for (player,line),sides in groups.items():
                if not player or isinstance(line,bool) or not isinstance(line,(float,int)) or not math.isfinite(line) or (line*2)%1:
                    rejected['INVALID_PROP_IDENTITY_OR_LINE']+=1;continue
                pair={o['name']:o for o in sides}
                if len(sides)!=2 or set(pair)!={'Over','Under'}:rejected['MISSING_PROP_COUNTERPART']+=1;continue
                try:
                    fair=devig_two_way(pair['Over']['price'],pair['Under']['price'])[0]
                    if quote is None or utc(quote)>utc(m['available_at']):raise ValueError('IMPOSSIBLE_QUOTE_TIMESTAMP')
                except ValueError:rejected['INVALID_PROP_PRICE_OR_TIMESTAMP']+=1;continue
                reasons=['BOOK_SETTLEMENT_RULE_UNVERIFIED','PLAYER_IDENTITY_UNVERIFIED']
                if not utc(m['available_at'])<=utc(at)<utc(p['commence_time']):reasons.append('EVENT_STARTED')
                if (utc(at)-utc(quote)).total_seconds()>180:reasons.append('STALE_PRICE')
                body=dict(sport=sport,odds_event_id=p['id'],event_start=p['commence_time'],home_team=p['home_team'],away_team=p['away_team'],
                    player_name=player,player_id=None,market=PROP_KEYS[sport][key],provider_market=key,period='full_game',line=line,
                    book=b['key'],over_odds=pair['Over']['price'],under_odds=pair['Under']['price'],
                    over_no_vig=fair,probability_basis='conditional_on_non_push' if float(line).is_integer() else 'binary_excluding_voids',
                    market_push_probability=None if float(line).is_integer() else 0.,
                    quote_timestamp=quote,captured_at=m['fetched_at'],snapshot_id=m['snapshot_id'],payload_hash=m['payload_hash'],
                    settlement_rule_id=None,reasons=reasons)
                body['quote_id']=digest(body);out.append(body)
    return out,dict(rejected)


def collect(root,*,daily_credit_cap=24,canonical_events=None,reserve_credits=50):
    if canonical_events is not None:
        return collect_nfl_slate(root,canonical_events,daily_credit_cap=daily_credit_cap,reserve_credits=reserve_credits)
    return collect_priority(root,daily_credit_cap=daily_credit_cap,reserve_credits=reserve_credits,
                            priority_markets={sport:list(keys) for sport,keys in PROP_KEYS.items()})


def future_research_events(events,at,minimum_lead_seconds=1800):
    if minimum_lead_seconds<0:raise ValueError('INVALID_PREGAME_LEAD')
    return sorted([e for e in events if utc(e['commence_time'])>utc(at)+timedelta(seconds=minimum_lead_seconds)],key=lambda e:(utc(e['commence_time']),e['id']))


def collection_interval(seconds_to_start):
    if seconds_to_start<=0:return 900
    if seconds_to_start<=300:return 60
    if seconds_to_start<=3600:return 900
    if seconds_to_start<=86400:return 3600
    return 21600


def collect_priority(root, *, daily_credit_cap=24, reserve_credits=50, cooldown_seconds=300, transport=None,
                     cadence_aware=False, minimum_lead_seconds=1800, canonical_deadlines=None, priority_markets=None,canonical_events=None):
    """Refresh a bounded priority cohort without erasing last-known observations.

    An incomplete/blocked refresh never makes a cached quote fresh. Each attempt
    records its requested market subset; successful empty responses supersede it.
    """
    if canonical_events is not None:
        return collect_nfl_slate(root,canonical_events,daily_credit_cap=daily_credit_cap,reserve_credits=reserve_credits,
                                 cooldown_seconds=cooldown_seconds,transport=transport)
    if daily_credit_cap<0 or reserve_credits<0 or cooldown_seconds<60:
        raise ValueError('INVALID_QUOTA_POLICY')
    root=Path(root);s=ResearchStore(root/'data');load_credentials(root/'.env')
    kwargs={} if transport is None else {'transport':transport}
    v=ProviderValidator(s,max_odds_credits=daily_credit_cap,**kwargs)
    path=s.root/'evaluations/prop-price-access.json'
    prior=json.loads(path.read_text()) if path.exists() else {'sports':[]}
    previous={r['sport']:r for r in prior['sports']};attempts=[];records=[]
    at=datetime.now(timezone.utc).isoformat()
    with v.ledger.connect() as db:
        used=db.execute('SELECT coalesce(sum(cost),0) FROM requests WHERE provider=? AND substr(requested_at,1,10)=?',('odds',at[:10])).fetchone()[0]
    priority={'NHL':['player_shots_on_goal','player_total_saves'], 'NBA':['player_rebounds','player_assists'],
              'MLB':['batter_hits','batter_total_bases'], 'NFL':['player_receptions','player_rush_attempts','player_reception_yds','player_pass_yds','player_rush_yds']}
    if priority_markets is not None:
        if set(priority_markets)!=set(priority) or any(not keys or len(keys)!=len(set(keys)) or any(k not in PROP_KEYS[s] for k in keys) for s,keys in priority_markets.items()):
            raise ValueError('INVALID_PRIORITY_MARKETS')
        priority=priority_markets
    for sport,keys in priority.items():
        old=previous.get(sport,{});record=dict(old) if old else {'sport':sport}
        old_event=old.get('event',{});deadline=(canonical_deadlines or {}).get(old_event.get('id'),old_event.get('commence_time'))
        lead=(utc(deadline)-utc(at)).total_seconds() if deadline else 86401
        interval=collection_interval(lead) if cadence_aware else cooldown_seconds
        previous_attempt=old.get('latest_attempt',{})
        last=old.get('last_request_at') or (previous_attempt.get('checked_at') if previous_attempt.get('status') not in ('REFRESH_COOLDOWN','DAILY_QUOTA_BUDGET_LIMIT') else None) or old.get('record',{}).get('checked_at')
        requested=False
        if last and (utc(at)-utc(last)).total_seconds()<interval:
            attempt=dict(sport=sport,status='REFRESH_COOLDOWN',checked_at=at)
        else:
            cap=max(0,daily_credit_cap-6) if cadence_aware and lead>900 else daily_credit_cap
            allowance=min(cap-used,max(0,(v.remaining or 0)-reserve_credits))
            chosen=keys[:max(0,allowance)]
            if not chosen:attempt=dict(sport=sport,status='DAILY_QUOTA_BUDGET_LIMIT',checked_at=at)
            elif sport=='NFL':
                from .nfl_schedule import next_slate
                try:
                    games=next_slate(root)
                    slate=collect_nfl_slate(root,games,daily_credit_cap=daily_credit_cap,reserve_credits=reserve_credits,
                        cooldown_seconds=cooldown_seconds,transport=transport)
                    used=slate['quota']['credits_used']
                    record=dict(sport='NFL',events=slate['events'],schedule_games=len(games),quota=slate['quota'],
                        latest_attempt=dict(sport='NFL',status='SLATE_PROCESSED',checked_at=slate['generated_at']),last_request_at=slate['generated_at'])
                    records.append(record);attempts.append(record['latest_attempt']);continue
                except (ValueError,KeyError,OSError,TypeError) as e:
                    attempt=dict(sport='NFL',status='SLATE_SOURCE_BLOCKED',checked_at=at,error_category=type(e).__name__)
            else:
                requested=True
                event_record,events=v.request('odds','sports/'+SPORTS[sport]+'/events',{'dateFormat':'iso'})
                upcoming=future_research_events(events,at,minimum_lead_seconds=minimum_lead_seconds) if isinstance(events,list) else []
                upcoming=[e for e in upcoming if utc((canonical_deadlines or {}).get(e['id'],e['commence_time']))>utc(at)]
                if not upcoming:attempt=dict(sport=sport,status='NO_UPCOMING_PROVIDER_EVENT',endpoint_status=event_record['status'],checked_at=at)
                else:
                    # NFL is handled by the canonical full-slate branch above.
                    event=upcoming[0]
                    new_lead=(utc((canonical_deadlines or {}).get(event['id'],event['commence_time']))-utc(at)).total_seconds()
                    new_cap=max(0,daily_credit_cap-6) if cadence_aware and new_lead>900 else daily_credit_cap
                    chosen=keys[:max(0,min(new_cap-used,max(0,(v.remaining or 0)-reserve_credits)))]
                    if not chosen:
                        record['last_request_at']=at
                        attempt=dict(sport=sport,status='DAILY_QUOTA_BUDGET_LIMIT',checked_at=at)
                        record['latest_attempt']=attempt;records.append(record);attempts.append(attempt);continue
                    r,_=v.request('odds','sports/'+SPORTS[sport]+'/events/'+event['id']+'/odds',
                        dict(markets=','.join(chosen),bookmakers='draftkings,fanduel,betmgm,betrivers,caesars',oddsFormat='american'),credit_cost=len(chosen))
                    used+=r.get('quota',{}).get('x-requests-last',len(chosen) if r['status']==200 else 0)
                    attempt=dict(sport=sport,status=r['status'],checked_at=r.get('checked_at',at),requested_markets=chosen,
                                 deferred_markets=[k for k in keys if k not in chosen],quota=r.get('quota',{}))
                    if r['status']==200:
                        qs,rejected=normalize_props(s,s.manifest(r['snapshot_id']),sport,r['checked_at'])
                        record=dict(sport=sport,record=r,status=200,event=event,paired_offers=len(qs),books=dict(Counter(q['book'] for q in qs)),
                                    unique_players=len({q['player_name'] for q in qs}),rejections=rejected)
        record['last_request_at']=attempt.get('checked_at',at) if requested else last
        record['latest_attempt']=attempt;records.append(record);attempts.append(attempt)
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),daily_credits_used=used,daily_cap=daily_credit_cap,
                selection_policy=f'NFL: complete canonical schedule date; other sports: earliest event with {minimum_lead_seconds}s lead; never price-selected',
                cadence_aware=cadence_aware,priority_markets=priority,sports=records)
    atomic_json(path,report);atomic_json(s.root/'evaluations/prop-priority-refresh.json',dict(generated_at=at,attempts=attempts,daily_credits_used=used))
    return report


def event_price_records(root,sport,event):
    """Select only explicit event snapshots; keep legacy single-event readers working."""
    root=Path(root);p=root/'data/evaluations/nfl-slate-price-access.json'
    if sport=='NFL' and p.exists():
        row=json.loads(p.read_text()).get('events',{}).get(event['event_id'])
        if row is not None:
            return list({r['snapshot_id']:r for r in row.get('records',{}).values() if r.get('status')==200}.values())
    p=root/'data/evaluations/prop-price-access.json'
    if not p.exists():return []
    rows=[r for r in json.loads(p.read_text()).get('sports',[]) if r['sport']==sport
          and r.get('event',{}).get('id')==event.get('odds_event_id')]
    return [r['record'] for r in rows if r.get('record',{}).get('status')==200]


def collect_nfl_slate(root,games,*,daily_credit_cap=24,reserve_credits=50,cooldown_seconds=300,transport=None):
    """Featured slate first, then one prop market per event in round-robin waves.

    Cost is reserved pessimistically before each request, then reconciled to actual
    headers. Missing/empty books and budget deferrals stay on their canonical game.
    Caller holds the shared research-runner lock for the whole operation.
    """
    from .nfl_schedule import match_odds
    if daily_credit_cap<0 or reserve_credits<0 or cooldown_seconds<60:raise ValueError('INVALID_QUOTA_POLICY')
    root=Path(root);s=ResearchStore(root/'data');load_credentials(root/'.env')
    v=ProviderValidator(s,max_odds_credits=daily_credit_cap,**({} if transport is None else {'transport':transport}))
    at=datetime.now(timezone.utc).isoformat();path=s.root/'evaluations/nfl-slate-price-access.json'
    prior=json.loads(path.read_text()) if path.exists() else {}
    def used():
        with v.ledger.connect() as db:
            return db.execute('SELECT coalesce(sum(cost),0) FROM requests WHERE provider=? AND substr(requested_at,1,10)=?',('odds',at[:10])).fetchone()[0]
    initial=used();unaccounted=0;quota_known=True;report=dict(generated_at=at,events={},requests=[],featured=None,
        quota=dict(credits_used=initial,daily_cap=daily_credit_cap,remaining=v.remaining,reserved_balance=reserve_credits),
        policy='Featured slate then receptions, receiving yards, passing yards, rush attempts, rush yards; every game per wave')
    def save():
        report['quota'].update(credits_used=used()+unaccounted,credits_used_this_sweep=used()+unaccounted-initial,remaining=v.remaining,
                               quota_headers_verified=quota_known)
        atomic_json(path,report)
    er,events=v.request('odds','sports/'+SPORTS['NFL']+'/events',{'dateFormat':'iso'});report['requests'].append(er)
    quota_known=er.get('quota',{}).get('x-requests-remaining') is not None
    events=events if isinstance(events,list) else []
    for g in games:
        e,reason=match_odds(g,events);old=prior.get('events',{}).get(g['event_id'],{})
        report['events'][g['event_id']]=dict(event=e,canonical_event_id=g['event_id'],identity_reason=reason,
            records=old.get('records',{}) if e and (old.get('event') or {}).get('id')==e['id'] else {},attempts={},
            main_market_status='NOT_REQUESTED',prop_market_status='NOT_REQUESTED')
    def request(endpoint,params,cost,previous=None):
        nonlocal unaccounted,quota_known
        now=datetime.now(timezone.utc).isoformat()
        if previous and previous.get('checked_at') and (utc(now)-utc(previous['checked_at'])).total_seconds()<cooldown_seconds:
            return dict(previous,cached=True),s.payload(s.manifest(previous['snapshot_id'])) if previous.get('status')==200 else None
        if not quota_known or used()+unaccounted+cost>daily_credit_cap or v.remaining is None or v.remaining-cost<reserve_credits:
            return dict(status='BUDGET_DEFERRED',checked_at=now,requested_markets=params.get('markets')),None
        r,p=v.request('odds',endpoint,params,credit_cost=cost);report['requests'].append(r)
        if r.get('quota',{}).get('x-requests-last') is None:unaccounted+=cost;quota_known=False
        if r.get('quota',{}).get('x-requests-remaining') is None:quota_known=False
        save();return r,p
    params=dict(markets='h2h,spreads,totals',bookmakers='draftkings,fanduel,betmgm,betrivers,caesars',oddsFormat='american')
    r,p=request('sports/'+SPORTS['NFL']+'/odds',params,3,prior.get('featured'))
    report['featured']=r
    for g in games:
        row=report['events'][g['event_id']];match,reason=match_odds(g,p if isinstance(p,list) else [])
        row['main_market_status']=('FETCHED' if match and match.get('bookmakers') else 'NO_MARKET') if r['status']==200 else ('BUDGET_DEFERRED' if r['status']=='BUDGET_DEFERRED' else 'FAILED')
        row['main_identity_reason']=reason
    keys=['player_receptions','player_reception_yds','player_pass_yds','player_rush_attempts','player_rush_yds']
    for key in keys:
        for g in games:
            row=report['events'][g['event_id']];e=row['event']
            if not e:row['attempts'][key]=dict(status='NO_MARKET',reason=row['identity_reason']);continue
            if utc(g['kickoff'])<=datetime.now(timezone.utc):row['attempts'][key]=dict(status='EVENT_STARTED');continue
            params=dict(markets=key,bookmakers='draftkings,fanduel,betmgm,betrivers,caesars',oddsFormat='american')
            r,p=request('sports/'+SPORTS['NFL']+'/events/'+e['id']+'/odds',params,1,row['records'].get(key))
            if r['status']==200:
                matched,_=match_odds(g,[p] if isinstance(p,dict) and all(k in p for k in ('home_team','away_team','commence_time')) else [])
                if matched is None or p.get('id')!=e['id'] or p.get('sport_key')!=SPORTS['NFL']:
                    r=dict(r,status='EVENT_RESPONSE_IDENTITY_MISMATCH');p=None
            returned=sorted({m['key'] for b in (p or {}).get('bookmakers',[]) for m in b.get('markets',[])}) if isinstance(p,dict) else []
            row['attempts'][key]=dict(status=r['status'],checked_at=r.get('checked_at'),returned_markets=returned,
                books=sorted({b['key'] for b in (p or {}).get('bookmakers',[])}) if isinstance(p,dict) else [],cached=r.get('cached',False))
            if r['status']==200:row['records'][key]=r
            save()
    for row in report['events'].values():
        states=[a['status'] for a in row['attempts'].values()]
        nonempty=any(a.get('returned_markets') for a in row['attempts'].values())
        row['prop_market_status']='SCANNED' if nonempty else ('BUDGET_DEFERRED' if 'BUDGET_DEFERRED' in states else ('NO_MARKET' if all(s in (200,'NO_MARKET') for s in states) else 'FAILED'))
        row['deferred_markets']=[k for k,a in row['attempts'].items() if a['status']=='BUDGET_DEFERRED']
        row['unavailable_markets']=[k for k,a in row['attempts'].items() if a['status'] in (200,'NO_MARKET') and not a.get('returned_markets')]
    save();return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--priority',action='store_true');args=p.parse_args()
    print(json.dumps((collect_priority if args.priority else collect)(args.root),indent=2))
