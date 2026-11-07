"""지도 응답 본문 캐시와 국토부 실거래 조회 캐시(키·single-flight·실패 미저장·병렬·부분 실패)."""
import asyncio
import json
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import api.realestate as api
from services import development as dev
from services import realestate_monitor as rm

ROOT = Path(__file__).resolve().parent.parent


def raw(n=3, status='ok', truncated=False):
    projects = [{'project_id': str(uuid.uuid4()), 'project_name': f'p{i}', 'project_type': 'REDEVELOPMENT',
                 'sigungu': '송파구', 'stage_raw': '조합설립인가', 'longitude': 127.1, 'latitude': 37.5} for i in range(n)]
    return {'status': status, 'projects': projects if status == 'ok' else [], 'reason': None,
            'bbox_filtered': False, 'truncated': truncated, 'db_calls': 50}


class MapResponseCacheTests(unittest.TestCase):
    def setUp(self):
        api._cache.clear()

    def call(self, results, calls):
        seq = list(results)
        with patch.object(dev, 'map_projects', side_effect=lambda *a: seq.pop(0)) as mp:
            out = [asyncio.run(api.development_map_route(**kw)) for kw in calls]
        return out, mp.call_count

    def test_body_is_reused_and_toggle_keeps_one_raw_load(self):
        (a, b, c, d), n = self.call([raw()], [{}, {}, {'include_completed': True}, {'include_completed': True}])
        self.assertEqual(n, 1)
        self.assertEqual(a.body, b.body)
        self.assertEqual(json.loads(a.body)['total'], 3)
        self.assertEqual(json.loads(c.body)['include_completed'], True)

    def test_failed_or_truncated_bodies_are_not_stored(self):
        for bad in (raw(status='unavailable'), raw(truncated=True)):
            api._cache.clear()
            _, n = self.call([bad, raw()], [{}, {}])
            self.assertEqual(n, 2)

    def test_district_requests_are_not_cached_and_return_dicts(self):
        (r1, r2), n = self.call([raw(), raw()], [{'sigungu': '송파구'}, {'sigungu': '송파구'}])
        self.assertEqual(n, 2)
        self.assertIsInstance(r1, dict)

    def test_route_keeps_the_public_path(self):
        src = (ROOT / 'api/realestate.py').read_text(encoding='utf-8')
        self.assertIn("@router.get('/development/map')\nasync def development_map_route(", src)


XML = """<response><header><resultCode>000</resultCode></header><body><items>
<item><dealAmount>90,000</dealAmount><dealYear>2026</dealYear><dealMonth>10</dealMonth><dealDay>3</dealDay>
<excluUseAr>84.9</excluUseAr><aptNm>A</aptNm><umdNm>거여동</umdNm><jibun>1</jibun></item></items></body></response>""".encode("utf-8")


def ok_response():
    r = type('R', (), {})()
    r.status_code = 200; r.content = XML; r.raise_for_status = lambda: None
    return r


class TradeCacheTests(unittest.TestCase):
    def setUp(self):
        rm._trade_cache.clear()

    def test_same_key_is_fetched_once_even_concurrently(self):
        calls = []

        def slow_get(*a, **k):
            calls.append(1); time.sleep(0.2); return ok_response()
        with patch.object(rm, 'get_public_data_key', return_value='k'), patch.object(rm.requests, 'get', side_effect=slow_get):
            threads = [threading.Thread(target=rm.fetch_trade_cached, args=('아파트', '11710', '202610')) for _ in range(6)]
            for t in threads: t.start()
            for t in threads: t.join()
            rows = rm.fetch_trade_cached('아파트', '11710', '202610')
        self.assertEqual(len(calls), 1)
        self.assertEqual(rows[0]['region'], '거여동')

    def test_month_and_type_are_part_of_the_key_and_copies_are_returned(self):
        with patch.object(rm, 'get_public_data_key', return_value='k'), patch.object(rm.requests, 'get', return_value=ok_response()) as g:
            a = rm.fetch_trade_cached('아파트', '11710', '202610'); a[0]['naver_url'] = 'x'
            b = rm.fetch_trade_cached('아파트', '11710', '202610')
            rm.fetch_trade_cached('아파트', '11710', '202609'); rm.fetch_trade_cached('오피스텔', '11710', '202610')
        self.assertEqual(g.call_count, 3)
        self.assertNotIn('naver_url', b[0])

    def test_failures_are_not_cached_and_partial_results_survive(self):
        def get(url, **k):
            if 'Offi' in url:
                raise rm.requests.Timeout('Read timed out')
            return ok_response()
        with patch.object(rm, 'get_public_data_key', return_value='k'), patch.object(rm.requests, 'get', side_effect=get):
            rows, errors = rm.fetch_trades_multi(['서울 > 송파구'], ['아파트', '오피스텔'], '202610')
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn('오피스텔', errors[0])
        self.assertNotIn(('11710', '오피스텔', '202610'), rm._trade_cache)

    def test_types_run_in_parallel(self):
        def get(*a, **k):
            time.sleep(0.3); return ok_response()
        with patch.object(rm, 'get_public_data_key', return_value='k'), patch.object(rm.requests, 'get', side_effect=get):
            t = time.monotonic()
            rm.fetch_trades_multi(['서울 > 송파구'], ['아파트', '연립·다세대', '단독·다가구', '오피스텔'], '202610')
            self.assertLess(time.monotonic() - t, 0.9)  # 순차면 1.2초


