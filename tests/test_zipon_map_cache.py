"""서울 전체 지도 원자료 캐시: MISS→HIT, 동시 요청 단일 조회, 키 독립, TTL, 미저장 조건, 토글 공유, 청약 캐시 회귀."""
import asyncio
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import api.realestate as api
from services import development as dev
from services import realestate_monitor as rm


def raw(n=3, stage='조합설립인가', status='ok', truncated=False):
    projects = [{'project_id': str(uuid.uuid4()), 'project_name': f'p{i}', 'project_type': 'REDEVELOPMENT',
                 'sigungu': '강동구', 'stage_raw': stage, 'longitude': 127.1, 'latitude': 37.5} for i in range(n)]
    return {'status': status, 'projects': projects if status == 'ok' else [], 'reason': None,
            'bbox_filtered': False, 'truncated': truncated, 'db_calls': 50}


class CachedCoreTests(unittest.TestCase):
    def setUp(self):
        api._cache.clear()

    def test_miss_then_hit_and_copy_protects_the_cache(self):
        calls = []
        loader = lambda: calls.append(1) or {'v': [1]}
        seen = []
        first = api._cached('k', loader, 300, None, True, seen.append)
        first['v'].append(99)  # 요청이 받은 값을 바꿔도
        second = api._cached('k', loader, 300, None, True, seen.append)
        self.assertEqual((len(calls), seen, second), (1, ['MISS', 'HIT'], {'v': [1]}))

    def test_concurrent_misses_on_one_key_load_once(self):
        calls, gate = [], threading.Event()

        def loader():
            calls.append(1); gate.wait(1); return {'ok': True}
        threads = [threading.Thread(target=api._cached, args=('same', loader, 300)) for _ in range(8)]
        for t in threads: t.start()
        time.sleep(0.1); gate.set()
        for t in threads: t.join()
        self.assertEqual(len(calls), 1)

    def test_different_keys_do_not_wait_for_each_other(self):
        slow_started, done = threading.Event(), []

        def slow():
            slow_started.set(); time.sleep(0.5); return 1
        t = threading.Thread(target=api._cached, args=('slow', slow, 300)); t.start()
        slow_started.wait(1)
        begin = time.monotonic()
        api._cached('fast', lambda: 2, 300)
        self.assertLess(time.monotonic() - begin, 0.3)
        t.join()

    def test_ttl_expiry_reloads(self):
        calls = []
        api._cached('t', lambda: calls.append(1) or 1, 300)
        api._cache['t'] = (time.monotonic() - 301, 1)
        api._cached('t', lambda: calls.append(1) or 1, 300)
        self.assertEqual(len(calls), 2)

    def test_exception_releases_the_lock_and_is_not_cached(self):
        def boom():
            raise RuntimeError('db')
        with self.assertRaises(RuntimeError):
            api._cached('e', boom, 300)
        self.assertFalse(api._key_lock('e').locked())
        self.assertEqual(api._cached('e', lambda: 'ok', 300), 'ok')

    def test_subscription_style_calls_keep_working(self):
        calls = []
        for _ in range(3):
            api._cached('sub:APT', lambda: calls.append(1) or [1, 2])
        self.assertEqual(len(calls), 1)


class MapEndpointCacheTests(unittest.TestCase):
    def setUp(self):
        api._cache.clear()

    def call(self, results, **kwargs):
        seq = list(results)
        with patch.object(dev, 'map_projects', side_effect=lambda *a: seq.pop(0)) as mp:
            out = [asyncio.run(api.development_map(**kw)) for kw in kwargs.get('calls', [{}])]
        return out, mp.call_count

    def test_toggle_shares_one_raw_load(self):
        r = raw(2) ; r['projects'].append(dict(r['projects'][0], project_id=str(uuid.uuid4()), stage_raw='조합해산'))
        (default, everything), n = self.call([r], calls=[{}, {'include_completed': True}])
        self.assertEqual(n, 1)
        self.assertEqual((default['total'], everything['total']), (2, 3))

    def test_failed_partial_or_truncated_results_are_not_stored(self):
        for bad in (raw(status='unavailable'), raw(truncated=True)):
            api._cache.clear()
            _, n = self.call([bad, raw()], calls=[{}, {}])
            self.assertEqual(n, 2, bad)

    def test_bbox_and_limit_are_part_of_the_key(self):
        box = dict(north=37.6, south=37.4, east=127.2, west=127.0)
        _, n = self.call([raw(), raw(), raw()], calls=[{}, box, {'limit': 100}])
        self.assertEqual(n, 3)

    def test_district_requests_are_not_cached(self):
        _, n = self.call([raw(), raw()], calls=[{'sigungu': '강동구'}, {'sigungu': '강동구'}])
        self.assertEqual(n, 2)

    def test_structured_log_has_no_secrets(self):
        with self.assertLogs('ailab.realestate', 'INFO') as logs:
            self.call([raw()], calls=[{}, {}])
        lines = [l for l in logs.output if 'zipon_map' in l]
        self.assertIn('"cache": "MISS"', lines[0]); self.assertIn('"cache": "HIT"', lines[1])
        self.assertIn('"db_calls": 50', lines[0]); self.assertIn('"db_calls": 0', lines[1])
        for l in lines:
            self.assertNotRegex(l, r'(?i)key|token|supabase|password|http')


class MeterTests(unittest.TestCase):
    def test_citywide_counts_db_calls(self):
        def answer(method, path, **req):
            if path == 'rpc/zipon_development_map':
                d = req['payload']['p_sigungu']
                return [{'project_id': str(uuid.uuid5(uuid.NAMESPACE_URL, d + str(i))), 'project_name': 'x', 'sigungu': d,
                         'longitude': 127.0, 'latitude': 37.5} for i in range(4)]
            return []
        with patch.object(rm, '_using_remote_db', return_value=True), patch.object(rm, '_remote_request', side_effect=answer):
            result = dev.map_projects(None, 500)
        # 25개 구 + 구 밖 1회 + 단계 상세 100건 / 50 = 2회
        self.assertEqual(result['db_calls'], 28)


if __name__ == '__main__':
    unittest.main()
