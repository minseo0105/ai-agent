"""Trial rules: interest in whole 100원, weekly settlement waits for the child's "이자 받기"."""
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.moneyon_trial as api
from services.moneyon import reward
from services.moneyon_trial import LEGACY_POOLS, POOL, TrialLedger, Trials, split


class ClaimRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = TrialLedger(os.path.join(self.tmp.name, 'trial.db'))
        self.trials = Trials(self.ledger)
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[api.trials] = lambda: self.trials
        self.client = TestClient(app)
        self.first = self.client.post('/api/moneyon/trial/start').json()

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def headers(self, trial=None):
        trial = trial or self.first
        return {'X-Moneyon-Trial': trial['token'], 'X-Moneyon-Trial-Version': str(trial['generation'])}

    def post(self, path, body, trial=None):
        trial = trial or self.first
        return self.client.post(f"/api/moneyon/trial/children/{trial['child']['id']}/{path}", json=body, headers=self.headers(trial))

    def state(self, trial=None):
        return self.client.get('/api/moneyon/trial/state', headers=self.headers(trial)).json()

    def interest_rows(self, state):
        return [t for t in state['state']['transactions'] if t['kind'] in ('allowance_bonus', 'savings_interest')]

    def test_reward_drops_amounts_under_100_only_with_a_unit(self):
        allowance, savings = {'rate_bps': 1000, 'cap': None, 'unit': 100}, {'rate_bps': 200, 'cap': 2000, 'unit': 100}
        self.assertEqual(reward(28500, allowance), 2800)
        self.assertEqual(reward(9990, allowance), 900)
        self.assertEqual(reward(999, allowance), 0)
        self.assertEqual(reward(1000, allowance), 100)
        self.assertEqual(reward(4900, savings), 0)
        self.assertEqual(reward(5000, savings), 100)
        self.assertEqual(reward(18000, savings), 300)
        self.assertEqual(reward(500000, savings), 2000)
        # Family and earlier trial policies have no unit: every won still counts.
        self.assertEqual(reward(28500, {'rate_bps': 1000, 'cap': None}), 2850)
        self.assertEqual(reward(14250, {'rate_bps': 1000, 'cap': 1500}), 1425)

    def test_split_keeps_whole_units_and_the_total(self):
        self.assertEqual(split(300, [15000, 3000], 100, ['a', 'b']), [300, 0])
        self.assertEqual(split(300, [10000, 10000, 10000], 100, ['a', 'b', 'c']), [100, 100, 100])
        self.assertEqual(split(400, [10000, 10000, 10000], 100, ['a', 'b', 'c']), [200, 100, 100])
        self.assertEqual(split(7, [1, 1], 1, ['a', 'b']), [4, 3])
        self.assertEqual(split(300, [0, 0], 100), [0, 0])

    def test_new_trial_estimates_in_100s_and_waits_for_claim(self):
        state = self.first['state']
        self.assertEqual(state['wallet'], 28500)
        self.assertEqual(state['rewards']['estimates'], {'allowance_bonus': 2800, 'savings_interest': 300})
        self.assertEqual(state['payment_rule']['current'], 'manual')
        before = self.interest_rows(self.first)
        moved = self.post('date', {'day': '2026-10-19'}).json()
        # Week closed: settlement shows what is waiting, nothing enters the ledger yet.
        self.assertEqual(self.interest_rows(moved), before)
        self.assertEqual((moved['state']['wallet'], moved['state']['vault']), (28500, 15000))
        waiting = [i for i in moved['state']['rewards']['items'] if i['status'] == 'awaiting_approval']
        self.assertEqual(sorted((i['reward_type'], i['amount']) for i in waiting), [('allowance_bonus', 2800), ('savings_interest', 300)])
        claimed = self.post('claim', {'key': 'claim-week-1'})
        self.assertEqual(claimed.status_code, 200)
        after = claimed.json()['state']
        self.assertEqual((after['wallet'], after['vault']), (31300, 15300))
        self.assertEqual(sum(b['balance'] for b in after['books']), after['vault'])
        self.assertFalse([i for i in after['rewards']['items'] if i['status'] == 'awaiting_approval'])

    def test_claim_twice_or_with_new_key_pays_once(self):
        self.post('date', {'day': '2026-10-19'})
        first = self.post('claim', {'key': 'claim-once-1'}).json()['state']
        again = self.post('claim', {'key': 'claim-once-1'}).json()['state']
        other = self.post('claim', {'key': 'claim-once-2'}).json()['state']
        for state in (again, other):
            self.assertEqual((state['wallet'], state['vault']), (first['wallet'], first['vault']))
        self.assertEqual(len([t for t in other['transactions'] if t['kind'] in ('allowance_bonus', 'savings_interest')]),
                         len([t for t in first['transactions'] if t['kind'] in ('allowance_bonus', 'savings_interest')]))

    def test_concurrent_claims_pay_once(self):
        self.post('date', {'day': '2026-10-19'})
        with ThreadPoolExecutor(6) as pool:
            codes = list(pool.map(lambda n: self.post('claim', {'key': f'claim-race-{n % 2}'}).status_code, range(6)))
        self.assertEqual(codes, [200] * 6)
        state = self.state()['state']
        self.assertEqual((state['wallet'], state['vault']), (31300, 15300))

    def test_month_of_waiting_weeks_claimed_together_in_100s(self):
        self.post('date', {'day': '2026-11-09'})  # 한 달 뒤 보기 = 28일
        moved = self.state()['state']
        waiting = [i for i in moved['rewards']['items'] if i['status'] == 'awaiting_approval']
        self.assertEqual(len({i['cycle_id'] for i in waiting}), 4)
        self.assertTrue(all(i['amount'] % 100 == 0 for i in waiting))
        total = sum(i['amount'] for i in waiting)
        after = self.post('claim', {'key': 'claim-month-1'}).json()['state']
        self.assertEqual(after['wallet'] + after['vault'], moved['wallet'] + moved['vault'] + total)
        paid = [t for t in after['transactions'] if t['kind'] in ('allowance_bonus', 'savings_interest')]
        self.assertTrue(all((t['wallet'] + t['vault']) % 100 == 0 for t in paid))

    def test_savings_interest_split_across_books_in_100s(self):
        book = self.post('books', {'name': '여행 자금', 'target': 30000, 'icon': '✈️', 'color': 'blue', 'nickname': '', 'key': 'book-travel-1'}).json()
        travel = next(b for b in book['books'] if b['name'] == '여행 자금')
        self.post('transactions', {'kind': 'deposit', 'amount': 10000, 'book_id': travel['id'], 'key': 'deposit-travel-1'})
        state = self.state()['state']
        self.assertEqual(state['rewards']['estimates']['savings_interest'], 500)  # 25,000 × 2% = 500
        self.assertTrue(all(b['interest'] % 100 == 0 for b in state['books']))
        self.assertEqual(sum(b['interest'] for b in state['books']), 500)
        self.post('date', {'day': '2026-10-19'})
        after = self.post('claim', {'key': 'claim-books-1'}).json()['state']
        self.assertEqual(sum(b['balance'] for b in after['books']), after['vault'])
        received = [e['amount'] for b in after['books'] for e in b['history'] if e['kind'] == 'savings_interest']
        self.assertEqual(sum(received), 500)
        self.assertTrue(all(a % 100 == 0 for a in received))

    def test_claim_needs_the_trial_token(self):
        self.post('date', {'day': '2026-10-19'})
        forged = self.client.post(f"/api/moneyon/trial/children/{self.first['child']['id']}/claim", json={'key': 'claim-forged-1'},
                                  headers={'X-Moneyon-Trial': 'invented', 'X-Moneyon-Trial-Version': '1'})
        self.assertEqual(forged.status_code, 403)
        other = self.client.post('/api/moneyon/trial/start').json()
        cross = self.client.post(f"/api/moneyon/trial/children/{self.first['child']['id']}/claim", json={'key': 'claim-cross-1'}, headers=self.headers(other))
        self.assertEqual(cross.status_code, 403)
        self.assertEqual(self.state()['state']['wallet'], 28500)

    def test_earlier_trial_keeps_its_rules(self):
        legacy = Trials(self.ledger, unit=1, payment='automatic')
        old = legacy.start()
        # The current service resolves the earlier trial and still applies the rules stored with it.
        row = self.trials.resolve(old['token'])
        state = self.trials.snapshot(row)['state']
        self.assertEqual(state['rewards']['estimates']['allowance_bonus'], 2850)
        self.trials.advance(row, __import__('datetime').date(2026, 10, 19))
        paid = [t for t in self.trials.snapshot(row)['state']['transactions'] if t['kind'] == 'allowance_bonus']
        self.assertEqual([t['wallet'] for t in paid], [2850])

    def test_samples_seeded_under_old_rules_are_never_handed_out(self):
        legacy = Trials(self.ledger, unit=1, payment='automatic')
        for owner in LEGACY_POOLS:
            legacy.seed(owner)
        self.assertEqual(self.trials.pooled(), 0)
        created = self.trials.start(cleanup=0)
        self.assertEqual(created['state']['rewards']['estimates']['allowance_bonus'], 2800)
        self.trials.refill(1)
        self.assertEqual(self.trials.pooled(), 1)
        self.trials.cleanup()
        with self.ledger.db() as db:
            owners = {r[0] for r in db.execute('SELECT owner FROM moneyon_demo_workspaces')}
        self.assertFalse(owners & set(LEGACY_POOLS))
        self.assertIn(POOL, owners)


if __name__ == '__main__':
    unittest.main()
