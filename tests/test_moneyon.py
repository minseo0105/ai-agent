import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import moneyon
from services.moneyon import Ledger, period, reward

POLICY = dict(frequency='weekly', amount=10000, pay_day=0, rate_bps=1000, cap=1000, rollover=True)
PROFILE = dict(name='모니', grade=1, avatar='🪙', theme='moneyon')
DAY = date(2026, 10, 12)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Ledger(os.path.join(self.tmp.name, 'test.sqlite3'))
        self.child = self.db.save_child('a', PROFILE, POLICY)
    def tearDown(self):
        self.tmp.cleanup()
    def tx(self, kind, key, **kw):
        self.db.transact('a', self.child, kind, key, today=kw.pop('today', DAY), **kw)
    def state(self):
        return self.db.state('a', self.child, DAY)
    def test_two_children_same_name_independent(self):
        other = self.db.save_child('a', PROFILE, POLICY | {'frequency':'monthly','pay_day':1,'amount':30000})
        self.tx('payment','payment-1')
        self.db.transact('a', other, 'payment','payment-2',today=DAY)
        self.tx('expense','expense-1',amount=4000)
        self.assertEqual(self.state()['wallet'],6000)
        self.assertEqual(self.state()['cycles'][0]['interest'],600)
        self.assertEqual(self.db.state('a',other)['wallet'],30000)
        self.assertNotEqual(other,self.child)
    def test_rounding_cap_and_dates(self):
        self.assertEqual(reward(199, POLICY),19)
        self.assertEqual(reward(100000, POLICY),1000)
        p = POLICY | {'frequency':'monthly','pay_day':31}
        self.assertEqual(period(date(2026,2,28),p),(date(2026,2,28),date(2026,3,31)))
        self.assertEqual(period(date(2026,1,1),p),(date(2025,12,31),date(2026,1,31)))
        self.assertEqual(period(DAY,POLICY),(DAY,date(2026,10,19)))
    def test_overspend_idempotency(self):
        self.tx('payment','payment-1')
        self.tx('payment','payment-1')
        with self.assertRaises(ValueError): self.tx('payment','payment-2')
        with self.assertRaises(ValueError): self.tx('expense','expense-1',amount=10001)
        self.tx('expense','expense-1',amount=4000)
        self.tx('expense','expense-1',amount=4000)
        self.assertEqual(self.state()['wallet'],6000)
    def test_vault_no_double_count_or_interest_reentry(self):
        self.tx('payment','payment-1')
        self.tx('deposit','deposit-1',amount=3000)
        self.assertEqual((self.state()['wallet'],self.state()['vault']),(7000,3000))
        self.tx('withdraw','withdraw-1',amount=2000)
        s=self.state()
        self.assertEqual(s['wallet']+s['vault'],10000)
        self.assertEqual(s['cycles'][0]['interest'],700)
        with self.assertRaises(ValueError): self.tx('withdraw','withdraw-2',amount=2000)
    def test_approval_snapshot_rollover(self):
        self.tx('payment','payment-1')
        self.tx('expense','expense-1',amount=4000)
        cid=self.state()['cycles'][0]['id']
        with self.assertRaises(ValueError): self.tx('interest','interest-1',cycle_id=cid)
        self.db.save_child('a',PROFILE,POLICY|{'rate_bps':5000},self.child)
        self.assertEqual(self.state()['wallet'],6000)
        self.tx('interest','interest-1',cycle_id=cid,today=date(2026,10,19))
        self.tx('interest','interest-1',cycle_id=cid,today=date(2026,10,19))
        with self.assertRaises(ValueError): self.tx('interest','interest-2',cycle_id=cid,today=date(2026,10,19))
        self.assertEqual(self.state()['wallet'],6600)
        self.tx('payment','payment-2',today=date(2026,10,19))
        s=self.db.state('a',self.child,date(2026,10,19))
        self.assertEqual(s['wallet'],16600)
        self.assertEqual(s['cycles'][0]['eligible'],10000)
        self.assertEqual(s['cycles'][0]['policy']['rate_bps'],5000)
        self.assertEqual(s['cycles'][1]['interest'],600)
    def test_no_rollover(self):
        self.db.save_child('a',PROFILE,POLICY|{'rollover':False},self.child)
        self.tx('payment','payment-1')
        self.tx('deposit','deposit-1',amount=3000)
        cid=self.state()['cycles'][0]['id']
        self.tx('interest','interest-1',cycle_id=cid,today=date(2026,10,19))
        self.assertEqual((self.state()['wallet'],self.state()['vault']),(700,3000))
    def test_cancel_audit(self):
        self.tx('payment','payment-1')
        self.tx('expense','expense-1',amount=4000)
        tx=next(t for t in self.state()['transactions'] if t['kind']=='expense')
        self.db.cancel_expense('a',self.child,tx['id'],'잘못 입력',DAY)
        self.db.cancel_expense('a',self.child,tx['id'],'중복 클릭',DAY)
        self.assertEqual(self.state()['wallet'],10000)
        self.assertEqual(self.state()['cycles'][0]['eligible'],10000)
        self.assertTrue(any(t['kind']=='expense' for t in self.state()['transactions']))
    def test_family_and_child_permissions(self):
        with self.assertRaises(PermissionError): self.db.state('b',self.child)
        token=self.db.unlock('a','123456')
        self.assertIsNone(self.db.unlock('a','000000'))
        session=self.db.child_session('a',token,self.child)
        other=self.db.save_child('a',PROFILE,POLICY)
        with self.assertRaises(PermissionError): self.db.authorize('a',session,child=other)
        with self.assertRaises(PermissionError): self.db.authorize('a',session,parent=True)
        with self.assertRaises(PermissionError): self.db.authorize('b',token,parent=True)
    def test_pause_archive_theme(self):
        self.tx('payment','payment-1')
        self.db.save_child('a',PROFILE|{'theme':'animals'},POLICY,self.child,'paused')
        with self.assertRaises(PermissionError): self.tx('expense','expense-1',amount=100)
        self.assertEqual(self.state()['wallet'],10000)
        self.db.save_child('a',PROFILE,POLICY,self.child,'archived')
        self.assertEqual(self.db.children('a')[0]['status'],'archived')
    def test_concurrent_approval_once(self):
        self.tx('payment','payment-1')
        cid=self.state()['cycles'][0]['id']
        def approve(i):
            try:
                self.tx('interest',f'interest-{i}',cycle_id=cid,today=date(2026,10,19))
                return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(approve,range(4)))
        self.assertEqual(sum(results),1)
        self.assertEqual(self.state()['wallet'],11000)
    def test_pending_end_keeps_trading_and_preserves_closing(self):
        self.tx('payment','payment-1')
        eligible=self.state()['cycles'][0]['eligible']
        self.tx('expense','expense-1',amount=100,today=date(2026,10,19))
        self.tx('payment','payment-2',today=date(2026,10,19))
        self.assertEqual(next(c for c in self.state()['cycles'] if c['start']=='2026-10-12')['eligible'],eligible)
    def test_goal_and_migration_repeat(self):
        self.db.goal('a',self.child,'책',30000)
        self.assertEqual(self.state()['goals'][0]['amount'],30000)
        Ledger(self.db.path)
        self.assertEqual(len(self.db.children('a')),1)
    def test_progress_amount_independent_quiz_once(self):
        self.assertFalse(self.db.complete_quiz('a',self.child,'interest',10))
        self.assertTrue(self.db.complete_quiz('a',self.child,'interest',100))
        self.assertTrue(self.db.complete_quiz('a',self.child,'interest',100))
        self.assertEqual(self.state()['xp'],20)
        self.assertEqual(self.state()['badges'],['금융 탐험가'])
        self.tx('payment','payment-1')
        self.assertEqual(self.state()['xp'],20)
    def test_child_selection_revokes_parent_and_lock_revokes_child(self):
        token=self.db.unlock('a','123456')
        childtoken=self.db.child_session('a',token,self.child)
        with self.assertRaises(PermissionError):self.db.authorize('a',token,parent=True)
        self.db.lock('a',childtoken)
        with self.assertRaises(PermissionError):self.db.authorize('a',childtoken,child=self.child)


