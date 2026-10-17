"""Only compare identical market lines; price and point CLV are distinct."""
import statistics
from .integrity import utc
from .odds import devig_two_way,american_to_implied

def market_consensus(contexts, *, as_of):
    groups={}
    for c in contexts:
        c.validate()
        if utc(c.quote_timestamp)>utc(as_of): raise ValueError('LOOKAHEAD_RISK')
        key=(c.event_id,c.market_type,c.selection,c.line)
        books=groups.setdefault(key,{})
        if c.book not in books or utc(c.quote_timestamp)>utc(books[c.book].quote_timestamp): books[c.book]=c
    return [dict(event_id=key[0],market=key[1],selection=key[2],line=key[3],
        no_vig_probability=statistics.median(devig_two_way(c.odds,c.opposite_odds)[0] for c in books.values()),
        books=sorted(books),book_count=len(books),quotes={b:dict(odds=c.odds,quote_timestamp=c.quote_timestamp,snapshot_id=c.snapshot_id) for b,c in books.items()})
        for key,books in groups.items()]

def movement(history, *, as_of):
    eligible=[c for c in history if utc(c.quote_timestamp)<=utc(as_of)]
    if not eligible: return None
    identity={(c.event_id,c.market_type,c.selection,c.book) for c in eligible}
    if len(identity)!=1: raise ValueError('MARKET_MOVEMENT_IDENTITY_MISMATCH')
    ordered=sorted(eligible,key=lambda c:utc(c.quote_timestamp)); a,b=ordered[0],ordered[-1]
    return dict(first_observed_quote=a.__dict__,current_quote=b.__dict__,true_opener_verified=False,
        line_movement=None if a.line is None else b.line-a.line,price_implied_movement=american_to_implied(b.odds)-american_to_implied(a.odds))

def closing_line_value(entry,closing):
    if closing is None: return dict(point_clv=None,price_clv=None,reason='MISSING_CLOSING_PRICE')
    if (entry.event_id,entry.market_type,entry.selection)!=(closing.event_id,closing.market_type,closing.selection): raise ValueError('CLOSING_MARKET_MISMATCH')
    closing.validate()
    if utc(closing.quote_timestamp)<utc(entry.quote_timestamp): raise ValueError('INVALID_CLOSING_TIMESTAMP')
    point=None
    if entry.market_type=='spread': point=entry.line-closing.line
    if entry.market_type=='total': point=closing.line-entry.line if entry.selection=='over' else entry.line-closing.line
    price=devig_two_way(closing.odds,closing.opposite_odds)[0]-american_to_implied(entry.odds) if entry.line==closing.line else None
    return dict(point_clv=point,price_clv=price,reason=None if price is not None else 'DIFFERENT_LINES_PRICE_CLV_NOT_COMPARABLE')
