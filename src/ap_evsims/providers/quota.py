"""Persistent request accounting and successful immutable historical-response cache."""
import json, sqlite3
from ..integrity import digest
from ..integrity import database

class QuotaLedger:
    def __init__(self,path):
        self.path=str(path)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY, request_key TEXT, provider TEXT, endpoint TEXT,
                parameters TEXT, requested_at TEXT, status TEXT, cost INTEGER,
                remaining INTEGER, provider_used INTEGER, snapshot_id TEXT);
                CREATE TABLE IF NOT EXISTS cache (request_key TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS duplicate_hits (request_key TEXT, checked_at TEXT);''')
    def connect(self):return database(self.path)
    @staticmethod
    def key(provider,endpoint,parameters):
        if any(x.lower() in ('apikey','api_key','authorization') for x in parameters):raise ValueError('SECRET_IN_METADATA')
        return digest(dict(provider=provider,endpoint=endpoint,parameters=parameters))
    def cached(self,provider,endpoint,parameters,at):
        key=self.key(provider,endpoint,parameters)
        with self.connect() as db:
            row=db.execute('SELECT snapshot_id FROM cache WHERE request_key=?',(key,)).fetchone()
            if row:db.execute('INSERT INTO duplicate_hits VALUES (?,?)',(key,at))
        return row[0] if row else None
    def record(self,record, *, immutable=False):
        key=self.key(record['provider'],record['endpoint'],record['parameters'])
        quota=record.get('quota',{})
        with self.connect() as db:
            db.execute('INSERT INTO requests (request_key,provider,endpoint,parameters,requested_at,status,cost,remaining,provider_used,snapshot_id) VALUES (?,?,?,?,?,?,?,?,?,?)',
                (key,record['provider'],record['endpoint'],json.dumps(record['parameters'],sort_keys=True),record['checked_at'],str(record['status']),
                 quota.get('x-requests-last'),quota.get('x-requests-remaining'),quota.get('x-requests-used'),record.get('snapshot_id')))
            if immutable and record['status']==200 and record.get('snapshot_id'):
                db.execute('INSERT OR IGNORE INTO cache VALUES (?,?)',(key,record['snapshot_id']))
    def summary(self):
        with self.connect() as db:
            count,cost=db.execute('SELECT count(*),sum(cost) FROM requests WHERE provider="odds"').fetchone()
            latest=db.execute('SELECT remaining,provider_used FROM requests WHERE provider="odds" AND remaining IS NOT NULL ORDER BY id DESC LIMIT 1').fetchone()
            duplicates=db.execute('SELECT count(*) FROM duplicate_hits').fetchone()[0]
            cached=db.execute('SELECT count(*) FROM cache').fetchone()[0]
        return dict(requests_recorded=count,credits_consumed_recorded=cost or 0,requests_remaining=latest[0] if latest else None,
            provider_requests_used=latest[1] if latest else None,duplicate_requests_prevented=duplicates,cached_historical_snapshots=cached)
