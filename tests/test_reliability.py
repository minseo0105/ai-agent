"""서버 안정성과 상태 정확성.

한 서비스의 장애가 프로세스나 다른 서비스를 끌어내리지 않는지, 오류가 사용자에게
원문 그대로 새지 않는지, 조건이 바뀌면 그 조건의 결과가 나오는지를 확인한다.
"""
import asyncio
import json
import logging
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import readiness as rd
from api import reliability as rl
from services import development_presentation as pr
from services import realestate_monitor as rm

ROOT = Path(__file__).resolve().parents[1]


def build_app():
    """reliability 층만 올린 작은 앱. 실제 서비스 라우터와 무관하게 동작을 본다."""
    app = FastAPI()
    app.add_exception_handler(HTTPException, rl.http_exception_handler)
    app.add_exception_handler(Exception, rl.unhandled_exception_handler)
    app.add_middleware(rl.RequestContextMiddleware)

    @app.get('/boom')
    def boom():
        raise RuntimeError('database password is hunter2 at https://secret.internal')

    @app.get('/known')
    def known():
        raise HTTPException(404, '골프장을 찾을 수 없습니다.')

    @app.get('/fine')
    def fine():
        return {'ok': True}

    return app


class ErrorSurfaceTests(unittest.TestCase):
    """오류를 200으로 숨기지 않으면서, 내부 사정도 화면에 보내지 않는다."""

    def setUp(self):
        self.client = TestClient(build_app(), raise_server_exceptions=False)

    def test_an_unhandled_error_is_a_500_without_internals(self):
        with self.assertLogs('ailab.request', level='ERROR'):
            response = self.client.get('/boom')
        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body['detail'], rl.INTERNAL_ERROR_MESSAGE)
        # traceback·비밀값·내부 주소가 화면으로 나가지 않는다.
        text = json.dumps(body, ensure_ascii=False)
        for leaked in ('hunter2', 'secret.internal', 'RuntimeError', 'Traceback', 'File "'):
            self.assertNotIn(leaked, text, leaked)

    def test_the_traceback_still_reaches_the_server_log(self):
        with self.assertLogs('ailab.request', level='ERROR') as logs:
            self.client.get('/boom')
        joined = '\n'.join(logs.output)
        self.assertIn('RuntimeError', joined)
        self.assertIn('request_id=', joined)

    def test_an_intended_error_keeps_its_message_and_status(self):
        response = self.client.get('/known')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['detail'], '골프장을 찾을 수 없습니다.')

    def test_every_response_carries_a_request_id_that_matches_the_log(self):
        with self.assertLogs('ailab.request', level='INFO') as logs:
            response = self.client.get('/fine')
        identifier = response.headers['X-Request-Id']
        self.assertTrue(identifier)
        self.assertEqual(response.json(), {'ok': True})
        line = '\n'.join(logs.output)
        self.assertIn(f'request_id={identifier}', line)
        for field in ('method=GET', 'path=/fine', 'status=200', 'duration_ms='):
            self.assertIn(field, line)

    def test_an_error_response_carries_the_same_request_id(self):
        with self.assertLogs('ailab.request', level='ERROR'):
            response = self.client.get('/boom')
        self.assertEqual(response.headers['X-Request-Id'], response.json()['request_id'])

    def test_a_caller_supplied_request_id_is_kept_for_tracing(self):
        response = self.client.get('/fine', headers={'X-Request-Id': 'trace-me-123'})
        self.assertEqual(response.headers['X-Request-Id'], 'trace-me-123')


class SecretRedactionTests(unittest.TestCase):
    def test_credentials_never_reach_the_log(self):
        safe = rl.redact({'Authorization': 'Bearer abc', 'apikey': 'k', 'X-NCP-APIGW-API-KEY': 'n',
                          'serviceKey': 's', 'Cookie': 'c', 'password': 'p', 'q': '강남역'})
        for name in ('Authorization', 'apikey', 'X-NCP-APIGW-API-KEY', 'serviceKey', 'Cookie',
                     'password'):
            self.assertEqual(safe[name], rl.REDACTED, name)
        # 검색어처럼 비밀이 아닌 값은 그대로 남아야 추적에 쓸 수 있다.
        self.assertEqual(safe['q'], '강남역')


