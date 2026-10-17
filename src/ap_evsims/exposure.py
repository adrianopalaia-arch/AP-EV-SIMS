"""Atomic research reservations and manually recorded bets; no placement API."""
import json
import math
import sqlite3
from dataclasses import dataclass
from .integrity import utc, database

@dataclass(frozen=True)
class ExposureLimits:
    cash_bankroll: float
    cash_total_fraction: float = .02
    cash_group_fraction: float = .01
    bonus_total: float = 0
    bonus_group: float = 0

    def __post_init__(self):
        values = (self.cash_bankroll, self.cash_total_fraction, self.cash_group_fraction, self.bonus_total, self.bonus_group)
        if not all(math.isfinite(v) and v >= 0 for v in values) or self.cash_bankroll <= 0 or not 0 < self.cash_group_fraction <= self.cash_total_fraction <= 1:
            raise ValueError('invalid exposure limits')

class ExposureLedger:
    def __init__(self, path):
        self.path = str(path)
        with database(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS positions (id TEXT PRIMARY KEY, account TEXT, amount REAL, groups_json TEXT, state TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS exposure_events (sequence INTEGER PRIMARY KEY, id TEXT, action TEXT, timestamp TEXT, body TEXT)')

    def record_open(self, *, position_id, account, amount, groups, at):
        """Import an already placed external bet even when it exceeds current limits.

        Rejecting an import for exceeding a budget would hide real exposure.
        No sportsbook is contacted and no wager is placed.
        """
        groups = sorted(set(groups))
        if not position_id or account not in ('cash','bonus') or not math.isfinite(amount) or amount <= 0 or not groups or not any(g.startswith('GAME:') for g in groups) or any(':' not in g for g in groups):
            raise ValueError('invalid open position')
        timestamp = utc(at).isoformat()
        with database(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO positions VALUES (?,?,?,?,?)', (position_id,account,amount,json.dumps(groups),'open'))
            db.execute('INSERT INTO exposure_events (id,action,timestamp,body) VALUES (?,?,?,?)', (position_id,'imported_open',timestamp,json.dumps(dict(account=account,amount=amount,groups=groups))))

    def reserve(self, *, position_id, account, amount, groups, at, limits):
        if account not in ('cash', 'bonus') or not math.isfinite(amount) or amount <= 0:
            raise ValueError('invalid exposure')
        groups = sorted(set(groups))
        if not position_id or not groups or any(not g or ':' not in g for g in groups) or not any(g.startswith('GAME:') for g in groups):
            return 'MISSING_EXPOSURE_GROUPS'
        timestamp = utc(at).isoformat()
        total_cap = limits.cash_bankroll * limits.cash_total_fraction if account == 'cash' else limits.bonus_total
        group_cap = limits.cash_bankroll * limits.cash_group_fraction if account == 'cash' else limits.bonus_group
        with database(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM positions WHERE id=?', (position_id,)).fetchone(): return 'DUPLICATE_POSITION'
            # Cash and free-bet budgets are separate; correlated outcomes share a cap.
            rows = db.execute("SELECT account,amount,groups_json FROM positions WHERE state IN ('reserved','open')").fetchall()
            if sum(r[1] for r in rows if r[0] == account) + amount > total_cap + 1e-9: return 'EXPOSURE_LIMIT'
            for group in groups:
                used = sum(r[1] for r in rows if group in json.loads(r[2]))
                if used + amount > group_cap + 1e-9: return 'CORRELATION_LIMIT'
            db.execute('INSERT INTO positions VALUES (?,?,?,?,?)', (position_id, account, amount, json.dumps(groups), 'reserved'))
            db.execute('INSERT INTO exposure_events (id,action,timestamp,body) VALUES (?,?,?,?)', (position_id,'reserved',timestamp,json.dumps(dict(account=account,amount=amount,groups=groups))))
        return None

    def transition(self, position_id, state, at):
        """Manual confirmation, cancellation or settlement. Open means externally placed."""
        timestamp = utc(at).isoformat()
        with database(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM positions WHERE id=?', (position_id,)).fetchone()
            last = db.execute('SELECT timestamp FROM exposure_events WHERE id=? ORDER BY sequence DESC LIMIT 1', (position_id,)).fetchone()
            permitted = {'reserved': ('open','cancelled'), 'open': ('settled','void')}
            if not row or state not in permitted.get(row[0], ()) or utc(timestamp) < utc(last[0]): raise ValueError('invalid exposure transition')
            db.execute('UPDATE positions SET state=? WHERE id=?', (state,position_id))
            db.execute('INSERT INTO exposure_events (id,action,timestamp,body) VALUES (?,?,?,?)', (position_id,state,timestamp,'{}'))

    def positions(self):
        with database(self.path) as db:
            return [dict(id=r[0],account=r[1],amount=r[2],groups=json.loads(r[3]),state=r[4]) for r in db.execute('SELECT * FROM positions ORDER BY id')]
