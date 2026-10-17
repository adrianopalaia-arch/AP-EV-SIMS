from __future__ import annotations
from .odds import expected_value


def evaluate_parlay(*, offered_american_odds: int | None, scenario_joint_probability: float | None, legs: int) -> dict:
    reasons=[]
    if legs < 2: reasons.append("PARLAY_REQUIRES_MULTIPLE_LEGS")
    if offered_american_odds is None: reasons.append("MISSING_ACTUAL_OFFERED_PARLAY_PRICE")
    if scenario_joint_probability is None: reasons.append("MISSING_SCENARIO_BASED_JOINT_PROBABILITY")
    if scenario_joint_probability is not None and not 0 < scenario_joint_probability < 1: reasons.append("INVALID_JOINT_PROBABILITY")
    if reasons:
        return {"status":"PASS","reasons":reasons}
    ev=expected_value(scenario_joint_probability,offered_american_odds)
    return {"status":"RESEARCH_CANDIDATE" if ev>0 else "PASS","ev":round(ev,4),"reasons":[] if ev>0 else ["NONPOSITIVE_PARLAY_EV"]}
