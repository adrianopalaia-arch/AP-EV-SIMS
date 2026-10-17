"""Strict historical rows, score settlement, and expanding chronological folds."""
from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path
from .integrity import utc, digest
from .models.base import FeatureSnapshot, MarketContext
from .odds import american_to_decimal

@dataclass(frozen=True)
class HistoricalObservation:
    observation_id: str
    features: FeatureSnapshot
    context: MarketContext
    home_score: int
    away_score: int
    result_available_at: str
    result_snapshot_id: str
    result_payload_hash: str
    game_status: str
    overtime: bool | None = None
    closing_context: MarketContext | None = None
    availability_timestamp: str | None = None
    lineup_verified: bool = False
    binary_settlement_verified: bool = False
    risk_groups: tuple[str, ...] = ()
    event_mapping: dict | None = None

    def validate(self):
        self.features.validate(self.context.prediction_timestamp)
        self.context.validate()
        if self.features.event_id!=self.context.event_id or self.features.sport!=self.context.sport:
            raise ValueError('EVENT_IDENTITY_MISMATCH')
        if self.game_status!='final' or not self.result_snapshot_id or len(self.result_payload_hash)!=64:
            raise ValueError('UNSETTLED_RESULT')
        if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in (self.home_score,self.away_score)):
            raise ValueError('INVALID_RESULT')
        if utc(self.result_available_at)<=utc(self.context.event_timestamp): raise ValueError('LOOKAHEAD_RISK')
        if self.closing_context:
            c=self.closing_context; c.validate()
            if (c.event_id,c.market_type,c.selection)!=(self.context.event_id,self.context.market_type,self.context.selection):
                raise ValueError('CLOSING_MARKET_MISMATCH')
            if utc(c.quote_timestamp)<utc(self.context.quote_timestamp): raise ValueError('INVALID_CLOSING_TIMESTAMP')

    @property
    def economic_key(self): return (self.context.event_id,self.context.market_type,self.context.selection)

    @property
    def margin(self): return self.home_score-self.away_score
    @property
    def total(self): return self.home_score+self.away_score

    @classmethod
    def from_dict(cls, r):
        d=dict(r); d['features']=FeatureSnapshot.from_dict(r['features']); d['context']=MarketContext(**r['context'])
        if r.get('closing_context'): d['closing_context']=MarketContext(**r['closing_context'])
        return cls(**d)

def validate_dataset(rows):
    ids=set(); keys=set()
    for r in rows:
        r.validate()
        if r.observation_id in ids or r.economic_key in keys: raise ValueError('DUPLICATE_HISTORICAL_OBSERVATION')
        ids.add(r.observation_id); keys.add(r.economic_key)
    return sorted(rows,key=lambda r:(utc(r.context.prediction_timestamp),r.observation_id))

def load_dataset(path):
    return validate_dataset([HistoricalObservation.from_dict(json.loads(line)) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()])

def settle(row):
    row.validate()
    c=row.context
    if c.market_type=='spread':
        value=row.margin+c.line if c.selection=='home' else -row.margin+c.line
    elif c.market_type=='total':
        value=row.total-c.line if c.selection=='over' else c.line-row.total
    elif c.market_type=='win': value=row.margin if c.selection=='home' else -row.margin
    else: raise ValueError('UNSUPPORTED_MARKET')
    if c.selection not in (('home','away') if c.market_type!='total' else ('over','under')): raise ValueError('INVALID_SELECTION')
    return 'WIN' if value>0 else 'LOSS' if value<0 else 'PUSH'

def unit_profit(result, odds):
    if result=='WIN': return american_to_decimal(odds)-1
    if result=='LOSS': return -1.0
    if result in ('PUSH','VOID'): return 0.0
    raise ValueError('INVALID_SETTLEMENT')

@dataclass(frozen=True)
class FoldWindow:
    training_end: str
    calibration_end: str
    selection_end: str
    evaluation_end: str

    def validate(self):
        if not utc(self.training_end)<utc(self.calibration_end)<utc(self.selection_end)<utc(self.evaluation_end):
            raise ValueError('INVALID_TIME_FOLD')

def partition(rows, window):
    window.validate(); rows=validate_dataset(rows)
    a,b,c,d=map(utc,(window.training_end,window.calibration_end,window.selection_end,window.evaluation_end))
    train=[r for r in rows if utc(r.result_available_at)<=a and utc(r.context.prediction_timestamp)<=a]
    calibration=[r for r in rows if a<utc(r.context.prediction_timestamp)<=b and utc(r.result_available_at)<=b]
    selection=[r for r in rows if b<utc(r.context.prediction_timestamp)<=c and utc(r.result_available_at)<=c]
    evaluation=[r for r in rows if c<utc(r.context.prediction_timestamp)<=d and utc(r.result_available_at)<=d]
    # No event may appear in more than one partition, even across books/markets.
    seen=set()
    for group in (train,calibration,selection,evaluation):
        events={r.context.event_id for r in group}
        if seen & events: raise ValueError('EVENT_FOLD_LEAKAGE')
        seen |= events
    return train,calibration,selection,evaluation
