from __future__ import annotations
import math


def american_to_decimal(odds: int) -> float:
    if isinstance(odds, bool) or not isinstance(odds, int) or abs(odds) < 100:
        raise ValueError("invalid American odds")
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / -odds)


def american_to_implied(odds: int) -> float:
    if isinstance(odds, bool) or not isinstance(odds, int) or abs(odds) < 100:
        raise ValueError("invalid American odds")
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


def probability_to_american(p: float) -> int:
    if not 0 < p < 1:
        raise ValueError("probability must be between 0 and 1")
    if p >= 0.5:
        return math.floor(-100.0 * p / (1.0 - p))
    return math.ceil(100.0 * (1.0 - p) / p)


def devig_two_way(odds_a: int, odds_b: int) -> tuple[float, float, float]:
    pa = american_to_implied(odds_a)
    pb = american_to_implied(odds_b)
    overround = pa + pb
    if overround <= 0:
        raise ValueError("invalid overround")
    return pa / overround, pb / overround, overround - 1.0


def expected_value(probability: float, american_odds: int) -> float:
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("invalid probability")
    return probability * american_to_decimal(american_odds) - 1.0


def max_american_for_min_ev(probability: float, minimum_ev: float) -> int:
    if not math.isfinite(minimum_ev) or minimum_ev < 0:
        raise ValueError("invalid minimum EV")
    if not 0 < probability < 1:
        raise ValueError("invalid probability")
    target_decimal = (1.0 + minimum_ev) / probability
    if target_decimal <= 1.0:
        raise ValueError("target decimal odds must exceed 1")
    if target_decimal >= 2.0:
        return math.ceil((target_decimal - 1.0) * 100.0)
    return math.ceil(-100.0 / (target_decimal - 1.0))
