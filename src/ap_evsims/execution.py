"""Additional research eligibility checks; these cannot override a Phase 1 PASS."""
from dataclasses import dataclass
import math
from .integrity import utc,digest
from .odds import american_to_decimal

@dataclass(frozen=True)
class MarketIdentity:
    event_id:str
    event_start:str
    book:str
    market:str
    period:str
    selection_id:str
    line:float|None
    settlement_rule_id:str|None
    player_id:str|None=None
    team_id:str|None=None
    @property
    def identity(self):return digest(self.__dict__)
    def validate(self, *, player_market=False):
        utc(self.event_start)
        if not self.settlement_rule_id:raise ValueError('UNKNOWN_SETTLEMENT_RULE')
        if not all((self.event_id,self.book,self.market,self.period,self.selection_id)):raise ValueError('MISSING_MARKET_IDENTITY')
        if player_market and (not self.player_id or not self.team_id):raise ValueError('UNVERIFIED_PLAYER_IDENTITY')
        if self.line is not None and (isinstance(self.line,bool) or not math.isfinite(self.line)):raise ValueError('INVALID_LINE')

def execution_reasons(identity, *, at,quote_at,available_at,opposite_quote_at,market_open,
                      executable_evidence=None,max_age=180,pair_tolerance=30,availability=None,availability_max_age=600):
    reasons=[]
    try:identity.validate()
    except ValueError as e:reasons.append(str(e))
    clock=utc(at)
    if clock>=utc(identity.event_start):reasons.append('EVENT_STARTED')
    if utc(quote_at)>utc(available_at) or utc(available_at)>clock:reasons.append('LOOKAHEAD_RISK')
    if (clock-utc(quote_at)).total_seconds()>max_age:reasons.append('STALE_PRICE')
    if abs((utc(quote_at)-utc(opposite_quote_at)).total_seconds())>pair_tolerance:reasons.append('NO_VIG_UNRELIABLE')
    if market_open is not True:reasons.append('MARKET_SUSPENDED_OR_UNVERIFIED')
    if not executable_evidence:reasons.append('QUOTE_EXECUTION_UNVERIFIED')
    else:
        if not executable_evidence.get('source') or executable_evidence.get('market_identity')!=identity.identity:reasons.append('QUOTE_EXECUTION_UNVERIFIED')
        if not executable_evidence.get('available_at') or utc(executable_evidence['available_at'])>clock:reasons.append('LOOKAHEAD_RISK')
    if availability is None:reasons.append('UNVERIFIED_LINEUP')
    else:
        if availability.get('event_id')!=identity.event_id or not availability.get('source') or availability.get('confirmed') is not True:reasons.append('UNVERIFIED_LINEUP')
        confirmed=availability.get('confirmed_at')
        if confirmed is None:reasons.append('UNVERIFIED_LINEUP')
        elif utc(confirmed)>clock:reasons.append('LOOKAHEAD_RISK')
        elif (clock-utc(confirmed)).total_seconds()>availability_max_age:reasons.append('STALE_AVAILABILITY')
    return list(dict.fromkeys(reasons))

def refresh_reasons(modeled,current,current_odds,max_price):
    if modeled.identity!=current.identity:return ['PRICE_MOVED','PROBABILITY_RECALCULATION_REQUIRED']
    if american_to_decimal(current_odds)<american_to_decimal(max_price):return ['PRICE_MOVED']
    return []

def pessimistic_decimal_price(american_odds,decimal_cents):
    if decimal_cents not in (0,5,10,15):raise ValueError('UNREGISTERED_SLIPPAGE_SCENARIO')
    # Explicit convention: subtract .05/.10/.15 decimal payout units per $1.
    return max(1.000001,american_to_decimal(american_odds)-decimal_cents/100)

def simple_edge_flags(phase1_status,quality,role_stability,simple_probability,opportunity_probability,champion_probability,market_probability,price_ok,disagreement_limit=.03):
    values=(simple_probability,opportunity_probability,champion_probability,market_probability)
    valid=all(isinstance(p,(int,float)) and math.isfinite(p) and 0<p<1 for p in values)
    clean=valid and phase1_status=='RESEARCH_CANDIDATE' and quality=='HIGH' and role_stability=='HIGH' and price_ok
    clean=bool(clean and min(values[:3])>market_probability and max(values[:3])-min(values[:3])<=disagreement_limit)
    return dict(SIMPLE_EDGE=clean,CLEAN_EDGE=clean,AP_TOP_PICK=clean,eligibility_unchanged=True,
        confidence_note='Correlated model agreement is not independent evidence.')
