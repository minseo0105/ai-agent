"""Regression for wallet 14,250 vs stale 11,100 interest principal."""
import unittest
from tests import test_moneyon_trial as base


class InterestConsistencyTests(unittest.TestCase):
    setUp=base.TrialTests.setUp
    tearDown=base.TrialTests.tearDown
    get=base.TrialTests.get
    post=base.TrialTests.post

    def reproduce(self):
        self.post('/allowance',dict(amount=3000,key='consistency-allowance'))
        self.post('/date',dict(day='2026-10-19'))
        cycle=next(i['cycle_id'] for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval')
        self.post('/approve',dict(cycle_id=cycle,approved=True,key='consistency-approval'))
        self.post('/date',dict(day='2026-10-23'))
        self.post('/transactions',dict(kind='expense',amount=20400,key='consistency-spend'))
        return cycle

    def test_reported_14250_wallet_and_1425_interest(self):
        self.reproduce()
        s=self.get()['state']
        item=next(i for i in s['rewards']['items'] if i['reward_type']=='allowance_bonus' and i['status']=='estimated')
        self.assertEqual((s['wallet'],item['base'],item['amount']),(14250,14250,1425))
        self.assertEqual(s['rewards']['estimates']['savings_interest'],306)

    def test_expense_and_experiment_share_principal_and_precision(self):
        self.reproduce()
        before=self.get()
        self.assertEqual(self.post('/experiment',dict(spend=3000)).json()['interest'],1125)
        self.assertEqual(self.get(),before)
        self.post('/transactions',dict(kind='expense',amount=3000,key='consistency-next-expense'))
        self.assertEqual(self.get()['state']['wallet'],11250)
        self.assertEqual(self.get()['state']['rewards']['estimates']['allowance_bonus'],1125)

    def test_closing_freezes_and_duplicate_approval_stays_blocked(self):
        old=self.reproduce()
        previous=[i for i in self.get()['state']['rewards']['items'] if i['cycle_id']==old]
        self.post('/date',dict(day='2026-10-26'))
        cycle=next(i['cycle_id'] for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval')
        pending=next(i for i in self.get()['state']['rewards']['items'] if i['cycle_id']==cycle and i['reward_type']=='allowance_bonus')
        self.assertEqual((pending['base'],pending['amount']),(14250,1425))
        body=dict(cycle_id=cycle,reward_type='allowance_bonus',approved=True,key='consistency-next-approval')
        self.assertEqual(self.post('/approve',body).status_code,200)
        self.assertEqual(self.get()['state']['wallet'],15675)
        self.assertEqual(self.post('/approve',body|{'key':'consistency-duplicate'}).status_code,409)
        self.assertEqual([i for i in self.get()['state']['rewards']['items'] if i['cycle_id']==old],previous)

    def test_normal_mode_keeps_configured_policy_and_parent_approval(self):
        # Normal family API uses parent-configured eligible-new-allowance rules,
        # not the public trial policy; don't silently rewrite existing families.
        from services.moneyon import Ledger
        from datetime import date
        ledger=Ledger(self.tmp.name+'/normal.db')
        ledger.unlock('normal','123456')
        child=ledger.save_child('normal',dict(name='아이',grade=2,avatar='coin',theme='moneyon'),
            dict(frequency='weekly',amount=14250,pay_day=0,rate_bps=1000,cap=10000,rollover=True))
        ledger.transact('normal',child,'payment','normal-payment',today=date(2026,10,12))
        state=ledger.state('normal',child,date(2026,10,12))
        self.assertEqual((state['wallet'],state['cycles'][0]['interest']),(14250,1425))
        ledger.transact('normal',child,'expense','normal-expense',amount=3000,today=date(2026,10,12))
        self.assertEqual(ledger.state('normal',child,date(2026,10,12))['cycles'][0]['interest'],1125)
        with self.assertRaises(ValueError):
            ledger.transact('normal',child,'interest','normal-early',cycle_id=state['cycles'][0]['id'],today=date(2026,10,12))
