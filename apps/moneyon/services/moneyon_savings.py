"""Additive savings subledger. Original wallet/vault postings remain authoritative."""
import uuid


def install(db):
    db.execute('''CREATE TABLE IF NOT EXISTS moneyon_books(
        id TEXT PRIMARY KEY, child TEXT NOT NULL, name TEXT NOT NULL,
        target INTEGER NOT NULL, icon TEXT NOT NULL, color TEXT NOT NULL,
        nickname TEXT NOT NULL, request_key TEXT NOT NULL, UNIQUE(child,request_key))''')
    db.execute('''CREATE TABLE IF NOT EXISTS moneyon_book_entries(
        transaction_id TEXT NOT NULL, book TEXT NOT NULL, amount INTEGER NOT NULL,
        PRIMARY KEY(transaction_id,book))''')
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
    return [dict(r) for r in db.execute('''SELECT b.*,COALESCE(SUM(e.amount),0) balance
        FROM moneyon_books b LEFT JOIN moneyon_book_entries e ON e.book=b.id
        WHERE b.child=? GROUP BY b.id ORDER BY b.rowid''', (child,))]


def create(db, child, name, target, icon, color, nickname, key):
    if not name.strip() or len(name)>30 or len(nickname)>20:
        raise ValueError('통장 이름은 1~30자, 별명은 20자까지 입력해 주세요.')
    if type(target) is not int or target<100 or target>10000000 or target%100:
        raise ValueError('목표는 100원 단위로 정해 주세요. 새 통장은 0원부터 시작해요.')
    if icon not in ('🐷','🎮','✈️','🎁','⭐') or color not in ('blue','mint','purple','pink'):
        raise ValueError('통장 꾸미기를 다시 선택해 주세요.')
    old=db.execute('SELECT * FROM moneyon_books WHERE child=? AND request_key=?',(child,key)).fetchone()
    if old:
        if (old['name'],old['target'],old['icon'],old['color'],old['nickname'])!=(name,target,icon,color,nickname):
            raise ValueError('같은 요청 번호의 통장 정보가 달라요.')
        return old['id']
    if len(balances(db,child))>=20: raise ValueError('통장은 20개까지 만들 수 있어요.')
    book=str(uuid.uuid4())
    db.execute('INSERT INTO moneyon_books VALUES(?,?,?,?,?,?,?,?)',(book,child,name,target,icon,color,nickname,key))
    return book


def assign(db, child, transaction, book):
    if not db.execute('SELECT 1 FROM moneyon_books WHERE child=? AND id=?',(child,book)).fetchone():
        raise ValueError('내 저축통장을 선택해 주세요.')
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
