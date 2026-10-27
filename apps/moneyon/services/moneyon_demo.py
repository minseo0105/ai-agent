"""Non-destructive, owner-scoped DEMO workspaces and business dates."""
import json
import secrets
import time
import uuid
from datetime import date

from services import moneyon_accounts as accounts


class DemoWorkspaces:
    def __init__(self, ledger):
        self.ledger = ledger

    def resolve(self, owner, demo_id):
        with self.ledger.db() as db:
            row = db.execute('SELECT * FROM moneyon_demo_workspaces WHERE family=? AND owner=? AND active=1', (demo_id, owner)).fetchone()
            if not row:
                raise PermissionError('이 데모 공간에 접근할 수 없어요.')
            return row['family']

    def info(self, family):
        with self.ledger.db() as db:
            row = db.execute('SELECT * FROM moneyon_demo_workspaces WHERE family=? AND active=1', (family,)).fetchone()
            return {'id': row['family'], 'date': row['business_date'], 'is_demo': True} if row else {'id': None, 'date': None, 'is_demo': False}

    def business_date(self, family, actual):
        info = self.info(family)
        return date.fromisoformat(info['date']) if info['is_demo'] else actual

    def create(self, source_family, source_token, actual, reset=False):
        self.ledger.authorize(source_family, source_token, parent=True)
        with self.ledger.db() as db:
            previous = db.execute('SELECT * FROM moneyon_demo_workspaces WHERE family=? AND active=1', (source_family,)).fetchone()
            if reset and not previous:
                raise PermissionError('초기화는 데모 공간에서만 할 수 있어요.')
            owner = previous['owner'] if previous else source_family
            parent = db.execute('SELECT * FROM families WHERE id=?', (source_family,)).fetchone()
            family = 'demo:' + uuid.uuid4().hex
            db.execute('INSERT INTO moneyon_demo_workspaces VALUES(?,?,?,?,?)', (family, owner, actual.isoformat(), 1, accounts.now(db, source_family)))
            db.execute('INSERT INTO families(id,salt,pin) VALUES(?,?,?)', (family, parent['salt'], parent['pin']))
            accounts.ensure_family(db, family)
            for name, grade, theme, avatar, frequency, amount, rate, day in [
                ('재현', 3, 'adventure', '🧑‍🚀', 'weekly', 10000, 1000, actual.weekday()),
                ('서연', 5, 'animals', '🐰', 'monthly', 30000, 500, actual.day),
            ]:
                child = str(uuid.uuid4())
                profile = {'name': name, 'grade': grade, 'theme': theme, 'avatar': avatar}
                policy = {'frequency': frequency, 'amount': amount, 'rate_bps': rate, 'pay_day': day, 'cap': 3000, 'rollover': True}
                db.execute('INSERT INTO children VALUES(?,?,?,?,?)', (child, family, json.dumps(profile), json.dumps(policy), 'active'))
                accounts.ensure_child(db, family, child)
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?,NULL,?)', (token, family, int(time.time()) + 900))
            if previous:
                db.execute('UPDATE moneyon_demo_workspaces SET active=0 WHERE family=?', (source_family,))
                db.execute('DELETE FROM sessions WHERE family=?', (source_family,))
            else:
                db.execute('DELETE FROM sessions WHERE token=?', (source_token,))
            return {'demo_id': family, 'token': token, 'date': actual.isoformat()}

    def advance(self, family, target):
        with self.ledger.db() as db:
            row = db.execute('SELECT * FROM moneyon_demo_workspaces WHERE family=? AND active=1', (family,)).fetchone()
            if not row:
                raise PermissionError('가상 날짜는 데모 공간에서만 바꿀 수 있어요.')
            current = date.fromisoformat(row['business_date'])
            if target < current or (target-current).days > 366:
                raise ValueError('가상 날짜는 현재부터 366일 이내의 미래로만 이동할 수 있어요.')
            db.execute('UPDATE moneyon_demo_workspaces SET business_date=? WHERE family=?', (target.isoformat(), family))
            return {'date': target.isoformat(), 'is_demo': True}
