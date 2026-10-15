"""Descriptive price calculations only. Never grants model or wager authority."""
import math
from .integrity import utc
from .odds import american_to_decimal, american_to_implied, devig_two_way


def probability(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
        raise ValueError('INVALID_PROBABILITY')
    return value


def outcome_ev(win, loss, push, odds):
    """Profit per unit staked; push returns the stake and contributes zero."""
    for value in (win,loss,push):probability(value)
    if not math.isclose(win+loss+push,1,abs_tol=1e-9,rel_tol=0):raise ValueError('INVALID_OUTCOME_MASS')
    return win*(american_to_decimal(odds)-1)-loss


def conditional_ev(p, odds, push):
    """Convert a non-push conditional probability to unconditional outcome mass."""
    probability(p);probability(push)
    return outcome_ev(p*(1-push),(1-p)*(1-push),push,odds)


def opposite_side(quote, group):
    # A matching pair_id is necessary, but never sufficient evidence by itself.
    if len(group)!=2 or not quote.get('pair_id'):return None
    other=next((r for r in group if r.get('quote_id')!=quote.get('quote_id')),None)
    if other is None:return None
    same=('provider','sport','event_id','event_start','home_team','away_team','book','market','period',
          'snapshot_id','raw_payload_hash','pair_id','settlement_rule_id')
    if any(quote.get(k)!=other.get(k) for k in same):return None
    if not quote.get('period') or not quote.get('snapshot_id') or not quote.get('raw_payload_hash'):return None
    try:
        if any(utc(quote[k])!=utc(other[k]) for k in ('observed_at','available_at')):return None
        expected={'Over','Under'} if quote['market']=='totals' else {quote['home_team'],quote['away_team']}
        if len(expected)!=2 or {quote['selection'],other['selection']}!=expected:return None
        a,b=quote.get('line'),other.get('line')
        if quote['market']=='h2h':return other if a is None and b is None else None
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (a,b)):return None
        if quote['market']=='spreads' and a==-b:return other
        if quote['market']=='totals' and a==b:return other
    except (KeyError,ValueError,TypeError):pass
    return None


def push_policy(quote):
    """Standard settled-game conventions, excluding voids; not book-rule proof.

    Integer score lines can push. NFL two-way ML and partial-game ML can tie.
    Quarter lines/unknown sports have unsupported payout semantics, not zero push.
    """
    sport=quote.get('sport');market=quote.get('market');line=quote.get('line')
    if sport not in ('CFB','NFL','NHL','MLB','NBA'):return 'UNKNOWN'
    if market=='h2h':
        if line is not None:return 'UNKNOWN'
        return 'NO_PUSH' if quote.get('period')=='full_game' and sport!='NFL' else 'PUSH_POSSIBLE'
    if market not in ('spreads','totals') or isinstance(line,bool) or not isinstance(line,(int,float)) or not math.isfinite(line):return 'UNKNOWN'
    if float(line).is_integer():return 'PUSH_POSSIBLE'
    if float(line*2).is_integer():return 'NO_PUSH'
    return 'UNKNOWN'


def market_calculations(quote, opposite):
    policy=push_policy(quote);push=0.0 if policy=='NO_PUSH' else None
    out=dict(decimal_odds=None,market_implied_probability=None,market_no_vig_probability=None,
        market_baseline_ev=None,market_conditional_ev=None,market_win_probability=None,
        market_loss_probability=None,market_push_probability=push,push_policy=policy,
        market_probability_basis='WIN_EXCLUDING_VOIDS' if policy=='NO_PUSH' else 'CONDITIONAL_ON_NON_PUSH' if policy=='PUSH_POSSIBLE' else 'UNVERIFIED_PRICE_NORMALIZATION',
        market_ev_basis='STANDARD_SETTLED_GAME_EXCLUDING_VOIDS' if policy=='NO_PUSH' else 'PUSH_PROBABILITY_UNKNOWN',
        calculation_reasons=[])
    reasons=out['calculation_reasons']
    try:
        out['decimal_odds']=american_to_decimal(quote['american_odds'])
        out['market_implied_probability']=american_to_implied(quote['american_odds'])
    except (ValueError,KeyError):reasons.append('INVALID_ODDS');return out
    if policy!='NO_PUSH':reasons.append('PUSH_PROBABILITY_UNKNOWN' if policy=='PUSH_POSSIBLE' else 'UNSUPPORTED_PAYOUT_RULE')
    if opposite is None:reasons.append('NO_MARKET_PAIR');return out
    try:p=devig_two_way(quote['american_odds'],opposite['american_odds'])[0]
    except (ValueError,KeyError):reasons.append('INVALID_OPPOSITE_ODDS');return out
    out['market_no_vig_probability']=p
    # Conditional EV is separately labelled, never masquerades as unconditional.
    if policy!='UNKNOWN':out['market_conditional_ev']=conditional_ev(p,quote['american_odds'],0)
    if push is not None:
        out.update(market_win_probability=p,market_loss_probability=1-p,
            market_baseline_ev=conditional_ev(p,quote['american_odds'],push))
    return out


def dashboard_market(row, at):
    """Stable requested columns; null AP fields remain null at the UI boundary."""
    pct=lambda key:None if row.get(key) is None else round(100*row[key],3)
    age=(utc(at)-utc(row['quote_timestamp'])).total_seconds()
    reasons=list(row['pass_reason'])
    if age>180 and 'STALE_PRICE' not in reasons:reasons.insert(0,'STALE_PRICE')
    kind='MARKET BASELINE ONLY' if row.get('model_probability') is None else 'UNVALIDATED RESEARCH MODEL'
    status='PASS: STALE_PRICE' if 'STALE_PRICE' in reasons else 'PASS: '+kind
    return {'Sport':row['sport'],'Game':row['away_team']+' @ '+row['home_team'],
        'Market':{'h2h':'Moneyline','spreads':'Spread','totals':'Total'}.get(row['market'],row['market']),
        'Selection':row['selection'],'Book':row['book'],'Line':row['line'],'Odds':row['odds'],
        'Break-even %':pct('market_implied_probability'),'Market no-vig %':pct('market_no_vig_probability'),
        'Market-baseline EV %':pct('market_baseline_ev'),'AP raw probability %':pct('model_probability'),
        'AP calibrated probability %':pct('calibrated_probability'),'AP p_low %':pct('p_low'),
        'AP model EV %':pct('ap_model_expected_value'),
        'Data quality':'STALE' if age>180 else row.get('data_quality','UNVERIFIED'),
        'Quote age':round(age/60,2),'Status':status,'PASS reason':', '.join(reasons),
        'Probability source':kind,'Probability basis':row.get('market_probability_basis'),
        'Conditional market EV % (non-push)':pct('market_conditional_ev'),
        'Market p_push %':pct('market_push_probability'),'AP p_push %':pct('ap_push_probability'),
        'Period':row.get('period'),'Quote time (UTC)':row['quote_timestamp'],'Event start (UTC)':row['event_start']}