class HealthAndReadinessTests(unittest.TestCase):
    """/health는 프로세스만, /ready는 의존성별로. 부가 장애가 전체를 멈추지 않는다."""

    def test_health_calls_nothing_outside_the_process(self):
        source = (ROOT / 'api/main.py').read_text(encoding='utf-8')
        body = source[source.index('def health():'):source.index('def ready():')]
        for forbidden in ('_remote_request', 'requests.', 'urlopen', 'readiness('):
            self.assertNotIn(forbidden, body, forbidden)

    def test_health_answers_immediately(self):
        app = FastAPI()

        @app.get('/api/health')
        def health():
            return {'ok': True, 'service': 'ailab-api'}

        client = TestClient(app)
        started = time.perf_counter()
        response = client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertLess((time.perf_counter() - started) * 1000, 500)

    def test_one_optional_dependency_down_is_degraded_not_unavailable(self):
        with patch.dict(rd.CHECKS, {'supabase': lambda: ('ok', None),
                                    'tavily': lambda: (_ for _ in ()).throw(TimeoutError('slow'))},
                        clear=False):
            report = rd.readiness()
        self.assertEqual(report['status'], 'degraded')
        self.assertEqual(report['dependencies']['supabase']['status'], 'ok')
        self.assertEqual(report['dependencies']['tavily']['status'], 'down')
        self.assertIn('tavily', report['degraded'])

    def test_a_required_dependency_down_is_not_ready(self):
        with patch.dict(rd.CHECKS, {'supabase': lambda: (_ for _ in ()).throw(OSError('refused'))},
                        clear=False):
            report = rd.readiness()
        self.assertEqual(report['status'], 'not_ready')
        self.assertEqual(report['dependencies']['supabase']['status'], 'down')

    def test_a_failing_check_never_escapes_or_leaks_its_message(self):
        def explode():
            raise RuntimeError('postgres://user:secret@host/db timed out')

        with patch.dict(rd.CHECKS, {'tavily': explode}, clear=False):
            report = rd.readiness()
        entry = report['dependencies']['tavily']
        self.assertEqual(entry['status'], 'down')
        # 오류의 종류만 남기고 주소·자격증명이 담긴 메시지는 내보내지 않는다.
        self.assertEqual(entry['note'], 'RuntimeError')
        self.assertNotIn('secret', json.dumps(report, ensure_ascii=False))

    def test_every_dependency_is_checked_even_when_one_fails(self):
        with patch.dict(rd.CHECKS, {'naver': lambda: (_ for _ in ()).throw(ValueError('x'))},
                        clear=False):
            report = rd.readiness()
        self.assertEqual(set(report['dependencies']), set(rd.CHECKS))

    def test_the_readiness_probe_does_not_spend_money_on_external_apis(self):
        source = (ROOT / 'api/readiness.py').read_text(encoding='utf-8')
        naver = source[source.index('def _naver():'):source.index('def _tavily():')]
        # 상태 확인 때문에 유료 지오코딩/경로 호출을 만들지 않는다.
        for forbidden in ('naver_geocode', 'urlopen', 'requests.'):
            self.assertNotIn(forbidden, naver, forbidden)


class StartupCostTests(unittest.TestCase):
    """서버가 뜨는 길목에 무거운 것을 두지 않는다. cold start가 곧 첫 요청 실패다."""

    def test_the_model_and_render_sdks_are_not_imported_at_module_level(self):
        for path, forbidden in (('services/agent.py', ('import anthropic',)),
                                ('services/report.py', ('import matplotlib', 'from reportlab')),
                                ('services/golf_gpt_analysis.py', ('from openai import OpenAI',))):
            source = (ROOT / path).read_text(encoding='utf-8')
            header = source[:source.index('\ndef ')] if '\ndef ' in source else source
            for token in forbidden:
                self.assertNotIn(token, header, f'{path}: {token}')

    def test_the_heavy_sdks_are_still_reachable_when_actually_used(self):
        from services import agent, report
        self.assertTrue(callable(agent.anthropic_sdk))
        self.assertTrue(callable(report._charting))
        self.assertTrue(callable(report._pdf_toolkit))

    def test_importing_the_api_does_not_pull_in_the_render_stack(self):
        import subprocess
        code = ('import sys; sys.path.insert(0, %r);'
                'import api.golf, api.realestate;'
                'print(",".join(m for m in ("matplotlib","reportlab","openai","anthropic")'
                ' if m in sys.modules))' % str(ROOT))
        out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                             cwd=str(ROOT))
        self.assertEqual(out.returncode, 0, out.stderr[:400])
        self.assertEqual(out.stdout.strip(), '', '골프·부동산 경로가 무거운 SDK를 끌고 온다')


