"""Offline account conservation, migration, permissions and DEMO isolation."""
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from api import moneyon
from services.moneyon import Ledger
from services.moneyon_banking import MockBankingAdapter
from services.moneyon_demo import DemoWorkspaces

DAY = date(2026, 10, 15)
POLICY = dict(frequency='weekly', amount=10000, pay_day=3, rate_bps=1000, cap=1000, rollover=True)
PROFILE = dict(name='재현', grade=3, avatar='🪙', theme='moneyon')


class Setup:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'banking.sqlite3')
        self.db = Ledger(self.path)
        self.parent_token = self.db.unlock('family-a', '123456')
        self.child = self.db.save_child('family-a', PROFILE, POLICY)
        self.other = self.db.save_child('family-a', PROFILE | {'name':'서연'}, POLICY | {'amount':30000,'frequency':'monthly','pay_day':15,'rate_bps':500})
        self.bank = MockBankingAdapter(self.db)
    def tearDown(self):
        self.tmp.cleanup()
    def parent(self, family='family-a'):
        return next(a for a in self.bank.get_accounts(family) if a['kind']=='parent')
    def state(self, child=None, day=DAY):
        return self.db.state('family-a', child or self.child, day)
    def pay(self, key='allowance-key', child=None):
        self.bank.transfer_allowance('family-a', child or self.child, key, DAY)
    def consistent(self):
        with self.db.db() as db:
            events=db.execute('SELECT id FROM bank_events').fetchall()
            for event in events:
                self.assertEqual(db.execute('SELECT SUM(amount) FROM bank_postings WHERE transfer_id=?',(event['id'],)).fetchone()[0],0)
            for c in db.execute('SELECT id FROM children').fetchall():
                old=db.execute('SELECT COALESCE(SUM(wallet),0),COALESCE(SUM(vault),0) FROM transactions WHERE child=?',(c['id'],)).fetchone()
                new=self.db._balance(db,c['id'])
                self.assertEqual((new['wallet'],new['vault']),tuple(old))
            for a in db.execute('SELECT id FROM bank_accounts').fetchall():
                running=0
                for posting in db.execute('SELECT amount,balance_after FROM bank_postings WHERE account_id=? ORDER BY rowid',(a['id'],)):
                    running+=posting['amount']; self.assertEqual(posting['balance_after'],running)