if __name__ == '__main__':
    unittest.main()


class MapResponseSingleFlightTests(unittest.TestCase):
    def test_concurrent_first_requests_build_the_body_once(self):
        api._cache.clear(); api._response_locks.clear()
        built = []
        real = api.development_map

        async def counted(*a, **k):
            built.append(1)
            await asyncio.sleep(0.05)
            return await real(*a, **k)

        async def run():
            return await asyncio.gather(*[api.development_map_route() for _ in range(5)])
        with patch.object(dev, 'map_projects', return_value=raw()), patch.object(api, 'development_map', side_effect=counted):
            out = asyncio.run(run())
        self.assertEqual(len(built), 1)
        self.assertEqual(len({r.body for r in out}), 1)


def forbidden_response():
    r = rm.requests.Response(); r.status_code = 403; r._content = b''
    return r


class TradeForbiddenBackoffTests(unittest.TestCase):
    def setUp(self):
        rm._trade_cache.clear(); rm._forbidden_until.clear()

    def test_403_type_is_not_called_again_within_backoff_and_stays_an_error(self):
        calls = []

        def get(url, **k):
            calls.append(url)
            return forbidden_response() if 'RH' in url else ok_response()
        with patch.object(rm, 'get_public_data_key', return_value='k'), patch.object(rm.requests, 'get', side_effect=get):
            for month in ('202611', '202610', '202609'):
                rows, errors = rm.fetch_trades_multi(['서울 > 송파구'], ['아파트', '연립·다세대'], month)
                self.assertEqual(len(rows), 1)                      # 정상 유형 결과는 유지
                self.assertEqual(len(errors), 1)
                self.assertIn('(403)', errors[0])                    # 거래 없음이 아니라 403
                self.assertEqual(errors[0].count('연립·다세대'), 1)
        self.assertEqual(sum('RH' in u for u in calls), 1)           # 403 유형은 한 번만 호출
        self.assertNotIn(('11710', '연립·다세대', '202611'), rm._trade_cache)  # 데이터로 캐시하지 않음

    def test_backoff_expires(self):
        rm._forbidden_until['연립·다세대'] = time.monotonic() - 1
        with patch.object(rm, 'get_public_data_key', return_value='k'), patch.object(rm.requests, 'get', return_value=ok_response()) as g:
            rm.fetch_trade_cached('연립·다세대', '11710', '202610')
        self.assertEqual(g.call_count, 1)


class TradeConcurrencyCapTests(unittest.TestCase):
    def setUp(self):
        rm._trade_cache.clear(); rm._forbidden_until.clear()

    def test_three_months_in_parallel_never_exceed_six_external_calls(self):
        live, peak, lock = [0], [0], threading.Lock()

        def get(*a, **k):
            with lock:
                live[0] += 1; peak[0] = max(peak[0], live[0])
            time.sleep(0.15)
            with lock:
                live[0] -= 1
            return ok_response()
        types = ['아파트', '연립·다세대', '단독·다가구', '오피스텔']
        with patch.object(rm, 'get_public_data_key', return_value='k'), patch.object(rm.requests, 'get', side_effect=get):
            ths = [threading.Thread(target=rm.fetch_trades_multi, args=(['서울 > 송파구'], types, m)) for m in ('202611', '202610', '202609')]
            for t in ths: t.start()
            for t in ths: t.join()
        self.assertLessEqual(peak[0], 6)
        self.assertGreater(peak[0], 4)   # 3개월이 실제로 병렬로 돈다


class ResponseCacheConsistencyTests(unittest.TestCase):
    def setUp(self):
        api._cache.clear(); api._response_locks.clear()

    def test_response_never_outlives_raw_and_keys_are_separate(self):
        with patch.object(dev, 'map_projects', return_value=raw()):
            asyncio.run(api.development_map_route())
            box = dict(north=37.6, south=37.4, east=127.2, west=127.0)
            asyncio.run(api.development_map_route(**box))
            asyncio.run(api.development_map_route(limit=100))
            asyncio.run(api.development_map_route(include_completed=True))
        resp = {k: v for k, v in api._cache.items() if k[0] == 'devmap-resp'}
        self.assertEqual(len(resp), 4)   # limit·bbox·완료사업 포함 여부가 모두 키를 가른다
        raw_entry = api._cache[api._map_cache_key(None, 500, None)]
        self.assertEqual(resp[('devmap-resp', 500, None, False)][0], raw_entry[0])  # 같은 만료 시각
        self.assertEqual(resp[('devmap-resp', 500, None, True)][0], raw_entry[0])


class StageMetadataParallelMatchTests(unittest.TestCase):
    def test_parallel_batches_match_by_project_id_regardless_of_order(self):
        rows = [{'project_id': str(uuid.uuid4())} for _ in range(160)]

        def request(method, path, params=None, payload=None):
            ids = params['project_id'][4:-1].split(',')
            time.sleep(0.05 if ids[0] < 'm' else 0.0)   # 묶음마다 응답 순서를 섞는다
            return [{'project_id': i, 'stage_raw': 'S-' + i[:8]} for i in reversed(ids)]
        with patch.object(rm, '_remote_request', side_effect=request):
            out = dev.stage_metadata(rows)
        for row in out:
            self.assertEqual(row['stage_raw'], 'S-' + row['project_id'][:8])
