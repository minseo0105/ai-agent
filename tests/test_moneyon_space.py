"""Standalone deployment boundary, source bundle and ephemeral restart policy."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from api.moneyon_trial import trials
from services.moneyon_trial import TrialLedger, Trials
from scripts.prepare_moneyon_space import prepare
from scripts.deploy_moneyon_space import validate

ROOT=Path(__file__).resolve().parents[1]


def load_app():
    spec=importlib.util.spec_from_file_location('moneyon_standalone',ROOT/'deploy/moneyon/space_app.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SpaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)
        self.module=load_app()
        self.service=Trials(TrialLedger(self.path/'trial.db'))
        self.module.app.dependency_overrides[trials]=lambda:self.service
        self.client=TestClient(self.module.app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def start(self):return self.client.post('/api/moneyon/trial/start')

    def test_sample_without_pin(self):
        response=self.start()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['state']['wallet'],28500)
        self.assertEqual(response.json()['state']['vault'],15000)

    def test_real_and_other_services_unreachable(self):
        for url in ('/api/moneyon/unlock','/api/moneyon/children','/api/admin/settings','/api/access/login','/api/realestate','/api/report','/api/banking'):
            for method in ('get','post'):
                self.assertEqual(getattr(self.client,method)(url).status_code,404,url)

    def test_no_api_documentation_or_files(self):
        for path in ('/docs','/redoc','/openapi.json','/runtime/trial.sqlite3','/.env','/services/config.py'):
            self.assertEqual(self.client.get(path).status_code,404,path)

    def test_only_exact_bee_asset_is_served(self):
        from fastapi import FastAPI
        folder=self.path/'static'
        assets=folder/'moneyon'/'characters'
        assets.mkdir(parents=True)
        png=(ROOT/'web/public/moneyon/characters/izani-bee.png').read_bytes()
        (assets/'izani-bee.png').write_bytes(png)
        (assets/'private.jpg').write_bytes(b'not public')
        app=FastAPI()
        app.mount('/',self.module.ExportedSite(directory=str(folder)))
        with TestClient(app) as client:
            response=client.get('/moneyon/characters/izani-bee.png')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.content,png)
            self.assertIn('image/png',response.headers['content-type'])
            self.assertEqual(client.get('/moneyon/characters/private.jpg').status_code,404)

    def test_cross_origin_mutations_rejected(self):
        self.assertEqual(self.client.post('/api/moneyon/trial/start',headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/moneyon/trial/start',headers={'Origin':'http://testserver'}).status_code,200)

    def test_cors_is_not_enabled_for_other_origins(self):
        response=self.client.options('/api/moneyon/trial/start',headers={'Origin':'https://evil.example','Access-Control-Request-Method':'POST'})
        self.assertNotIn('access-control-allow-origin',response.headers)

    def test_https_origin_behind_hf_tls_proxy(self):
        self.assertEqual(self.client.post('/api/moneyon/trial/start',headers={'Origin':'https://testserver'}).status_code,200)
        self.assertEqual(self.client.post('/api/moneyon/trial/start',headers={'Origin':'https://elsewhere','X-Forwarded-Host':'elsewhere'}).status_code,403)

    def test_body_size_and_security_headers(self):
        self.assertEqual(self.client.post('/api/moneyon/trial/start',content=b'x'*17000).status_code,413)
        response=self.start()
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(response.headers['Referrer-Policy'],'same-origin')

    def test_health_has_no_keys_or_providers(self):
        response=self.client.get('/api/health')
        self.assertEqual(response.json(),{'ok':True,'service':'moneyon-trial','storage':'ephemeral','family_api':False})

    def test_limiter_is_bounded_and_does_not_trust_forwarded_ip(self):
        with self.module.lock:
            from collections import deque
            import time
            self.module.windows[('testclient','start')]=deque([time.monotonic()]*60)
        response=self.client.post('/api/moneyon/trial/start',headers={'X-Forwarded-For':'different'})
        self.assertEqual(response.status_code,429)
        self.assertEqual(response.headers['Retry-After'],'60')

    def test_process_restart_same_file_preserves_session(self):
        created=self.start().json()
        service=Trials(TrialLedger(self.path/'trial.db'))
        self.assertEqual(service.snapshot(service.resolve(created['token']))['state']['wallet'],28500)

    def test_container_disk_loss_expires_old_capability(self):
        created=self.start().json()
        new=Trials(TrialLedger(self.path/'new-container.db'))
        with self.assertRaises(PermissionError):new.resolve(created['token'])
        self.assertEqual(new.start()['state']['wallet'],28500)

    def test_bundle_is_source_only_and_manifest_matches(self):
        bundle=self.path/'bundle'
        manifest=prepare(bundle)
        self.assertEqual(validate(bundle)[1],manifest)
        for path in manifest:
            self.assertFalse(any(x in path for x in ('secrets.toml','.env','sqlite3','api/main.py','data/','node_modules','api/realestate.py')))
        self.assertNotIn('web/src/app/moneyon/MoneyOn.tsx',manifest)
        self.assertIn('sdk: docker',(bundle/'README.md').read_text(encoding='utf-8'))

    def test_changed_and_extra_bundle_files_are_rejected(self):
        bundle=self.path/'bundle'
        prepare(bundle)
        (bundle/'secret.env').write_text('not-a-real-secret')
        with self.assertRaises(ValueError):validate(bundle)
        (bundle/'secret.env').unlink()
        (bundle/'Dockerfile').write_text('changed')
        with self.assertRaises(ValueError):validate(bundle)

    def test_existing_bundle_never_overwritten(self):
        prepare(self.path/'bundle')
        with self.assertRaises(ValueError):prepare(self.path/'bundle')

    def test_exported_assets_and_moneyon_route(self):
        from fastapi import FastAPI
        folder=self.path/'static'
        (folder/'_next'/'static').mkdir(parents=True)
        (folder/'_next'/'static'/'test.css').write_text('body{color:green}')
        (folder/'index.html').write_text('landing')
        (folder/'moneyon.html').write_text('moneyon')
        app=FastAPI()
        app.mount('/',self.module.ExportedSite(directory=str(folder),html=True))
        with TestClient(app) as client:
            self.assertEqual(client.get('/').text,'landing')
            self.assertEqual(client.get('/moneyon').text,'moneyon')
            self.assertEqual(client.get('/_next/static/test.css').status_code,200)
            self.assertEqual(client.get('/moneyon.html').status_code,404)


if __name__=='__main__':unittest.main()
