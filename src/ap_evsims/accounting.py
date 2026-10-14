"""Append-only reconciled cash/bonus journal. Records external actions; never places bets."""
from decimal import Decimal,InvalidOperation
import json
from .integrity import database,digest,utc

def cents(value):
    try:
        amount=Decimal(str(value))
        if not amount.is_finite() or amount!=amount.quantize(Decimal('.01')):raise ValueError('INVALID_CURRENCY_PRECISION')
    except (InvalidOperation,TypeError):raise ValueError('INVALID_CURRENCY')
    return int(amount*100)

class AccountLedger:
    def __init__(self,path):
        self.path=str(path)
        with database(self.path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS journal (
                sequence INTEGER PRIMARY KEY,id TEXT UNIQUE,at TEXT,kind TEXT,
                cash_cents INTEGER,bonus_cents INTEGER,reference TEXT,body TEXT,body_hash TEXT)''')
    def append(self, *, transaction_id,at,kind,cash_delta=0,bonus_delta=0,reference,source):
        kinds={'opening_reconciliation','deposit','withdrawal','bonus_credit','cash_stake','bonus_stake','settlement','correction','bonus_expiry'}
        if kind not in kinds or not transaction_id or not reference or not source:raise ValueError('INVALID_ACCOUNT_TRANSACTION')
        cash,bonus=cents(cash_delta),cents(bonus_delta);at=utc(at).isoformat()
        if kind=='deposit' and (cash<=0 or bonus!=0):raise ValueError('INVALID_ACCOUNT_TRANSACTION')
        if kind in ('withdrawal','cash_stake') and (cash>=0 or bonus!=0):raise ValueError('INVALID_ACCOUNT_TRANSACTION')
        if kind in ('bonus_stake','bonus_expiry') and (bonus>=0 or cash!=0):raise ValueError('INVALID_ACCOUNT_TRANSACTION')
        if kind=='bonus_credit' and (bonus<=0 or cash!=0):raise ValueError('INVALID_ACCOUNT_TRANSACTION')
        if kind=='settlement' and (cash<0 or bonus<0):raise ValueError('USE_CORRECTION_TRANSACTION')
        body=dict(id=transaction_id,at=at,kind=kind,cash_cents=cash,bonus_cents=bonus,reference=reference,source=source)
        fingerprint=digest(body)
        with database(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT body_hash FROM journal WHERE id=?',(transaction_id,)).fetchone()
            if prior:
                if prior[0]!=fingerprint:raise ValueError('ACCOUNT_TRANSACTION_MUTATION')
                return transaction_id
            existing=db.execute('SELECT kind,at FROM journal ORDER BY sequence DESC LIMIT 1').fetchone()
            if existing is None and kind!='opening_reconciliation':raise ValueError('BANKROLL_NOT_RECONCILED')
            if existing and kind=='opening_reconciliation':raise ValueError('OPENING_ALREADY_RECORDED')
            if existing and utc(at)<utc(existing[1]):raise ValueError('ACCOUNT_TIME_REVERSAL')
            if kind in ('cash_stake','bonus_stake','settlement') and db.execute('SELECT 1 FROM journal WHERE kind=? AND reference=?',(kind,reference)).fetchone():raise ValueError('DUPLICATE_ECONOMIC_TRANSACTION')
            if kind=='correction' and not db.execute('SELECT 1 FROM journal WHERE id=?',(reference,)).fetchone():raise ValueError('UNKNOWN_CORRECTION_REFERENCE')
            totals=db.execute('SELECT coalesce(sum(cash_cents),0),coalesce(sum(bonus_cents),0) FROM journal').fetchone()
            if totals[0]+cash<0 or totals[1]+bonus<0:raise ValueError('INSUFFICIENT_ACCOUNT_BALANCE')
            db.execute('INSERT INTO journal(id,at,kind,cash_cents,bonus_cents,reference,body,body_hash) VALUES (?,?,?,?,?,?,?,?)',
                (transaction_id,at,kind,cash,bonus,reference,json.dumps(body,sort_keys=True),fingerprint))
        return transaction_id
    def state(self):
        with database(self.path) as db:rows=db.execute('SELECT body,body_hash FROM journal ORDER BY sequence').fetchall()
        cash=bonus=0;last=None
        for raw,fingerprint in rows:
            body=json.loads(raw)
            if digest(body)!=fingerprint:raise ValueError('ACCOUNT_HASH_MISMATCH')
            cash+=body['cash_cents'];bonus+=body['bonus_cents'];last=body['at']
        return dict(cash_bankroll=cash/100 if rows else None,bonus_balance=bonus/100 if rows else None,
            last_reconciled_at=last,transaction_count=len(rows),status='RECORDED_EXTERNAL_ACCOUNT' if rows else 'BANKROLL_NOT_RECONCILED')
