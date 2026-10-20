"""Closing principal, separate approvals and double-entry reward invariants."""
from datetime import date
from unittest.mock import patch
import unittest
from tests import test_moneyon_trial as base


class DualRewardTests(unittest.TestCase):
    setUp=base.TrialTests.setUp
    tearDown=base.TrialTests.tearDown
    get=base.TrialTests.get
    post=base.TrialTests.post
    def estimates(self):
        return self.get()['state']['rewards']['estimates']

    def close_week(self):
        self.post('/date', {'day':'2026-10-19'})
        return next(i['cycle_id'] for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval')

    def test_disjoint_realtime_principals(self):
        self.post('/transactions', {'kind':'expense','amount':1000,'key':'dual-expense'})
        self.assertEqual(self.estimates(), {'allowance_bonus':2750,'savings_interest':300})
        self.post('/transactions', {'kind':'deposit','amount':5000,'key':'dual-deposit'})
        self.assertEqual(self.estimates(), {'allowance_bonus':2250,'savings_interest':400})
        self.post('/transactions', {'kind':'withdraw','amount':1000,'key':'dual-withdraw'})
        self.assertEqual(self.estimates(), {'allowance_bonus':2350,'savings_interest':380})
        items=[i for i in self.get()['state']['rewards']['items'] if i['status']=='estimated']
        self.assertEqual(sum(i['base'] for i in items),42500)

    def test_separate_approval_and_frozen_closing_balance(self):
        cycle=self.close_week()
        body={'cycle_id':cycle,'approved':True,'key':'dual-bonus','reward_type':'allowance_bonus'}
        result=self.post('/approve',body)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual((result.json()['state']['wallet'],result.json()['state']['vault']),(31350,15000))
        items=[i for i in result.json()['state']['rewards']['items'] if i['cycle_id']==cycle]
        self.assertEqual([i['status'] for i in items],['paid','awaiting_approval'])
        self.assertEqual(items[1]['amount'],300)
        self.assertEqual(self.post('/approve',body).status_code,200)
        self.assertEqual(self.post('/approve',body|{'key':'double-bonus'}).status_code,409)
        self.assertEqual(self.post('/approve',body|{'key':'dual-savings','reward_type':'savings_interest'}).status_code,200)
        state=self.get()['state']
        self.assertEqual((state['wallet'],state['vault']),(31350,15300))
        with self.ledger.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trial_rewards WHERE cycle=?',(cycle,)).fetchone()[0],2)
            self.assertFalse(db.execute('SELECT transfer_id FROM bank_postings GROUP BY transfer_id HAVING SUM(amount)<>0').fetchall())
        row=self.trials.resolve(self.first['token'])
        parent=next(a for a in self.ledger.state(row['family'],row['child'],date(2026,10,19))['banking']['accounts'] if a['kind']=='wallet')
        self.assertEqual(parent['balance'],31350)

    def test_atomic_two_reward_failure(self):
        cycle=self.close_week()
        before=self.get()
        original=self.ledger._entry
        def fail(*args,**kwargs):
            if args[3]=='savings_interest':
                raise ValueError('injected payment failure')
            return original(*args,**kwargs)
        with patch.object(self.ledger,'_entry',side_effect=fail):
            response=self.post('/approve',{'cycle_id':cycle,'approved':True,'key':'atomic-dual'})
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.get(),before)

    def test_closed_week_unchanged_by_next_week(self):
        cycle=self.close_week()
        body={'cycle_id':cycle,'approved':True,'key':'close-dual'}
        self.assertEqual(self.post('/approve',body).status_code,200)
        self.post('/allowance',{'amount':1000,'key':'following-week'})
        self.assertEqual(self.estimates(),{'allowance_bonus':3235,'savings_interest':306})
        old=[i for i in self.get()['state']['rewards']['items'] if i['cycle_id']==cycle]
        self.assertEqual([i['paid_amount'] for i in old],[2850,300])

    def test_reset_restores_both_estimates(self):
        self.post('/transactions',{'kind':'deposit','amount':10000,'key':'before-dual-reset'})
        result=self.client.post(self.base+'/reset',json={'key':'dual-reset-sample'},headers=self.headers)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['state']['rewards']['estimates'],{'allowance_bonus':2850,'savings_interest':300})

    def test_experiment_uses_wallet_principal(self):
        r=self.post('/experiment',{'spend':1000})
        self.assertEqual(r.json()['interest'],2750)
        self.assertEqual(r.json()['savings_interest'],300)

    def test_hundred_won_input_rule_preserves_ledger(self):
        for amount in (1, 99, 101, 333, 1234):
            for kind in ('expense','deposit','withdraw'):
                before=self.get()
                response=self.post('/transactions',{'kind':kind,'amount':amount,'key':'reject-non-hundred'})
                self.assertEqual(response.status_code,422,response.text)
                self.assertEqual(self.get(),before)
            before=self.get()
            self.assertEqual(self.post('/allowance',{'amount':amount,'key':'reject-allowance'}).status_code,422)
            self.assertEqual(self.get(),before)

    def test_final_requested_flow(self):
        self.assertEqual(self.post('/transactions',{'kind':'expense','amount':3000,'key':'final-expense'}).status_code,200)
        self.assertEqual(self.get()['state']['wallet'],25500)
        self.assertEqual(self.estimates(),{'allowance_bonus':2550,'savings_interest':300})
        self.assertEqual(self.post('/transactions',{'kind':'deposit','amount':5000,'key':'final-deposit'}).status_code,200)
        self.assertEqual((self.get()['state']['wallet'],self.get()['state']['vault']),(20500,20000))
        self.assertEqual(self.estimates(),{'allowance_bonus':2050,'savings_interest':400})
        cycle=self.close_week()
        for kind in ('allowance_bonus','savings_interest'):
            response=self.post('/approve',{'cycle_id':cycle,'approved':True,'key':'final-'+kind,'reward_type':kind})
            self.assertEqual(response.status_code,200,response.text)
        self.assertEqual((self.get()['state']['wallet'],self.get()['state']['vault']),(22550,20400))
