"""Source-verified quotes and conservative cross-book/closing comparisons."""
from collections import defaultdict
import statistics
from .integrity import utc, digest
from .display_pricing import opposite_side, market_calculations
from .odds import american_to_implied


def family(q):
    return (q['sport'], q['event_id'], utc(q['event_start']).isoformat(), q['market'], q['period'], q['selection'])


def archived_quotes(store, warehouse, at):
    """Do not treat a mutable warehouse row or claimed hash as source verification."""
    with warehouse.connect() as db:
        result=db.execute("SELECT * FROM odds_quotes WHERE sport='CFB' AND available_at<=? AND ingested_at<=? ORDER BY available_at,quote_id",[at,at])
        names=[c[0] for c in result.description];quotes=[dict(zip(names,row)) for row in result.fetchall()]
    manifests={};payloads={};out=[]
    for q in quotes:
        sid=q['snapshot_id']
        if sid not in manifests:
            m=store.manifest(sid);manifests[sid]=m;p=store.payload(m)
            payloads[sid]={e['id']:e for e in (p['data'] if isinstance(p,dict) else p)}
        m=manifests[sid];event=payloads[sid].get(q['event_id'].removeprefix('odds:'))
        if m['provider']!='odds' or m['parameters'].get('endpoint_status',200)!=200 or event is None:raise ValueError('QUOTE_SOURCE_MISMATCH')
        if (event['home_team'],event['away_team'],utc(event['commence_time']),event['sport_key'])!=(q['home_team'],q['away_team'],utc(q['event_start']),'americanfootball_ncaaf'):
            raise ValueError('QUOTE_SOURCE_MISMATCH')
        if (q['raw_payload_hash'],utc(q['available_at']),utc(q['ingested_at']))!=(m['payload_hash'],utc(m['available_at']),utc(m['fetched_at'])):
            raise ValueError('QUOTE_SOURCE_MISMATCH')
        found=False
        for b in event['bookmakers']:
            if b['key']!=q['book']:continue
            for market in b['markets']:
                if (market['key'],market.get('period','full_game'))!=(q['market'],q['period']):continue
                observed=market.get('last_update',b.get('last_update'))
                for o in market['outcomes']:
                    if (o['name'],o.get('point'),o['price'],utc(observed))!=(q['selection'],q['line'],q['american_odds'],utc(q['observed_at'])):continue
                    series=digest([q['sport'],event['id'],utc(q['event_start']).isoformat(),q['book'],q['market'],q['period'],q['selection']])
                    # Preserve raw numeric representation when reproducing the
                    # ingestion hash (JSON integer 4 is not JSON float 4.0).
                    identity=digest([series,o.get('point'),o['price'],observed,m['available_at'],sid])
                    if identity!=q['quote_id'] or q['pair_id']!=digest([sid,event['id'],q['book'],market]):raise ValueError('QUOTE_SOURCE_MISMATCH')
                    found=True
        if not found:raise ValueError('QUOTE_SOURCE_MISMATCH')
        out.append({k:utc(v).isoformat() if k in ('event_start','observed_at','available_at','ingested_at') else v for k,v in q.items()})
    return out


def fresh(q,at,max_age=180):
    return (utc(q['observed_at'])<=utc(q['available_at'])<=utc(q['ingested_at'])<=utc(at)<utc(q['event_start'])
            and 0<=(utc(at)-utc(q['observed_at'])).total_seconds()<=max_age)


