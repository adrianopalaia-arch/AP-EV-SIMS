from dataclasses import dataclass, asdict, field
import math
from typing import Protocol
from ..integrity import utc, digest
from ..odds import american_to_decimal

@dataclass(frozen=True)
class FeatureValue:
    value: float
    source: str
    observed_at: str
    available_at: str | None
    snapshot_id: str
    payload_hash: str
    source_path: str | None = None

    def validate(self, at):
        if self.available_at is None:
            raise ValueError('HISTORICAL_AVAILABILITY_UNVERIFIED')
        if not self.source or not self.snapshot_id or len(self.payload_hash) != 64:
            raise ValueError('MISSING_FEATURE_PROVENANCE')
        if isinstance(self.value, bool) or not isinstance(self.value, (int,float)) or not math.isfinite(self.value):
            raise ValueError('MISSING_FEATURES')
        if not utc(self.observed_at) <= utc(self.available_at) <= utc(at):
            raise ValueError('LOOKAHEAD_RISK')

@dataclass(frozen=True)
class FeatureSnapshot:
    event_id: str
    sport: str
    timestamp: str
    values: dict[str, FeatureValue]

    @property
    def fingerprint(self): return digest(asdict(self))

    def validate(self, as_of, required=()):
        if utc(self.timestamp) > utc(as_of): raise ValueError('LOOKAHEAD_RISK')
        if not self.event_id or not self.sport: raise ValueError('MISSING_EVENT_IDENTITY')
        for name,value in self.values.items():
            if any(x in name.lower() for x in ('closing','postgame','final_score','settled','outcome')):
                raise ValueError('FORBIDDEN_FEATURE')
            value.validate(self.timestamp)
        if any(name not in self.values for name in required): raise ValueError('MISSING_FEATURES')

    @classmethod
    def from_dict(cls, data):
        return cls(data['event_id'],data['sport'],data['timestamp'],{k:FeatureValue(**v) for k,v in data['values'].items()})

@dataclass(frozen=True)
class MarketContext:
    event_id: str
    sport: str
    market_type: str
    selection: str
    book: str
    line: float | None
    odds: int
    opposite_odds: int | None
    prediction_timestamp: str
    quote_timestamp: str
    event_timestamp: str
    snapshot_id: str
    opposite_line: float | None = None
    snapshot_available_at: str | None = None

    def validate(self):
        if not self.event_id or not self.snapshot_id or not self.book: raise ValueError('MISSING_MARKET_IDENTITY')
        if not utc(self.prediction_timestamp) <= utc(self.quote_timestamp) < utc(self.event_timestamp):
            raise ValueError('LOOKAHEAD_RISK')
        if self.snapshot_available_at is not None and not utc(self.quote_timestamp)<=utc(self.snapshot_available_at)<utc(self.event_timestamp):
            raise ValueError('LOOKAHEAD_RISK')
        american_to_decimal(self.odds)
        if self.opposite_odds is None: raise ValueError('MISSING_MARKET_PAIR')
        american_to_decimal(self.opposite_odds)
        if self.market_type in ('spread','total') and (self.line is None or not math.isfinite(self.line) or self.line != self.opposite_line):
            raise ValueError('MISSING_MARKET_PAIR')

@dataclass(frozen=True)
class PredictionResult:
    raw_probability: float | None
    calibrated_probability: float | None
    uncertainty_lower_bound: float | None
    fair_decimal_odds: float | None
    fair_american_odds: int | None
    model_version: str
    training_cutoff: str | None
    feature_snapshot_timestamp: str
    data_fingerprint: str
    market_type: str
    calibration_version: str | None
    model_artifact_id: str | None
    explanation: dict = field(default_factory=dict)
    reasons: tuple[str, ...] = ()

    def to_dict(self): return asdict(self)

class SportModel(Protocol):
    model_version: str
    def predict(self, features: FeatureSnapshot, market_context: MarketContext) -> PredictionResult: ...
