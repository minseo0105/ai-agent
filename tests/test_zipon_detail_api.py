"""읽기 전용 상세 API: 입력 검증·권한·성능·에러 처리·RPC 정합성·connections 실제 상태(설계 §6)."""
import asyncio
import threading
import time
import unittest
import uuid
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from services import access as ac
from services import development as dev
from services import development_detail as detail
from services import development_presentation as pr
from services import development_stage as stage
from services import realestate_monitor as rm

with patch.object(rm, 'init_db'):
    from api import realestate as api

PID = '11111111-1111-5111-8111-111111111111'
VERIFIED_PID = next(pid for pid, item in stage.catalog().items()
                    if item.get('stage_verified_level') == 'OFFICIAL_DETAIL_VERIFIED')


def project_row(**overrides):
    return dict({
        'project_id': PID, 'project_name': '테스트1구역', 'project_type': 'REDEVELOPMENT', 'sigungu': '강동구',
        'dong': '천호동', 'address': '서울 강동구 천호동 1', 'stage_raw': '사업시행인가', 'stage': 'IMPLEMENTATION_APPROVED',
        'status': 'UNKNOWN', 'validation_status': 'NEEDS_REVIEW', 'location': None, 'geometry_verified': False,
        'geometry_source': None, 'geometry_verified_at': None, 'last_verified_at': '2026-11-01T00:00:00+00:00',
        'area_m2': None, 'planned_units': 1200, 'planned_floor': None, 'planned_far': None, 'selected_date': None,
        'notice_date': '2020-01-02', 'source_date': None, 'official_authority': 'cleanup.seoul.go.kr',
        'external_id': 'abc', 'stage_mapping_version': 'v1', 'field_evidence': {}, 'confidence_level': None,
        'revision': 2}, **overrides)


SOURCES = [{'source_id': str(uuid.uuid4()), 'source_name': '서울시 정비사업 정보몽땅',
            'source_url': 'https://cleanup.seoul.go.kr/cafe/x', 'is_official': True,
            'collected_at': '2026-11-01T01:00:00+00:00', 'verified_at': '2026-11-01T02:00:00+00:00',
            'validation_status': 'VERIFIED', 'document_title': None, 'published_at': None, 'effective_at': None}]
UPDATES = [{'update_id': str(uuid.uuid4()), 'update_kind': 'STAGE', 'previous_stage': '조합설립인가',
            'new_stage': '사업시행인가', 'previous_status': 'UNKNOWN', 'new_status': 'UNKNOWN', 'from_revision': 1,
            'to_revision': 2, 'title': 'Official refresh applied', 'changed_fields': ['stage'],
            'recorded_at': '2026-11-01T03:00:00+00:00', 'published_at': None, 'effective_at': None}]


class FakeStore:
    """REST 읽기만 흉내 낸다. 호출 기록과 지연·실패를 지정할 수 있다."""
    def __init__(self, project=None, sources=SOURCES, updates=UPDATES, delay=0.0, fail=()):
        self.project = [project_row()] if project is None else project
        self.sources, self.updates, self.delay, self.fail = sources, updates, delay, set(fail)
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, table, params):
        with self.lock:
            self.calls.append((table, dict(params)))
        if self.delay:
            time.sleep(self.delay)
        if table in self.fail:
            raise RuntimeError('boom')
        return {'development_projects': self.project, 'development_project_sources': self.sources,
                'development_updates': self.updates}[table]


def run(store=None, project_id=PID, cache=None, **kwargs):
    store = store or FakeStore()
    return detail.project_detail(project_id, fetch=store, cache={} if cache is None else cache,
                                 api_status={'public_data_key': True, 'persistent_storage': True},
                                 coordinate_provider=False, remote=True, **kwargs)


