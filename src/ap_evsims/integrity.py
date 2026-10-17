"""Local research evidence. Registry membership, not a caller flag, grants eligibility."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from .calibration import brier_score, log_loss

@contextmanager
def database(path):
    db = sqlite3.connect(path, timeout=30)
    try:
        with db:
            yield db
    finally:
        db.close()

def utc(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError('timezone required')
    return d.astimezone(timezone.utc)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()).hexdigest()

@dataclass(frozen=True)
class Evidence:
    report_id: str
    sport: str
    market: str
    model_version: str
    mode: str
    training_cutoff: str
    evaluation_start: str
    evaluation_end: str
    expires: str
    dataset_fingerprint: str
    n: int
    brier: float
    market_brier: float
    logloss: float
    market_logloss: float

class ValidationRegistry:
    def __init__(self, path):
        self.path = str(path)
        with database(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, body TEXT NOT NULL)')

    def get(self, report_id):
        with database(self.path) as db:
            row = db.execute('SELECT body FROM evidence WHERE id=?', (report_id,)).fetchone()
        return None if row is None else Evidence(**json.loads(row[0]))

    def evaluate(self, *, sport, market, model_version, mode, training_cutoff, expires, observations):
        """Compute evidence from frozen OOS observations; never accept supplied metrics.

        Local integrity is not proof of external provenance. A trusted ingestion/evaluation
        boundary and independent review remain required before real-money deployment.
        """
        if mode not in ('pregame', 'live') or not observations:
            raise ValueError('invalid evaluation')
        ids = set()
        for r in observations:
            if r['id'] in ids: raise ValueError('duplicate observation')
            ids.add(r['id'])
            if not utc(training_cutoff) < utc(r['feature_time']) <= utc(r['prediction_time']) <= utc(r['quote_time']) < utc(r['outcome_time']):
                raise ValueError('LOOKAHEAD_RISK')
            if r['mode'] != mode or r['model_version'] != model_version or r['sport'] != sport or r['market'] != market:
                raise ValueError('evaluation mismatch')
            if (mode == 'pregame' and utc(r['quote_time']) >= utc(r['event_start'])) or (mode == 'live' and utc(r['quote_time']) < utc(r['event_start'])):
                raise ValueError('mode mismatch')
            if r['outcome'] not in (0, 1): raise ValueError('binary settlement required')
            for k in ('p', 'market_p'):
                if not math.isfinite(r[k]) or not 0 < r[k] < 1: raise ValueError('invalid probability')
        ordered = sorted(observations, key=lambda r: r['id'])
        start = min(utc(r['prediction_time']) for r in ordered).isoformat()
        end = max(utc(r['outcome_time']) for r in ordered).isoformat()
        if utc(expires) <= utc(end): raise ValueError('invalid expiry')
        p = [r['p'] for r in ordered]; m = [r['market_p'] for r in ordered]; y = [r['outcome'] for r in ordered]
        body = dict(sport=sport, market=market, model_version=model_version, mode=mode,
                    training_cutoff=utc(training_cutoff).isoformat(), evaluation_start=start,
                    evaluation_end=end, expires=utc(expires).isoformat(), dataset_fingerprint=digest(ordered),
                    n=len(y), brier=brier_score(p,y), market_brier=brier_score(m,y),
                    logloss=log_loss(p,y), market_logloss=log_loss(m,y))
        e = Evidence(report_id=digest(body), **body)
        with database(self.path) as db:
            db.execute('INSERT OR IGNORE INTO evidence VALUES (?,?)', (e.report_id, json.dumps(asdict(e), sort_keys=True)))
        return e

    def verify(self, evidence, *, sport, market, model_version, mode, dataset_fingerprint, training_cutoff, as_of, minimum_n=300):
        if not isinstance(evidence, Evidence): return False
        with database(self.path) as db:
            row = db.execute('SELECT body FROM evidence WHERE id=?', (evidence.report_id,)).fetchone()
        if not row or json.loads(row[0]) != asdict(evidence): return False
        return (evidence.sport, evidence.market, evidence.model_version, evidence.mode, evidence.dataset_fingerprint, utc(evidence.training_cutoff)) == (sport, market, model_version, mode, dataset_fingerprint, utc(training_cutoff)) and utc(evidence.evaluation_end) < utc(as_of) < utc(evidence.expires) and evidence.n >= minimum_n and evidence.brier < evidence.market_brier and evidence.logloss < evidence.market_logloss

class SnapshotStore:
    def __init__(self, path):
        self.path = str(path)
        with database(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, kind TEXT, key TEXT, observed TEXT, available TEXT, body TEXT)')

    def append(self, *, kind, key, observed, available, payload):
        observed = utc(observed).isoformat(); available = utc(available).isoformat()
        if utc(observed) > utc(available): raise ValueError('LOOKAHEAD_RISK')
        body = json.dumps(payload, sort_keys=True, allow_nan=False)
        identity = digest([kind, key, observed, available, payload])
        with database(self.path) as db:
            db.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?,?,?)', (identity,kind,key,observed,available,body))
        return identity

    def as_of(self, kind, key, decision_time):
        cutoff = utc(decision_time).isoformat()
        with database(self.path) as db:
            row = db.execute('SELECT id,observed,available,body FROM snapshots WHERE kind=? AND key=? AND observed<=? AND available<=? ORDER BY observed DESC, available DESC, id DESC LIMIT 1', (kind,key,cutoff,cutoff)).fetchone()
        return None if not row else dict(snapshot_id=row[0], observed=row[1], available=row[2], payload=json.loads(row[3]))
