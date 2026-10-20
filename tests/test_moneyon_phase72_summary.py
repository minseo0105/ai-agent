"""Phase 7.2 weekly wallet reconciliation, before payment-policy changes."""
import unittest
from tests import test_moneyon_trial as base


class WeeklySummaryTests(unittest.TestCase):
    setUp=base.TrialTests.setUp
    tearDown=base.TrialTests.tearDown
    get=base.TrialTests.get
    post=base.TrialTests.post

    def assert_summary(self):
        state=self.get()['state'];s=state['education']
        self.assertEqual(s['remaining'],state['wallet'])
        self.assertEqual(s['opening']+s['received']+s['interest_received']+s['other_in']+s['withdrawn']-s['spent']-s['saved']-s['other_out'],state['wallet'])
        return s

    def test_seed_separates_legacy_return_and_interest(self):
        s=self.assert_summary()
        self.assertEqual((s['opening'],s['received'],s['interest_received'],s['other_out']),(15000,50000,1500,15000))
        self.assertEqual((s['spent'],s['saved'],s['withdrawn'],s['remaining']),(8000,15000,0,28500))

    def test_deposit_and_withdraw_are_not_net_or_expenses(self):
        self.post('/transactions',dict(kind='deposit',amount=1000,key='summary-deposit'))
        self.post('/transactions',dict(kind='withdraw',amount=500,key='summary-withdraw'))
        s=self.assert_summary()
        self.assertEqual((s['spent'],s['saved'],s['withdrawn']),(8000,16000,500))

    def test_paid_prior_interest_is_not_new_allowance_or_opening(self):
        self.post('/date',dict(day='2026-10-19'))
        cycle=next(i['cycle_id'] for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval')
        self.post('/approve',dict(cycle_id=cycle,approved=True,key='summary-paid-interest'))
        s=self.assert_summary()
        self.assertEqual((s['opening'],s['received'],s['interest_received'],s['remaining']),(28500,0,2850,31350))

    def test_retry_and_new_week_keep_period_boundaries(self):
        body=dict(kind='deposit',amount=1000,key='summary-retry-deposit')
        self.post('/transactions',body);self.post('/transactions',body)
        self.assertEqual(self.assert_summary()['saved'],16000)
        self.post('/date',dict(day='2026-10-19'))
        s=self.assert_summary()
        self.assertEqual((s['opening'],s['received'],s['spent'],s['saved']),(27500,0,0,0))
