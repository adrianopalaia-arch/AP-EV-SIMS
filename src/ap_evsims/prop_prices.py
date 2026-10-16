"""Quota-bounded current prop capture and exact within-book market pairing."""
from collections import defaultdict,Counter
from datetime import datetime,timezone
import json,math
from pathlib import Path
from .providers.validation import ProviderValidator,SPORTS
from .providers.security import load_credentials
from .research_store import ResearchStore
from .integrity import digest,utc
from .odds import american_to_implied,devig_two_way

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


def collect(root,*,daily_credit_cap=24):
    root=Path(root);s=ResearchStore(root/'data');load_credentials(root/'.env');v=ProviderValidator(s,max_odds_credits=16)
    records=[];at=datetime.now(timezone.utc).isoformat()
    with v.ledger.connect() as db:
        used=db.execute('SELECT coalesce(sum(cost),0) FROM requests WHERE provider=? AND requested_at>=?',('odds',utc(at).date().isoformat())).fetchone()[0]
    for sport,keys in PROP_KEYS.items():
        event_record,events=v.request('odds','sports/'+SPORTS[sport]+'/events',dict(dateFormat='iso'))
        upcoming=sorted([e for e in events if utc(e['commence_time'])>utc(at)],key=lambda e:(utc(e['commence_time']),e['id'])) if isinstance(events,list) else []
        if not upcoming:records.append(dict(sport=sport,status='NO_UPCOMING_PROVIDER_EVENT',event_status=event_record['status']));continue
        cost=len(keys)
        if used+cost>daily_credit_cap:records.append(dict(sport=sport,status='DAILY_QUOTA_BUDGET_LIMIT'));continue
        event=upcoming[0];params=dict(markets=','.join(keys),bookmakers='draftkings,fanduel,betmgm,betrivers,caesars',oddsFormat='american')
        r,p=v.request('odds','sports/'+SPORTS[sport]+'/events/'+event['id']+'/odds',params,credit_cost=cost)
        used+=r.get('quota',{}).get('x-requests-last',cost if r['status']==200 else 0)
        if r['status']==200:
            m=s.manifest(r['snapshot_id']);qs,rejected=normalize_props(s,m,sport,r['checked_at'])
        else:qs=[];rejected={}
        records.append(dict(sport=sport,record=r,status=r['status'],event=event,paired_offers=len(qs),
            books=dict(Counter(q['book'] for q in qs)),unique_players=len({q['player_name'] for q in qs}),rejections=rejected))
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),daily_credits_used=used,daily_cap=daily_credit_cap,
        selection_policy='earliest future event per sport; fixed markets; no favorable-price search',sports=records)
    (s.root/'evaluations/prop-price-access.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');args=p.parse_args();print(json.dumps(collect(args.root),indent=2))
