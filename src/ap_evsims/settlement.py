"""Explicit versioned rules and payoff arithmetic. Unknown rules never grade a wager."""
from dataclasses import dataclass
import math
from .integrity import digest,utc
from .odds import american_to_decimal

@dataclass(frozen=True)
class SettlementRule:
    book:str
    sport:str
    market:str
    period:str
    overtime_included:bool
    push_allowed:bool
    nonparticipant_void:bool
    minimum_participation:float
    listed_starter_required:bool
    source:str
    available_at:str
    version:str
    @property
    def rule_id(self):return digest(self.__dict__)

def grade(rule, *, context,observed_stat,final_status,decision_at,participation=None,listed_starter_matches=None):
    if rule is None:raise ValueError('UNKNOWN_SETTLEMENT_RULE')
    if not rule.source or not rule.version or utc(rule.available_at)>utc(decision_at):raise ValueError('UNVERIFIED_SETTLEMENT_RULE')
    if (rule.book,rule.sport,rule.market)!=(context.book,context.sport,context.market_type):raise ValueError('SETTLEMENT_IDENTITY_MISMATCH')
    if rule.period!='full_game':raise ValueError('UNSUPPORTED_SETTLEMENT_PERIOD')
    # Regulation-only and three-way require separate regulation stats/outcomes.
    if not rule.overtime_included:raise ValueError('REGULATION_RESULT_REQUIRED')
    if final_status in ('cancelled','void'):return 'VOID'
    if final_status!='final':raise ValueError('RESULT_NOT_FINAL')
    if rule.listed_starter_required:
        if listed_starter_matches is None:raise ValueError('UNVERIFIED_PITCHER')
        if not listed_starter_matches:return 'VOID'
    if rule.nonparticipant_void or rule.minimum_participation>0:
        if participation is None:raise ValueError('MISSING_PARTICIPATION')
        if participation<rule.minimum_participation or (rule.nonparticipant_void and participation==0):return 'VOID'
    if isinstance(observed_stat,bool) or not isinstance(observed_stat,(int,float)) or not math.isfinite(observed_stat):raise ValueError('MISSING_RESULT')
    if context.market_type=='spread':value=(observed_stat if context.selection=='home' else -observed_stat)+context.line
    elif context.market_type in ('win','moneyline'):value=observed_stat if context.selection=='home' else -observed_stat
    else:
        if context.line is None or context.selection not in ('over','under'):raise ValueError('UNSUPPORTED_SETTLEMENT_SELECTION')
        value=observed_stat-context.line if context.selection=='over' else context.line-observed_stat
    if value==0:
        if not rule.push_allowed:raise ValueError('UNSUPPORTED_TIE_RULE')
        return 'PUSH'
    return 'WIN' if value>0 else 'LOSS'

def cashflow(outcome,odds,stake, *, account='cash',bonus_stake_returned=False):
    if not math.isfinite(stake) or stake<0:raise ValueError('INVALID_STAKE')
    if account not in ('cash','bonus'):raise ValueError('INVALID_ACCOUNT')
    decimal=american_to_decimal(odds)
    if outcome not in ('WIN','LOSS','PUSH','VOID'):raise ValueError('UNSETTLED_OUTCOME')
    if account=='cash':
        returned=stake*decimal if outcome=='WIN' else stake if outcome in ('PUSH','VOID') else 0
        return dict(cash_return=returned,bonus_return=0,cash_profit=returned-stake,roi_denominator=0 if outcome=='VOID' else stake)
    cash_return=stake*(decimal if bonus_stake_returned else decimal-1) if outcome=='WIN' else 0
    return dict(cash_return=cash_return,bonus_return=stake if outcome in ('PUSH','VOID') else 0,
        cash_profit=cash_return,roi_denominator=None)
