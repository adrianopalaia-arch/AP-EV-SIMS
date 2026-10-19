from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json

class Ledger:
    def __init__(self,path: str | Path): self.path=Path(path)
    def append(self,record: dict) -> None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        payload={**record,"recorded_utc":datetime.now(timezone.utc).isoformat()}
        serialized=json.dumps(payload,sort_keys=True,allow_nan=False)+"\n"
        with self.path.open("a",encoding="utf-8") as f:f.write(serialized)
    def read(self) -> list[dict]:
        if not self.path.exists(): return []
        return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]
