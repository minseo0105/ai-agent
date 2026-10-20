"""Account postings derived from MONEY:ON events, in the same SQLite transaction.

There are no stored mutable balances and no network banking calls. Legacy events
are replayed once against a clearing account, never charged to the new parent.
"""
import uuid
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
TYPES = {'payment': 'ALLOWANCE_TRANSFER', 'expense': 'MANUAL_EXPENSE',
         'allowance_bonus': 'ALLOWANCE_SAVING_BONUS', 'savings_interest': 'PIGGY_BANK_INTEREST',
         'interest': 'PARENT_REWARD_INTEREST', 'deposit': 'SAVINGS_DEPOSIT',
         'withdraw': 'SAVINGS_WITHDRAWAL', 'expense_cancel': 'PURCHASE_REVERSAL',
         'expiry': 'ALLOWANCE_RETURN'}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS bank_accounts(
 id TEXT PRIMARY KEY, family TEXT NOT NULL, child TEXT, kind TEXT NOT NULL,
 scope TEXT NOT NULL, alias TEXT NOT NULL, UNIQUE(family,scope));
CREATE TABLE IF NOT EXISTS bank_events(
 id TEXT PRIMARY KEY, source_transaction TEXT UNIQUE, family TEXT NOT NULL,
 child TEXT, transaction_type TEXT NOT NULL, merchant TEXT NOT NULL DEFAULT '',
 occurred_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'POSTED', legacy INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS bank_postings(
 id TEXT PRIMARY KEY, transfer_id TEXT NOT NULL REFERENCES bank_events(id),
 account_id TEXT NOT NULL REFERENCES bank_accounts(id), amount INTEGER NOT NULL,
 balance_after INTEGER NOT NULL, UNIQUE(transfer_id,account_id));
CREATE INDEX IF NOT EXISTS bank_postings_account ON bank_postings(account_id);
CREATE TABLE IF NOT EXISTS bank_category_changes(
 id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id TEXT NOT NULL,
 family TEXT NOT NULL, child TEXT NOT NULL, category TEXT NOT NULL, occurred_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS moneyon_demo_workspaces(
 family TEXT PRIMARY KEY, owner TEXT NOT NULL, business_date TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS moneyon_demo_owner ON moneyon_demo_workspaces(owner,active);
'''


def now(db, family):
    stamp = datetime.now(KST)
    row = db.execute('SELECT business_date FROM moneyon_demo_workspaces WHERE family=? AND active=1', (family,)).fetchone()
    return stamp.replace(year=int(row[0][:4]), month=int(row[0][5:7]), day=int(row[0][8:10])).isoformat() if row else stamp.isoformat()


def balance(db, account_id):
    return db.execute('SELECT COALESCE(SUM(amount),0) FROM bank_postings WHERE account_id=?', (account_id,)).fetchone()[0]


def _account(db, family, kind, child=None):
    scope = kind + (':' + child if child else '')
    row = db.execute('SELECT * FROM bank_accounts WHERE family=? AND scope=?', (family, scope)).fetchone()
    if row:
        return row['id']
    account_id = 'DEMO-' + {'parent': 'P', 'wallet': 'C', 'vault': 'S', 'clearing': 'X'}[kind] + '-' + uuid.uuid4().hex[:16].upper()
    alias = {'parent': '부모 용돈 통장', 'wallet': '나의 용돈 통장', 'vault': '나의 저축금고', 'clearing': '가상 결제·이관 조정'}[kind]
    db.execute('INSERT INTO bank_accounts VALUES(?,?,?,?,?,?)', (account_id, family, child, kind, scope, alias))
    return account_id


def _post(db, event, account_id, amount):
    after = balance(db, account_id) + amount
    kind = db.execute('SELECT kind FROM bank_accounts WHERE id=?', (account_id,)).fetchone()[0]
    if kind != 'clearing' and after < 0:
        raise ValueError('부모 가상 계좌 잔액이 부족해요.' if kind == 'parent' else '가상 계좌 잔액이 부족해요.')
    db.execute('INSERT INTO bank_postings VALUES(?,?,?,?,?)', (str(uuid.uuid4()), event, account_id, amount, after))


def ensure_family(db, family):
    existing = db.execute("SELECT id FROM bank_accounts WHERE family=? AND kind='parent'", (family,)).fetchone()
    if existing:
        return existing[0]
    parent = _account(db, family, 'parent')
    clearing = _account(db, family, 'clearing')
    event = 'DEMO-TX-' + uuid.uuid4().hex
    db.execute('INSERT INTO bank_events(id,family,transaction_type,occurred_at) VALUES(?,?,?,?)', (event, family, 'DEMO_INITIAL_FUNDING', now(db, family)))
    _post(db, event, parent, 500000)
    _post(db, event, clearing, -500000)
    return parent


def ensure_child(db, family, child):
    ensure_family(db, family)
    return _account(db, family, 'wallet', child), _account(db, family, 'vault', child)


def record(db, transaction, legacy=False, metadata=None):
    t = transaction
    if not t['wallet'] and not t['vault'] and t['kind'] not in ('interest', 'allowance_bonus', 'savings_interest'):
        return
    if db.execute('SELECT 1 FROM bank_events WHERE source_transaction=?', (t['id'],)).fetchone():
        return
    family = db.execute('SELECT family FROM children WHERE id=?', (t['child'],)).fetchone()[0]
    wallet, vault = ensure_child(db, family, t['child'])
    parent = ensure_family(db, family)
    clearing = _account(db, family, 'clearing')
    event = 'DEMO-TX-' + t['id']
    metadata = metadata or {}
    transaction_type = 'SIMULATED_PURCHASE' if metadata.get('merchant') else TYPES[t['kind']]
    db.execute('INSERT INTO bank_events VALUES(?,?,?,?,?,?,?,?,?)', (event, t['id'], family, t['child'], transaction_type, metadata.get('merchant', ''), t['created'], 'POSTED', int(legacy)))
    # Parent funding only applies to new transfers. Historical events use clearing.
    parent_delta = -(t['wallet'] + t['vault']) if not legacy and t['kind'] in ('payment', 'interest', 'expiry', 'allowance_bonus', 'savings_interest') else 0
    if t['wallet'] or t['kind'] == 'interest':
        _post(db, event, wallet, t['wallet'])
    if t['vault']:
        _post(db, event, vault, t['vault'])
    if parent_delta or (not legacy and t['kind'] == 'interest'):
        _post(db, event, parent, parent_delta)
    offset = -(t['wallet'] + t['vault'] + parent_delta)
    if offset:
        _post(db, event, clearing, offset)
    if db.execute('SELECT COALESCE(SUM(amount),0) FROM bank_postings WHERE transfer_id=?', (event,)).fetchone()[0] != 0:
        raise ValueError('가상 이체의 입출금 금액이 일치하지 않아요.')


def migrate(db):
    if db.execute('SELECT 1 FROM moneyon_schema WHERE version=2').fetchone():
        return
    for row in db.execute('SELECT id AS family FROM families UNION SELECT family FROM children').fetchall():
        ensure_family(db, row['family'])
    for child in db.execute('SELECT id,family FROM children').fetchall():
        ensure_child(db, child['family'], child['id'])
    for row in db.execute("SELECT t.* FROM transactions t LEFT JOIN bank_events b ON b.source_transaction=t.id WHERE b.id IS NULL AND (t.wallet!=0 OR t.vault!=0 OR t.kind='interest') ORDER BY t.rowid").fetchall():
        record(db, row, legacy=True)
    db.execute('INSERT OR IGNORE INTO moneyon_schema VALUES(2)')


def child_balance(db, child):
    rows = db.execute("SELECT a.kind,COALESCE(SUM(p.amount),0) amount FROM bank_accounts a LEFT JOIN bank_postings p ON p.account_id=a.id WHERE a.child=? GROUP BY a.id", (child,)).fetchall()
    return {'wallet': next((r['amount'] for r in rows if r['kind'] == 'wallet'), 0),
            'vault': next((r['amount'] for r in rows if r['kind'] == 'vault'), 0)}


def categories(db, child):
    return {r['transaction_id']: r['category'] for r in db.execute('SELECT transaction_id,category FROM bank_category_changes WHERE child=? ORDER BY id', (child,))}


def accounts(db, family, child=None):
    ensure_family(db, family)
    query = "SELECT * FROM bank_accounts WHERE family=? AND kind!='clearing'"
    args = [family]
    if child:
        query += ' AND child=?'
        args.append(child)
    return [dict(r) | {'balance': balance(db, r['id']), 'notice': '가상 계좌 · 실제 금융 거래 아님'} for r in db.execute(query + ' ORDER BY rowid', args)]


def transactions(db, family, account_id, child=None):
    account = db.execute('SELECT * FROM bank_accounts WHERE id=? AND family=?', (account_id, family)).fetchone()
    if not account or account['kind'] == 'clearing' or (child and account['child'] != child):
        raise PermissionError('이 가상 계좌를 조회할 수 없어요.')
    rows = db.execute('''SELECT p.rowid seq,p.account_id,p.amount,p.balance_after,e.id transfer_id,
      COALESCE(e.source_transaction,e.id) transaction_id,e.child child_id,e.transaction_type,e.occurred_at,
      e.merchant,e.status,e.legacy,COALESCE(t.category,'') category,COALESCE(t.note,'') note,COALESCE(t.request_key,'') request_key
      FROM bank_postings p JOIN bank_events e ON e.id=p.transfer_id
      LEFT JOIN transactions t ON t.id=e.source_transaction
      WHERE p.account_id=? ORDER BY p.rowid DESC''', (account_id,)).fetchall()
    changed = {r['transaction_id']: r['category'] for r in db.execute('SELECT transaction_id,category FROM bank_category_changes WHERE family=? ORDER BY id', (family,))}
    result = []
    for row in rows:
        item = dict(row) | {'category': changed.get(row['transaction_id'], row['category'])}
        if row['transaction_type'] == 'PURCHASE_REVERSAL':
            original_id = row['request_key'].removeprefix('cancel:')
            original = db.execute('SELECT category FROM transactions WHERE id=? AND child=?', (original_id, row['child_id'])).fetchone()
            item['category'] = changed.get(original_id, original['category'] if original else '')
        result.append(item)
    return result
