"""No production I/O: authenticated read-only queries and safe aggregate presentation."""
import asyncio
import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import usage_dashboard as api
from services import access
from services import usage_dashboard as usage


def raw(period='today'):
    end = datetime(2026, 10, 3, 3, tzinfo=timezone.utc)
    start = datetime(2026, 10, 2, 15, tzinfo=timezone.utc) - timedelta(days=usage.PERIODS[period] - 1)
    zeros = {k: 0 for k in usage.ServiceCounts.model_fields if k != 'service'}
    return {'status': 'ok', 'start_at': start.isoformat(), 'end_at': end.isoformat(),
            'totals': {'visits': 3, 'page_views': 5, 'features': 4, 'external': 3, 'errors': 1},
            'pages': [{'service': 'realestate', 'route': '/realestate', 'visits': 3, 'page_views': 5, 'features': 4}],
            'services': [{**zeros, 'service': 'realestate', 'visits': 3, 'page_views': 5, 'features': 4,
                          'used_sessions': 2, 'map_clicks': 3, 'project_clicks': 2, 'naver': 2, 'errors': 1,
                          'funnel_entered': 3, 'funnel_searched': 1, 'funnel_engaged': 1, 'funnel_external': 1}],
            'daily': [{'day': '2026-10-03', 'service': 'all', 'visits': 3, 'page_views': 5, 'features': 4}],
            'recent': [{'created_at': end.isoformat(), 'service': 'realestate', 'route': '/realestate',
                        'event_type': 'project_click', 'action': None}]}


def signed(role='admin', expiry=None):
    with patch.object(access, '_secret_key', return_value=b'test-only-secret'):
        return access._sign({'r': role, 'exp': expiry if expiry is not None else time.time() + 600})