def consensus(anchor,quotes,at):
    """Median no-vig probability, equal book weight, >=2 books excluding DK.

    Exact line/period/side matching is required. Shared books are not independent
    samples, and price disagreement is never interpreted as a model edge.
    """
    pairs=defaultdict(list)
    for q in quotes:pairs[q['pair_id']].append(q)
    books={}
    for q in quotes:
        if q['book']==anchor['book'] or family(q)!=family(anchor) or q['line']!=anchor['line'] or not fresh(q,at):continue
        other=opposite_side(q,pairs[q['pair_id']]);calc=market_calculations(q,other)
        if calc['market_no_vig_probability'] is None or calc['push_policy']=='UNKNOWN':continue
        previous=books.get(q['book'])
        if previous is None or utc(q['observed_at'])>utc(previous[0]['observed_at']):books[q['book']]=(q,calc)
        elif utc(q['observed_at'])==utc(previous[0]['observed_at']) and calc['market_no_vig_probability']!=previous[1]['market_no_vig_probability']:
            return dict(probability=None,book_count=len(books),reason='CONFLICTING_BOOK_QUOTES',quotes=[])
    values=[c['market_no_vig_probability'] for q,c in books.values()]
    return dict(probability=statistics.median(values) if len(values)>=2 else None,book_count=len(values),
        reason=None if len(values)>=2 else 'INSUFFICIENT_CONTEMPORANEOUS_BOOKS',method='median_two_way_no_vig_excluding_entry_book',
        probability_basis=market_calculations(anchor,None)['market_probability_basis'],
        quotes=[dict(book=b,quote_id=q['quote_id'],snapshot_id=q['snapshot_id'],line=q['line'],odds=q['american_odds'],
                     probability=c['market_no_vig_probability'],observed_at=q['observed_at']) for b,(q,c) in sorted(books.items())])


def closing_evidence(store,entry,quotes,at):
    """Near-start last captured price; never claims the exchange's true close."""
    if utc(at)<utc(entry['event_start']):return dict(reason='EVENT_NOT_STARTED',closing_price=None,point_clv=None,price_clv=None)
    history=[q for q in quotes if family(q)==family(entry) and q['book']==entry['book'] and utc(q['available_at'])<utc(entry['event_start'])]
    last=max(history,key=lambda q:(utc(q['available_at']),utc(q['observed_at']),q['quote_id']),default=None)
    base=dict(closing_price=None,last_observed_pregame=last,point_clv=None,price_clv=None,
              definition='last verified capture within 5 minutes before start; not proof of true book close')
    if last is None or not 0<(utc(entry['event_start'])-utc(last['observed_at'])).total_seconds()<=300:
        return dict(base,reason='MISSING_NEAR_START_CLOSE')
    # A newer full snapshot omitting the market means suspended/unavailable.
    for path in (store.root/'manifests').glob('*.json'):
        import json
        m=json.loads(path.read_text(encoding='utf-8'))
        if m['provider']!='odds' or m['endpoint']!='sports/americanfootball_ncaaf/odds' or m['parameters'].get('endpoint_status',200)!=200 or not m.get('available_at'):continue
        params={k:v for k,v in m['parameters'].items() if k not in ('endpoint_status','error_payload_sanitized')}
        if params and (params.get('regions')!='us' or set(params.get('markets','').split(','))!={'h2h','spreads','totals'} or 'bookmakers' in params):continue
        if utc(last['available_at'])<utc(m['available_at'])<utc(entry['event_start']) and utc(m['fetched_at'])<=utc(at):
            store.manifest(m['snapshot_id'])
            return dict(base,reason='MARKET_NOT_AVAILABLE_AT_LAST_CAPTURE')
    pair=[q for q in quotes if q['pair_id']==last['pair_id']]
    other=opposite_side(last,pair);p=market_calculations(last,other)['market_no_vig_probability']
    if p is None:return dict(base,reason='MISSING_CLOSING_PAIR')
    point=None
    if entry['market']=='spreads':point=entry['line']-last['line']
    if entry['market']=='totals':point=(last['line']-entry['line'])*(1 if entry['selection']=='Over' else -1)
    comparable=entry['line']==last['line']
    return dict(base,closing_price=last,point_clv=point,price_clv=p-american_to_implied(entry['american_odds']) if comparable else None,
                price_clv_basis='closing no-vig probability minus entry break-even; conditional on non-push when applicable',
                reason=None if comparable else 'DIFFERENT_LINES_PRICE_CLV_NOT_COMPARABLE')