class InputAndConfigTests(unittest.TestCase):
    def test_only_uuid_ids_are_accepted(self):
        for bad in ('1', "abc'; drop", '../x', PID + '&select=*', '11111111-1111-5111-8111-11111111111g', '', ' ' + PID):
            with self.assertRaises(detail.DetailError) as caught:
                run(project_id=bad)
            self.assertEqual(caught.exception.status, 422, bad)

    def test_valid_uuid_is_normalised_before_it_reaches_the_query(self):
        store = FakeStore()
        run(store, project_id=PID.upper())
        for table, params in store.calls:
            self.assertEqual(params['project_id'], 'eq.' + PID)

    def test_missing_storage_is_a_503_not_an_empty_project(self):
        with self.assertRaises(detail.DetailError) as caught:
            detail.project_detail(PID, fetch=FakeStore(), cache={}, remote=False,
                                  api_status={'public_data_key': False, 'persistent_storage': False},
                                  coordinate_provider=False)
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(caught.exception.code, 'NOT_CONFIGURED')


class ErrorHandlingTests(unittest.TestCase):
    def test_unknown_project_is_404(self):
        with self.assertRaises(detail.DetailError) as caught:
            run(FakeStore(project=[]))
        self.assertEqual(caught.exception.status, 404)

    def test_project_read_failure_is_503_without_internal_details(self):
        with self.assertRaises(detail.DetailError) as caught:
            run(FakeStore(fail=('development_projects',)))
        self.assertEqual(caught.exception.status, 503)
        self.assertNotIn('boom', caught.exception.message)

    def test_sources_failure_is_a_partial_result_marked_unavailable(self):
        result = run(FakeStore(fail=('development_project_sources',)))
        self.assertEqual(result['sources']['state'], 'unavailable')
        self.assertEqual(result['sources']['items'], [])
        self.assertEqual(result['recent_updates']['state'], 'ok')
        self.assertEqual(result['project']['name'], '테스트1구역')

    def test_updates_failure_is_a_partial_result_marked_unavailable(self):
        result = run(FakeStore(fail=('development_updates',)))
        self.assertEqual(result['recent_updates']['state'], 'unavailable')
        self.assertEqual(result['sources']['state'], 'ok')

    def test_empty_sources_and_updates_are_ok_and_empty_not_unavailable(self):
        result = run(FakeStore(sources=[], updates=[]))
        self.assertEqual((result['sources']['state'], result['recent_updates']['state']), ('ok', 'ok'))
        self.assertEqual((result['sources']['items'], result['recent_updates']['items']), ([], []))

    def test_slow_side_reads_do_not_block_the_response_past_the_deadline(self):
        class Slow(FakeStore):
            def __call__(self, table, params):
                if table != 'development_projects':
                    time.sleep(0.6)
                return super().__call__(table, params)
        started = time.monotonic()
        result = run(Slow(), deadline=0.15)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(result['sources']['state'], 'unavailable')
        self.assertEqual(result['recent_updates']['state'], 'unavailable')

    def test_endpoint_maps_errors_to_http_status(self):
        cases = ((detail.DetailError(422, 'INVALID_ID', 'x'), 422), (detail.DetailError(404, 'NOT_FOUND', 'x'), 404),
                 (detail.DetailError(503, 'UNAVAILABLE', 'x'), 503))
        for error, status in cases:
            with patch.object(api.detail, 'project_detail', side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(api.development_project_detail(PID))
            self.assertEqual(caught.exception.status_code, status)


class PerformanceAndCacheTests(unittest.TestCase):
    def test_three_reads_run_in_parallel(self):
        started = time.monotonic()
        run(FakeStore(delay=0.2))
        self.assertLess(time.monotonic() - started, 0.45)  # 순차였다면 0.6초 이상

    def test_second_call_is_served_from_cache_without_any_read(self):
        store, cache = FakeStore(), {}
        first = run(store, cache=cache)
        calls = len(store.calls)
        second = run(store, cache=cache)
        self.assertEqual(len(store.calls), calls)
        self.assertEqual(first['project']['project_id'], second['project']['project_id'])

    def test_cache_expires(self):
        store, cache, now = FakeStore(), {}, [1000.0]
        clock = lambda: now[0]
        detail.project_detail(PID, fetch=store, cache=cache, remote=True, clock=clock,
                              api_status={'public_data_key': True}, coordinate_provider=False)
        calls = len(store.calls)
        now[0] += detail.CACHE_SECONDS - 1
        detail.project_detail(PID, fetch=store, cache=cache, remote=True, clock=clock,
                              api_status={'public_data_key': True}, coordinate_provider=False)
        self.assertEqual(len(store.calls), calls)
        now[0] += 2
        detail.project_detail(PID, fetch=store, cache=cache, remote=True, clock=clock,
                              api_status={'public_data_key': True}, coordinate_provider=False)
        self.assertGreater(len(store.calls), calls)

    def test_partial_results_are_not_cached_so_a_transient_failure_retries(self):
        store, cache = FakeStore(fail=('development_updates',)), {}
        run(store, cache=cache)
        store.fail.clear()
        again = run(store, cache=cache)
        self.assertEqual(again['recent_updates']['state'], 'ok')

    def test_cache_size_is_bounded(self):
        cache = {}
        for i in range(detail.CACHE_LIMIT + 20):
            pid = str(uuid.UUID(int=i + 1))
            run(FakeStore(project=[project_row(project_id=pid)]), project_id=pid, cache=cache)
        self.assertLessEqual(len(cache), detail.CACHE_LIMIT)

    def test_result_sizes_are_capped(self):
        many_sources = [dict(SOURCES[0], source_id=str(uuid.uuid4())) for _ in range(30)]
        many_updates = [dict(UPDATES[0], update_id=str(uuid.uuid4())) for _ in range(30)]
        store = FakeStore(sources=many_sources, updates=many_updates)
        result = run(store)
        self.assertLessEqual(len(result['sources']['items']), detail.SIDE_LIMIT)
        self.assertLessEqual(len(result['recent_updates']['items']), detail.SIDE_LIMIT)
        limits = {table: params['limit'] for table, params in store.calls}
        self.assertEqual(limits['development_project_sources'], detail.SIDE_LIMIT)
        self.assertEqual(limits['development_updates'], detail.SIDE_LIMIT)


class DataHonestyTests(unittest.TestCase):
    def test_null_facts_stay_null_and_are_never_invented(self):
        facts = run()['project']['facts']
        self.assertIsNone(facts['area_m2'])
        self.assertIsNone(facts['planned_floor'])
        self.assertIsNone(facts['planned_far'])
        self.assertIsNone(facts['source_date'])
        self.assertEqual(facts['planned_units'], 1200)
        self.assertEqual(facts['notice_date'], '2020-01-02')

    def test_boundary_block_reports_only_verification_state(self):
        block = run()['project']['boundary']
        self.assertFalse(block['verified'])
        self.assertNotIn('geometry', block)
        verified = run(FakeStore(project=[project_row(geometry_verified=True, geometry_source='X')]))
        self.assertTrue(verified['project']['boundary']['verified'])

    def test_unsafe_or_non_https_source_links_are_dropped_and_official_is_checked_by_host(self):
        sources = [dict(SOURCES[0], source_url='http://cleanup.seoul.go.kr/x'),
                   dict(SOURCES[0], source_url='javascript:alert(1)'),
                   dict(SOURCES[0], source_url='https://evil.example/x', is_official=True),
                   dict(SOURCES[0], source_url='https://cleanup.seoul.go.kr/ok')]
        items = run(FakeStore(sources=sources))['sources']['items']
        urls = [i['url'] for i in items]
        self.assertNotIn('http://cleanup.seoul.go.kr/x', urls)
        self.assertNotIn('javascript:alert(1)', urls)
        by_url = {i['url']: i for i in items if i['url']}
        self.assertTrue(by_url['https://cleanup.seoul.go.kr/ok']['official'])
        self.assertFalse(by_url['https://evil.example/x']['official'])  # is_official 플래그만 믿지 않는다

    def test_provenance_separates_collection_from_official_dates(self):
        prov = run()['provenance']
        self.assertEqual(prov['last_collected_at'], '2026-11-01T01:00:00+00:00')
        self.assertEqual(prov['last_verified_at'], '2026-11-01T00:00:00+00:00')
        self.assertEqual(prov['notice_date'], '2020-01-02')
        self.assertIsNone(prov['source_date'])

    def test_list_only_project_gets_an_unverified_timeline(self):
        timeline = run()['process_timeline']
        self.assertFalse(timeline['verified'])
        self.assertEqual(timeline['steps'], [])

    def test_verified_project_gets_the_eight_step_timeline_from_official_history(self):
        store = FakeStore(project=[project_row(project_id=VERIFIED_PID)])
        result = run(store, project_id=VERIFIED_PID)
        timeline = result['process_timeline']
        self.assertTrue(timeline['verified'])
        self.assertEqual(len(timeline['steps']), 8)
        self.assertEqual(timeline['source']['url'], result['project']['official_source']['url'])
        self.assertEqual(timeline['current_official']['name'], result['project']['stage']['label'])


class RpcConsistencyTests(unittest.TestCase):
    """지도 RPC 행(+ stage_metadata)과 상세 REST 행이 같은 사업을 같게 말해야 한다."""
    SHARED = ('project_id', 'name', 'type_label', 'district', 'dong', 'address', 'stage', 'stage_guide',
              'status_label', 'trust', 'official_source', 'last_checked', 'source_date', 'notice_date',
              'location_accuracy', 'stage_verified_level', 'stage_basis', 'stage_history', 'stage_timeline',
              'program', 'investor_guide', 'mappable')

    def rpc_style(self, row):
        keep = ('project_id', 'project_name', 'project_type', 'sigungu', 'dong', 'address', 'stage_raw', 'status',
                'validation_status', 'last_verified_at')
        rpc = {k: row[k] for k in keep}
        rpc.update(longitude=None, latitude=None, boundary=None, geometry_verified=row['geometry_verified'])
        meta = {k: row[k] for k in ('stage', 'stage_raw', 'stage_mapping_version', 'source_date', 'notice_date',
                                    'last_verified_at', 'field_evidence', 'external_id', 'official_authority')}
        return dict(rpc, **meta)

    def check(self, row):
        from_rpc = pr.present_project(self.rpc_style(row))
        from_detail = run(FakeStore(project=[row]), project_id=row['project_id'])['project']
        for key in self.SHARED:
            if key in ('mappable',):
                continue
            self.assertEqual(from_rpc[key], from_detail[key], key)

    def test_list_level_project_matches(self):
        self.check(project_row())

    def test_verified_official_detail_project_matches(self):
        self.check(project_row(project_id=VERIFIED_PID))

    def test_applied_refresh_project_matches(self):
        self.check(project_row(project_id=VERIFIED_PID, stage_mapping_version='zipon-refresh-policy-v1'))


class ConnectionsTests(unittest.TestCase):
    def conn(self, row=None, key=True, provider=False):
        return detail.connections_for(row or project_row(), api_status={'public_data_key': key},
                                      coordinate_provider=provider)

    def test_trades_without_server_key_is_not_connected(self):
        self.assertEqual(self.conn(key=False)['trades']['state'], 'NOT_CONNECTED')
        self.assertFalse(self.conn(key=False)['trades']['api_key_configured'])

    def test_trades_with_key_is_regional_only_never_zone_level(self):
        trades = self.conn(key=True)['trades']
        self.assertEqual(trades['state'], 'REGIONAL_ONLY')
        self.assertEqual(trades['zone_panel'], 'NOT_IMPLEMENTED')

    def test_linked_types_come_from_the_real_api_table(self):
        self.assertEqual(self.conn()['trades']['linked_types'], list(rm.TRADE_APIS.keys()))

    def test_land_is_reported_unlinked_because_it_is_not_in_the_api_table(self):
        self.assertNotIn('토지', rm.TRADE_APIS)
        self.assertIn('토지', self.conn()['trades']['unlinked_types'])
        with patch.dict(rm.TRADE_APIS, {'토지': 'https://example.invalid/land'}):
            self.assertNotIn('토지', self.conn()['trades']['unlinked_types'])

    def test_zone_matching_is_blocked_without_a_verified_boundary(self):
        self.assertEqual(self.conn()['trades']['zone_matching'], 'BLOCKED_NO_VERIFIED_BOUNDARY')

    def test_a_verified_boundary_alone_does_not_make_zone_matching_available(self):
        verified = self.conn(project_row(geometry_verified=True))
        self.assertEqual(verified['trades']['zone_matching'], 'NOT_IMPLEMENTED')

    def test_nothing_unimplemented_ever_reads_as_usable(self):
        usable = {'AVAILABLE', 'CONNECTED', 'ENABLED', 'READY', 'ON'}
        for key in (True, False):
            for row in (project_row(), project_row(geometry_verified=True)):
                block = self.conn(row, key=key, provider=True)
                flat = [block['trades']['state'], block['trades']['zone_panel'], block['trades']['zone_matching'],
                        block['rights_engine']['state'], block['listings']['state']]
                self.assertFalse(usable & set(flat), flat)

    def test_rights_engine_and_listings_are_not_connected(self):
        block = self.conn()
        self.assertEqual(block['rights_engine']['state'], 'NOT_CONNECTED')
        self.assertEqual(block['listings']['state'], 'NOT_CONNECTED')

    def test_coordinate_provider_flag_reflects_the_real_credentials(self):
        self.assertTrue(self.conn(provider=True)['trades']['coordinate_provider_configured'])
        self.assertFalse(self.conn(provider=False)['trades']['coordinate_provider_configured'])

    def test_implementation_flags_are_the_single_switch(self):
        # 기능이 구현되면 이 상수가 바뀌고 connections가 함께 바뀐다(별도 '사용 가능' 플래그 없음).
        self.assertFalse(detail.ZONE_TRADES_IMPLEMENTED)
        with patch.object(detail, 'ZONE_TRADES_IMPLEMENTED', True):
            block = self.conn(project_row(geometry_verified=True))['trades']
            self.assertEqual((block['zone_panel'], block['zone_matching']), ('IMPLEMENTED', 'AVAILABLE'))
            self.assertEqual(self.conn()['trades']['zone_matching'], 'BLOCKED_NO_VERIFIED_BOUNDARY')

    def test_detail_response_carries_connections_from_the_actual_environment(self):
        result = run()
        self.assertEqual(result['connections']['trades']['state'], 'REGIONAL_ONLY')


class EndToEndHttpTests(unittest.TestCase):
    """실제 라우터 + 접근 미들웨어를 거친 HTTP 응답."""
    PATH = '/api/realestate/development/projects/'

    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.access import AccessMiddleware
        app = FastAPI()
        app.include_router(api.router)
        app.add_middleware(AccessMiddleware)
        cls.client = TestClient(app)

    def get(self, path, mode='public', who=None, service='inherit'):
        settings = dict(ac.DEFAULT_SETTINGS, site_mode=mode,
                        services=dict(ac.DEFAULT_SETTINGS['services'], realestate=service), members=[])
        with patch.object(ac, 'load_settings', return_value=settings), patch.object(ac, 'identify', return_value=who):
            return self.client.get(path, headers={'Authorization': 'Bearer t'} if who else {})

    def test_public_request_reaches_the_service(self):
        with patch.object(api.detail, 'project_detail', return_value={'ok': True}) as call:
            response = self.get(self.PATH + PID)
        self.assertEqual((response.status_code, response.json()), (200, {'ok': True}))
        call.assert_called_once_with(PID)

    def test_members_only_without_login_is_401_and_never_reaches_the_service(self):
        with patch.object(api.detail, 'project_detail') as call:
            response = self.get(self.PATH + PID, mode='members')
        self.assertEqual(response.status_code, 401)
        call.assert_not_called()

    def test_hidden_and_closed_are_403(self):
        member = {'role': 'member', 'id': 'm', 'name': 'n'}
        with patch.object(api.detail, 'project_detail') as call:
            self.assertEqual(self.get(self.PATH + PID, service='hidden', who=member).status_code, 403)
            self.assertEqual(self.get(self.PATH + PID, mode='closed').status_code, 403)
        call.assert_not_called()

    def test_invalid_id_is_422_and_unknown_is_404_and_outage_is_503(self):
        self.assertEqual(self.get(self.PATH + 'not-a-uuid').status_code, 422)
        for error, status in ((detail.DetailError(404, 'NOT_FOUND', 'x'), 404), (detail.DetailError(503, 'UNAVAILABLE', 'x'), 503)):
            with patch.object(api.detail, 'project_detail', side_effect=error):
                self.assertEqual(self.get(self.PATH + PID).status_code, status)

    def test_only_get_is_allowed(self):
        self.assertEqual(self.client.post(self.PATH + PID).status_code, 405)
        self.assertEqual(self.client.delete(self.PATH + PID).status_code, 405)


class AccessTests(unittest.TestCase):
    """새 경로는 /api/realestate 아래라 기존 서비스 단위 접근 규칙을 상속한다."""
    PATH = '/api/realestate/development/projects/' + PID

    def settings(self, mode='public', service='inherit'):
        return dict(ac.DEFAULT_SETTINGS, site_mode=mode, services=dict(ac.DEFAULT_SETTINGS['services'], realestate=service),
                    members=[])

    def check(self, settings, who):
        with patch.object(ac, 'load_settings', return_value=settings), patch.object(ac, 'identify', return_value=who):
            return ac.check_api(self.PATH, 'token' if who else None)

    def test_path_belongs_to_the_realestate_service(self):
        self.assertEqual(ac.service_for_path(self.PATH), 'realestate')

    def test_public_allows_everyone(self):
        self.assertIsNone(self.check(self.settings('public'), None))

    def test_members_only_requires_login(self):
        with self.assertRaises(ac.AccessError) as caught:
            self.check(self.settings('members'), None)
        self.assertEqual(caught.exception.status, 401)
        self.assertIsNone(self.check(self.settings('members'), {'role': 'member', 'id': 'm', 'name': 'n'}))

    def test_hidden_service_is_blocked_for_members_but_open_to_admin(self):
        member = {'role': 'member', 'id': 'm', 'name': 'n'}
        with self.assertRaises(ac.AccessError) as caught:
            self.check(self.settings('public', 'hidden'), member)
        self.assertEqual(caught.exception.status, 403)
        self.assertIsNone(self.check(self.settings('public', 'hidden'), {'role': 'admin', 'name': 'a'}))

    def test_closed_site_blocks_everyone_but_admin(self):
        for who in (None, {'role': 'member', 'id': 'm', 'name': 'n'}):
            with self.assertRaises(ac.AccessError) as caught:
                self.check(self.settings('closed'), who)
            self.assertEqual(caught.exception.status, 403)
        self.assertIsNone(self.check(self.settings('closed'), {'role': 'admin', 'name': 'a'}))

    def test_the_new_route_is_a_get_and_is_not_admin_only(self):
        route = next(r for r in api.router.routes if r.path.endswith('/development/projects/{project_id}'))
        self.assertEqual(route.methods, {'GET'})
        names = [getattr(d.call, '__name__', '') for d in route.dependant.dependencies]
        self.assertNotIn('require_admin', names)  # 일반 공개 범위 규칙을 따른다(관리자 전용이 아님)

    def test_the_service_never_writes(self):
        source = Path(detail.__file__).read_text(encoding='utf-8')
        for word in ("'POST'", "'PATCH'", "'PUT'", "'DELETE'", 'requests.post', '.upsert', 'rpc/'):
            self.assertNotIn(word, source, word)


if __name__ == '__main__':
    unittest.main()