class PresentationTests(unittest.TestCase):
    def test_page_labels_counts_and_missing_instrumentation(self):
        data = usage.present_summary(raw(), 'today')
        pages = {p['route']: p for p in data['pages']}
        self.assertEqual(pages['/']['label'], 'AI LAB 홈')
        self.assertEqual(pages['/golf']['label'], 'Golf')
        self.assertEqual(pages['/golf/club']['label'], 'Golf · 골프장 상세')
        self.assertEqual(pages['/realestate']['visits'], 3)
        self.assertEqual(pages['/realestate']['page_views'], 5)
        self.assertEqual(pages['/golf']['features'], 0)
        self.assertEqual(pages['/golf']['feature_status'], 'COLLECTED')
        for route in ('/', '/dreamcar', '/report', '/saju', '/gif', '/car-selector', '/golf/club'):
            self.assertIsNone(pages[route]['features'])
            self.assertEqual(pages[route]['feature_status'], 'NOT_INSTRUMENTED')

    def test_rates_and_funnel_are_different_concepts(self):
        data = usage.present_summary(raw(), 'today')
        zipon = next(s for s in data['services'] if s['service'] == 'realestate')
        self.assertEqual(zipon['feature_rate'], 66.7)
        self.assertEqual(zipon['used_sessions'], 2)
        self.assertEqual(zipon['session_funnel'], [3, 1, 1, 1])
        self.assertEqual(zipon['features'], 4)
        golf = next(s for s in data['services'] if s['service'] == 'golf')
        self.assertIsNone(golf['feature_rate'])
        self.assertEqual(golf['features'], 0)

    def test_unknown_static_routes_are_not_dropped_or_rendered_as_html(self):
        value = raw()
        value['pages'].append({'service': 'other', 'route': '/future-tool', 'visits': 1, 'page_views': 2, 'features': 0})
        value['pages'].append({'service': 'other', 'route': '/<script>?email=private@example.com', 'visits': 1, 'page_views': 1, 'features': 0})
        data = usage.present_summary(value, 'today')
        self.assertTrue(any(p['label'] == '/future-tool' for p in data['pages']))
        self.assertNotIn('<script>', json.dumps(data))
        self.assertNotIn('private@example.com', json.dumps(data))

    def test_all_sensitive_fields_are_projected_out(self):
        value = raw()
        value['session_id'] = 'do-not-return'
        value['recent'][0].update(session_id='do-not-return', metadata={'query': 'private'}, request_id='private', ip='private')
        output = json.dumps(usage.present_summary(value, 'today'))
        for forbidden in ('session_id', 'do-not-return', 'metadata', 'request_id', 'private'):
            self.assertNotIn(forbidden, output)

    def test_activity_labels_use_real_taxonomy(self):
        for service, event, action, expected in [
            ('realestate', 'search', 'address_search', '부동산 검색'),
            ('realestate', 'search', 'trade_search', '부동산 검색'),
            ('golf', 'search', 'golf_search', '골프장 검색'),
            ('realestate', 'map_click', None, '지도에서 개발사업 확인'),
            ('realestate', 'project_click', None, '개발사업 상세 확인'),
            ('realestate', 'external_link_click', 'naver_land_click', '네이버부동산 이동'),
            ('realestate', 'external_link_click', 'official_source_click', '공식 자료 이동'),
        ]:
            row = usage.Activity(created_at=datetime.now(timezone.utc), service=service, route='/', event_type=event, action=action)
            self.assertEqual(usage.activity_label(row), expected)

    def test_kst_days_are_zero_filled_without_recounting_sessions(self):
        for period, days in usage.PERIODS.items():
            data = usage.present_summary(raw(period), period)
            self.assertEqual(data['timezone'], 'Asia/Seoul')
            self.assertEqual(len(data['daily']), days * 3)
            self.assertEqual(data['daily'][-1]['day'], '2026-10-03')
            self.assertEqual(data['totals']['visits'], 3)

    def test_malformed_or_impossible_aggregates_are_not_reported_as_zero(self):
        for mutate in (lambda v: v.pop('totals'), lambda v: v['services'][0].update(used_sessions=4),
                       lambda v: v['services'][0].update(funnel_external=3)):
            value = raw(); mutate(value)
            with self.assertRaises(ValueError): usage.present_summary(value, 'today')


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI(); app.include_router(api.router)
        @app.get('/core')
        def core(): return {'ok': True}
        self.client = TestClient(app)

    def test_public_member_expired_and_forged_tokens_cannot_read_even_cached_data(self):
        with patch.object(api, 'readonly_signing_key', AsyncMock(return_value=b'test-only-secret')), patch.object(api.reader, 'get', AsyncMock()) as get:
            for token in (None, signed('member'), signed(expiry=time.time()-1), signed()+'forged', 'broken'):
                response = self.client.get('/api/admin/usage', headers={'Authorization': 'Bearer '+token} if token else {})
                self.assertEqual(response.status_code, 401)
                self.assertIn('no-store', response.headers['cache-control'])
            get.assert_not_called()

    def test_admin_can_read_and_response_is_never_publicly_cached(self):
        with patch.object(api, 'readonly_signing_key', AsyncMock(return_value=b'test-only-secret')), patch.object(api.reader, 'get', AsyncMock(return_value={'safe': True})) as get:
            response = self.client.get('/api/admin/usage?period=7d', headers={'Authorization': 'Bearer '+signed()})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'safe': True})
            get.assert_awaited_once_with('7d')
            self.assertIn('no-store', response.headers['cache-control'])
            self.assertEqual(response.headers['vary'], 'Authorization')

    def test_failure_is_generic_and_does_not_affect_core(self):
        with patch.object(api, 'readonly_signing_key', AsyncMock(return_value=b'test-only-secret')), patch.object(api.reader, 'get', AsyncMock(side_effect=usage.DashboardUnavailable())):
            response = self.client.get('/api/admin/usage', headers={'Authorization': 'Bearer '+signed()})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('secret', response.text)
            self.assertEqual(self.client.get('/core').json(), {'ok': True})

    def test_no_mutation_endpoint_and_only_supported_periods(self):
        with patch.object(api, 'readonly_signing_key', AsyncMock(return_value=b'test-only-secret')):
            self.assertEqual(self.client.post('/api/admin/usage').status_code, 405)
            self.assertEqual(self.client.get('/api/admin/usage?period=365d', headers={'Authorization': 'Bearer '+signed()}).status_code, 422)


class ReadOnlyTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_auth_secret_never_initializes_settings_or_secret(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(access, '_secret_cache', {'value': None}), \
             patch.object(api, '_key', None), patch.object(api, 'get_secret', return_value=''), \
             patch.object(type(access.SECRET_PATH), 'is_file', return_value=False), \
             patch.object(access, '_remote_put') as put, patch.object(access, '_secret_key') as initialize:
            with self.assertRaises(usage.DashboardUnavailable): await api.readonly_signing_key()
            put.assert_not_called(); initialize.assert_not_called()

    async def test_http_transport_is_read_only_bounded_and_does_not_follow_redirects(self):
        sent=[]
        async def handler(request):
            sent.append(request)
            return httpx.Response(200,json={'ok': True})
        original=httpx.AsyncClient
        with patch.object(usage.httpx, 'AsyncClient', side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)):
            self.assertEqual(await usage.read_json('https://db.invalid/rest/v1/rpc/usage_dashboard', 'sb_secret_test', {'p_days': 1}), {'ok': True})
            with self.assertRaises(usage.DashboardUnavailable):
                await usage.read_json('https://db.invalid', 'sb_secret_test', limit=1)
        self.assertTrue(all(r.method == 'GET' for r in sent))
        self.assertEqual(sent[0].url.params['p_days'],'1')

    async def test_cache_and_auth_read_timeout_cannot_queue_unlimited_queries(self):
        reader=usage.DashboardReader()
        async def slow(*args, **kwargs):
            await asyncio.sleep(0.03); return raw()
        with patch.object(usage, 'get_secret', side_effect=lambda name: 'https://db.invalid' if name=='SUPABASE_URL' else 'sb_secret_test' if name=='SUPABASE_SERVICE_ROLE_KEY' else ''), \
             patch.object(usage, 'read_json', side_effect=slow) as read:
            pending=asyncio.create_task(reader.get('today'))
            await asyncio.sleep(0)
            with self.assertRaises(usage.DashboardUnavailable): await reader.get('today')
            first=await pending
            self.assertEqual(await reader.get('today'), first)
            self.assertEqual(read.call_count, 1)

            # Even a fresh monotonic cache entry must expire across KST midnight.
            stamp, day, value = reader.cache['today']
            reader.cache['today'] = (stamp, day - usage.timedelta(days=1), value)
            await reader.get('today')
            self.assertEqual(read.call_count, 2)

    async def test_db_failure_missing_function_and_timeout_never_become_zero(self):
        for failure in (TimeoutError('private'), RuntimeError('private'), usage.DashboardUnavailable('setup_required')):
            reader=usage.DashboardReader()
            with patch.object(usage, 'get_secret', return_value='test'), patch.object(usage, 'read_json', side_effect=failure) as read:
                for _ in range(2):
                    with self.assertRaises(usage.DashboardUnavailable) as result: await reader.get('today')
                    self.assertNotIn('private', str(result.exception))
                self.assertEqual(read.call_count, 1)
                self.assertEqual(reader.cache,{})

    async def test_large_period_is_explicitly_unavailable(self):
        with patch.object(usage, 'get_secret', return_value='test'), patch.object(usage, 'read_json', AsyncMock(return_value={'status':'too_many_events'})):
            with self.assertRaises(usage.DashboardUnavailable) as error: await usage.DashboardReader().get('30d')
            self.assertEqual(error.exception.code,'range_too_large')


if __name__ == '__main__': unittest.main()
