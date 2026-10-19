"""Reconstruct an independent, contemporaneous CFB sportsbook benchmark.

Read the original whole response, not a caller-supplied consensus probability.
One snapshot, exact event/start/period/line, paired prices, one vote per book.
"""
import statistics
from .integrity import utc
from .odds import devig_two_way
from .providers.normalize import odds_contexts


def verified_consensus(store,row):
    c=row.context;m=store.manifest(c.snapshot_id);payload=store.payload(m)
    if m['provider']!='odds' or m['parameters'].get('endpoint_status',200)!=200:
        raise ValueError('BENCHMARK_SOURCE_MISMATCH')
    at=utc(c.snapshot_available_at or c.quote_timestamp)
    if not m['available_at'] or utc(m['available_at'])!=at:raise ValueError('BENCHMARK_AVAILABILITY_MISMATCH')
    if not utc(c.quote_timestamp)<=at<utc(c.event_timestamp):raise ValueError('LOOKAHEAD_RISK')
    events=payload['data'] if isinstance(payload,dict) else payload
    mapping=row.event_mapping
    if not mapping:raise ValueError('BENCHMARK_EVENT_MAPPING_REQUIRED')
    matching=[e for e in events if (e['home_team'],e['away_team'],utc(e['commence_time']))==
              (mapping['home_team'],mapping['away_team'],utc(c.event_timestamp))]
    if len(matching)!=1:raise ValueError('BENCHMARK_EVENT_IDENTITY_MISMATCH')
    event=matching[0];books={};excluded=[]
    key={'spread':'spreads','total':'totals','win':'h2h'}[c.market_type]
    for book in event.get('bookmakers',[]):
        if book['key']==c.book:continue
        for market in book.get('markets',[]):
            if market['key']!=key or market.get('period','full_game')!='full_game':continue
            quote=market.get('last_update',book.get('last_update'))
            if quote is None or not 0<=(at-utc(quote)).total_seconds()<=180:
                excluded.append(dict(book=book['key'],reason='STALE_OR_FUTURE_BENCHMARK_QUOTE'));continue
            subset=[dict(event,bookmakers=[dict(book,markets=[market])])]
            p=dict(payload,data=subset) if isinstance(payload,dict) else subset
            contexts,failures=odds_contexts(p,m,prediction_at=quote,event_mapping={event['id']:mapping})
            if not contexts:
                excluded.append(dict(book=book['key'],reason='MISSING_OR_INVALID_BENCHMARK_PAIR'));continue
            b=contexts[0]
            if c.selection not in ('home','over'):raise ValueError('UNSUPPORTED_BENCHMARK_DIRECTION')
            if (b.market_type,b.selection,b.line)!=(c.market_type,c.selection,c.line):
                excluded.append(dict(book=book['key'],reason='BENCHMARK_LINE_MISMATCH'));continue
            evidence=dict(book=b.book,line=b.line,odds=b.odds,opposite_odds=b.opposite_odds,
                quote_timestamp=b.quote_timestamp,available_at=m['available_at'],snapshot_id=m['snapshot_id'],
                payload_hash=m['payload_hash'],probability=devig_two_way(b.odds,b.opposite_odds)[0])
            if b.book in books and books[b.book]!=evidence:
                return dict(probability=None,reason='CONFLICTING_BENCHMARK_BOOK',book_count=0,quotes=[],excluded=excluded)
            books[b.book]=evidence
    values=list(books.values())
    push_capable=c.market_type in ('spread','total') and c.line==int(c.line)
    return dict(probability=statistics.median(v['probability'] for v in values) if len(values)>=2 else None,
        reason=None if len(values)>=2 else 'INSUFFICIENT_CONTEMPORANEOUS_BOOKS',book_count=len(values),
        method='median_two_way_no_vig_excluding_execution_book',
        probability_basis='conditional_on_non_push' if push_capable else 'binary_no_push',
        push_probability=None if push_capable else 0,as_of=at.isoformat(),quotes=sorted(values,key=lambda x:x['book']),excluded=excluded)
