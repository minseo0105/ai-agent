"""Admin ZIP dashboard authorization and read-only failure isolation."""
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import zipon_data as api
from api import usage_dashboard as auth
from services import access


def token(role='admin'):
    with patch.object(access,'_secret_key',return_value=b'test-only-secret'):
        return access._sign({'r':role,'exp':time.time()+600})


class DashboardTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(api.router);self.client=TestClient(app)

    def test_public_member_and_forged_tokens_never_query_database(self):
        with patch.object(auth,'readonly_signing_key',AsyncMock(return_value=b'test-only-secret')),patch.object(api,'read_json',AsyncMock()) as read:
            for bearer in (None,token('member'),token()+'forged'):
                response=self.client.get('/api/admin/zipon-data',headers={'Authorization':'Bearer '+bearer} if bearer else {})
                self.assertEqual(response.status_code,401)
            read.assert_not_called()

    def test_admin_uses_zip_only_read_and_no_store(self):
        config=lambda name,**kwargs:'https://zip.example' if name.endswith('URL') else 'test-server-key'
        with patch.object(auth,'readonly_signing_key',AsyncMock(return_value=b'test-only-secret')),patch.object(api,'get_secret',side_effect=config),patch.object(api,'read_json',AsyncMock(return_value={'total':123})) as read:
            response=self.client.get('/api/admin/zipon-data',headers={'Authorization':'Bearer '+token()})
            self.assertEqual(response.status_code,200)
            self.assertIn('no-store',response.headers['cache-control'])
            self.assertEqual(read.call_args.args[0],'https://zip.example/rest/v1/rpc/zipon_refresh_dashboard')
            self.assertNotIn('test-server-key',response.text)
            self.assertEqual(self.client.post('/api/admin/zipon-data').status_code,405)

    def test_missing_config_or_db_failure_is_not_zero_success(self):
        with patch.object(auth,'readonly_signing_key',AsyncMock(return_value=b'test-only-secret')),patch.object(api,'get_secret',return_value=''):
            self.assertEqual(self.client.get('/api/admin/zipon-data',headers={'Authorization':'Bearer '+token()}).status_code,503)
        with patch.object(auth,'readonly_signing_key',AsyncMock(return_value=b'test-only-secret')),patch.object(api,'get_secret',return_value='test-only'),patch.object(api,'read_json',AsyncMock(side_effect=RuntimeError('credential-secret'))):
            response=self.client.get('/api/admin/zipon-data',headers={'Authorization':'Bearer '+token()})
            self.assertEqual(response.status_code,503);self.assertNotIn('credential-secret',response.text)


if __name__=='__main__':unittest.main()
