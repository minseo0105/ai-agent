"""Offline only: no production credentials, DB writes, or external service calls."""
import asyncio
import json
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import analytics as api
from api.reliability import RequestContextMiddleware
from services import usage_events as usage


def event(**values):
    return {'session_id': str(uuid4()), 'route': '/realestate', 'service': 'realestate',
            'event_type': 'page_view', 'metadata': {}, **values}


def application():
    app = FastAPI()
    app.include_router(api.router)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(api.UsageErrorsMiddleware)

    @app.get('/api/golf/example')
    def fail():
        raise HTTPException(502, 'private data stays in core response')

    @app.get('/api/realestate/example')
    def ok():
        return {'ok': True}

    @app.get('/api/realestate/unhandled')
    def unhandled():
        raise RuntimeError('secret')

    return app


class EndpointTests(unittest.TestCase):
    def setUp(self):
        api.budget = api.Budget()
        self.client = TestClient(application())

    def test_accepts_without_waiting_for_storage(self):
        row = event()
        with patch.object(api.collector, 'offer') as offer:
            r = self.client.post('/api/analytics/events', json={'events': [row]})
        self.assertEqual(r.status_code, 204)
        offer.assert_called_once_with(row)

    def test_missing_table_or_unconfigured_collector_never_breaks_core(self):
        with patch.object(api.collector, 'queue', None):
            self.assertEqual(self.client.post('/api/analytics/events', json={'events': [event()]}).status_code, 204)
            self.assertEqual(self.client.get('/api/realestate/example').json(), {'ok': True})

    def test_invalid_and_forbidden_values_are_rejected_without_echo(self):
        changes = [{'metadata': {'email': 'private@example.com'}},
                   {'metadata': {'action': 'private@example.com'}},
                   {'metadata': {'nested': {'secret': 'abc'}}},
                   {'route': '/realestate?address=private'}, {'service': 'private'},
                   {'session_id': 'private'}, {'email': 'private@example.com'},
                   {'request_id': 'private'}, {'event_type': 'api_error'}]
        with patch.object(api.collector, 'offer') as offer:
            for change in changes:
                with self.subTest(change=change):
                    api.budget = api.Budget()
                    r = self.client.post('/api/analytics/events', json={'events': [event(**change)]})
                    self.assertEqual(r.status_code, 400)
                    self.assertNotIn('private', r.text)
            offer.assert_not_called()

    def test_malformed_oversize_and_unbounded_batch(self):
        for body in ['{', 'x' * 17000, json.dumps({'events': [event()] * 21})]:
            self.assertEqual(self.client.post('/api/analytics/events', content=body).status_code, 400)

    def test_budget_drops_without_growing_a_session_or_ip_map(self):
        api.budget.tokens = 0
        with patch.object(api.collector, 'offer') as offer:
            self.assertEqual(self.client.post('/api/analytics/events', json={'events': [event()]}).status_code, 204)
            offer.assert_not_called()

    def test_api_error_is_server_only_private_and_does_not_change_response(self):
        with patch.object(api.collector, 'offer') as offer:
            r = self.client.get('/api/golf/example?q=private', headers={'Authorization': 'private', 'Cookie': 'private'})
            self.assertEqual(r.status_code, 502)
            row = offer.call_args.args[0]
            self.assertEqual(row['event_type'], 'api_error')
            self.assertEqual(row['metadata'], {'status': 502})
            self.assertEqual(row['request_id'], r.headers['x-request-id'])
            self.assertNotIn('private', json.dumps(row))
            self.assertIsNone(row['session_id'])

    def test_caller_request_id_is_never_stored(self):
        with patch.object(api.collector, 'offer') as offer:
            self.client.get('/api/golf/example', headers={'X-Request-Id': 'private@example.com'})
            self.assertIsNone(offer.call_args.args[0]['request_id'])

    def test_observer_failure_cannot_replace_core_error_or_success(self):
        with patch.object(api.collector, 'offer', side_effect=RuntimeError):
            self.assertEqual(self.client.get('/api/golf/example').status_code, 502)
            self.assertEqual(self.client.get('/api/realestate/example').status_code, 200)

    def test_endpoint_collector_exception_is_also_quiet(self):
        with patch.object(api.collector, 'offer', side_effect=RuntimeError('private')):
            response = self.client.post('/api/analytics/events', json={'events': [event()]})
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.text, '')

    def test_browser_cannot_read_events_or_query_an_admin_summary(self):
        self.assertEqual(self.client.get('/api/analytics/events').status_code, 405)
        self.assertEqual(self.client.get('/api/analytics/summary').status_code, 404)

    def test_unhandled_exception_is_counted_once(self):
        with patch.object(api.collector, 'offer') as offer:
            self.assertEqual(self.client.get('/api/realestate/unhandled').status_code, 500)
            self.assertEqual(offer.call_count, 1)


class WriterTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, status=None, timeout=False):
        sent = []
        async def handler(request):
            sent.append(request)
            if timeout:
                await asyncio.sleep(10)
            return httpx.Response(status or 201)
        original_client = httpx.AsyncClient
        def client(**kwargs):
            return original_client(transport=httpx.MockTransport(handler), **kwargs)
        credentials = {'SUPABASE_URL': 'https://analytics.invalid', 'SUPABASE_SERVICE_ROLE_KEY': 'sb_secret_test'}
        worker = usage.UsageCollector()
        with patch.object(usage, 'get_secret', side_effect=lambda key: credentials.get(key, '')), patch.object(usage.httpx, 'AsyncClient', side_effect=client):
            await worker.start()
            started = time.monotonic()
            worker.offer(event())
            self.assertLess(time.monotonic() - started, 0.05)
            for _ in range(140):
                await asyncio.sleep(0.01)
                if (timeout or status) and worker.cooldown:
                    break
                if not timeout and not status and sent:
                    break
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0].url.path, '/rest/v1/usage_events')
            self.assertNotIn('authorization', sent[0].headers)
            self.assertEqual(sent[0].headers['apikey'], 'sb_secret_test')
            if timeout or status:
                self.assertGreater(worker.cooldown, time.monotonic())
                worker.offer(event())
                self.assertEqual(worker.queue.qsize(), 0)
            await asyncio.wait_for(worker.queue.join(), timeout=0.5)
            await worker.stop()
            self.assertIsNone(worker.task)

    async def test_success(self):
        await self.exercise()

    async def test_db_failure(self):
        await self.exercise(status=503)

    async def test_table_not_migrated(self):
        await self.exercise(status=404)

    async def test_total_timeout(self):
        await self.exercise(timeout=True)

    async def test_queue_is_bounded(self):
        worker = usage.UsageCollector()
        worker.queue = asyncio.Queue(maxsize=256)
        for _ in range(10000):
            worker.offer(event())
        self.assertEqual(worker.queue.qsize(), 256)

    async def test_no_credentials_no_task(self):
        worker = usage.UsageCollector()
        with patch.object(usage, 'get_secret', return_value=''):
            await worker.start()
        self.assertIsNone(worker.task)
        self.assertIsNone(worker.queue)

    async def test_analytics_failure_does_not_block_health_or_ready(self):
        # Import the real app with the core DB initializer disabled, never production writes.
        with patch('services.realestate_monitor.init_db'):
            from api.main import app
        with patch.object(usage.collector, 'start', side_effect=RuntimeError('unavailable')), \
             patch('api.main.readiness', return_value={'status': 'ready', 'dependencies': {}}):
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/health').status_code, 200)
                self.assertEqual(client.get('/api/ready').json()['status'], 'ready')


if __name__ == '__main__':
    unittest.main()
