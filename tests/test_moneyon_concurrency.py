"""Trial Space stability: WAL, indexes, pre-seeded pool, cleanup and friendly server errors."""
import importlib.util
import os
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import moneyon_trial as api
from services.moneyon_trial import INDEXES, POOL, TrialLedger, Trials

ROOT = Path(__file__).resolve().parents[1]


def tables(db):
    return [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]


class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'trial.db')
        self.ledger = TrialLedger(self.path)
        self.trials = Trials(self.ledger)
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[api.trials] = lambda: self.trials
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def rows(self, family):
        """Every row anywhere in the database that belongs to one workspace."""
        with self.ledger.db() as db:
            child = db.execute('SELECT id FROM children WHERE family=?', (family,)).fetchone()
            child = child[0] if child else '-'
            total = 0
            for table in tables(db):
                columns = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
                for column, value in (('family', family), ('child', child)):
                    if column in columns:
                        total += db.execute(f'SELECT COUNT(*) FROM {table} WHERE {column}=?', (value,)).fetchone()[0]
            return total

    def test_wal_and_indexes_on_new_and_existing_database(self):
        db = sqlite3.connect(self.path)
        try:
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            plans = [' '.join(r[3] for r in db.execute('EXPLAIN QUERY PLAN ' + q, ('x',))) for q in (
                'SELECT * FROM transactions WHERE cycle=?', 'SELECT * FROM bank_accounts WHERE child=?',
                'SELECT * FROM moneyon_book_entries WHERE book=?', 'SELECT * FROM goals WHERE child=?',
                'SELECT * FROM bank_events WHERE family=?')]
        finally:
            db.close()
        for statement in INDEXES:
            self.assertIn(statement.split()[5], names)
        self.assertFalse([p for p in plans if p.startswith('SCAN')], plans)
        # Re-opening an existing file keeps data and does not fail on existing indexes/column.
        token = self.trials.start()['token']
        again = Trials(TrialLedger(self.path))
        self.assertEqual(again.snapshot(again.resolve(token))['state']['wallet'], 28500)

    def test_pool_claim_is_identical_to_fresh_seed(self):
        fresh = self.trials.start()
        self.assertTrue(self.trials.refill(2))
        self.assertTrue(self.trials.refill(2))
        self.assertFalse(self.trials.refill(2))
        claimed = self.trials.start()
        self.assertEqual(self.trials.pooled(), 1)
        keep = ('wallet', 'vault')
        self.assertEqual({k: claimed['state'][k] for k in keep}, {k: fresh['state'][k] for k in keep})
        self.assertEqual(claimed['state']['rewards']['estimates'], fresh['state']['rewards']['estimates'])
        self.assertEqual(claimed['state']['education']['parent_balance'], fresh['state']['education']['parent_balance'])
        self.assertEqual(claimed['day'], fresh['day'])
        # Keys embed per-seed cycle UUIDs; the sequence of seeded entries must match.
        shape = lambda s: [(t['request_key'].split(':')[0], t['kind'], t['wallet'], t['vault'], t['created'][:10]) for t in s['state']['transactions']]
        self.assertEqual(shape(claimed), shape(fresh))
        with self.ledger.db() as db:
            owner = db.execute('SELECT owner FROM moneyon_demo_workspaces WHERE family=?',
                               (self.trials.resolve(claimed['token'])['family'],)).fetchone()[0]
        self.assertEqual(owner, Trials.digest(claimed['token']))

    def test_concurrent_starts_never_share_a_pooled_workspace(self):
        for _ in range(6):
            self.trials.refill(6)
        with ThreadPoolExecutor(10) as pool:
            started = list(pool.map(lambda _: self.trials.start(), range(10)))
        families = {self.trials.resolve(s['token'])['family'] for s in started}
        self.assertEqual(len(families), 10)
        self.assertEqual(self.trials.pooled(), 0)
        self.assertTrue(all(s['state']['wallet'] == 28500 for s in started))

    def test_reset_uses_pool_and_cleanup_removes_archived_workspace(self):
        first = self.trials.start()
        old_family = self.trials.resolve(first['token'])['family']
        self.trials.refill(1)
        reset = self.trials.reset(first['token'], 1, 'reset-key-123')
        self.assertEqual((reset['state']['wallet'], reset['generation'], self.trials.pooled()), (28500, 2, 0))
        new_family = self.trials.resolve(first['token'])['family']
        with self.ledger.db() as db:
            db.execute('UPDATE trial_visitors SET expires=0')
        self.assertEqual(self.trials.cleanup(), 1)
        self.assertEqual((self.rows(old_family), self.rows(new_family)), (0, 0))

    def test_cleanup_only_removes_expired_and_keeps_active(self):
        active = self.trials.start(cleanup=0)
        expired = self.trials.start(cleanup=0)
        self.trials.refill(1)
        gone = self.trials.resolve(expired['token'])['family']
        with self.ledger.db() as db:
            db.execute('UPDATE trial_visitors SET expires=? WHERE capability=?', (int(time.time()) - 1, Trials.digest(expired['token'])))
            postings = db.execute('SELECT COUNT(*) FROM bank_postings').fetchone()[0]
        self.assertGreater(self.rows(gone), 0)
        self.assertEqual(self.trials.cleanup(), 1)
        self.assertEqual(self.rows(gone), 0)
        with self.ledger.db() as db:
            self.assertLess(db.execute('SELECT COUNT(*) FROM bank_postings').fetchone()[0], postings)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM families WHERE id=?', (gone,)).fetchone()[0], 0)
        self.assertEqual(self.trials.snapshot(self.trials.resolve(active['token']))['state']['wallet'], 28500)
        self.assertEqual(self.trials.pooled(), 1)
        self.assertEqual(self.client.get('/api/moneyon/trial/state', headers={'X-Moneyon-Trial': expired['token']}).status_code, 403)

    def test_cap_only_removes_idle_visitors(self):
        now = int(time.time())
        started = [self.trials.start(cleanup=0) for _ in range(4)]
        digests = [Trials.digest(s['token']) for s in started]
        with self.ledger.db() as db:
            db.execute('UPDATE trial_visitors SET last_seen=? WHERE capability IN (?,?)', (now - 10000, digests[0], digests[1]))
        # Keep 1: only the two idle visitors may go, the two recently seen ones stay over the cap.
        self.assertEqual(self.trials.cleanup(keep=1), 2)
        self.assertEqual(self.client.get('/api/moneyon/trial/state', headers={'X-Moneyon-Trial': started[0]['token']}).status_code, 403)
        for s in started[2:]:
            self.assertEqual(self.client.get('/api/moneyon/trial/state', headers={'X-Moneyon-Trial': s['token']}).status_code, 200)

    def test_database_lock_is_a_friendly_503(self):
        with patch.object(Trials, 'start', side_effect=sqlite3.OperationalError('database is locked')):
            response = self.client.post('/api/moneyon/trial/start')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['Retry-After'], '5')
        self.assertIn('잠시 후', response.json()['detail'])
        token = self.trials.start()['token']
        with patch.object(Trials, 'snapshot', side_effect=sqlite3.OperationalError('database is locked')):
            response = self.client.get('/api/moneyon/trial/state', headers={'X-Moneyon-Trial': token})
        self.assertEqual(response.status_code, 503)


class SpaceErrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        spec = importlib.util.spec_from_file_location('moneyon_space_errors', ROOT / 'deploy/moneyon/space_app.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.service = Trials(TrialLedger(Path(self.tmp.name) / 'trial.db'))
        self.module.app.dependency_overrides[api.trials] = lambda: self.service
        self.client = TestClient(self.module.app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_unexpected_error_is_korean_json_without_traceback(self):
        with patch.object(Trials, 'start', side_effect=RuntimeError('secret internal detail')):
            response = self.client.post('/api/moneyon/trial/start')
        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.headers['content-type'].startswith('application/json'))
        self.assertNotIn('secret', response.text)
        self.assertIn('잠시 후', response.json()['detail'])

    def test_maintenance_refills_and_cleans_only_when_idle(self):
        self.module.POOL_TARGET = 2
        with patch.object(self.module, 'trials', lambda: self.service):
            self.module.last_request[0] = time.monotonic() + 3600  # busy: must not seed
            stop = self.module.Event()
            worker = self.module.Thread(target=self.module.maintain, args=(stop,), daemon=True)
            worker.start()
            time.sleep(0.6)
            self.assertEqual(self.service.pooled(), 0)
            self.module.last_request[0] = 0.0
            deadline = time.monotonic() + 15
            while self.service.pooled() < 2 and time.monotonic() < deadline:
                time.sleep(0.1)
            stop.set()
            worker.join(5)
        self.assertEqual(self.service.pooled(), 2)
        self.assertEqual(self.client.get('/api/health').json()['ok'], True)


if __name__ == '__main__':
    unittest.main()