class BankingTests(Setup, unittest.TestCase):
    def test_independent_demo_accounts_and_initial_parent_funds(self):
        a=self.bank.get_accounts('family-a')
        self.assertEqual(len(a),5)
        self.assertEqual(len({r['id'] for r in a}),5)
        self.assertTrue(all(r['id'].startswith('DEMO-') for r in a))
        self.assertEqual(self.parent()['balance'],500000)
        self.assertEqual(self.state()['wallet'],0)
        self.assertEqual(len(self.bank.get_accounts('family-a',self.child)),2)
        self.consistent()
    def test_allowance_double_entry_same_transfer_id_and_passbook(self):
        self.pay()
        self.assertEqual(self.parent()['balance'],490000)
        state=self.state()
        self.assertEqual(state['wallet'],10000)
        child_tx=next(t for t in state['banking']['transactions'] if t['transaction_type']=='ALLOWANCE_TRANSFER')
        parent_tx=self.bank.get_transactions('family-a',self.parent()['id'])[0]
        self.assertEqual(child_tx['transfer_id'],parent_tx['transfer_id'])
        self.assertEqual((parent_tx['amount'],child_tx['amount']),(-10000,10000))
        self.assertEqual(child_tx['transaction_id'],state['transactions'][0]['id'])
        self.consistent()
    def test_duplicate_requests_and_conflicting_key(self):
        self.pay(); self.pay()
        self.bank.simulate_purchase('family-a',self.child,'purchase-key','문구점',4000,DAY)
        self.bank.simulate_purchase('family-a',self.child,'purchase-key','문구점',4000,DAY)
        with self.assertRaises(ValueError):self.bank.simulate_purchase('family-a',self.child,'purchase-key','서점',5000,DAY)
        with self.assertRaises(ValueError):self.pay('different-key')
        self.assertEqual(self.state()['wallet'],6000)
        self.assertEqual(self.parent()['balance'],490000)
        self.assertEqual(sum(t['kind']=='expense' for t in self.state()['transactions']),1)
        self.consistent()
    def test_parent_insufficient_rolls_back_cycle_and_all_entries(self):
        self.db.save_child('family-a',PROFILE,POLICY|{'amount':500001},self.child)
        before=self.state(); parent_before=self.parent()
        with self.assertRaisesRegex(ValueError,'부모'):self.pay()
        self.assertEqual(self.state(),before)
        self.assertEqual(self.parent(),parent_before)
        self.consistent()
    def test_injected_posting_failure_atomicity(self):
        from services import moneyon_accounts as ac
        original=ac._post
        def fail(db,event,account,amount):
            if amount<0:raise RuntimeError('injected transfer failure')
            return original(db,event,account,amount)
        before=self.state()
        with patch.object(ac,'_post',side_effect=fail):
            with self.assertRaises(RuntimeError):self.pay()
        self.assertEqual(self.state(),before)
        self.assertEqual(self.parent()['balance'],500000)
        self.consistent()
    def test_purchase_auto_category_and_category_audit_changes_no_amount(self):
        self.pay()
        self.bank.simulate_purchase('family-a',self.child,'purchase-key','문구점',4000,DAY)
        s=self.state(); tx=next(t for t in s['transactions'] if t['kind']=='expense')
        self.assertEqual((s['wallet'],s['cycles'][0]['interest']),(6000,600))
        self.assertEqual(tx['category'],'문구')
        self.bank.change_category('family-a',self.child,tx['id'],'선물')
        changed=self.state()
        self.assertEqual(changed['wallet'],6000)
        self.assertEqual(changed['report']['categories'],{'선물':4000})
        self.assertEqual(changed['banking']['transactions'][0]['category'],'선물')
        with self.db.db() as db:
            self.assertEqual(db.execute('SELECT category FROM transactions WHERE id=?',(tx['id'],)).fetchone()[0],'문구')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bank_category_changes').fetchone()[0],1)
        self.consistent()
    def test_manual_and_simulated_expenses_share_one_balance(self):
        self.pay()
        self.db.transact('family-a',self.child,'expense','manual-key',amount=1000,category='간식',today=DAY)
        self.bank.simulate_purchase('family-a',self.child,'simulation-key','편의점',2000,DAY)
        s=self.state()
        self.assertEqual(s['wallet'],7000)
        self.assertEqual({t['transaction_type'] for t in s['banking']['transactions']},{'ALLOWANCE_TRANSFER','SIMULATED_PURCHASE','MANUAL_EXPENSE'})
        self.consistent()
    def test_reward_transfer_approval_once_and_snapshot(self):
        self.pay();self.bank.simulate_purchase('family-a',self.child,'purchase-key','문구점',4000,DAY)
        cycle=self.state()['cycles'][0]['id']
        with self.assertRaises(ValueError):self.bank.settle_reward_interest('family-a',self.child,'interest-key',cycle,DAY)
        self.db.save_child('family-a',PROFILE,POLICY|{'rate_bps':5000},self.child)
        self.assertEqual(self.state()['wallet'],6000)
        self.bank.settle_reward_interest('family-a',self.child,'interest-key',cycle,date(2026,10,22))
        self.bank.settle_reward_interest('family-a',self.child,'interest-key',cycle,date(2026,10,22))
        with self.assertRaises(ValueError):self.bank.settle_reward_interest('family-a',self.child,'interest-again',cycle,date(2026,10,22))
        self.assertEqual(self.state()['wallet'],6600)
        self.assertEqual(self.parent()['balance'],489400)
        t=self.state()['banking']['transactions'][0]
        p=self.bank.get_transactions('family-a',self.parent()['id'])[0]
        self.assertEqual(t['transaction_type'],'PARENT_REWARD_INTEREST')
        self.assertEqual(t['transfer_id'],p['transfer_id'])
        self.consistent()
    def test_reward_insufficient_does_not_settle_or_leave_partial_event(self):
        self.db.save_child('family-a',PROFILE,POLICY|{'amount':500000},self.child)
        self.pay();cycle=self.state()['cycles'][0]['id'];before=self.state()
        with self.assertRaisesRegex(ValueError,'부모'):self.bank.settle_reward_interest('family-a',self.child,'interest-key',cycle,date(2026,10,22))
        self.assertEqual(self.state(),before)
        self.assertEqual(self.parent()['balance'],0)
        self.consistent()
    def test_vault_transfer_linkage_conservation_not_expense(self):
        self.pay();self.bank.transfer_to_savings('family-a',self.child,'save-key',5000,DAY)
        s=self.state(); entries=[t for t in s['banking']['transactions'] if t['transaction_type']=='SAVINGS_DEPOSIT']
        self.assertEqual(len(entries),2);self.assertEqual(entries[0]['transfer_id'],entries[1]['transfer_id'])
        self.assertEqual(sum(t['amount'] for t in entries),0)
        self.assertEqual((s['wallet'],s['vault'],s['report']['spent']),(5000,5000,0))
        self.bank.transfer_from_savings('family-a',self.child,'withdraw-key',2000,DAY)
        self.assertEqual((self.state()['wallet'],self.state()['vault']),(7000,3000))
        self.assertEqual(self.parent()['balance'],490000)
        self.consistent()
    def test_child_and_family_account_isolation(self):
        self.pay();other_before=self.state(self.other)
        self.bank.simulate_purchase('family-a',self.child,'purchase-key','문구점',4000,DAY)
        self.assertEqual(self.state(self.other),other_before)
        with self.assertRaises(PermissionError):self.bank.get_accounts('family-b',self.child)
        account=self.bank.get_accounts('family-a',self.other)[0]['id']
        with self.assertRaises(PermissionError):self.bank.get_transactions('family-a',account,self.child)
        with self.assertRaises(PermissionError):self.bank.get_account_balance('family-b',self.parent()['id'])
        self.consistent()
    def test_cancellation_is_opposite_posting_and_preserves_original(self):
        self.pay();self.bank.simulate_purchase('family-a',self.child,'purchase-key','문구점',4000,DAY)
        transaction=next(t for t in self.state()['transactions'] if t['kind']=='expense')
        self.bank.change_category('family-a',self.child,transaction['id'],'선물')
        self.db.cancel_expense('family-a',self.child,transaction['id'],'잘못 입력',DAY)
        self.assertEqual(self.state()['wallet'],10000)
        self.assertEqual(self.parent()['balance'],490000)
        self.assertEqual(self.state()['banking']['transactions'][0]['transaction_type'],'PURCHASE_REVERSAL')
        self.assertTrue(any(t['id']==transaction['id'] for t in self.state()['transactions']))
        category_items=[t for t in self.state()['banking']['transactions'] if t['category']=='선물']
        self.assertEqual(sum(t['amount'] for t in category_items),0)
        self.consistent()
    def test_concurrent_transfer_debits_parent_once(self):
        def pay(i):
            try:self.pay('pay-key-'+str(i));return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(pay,range(4)))
        self.assertEqual(sum(results),1)
        self.assertEqual(self.parent()['balance'],490000)
        self.consistent()
    def test_concurrent_siblings_cannot_overdraw_shared_parent(self):
        for child in (self.child,self.other):self.db.save_child('family-a',PROFILE,POLICY|{'amount':400000},child)
        def pay(child):
            try:self.pay('sibling-'+child,child);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(pay,[self.child,self.other]))
        self.assertEqual(sum(results),1)
        self.assertEqual(self.parent()['balance'],100000)
        self.assertEqual(self.state()['wallet']+self.state(self.other)['wallet'],400000)
        self.assertEqual(len(self.state()['cycles'])+len(self.state(self.other)['cycles']),1)
        self.consistent()
    def test_legacy_migration_preserves_rows_and_does_not_debit_parent(self):
        path=os.path.join(self.tmp.name,'legacy.sqlite3')
        with sqlite3.connect(path) as db:
            db.executescript('''CREATE TABLE children(id TEXT PRIMARY KEY,family TEXT,profile TEXT,policy TEXT,status TEXT);
              CREATE TABLE transactions(id TEXT PRIMARY KEY,child TEXT,cycle TEXT,kind TEXT,wallet INTEGER,vault INTEGER,eligible_delta INTEGER,category TEXT,note TEXT,created TEXT,request_key TEXT,UNIQUE(child,request_key));''')
            import json
            db.execute('INSERT INTO children VALUES(?,?,?,?,?)',('old-child','old-family',json.dumps(PROFILE),json.dumps(POLICY),'active'))
            rows=[('old-pay','old-child',None,'payment',10000,0,0,'','旧 기록','2026-10-01','old-pay-key'),('old-expense','old-child',None,'expense',-4000,0,0,'문구','문구점','2026-10-02','old-expense-key'),('old-save','old-child',None,'deposit',-1000,1000,0,'','','2026-10-03','old-save-key')]
            db.executemany('INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,?)',rows)
        db.close()
        migrated=Ledger(path); bank=MockBankingAdapter(migrated)
        self.assertEqual((migrated.state('old-family','old-child')['wallet'],migrated.state('old-family','old-child')['vault']),(5000,1000))
        self.assertEqual(next(a for a in bank.get_accounts('old-family') if a['kind']=='parent')['balance'],500000)
        with migrated.db() as db:self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM transactions ORDER BY rowid')],rows)
        before=migrated.state('old-family','old-child')
        Ledger(path)
        self.assertEqual(migrated.state('old-family','old-child'),before)
        self.assertTrue(all(t['legacy']==1 for t in before['banking']['transactions']))
        bank.transfer_allowance('old-family','old-child','post-migration-pay',DAY)
        after=migrated.state('old-family','old-child',DAY)
        self.assertEqual((after['wallet'],after['vault']),(15000,1000))
        self.assertEqual(next(a for a in bank.get_accounts('old-family') if a['kind']=='parent')['balance'],490000)
        self.assertEqual(after['banking']['transactions'][0]['legacy'],0)


