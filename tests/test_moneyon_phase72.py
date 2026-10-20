"""Phase 7.2 additive migration, payment policy, book and payout invariants."""
import unittest
from unittest.mock import patch
from tests import test_moneyon_trial as base
from services import moneyon_savings as savings


class Phase72Tests(unittest.TestCase):
    setUp=base.TrialTests.setUp
    tearDown=base.TrialTests.tearDown
    get=base.TrialTests.get
    post=base.TrialTests.post

    def book(self,name='여행 자금',key='book-travel'):
        result=self.post('/books',dict(name=name,target=100000,icon='✈️',color='mint',nickname='꿈',key=key))
        self.assertEqual(result.status_code,200,result.text)
        return next(b for b in result.json()['books'] if b['request_key']==key)['id']

    def paid(self):
        # 28,500 - 14,200 + 50 is not a permitted ordinary transaction;
        # preserve won-level legacy balance using a historical ledger posting.
        row=self.trials.resolve(self.first['token'])
        with self.ledger.db() as db:
            self.ledger._entry(db,row['child'],None,'expense',-14250,0,0,'legacy-exact-balance',business_date=self.trials.day(row))
        self.assertEqual(self.get()['state']['rewards']['estimates']['allowance_bonus'],1425)
        cycle=next(c['id'] for c in self.get()['state']['cycles'] if not c['ended'])
        self.post('/date',dict(day='2026-10-19'))
        response=self.post('/approve',dict(cycle_id=cycle,reward_type='allowance_bonus',approved=True,key='approve-1425'))
        self.assertEqual(response.status_code,200,response.text)
        return self.get()['state']['payout_choices'][0]

    def test_migration_preserves_transactions_and_is_idempotent(self):
        row=self.trials.resolve(self.first['token'])
        with self.ledger.db() as db:
            before=[tuple(r) for r in db.execute('SELECT * FROM transactions ORDER BY rowid')]
            db.execute('DELETE FROM moneyon_book_entries');db.execute('DELETE FROM moneyon_books')
            for _ in range(3): savings.migrate(db,row['child'])
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM transactions ORDER BY rowid')])
        self.assertEqual(self.get()['state']['books'][0]['balance'],15000)

    def test_books_deposit_withdraw_and_retry(self):
        book=self.book();before=self.get()['state']
        payload=dict(kind='deposit',amount=5000,key='book-deposit',book_id=book)
        self.assertEqual(self.post('/transactions',payload).status_code,200)
        self.assertEqual(self.post('/transactions',payload).status_code,200)
        state=self.get()['state'];self.assertEqual((state['wallet'],state['vault']),(23500,20000))
        self.assertEqual(sum(b['interest'] for b in state['books']),state['rewards']['estimates']['savings_interest'])
        self.assertEqual(next(b['balance'] for b in state['books'] if b['id']==book),5000)
        self.assertEqual(self.post('/transactions',dict(kind='withdraw',amount=5100,key='over-own-book',book_id=book)).status_code,409)
        self.assertEqual(self.post('/transactions',dict(kind='withdraw',amount=1000,key='own-book-withdraw',book_id=book)).status_code,200)
        self.assertEqual(sum(b['balance'] for b in self.get()['state']['books']),19000)

    def test_pending_does_not_block_and_closing_is_frozen(self):
        self.post('/date',dict(day='2026-10-19'))
        closed=[i for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval']
        for kind in ('expense','deposit','withdraw'):
            r=self.post('/transactions',dict(kind=kind,amount=1000,key='pending-'+kind));self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.post('/allowance',dict(amount=1000,key='pending-allowance')).status_code,200)
        self.assertEqual(closed,[i for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval'])

    def test_new_automatic_existing_manual_and_future_optin(self):
        new=self.client.post(self.base+'/start').json()
        self.assertEqual(new['state']['payment_rule']['current'],'automatic')
        self.assertEqual(self.get()['state']['payment_rule']['current'],'manual')
        self.post('/payment-rule',dict(mode='automatic',approved=True))
        self.post('/date',dict(day='2026-10-19'))
        self.assertEqual(len([i for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval']),2)
        self.post('/date',dict(day='2026-10-26'))
        items=self.get()['state']['rewards']['items']
        self.assertEqual(len([i for i in items if i['start']=='2026-10-19' and i['status']=='paid']),2)

    def test_auto_retry_and_insufficient_parent_no_creation(self):
        row=self.trials.resolve(self.first['token'])
        with self.ledger.db() as db:
            db.execute('INSERT INTO moneyon_payment_rules VALUES(?,?,?)',(row['child'],'2026-10-12','automatic'))
        self.post('/date',dict(day='2026-10-19'));state=self.get()['state']
        self.assertEqual(state['wallet'],31350)
        self.post('/date',dict(day='2026-10-19'));self.assertEqual(state['transactions'],self.get()['state']['transactions'])

    def test_insufficient_funds_remains_pending_and_trading_continues(self):
        self.assertEqual(self.post('/allowance',dict(amount=448500,key='use-parent-budget')).status_code,200)
        row=self.trials.resolve(self.first['token'])
        with self.ledger.db() as db:
            db.execute('INSERT INTO moneyon_payment_rules VALUES(?,?,?)',(row['child'],'2026-10-12','automatic'))
        before=self.get()['state']
        self.assertEqual(before['education']['parent_balance'],0)
        self.assertEqual(self.post('/date',dict(day='2026-10-19')).status_code,200)
        after=self.get()['state']
        self.assertEqual((after['wallet'],after['vault']),(before['wallet'],before['vault']))
        self.assertEqual(len([i for i in after['rewards']['items'] if i['status']=='awaiting_approval']),2)
        self.assertEqual(self.post('/transactions',dict(kind='expense',amount=100,key='still-spend-pending')).status_code,200)
        with self.ledger.db() as db:
            self.assertFalse(db.execute('SELECT transfer_id FROM bank_postings GROUP BY transfer_id HAVING SUM(amount)<>0').fetchall())

    def test_auto_multiweek_jump_equals_incremental_boundaries(self):
        new=self.client.post(self.base+'/start').json()
        other=self.trials.resolve(new['token'])
        row=self.trials.resolve(self.first['token'])
        with self.ledger.db() as db:
            db.execute('INSERT INTO moneyon_payment_rules VALUES(?,?,?)',(row['child'],'2026-10-12','automatic'))
        from datetime import date
        self.trials.advance(row,date(2026,10,26))
        self.trials.advance(other,date(2026,10,19));self.trials.advance(other,date(2026,10,26))
        a=self.trials.snapshot(row)['state'];b=self.trials.snapshot(other)['state']
        self.assertEqual((a['wallet'],a['vault']),(b['wallet'],b['vault']))
        self.assertEqual(a['wallet'],34485)

    def test_book_interest_uses_closing_distribution_not_payment_balances(self):
        book=self.book()
        self.post('/transactions',dict(kind='deposit',amount=5000,key='split-principal',book_id=book))
        self.post('/date',dict(day='2026-10-19'))
        self.post('/transactions',dict(kind='withdraw',amount=5000,key='withdraw-after-close',book_id=book))
        cycle=next(i['cycle_id'] for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval')
        self.assertEqual(self.post('/approve',dict(cycle_id=cycle,reward_type='savings_interest',approved=True,key='pay-frozen-books')).status_code,200)
        state=self.get()['state']
        self.assertEqual(next(b['balance'] for b in state['books'] if b['id']==book),100)
        self.assertEqual(sum(b['balance'] for b in state['books']),15400)

    def test_all_exact_partial_keep_duplicate_and_spent(self):
        p=self.paid();book=self.book()
        body=dict(payout=p['payout'],choice='all',amount=1425,book_id=book,key='save-exact-reward')
        self.assertEqual(self.post('/reward-saving',body).status_code,200)
        self.assertEqual(self.post('/reward-saving',body).status_code,200)
        self.assertEqual(self.post('/reward-saving',dict(body,key='save-again-reward')).status_code,409)
        s=self.get()['state'];self.assertEqual(s['wallet'],14250)
        self.assertEqual(next(b['balance'] for b in s['books'] if b['id']==book),1425)
        self.assertEqual(s['education']['spent'],0);self.assertEqual(s['education']['saved'],1425)

    def test_partial_100_and_rollback(self):
        p=self.paid();book=self.book()
        body=dict(payout=p['payout'],choice='partial',amount=1000,book_id=book,key='partial-reward-save')
        before=self.get()['state']
        with patch('services.moneyon_savings.assign',side_effect=ValueError('주입한 실패')):
            self.assertEqual(self.post('/reward-saving',body).status_code,409)
        self.assertEqual(self.get()['state']['transactions'],before['transactions'])
        self.assertEqual(self.post('/reward-saving',dict(body,amount=425)).status_code,409)
        self.assertEqual(self.post('/reward-saving',body).status_code,200)
        self.assertEqual(self.get()['state']['wallet'],14675)

    def test_spending_consumes_entitlement_and_keep(self):
        p=self.paid();self.post('/transactions',dict(kind='expense',amount=100,key='spend-reward-first'))
        self.post('/allowance',dict(amount=1000,key='new-allowance-not-restore'))
        self.assertEqual(self.get()['state']['payout_choices'][0]['available'],1325)
        book=self.book()
        self.assertEqual(self.post('/reward-saving',dict(payout=p['payout'],choice='all',amount=1425,book_id=book,key='spent-cannot-all')).status_code,409)
        self.assertEqual(self.post('/reward-saving',dict(payout=p['payout'],choice='keep',amount=0,key='keep-reward-here')).status_code,200)

    def test_visitor_isolation_and_reset(self):
        other=self.client.post(self.base+'/start').json();book=other['state']['books'][0]['id']
        self.assertEqual(self.post('/transactions',dict(kind='deposit',amount=100,key='foreign-book-no',book_id=book)).status_code,409)
        self.book();r=self.client.post(self.base+'/reset',json=dict(key='reset-phase72'),headers=self.headers)
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['state']['books']),1)
        self.assertEqual((r.json()['state']['wallet'],r.json()['state']['vault']),(28500,15000))


if __name__=='__main__': unittest.main()
