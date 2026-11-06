"""표시용 단계명 계층과 생애주기 회귀. 법적 단계·사업 상태 판정은 바꾸지 않는다."""
import tempfile
import unittest
from unittest.mock import Mock, patch

from services import development_presentation as pr
from services.development_refresh import refresh


class StageDisplayTests(unittest.TestCase):
    def test_shintong_early_terms_are_display_only(self):
        for raw in ('신통 착수', '신통착수', '신통 통보', '용역착수'):
            d = pr.stage_display(raw)
            self.assertEqual((d['family'], d['label'], d['raw']), ('SHINTONG_EARLY', '신속통합기획 초기·준비', raw))
            self.assertFalse(d['legal_stage_confirmed'])

    def test_committee_forming_is_not_committee_approved(self):
        d = pr.stage_display('추진위구성')
        self.assertEqual(d['label'], '추진위원회 구성 중(승인 전)')
        self.assertFalse(d['legal_stage_confirmed'])
        self.assertTrue(pr.stage_display('추진위원회승인')['legal_stage_confirmed'])

    def test_advisory_is_not_deliberation_done(self):
        for raw in ('신통 자문', '자문'):
            self.assertIn('심의 완료 아님', pr.stage_display(raw)['label'])

    def test_ambiguous_terms_keep_raw_and_need_official_check(self):
        for raw in ('준공', '재촉', '사업인가', '인가 완료', '시행자지정(신탁)', '신탁시행자지정(신탁)'):
            d = pr.stage_display(raw)
            self.assertEqual((d['label'], d['family'], d['needs_official_check']), (raw, 'UNMAPPED', True), raw)

    def test_display_layer_does_not_change_lifecycle(self):
        for raw in ('신통 착수', '추진위구성', '자문', '준공', '시행자지정(신탁)'):
            self.assertEqual(pr.lifecycle({'stage_raw': raw})['code'], 'UNKNOWN', raw)

    def test_official_terms_pass_through(self):
        d = pr.stage_display('조합설립인가')
        self.assertEqual((d['family'], d['label'], d['legal_stage_confirmed']), ('OFFICIAL_STAGE', '조합설립인가', True))
        self.assertEqual(pr.stage_display(None)['label'], None)


class ClosedCompletedRegressionTests(unittest.TestCase):
    # 2026-11-07 운영 스냅샷(읽기 전용 SELECT) 기준 236건: 단계명별 건수와 분류.
    SNAPSHOT = {('조합해산', 'CLOSED'): 98, ('조합청산', 'CLOSED'): 58,
                ('이전고시', 'COMPLETED'): 50, ('준공인가', 'COMPLETED'): 30}

    def test_the_236_closed_or_completed_projects_keep_their_class(self):
        total = 0
        for (raw, code), count in self.SNAPSHOT.items():
            life = pr.lifecycle({'stage_raw': raw})
            self.assertEqual(life['code'], code, raw)
            self.assertFalse(life['in_default_map'], raw)
            total += count
        self.assertEqual(total, 236)


class NoCurrentStageErrorCarriesProjectIdTests(unittest.TestCase):
    def run_with(self, record, detail):
        db = Mock()
        db.rows.side_effect = lambda table, *a, **k: []
        runs = [{'source': 'cleanup_11740', 'source_url': 'https://cleanup.seoul.go.kr/list', 'status': 'SUCCEEDED',
                 'source_complete': True, 'errors': []}]
        collection = {'records': [record], 'districts': ['강동구'], 'runs': runs}
        with tempfile.TemporaryDirectory() as folder, \
             patch('services.development_refresh.collector.collect', return_value=collection), \
             patch('services.development_refresh.collect_notices', return_value={'source': 'official_notices', 'status': 'SUCCEEDED', 'source_complete': True, 'errors': [], 'items': [], 'seen': [], 'target_aliases': []}), \
             patch('services.development_refresh.identity', return_value=(None, None)), \
             patch('services.development_refresh.observation', side_effect=detail), \
             patch('services.development_refresh.review'), \
             patch('services.development_refresh.source_for', return_value={'content_hash': 'x'}), \
             patch('services.development_refresh.decision', return_value='NEW_CANDIDATE_REVIEW'):
            return refresh(db=db, http=Mock(objects=[]), directory=folder, shp=False)

    def record(self, **extra):
        return {'project_id': 'p-1', 'project_name': '천호1', 'external_id': 'chunho1', 'sigungu': '강동구',
                'source': {'source_url': 'https://cleanup.seoul.go.kr/list', 'content_hash': 'h'}, **extra}

    def test_detail_reason_error_records_project_id_only(self):
        report = self.run_with(self.record(), lambda *a: ({}, 'NO_CURRENT_STAGE'))
        errors = [e for e in report['errors'] if e['source'] == 'official_detail']
        self.assertEqual(errors, [{'source': 'official_detail', 'code': 'NO_CURRENT_STAGE', 'project_id': 'p-1'}])

    def test_missing_project_id_is_safe(self):
        # project_id가 없는 레코드는 수집 루프가 정렬 단계에서 이미 안전하게 실패 보고로 끝난다.
        # 예외가 밖으로 새지 않고, 오류 항목에 엉뚱한 project_id가 들어가지 않는다.
        rec = self.record(); rec.pop('project_id')
        report = self.run_with(rec, lambda *a: ({}, 'NO_CURRENT_STAGE'))
        self.assertIn(report['status'], ('FAILED', 'PARTIAL'))
        for e in report['errors']:
            if e.get('source') == 'official_detail':
                self.assertIsNone(e['project_id'])


if __name__ == '__main__':
    unittest.main()