class DemoTests(Setup, unittest.TestCase):
    def test_seed_and_reset_archive_only_demo_family(self):
        original=self.db.children('family-a'); original_state=self.state()
        demo=DemoWorkspaces(self.db); first=demo.create('family-a',self.parent_token,DAY)
        self.assertEqual(self.db.children('family-a'),original)
        self.assertEqual(self.state(),original_state)
        kids=self.db.children(first['demo_id'])
        self.assertEqual([c['profile']['name'] for c in kids],['재현','서연'])
        self.assertEqual([c['policy']['rate_bps'] for c in kids],[1000,500])
        self.bank.transfer_allowance(first['demo_id'],kids[0]['id'],'demo-pay',DAY)
        second=demo.create(first['demo_id'],first['token'],DAY,reset=True)
        self.assertNotEqual(first['demo_id'],second['demo_id'])
        self.assertEqual(self.db.state(first['demo_id'],kids[0]['id'])['wallet'],10000)
        self.assertEqual(self.parent(second['demo_id'])['balance'],500000)
        self.assertEqual(self.db.children('family-a'),original)
        with self.assertRaises(PermissionError):demo.resolve('family-a',first['demo_id'])
        with self.assertRaises(PermissionError):demo.resolve('family-b',second['demo_id'])
        self.consistent()
    def test_virtual_date_isolated_and_timestamp_uses_demo_day(self):
        demo=DemoWorkspaces(self.db);d=demo.create('family-a',self.parent_token,DAY);family=d['demo_id']
        kid=self.db.children(family)[0]['id'];self.bank.transfer_allowance(family,kid,'demo-pay',DAY)
        demo.advance(family,date(2026,10,22))
        self.assertEqual(demo.business_date('family-a',DAY),DAY)
        self.assertEqual(demo.business_date(family,DAY),date(2026,10,22))
        s=self.db.state(family,kid,date(2026,10,22));self.assertTrue(s['cycles'][0]['ended'])
        self.bank.settle_reward_interest(family,kid,'demo-interest',s['cycles'][0]['id'],date(2026,10,22))
        self.assertTrue(self.db.state(family,kid)['banking']['transactions'][0]['occurred_at'].startswith('2026-10-22'))
        with self.assertRaises(PermissionError):demo.advance('family-a',date(2026,10,22))
        with self.assertRaises(ValueError):demo.advance(family,DAY)
        with self.assertRaises(PermissionError):demo.create('family-a',self.db.unlock('family-a','123456'),DAY,reset=True)
        self.consistent()


