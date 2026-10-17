"""Phase 1 decision boundary. Binary cash markets only until settlement models exist."""
from dataclasses import dataclass, field
import math
from .integrity import utc, digest, Evidence, ValidationRegistry
from .exposure import ExposureLedger, ExposureLimits
from .features import feature_reasons
from .odds import american_to_decimal, american_to_implied, devig_two_way, expected_value, probability_to_american, max_american_for_min_ev
from .ledger import Ledger

@dataclass(frozen=True)
class ResearchCandidate:
    candidate_id: str
    event_id: str
    sport: str
    market: str
    selection: str
    model_version: str
    mode: str
    dataset_fingerprint: str
    training_cutoff: str
    event_start: str
    quote_time: str
    opposite_quote_time: str
    availability_time: str
    feature_time: str
    prediction_time: str
    p_model: float
    p_low: float
    american_odds: int
    opposite_odds: int
    book: str
    market_line: float | None
    opposite_market_line: float | None
    lineup_verified: bool
    live_state_verified: bool
    binary_settlement_verified: bool
    exposure_groups: tuple[str, ...]
    features: dict = field(default_factory=dict)
    model_disagreement: float = 0
    account: str = 'cash'

def decide(c: ResearchCandidate, evidence: Evidence | None, *, registry: ValidationRegistry,
           exposure: ExposureLedger, limits: ExposureLimits, ledger: Ledger, now,
           reserve=True, min_ev=.05, min_edge=.02, minimum_n=300):
    if not math.isfinite(min_ev) or min_ev < 0 or not math.isfinite(min_edge) or min_edge < 0:
        raise ValueError('invalid decision policy')
    decision_time = utc(now)
    reasons = []
    output = dict(candidate_id=c.candidate_id,event_id=c.event_id,sport=c.sport,market=c.market,
                  selection=c.selection,book=c.book,model_version=c.model_version,mode=c.mode,
                  p_model=c.p_model,p_low=c.p_low, sportsbook_odds=c.american_odds,
                  market_line=c.market_line,implied=None,market_fair=None,fair_odds=None,
                  ev_conservative=None,max_acceptable_price=None,stake_usd=0,
                  dataset_fingerprint=c.dataset_fingerprint,report_id=getattr(evidence,'report_id',None),
                  timestamps=dict(event_start=c.event_start,quote=c.quote_time,opposite_quote=c.opposite_quote_time,
                                  lineup_injury=c.availability_time,feature_snapshot=c.feature_time,
                                  model_prediction=c.prediction_time,decision=decision_time.isoformat()),
                  exposure_groups=list(c.exposure_groups),account=c.account)
    try:
        event, quote, opposite, availability, feature, prediction = map(utc, (c.event_start,c.quote_time,c.opposite_quote_time,c.availability_time,c.feature_time,c.prediction_time))
        # Predictions and market snapshots must exist by decision time; all input
        # availability must precede the prediction and the quote being evaluated.
        if not availability <= feature <= prediction <= quote <= decision_time or opposite > quote:
            reasons.append('LOOKAHEAD_RISK')
        if (decision_time-quote).total_seconds() > (15 if c.mode == 'live' else 180) or (quote-opposite).total_seconds() > (15 if c.mode == 'live' else 180): reasons.append('STALE_PRICE')
        if (decision_time-availability).total_seconds() > (30 if c.mode == 'live' else 600) or (decision_time-feature).total_seconds() > (30 if c.mode == 'live' else 600): reasons.append('STALE_DATA')
        if c.mode not in ('pregame','live') or (c.mode == 'pregame' and quote >= event) or (c.mode == 'pregame' and decision_time >= event) or (c.mode == 'live' and (quote < event or not c.live_state_verified)):
            reasons.append('MODE_MISMATCH')
        valid = registry.verify(evidence,sport=c.sport,market=c.market,model_version=c.model_version,mode=c.mode,
                                dataset_fingerprint=c.dataset_fingerprint,training_cutoff=c.training_cutoff,as_of=feature,minimum_n=minimum_n)
        if not valid: reasons.append('MODEL_NOT_CALIBRATED')
    except (ValueError,TypeError,AttributeError,OverflowError): reasons.extend(['LOOKAHEAD_RISK','MODEL_NOT_CALIBRATED'])
    reasons.extend(feature_reasons(c.sport,c.features,c.feature_time))
    if not c.lineup_verified: reasons.append('UNVERIFIED_LINEUP')
    if not c.binary_settlement_verified: reasons.append('UNVERIFIED_SETTLEMENT')
    if c.account != 'cash': reasons.append('BONUS_EV_NOT_IMPLEMENTED')
    if not c.candidate_id or not c.event_id or 'GAME:'+c.event_id not in c.exposure_groups or not any(g.startswith('TEAM:') for g in c.exposure_groups): reasons.append('MISSING_EXPOSURE_GROUPS')
    if c.market not in ({'spread','total'} if c.sport == 'CFB' else {'shots','goalie','team'}): reasons.append('UNSUPPORTED_MARKET')
    if c.sport == 'NHL' and c.market == 'shots' and not any(g.startswith('PLAYER:') for g in c.exposure_groups): reasons.append('MISSING_EXPOSURE_GROUPS')
    if not math.isfinite(c.model_disagreement) or not 0 <= c.model_disagreement <= .08: reasons.append('MODEL_DISAGREEMENT')
    if not all(math.isfinite(p) for p in (c.p_model,c.p_low)) or not 0 < c.p_low <= c.p_model < 1 or c.p_model-c.p_low > .08:
        reasons.append('INVALID_PROBABILITY')
    else:
        try:
            if any(isinstance(o,bool) or not isinstance(o,int) for o in (c.american_odds,c.opposite_odds)): raise ValueError('invalid odds')
            implied = american_to_implied(c.american_odds)
            market, _, vig = devig_two_way(c.american_odds,c.opposite_odds)
            ev = expected_value(c.p_low,c.american_odds)
            output.update(implied=implied,market_fair=market,vig=vig,fair_odds=probability_to_american(c.p_low),
                          ev_conservative=ev,max_acceptable_price=max_american_for_min_ev(c.p_low,min_ev))
            if ev < min_ev or c.p_low-market < min_edge: reasons.append('EDGE_TOO_SMALL')
            price_feature = c.features.get('american_odds',{}).get('value')
            if price_feature != c.american_odds or c.opposite_market_line != c.market_line: reasons.append('PRICE_MOVED')
            if c.sport == 'CFB' and c.features.get('market_line',{}).get('value') != c.market_line: reasons.append('PRICE_MOVED')
            if c.sport == 'CFB' and (c.market_line is None or not math.isfinite(c.market_line) or c.market_line % 1 == 0): reasons.append('PUSH_MODEL_REQUIRED')
            if not reasons:
                decimal = american_to_decimal(c.american_odds)
                kelly = max(0, (c.p_low*decimal-1)/(decimal-1))*.25
                stake = math.floor(min(limits.cash_bankroll*kelly, limits.cash_bankroll*limits.cash_group_fraction)*100)/100
                if stake < 1: reasons.append('STAKE_TOO_SMALL')
                elif not reserve: reasons.append('EXPOSURE_NOT_RESERVED')
                else:
                    rejected = exposure.reserve(position_id=c.candidate_id,account=c.account,amount=stake,groups=c.exposure_groups,at=decision_time,limits=limits)
                    if rejected: reasons.append(rejected)
                    else: output['stake_usd'] = stake
        except (ValueError,TypeError,OverflowError,ZeroDivisionError): reasons.append('INVALID_PRICE')
    output.update(status='PASS' if reasons else 'RESEARCH_CANDIDATE',reasons=list(dict.fromkeys(reasons)))
    # Strict JSON: a rejected NaN remains explicitly missing, never a numeric edge.
    for key in ('p_model','p_low','sportsbook_odds','market_line'):
        if isinstance(output[key],float) and not math.isfinite(output[key]): output[key] = None
    ledger.append(output)
    return output
