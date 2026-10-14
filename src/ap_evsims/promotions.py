"""Pure promotion payoff arithmetic; probabilities and decision authority are unchanged."""
import math
from .odds import american_to_decimal

def promotion_ev(*,p_win,p_push,odds,stake,kind='cash',boost_fraction=0,refund_cap=0,
                 refund_conversion=None,terms_verified=False):
    values=(p_win,p_push,stake,boost_fraction,refund_cap)
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in values):raise ValueError('INVALID_PROMOTION_INPUT')
    if not 0<=p_win<=1 or not 0<=p_push<=1 or p_win+p_push>1 or min(stake,boost_fraction,refund_cap)<0:raise ValueError('INVALID_PROMOTION_INPUT')
    if not terms_verified:raise ValueError('PROMOTION_TERMS_UNVERIFIED')
    if kind not in ('cash','profit_boost','free_bet','no_sweat'):raise ValueError('UNKNOWN_PROMOTION')
    b=american_to_decimal(odds)-1;loss=1-p_win-p_push
    win_cash=stake*b*(1+boost_fraction if kind=='profit_boost' else 1)
    if kind=='free_bet':
        # Unused/returned promotional stake is not cash profit.
        expected=p_win*win_cash;refund_value=None
    else:
        expected=p_win*win_cash-loss*stake;refund_value=0
    if kind=='no_sweat':
        if refund_conversion is None or not math.isfinite(refund_conversion) or not 0<=refund_conversion<=1:raise ValueError('BONUS_CONVERSION_UNVERIFIED')
        refund_value=min(stake,refund_cap)*refund_conversion;expected+=loss*refund_value
    return dict(expected_cash_profit=expected,normal_cash_ev=p_win*stake*b-loss*stake,
        p_win=p_win,p_push=p_push,refund_value_assumption=refund_value,account='bonus' if kind=='free_bet' else 'cash',
        decision='RESEARCH_ONLY',phase1_eligibility_unchanged=True)
