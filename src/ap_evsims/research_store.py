"""Content-addressed raw responses and reproducible research manifests."""
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
from .integrity import digest, utc

class ResearchStore:
    def __init__(self, root):
        self.root=Path(root)
        for name in ('raw/cfbd','raw/odds','raw/weather','raw/results','raw/nhl','raw/nfl','raw/mlb','raw/nba','raw/availability','normalized','features','snapshots','predictions','settlements','models','manifests','evaluations'):
            (self.root/name).mkdir(parents=True,exist_ok=True)

    def archive(self, *, provider, endpoint, parameters, body, fetched_at, observed_at=None, available_at=None, availability_basis='unverified', requested_at=None, provider_event_id=None, canonical_event_id=None, revision_id=None):
        if provider not in ('cfbd','odds','weather','results','nhl','nfl','mlb','nba','availability'): raise ValueError('unknown provider')
        if any(k.lower() in ('apikey','api_key','authorization') for k in parameters): raise ValueError('SECRET_IN_METADATA')
        fetched_at=utc(fetched_at).isoformat()
        if requested_at is not None and utc(requested_at)>utc(fetched_at):raise ValueError('LOOKAHEAD_RISK')
        if available_at is not None:
            if observed_at is None or not utc(observed_at) <= utc(available_at) <= utc(fetched_at): raise ValueError('LOOKAHEAD_RISK')
            if availability_basis not in ('recorded_response','historical_odds_snapshot'): raise ValueError('HISTORICAL_AVAILABILITY_UNVERIFIED')
            if availability_basis=='recorded_response' and utc(available_at)!=utc(fetched_at): raise ValueError('unproven historical availability')
            if availability_basis=='historical_odds_snapshot' and provider!='odds': raise ValueError('invalid availability basis')
        payload_hash=hashlib.sha256(body).hexdigest()
        payload_path=self.root/'raw'/provider/(payload_hash+'.json')
        self._immutable(payload_path,body)
        manifest=dict(provider=provider,endpoint=endpoint,parameters=parameters,fetched_at=fetched_at,
            requested_at=requested_at,ingested_at=fetched_at,provider_event_id=provider_event_id,
            canonical_event_id=canonical_event_id,revision_id=revision_id or payload_hash,
            observed_at=observed_at,available_at=available_at,availability_basis=availability_basis,
            payload_hash=payload_hash,raw_path=str(payload_path.relative_to(self.root)),
            qualification_reason=None if available_at else 'HISTORICAL_AVAILABILITY_UNVERIFIED')
        snapshot_id=digest(manifest); manifest['snapshot_id']=snapshot_id
        self._immutable(self.root/'manifests'/(snapshot_id+'.json'),json.dumps(manifest,sort_keys=True,allow_nan=False,indent=2).encode())
        return manifest

    @staticmethod
    def _immutable(path,body):
        try:
            with path.open('xb') as f: f.write(body)
        except FileExistsError:
            if path.read_bytes()!=body: raise ValueError('IMMUTABLE_CONTENT_MISMATCH')

    def payload(self, manifest):
        path=(self.root/manifest['raw_path']).resolve()
        if self.root.resolve() not in path.parents: raise ValueError('invalid manifest path')
        body=path.read_bytes()
        if hashlib.sha256(body).hexdigest()!=manifest['payload_hash']: raise ValueError('PAYLOAD_HASH_MISMATCH')
        return json.loads(body)

    def manifest(self,snapshot_id):
        if len(snapshot_id)!=64 or any(c not in '0123456789abcdef' for c in snapshot_id): raise ValueError('INVALID_SNAPSHOT_ID')
        path=self.root/'manifests'/(snapshot_id+'.json')
        if not path.exists(): raise ValueError('MISSING_SOURCE_MANIFEST')
        manifest=json.loads(path.read_text(encoding='utf-8'))
        if manifest.get('snapshot_id')!=snapshot_id or digest({k:v for k,v in manifest.items() if k!='snapshot_id'})!=snapshot_id:
            raise ValueError('MANIFEST_HASH_MISMATCH')
        self.payload(manifest)
        return manifest

    def write_table(self, name, rows):
        """JSONL is always available; optional Parquet mirrors it without inventing data."""
        if Path(name).name!=name: raise ValueError('invalid table name')
        body=''.join(json.dumps(r,sort_keys=True,allow_nan=False)+'\n' for r in rows).encode()
        fingerprint=hashlib.sha256(body).hexdigest()
        path=self.root/'normalized'/(name+'-'+fingerprint+'.jsonl')
        self._immutable(path,body)
        parquet=None
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            if rows:
                target=path.with_suffix('.parquet')
                if not target.exists(): pq.write_table(pa.Table.from_pylist(rows),target)
                parquet=str(target.relative_to(self.root))
        except ImportError: pass
        return dict(path=str(path.relative_to(self.root)),parquet_path=parquet,fingerprint=fingerprint,n=len(rows))
