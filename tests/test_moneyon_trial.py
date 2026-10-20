"""Trial capability isolation, real postings, rollback and settlement tests."""
import hashlib
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import moneyon_trial as api
from services.moneyon import Ledger, reward
from services.moneyon_banking import MockBankingAdapter
from services.moneyon_trial import TrialLedger, Trials


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = TrialLedger(os.path.join(self.tmp.name, 'trial.db'))
        # The earlier trial rules (1원 interest, automatic payment) stay supported for
        # trials created before the 100원 rules; these engine tests keep covering them.
        self.trials = Trials(self.ledger, unit=1, payment='automatic')
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[api.trials] = lambda: self.trials
        self.client = TestClient(app)
        self.first = self.client.post('/api/moneyon/trial/start').json()
        # Existing-user regression fixture: absence of a rule preserves manual approval.
        with self.ledger.db() as db:
            db.execute('DELETE FROM moneyon_payment_rules WHERE child=?',(self.first['child']['id'],))
        self.first.update(self.trials.snapshot(self.trials.resolve(self.first['token'])))
        self.base = '/api/moneyon/trial'
        self.headers = {'X-Moneyon-Trial': self.first['token'], 'X-Moneyon-Trial-Version': '1'}
        self.path = self.base + '/children/' + self.first['child']['id']

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def get(self):
        return self.client.get(self.base + '/state', headers=self.headers).json()

    def post(self, suffix, body):
        return self.client.post(self.path + suffix, json=body, headers=self.headers)

    def test_sample_balances(self):
        s = self.first['state']
        self.assertEqual((s['wallet'], s['vault'], s['wallet'] + s['vault']), (28500,15000,43500))
        self.assertEqual(next(c for c in s['cycles'] if not c['ended'])['interest'], 3150)

    def test_seed_real_transactions(self):
        tx = self.first['state']['transactions']
        expected = {'seed-current-payment':50000, 'seed-stationery':-5000, 'seed-snack':-3000, 'seed-savings':-15000, 'seed-previous-reward':1500}
        for key, amount in expected.items():
            self.assertEqual(next(t for t in tx if t['request_key']==key)['wallet'], amount)
        self.assertEqual(next(t for t in tx if t['request_key']=='seed-previous-reward:expiry')['wallet'], -15000)

    def test_trial_wallet_reward_uses_engine_and_legacy_eligibility_is_preserved(self):
        c = next(c for c in self.first['state']['cycles'] if not c['ended'])
        self.assertEqual(c['eligible'],27000)
        self.assertEqual(self.first['state']['rewards']['estimates'], {'allowance_bonus':2850,'savings_interest':300})
        self.assertEqual(self.first['state']['report']['categories'],{'문구':5000,'간식':3000})

    def test_prior_reward_was_settled_by_engine(self):
        previous = next(c for c in self.first['state']['cycles'] if c['ended'])
        self.assertTrue(previous['settled'])
        self.assertEqual(previous['policy']['cap'],1500)
        self.assertEqual(previous['policy']['amount']*previous['policy']['rate_bps']//10000,1500)

    def test_balanced_postings_and_parent_debit(self):
        row=self.trials.resolve(self.first['token'])
        with self.ledger.db() as db:
            imbalanced=db.execute('SELECT transfer_id FROM bank_postings GROUP BY transfer_id HAVING SUM(amount)<>0').fetchall()
        self.assertEqual(imbalanced,[])
        parent=next(a for a in MockBankingAdapter(self.ledger).get_accounts(row['family']) if a['kind']=='parent')
        self.assertEqual(parent['balance'],448500)

    def test_allowance_double_entry(self):
        r=self.post('/allowance',{'amount':1200,'key':'allowance-unique'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['state']['wallet'],29700)
        row=self.trials.resolve(self.first['token'])
        parent=next(a for a in MockBankingAdapter(self.ledger).get_accounts(row['family']) if a['kind']=='parent')
        self.assertEqual(parent['balance'],447300)
        cycle=next(c for c in r.json()['state']['cycles'] if not c['ended'])
        self.assertEqual(cycle['eligible'],28200)

    def test_allowance_retry_and_conflict(self):
        body={'amount':1000,'key':'allowance-retry'}
        self.post('/allowance',body)
        self.post('/allowance',body)
        self.assertEqual(self.get()['state']['wallet'],29500)
        before=self.get()
        self.assertEqual(self.post('/allowance',body|{'amount':2000}).status_code,409)
        self.assertEqual(self.get(),before)

    def test_insufficient_parent_rolls_back(self):
        before=self.get()
        self.assertEqual(self.post('/allowance',{'amount':1000000,'key':'no-parent-money'}).status_code,409)
        self.assertEqual(self.get(),before)

    def test_expense_category_and_reward_recalculate(self):
        r=self.post('/transactions',{'kind':'expense','key':'expense-larger','amount':20000,'category':'책','note':'책 구매'})
        self.assertEqual(r.status_code,200,r.text)
        s=r.json()
        self.assertEqual(s['wallet'],8500)
        self.assertEqual(s['report']['categories']['책'],20000)
        self.assertEqual(next(c for c in s['cycles'] if not c['ended'])['interest'],1150)

    def test_expense_failure_immutable(self):
        before=self.get()
        self.assertEqual(self.post('/transactions',{'kind':'expense','key':'expense-too-much','amount':28600}).status_code,409)
        self.assertEqual(self.get(),before)

    def test_invalid_amounts(self):
        for amount in (0,-1,1.5,True,'100',10000001):
            before=self.get()
            self.assertEqual(self.post('/allowance',{'amount':amount,'key':'invalid-amount'}).status_code,422)
            self.assertEqual(self.get(),before)

    def test_savings_preserves_total_and_goal_progress(self):
        s=self.post('/transactions',{'kind':'deposit','key':'savings-new','amount':5000}).json()
        self.assertEqual((s['wallet'],s['vault']), (23500,20000))
        self.assertEqual(s['wallet']+s['vault'],43500)
        self.assertEqual(s['goals'][0]['amount'],30000)
        self.assertEqual(s['vault']*100//s['goals'][0]['amount'],66)

    def test_category_annotation_uses_same_ledger(self):
        tx=next(t for t in self.first['state']['transactions'] if t['request_key']=='seed-stationery')
        r=self.client.patch(self.path+'/transactions/'+tx['id']+'/category',json={'category':'선물'},headers=self.headers)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['report']['categories']['선물'],5000)
        self.assertEqual(r.json()['wallet'],28500)

    def test_future_approval_rejected(self):
        c=next(c for c in self.first['state']['cycles'] if not c['ended'])
        before=self.get()
        self.assertEqual(self.post('/approve',{'cycle_id':c['id'],'approved':True,'key':'approve-early'}).status_code,409)
        self.assertEqual(self.get(),before)

    def test_approval_requires_explicit_simulation(self):
        c=self.first['state']['cycles'][0]
        self.assertEqual(self.post('/approve',{'cycle_id':c['id'],'approved':False,'key':'approve-false'}).status_code,422)
        for kind in ('payment','interest'):
            self.assertEqual(self.post('/transactions',{'kind':kind,'key':'not-parent-route'}).status_code,422)

    def test_date_settlement_duplicate_guard(self):
        self.assertEqual(self.post('/date',{'day':'2026-10-19'}).status_code,200)
        c=next(c for c in self.get()['state']['cycles'] if c['ended'] and not c['settled'])
        body={'cycle_id':c['id'],'approved':True,'key':'approve-ended'}
        self.assertEqual(self.post('/approve',body).status_code,200)
        before=self.get()
        self.assertEqual(before['state']['wallet'],31350)
        self.assertEqual(self.post('/approve',body).status_code,200)
        self.assertEqual(self.post('/approve',body|{'key':'approve-second'}).status_code,409)
        self.assertEqual(self.get(),before)

    def test_ended_cycle_keeps_spend_and_allowance_available(self):
        self.post('/date',{'day':'2026-10-19'})
        before=self.get()
        self.assertEqual(self.post('/transactions',{'kind':'expense','key':'pending-spending','amount':100}).status_code,200)
        self.assertEqual(self.post('/allowance',{'amount':100,'key':'pending-allowance'}).status_code,200)
        self.assertEqual(self.get()['state']['wallet'],before['state']['wallet'])

    def test_allowance_after_settlement_opens_valid_cycle(self):
        self.test_date_settlement_duplicate_guard()
        r=self.post('/allowance',{'amount':2000,'key':'next-allowance'})
        self.assertEqual(r.status_code,200,r.text)
        c=next(c for c in r.json()['state']['cycles'] if not c['ended'])
        self.assertEqual((c['eligible'],c['interest']), (2000,3641))

    def test_date_bounds(self):
        for day in ('2026-10-11','2027-10-13','bad-date'):
            before=self.get()
            self.assertIn(self.post('/date',{'day':day}).status_code,(409,422))
            self.assertEqual(self.get(),before)

    def test_reset_restores_sample_and_rejects_old_child(self):
        self.post('/allowance',{'amount':2500,'key':'before-reset'})
        self.post('/date',{'day':'2026-10-19'})
        r=self.client.post(self.base+'/reset',json={'key':'reset-sample'},headers=self.headers)
        self.assertEqual(r.status_code,200,r.text)
        s=r.json()
        self.assertEqual((s['state']['wallet'],s['state']['vault'],s['day']), (28500,15000,'2026-10-12'))
        self.assertEqual(s['generation'],2)
        self.assertEqual(self.client.get(self.path,headers=self.headers).status_code,403)
        self.assertEqual(self.client.post(self.base+'/reset',json={'key':'reset-sample'},headers=self.headers).status_code,200)
        self.assertEqual(self.client.post(self.base+'/reset',json={'key':'stale-request'},headers=self.headers).status_code,409)

    def test_reset_atomic_on_partial_seed_failure(self):
        before=self.get()
        count=None
        with self.ledger.db() as db: count=db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        with patch.object(MockBankingAdapter,'transfer_to_savings',side_effect=ValueError('injected')):
            self.assertEqual(self.client.post(self.base+'/reset',json={'key':'reset-failure'},headers=self.headers).status_code,409)
        self.assertEqual(self.get(),before)
        with self.ledger.db() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0],count)

    def test_independent_visitors_cannot_read_write_or_reset_other(self):
        second=self.client.post(self.base+'/start').json()
        headers={'X-Moneyon-Trial':second['token'],'X-Moneyon-Trial-Version':'1'}
        self.assertEqual(self.client.get(self.path,headers=headers).status_code,403)
        self.assertEqual(self.client.post(self.path+'/allowance',json={'amount':500,'key':'cross-visitor'},headers=headers).status_code,403)
        self.client.post(self.base+'/reset',json={'key':'second-reset'},headers=headers)
        self.assertEqual(self.get(),{k:v for k,v in self.first.items() if k!='token'})

    def test_missing_forged_expired_capability(self):
        for headers in ({},{'X-Moneyon-Trial':'not-a-token'}):
            self.assertEqual(self.client.get(self.base+'/state',headers=headers).status_code,403)
        with self.ledger.db() as db: db.execute('UPDATE trial_visitors SET expires=0')
        self.assertEqual(self.client.get(self.base+'/state',headers=self.headers).status_code,403)

    def test_refresh_resume_from_new_client(self):
        self.post('/allowance',{'amount':1000,'key':'refresh-payment'})
        with TestClient(self.client.app) as reconnect:
            r=reconnect.get(self.base+'/state',headers=self.headers)
            self.assertEqual(r.json()['state']['wallet'],29500)

    def test_concurrent_idempotent_allowance(self):
        def receive(_):
            return self.post('/allowance',{'amount':1000,'key':'concurrent-key'}).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(receive,range(8))),[200]*8)
        self.assertEqual(self.get()['state']['wallet'],29500)

    def test_concurrent_reset_retries_seed_once(self):
        def reset(_):
            return self.client.post(self.base+'/reset',json={'key':'concurrent-reset'},headers=self.headers).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(reset,range(8))),[200]*8)
        self.assertEqual(self.get()['generation'],2)

    def test_real_family_database_is_unchanged(self):
        path=os.path.join(self.tmp.name,'family.db')
        family=Ledger(path)
        family.unlock('actual-family','120056')
        child=family.save_child('actual-family',self.first['child']['profile'],self.first['child']['policy'])
        family.transact('actual-family',child,'payment','actual-allowance',today=date(2026,10,12))
        def digest():
            with open(path,'rb') as f:return hashlib.sha256(f.read()).hexdigest()
        before=digest()
        self.post('/allowance',{'amount':1000,'key':'trial-not-real'})
        self.client.post(self.base+'/reset',json={'key':'trial-reset-real'},headers=self.headers)
        self.assertEqual(digest(),before)
        self.assertEqual(family.state('actual-family',child,date(2026,10,12))['wallet'],50000)

    def test_trial_storage_cannot_equal_family_storage(self):
        with patch.dict(os.environ,{'MONEYON_TRIAL_ENABLED':'1','MONEYON_TRIAL_DB':self.ledger.path,'MONEYON_DB':self.ledger.path}):
            with self.assertRaises(Exception) as raised: api.trials()
            self.assertEqual(raised.exception.status_code,503)

    def test_trial_requires_explicit_enablement(self):
        with patch.dict(os.environ,{'MONEYON_TRIAL_ENABLED':'0'}):
            with self.assertRaises(Exception) as raised: api.trials()
            self.assertEqual(raised.exception.status_code,503)

    def test_capability_response_is_not_cacheable(self):
        response=self.client.get(self.base+'/state',headers=self.headers)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.headers['Vary'],'X-Moneyon-Trial')

    def test_concurrent_visitors_remain_independent(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            visits=list(pool.map(lambda _:self.trials.start(),range(4)))
        self.assertEqual(len({v['token'] for v in visits}),4)
        self.assertEqual(len({v['child']['id'] for v in visits}),4)
        first=visits[0]
        self.trials.allowance(self.trials.resolve(first['token']),1000,'parallel-visitor')
        for visitor in visits:
            snapshot=self.trials.snapshot(self.trials.resolve(visitor['token']))
            self.assertEqual(snapshot['state']['wallet'],29500 if visitor is first else 28500)

    def test_cross_visitor_approval_and_category_rejected(self):
        second=self.trials.start()
        headers={'X-Moneyon-Trial':second['token'],'X-Moneyon-Trial-Version':'1'}
        cycle=self.first['state']['cycles'][0]
        response=self.client.post(self.path+'/approve',headers=headers,json={'cycle_id':cycle['id'],'approved':True,'key':'cross-approval'})
        self.assertEqual(response.status_code,403)
        tx=next(t for t in self.first['state']['transactions'] if t['kind']=='expense')
        response=self.client.patch(self.path+'/transactions/'+tx['id']+'/category',headers=headers,json={'category':'선물'})
        self.assertEqual(response.status_code,403)

    def test_stale_generation_cannot_mutate_reset_workspace(self):
        response=self.client.post(self.base+'/reset',json={'key':'version-reset'},headers=self.headers)
        newpath=self.base+'/children/'+response.json()['child']['id']
        before=self.get()
        response=self.client.post(newpath+'/allowance',headers=self.headers,json={'amount':1000,'key':'stale-allowance'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.get(),before)


if __name__=='__main__': unittest.main()
