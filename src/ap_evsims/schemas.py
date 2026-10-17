from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

UTC = timezone.utc

def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(UTC)

@dataclass(frozen=True)
class Candidate:
    event_id: str
    sport: str
    market: str
    selection: str
    book: str
    american_odds: int
    opposite_odds: Optional[int]
    quote_time_utc: str
    event_time_utc: str
    data_time_utc: str
    model_version: str
    model_mode: str
    p_model: float
    p_low: float
    lineup_verified: bool
    role_verified: bool
    live_state_verified: bool
    settlement_verified: bool
    event_group: str
    risk_groups: tuple[str, ...] = field(default_factory=tuple)
    feature_cutoff_utc: Optional[str] = None
    scenario_joint_probability: Optional[float] = None
    offered_parlay_odds: Optional[int] = None

    @property
    def is_live(self) -> bool:
        return self.model_mode.lower() == "live"
