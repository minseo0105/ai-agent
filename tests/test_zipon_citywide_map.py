"""서울 전체 지도: 자치구 페이지 합치기(500건 한도 해소), 중복 제거, 실패·잘림 신호, 완료사업 필터, 표시 단계."""
import asyncio
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from services import development as dev
from services import realestate_monitor as rm

ROOT = Path(__file__).resolve().parent.parent


def rows_for(district, n, stage='조합설립인가'):
    return [{'project_id': str(uuid.uuid5(uuid.NAMESPACE_URL, f'{district}-{i}')), 'project_name': f'{district}{i}',
             'project_type': 'REDEVELOPMENT', 'sigungu': district, 'stage_raw': stage,
             'longitude': 127.0, 'latitude': 37.5} for i in range(n)]


class CitywideMapTests(unittest.TestCase):
    def run_map(self, per_district, others=(), fail=None, sigungu=None, limit=500):
        calls = {'rpc': 0}

        def answer(method, path, **req):
            if path == 'rpc/zipon_development_map':
                calls['rpc'] += 1
                d = req['payload']['p_sigungu']
                if d == fail:
                    raise RuntimeError('down')
                return per_district.get(d, [])[:req['payload']['p_limit']]
            params = req.get('params', {})
            if 'or' in params:
                return list(others)
            if fail and params.get('sigungu') == 'eq.' + fail:
                raise RuntimeError('down')
            return []  # stage_metadata

        with patch.object(rm, '_using_remote_db', return_value=True), patch.object(rm, '_remote_request', side_effect=answer):
            return dev.map_projects(sigungu, limit), calls

    def test_more_than_500_citywide_rows_are_all_returned_without_duplicates(self):
        data = {d: rows_for(d, 48) for d in dev.SEOUL_MAP_DISTRICTS}   # 25 × 48 = 1,200
        data['강동구'] = data['강동구'] + data['강동구'][:3]               # 중복 행
        result, calls = self.run_map(data)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(len(result['projects']), 1200)
        self.assertEqual(len({p['project_id'] for p in result['projects']}), 1200)
        self.assertFalse(result['truncated'])
        self.assertEqual(calls['rpc'], 25)  # 구마다 한 번, 추가 호출 없음

    def test_page_boundary_sets_truncated(self):
        data = {d: rows_for(d, 3) for d in dev.SEOUL_MAP_DISTRICTS}
        data['송파구'] = rows_for('송파구', 10)
        result, _ = self.run_map(data, limit=10)
        self.assertTrue(result['truncated'])
        result, _ = self.run_map({d: rows_for(d, 9) for d in dev.SEOUL_MAP_DISTRICTS}, limit=10)
        self.assertFalse(result['truncated'])

    def test_rows_outside_the_25_districts_are_included(self):
        other = dict(rows_for('X', 1)[0], sigungu=None)
        result, _ = self.run_map({d: rows_for(d, 1) for d in dev.SEOUL_MAP_DISTRICTS}, others=[other])
        self.assertEqual(len(result['projects']), 26)

    def test_one_failed_district_fails_the_whole_city_rather_than_hiding_it(self):
        result, _ = self.run_map({d: rows_for(d, 2) for d in dev.SEOUL_MAP_DISTRICTS}, fail='중구')
        self.assertEqual(result['status'], 'unavailable')

    def test_single_district_path_is_unchanged(self):
        result, calls = self.run_map({'강동구': rows_for('강동구', 5)}, sigungu='강동구')
        self.assertEqual((len(result['projects']), calls['rpc']), (5, 1))


class CitywideEndpointFilterTests(unittest.TestCase):
    def call(self, include_completed):
        from api.realestate import development_map
        data = {d: [] for d in dev.SEOUL_MAP_DISTRICTS}
        data['강동구'] = (rows_for('강동구', 300) + rows_for('강동구', 2, '조합해산')[0:0]
                       + [dict(r, project_id=str(uuid.uuid4())) for r in rows_for('강동구', 2, '조합해산')]
                       + [dict(r, project_id=str(uuid.uuid4())) for r in rows_for('강동구', 2, '이전고시')])
        data['서초구'] = rows_for('서초구', 300) + [dict(r, project_id=str(uuid.uuid4())) for r in rows_for('서초구', 1, '신통 착수')]

        def answer(method, path, **req):
            if path == 'rpc/zipon_development_map':
                return data.get(req['payload']['p_sigungu'], [])
            return []
        with patch.object(rm, '_using_remote_db', return_value=True), patch.object(rm, '_remote_request', side_effect=answer):
            return asyncio.run(development_map(include_completed=include_completed))

    def test_default_hides_closed_and_completed_and_toggle_shows_them(self):
        default, everything = self.call(False), self.call(True)
        self.assertEqual(everything['total'], 605)
        self.assertEqual(default['total'], 601)
        self.assertEqual(default['hidden_completed'], 4)
        unknown = [p for p in default['projects'] if p['stage_display']['family'] == 'SHINTONG_EARLY']
        self.assertEqual(len(unknown), 1)  # 상태 미확인도 기본 지도에 남는다


class StageDisplayUiTests(unittest.TestCase):
    def test_project_info_shows_display_stage_without_claiming_a_legal_stage(self):
        src = (ROOT / 'web/src/components/realestate/zip/tabs/ProjectInfoTab.tsx').read_text(encoding='utf-8')
        self.assertIn('data-stage-display', src)
        self.assertIn('!project.stage_display.legal_stage_confirmed', src)
        self.assertIn('공식 법적 단계가 아닙니다', src)
        self.assertIn('공식 원문', src)


if __name__ == '__main__':
    unittest.main()
