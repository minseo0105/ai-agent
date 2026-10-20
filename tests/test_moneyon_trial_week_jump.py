"""Existing trial date endpoint: same-target retries, concurrent jumps and frozen weeks."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from tests import test_moneyon_trial as base


class WeekJumpTests(unittest.TestCase):
    setUp=base.TrialTests.setUp
    tearDown=base.TrialTests.tearDown
    get=base.TrialTests.get
    post=base.TrialTests.post

    def test_same_target_retry_does_not_duplicate_closing(self):
        self.assertEqual(self.post('/date',{'day':'2026-10-19'}).status_code,200)
        before=self.get()
        self.assertEqual(self.post('/date',{'day':'2026-10-19'}).status_code,200)
        self.assertEqual(self.get(),before)
        with self.ledger.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trial_closings').fetchone()[0],2)

    def test_concurrent_same_target_is_one_week_only(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.post('/date',{'day':'2026-10-19'}).status_code,range(2)))
        self.assertEqual(results,[200,200])
        self.assertEqual(self.get()['day'],'2026-10-19')
        with self.ledger.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM trial_closings').fetchone()[0],2)
            self.assertFalse(db.execute('SELECT child,start FROM cycles GROUP BY child,start HAVING COUNT(*)>1').fetchall())

    def test_two_weeks_preserve_paid_week_and_reset(self):
        self.post('/date',{'day':'2026-10-19'})
        cycle=next(i['cycle_id'] for i in self.get()['state']['rewards']['items'] if i['status']=='awaiting_approval')
        self.assertEqual(self.post('/approve',dict(cycle_id=cycle,approved=True,key='jump-both-rewards')).status_code,200)
        before=[i for i in self.get()['state']['rewards']['items'] if i['cycle_id']==cycle]
        self.post('/date',{'day':'2026-10-26'})
        after=[i for i in self.get()['state']['rewards']['items'] if i['cycle_id']==cycle]
        self.assertEqual(before,after)
        self.assertEqual(self.post('/approve',dict(cycle_id=cycle,approved=True,key='jump-duplicate-paid')).status_code,409)
        reset=self.client.post(self.base+'/reset',json={'key':'jump-reset-initial'},headers=self.headers).json()
        self.assertEqual(reset['day'],'2026-10-12')
        self.assertEqual(reset['state']['rewards']['estimates']['allowance_bonus'],2850)

    def test_trial_day_is_not_session_clock_and_experiment_is_readonly(self):
        before=self.get()
        result=self.post('/experiment',{'spend':100}).json()
        self.assertEqual(result['interest'],2840)
        self.assertEqual(self.get(),before)
        self.post('/date',{'day':'2026-10-19'})
        self.assertEqual(self.get()['expires'],before['expires'])
        other=self.client.post(self.base+'/start').json()
        self.assertEqual(other['day'],'2026-10-12')
        self.assertEqual(self.get()['day'],'2026-10-19')