class LifecycleTests(unittest.TestCase):
    """완료 판정은 공식 종결 단계만. 착공은 완료가 아니고, 애매하면 숨기지 않는다."""

    def life(self, **row):
        return pr.lifecycle({'project_type': 'REDEVELOPMENT', **row})

    def test_only_an_official_terminal_stage_is_completed(self):
        for stage in ('준공인가', '이전고시'):
            entry = self.life(stage_raw=stage)
            self.assertEqual(entry['code'], 'COMPLETED', stage)
            self.assertEqual(entry['basis'], 'OFFICIAL_TERMINAL_STAGE')
            self.assertFalse(entry['in_default_map'])

    def test_construction_is_not_completed(self):
        entry = self.life(stage_raw='착공')
        self.assertEqual(entry['code'], 'CONSTRUCTION')
        self.assertTrue(entry['in_default_map'])

    def test_an_ambiguous_stage_stays_unknown_and_visible(self):
        for stage in ('조합해산', '조합청산'):
            entry = self.life(stage_raw=stage)
            self.assertEqual(entry['code'], 'UNKNOWN', stage)
            # 끝났을 수도 있다는 가설은 적되, 그것으로 지도에서 지우지 않는다.
            self.assertTrue(entry['hypothesis'], stage)
            self.assertTrue(entry['in_default_map'], stage)

    def test_a_project_without_stage_evidence_is_never_hidden(self):
        entry = self.life()
        self.assertEqual(entry['code'], 'UNKNOWN')
        self.assertEqual(entry['basis'], 'UNRESOLVED')
        self.assertTrue(entry['in_default_map'])

    def test_a_name_that_sounds_finished_does_not_decide_anything(self):
        entry = self.life(project_name='둔촌주공 준공 완료된 아파트', stage_raw='조합설립인가')
        self.assertEqual(entry['code'], 'UNKNOWN')
        self.assertTrue(entry['in_default_map'])

    def test_the_map_point_carries_the_lifecycle(self):
        point = pr.map_point({'project_id': 'p', 'project_name': 'x', 'project_type': 'REDEVELOPMENT',
                              'sigungu': '강동구', 'stage_raw': '이전고시',
                              'validation_status': 'VERIFIED'})
        self.assertEqual(point['lifecycle'], 'COMPLETED')
        self.assertEqual(point['lifecycle_label'], '사업 완료')
        self.assertFalse(point['in_default_map'])


class DefaultMapFilterTests(unittest.TestCase):
    """기본 지도는 완료를 빼고, 토글을 켜면 되돌아온다. 데이터는 지우지 않는다."""

    def rows(self):
        import binascii
        import struct
        point = binascii.hexlify(struct.pack('<BIIdd', 1, 0x20000001, 4326, 127.1, 37.5)).decode()
        common = {'project_type': 'REDEVELOPMENT', 'sigungu': '강동구',
                  'validation_status': 'VERIFIED', 'location': point, 'geometry_verified': False}
        return [dict(common, project_id='done', project_name='완료', stage_raw='준공인가'),
                dict(common, project_id='moving', project_name='이전고시', stage_raw='이전고시'),
                dict(common, project_id='building', project_name='착공', stage_raw='착공'),
                dict(common, project_id='live', project_name='진행', stage_raw='조합설립인가'),
                dict(common, project_id='quiet', project_name='근거없음')]

    def call(self, **kwargs):
        from api.realestate import development_map

        def answer(method, path, **request):
            if path == 'rpc/zipon_development_map':
                raise RuntimeError('rpc not installed')
            if request.get('params', {}).get('select', '').startswith('project_id,stage'):
                return []
            return self.rows()

        with patch.object(rm, '_using_remote_db', return_value=True), \
                patch.object(rm, '_remote_request', side_effect=answer):
            return asyncio.run(development_map(**kwargs))

    def test_completed_projects_are_absent_from_the_default_map(self):
        result = self.call()
        names = [p['name'] for p in result['points']]
        self.assertNotIn('완료', names)
        self.assertNotIn('이전고시', names)
        # 착공·진행·근거없음은 남는다. 확인 못 한 것을 끝난 것으로 다루지 않는다.
        self.assertEqual(sorted(names), sorted(['착공', '진행', '근거없음']))
        self.assertEqual(result['hidden_completed'], 2)
        self.assertFalse(result['include_completed'])

    def test_the_toggle_brings_them_back(self):
        result = self.call(include_completed=True)
        self.assertEqual(len(result['points']), 5)
        self.assertTrue(result['include_completed'])
        self.assertEqual(result['lifecycle_counts']['COMPLETED'], 2)

    def test_the_list_and_the_markers_are_filtered_together(self):
        result = self.call()
        self.assertEqual(len(result['points']), len(result['projects']))
        listed = {row['project_id'] for row in result['projects']}
        self.assertEqual(listed, {p['project_id'] for p in result['points']})

    def test_the_counts_describe_everything_not_only_what_is_shown(self):
        result = self.call()
        self.assertEqual(sum(result['lifecycle_counts'].values()), 5)


