"""Additive savings subledger. Original wallet/vault postings remain authoritative."""
import time
import uuid

# 새 저축통장 꾸미기 아이콘(아이 눈높이 목표: 장난감·탈것·책·생일 선물·친구 선물). 앞의 5개는 예전 통장 때문에 유지.
ICONS = ('🐷', '🎮', '✈️', '🎁', '⭐', '🧸', '🚲', '📚', '🎂', '💝')


def install(db):
    db.execute('''CREATE TABLE IF NOT EXISTS moneyon_books(
        id TEXT PRIMARY KEY, child TEXT NOT NULL, name TEXT NOT NULL,
        target INTEGER NOT NULL, icon TEXT NOT NULL, color TEXT NOT NULL,
        nickname TEXT NOT NULL, request_key TEXT NOT NULL, UNIQUE(child,request_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS moneyon_book_entries(
        transaction_id TEXT NOT NULL, book TEXT NOT NULL, amount INTEGER NOT NULL,
        PRIMARY KEY(transaction_id,book))''')
    # 엄마 승인 상태. 행이 없는 통장(승인 기능 이전에 만든 것, 기본 통장)은 '승인됨'으로 본다.
    db.execute('''CREATE TABLE IF NOT EXISTS moneyon_book_approvals(
        book TEXT PRIMARY KEY, child TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','approved')),
        requested_at INTEGER NOT NULL, approved_at INTEGER)''')
    db.execute('''CREATE TABLE IF NOT EXISTS moneyon_reward_choices(
        payout TEXT PRIMARY KEY, child TEXT NOT NULL, choice TEXT NOT NULL,
        amount INTEGER NOT NULL, book TEXT, transaction_id TEXT, request_key TEXT NOT NULL,
        UNIQUE(child,request_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS moneyon_payment_rules(
        child TEXT NOT NULL, effective TEXT NOT NULL, mode TEXT NOT NULL,
        PRIMARY KEY(child,effective))''')


def migrate(db, child):
    default = 'default:' + child
    goal = db.execute('SELECT name,amount FROM goals WHERE child=? ORDER BY rowid LIMIT 1', (child,)).fetchone()
    db.execute('INSERT OR IGNORE INTO moneyon_books VALUES(?,?,?,?,?,?,?,?)',
               (default, child, '기본 저축통장', goal['amount'] if goal else 30000, '🐷', 'blue', '', 'migration'))
    # Each historical vault posting is connected exactly once, with its ID intact.
    db.execute('''INSERT INTO moneyon_book_entries SELECT t.id,?,t.vault FROM transactions t
        WHERE t.child=? AND t.vault!=0 AND NOT EXISTS
        (SELECT 1 FROM moneyon_book_entries b WHERE b.transaction_id=t.id)''', (default, child))
    return default


def balances(db, child):
    migrate(db, child)
    now = int(time.time())
    return [dict(r) for r in db.execute('''SELECT b.*,COALESCE(SUM(e.amount),0) balance,
        COALESCE(a.status,'approved') status,
        CASE WHEN a.status='pending' THEN MAX(0,?-a.requested_at) END waited
        FROM moneyon_books b LEFT JOIN moneyon_book_entries e ON e.book=b.id
        LEFT JOIN moneyon_book_approvals a ON a.book=b.id
        WHERE b.child=? GROUP BY b.id ORDER BY b.rowid''', (now, child))]


def create(db, child, name, target, icon, color, nickname, key, approval=False):
    if not name.strip() or len(name)>30 or len(nickname)>20:
        raise ValueError('통장 이름은 1~30자, 별명은 20자까지 입력해 주세요.')
    if type(target) is not int or target<100 or target>10000000 or target%100:
        raise ValueError('목표는 100원 단위로 정해 주세요. 새 통장은 0원부터 시작해요.')
    if icon not in ICONS or color not in ('blue','mint','purple','pink'):
        raise ValueError('통장 꾸미기를 다시 선택해 주세요.')
    old=db.execute('SELECT * FROM moneyon_books WHERE child=? AND request_key=?',(child,key)).fetchone()
    if old:
        if (old['name'],old['target'],old['icon'],old['color'],old['nickname'])!=(name,target,icon,color,nickname):
            raise ValueError('같은 요청 번호의 통장 정보가 달라요.')
        return old['id']
    if len(balances(db,child))>=20: raise ValueError('통장은 20개까지 만들 수 있어요.')
    book=str(uuid.uuid4())
    db.execute('INSERT INTO moneyon_books VALUES(?,?,?,?,?,?,?,?)',(book,child,name,target,icon,color,nickname,key))
    if approval:
        db.execute("INSERT INTO moneyon_book_approvals VALUES(?,?,'pending',?,NULL)",(book,child,int(time.time())))
    return book


def is_pending(db, child, book):
    return bool(db.execute("SELECT 1 FROM moneyon_book_approvals WHERE child=? AND book=? AND status='pending'",(child,book)).fetchone())


def approve(db, child, book):
    """엄마 승인. 이미 승인됐거나 승인 대상이 아닌 통장은 그대로 두고 성공으로 본다(두 번 눌러도 안전)."""
    if not db.execute('SELECT 1 FROM moneyon_books WHERE child=? AND id=?',(child,book)).fetchone():
        raise ValueError('저축통장을 찾을 수 없어요.')
    db.execute("UPDATE moneyon_book_approvals SET status='approved',approved_at=? WHERE child=? AND book=? AND status='pending'",
               (int(time.time()),child,book))


def assign(db, child, transaction, book):
    if not db.execute('SELECT 1 FROM moneyon_books WHERE child=? AND id=?',(child,book)).fetchone():
        raise ValueError('내 저축통장을 선택해 주세요.')
    if is_pending(db,child,book):
        raise ValueError('엄마가 승인하면 이 통장을 쓸 수 있어요.')
    tx=db.execute('SELECT vault FROM transactions WHERE child=? AND id=?',(child,transaction)).fetchone()
    existing=db.execute('SELECT * FROM moneyon_book_entries WHERE transaction_id=?',(transaction,)).fetchall()
    if existing and any(e['book']!=book for e in existing):
        raise ValueError('이미 다른 통장에 기록한 거래예요.')
    db.execute('INSERT OR IGNORE INTO moneyon_book_entries VALUES(?,?,?)',(transaction,book,tx['vault']))


def mode(db, child, cycle_start):
    row=db.execute('SELECT mode FROM moneyon_payment_rules WHERE child=? AND effective<=? ORDER BY effective DESC LIMIT 1',(child,cycle_start)).fetchone()
    return row['mode'] if row else 'manual'


def payout_available(db, child, payout):
    tx=db.execute("SELECT rowid,* FROM transactions WHERE id=? AND child=? AND kind='allowance_bonus'",(payout,child)).fetchone()
    if not tx: raise ValueError('실제로 받은 용돈 이자를 선택해 주세요.')
    # Conservative attribution: all later wallet debits consume this payout first.
    # New allowance never restores an already spent payout's saving entitlement.
    debits=db.execute('SELECT COALESCE(SUM(-wallet),0) FROM transactions WHERE child=? AND rowid>? AND wallet<0',(child,tx['rowid'])).fetchone()[0]
    return max(0,tx['wallet']-debits)
