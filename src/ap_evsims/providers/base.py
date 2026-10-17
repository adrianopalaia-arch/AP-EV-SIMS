from __future__ import annotations
from abc import ABC, abstractmethod

class OddsProvider(ABC):
    @abstractmethod
    def snapshot(self, sport: str, event_id: str) -> dict: ...

class SportDataProvider(ABC):
    @abstractmethod
    def pregame_state(self, sport: str, event_id: str) -> dict: ...
    @abstractmethod
    def live_state(self, sport: str, event_id: str) -> dict: ...
