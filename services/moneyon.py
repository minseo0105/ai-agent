"""MONEY:ON local educational ledger. No bank or external AI calls."""
import calendar
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from services import moneyon_accounts as accounts


def period(today, policy):
    if policy['frequency'] == 'weekly':
        start = today - timedelta(days=(today.weekday() - policy['pay_day']) % 7)
        return start, start + timedelta(days=7)
    def day(y, m):
        return date(y, m, min(policy['pay_day'], calendar.monthrange(y, m)[1]))
    start = day(today.year, today.month)
    if start > today:
        prev = today.replace(day=1) - timedelta(days=1)
        start = day(prev.year, prev.month)
    nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, day(nxt.year, nxt.month)


def reward(eligible, policy):
    amount = max(0, eligible) * policy['rate_bps'] // 10000
    return amount if policy['cap'] is None else min(amount, policy['cap'])


class Ledger:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS moneyon_schema(version INTEGER PRIMARY KEY);
            INSERT OR IGNORE INTO moneyon_schema VALUES(1);
            CREATE TABLE IF NOT EXISTS families(id TEXT PRIMARY KEY, salt TEXT NOT NULL, pin TEXT NOT NULL, failures INTEGER DEFAULT 0, locked_until INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS children(id TEXT PRIMARY KEY, family TEXT NOT NULL, profile TEXT NOT NULL, policy TEXT NOT NULL, status TEXT DEFAULT 'active');
            CREATE TABLE IF NOT EXISTS cycles(id TEXT PRIMARY KEY, child TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, policy TEXT NOT NULL, eligible INTEGER NOT NULL, settled INTEGER DEFAULT 0, UNIQUE(child,start));
            CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY, child TEXT NOT NULL, cycle TEXT, kind TEXT NOT NULL, wallet INTEGER NOT NULL, vault INTEGER NOT NULL DEFAULT 0, eligible_delta INTEGER NOT NULL DEFAULT 0, category TEXT, note TEXT, created TEXT NOT NULL, request_key TEXT NOT NULL, UNIQUE(child,request_key));
            CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY, child TEXT NOT NULL, name TEXT NOT NULL, amount INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, family TEXT NOT NULL, child TEXT, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS quest_progress(child TEXT NOT NULL, quest TEXT NOT NULL, completed TEXT NOT NULL, PRIMARY KEY(child,quest));
            ''')
            db.executescript(accounts.SCHEMA)
            db.execute('BEGIN IMMEDIATE')
            accounts.migrate(db)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def unlock(self, family, pin):
        with self.db() as db:
            row = db.execute('SELECT * FROM families WHERE id=?', (family,)).fetchone()
            if row and row['locked_until'] > time.time():
                return None
            salt = row['salt'] if row else secrets.token_hex(16)
            digest = hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
            if row and not hmac.compare_digest(row['pin'], digest):
                failures = row['failures'] + 1
                db.execute('UPDATE families SET failures=?,locked_until=? WHERE id=?', (failures, int(time.time()) + 300 if failures >= 5 else 0, family))
                return None
            db.execute('INSERT OR IGNORE INTO families(id,salt,pin) VALUES(?,?,?)', (family, salt, digest))
            accounts.ensure_family(db, family)
            db.execute('UPDATE families SET failures=0,locked_until=0 WHERE id=?', (family,))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?,NULL,?)', (token, family, int(time.time()) + 900))
            return token

    def authorize(self, family, token, child=None, parent=False):
        with self.db() as db:
            row = db.execute('SELECT * FROM sessions WHERE token=? AND family=? AND expires>?', (token, family, int(time.time()))).fetchone()
            if not row or (parent and row['child']) or (row['child'] and row['child'] != child):
                raise PermissionError('부모 인증 또는 아이 선택이 필요해요.')
            if row['child']:
                self._child(db, family, row['child'], active=True)
            return dict(row)

    def child_session(self, family, parent_token, child):
        self.authorize(family, parent_token, parent=True)
        with self.db() as db:
            self._child(db, family, child, active=True)
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token, family, child, int(time.time()) + 3600))
            db.execute('DELETE FROM sessions WHERE token=?', (parent_token,))
            return token

    def lock(self, family, token):
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE family=? AND token=?', (family, token))

    def _child(self, db, family, child, active=False):
        row = db.execute('SELECT * FROM children WHERE id=? AND family=?', (child, family)).fetchone()
        if not row or (active and row['status'] != 'active'):
            raise PermissionError('이 아이의 계정을 이용할 수 없어요.')
        return row

    def children(self, family):
        with self.db() as db:
            return [dict(r) | {'profile': json.loads(r['profile']), 'policy': json.loads(r['policy'])} for r in db.execute('SELECT * FROM children WHERE family=?', (family,))]

    def save_child(self, family, profile, policy, child=None, status='active'):
        with self.db() as db:
            if child:
                self._child(db, family, child)
                db.execute('UPDATE children SET profile=?,policy=?,status=? WHERE id=?', (json.dumps(profile), json.dumps(policy), status, child))
            else:
                child = str(uuid.uuid4())
                db.execute('INSERT INTO children VALUES(?,?,?,?,?)', (child, family, json.dumps(profile), json.dumps(policy), status))
            accounts.ensure_child(db, family, child)
            return child

    def _balance(self, db, child):
        return accounts.child_balance(db, child)

    def _entry(self, db, child, cycle, kind, wallet, vault, delta, key, category='', note='', metadata=None, business_date=None):
        family = db.execute('SELECT family FROM children WHERE id=?', (child,)).fetchone()[0]
        transaction_id = str(uuid.uuid4())
        occurred_at = accounts.now(db, family)
        if business_date:
            occurred_at = business_date.isoformat() + occurred_at[10:]
        db.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?)', (transaction_id, child, cycle, kind, wallet, vault, delta, category, note, occurred_at, key))
        entry = db.execute('SELECT * FROM transactions WHERE id=?', (transaction_id,)).fetchone()
        accounts.record(db, entry, metadata=metadata)

    def _eligible(self, db, cycle):
        used = db.execute('SELECT COALESCE(SUM(eligible_delta),0) FROM transactions WHERE cycle=?', (cycle['id'],)).fetchone()[0]
        return max(0, cycle['eligible'] + used)

    def state(self, family, child, today=None):
        today = today or datetime.now(accounts.KST).date()
        with self.db() as db:
            c = self._child(db, family, child)
            cycles = []
            for row in db.execute('SELECT * FROM cycles WHERE child=? ORDER BY start DESC', (child,)):
                r = dict(row)
                r['policy'] = json.loads(r['policy'])
                r['eligible'] = self._eligible(db, row)
                r['interest'] = reward(r['eligible'], r['policy'])
                r['ended'] = r['end'] <= today.isoformat()
                cycles.append(r)
            transactions = [dict(r) for r in db.execute('SELECT * FROM transactions WHERE child=? ORDER BY rowid DESC', (child,))]
            changes = accounts.categories(db, child)
            for t in transactions:
                t['category'] = changes.get(t['id'], t['category'])
            goals = [dict(r) for r in db.execute('SELECT * FROM goals WHERE child=?', (child,))]
            quests = [r['quest'] for r in db.execute('SELECT quest FROM quest_progress WHERE child=?', (child,))]
            days = len({t['created'][:10] for t in transactions if t['kind'] == 'expense'})
            balance = self._balance(db, child)
            xp = days * 10 + bool(goals) * 20 + len(quests) * 20
            stage = min(5, xp // 50)
            badges = (['첫 기록'] if days else []) + (['꿈 설계자'] if goals else []) + (['금융 탐험가'] if quests else []) + (['꾸준한 기록'] if days >= 3 else [])
            month = today.strftime('%Y-%m')
            monthly = [t for t in transactions if t['created'].startswith(month)]
            cancelled = {t['request_key'][7:] for t in transactions if t['kind'] == 'expense_cancel'}
            expenses = [t for t in monthly if t['kind'] == 'expense' and t['id'] not in cancelled]
            categories = {}
            for t in expenses:
                categories[t['category']] = categories.get(t['category'], 0) - t['wallet']
            received = sum(t['wallet'] for t in monthly if t['kind'] == 'payment')
            spent = sum(-t['wallet'] for t in expenses)
            report = {'paid': received, 'spent': spent, 'interest': sum(t['wallet'] for t in monthly if t['kind'] == 'interest'), 'categories': categories, 'record_days': len({t['created'][:10] for t in expenses}), 'savings_rate': max(0, (received-spent)*100//received) if received else None}
            bank_accounts = accounts.accounts(db, family, child)
            bank_transactions = [t for a in bank_accounts for t in accounts.transactions(db, family, a['id'], child)]
            bank_transactions.sort(key=lambda t: t['seq'], reverse=True)
            return balance | {'cycles': cycles, 'transactions': transactions, 'goals': goals, 'quests': quests, 'xp': xp, 'stage': stage, 'badges': badges, 'report': report, 'banking': {'accounts': bank_accounts, 'transactions': bank_transactions}, 'next_payday': period(today, json.loads(c['policy']))[1].isoformat()}

    def complete_quiz(self, family, child, quest, answer):
        with self.db() as db:
            c = self._child(db, family, child, active=True)
            grade = json.loads(c['profile'])['grade']
            expected = {'interest': 100 if grade <= 3 else 750, 'needs': 1}
            if quest not in expected:
                raise ValueError('이 퀘스트를 찾을 수 없어요.')
            if answer != expected[quest]:
                return False
            db.execute('INSERT OR IGNORE INTO quest_progress VALUES(?,?,?)', (child, quest, accounts.now(db, family)[:10]))
            return True

    def transact(self, family, child, kind, key, amount=0, category='', note='', cycle_id=None, today=None, metadata=None):
        today = today or datetime.now(accounts.KST).date()
        with self.db() as db:
            c = self._child(db, family, child, active=True)
            existing = db.execute('SELECT * FROM transactions WHERE child=? AND request_key=?', (child, key)).fetchone()
            if existing:
                if existing['kind'] != kind or (kind in ('expense', 'deposit', 'withdraw') and abs(existing['wallet']) != amount) or (kind == 'expense' and (existing['note'] != note or existing['category'] != category)) or (kind == 'interest' and existing['cycle'] != cycle_id):
                    raise ValueError('같은 요청 키를 다른 거래에 사용할 수 없어요.')
                return
            bal = self._balance(db, child)
            current = db.execute('SELECT * FROM cycles WHERE child=? AND start<=? AND end>?', (child, today.isoformat(), today.isoformat())).fetchone()
            policy = json.loads(c['policy'])
            if kind == 'payment':
                start, end = period(today, policy)
                if db.execute('SELECT 1 FROM cycles WHERE child=? AND start<? AND end>?', (child, end.isoformat(), start.isoformat())).fetchone():
                    raise ValueError('이미 지급한 주기와 겹쳐요.')
                cid = str(uuid.uuid4())
                db.execute('INSERT INTO cycles VALUES(?,?,?,?,?,?,0)', (cid, child, start.isoformat(), end.isoformat(), json.dumps(policy), policy['amount']))
                self._entry(db, child, cid, kind, policy['amount'], 0, 0, key, business_date=today)
                return
            if kind == 'interest':
                cyc = db.execute('SELECT * FROM cycles WHERE id=? AND child=?', (cycle_id, child)).fetchone()
                if not cyc or cyc['end'] > today.isoformat() or cyc['settled']:
                    raise ValueError('종료된 미정산 주기만 승인할 수 있어요.')
                p = json.loads(cyc['policy'])
                eligible = self._eligible(db, cyc)
                interest = reward(eligible, p)
                if accounts.balance(db, accounts.ensure_family(db, family)) < interest:
                    raise ValueError('부모 가상 계좌 잔액이 부족해요.')
                if not p['rollover']:
                    self._entry(db, child, cyc['id'], 'expiry', -min(eligible, bal['wallet']), 0, -eligible, key + ':expiry', note='이월하지 않는 신규 용돈 회수', business_date=today)
                self._entry(db, child, cyc['id'], kind, interest, 0, 0, key, business_date=today)
                db.execute('UPDATE cycles SET settled=1 WHERE id=?', (cyc['id'],))
                return
            if amount <= 0 or type(amount) is not int:
                raise ValueError('금액은 1원 이상의 정수로 입력해 주세요.')
            if kind not in ('expense', 'deposit', 'withdraw'):
                raise ValueError('지원하지 않는 거래예요.')
            if amount > bal['vault' if kind == 'withdraw' else 'wallet']:
                raise ValueError('사용할 수 있는 잔액이 부족해요.')
            # Consume the new allowance first; vault withdrawals never restore eligibility.
            # Closed periods retain their eligibility; only the open period can change.
            remaining = amount if kind != 'withdraw' else 0
            for cyc in db.execute('SELECT * FROM cycles WHERE child=? AND settled=0 AND end>? ORDER BY start', (child, today.isoformat())).fetchall():
                delta = min(remaining, self._eligible(db, cyc))
                if delta:
                    self._entry(db, child, cyc['id'], 'eligibility', 0, 0, -delta, key + ':' + cyc['id'], business_date=today)
                    remaining -= delta
            self._entry(db, child, current['id'] if current else None, kind, amount if kind == 'withdraw' else -amount, amount if kind == 'deposit' else -amount if kind == 'withdraw' else 0, 0, key, category, note, metadata, business_date=today)

    def goal(self, family, child, name, amount):
        with self.db() as db:
            self._child(db, family, child, active=True)
            db.execute('INSERT INTO goals VALUES(?,?,?,?)', (str(uuid.uuid4()), child, name, amount))

    def cancel_expense(self, family, child, transaction, reason, today=None):
        today = today or datetime.now(accounts.KST).date()
        with self.db() as db:
            self._child(db, family, child, active=True)
            original = db.execute("SELECT * FROM transactions WHERE id=? AND child=? AND kind='expense'", (transaction, child)).fetchone()
            if not original:
                raise ValueError('취소할 지출을 찾을 수 없어요.')
            key = 'cancel:' + transaction
            if db.execute('SELECT 1 FROM transactions WHERE child=? AND request_key=?', (child, key)).fetchone():
                return
            if original['cycle']:
                cycle = db.execute('SELECT * FROM cycles WHERE id=?', (original['cycle'],)).fetchone()
                if cycle['settled'] or cycle['end'] <= today.isoformat():
                    raise ValueError('종료된 주기 지출은 정산 보호를 위해 취소할 수 없어요.')
            # Reverse the original eligibility allocations, retaining both audit entries.
            allocations = db.execute("SELECT * FROM transactions WHERE child=? AND kind='eligibility'", (child,)).fetchall()
            for entry in allocations:
                if entry['request_key'] == original['request_key'] + ':' + entry['cycle']:
                    self._entry(db, child, entry['cycle'], 'eligibility', 0, 0, -entry['eligible_delta'], key + ':' + entry['cycle'], note=reason, business_date=today)
            self._entry(db, child, original['cycle'], 'expense_cancel', -original['wallet'], 0, 0, key, note=reason, business_date=today)
