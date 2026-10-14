"""Explicit provider identities; no fuzzy team joins or retrospective availability guesses."""
from ..integrity import utc
from ..models.base import MarketContext
from ..odds import american_to_decimal

def odds_contexts(payload, manifest, *, prediction_at, event_mapping):
    if not manifest.get('available_at'): raise ValueError('HISTORICAL_AVAILABILITY_UNVERIFIED')
    historical=manifest['availability_basis']=='historical_odds_snapshot'
    events=payload['data'] if historical else payload
    if historical and utc(payload['timestamp'])!=utc(manifest['observed_at']): raise ValueError('SNAPSHOT_TIMESTAMP_MISMATCH')
    out=[]; rejections=[]
    for event in events:
        mapping=event_mapping.get(event['id'])
        if not mapping or (mapping['home_team'],mapping['away_team'])!=(event['home_team'],event['away_team']):
            rejections.append(dict(provider_event_id=event['id'],reason='EVENT_MAPPING_UNVERIFIED')); continue
        for book in event.get('bookmakers',[]):
            for market in book.get('markets',[]):
                kind={'spreads':'spread','totals':'total','h2h':'win'}.get(market['key'])
                if kind is None: continue
                outcomes=market.get('outcomes',[])
                labels=('Over','Under') if kind=='total' else (event['home_team'],event['away_team'])
                pair={r['name']:r for r in outcomes}
                try:
                    if len(outcomes)!=2 or any(label not in pair for label in labels): raise ValueError('MISSING_MARKET_PAIR')
                    a,b=(pair[label] for label in labels)
                    american_to_decimal(a['price']); american_to_decimal(b['price'])
                    line=a.get('point'); other=b.get('point')
                    if kind=='spread' and (line is None or other is None or line!=-other): raise ValueError('MISSING_MARKET_PAIR')
                    if kind=='total' and (line is None or line!=other): raise ValueError('MISSING_MARKET_PAIR')
                    quote=market.get('last_update') or book['last_update']
                    if utc(quote)>utc(manifest['available_at']): raise ValueError('LOOKAHEAD_RISK')
                    c=MarketContext(mapping['event_id'],'CFB',kind,'over' if kind=='total' else 'home',book['key'],line,a['price'],b['price'],prediction_at,quote,event['commence_time'],manifest['snapshot_id'],line,manifest['available_at'])
                    c.validate(); out.append(c)
                except (ValueError,KeyError,TypeError) as e:
                    rejections.append(dict(provider_event_id=event['id'],book=book['key'],market=kind,reason=str(e)))
    return out,rejections

def canonical_cfbd_results(payload, manifest):
    rows=[]
    for g in payload:
        final=g.get('completed') is True
        rows.append(dict(event_id=str(g['id']),home_team=g['homeTeam'],away_team=g['awayTeam'],
            event_timestamp=g['startDate'],home_score=g.get('homePoints'),away_score=g.get('awayPoints'),
            status='final' if final else 'unsettled',overtime=g.get('overtime'),
            result_available_at=manifest.get('available_at'),snapshot_id=manifest['snapshot_id'],payload_hash=manifest['payload_hash']))
    return rows

def require_historical_availability(manifest,as_of):
    if not manifest.get('available_at') or utc(manifest['available_at'])>utc(as_of):
        raise ValueError('HISTORICAL_AVAILABILITY_UNVERIFIED')
    # CORE/season advanced data cannot be retroactively dated by a week/year filter.
    if manifest.get('endpoint') in ('ratings/core','stats/game/advanced') and manifest.get('availability_basis')!='recorded_response':
        raise ValueError('HISTORICAL_AVAILABILITY_UNVERIFIED')