class BankingAPITests(Setup, unittest.TestCase):
    def setUp(self):
        super().setUp();app=FastAPI();app.include_router(moneyon.router)
        app.dependency_overrides[moneyon.ledger]=lambda:self.db
        def identity(request:Request):
            workspace=request.headers.get('x-moneyon-demo')
            try:return DemoWorkspaces(self.db).resolve('family-a',workspace) if workspace else 'family-a'
            except PermissionError as e:raise HTTPException(403,str(e))
        app.dependency_overrides[moneyon.identity]=identity
        self.client=TestClient(app);self.headers={'X-Moneyon-Session':self.parent_token}
    def test_child_cannot_read_parent_banking_or_demo_tools(self):
        token=self.db.child_session('family-a',self.parent_token,self.child);h={'X-Moneyon-Session':token}
        for path in ['/banking','/demo/start','/demo/reset']:
            r=self.client.get('/api/moneyon'+path,headers=h) if path=='/banking' else self.client.post('/api/moneyon'+path,headers=h,json={})
            self.assertEqual(r.status_code,403)
        s=self.client.get('/api/moneyon/children/'+self.child,headers=h).json()
        self.assertEqual({a['kind'] for a in s['banking']['accounts']},{'wallet','vault'})
    def test_demo_environment_gate_and_original_workspace_reset_rejected(self):
        with patch.dict(os.environ,{'MONEYON_DEMO':'0'}):self.assertEqual(self.client.post('/api/moneyon/demo/start',headers=self.headers,json={}).status_code,403)
        with patch.dict(os.environ,{'MONEYON_DEMO':'1'}):self.assertEqual(self.client.post('/api/moneyon/demo/reset',headers=self.headers,json={}).status_code,403)
        with patch.dict(os.environ,{'MONEYON_DEMO':'1','APP_ENV':'production'}):self.assertEqual(self.client.post('/api/moneyon/demo/start',headers=self.headers,json={}).status_code,403)
    def test_demo_start_date_and_reauthentication_flow(self):
        with patch.dict(os.environ,{'MONEYON_DEMO':'1'}),patch.object(moneyon,'today',return_value=DAY):
            d=self.client.post('/api/moneyon/demo/start',headers=self.headers,json={}).json()
            h={'X-Moneyon-Session':d['token'],'X-Moneyon-Demo':d['demo_id']}
            r=self.client.post('/api/moneyon/demo/date',headers=h,json={'date':'2026-10-22'})
            self.assertEqual(r.status_code,200)
            self.assertEqual(self.client.get('/api/moneyon/banking',headers=h).json()['business_date'],'2026-10-22')
            self.assertEqual(self.client.get('/api/moneyon/children',headers={'X-Moneyon-Session':d['token']}).status_code,403)
            pin=self.client.post('/api/moneyon/unlock',headers={'X-Moneyon-Demo':d['demo_id']},json={'pin':'123456'})
            self.assertEqual(pin.status_code,200)
    def test_purchase_api_and_category_edit_do_not_create_second_expense(self):
        with patch.object(moneyon,'today',return_value=DAY):
            url='/api/moneyon/children/'+self.child
            self.assertEqual(self.client.post(url+'/transactions',headers=self.headers,json={'kind':'payment','key':'api-payment'}).status_code,200)
            r=self.client.post(url+'/transactions',headers=self.headers,json={'kind':'expense','merchant':'문구점','amount':4000,'key':'api-purchase'})
            self.assertEqual(r.status_code,200);s=r.json();self.assertEqual(s['wallet'],6000)
            tid=next(t['id'] for t in s['transactions'] if t['kind']=='expense')
            r=self.client.patch(url+'/transactions/'+tid+'/category',headers=self.headers,json={'category':'선물'})
            self.assertEqual(r.status_code,200);self.assertEqual(r.json()['wallet'],6000)
            self.assertEqual(sum(t['kind']=='expense' for t in r.json()['transactions']),1)
    def test_real_identity_checks_demo_owner_and_missing_login(self):
        token=self.db.unlock('member:owner','123456')
        d=DemoWorkspaces(self.db).create('member:owner',token,DAY)
        request=Request({'type':'http','headers':[(b'x-moneyon-demo',d['demo_id'].encode())]})
        with patch.dict(os.environ,{'MONEYON_DEMO':'1','APP_ENV':'development'}),patch.object(moneyon,'ledger',return_value=self.db):
            with patch.object(moneyon.access,'identify',return_value=None):
                with self.assertRaises(HTTPException) as e:moneyon.identity(request)
                self.assertEqual(e.exception.status_code,401)
            with patch.object(moneyon.access,'identify',return_value={'role':'member','id':'stranger'}):
                with self.assertRaises(HTTPException) as e:moneyon.identity(request)
                self.assertEqual(e.exception.status_code,403)
            with patch.object(moneyon.access,'identify',return_value={'role':'member','id':'owner'}):
                self.assertEqual(moneyon.identity(request),d['demo_id'])


if __name__=='__main__':unittest.main()
