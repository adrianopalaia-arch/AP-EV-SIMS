from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from .schemas import Candidate, parse_utc
from .calibration import ValidationReport
from .odds import american_to_implied, devig_two_way, expected_value, max_american_for_min_ev

UTC=timezone.utc

@dataclass(frozen=True)
class ScreeningConfig:
    min_validation_n: int = 300
    max_quote_age_seconds: int = 180
    max_data_age_seconds: int = 600
    max_probability_gap: float = 0.08
    min_conservative_ev: float = 0.05
    min_edge_vs_devig_market: float = 0.02
    max_single_stake_units: float = 0.5
    kelly_fraction: float = 0.25


def _fractional_kelly(p: float, decimal_odds: float, fraction: float) -> float:
    b = decimal_odds - 1.0
    q = 1-p
    full=max(0.0,(b*p-q)/b) if b>0 else 0.0
    return full*fraction


def screen_candidate(c: Candidate, report: ValidationReport, now: datetime, unit_usd: float, cfg: ScreeningConfig = ScreeningConfig()) -> dict:
    # Legacy CSV metrics are untrusted. Use decision.decide with registered evidence.
    reasons=["MODEL_NOT_CALIBRATED", "LEGACY_PROVENANCE_INCOMPLETE"]
    now=now.astimezone(UTC)
    quote=parse_utc(c.quote_time_utc); data=parse_utc(c.data_time_utc); event=parse_utc(c.event_time_utc)
    feature=parse_utc(c.feature_cutoff_utc) if c.feature_cutoff_utc else data

    if c.book.lower() != "draftkings": reasons.append("NOT_DRAFTKINGS_EXECUTION_PRICE")
    if not (0 < c.p_low <= c.p_model < 1): reasons.append("INVALID_PROBABILITY_INTERVAL")
    if c.p_model-c.p_low > cfg.max_probability_gap: reasons.append("MODEL_UNCERTAINTY_TOO_WIDE")
    if not c.lineup_verified: reasons.append("LINEUP_NOT_VERIFIED")
    if not c.role_verified: reasons.append("ROLE_NOT_VERIFIED")
    if not c.settlement_verified: reasons.append("SETTLEMENT_RULE_NOT_VERIFIED")
    if quote > now + timedelta(seconds=30) or now-quote > timedelta(seconds=cfg.max_quote_age_seconds): reasons.append("STALE_OR_FUTURE_QUOTE")
    if data > now + timedelta(seconds=30) or now-data > timedelta(seconds=cfg.max_data_age_seconds): reasons.append("STALE_OR_FUTURE_DATA")
    if feature > quote: reasons.append("LOOKAHEAD_FEATURE_TIMESTAMP")
    if event <= now and not c.is_live: reasons.append("PREGAME_MODEL_USED_AFTER_START")
    if c.is_live and not c.live_state_verified: reasons.append("LIVE_STATE_NOT_VERIFIED")

    if report.sport != c.sport or report.market != c.market or report.model_version != c.model_version or report.mode != c.model_mode:
        reasons.append("VALIDATION_REPORT_MISMATCH")
    elif not report.is_eligible(cfg.min_validation_n):
        reasons.append("VALIDATION_REPORT_NOT_ELIGIBLE")

    implied=american_to_implied(c.american_odds)
    market_fair=None; vig=None
    if c.opposite_odds is not None:
        market_fair, _, vig = devig_two_way(c.american_odds,c.opposite_odds)
        if c.p_low-market_fair < cfg.min_edge_vs_devig_market:
            reasons.append("EDGE_VS_DEVIG_MARKET_TOO_SMALL")
    else:
        reasons.append("MISSING_OPPOSITE_PRICE_FOR_DEVIG")

    ev=expected_value(c.p_low,c.american_odds)
    if ev < cfg.min_conservative_ev: reasons.append("CONSERVATIVE_EV_TOO_LOW")

    dec = 1 + (c.american_odds/100 if c.american_odds>0 else 100/-c.american_odds)
    kelly = _fractional_kelly(c.p_low,dec,cfg.kelly_fraction)
    stake = min(unit_usd*cfg.max_single_stake_units, unit_usd*kelly)
    if stake < 1.0: reasons.append("STAKE_BELOW_ONE_DOLLAR")

    status="CORE_CANDIDATE" if not reasons else "PASS"
    return {
        "event_id":c.event_id,"sport":c.sport,"market":c.market,"selection":c.selection,
        "price":c.american_odds,"p_model":round(c.p_model,4),"p_low":round(c.p_low,4),
        "implied":round(implied,4),"market_fair":None if market_fair is None else round(market_fair,4),
        "vig":None if vig is None else round(vig,4),"edge_vs_market":None if market_fair is None else round(c.p_low-market_fair,4),
        "ev_conservative":round(ev,4),"max_acceptable_price":max_american_for_min_ev(c.p_low,cfg.min_conservative_ev),
        "stake_usd":round(stake,2) if status=="CORE_CANDIDATE" else 0.0,
        "status":status,"reasons":reasons,"event_group":c.event_group,"risk_groups":list(c.risk_groups),
    }
