"""Phase 7: closing snapshots, approval funding and same-week interest exclusion."""
from tests import test_moneyon_dual_rewards as dual
from tests import test_moneyon_trial as base
import unittest


class WeeklyEducationTests(unittest.TestCase):
    setUp=base.TrialTests.setUp
    tearDown=base.TrialTests.tearDown
    get=base.TrialTests.get
    post=base.TrialTests.post
    close_week=dual.DualRewardTests.close_week

    def item(self, cycle=None, kind='allowance_bonus'):
        return next(i for i in self.get()['state']['rewards']['items']
                    if i['reward_type']==kind and (i['cycle_id']==cycle if cycle else i['status']=='estimated'))

    def approve(self, cycle, kind='allowance_bonus', key='weekly-approval'):
        return self.post('/approve',dict(cycle_id=cycle,reward_type=kind,approved=True,key=key))

    def test_sample_equation_and_weekly_totals(self):
        state=self.get()['state']
        self.assertEqual((self.item()['base'],self.item()['amount'],self.item()['rate_bps']),(28500,2850,1000))
        self.assertEqual({k:state['education'][k] for k in ('received','spent','saved','opening')},
                         dict(received=50000,spent=8000,saved=15000,opening=15000))
        self.assertIsNone(self.item()['cap'])

    def test_allowance_expense_savings_equations(self):
        parent=self.get()['state']['education']['parent_balance']
        self.assertEqual(self.post('/allowance',dict(amount=30000,key='mom-bank-allowance')).status_code,200)
        state=self.get()['state']
        self.assertEqual((state['wallet'],state['education']['parent_balance']),(58500,parent-30000))
        self.assertEqual(self.item()['amount'],5850)
        self.post('/transactions',dict(kind='expense',amount=3000,key='weekly-expense'))
        self.assertEqual((self.get()['state']['education']['spent'],self.item()['amount']),(11000,5550))
        self.post('/transactions',dict(kind='deposit',amount=5000,key='weekly-saving'))
        state=self.get()['state']
        self.assertEqual((state['wallet'],state['vault']),(50500,20000))
        self.assertEqual((self.item()['amount'],self.item(kind='savings_interest')['amount']),(5050,400))

    def test_closing_frozen_and_separate_destinations(self):
        cycle=self.close_week()
        before=self.get()['state']
        self.assertEqual(self.item(cycle)['status'],'awaiting_approval')
        self.assertEqual(self.approve(cycle).status_code,200)
        after=self.get()['state']
        self.assertEqual((after['wallet'],after['vault']),(31350,15000))
        self.assertEqual(after['education']['parent_balance'],before['education']['parent_balance']-2850)
        self.assertEqual((self.item(cycle)['base'],self.item(cycle)['paid_amount']),(28500,2850))
        self.assertEqual((self.item()['base'],self.item()['amount']),(31350,3135))
        self.assertEqual(self.approve(cycle,'savings_interest','weekly-piggy').status_code,200)
        self.assertEqual(self.get()['state']['vault'],15300)
        self.post('/transactions',dict(kind='expense',amount=3000,key='after-closing-spend'))
        self.assertEqual((self.item()['base'],self.item()['amount']),(28350,2835))
        self.assertEqual((self.item(cycle)['base'],self.item(cycle)['amount']),(28500,2850))
        with self.ledger.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trial_closings WHERE cycle=?',(cycle,)).fetchone()[0],2)
            self.assertFalse(db.execute('SELECT transfer_id FROM bank_postings GROUP BY transfer_id HAVING SUM(amount)<>0').fetchall())

    def test_sunday_monday_boundary_and_no_early_approval(self):
        cycle=self.item()['cycle_id']
        self.post('/date',dict(day='2026-10-18'))
        self.assertEqual(self.item(cycle)['status'],'estimated')
        self.assertEqual(self.approve(cycle).status_code,409)
        self.post('/transactions',dict(kind='expense',amount=3000,key='sunday-expense'))
        self.post('/date',dict(day='2026-10-19'))
        self.assertEqual((self.item(cycle)['base'],self.item(cycle)['amount']),(25500,2550))
        self.assertEqual(self.item(cycle)['status'],'awaiting_approval')
        self.approve(cycle)
        self.assertEqual((self.item(cycle)['amount'],self.item()['amount']),(2550,2805))

    def test_delayed_approval_does_not_change_any_closed_week(self):
        cycle=self.close_week()
        self.post('/date',dict(day='2026-10-26'))
        closed=[i for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval']
        self.approve(cycle)
        for old in closed:
            now=self.item(old['cycle_id'],old['reward_type'])
            self.assertEqual((now['base'],now['amount']),(old['base'],old['amount']))

    def test_parent_insufficient_reward_atomicity(self):
        cycle=self.close_week()
        row=self.trials.resolve(self.first['token'])
        from services import moneyon_accounts as accounts
        with self.ledger.db() as db:
            parent=accounts.ensure_family(db,row['family'])
            db.execute('UPDATE bank_postings SET amount=0 WHERE account_id=?',(parent,))
        before=self.get()
        self.assertEqual(self.approve(cycle).status_code,409)
        self.assertEqual(self.get(),before)

    def test_no_800_cap_and_integer_rounding(self):
        self.post('/allowance',dict(amount=100000,key='uncapped-weekly-allowance'))
        self.assertEqual(self.item()['amount'],12850)
        from services.moneyon import reward
        self.assertEqual(reward(25559,dict(rate_bps=1000,cap=None)),2555)

    def test_restart_keeps_snapshot_and_other_visitor_isolated(self):
        cycle=self.close_week()
        second=self.client.post(self.base+'/start').json()
        self.approve(cycle)
        from services.moneyon_trial import TrialLedger,Trials
        restarted=Trials(TrialLedger(self.ledger.path), unit=1, payment='automatic')
        first=restarted.snapshot(restarted.resolve(self.first['token']))
        other=restarted.snapshot(restarted.resolve(second['token']))
        self.assertEqual(first['state']['wallet'],31350)
        self.assertEqual(other['state']['wallet'],28500)
        self.assertEqual(first['state']['rewards']['items'][0]['amount'],self.get()['state']['rewards']['items'][0]['amount'])
