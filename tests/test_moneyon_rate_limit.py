"""Space request limits: starts per peer, writes per accepted trial, unknown tokens per peer."""
import hashlib
import importlib.util
import tempfile
import time
import unittest
from collections import deque
from pathlib import Path

from fastapi.testclient import TestClient
from api.moneyon_trial import trials
from services.moneyon_trial import TrialLedger, Trials

ROOT=Path(__file__).resolve().parents[1]


def load_app():
    spec=importlib.util.spec_from_file_location('moneyon_standalone_limits',ROOT/'deploy/moneyon/space_app.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RateLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.module=load_app()
        self.service=Trials(TrialLedger(Path(self.tmp.name)/'trial.db'))
        self.module.app.dependency_overrides[trials]=lambda:self.service
        self.client=TestClient(self.module.app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def fill(self,key,count):
        with self.module.lock:
            self.module.windows[key]=deque([time.monotonic()]*count)

    def trial(self):
        created=self.client.post('/api/moneyon/trial/start').json()
        self.version=str(created['generation'])
        return created['token'],created['child']['id']

    def allowance(self,token,child,key):
        return self.client.post(f'/api/moneyon/trial/children/{child}/allowance',headers={'X-Moneyon-Trial':token,'X-Moneyon-Trial-Version':self.version},json={'amount':1000,'key':key})

    def digest(self,token):return hashlib.sha256(token.encode()).hexdigest()

    def test_limits_are_300_starts_600_peer_writes_300_trial_writes(self):
        self.assertEqual((self.module.START_LIMIT,self.module.WRITE_LIMIT,self.module.TRIAL_LIMIT),(300,600,300))

    def test_start_allows_300_per_minute_per_peer(self):
        self.fill(('testclient','start'),299)
        self.assertEqual(self.client.post('/api/moneyon/trial/start').status_code,200)
        self.assertEqual(self.client.post('/api/moneyon/trial/start').status_code,429)

    def test_accepted_trial_writes_use_their_own_bucket(self):
        token,child=self.trial()
        self.assertEqual(self.client.get('/api/moneyon/trial/state',headers={'X-Moneyon-Trial':token}).status_code,200)
        # Everyone else behind the same peer used up the peer quota; this visitor still works.
        self.fill(('testclient','write'),600)
        self.assertEqual(self.allowance(token,child,'allowance-own-1').status_code,200)
        self.assertEqual(self.client.post('/api/moneyon/trial/reset',json={'key':'no-token-1'}).status_code,429)

    def test_each_trial_gets_300_writes_per_minute(self):
        token,child=self.trial()
        other,other_child=self.trial()
        for t in (token,other):
            self.assertEqual(self.client.get('/api/moneyon/trial/state',headers={'X-Moneyon-Trial':t}).status_code,200)
        self.fill(('trial',self.digest(token)),299)
        self.assertEqual(self.allowance(token,child,'allowance-cap-1').status_code,200)
        response=self.allowance(token,child,'allowance-cap-2')
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.headers['Retry-After'],'60')
        self.assertEqual(self.allowance(other,other_child,'allowance-other-1').status_code,200)

    def test_invented_tokens_stay_on_the_peer_limit(self):
        self.fill(('testclient','write'),600)
        for i in range(5):
            response=self.client.post('/api/moneyon/trial/children/x/allowance',headers={'X-Moneyon-Trial':f'invented-{i}'},json={'amount':1000,'key':f'invented-key-{i}'})
            self.assertEqual(response.status_code,429)
        with self.module.lock:
            self.assertFalse(any(k[0]=='trial' for k in self.module.windows))

    def test_rejected_tokens_never_become_trusted(self):
        for i in range(3):
            response=self.client.get('/api/moneyon/trial/state',headers={'X-Moneyon-Trial':f'wrong-token-{i}'})
            self.assertEqual(response.status_code,403)
        self.assertEqual(len(self.module.verified),0)
        self.assertEqual(self.client.post('/api/moneyon/trial/children/x/allowance',headers={'X-Moneyon-Trial':'wrong-token-0'},json={'amount':1000,'key':'wrong-key-1'}).status_code,403)
        with self.module.lock:
            self.assertEqual(len(self.module.windows[('testclient','write')]),1)

    def test_expired_trial_falls_back_to_peer_limit(self):
        token,child=self.trial()
        self.assertEqual(self.client.get('/api/moneyon/trial/state',headers={'X-Moneyon-Trial':token}).status_code,200)
        self.assertIn(self.digest(token),self.module.verified)
        with self.service.ledger.db() as db:
            db.execute('UPDATE trial_visitors SET expires=0')
        self.assertEqual(self.allowance(token,child,'allowance-expired-1').status_code,403)
        self.assertNotIn(self.digest(token),self.module.verified)
        self.fill(('testclient','write'),600)
        self.assertEqual(self.allowance(token,child,'allowance-expired-2').status_code,429)

    def test_forwarded_for_does_not_pick_the_bucket(self):
        self.fill(('testclient','write'),600)
        response=self.client.post('/api/moneyon/trial/reset',headers={'X-Forwarded-For':'203.0.113.9'},json={'key':'forwarded-1'})
        self.assertEqual(response.status_code,429)


if __name__=='__main__':
    unittest.main()
