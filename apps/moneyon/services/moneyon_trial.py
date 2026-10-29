"""Capability-scoped trial workspaces in a dedicated SQLite file.

Only the trial ledger binds nested operations to one transaction. The family
ledger, reward calculation and double-entry Mock Banking postings are reused.
"""
import hashlib
import json
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from pathlib import Path

from services.moneyon import Ledger, reward, period
from services import moneyon_accounts as accounts
from services.moneyon_banking import MockBankingAdapter
from services import moneyon_savings as savings

# Pre-seeded sample workspaces wait under this owner until a visitor claims one.
# The suffix is the seed rules version: samples made under older rules (owner
# 'pool', 'pool:v2' = fixed 2026-10-12 trial date) are never handed out and are removed by cleanup.
POOL = 'pool:v3'
LEGACY_POOLS = ('pool', 'pool:v2')


def kst_today():
    """실제 한국시간 오늘. 서버 시계가 UTC여도(자정~09시는 UTC로 아직 어제) 한국 날짜."""
    return datetime.now(accounts.KST).date()
# New trials: interest in whole 100원 (amounts under 100원 are dropped) and the
# child presses "이자 받기" after the weekly settlement instead of automatic payment.
UNIT = 100


def split(total, weights, unit=1, ids=()):
    """Share total by weights in whole units; leftover units go to the largest remainders, ties by id."""
    whole = sum(weights)
    if not whole:
        return [0] * len(weights)
    units = total // unit
    shares = [units * w // whole for w in weights]
    ids = list(ids) or list(range(len(weights)))
    for n in sorted(range(len(weights)), key=lambda n: (-(units * weights[n] % whole), ids[n]))[:units - sum(shares)]:
        shares[n] += 1
    shares = [s * unit for s in shares]
    shares[0] += total - units * unit
    return shares
# Lookups that scanned whole tables once many visitors had accumulated.
INDEXES = (
    'CREATE INDEX IF NOT EXISTS transactions_cycle ON transactions(cycle)',
    'CREATE INDEX IF NOT EXISTS bank_accounts_child ON bank_accounts(child)',
    'CREATE INDEX IF NOT EXISTS book_entries_book ON moneyon_book_entries(book)',
    'CREATE INDEX IF NOT EXISTS goals_child ON goals(child)',
    'CREATE INDEX IF NOT EXISTS bank_events_family ON bank_events(family)',
    'CREATE INDEX IF NOT EXISTS children_family ON children(family)',
    'CREATE INDEX IF NOT EXISTS category_changes_child ON bank_category_changes(child)',
    'CREATE INDEX IF NOT EXISTS trial_visitors_expires ON trial_visitors(expires)',
    'CREATE INDEX IF NOT EXISTS trial_visitors_seen ON trial_visitors(last_seen)',
)
_locks = {}
_locks_guard = threading.Lock()


def _path_lock(path):
    # One process serves the Space. Queueing writers here wakes them in turn
    # instead of letting SQLite's busy handler sleep-poll past its timeout.
    with _locks_guard:
        return _locks.setdefault(str(Path(path).resolve()), threading.RLock())


class TrialLedger(Ledger):
    def __init__(self, path):
        self.connection = ContextVar('trial_connection', default=None)
        self.lock = _path_lock(path)
        # One connection is reused while requests are queued and closed once the
        # queue empties: closing the last WAL connection checkpoints the file.
        self.shared = None
        self.queued = 0
        self.queue_guard = threading.Lock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # WAL is a property of the file and must be set outside a transaction.
        wal = sqlite3.connect(str(path), timeout=30)
        try:
            wal.execute('PRAGMA journal_mode=WAL')
        finally:
            wal.close()
        super().__init__(path)
        with self.db() as db:
            savings.install(db)
            db.execute('''CREATE TABLE IF NOT EXISTS trial_visitors(
                capability TEXT PRIMARY KEY, family TEXT NOT NULL, child TEXT NOT NULL,
                expires INTEGER NOT NULL, generation INTEGER NOT NULL, reset_key TEXT)''')
            if 'last_seen' not in {r['name'] for r in db.execute('PRAGMA table_info(trial_visitors)')}:
                db.execute('ALTER TABLE trial_visitors ADD COLUMN last_seen INTEGER NOT NULL DEFAULT 0')
            db.execute('''CREATE TABLE IF NOT EXISTS trial_rewards(
                child TEXT NOT NULL, cycle TEXT NOT NULL, reward_type TEXT NOT NULL,
                base INTEGER NOT NULL, amount INTEGER NOT NULL, transaction_id TEXT NOT NULL,
                paid_at TEXT NOT NULL, PRIMARY KEY(child,cycle,reward_type))''')
            # 실제 날짜를 따르는 체험(10-29부터 새로 만든 것). 체험일이 실제 오늘보다 뒤처지면 오늘로 따라간다.
            db.execute('CREATE TABLE IF NOT EXISTS trial_clock(family TEXT PRIMARY KEY, since TEXT NOT NULL)')
            db.execute('''CREATE TABLE IF NOT EXISTS trial_closings(
                child TEXT NOT NULL, cycle TEXT NOT NULL, reward_type TEXT NOT NULL,
                base INTEGER NOT NULL, amount INTEGER NOT NULL,
                PRIMARY KEY(child,cycle,reward_type))''')
            for statement in INDEXES:
                db.execute(statement)

    def _connect(self):
        # Shared between request threads, always under self.lock.
        db = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=30000')
        db.execute('PRAGMA synchronous=NORMAL')
        return db

    def reward_items(self, db, child, cycle, today):
        policy = json.loads(cycle['policy']) if isinstance(cycle['policy'], str) else cycle['policy']
        if not policy.get('dual_rewards'):
            return []
        # Closing balances are reconstructed from dated ledger entries, so later
        # approval deposits never change an already closed week's principal.
        cutoff = min(today.isoformat(), cycle['end'])
        ended = cycle['end'] <= today.isoformat()
        rows = db.execute('SELECT wallet,vault,kind,created FROM transactions WHERE child=? AND substr(created,1,10) '
                          + ('<' if ended else '<=') + ' ?', (child, cutoff)).fetchall()
        # Prior-week interest is part of this week's spendable wallet. Closed
        # snapshots and their exclusive end date prevent retroactive interest
        # or duplicate settlement; do not subtract those credits a second time.
        bases = {'allowance_bonus': max(0, sum(r['wallet'] for r in rows)),
                 'savings_interest': sum(r['vault'] for r in rows)}
        items = []
        for kind, base in bases.items():
            paid = db.execute('SELECT * FROM trial_rewards WHERE child=? AND cycle=? AND reward_type=?',
                              (child, cycle['id'], kind)).fetchone()
            rule = policy['dual_rewards'][kind]
            closing = db.execute('SELECT base,amount FROM trial_closings WHERE child=? AND cycle=? AND reward_type=?',
                                 (child, cycle['id'], kind)).fetchone()
            base = paid['base'] if paid else closing['base'] if closing else base
            amount = paid['amount'] if paid else closing['amount'] if closing else reward(base, rule)
            items.append(dict(cycle_id=cycle['id'], start=cycle['start'], end=cycle['end'],
                              reward_type=kind, base=max(0, base), amount=amount,
                              destination='wallet' if kind == 'allowance_bonus' else 'vault',
                              rate_bps=rule['rate_bps'], cap=rule['cap'], unit=rule.get('unit', 1),
                              status='paid' if paid else 'awaiting_approval' if ended else 'estimated',
                              paid_amount=paid['amount'] if paid else 0,
                              paid_at=paid['paid_at'] if paid else None,
                              transaction_id=paid['transaction_id'] if paid else None))
            items[-1]['payment_mode']=savings.mode(db,child,cycle['start'])
        return items

    def state(self, family, child, today=None):
        with self.db() as db:
            state = super().state(family, child, today)
            state['books'] = savings.balances(db, child)
            if sum(b['balance'] for b in state['books']) != state['vault']:
                raise ValueError('저축통장과 원장 잔액이 일치하지 않아요.')
            for book in state['books']:
                book['history'] = [dict(r) for r in db.execute('''SELECT t.id,t.kind,t.created,e.amount FROM moneyon_book_entries e
                    JOIN transactions t ON t.id=e.transaction_id WHERE e.book=? ORDER BY t.rowid DESC''',(book['id'],))]
            day = today or date.fromisoformat(accounts.now(db, family)[:10])
            state['payment_rule'] = dict(current=savings.mode(db,child,day.isoformat()),
                scheduled=[dict(r) for r in db.execute('SELECT effective,mode FROM moneyon_payment_rules WHERE child=? ORDER BY effective',(child,))])
            state['payout_choices'] = [dict(payout=t['id'],amount=t['wallet'],available=savings.payout_available(db,child,t['id']),
                choice=dict(choice) if (choice:=db.execute('SELECT * FROM moneyon_reward_choices WHERE payout=?',(t['id'],)).fetchone()) else None)
                for t in state['transactions'] if t['kind']=='allowance_bonus']
            items = [item for c in state['cycles'] for item in self.reward_items(db, child, c, day)]
            if items:
                current = next((c for c in state['cycles'] if c['start'] <= day.isoformat() < c['end']), None)
                estimates = [i for i in items if current and i['cycle_id'] == current['id']]
                state['rewards'] = dict(items=items, estimates={i['reward_type']: i['amount'] for i in estimates},
                                        expected_total=sum(i['amount'] for i in estimates), destination='separate')
                # Split the one aggregate estimate, never calculate the capped rate anew for every book.
                total_interest=state['rewards']['estimates'].get('savings_interest',0)
                unit=next((i['unit'] for i in estimates if i['reward_type']=='savings_interest'),1)
                shares=split(total_interest,[b['balance'] for b in state['books']],unit,[b['id'] for b in state['books']])
                for book,share in zip(state['books'],shares):
                    book['interest']=share
                if current:
                    tx = [t for t in state['transactions'] if current['start'] <= t['created'][:10] < current['end']]
                    state['education'] = dict(start=current['start'], end=current['end'],
                        opening=sum(t['wallet'] for t in state['transactions'] if t['created'][:10] < current['start']),
                        received=sum(t['wallet'] for t in tx if t['kind'] == 'payment'),
                        interest_received=sum(t['wallet'] for t in tx if t['kind'] in ('interest', 'allowance_bonus')),
                        spent=-sum(t['wallet'] for t in tx if t['kind'] in ('expense', 'expense_cancel')),
                        saved=sum(t['vault'] for t in tx if t['kind'] == 'deposit'),
                        withdrawn=sum(t['wallet'] for t in tx if t['kind'] == 'withdraw'),
                        other_in=sum(max(0,t['wallet']) for t in tx if t['kind'] not in ('payment','interest','allowance_bonus','expense','expense_cancel','deposit','withdraw')),
                        other_out=-sum(min(0,t['wallet']) for t in tx if t['kind'] not in ('payment','interest','allowance_bonus','expense','expense_cancel','deposit','withdraw')),
                        parent_balance=accounts.balance(db, accounts.ensure_family(db, family)))
                    summary=state['education']
                    summary['remaining']=summary['opening']+summary['received']+summary['interest_received']+summary['other_in']+summary['withdrawn']-summary['spent']-summary['saved']-summary['other_out']
                    if summary['remaining'] != state['wallet']:
                        raise ValueError('주간 결산과 통장 잔액이 일치하지 않아요.')
                for c in state['cycles']:
                    own = [i for i in items if i['cycle_id'] == c['id']]
                    if own:
                        c['interest'] = sum(i['amount'] for i in own if i['status'] != 'paid')
            return state

    def settle_rewards(self, family, child, cycle_id, key, today, reward_type=None):
        with self.db() as db:
            self._child(db, family, child, active=True)
            cycle = db.execute('SELECT * FROM cycles WHERE child=? AND id=?', (child, cycle_id)).fetchone()
            if not cycle or cycle['end'] > today.isoformat():
                raise ValueError('종료된 주차만 승인할 수 있어요.')
            items = self.reward_items(db, child, dict(cycle), today)
            if not items:
                raise ValueError('이 주차는 기존 보상 정책을 사용해요.')
            selected = [i for i in items if reward_type is None or i['reward_type'] == reward_type]
            for item in selected:
                if item['status'] == 'paid':
                    previous_key = db.execute('SELECT request_key FROM transactions WHERE id=?', (item['transaction_id'],)).fetchone()[0]
                    if previous_key != key + ':' + item['reward_type']:
                        raise ValueError('이미 지급한 보상이에요.')
                    continue
                kind = item['reward_type']
                entry_key = key + ':' + kind
                if db.execute('SELECT 1 FROM transactions WHERE child=? AND request_key=?', (child, entry_key)).fetchone():
                    raise ValueError('같은 요청 키를 다른 주차에 사용할 수 없어요.')
                self._entry(db, child, cycle_id, kind,
                            item['amount'] if kind == 'allowance_bonus' else 0,
                            item['amount'] if kind == 'savings_interest' else 0, 0, entry_key,
                            note='엄마 은행 용돈 이자' if kind == 'allowance_bonus' else '저금통 이자', business_date=today)
                transaction = db.execute('SELECT id FROM transactions WHERE child=? AND request_key=?', (child, entry_key)).fetchone()[0]
                if kind == 'savings_interest':
                    # Attribute paid interest to the books held at the immutable closing cutoff.
                    books=savings.balances(db,child)
                    # balances() migrates unassigned legacy rows; remove this new credit before allocation.
                    db.execute('DELETE FROM moneyon_book_entries WHERE transaction_id=?',(transaction,))
                    weights=[max(0,db.execute('''SELECT COALESCE(SUM(e.amount),0) FROM moneyon_book_entries e JOIN transactions t ON t.id=e.transaction_id
                        WHERE e.book=? AND substr(t.created,1,10)<?''',(b['id'],cycle['end'])).fetchone()[0]) for b in books]
                    amounts=split(item['amount'],weights,item['unit'],[b['id'] for b in books])
                    if not sum(weights): amounts[0]=item['amount']
                    for book,amount in zip(books,amounts):
                        if amount: db.execute('INSERT INTO moneyon_book_entries VALUES(?,?,?)',(transaction,book['id'],amount))
                db.execute('INSERT INTO trial_rewards VALUES(?,?,?,?,?,?,?)',
                           (child, cycle_id, kind, item['base'], item['amount'], transaction, accounts.now(db, family)))
            count = db.execute('SELECT COUNT(*) FROM trial_rewards WHERE child=? AND cycle=?', (child, cycle_id)).fetchone()[0]
            if count == 2:
                db.execute('UPDATE cycles SET settled=1 WHERE id=?', (cycle_id,))

    @contextmanager
    def db(self):
        current = self.connection.get()
        if current is not None:
            savepoint = 'nested_' + uuid.uuid4().hex
            current.execute('SAVEPOINT ' + savepoint)
            try:
                yield current
                current.execute('RELEASE ' + savepoint)
            except Exception:
                current.execute('ROLLBACK TO ' + savepoint)
                current.execute('RELEASE ' + savepoint)
                raise
        else:
            with self.queue_guard:
                self.queued += 1
            with self.lock:
                try:
                    if self.shared is None:
                        self.shared = self._connect()
                    db = self.shared
                    token = self.connection.set(db)
                    try:
                        db.execute('BEGIN IMMEDIATE')
                        try:
                            yield db
                            db.commit()
                        except BaseException:
                            db.rollback()
                            raise
                    finally:
                        self.connection.reset(token)
                finally:
                    with self.queue_guard:
                        self.queued -= 1
                        idle = self.queued == 0
                    if idle and self.shared is not None:
                        self.shared.close()
                        self.shared = None


class Trials:
    def __init__(self, ledger, unit=UNIT, payment='manual', today=kst_today):
        # Rules for newly seeded trials. Existing trials keep the rules stored with them;
        # unit=1, payment='automatic' reproduces the earlier trial rules.
        # 체험일은 실제 한국시간 오늘(today). 미리 채운 예시 기록은 이번 주 월요일(주간 정산 시작일)에 둔다.
        self.ledger, self.unit, self.payment, self.today = ledger, unit, payment, today

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def resolve(self, token, child=None, generation=None):
        with self.ledger.db() as db:
            now = int(time.time())
            row = db.execute('SELECT * FROM trial_visitors WHERE capability=? AND expires>?',
                             (self.digest(token), now)).fetchone()
            if not token or not row or (child is not None and row['child'] != child):
                raise PermissionError('체험 세션이 없거나 만료됐어요. 새 체험을 시작해 주세요.')
            if generation is not None and row['generation'] != generation:
                raise ValueError('초기화된 통장이에요. 새로고침하고 다시 해 주세요.')
            if row['last_seen'] < now - 60:
                db.execute('UPDATE trial_visitors SET last_seen=? WHERE capability=?', (now, row['capability']))
            self.catch_up(dict(row))
            return dict(row)

    def catch_up(self, row):
        """실제 날짜를 따르는 체험이 자정을 넘겨 실제 오늘보다 뒤처졌으면 오늘로 옮긴다(주 경계·이자 마감은 advance가 순서대로).
        '일주일 뒤 보기'로 앞으로 옮긴 체험(체험일 > 오늘)과 예전 고정 날짜 체험은 그대로 둔다."""
        with self.ledger.db() as db:
            if not db.execute('SELECT 1 FROM trial_clock WHERE family=?', (row['family'],)).fetchone():
                return
        today = self.today()
        if self.day(row) < today:
            self.advance(row, today)

    def day(self, row):
        with self.ledger.db() as db:
            return date.fromisoformat(db.execute('SELECT business_date FROM moneyon_demo_workspaces WHERE family=?', (row['family'],)).fetchone()[0])

    def seed(self, owner):
        # A completed historical cycle earns 1,500, returns its principal,
        # and leaves only the earned reward as the current opening balance.
        family = 'trial:' + str(uuid.uuid4())
        today = self.today()
        day = today - timedelta(days=today.weekday())  # 이번 주 월요일: 예시 기록(지난주 용돈·이번 주 용돈·쓴 돈·저금)의 날짜
        policy = dict(frequency='weekly', amount=15000, pay_day=0,
                      rate_bps=1000, cap=1500, rollover=False)
        dbledger = self.ledger
        with dbledger.db() as db:
            db.execute('INSERT INTO families(id,salt,pin) VALUES(?,?,?)', (family, secrets.token_hex(16), secrets.token_hex(64)))
            db.execute('INSERT INTO moneyon_demo_workspaces VALUES(?,?,?,?,?)', (family, owner, day.isoformat(), 1, accounts.now(db, family)))
            child = dbledger.save_child(family, dict(name='하늘', grade=2, avatar='🪙', theme='moneyon'), policy)
            adapter = MockBankingAdapter(dbledger)
            adapter.transfer_allowance(family, child, 'seed-previous-payment', day - timedelta(days=7))
            cycle = db.execute('SELECT id FROM cycles WHERE child=?', (child,)).fetchone()[0]
            adapter.settle_reward_interest(family, child, 'seed-previous-reward', cycle, day)
            policy.update(amount=50000, cap=1000000, rollover=True)
            dbledger.save_child(family, dict(name='하늘', grade=2, avatar='🪙', theme='moneyon'), policy, child)
            adapter.transfer_allowance(family, child, 'seed-current-payment', day)
            dbledger.transact(family, child, 'expense', 'seed-stationery', 5000, '문구', '문구 구매', today=day)
            dbledger.transact(family, child, 'expense', 'seed-snack', 3000, '간식', '간식 구매', today=day)
            adapter.transfer_to_savings(family, child, 'seed-savings', 15000, day)
            policy['dual_rewards'] = {'allowance_bonus': {'rate_bps': 1000, 'cap': None},
                                      'savings_interest': {'rate_bps': 200, 'cap': 2000}}
            if self.unit != 1:
                for rule in policy['dual_rewards'].values():
                    rule['unit'] = self.unit
            dbledger.save_child(family, dict(name='하늘', grade=2, avatar='🪙', theme='moneyon'), policy, child)
            db.execute('UPDATE cycles SET policy=? WHERE child=? AND settled=0', (json.dumps(policy), child))
            dbledger.goal(family, child, '나의 첫 자전거', 30000)
            savings.migrate(db,child)
            db.execute('INSERT INTO moneyon_payment_rules VALUES(?,?,?)',(child,day.isoformat(),self.payment))
            # 체험일 = 실제 오늘(같은 주라 정산 경계를 넘지 않는다). 이제부터 새 기록은 오늘 날짜·지금 시각.
            db.execute('UPDATE moneyon_demo_workspaces SET business_date=? WHERE family=?', (today.isoformat(), family))
            db.execute('INSERT INTO trial_clock VALUES(?,?)', (family, today.isoformat()))
        return family, child

    def workspace(self, owner):
        """Claim a pre-seeded sample when one is waiting, otherwise seed now. Both are identical seeds."""
        with self.ledger.db() as db:
            # Waiting samples follow the default rules; other rules always seed fresh.
            # 미리 만든 예시는 이번 주에 만든 것만(지난주 것은 예시 기록 날짜가 지난주라 쓰지 않는다). 받으면 체험일을 오늘로.
            today = self.today()
            monday = today - timedelta(days=today.weekday())
            row = (self.unit, self.payment) == (UNIT, 'manual') and db.execute(
                'SELECT family FROM moneyon_demo_workspaces WHERE owner=? AND active=1 AND business_date>=? AND business_date<=? ORDER BY rowid LIMIT 1',
                (POOL, monday.isoformat(), today.isoformat())).fetchone()
            if not row:
                return self.seed(owner)
            db.execute('UPDATE moneyon_demo_workspaces SET owner=?,business_date=? WHERE family=?', (owner, today.isoformat(), row['family']))
            return row['family'], db.execute('SELECT id FROM children WHERE family=?', (row['family'],)).fetchone()[0]

    def pooled(self):
        """이번 주에 만든(받을 수 있는) 예시 수. 지난주 예시는 정리한다(주가 바뀌면 새로 채움)."""
        today = self.today()
        monday = (today - timedelta(days=today.weekday())).isoformat()
        with self.ledger.db() as db:
            stale = [r[0] for r in db.execute('SELECT family FROM moneyon_demo_workspaces WHERE owner=? AND business_date<? LIMIT 20', (POOL, monday))]
            for family in stale:
                db.execute('UPDATE moneyon_demo_workspaces SET owner=? WHERE family=?', (POOL + ':stale', family))
            if stale:
                self._purge(db, POOL + ':stale')
            return db.execute('SELECT COUNT(*) FROM moneyon_demo_workspaces WHERE owner=? AND active=1', (POOL,)).fetchone()[0]

    def refill(self, target):
        """Seed one waiting sample if fewer than target are ready. Returns True when one was added."""
        if self.pooled() >= target:
            return False
        self.seed(POOL)
        return True

    def start(self, cleanup=5):
        token = secrets.token_urlsafe(32)
        digest = self.digest(token)
        now = int(time.time())
        with self.ledger.db() as db:
            family, child = self.workspace(digest)
            db.execute('INSERT INTO trial_visitors(capability,family,child,expires,generation,reset_key,last_seen) VALUES(?,?,?,?,1,NULL,?)',
                       (digest, family, child, now + 86400, now))
            result = dict(token=token, **self.snapshot(self.resolve(token)))
            # Indexed probe; the rare cleanup shares this transaction instead of opening another.
            if cleanup and db.execute('SELECT 1 FROM trial_visitors WHERE expires<=? LIMIT 1', (now,)).fetchone():
                self.cleanup(now, limit=cleanup)
        return result

    def cleanup(self, now=None, limit=20, keep=None, idle=7200):
        """Delete expired visitors, then the longest-idle ones above keep. Visitors seen within idle are never removed."""
        now = int(time.time()) if now is None else now
        with self.ledger.db() as db:
            doomed = [r[0] for r in db.execute('SELECT capability FROM trial_visitors WHERE expires<=? ORDER BY expires LIMIT ?', (now, limit))]
            if keep is not None and len(doomed) < limit:
                excess = db.execute('SELECT COUNT(*) FROM trial_visitors WHERE expires>?', (now,)).fetchone()[0] - keep
                if excess > 0:
                    doomed += [r[0] for r in db.execute('SELECT capability FROM trial_visitors WHERE expires>? AND last_seen<? ORDER BY last_seen LIMIT ?',
                                                         (now, now - idle, min(excess, limit - len(doomed))))]
            for capability in doomed:
                self._purge(db, capability)
            for owner in LEGACY_POOLS:
                if db.execute('SELECT 1 FROM moneyon_demo_workspaces WHERE owner=? LIMIT 1', (owner,)).fetchone():
                    self._purge(db, owner)
            return len(doomed)

    @staticmethod
    def _purge(db, capability):
        # Every workspace this capability ever owned, including ones archived by reset.
        for (family,) in db.execute('SELECT family FROM moneyon_demo_workspaces WHERE owner=?', (capability,)).fetchall():
            children = [r[0] for r in db.execute('SELECT id FROM children WHERE family=?', (family,))]
            accounts_ = [r[0] for r in db.execute('SELECT id FROM bank_accounts WHERE family=?', (family,))]
            for account in accounts_:
                db.execute('DELETE FROM bank_postings WHERE account_id=?', (account,))
            for table in ('bank_events', 'bank_accounts', 'bank_category_changes', 'sessions'):
                db.execute(f'DELETE FROM {table} WHERE family=?', (family,))
            for child in children:
                db.execute('DELETE FROM moneyon_book_entries WHERE book IN (SELECT id FROM moneyon_books WHERE child=?)', (child,))
                for table in ('moneyon_book_approvals', 'moneyon_books', 'moneyon_reward_choices', 'moneyon_payment_rules', 'trial_rewards',
                              'trial_closings', 'quest_progress', 'goals', 'transactions', 'cycles'):
                    db.execute(f'DELETE FROM {table} WHERE child=?', (child,))
            db.execute('DELETE FROM children WHERE family=?', (family,))
            db.execute('DELETE FROM families WHERE id=?', (family,))
            db.execute('DELETE FROM moneyon_demo_workspaces WHERE family=?', (family,))
        db.execute('DELETE FROM trial_visitors WHERE capability=?', (capability,))

    def snapshot(self, row):
        with self.ledger.db():
            day = self.day(row)
            return dict(child=next(c for c in self.ledger.children(row['family']) if c['id'] == row['child']),
                        state=self.ledger.state(row['family'], row['child'], day),
                        day=day.isoformat(), generation=row['generation'], expires=row['expires'])

    def reset(self, token, generation, key):
        with self.ledger.db() as db:
            row = self.resolve(token)
            if row['reset_key'] == key and row['generation'] == generation + 1:
                return self.snapshot(row)
            self.resolve(token, generation=generation)
            family, child = self.workspace(row['capability'])
            # Old rows remain an isolated audit archive; the capability can no
            # longer address them. No family/user DB is opened here.
            db.execute('UPDATE moneyon_demo_workspaces SET active=0 WHERE family=?', (row['family'],))
            db.execute('UPDATE trial_visitors SET family=?,child=?,generation=generation+1,reset_key=? WHERE capability=?',
                       (family, child, key, row['capability']))
            return self.snapshot(self.resolve(token))

    def claim(self, row, key):
        """Pay every finished week's waiting interest in one transaction ("이자 받기").

        Only items still waiting are paid, so a repeated or concurrent claim never pays twice;
        a retry with the same key finds them paid and returns the same state."""
        day = self.day(row)
        with self.ledger.db() as db:
            paid = 0
            for cycle in db.execute('SELECT * FROM cycles WHERE child=? AND end<=? ORDER BY start', (row['child'], day.isoformat())).fetchall():
                for item in self.ledger.reward_items(db, row['child'], dict(cycle), day):
                    if item['status'] != 'awaiting_approval':
                        continue
                    self.ledger.settle_rewards(row['family'], row['child'], cycle['id'], f"{key}:{cycle['id']}", day, item['reward_type'])
                    paid += item['amount']
            return paid

    def allowance(self, row, amount, key):
        if type(amount) is not int or not 100 <= amount <= 10000000 or amount % 100:
            raise ValueError('금액은 100원 단위로 100원 이상 1천만원 이하로 입력해 주세요.')
        family, child, day = row['family'], row['child'], self.day(row)
        with self.ledger.db() as db:
            previous = db.execute('SELECT * FROM transactions WHERE child=? AND request_key=?', (child, key)).fetchone()
            if previous:
                if previous['kind'] != 'payment' or previous['wallet'] != amount:
                    raise ValueError('같은 요청 번호의 금액이 달라요.')
                return
            cycle = db.execute('SELECT * FROM cycles WHERE child=? AND start<=? AND end>? AND settled=0', (child, day.isoformat(), day.isoformat())).fetchone()
            if cycle:
                # Additional trial allowance belongs to the current snapshot;
                # existing eligibility consumption/reward engine handles it.
                self.ledger._entry(db, child, cycle['id'], 'payment', amount, 0, amount, key, note='체험 용돈 받기', business_date=day)
            else:
                c = self.ledger.children(family)[0]
                policy = dict(c['policy'], amount=amount)
                self.ledger.save_child(family, c['profile'], policy, child)
                MockBankingAdapter(self.ledger).transfer_allowance(family, child, key, day)

    def advance(self, row, day):
        if not self.day(row) <= day <= date(2027, 10, 12):
            raise ValueError('현재 체험일부터 2027-10-12 사이로 이동해 주세요.')
        # Process each boundary in date order so an automatic payment from one
        # week is present before the next week's closing balance is frozen.
        with self.ledger.db() as db:
            while self.day(row)<day:
                current=self.day(row)
                boundary=db.execute('SELECT MIN(end) FROM cycles WHERE child=? AND end>?',(row['child'],current.isoformat())).fetchone()[0]
                step=min(day,date.fromisoformat(boundary)) if boundary else day
                self._advance_step(row,step)
            self._advance_step(row,day)

    def _advance_step(self, row, day):
        with self.ledger.db() as db:
            for cycle in db.execute('SELECT * FROM cycles WHERE child=? AND end<=?', (row['child'], day.isoformat())).fetchall():
                for item in self.ledger.reward_items(db, row['child'], dict(cycle), day):
                    db.execute('INSERT OR IGNORE INTO trial_closings VALUES(?,?,?,?,?)',
                               (row['child'], cycle['id'], item['reward_type'], item['base'], item['amount']))
            child = self.ledger._child(db, row['family'], row['child'])
            policy = json.loads(child['policy'])
            if policy.get('dual_rewards'):
                last = db.execute('SELECT end FROM cycles WHERE child=? ORDER BY start DESC LIMIT 1', (row['child'],)).fetchone()
                start = date.fromisoformat(last['end'])
                while start <= day:
                    _, end = period(start, policy)
                    db.execute('INSERT INTO cycles VALUES(?,?,?,?,?,?,0)',
                               (str(uuid.uuid4()), row['child'], start.isoformat(), end.isoformat(), json.dumps(policy), 0))
                    start = end
                for cycle in db.execute('SELECT * FROM cycles WHERE child=? AND end<=?', (row['child'], day.isoformat())).fetchall():
                    for item in self.ledger.reward_items(db, row['child'], dict(cycle), day):
                        db.execute('INSERT OR IGNORE INTO trial_closings VALUES(?,?,?,?,?)',
                                   (row['child'], cycle['id'], item['reward_type'], item['base'], item['amount']))
            db.execute('UPDATE moneyon_demo_workspaces SET business_date=? WHERE family=?', (day.isoformat(), row['family']))
            for cycle in db.execute('SELECT * FROM cycles WHERE child=? AND settled=0 AND end<=? ORDER BY start',(row['child'],day.isoformat())).fetchall():
                if savings.mode(db,row['child'],cycle['start'])=='automatic':
                    for kind in ('allowance_bonus','savings_interest'):
                        if db.execute('SELECT 1 FROM trial_rewards WHERE child=? AND cycle=? AND reward_type=?',(row['child'],cycle['id'],kind)).fetchone(): continue
                        try:
                            self.ledger.settle_rewards(row['family'],row['child'],cycle['id'],'auto:'+cycle['id'],day,kind)
                        except ValueError as error:
                            if '잔액' not in str(error): raise