class LifecycleAuditTests(unittest.TestCase):
    """130건 감사 산출물. 이번 단계에서 DB에 쓰지 않는다."""

    @classmethod
    def setUpClass(cls):
        cls.document = json.loads((ROOT / 'data/development/lifecycle_audit_20260929.json')
                                  .read_text(encoding='utf-8'))

    def test_it_covers_the_130_and_writes_nothing(self):
        self.assertEqual(self.document['totals']['projects'], 130)
        self.assertEqual(len(self.document['items']), 130)
        self.assertFalse(self.document['db_write'])
        self.assertFalse(self.document['bulk_update_applied'])

    def test_every_row_carries_the_evidence_a_reviewer_needs(self):
        for row in self.document['items']:
            for field in ('project_id', 'project_name', 'district', 'current_stage',
                          'lifecycle_candidate', 'evidence', 'official_source_url',
                          'confidence', 'review_required', 'reason'):
                self.assertIn(field, row)
            self.assertIn(row['lifecycle_candidate'],
                          ('ACTIVE', 'CONSTRUCTION', 'COMPLETED', 'CANCELLED', 'UNKNOWN'))

    def test_completed_rows_all_cite_an_official_terminal_stage(self):
        done = [r for r in self.document['items'] if r['lifecycle_candidate'] == 'COMPLETED']
        self.assertTrue(done)
        for row in done:
            self.assertEqual(row['confidence'], 'OFFICIAL_TERMINAL_STAGE')
            self.assertIn(row['current_stage'], ('COMPLETED', 'TRANSFER_NOTICE'))
            self.assertFalse(row['in_default_map'])

    def test_no_construction_row_was_called_completed(self):
        for row in self.document['items']:
            if row['current_stage'] == 'CONSTRUCTION':
                self.assertEqual(row['lifecycle_candidate'], 'CONSTRUCTION')
                self.assertTrue(row['in_default_map'])

    def test_ambiguous_rows_are_left_for_a_person(self):
        review = [r for r in self.document['items'] if r['review_required']]
        self.assertTrue(review)
        for row in review:
            self.assertEqual(row['lifecycle_candidate'], 'UNKNOWN')
            self.assertEqual(row['confidence'], 'HYPOTHESIS_ONLY')
            self.assertTrue(row['in_default_map'])


class ReliabilityDocumentTests(unittest.TestCase):
    def setUp(self):
        self.document = (ROOT / 'docs/ailab_reliability_2026-09-29.md').read_text(encoding='utf-8')

    def test_it_records_the_measured_startup_improvement(self):
        self.assertIn('2558ms → 708ms', self.document)
        self.assertIn('/api/health', self.document)
        self.assertIn('/api/ready', self.document)

    def test_it_states_the_write_retry_rule(self):
        self.assertIn('쓰기 요청은 같은 일이 두 번 일어날 수 있으므로 자동 재시도하지 않는다',
                      self.document)

    def test_it_states_that_unknown_is_never_hidden(self):
        self.assertIn('UNKNOWN은 숨기지 않는다', self.document)
        self.assertIn('DB에서 지우지 않는다', self.document)

    def test_it_reports_the_lifecycle_counts_that_the_audit_produced(self):
        audit = json.loads((ROOT / 'data/development/lifecycle_audit_20260929.json')
                           .read_text(encoding='utf-8'))['totals']
        for value in (audit['COMPLETED'], audit['CONSTRUCTION'], audit['UNKNOWN'],
                      audit['review_required']):
            self.assertIn(f'| {value} |', self.document, value)

    def test_it_keeps_the_spatial_safety_rule(self):
        self.assertIn('대표좌표만으로는 INSIDE가 되지 않고', self.document)
        self.assertIn('seoul-identity-v1', self.document)