class APITests(LedgerTests):
    def setUp(self):
        super().setUp()
        app=FastAPI(); app.include_router(moneyon.router)
        app.dependency_overrides[moneyon.ledger]=lambda:self.db
        app.dependency_overrides[moneyon.identity]=lambda:'a'
        self.client=TestClient(app)
        self.token=self.db.unlock('a','123456')
        self.headers={'X-Moneyon-Session':self.token}
    def test_api_child_cannot_pay_and_cannot_switch(self):
        token=self.db.child_session('a',self.token,self.child)
        headers={'X-Moneyon-Session':token}
        url=f'/api/moneyon/children/{self.child}'
        self.assertEqual(self.client.post(url+'/transactions',headers=headers,json={'kind':'payment','key':'payment-1'}).status_code,403)
        self.assertEqual(self.client.get('/api/moneyon/children',headers=headers).status_code,403)
        other=self.db.save_child('a',PROFILE,POLICY)
        self.assertEqual(self.client.get('/api/moneyon/children/'+other,headers=headers).status_code,403)
        self.assertEqual(self.client.get(url).status_code,403)
    def test_experiment_read_only_and_goal(self):
        with patch.object(moneyon,'today',return_value=DAY):
            url=f'/api/moneyon/children/{self.child}'
            self.client.post(url+'/transactions',headers=self.headers,json={'kind':'payment','key':'payment-1'})
            before=self.client.get(url,headers=self.headers).json()
            r=self.client.post(url+'/experiment',headers=self.headers,json={'spend':3000})
            self.assertEqual(r.json(),dict(left=7000,eligible=7000,interest=700,total=7700))
            self.assertEqual(self.client.get(url,headers=self.headers).json(),before)
            self.assertEqual(self.client.post(url+'/goals',headers=self.headers,json={'name':'책','amount':30000}).status_code,200)
            self.assertEqual(self.client.post(url+'/transactions',headers=self.headers,json={'kind':'expense','key':'expense-1','amount':1.5}).status_code,422)
    def test_production_disabled(self):
        with patch.dict(os.environ,{'MONEYON_LOCAL_DEV':'1','APP_ENV':'production'}):
            with self.assertRaises(Exception) as e: moneyon.ledger()
            self.assertEqual(e.exception.status_code,503)
    def test_child_can_revoke_own_session(self):
        token=self.db.child_session('a',self.token,self.child)
        headers={'X-Moneyon-Session':token}
        self.assertEqual(self.client.post('/api/moneyon/lock',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/moneyon/children/'+self.child,headers=headers).status_code,403)


if __name__=='__main__': unittest.main()
