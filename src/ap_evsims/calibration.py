from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Iterable, Sequence

def _validate(probabilities, outcomes):
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must be equal non-empty lengths")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities) or any(y not in (0,1) for y in outcomes):
        raise ValueError("invalid binary forecast observations")


def brier_score(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    _validate(probabilities, outcomes)
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must be equal non-empty lengths")
    return sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / len(probabilities)


def log_loss(probabilities: Sequence[float], outcomes: Sequence[int], eps: float = 1e-12) -> float:
    _validate(probabilities, outcomes)
    if not math.isfinite(eps) or not 0 < eps < .5: raise ValueError("invalid epsilon")
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must be equal non-empty lengths")
    total = 0.0
    for p, y in zip(probabilities, outcomes):
        p = min(max(p, eps), 1 - eps)
        total += -(y * math.log(p) + (1-y) * math.log(1-p))
    return total / len(probabilities)


def calibration_bins(probabilities: Sequence[float], outcomes: Sequence[int], bins: int = 10) -> list[dict]:
    _validate(probabilities, outcomes)
    if bins < 2:
        raise ValueError("bins must be >=2")
    out=[]
    for i in range(bins):
        lo, hi = i / bins, (i+1) / bins
        idx=[j for j,p in enumerate(probabilities) if (lo <= p < hi) or (i==bins-1 and p==1)]
        if not idx:
            continue
        out.append({
            "lo":lo,"hi":hi,"n":len(idx),
            "predicted":sum(probabilities[j] for j in idx)/len(idx),
            "observed":sum(outcomes[j] for j in idx)/len(idx),
        })
    return out

@dataclass(frozen=True)
class ValidationReport:
    sport: str
    market: str
    model_version: str
    mode: str  # pregame/live
    n: int
    brier: float
    market_brier: float
    logloss: float
    market_logloss: float
    training_cutoff_utc: str
    validation_end_utc: str
    authenticated: bool = False

    def is_eligible(self, minimum_n: int = 300) -> bool:
        return (
            self.authenticated
            and self.n >= minimum_n
            and self.brier < self.market_brier
            and self.logloss < self.market_logloss
        )
