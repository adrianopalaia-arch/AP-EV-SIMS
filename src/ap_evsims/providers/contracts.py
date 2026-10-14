"""Fixture-first provider boundary. Credentials belong in runtime configuration."""
from dataclasses import dataclass
from typing import Protocol
from ..integrity import SnapshotStore

@dataclass(frozen=True)
class ProviderSnapshot:
    snapshot_id: str
    observed: str
    available: str
    payload: dict

class SnapshotProvider(Protocol):
    def as_of(self, key: str, at: str) -> ProviderSnapshot | None: ...

class SportsbookOddsProvider(SnapshotProvider, Protocol): pass
class OfficialAvailabilityProvider(SnapshotProvider, Protocol): pass
class WeatherProvider(SnapshotProvider, Protocol): pass
class CFBStatisticsProvider(SnapshotProvider, Protocol): pass
class NHLStatisticsProvider(SnapshotProvider, Protocol): pass
class ResultsSettlementProvider(SnapshotProvider, Protocol): pass

class FixtureProvider:
    def __init__(self, store: SnapshotStore, kind: str):
        if kind not in ('odds','availability','weather','cfb','nhl','results'): raise ValueError('unknown provider')
        self.store, self.kind = store, kind

    def as_of(self, key, at):
        row = self.store.as_of(self.kind, key, at)
        return None if row is None else ProviderSnapshot(**row)
