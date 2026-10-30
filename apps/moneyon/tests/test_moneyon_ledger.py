r"""MONEY:ON 잔액 초과 거절과 장부 맞추기 테스트(오프라인, 비용 0). 실행: apps/moneyon에서
   ..\..\..\.venv\Scripts\python.exe -B -m unittest tests.test_moneyon_ledger -v
"""
import os
import shutil
import sqlite3
import tempfile
import threading
import unittest

from fastapi.testclient import TestClient

from services import moneyon_audit as audit
from services import moneyon_trial
from tests.test_moneyon_ai import Base  # 환경(체험 모드 켜기)과 앱 로딩은 AI 테스트 모듈과 같다

P = '/api/moneyon/trial'
KEYS = ('MONEYON_TRIAL_DB', 'MONEYON_DB', 'MONEYON_AI_USAGE')
TMP = tempfile.mkdtemp()
_saved = {}


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


class LedgerTest(Base):
    def open(self, demo=True):
        snap = self.start(demo)
        self.token, self.child, self.gen = snap['token'], snap['child']['id'], snap['generation']
        return snap['state']

    def headers(self):
        return {'X-Moneyon-Trial': self.token, 'X-Moneyon-Trial-Version': str(self.gen)}

    def tx(self, kind, amount, key, book=None, client=None):
        body = {'kind': kind, 'amount': amount, 'key': key}
        if kind == 'expense':
            body['category'] = '간식'
        if book:
            body['book_id'] = book
        return (client or self.client).post(f'{P}/children/{self.child}/transactions', json=body, headers=self.headers())

    def state(self):
        r = self.client.get(f'{P}/children/{self.child}', headers=self.headers())
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def allowance(self, amount, key):
        r = self.client.post(f'{P}/children/{self.child}/allowance', json={'amount': amount, 'key': key}, headers=self.headers())
        self.assertEqual(r.status_code, 200, r.text)

    def audit_db(self):
        return audit.audit_database(os.environ['MONEYON_TRIAL_DB'])

    # ---- 잔액 초과 거절 ----
    def test_over_balance_is_rejected_for_every_kind(self):
        state = self.open()
        wallet, book = state['wallet'], state['books'][0]
        for n, (kind, amount, message) in enumerate((
                ('expense', wallet + 100, f'남은 용돈은 {wallet:,}원이에요'),
                ('deposit', wallet + 100, f'남은 용돈은 {wallet:,}원이에요'),
                ('withdraw', book['balance'] + 100, f"{book['balance']:,}원이 있어요"))):
            r = self.tx(kind, amount, f'over-key-{n:05d}', book['id'] if kind != 'expense' else None)
            self.assertEqual(r.status_code, 409, (kind, r.text))
            self.assertIn(message, r.json()['detail'])
        after = self.state()
        self.assertEqual((after['wallet'], after['vault']), (state['wallet'], state['vault']))

    def test_zero_balance_rejects_any_spend(self):
        state = self.open()
        self.assertEqual(self.tx('expense', state['wallet'], 'zero-key-00001').status_code, 200)
        self.assertEqual(self.state()['wallet'], 0)
        for n, kind in enumerate(('expense', 'deposit')):
            r = self.tx(kind, 100, f'zero-key-1000{n}', state['books'][0]['id'])
            self.assertEqual(r.status_code, 409, r.text)
            self.assertIn('남은 용돈은 0원이에요', r.json()['detail'])
        self.assertEqual(self.state()['wallet'], 0)

    def test_exact_balance_is_allowed_and_never_negative(self):
        state = self.open()
        self.assertEqual(self.tx('deposit', state['wallet'], 'exact-key-0001', state['books'][0]['id']).status_code, 200)
        self.assertEqual(self.state()['wallet'], 0)

    def test_direct_input_garbage_is_rejected(self):
        state = self.open()
        for n, amount in enumerate((0, -100, 150, 100.5, '3000', None, 10 ** 12)):
            r = self.tx('expense', amount, f'bad-key-{n:05d}')
            self.assertIn(r.status_code, (409, 422), (amount, r.text))
        self.assertEqual(self.state()['wallet'], state['wallet'])

    def test_same_key_retry_does_not_spend_twice(self):
        state = self.open()
        for _ in range(3):
            self.assertEqual(self.tx('expense', 1000, 'retry-key-0001').status_code, 200)
        self.assertEqual(self.state()['wallet'], state['wallet'] - 1000)

    def test_two_concurrent_requests_cannot_overdraw(self):
        state = self.open()
        half = (state['wallet'] // 200 + 1) * 100  # 하나씩은 되지만 둘이면 넘는 금액
        self.assertLessEqual(half, state['wallet'])
        self.assertGreater(half * 2, state['wallet'])
        codes, gate = [], threading.Barrier(2)

        def go(i):
            client = TestClient(self.client.app)
            gate.wait()
            codes.append(self.tx('expense', half, f'conc-key-{i:05d}', client=client).status_code)

        threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sorted(codes), [200, 409])
        self.assertEqual(self.state()['wallet'], state['wallet'] - half)
        self.assertEqual(self.audit_db()['mismatched'], 0)

    def test_ledger_guard_rolls_back_a_negative_result(self):
        # 저장소 수준 검사: 금액이 잔액을 넘으면 장부에 아무것도 남기지 않는다.
        state = self.open()
        trial = moneyon_trial.TrialLedger(os.environ['MONEYON_TRIAL_DB'])
        with trial.db() as db:
            family = db.execute('SELECT family FROM children WHERE id=?', (self.child,)).fetchone()[0]
        with self.assertRaises(ValueError):
            trial.transact(family, self.child, 'expense', 'guard-key-0001', state['wallet'] + 100, '간식', '간식')
        self.assertEqual(self.state()['wallet'], state['wallet'])
        self.assertEqual(self.audit_db()['mismatched'], 0)

    # ---- 장부 맞추기 ----
    def test_fresh_demo_workspace_is_balanced(self):
        self.open()
        report = self.audit_db()
        self.assertEqual((report['mismatched'], report['negative'], report['unreadable']), (0, 0, 0), report['problems'])

    def test_full_flow_matches_server_ledger(self):
        state = self.open()
        book = state['books'][0]['id']
        self.allowance(10000, 'ledger-allow-01')
        self.assertEqual(self.tx('expense', 2000, 'ledger-spend-01').status_code, 200)
        self.assertEqual(self.tx('deposit', 3000, 'ledger-save-001', book).status_code, 200)
        self.assertEqual(self.tx('withdraw', 1000, 'ledger-take-001', book).status_code, 200)
        s = self.state()
        self.assertEqual(s['wallet'], state['wallet'] + 10000 - 2000 - 3000 + 1000)
        self.assertEqual(s['vault'], state['vault'] + 3000 - 1000)
        # 화면이 쓰는 숫자 = 서버 장부
        by_account = {a['kind']: a['balance'] for a in s['banking']['accounts'] if a['kind'] in ('wallet', 'vault')}
        self.assertEqual(by_account, {'wallet': s['wallet'], 'vault': s['vault']})
        self.assertEqual(sum(b['balance'] for b in s['books']), s['vault'])
        self.assertEqual(sum(t['wallet'] for t in s['transactions']), s['wallet'])
        self.assertEqual(sum(t['vault'] for t in s['transactions']), s['vault'])
        if s.get('education'):
            e = s['education']
            self.assertEqual(e['remaining'], s['wallet'])
            self.assertEqual(e['opening'] + e['received'] + e['interest_received'] + e['other_in'] + e['withdrawn'] - e['spent'] - e['saved'] - e['other_out'], s['wallet'])
        # 기록 목록: 최신이 맨 위, 금액은 거래와 같다
        seqs = [t['seq'] for t in s['banking']['transactions']]
        self.assertEqual(seqs, sorted(seqs, reverse=True))
        self.assertEqual(s['transactions'][0]['request_key'], 'ledger-take-001')
        spend = next(t for t in s['transactions'] if t['request_key'] == 'ledger-spend-01')
        self.assertEqual(spend['wallet'], -2000)
        wallet_id = next(a['id'] for a in s['banking']['accounts'] if a['kind'] == 'wallet')
        self.assertEqual(sum(t['amount'] for t in s['banking']['transactions'] if t['account_id'] == wallet_id), s['wallet'])
        self.assertEqual(self.audit_db()['mismatched'], 0)

    def test_audit_reports_a_tampered_ledger(self):
        self.open()
        path = os.environ['MONEYON_TRIAL_DB']
        db = sqlite3.connect(path)
        try:
            row = db.execute("SELECT p.id FROM bank_postings p JOIN bank_accounts a ON a.id=p.account_id WHERE a.kind='wallet' LIMIT 1").fetchone()
            db.execute('UPDATE bank_postings SET amount=amount+700 WHERE id=?', (row[0],))
            db.commit()
            self.assertGreaterEqual(self.audit_db()['mismatched'], 1)
            db.execute('UPDATE bank_postings SET amount=amount-700 WHERE id=?', (row[0],))  # 되돌려서 다른 테스트에 영향이 없게
            db.commit()
        finally:
            db.close()
        self.assertEqual(self.audit_db()['mismatched'], 0)


if __name__ == '__main__':
    unittest.main()
