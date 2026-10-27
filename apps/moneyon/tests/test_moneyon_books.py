r"""MONEY:ON 저축통장 엄마 승인 흐름 테스트(오프라인, 비용 0). 실행: apps/moneyon에서
   ..\..\..\..\.venv\Scripts\python.exe -B -m unittest tests.test_moneyon_books -v
"""
import os
import shutil
import sqlite3
import tempfile
import unittest

from tests.test_moneyon_ai import Base  # 환경(체험 모드 켜기)과 앱 로딩은 AI 테스트 모듈과 같다

P = '/api/moneyon/trial'
KEYS = ('MONEYON_TRIAL_DB', 'MONEYON_DB', 'MONEYON_AI_USAGE')
TMP = tempfile.mkdtemp()
_saved = {}


# AI 테스트 모듈은 끝날 때 자기 임시 폴더를 지운다. 이 모듈은 자기 DB를 쓰고, 끝나면 환경변수를 되돌린다.
def setUpModule():
    _saved.update({k: os.environ.get(k) for k in KEYS})
    os.environ.update(MONEYON_TRIAL_DB=f'{TMP}/trial.sqlite3', MONEYON_DB=f'{TMP}/dev.sqlite3', MONEYON_AI_USAGE=f'{TMP}/ai_usage.json')


def tearDownModule():
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    shutil.rmtree(TMP, ignore_errors=True)


class BooksTest(Base):
    def open(self, demo=True):
        snap = self.start(demo)
        return snap['token'], snap['child']['id'], snap['generation']

    def call(self, method, path, token, generation, body=None):
        return self.client.request(method, P + path, json=body, headers={'X-Moneyon-Trial': token, 'X-Moneyon-Trial-Version': str(generation)})

    def make_book(self, token, child, generation, key='book-key-0001', **over):
        body = {'name': '장난감', 'target': 30000, 'icon': '🧸', 'color': 'blue', 'nickname': '', 'key': key, **over}
        return self.call('POST', f'/children/{child}/books', token, generation, body)

    def find(self, state, name):
        return next(b for b in state['books'] if b['name'] == name)

    def deposit(self, token, child, generation, book, key='dep-key-00001'):
        return self.call('POST', f'/children/{child}/transactions', token, generation, {'kind': 'deposit', 'amount': 1000, 'book_id': book, 'key': key})

    def test_new_book_waits_for_approval(self):
        token, child, gen = self.open()
        r = self.make_book(token, child, gen)
        self.assertEqual(r.status_code, 200, r.text)
        book = self.find(r.json(), '장난감')
        self.assertEqual(book['status'], 'pending')
        self.assertIsInstance(book['waited'], int)
        self.assertEqual(book['balance'], 0)
        default = next(b for b in r.json()['books'] if b['id'].startswith('default:'))
        self.assertEqual(default['status'], 'approved')  # 승인 기능 이전 통장·기본 통장은 그대로 쓸 수 있다
        self.assertIsNone(default['waited'])

    def test_pending_book_blocks_deposit_and_coach(self):
        token, child, gen = self.open()
        book = self.find(self.make_book(token, child, gen).json(), '장난감')
        r = self.deposit(token, child, gen, book['id'])
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn('승인', r.json()['detail'])
        r, _ = self.ask(token, 'coach', {'book_id': book['id'], 'weekly': 1000})
        self.assertEqual(r.status_code, 400, r.text)

    def test_approve_activates_and_is_idempotent(self):
        token, child, gen = self.open()
        book = self.find(self.make_book(token, child, gen).json(), '장난감')
        for _ in range(2):
            r = self.call('POST', f'/children/{child}/books/{book["id"]}/approve', token, gen, {})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(self.find(r.json(), '장난감')['status'], 'approved')
        self.assertIsNone(self.find(r.json(), '장난감')['waited'])
        r = self.deposit(token, child, gen, book['id'])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.find(r.json(), '장난감')['balance'], 1000)

    def test_other_trial_cannot_approve(self):
        token, child, gen = self.open()
        book = self.find(self.make_book(token, child, gen).json(), '장난감')
        other, _, other_gen = self.open()
        r = self.call('POST', f'/children/{child}/books/{book["id"]}/approve', other, other_gen, {})
        self.assertEqual(r.status_code, 403, r.text)
        state = self.call('GET', f'/children/{child}', token, gen).json()
        self.assertEqual(self.find(state, '장난감')['status'], 'pending')

    def test_unknown_book_is_rejected(self):
        token, child, gen = self.open()
        r = self.call('POST', f'/children/{child}/books/no-such-book/approve', token, gen, {})
        self.assertEqual(r.status_code, 409, r.text)

    def test_goal_icons(self):
        token, child, gen = self.open()
        for i, icon in enumerate(('🚲', '📚', '🎂', '💝')):
            self.assertEqual(self.make_book(token, child, gen, key=f'icon-key-{i:04d}', name=f'목표{i}', icon=icon).status_code, 200)
        self.assertEqual(self.make_book(token, child, gen, key='icon-key-bad1', name='나쁜것', icon='💣').status_code, 409)

    def test_pending_book_does_not_break_weekly_settlement(self):
        token, child, gen = self.open()
        self.make_book(token, child, gen)
        snap = self.client.get(P + '/state', headers={'X-Moneyon-Trial': token}).json()
        # 일주일 뒤로: 저축 이자 배분·잔액 합계 검증이 승인 대기 통장(잔액 0)을 포함해도 통과해야 한다.
        import datetime
        nxt = (datetime.date.fromisoformat(snap['day']) + datetime.timedelta(days=7)).isoformat()
        r = self.call('POST', f'/children/{child}/date', token, snap['generation'], {'day': nxt})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.find(r.json()['state'], '장난감')['status'], 'pending')

    def test_reset_starts_without_the_pending_book(self):
        token, child, gen = self.open()
        book = self.find(self.make_book(token, child, gen).json(), '장난감')
        db = sqlite3.connect(f'{TMP}/trial.sqlite3')
        try:
            count = lambda: db.execute('SELECT COUNT(*) FROM moneyon_book_approvals WHERE book=?', (book['id'],)).fetchone()[0]
            self.assertEqual(count(), 1)
            r = self.call('POST', '/reset', token, gen, {'key': 'reset-key-0001'})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(count(), 1)  # 초기화는 새 작업공간으로 옮기고 옛 것은 보관한다. 새 상태에는 이 통장이 없다.
            self.assertNotIn('장난감', [b['name'] for b in r.json()['state']['books']])
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
