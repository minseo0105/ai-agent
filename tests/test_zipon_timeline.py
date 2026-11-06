"""공식 14단계 → 화면 8단계 타임라인. 공식 정보가 항상 우선한다(설계 §3)."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_timeline as tl

OFFICIAL = ['기본계획수립', '안전진단', '정비구역지정', '조합설립추진위원회승인', '조합설립인가',
            '사업시행인가', '관리처분인가', '철거신고', '착공신고', '일반분양승인', '준공인가',
            '이전고시', '조합해산', '조합청산']
SOURCE = {'name': '서울시 정비사업 정보몽땅', 'url': 'https://cleanup.seoul.go.kr/x', 'fetched_at': '2026-11-01T00:00:00+00:00'}


def history(current, dates=None):
    """공식 상세 단계 목록을 같은 모양으로 만든다. dates: {공식 단계명: ISO 날짜 또는 (원문, 정밀도)}."""
    dates = dates or {}
    out = []
    for order, name in enumerate(OFFICIAL, 1):
        value = dates.get(name)
        if isinstance(value, tuple):
            raw, precision = value
            date = raw if precision != 'ISO_DATE' else raw
        else:
            raw, precision, date = (value, 'ISO_DATE', value) if value else (None, None, None)
        out.append({'stage_name': name, 'stage_date': date if value else None, 'date_raw': raw if value else None,
                    'date_precision': precision if value else None, 'stage_order': order,
                    'is_current': name == current})
    return out


def build(project_type, current, dates=None, level='OFFICIAL_DETAIL_VERIFIED', program=None, hist=None):
    return tl.process_timeline(project_type=project_type, program=program,
                               stage_history=history(current, dates) if hist is None else hist,
                               current_official_stage=current, verified_level=level, source=SOURCE)


def step(result, order):
    return next(s for s in result['steps'] if s['order'] == order)


class MappingTests(unittest.TestCase):
    def test_official_order_is_the_fourteen_stage_list(self):
        self.assertEqual(tl.OFFICIAL_ORDER, OFFICIAL)

    def test_eight_steps_map_to_the_official_names(self):
        result = build('REDEVELOPMENT', '사업시행인가')
        self.assertEqual([s['order'] for s in result['steps']], list(range(1, 9)))
        self.assertEqual([s['official_names'] for s in result['steps']],
                         [['정비구역지정'], ['조합설립추진위원회승인'], ['조합설립인가'], ['사업시행인가'],
                          ['관리처분인가'], ['철거신고'], ['착공신고'], ['준공인가', '이전고시']])

    def test_every_official_stage_is_shown_exactly_once(self):
        result = build('RECONSTRUCTION', '관리처분인가')
        shown = []
        for s in result['steps']:
            shown += s['official_names']
        shown += [r['official_name'] for r in result['pre_steps'] + result['extra_steps'] + result['closing_steps']]
        self.assertEqual(sorted(shown, key=OFFICIAL.index), OFFICIAL)

    def test_unrecognised_official_stage_never_breaks_the_build(self):
        hist = history('사업시행인가')
        hist[5]['stage_name'] = '알 수 없는 단계'
        result = build('REDEVELOPMENT', '알 수 없는 단계', hist=hist)
        self.assertIsNone(result['progress'])
        self.assertFalse(result['current_official']['recognised'])


class RealDataShapeTests(unittest.TestCase):
    def test_current_stage_missing_from_the_fourteen_is_shown_as_official_text(self):
        # 실제 공식 데이터에 '부분준공인가'가 현재 단계로 나온 사업이 있다(14단계 목록에 없음).
        hist = history('준공인가')
        for item in hist:
            item['is_current'] = False
        result = build('REDEVELOPMENT', '부분준공인가', hist=hist)
        self.assertEqual(result['current_official']['name'], '부분준공인가')
        self.assertFalse(result['current_official']['recognised'])
        self.assertIsNone(result['progress'])  # 위치를 추정하지 않는다
        self.assertTrue(all(s['status'] != 'CURRENT' for s in result['steps']))


class StatusTests(unittest.TestCase):
    def test_current_step_and_passed_and_upcoming(self):
        result = build('REDEVELOPMENT', '사업시행인가', {'조합설립인가': '2020-03-04', '정비구역지정': '2018-01-02'})
        self.assertEqual([s['status'] for s in result['steps']],
                         ['REACHED_DATED', 'REACHED_UNDATED', 'REACHED_DATED', 'CURRENT',
                          'UPCOMING', 'UPCOMING', 'UPCOMING', 'UPCOMING'])
        self.assertEqual(step(result, 1)['date'], '2018-01-02')
        self.assertIsNone(step(result, 2)['date'])

    def test_progress_phrase_counts_reached_and_dated_without_percentages(self):
        result = build('REDEVELOPMENT', '사업시행인가', {'조합설립인가': '2020-03-04', '정비구역지정': '2018-01-02'})
        self.assertEqual(result['progress']['reached'], 4)
        self.assertEqual(result['progress']['dated'], 2)
        self.assertEqual(result['progress']['phrase'], '8개 주요 단계 중 4단계 도달 (일자 확인 2)')
        self.assertNotIn('%', result['progress']['phrase'])

    def test_short_year_dates_are_kept_verbatim_and_never_given_a_century(self):
        result = build('REDEVELOPMENT', '사업시행인가', {'조합설립인가': ('14.12.15', 'SOURCE_SHORT_YEAR')})
        s = step(result, 3)
        self.assertEqual(s['status'], 'REACHED_DATED')
        self.assertEqual(s['date_display'], '14.12.15')
        self.assertIsNone(s['date'])  # ISO 날짜로 바꾸지 않는다
        self.assertEqual(s['date_precision'], 'SOURCE_SHORT_YEAR')

    def test_first_stage_current_and_last_stage_current(self):
        first = build('REDEVELOPMENT', '정비구역지정')
        self.assertEqual(first['progress']['reached'], 1)
        self.assertEqual(step(first, 1)['status'], 'CURRENT')
        last = build('REDEVELOPMENT', '이전고시')
        self.assertEqual(last['progress']['reached'], 8)
        self.assertEqual(step(last, 8)['status'], 'CURRENT')

    def test_completion_step_has_two_sub_items_with_their_own_dates(self):
        result = build('REDEVELOPMENT', '준공인가', {'준공인가': '2026-01-05'})
        s = step(result, 8)
        self.assertEqual(s['status'], 'CURRENT')
        self.assertEqual([(x['official_name'], x['date'], x['status']) for x in s['sub_items']],
                         [('준공인가', '2026-01-05', 'CURRENT'), ('이전고시', None, 'UPCOMING')])

    def test_input_is_not_modified(self):
        hist = history('사업시행인가', {'조합설립인가': '2020-03-04'})
        before = copy.deepcopy(hist)
        build('REDEVELOPMENT', '사업시행인가', hist=hist)
        self.assertEqual(hist, before)


class OfficialFirstTests(unittest.TestCase):
    """안내용 흐름과 공식 기록이 다르면 공식 기록을 보여 준다."""

    def test_redevelopment_safety_check_with_official_date_is_shown(self):
        result = build('REDEVELOPMENT', '사업시행인가', {'안전진단': '2015-06-01'})
        row = next(r for r in result['pre_steps'] if r['official_name'] == '안전진단')
        self.assertEqual(row['status'], 'REACHED_DATED')
        self.assertEqual(row['date'], '2015-06-01')

    def test_redevelopment_safety_check_without_record_is_marked_usually_skipped(self):
        result = build('REDEVELOPMENT', '사업시행인가')
        row = next(r for r in result['pre_steps'] if r['official_name'] == '안전진단')
        self.assertEqual(row['applicability'], 'USUALLY_SKIPPED')
        self.assertEqual(row['status'], 'USUALLY_SKIPPED')

    def test_reconstruction_safety_check_is_a_standard_pre_step(self):
        result = build('RECONSTRUCTION', '사업시행인가')
        row = next(r for r in result['pre_steps'] if r['official_name'] == '안전진단')
        self.assertEqual(row['applicability'], 'STANDARD')
        self.assertEqual(row['status'], 'NOT_RECORDED')

    def test_other_types_never_mark_a_stage_not_applicable(self):
        for kind in ('MOATOWN', 'MOAHOUSE', 'SHINTONG', 'FAST_TRACK', None, 'OTHER'):
            result = build(kind, '사업시행인가')
            self.assertEqual(result['flow']['code'], 'GENERIC', kind)
            self.assertNotIn('USUALLY_SKIPPED', [r['status'] for r in result['pre_steps']], kind)
            self.assertIn('별도 절차는 정의하지 않았습니다', result['flow']['note'])

    def test_official_date_after_the_current_stage_still_counts_as_reached(self):
        result = build('REDEVELOPMENT', '사업시행인가', {'관리처분인가': '2024-02-02'})
        self.assertEqual(step(result, 5)['status'], 'REACHED_DATED')
        self.assertEqual(step(result, 5)['date'], '2024-02-02')

    def test_current_official_stage_outside_the_eight_is_shown_on_its_own_line(self):
        for name, bucket in (('안전진단', 'pre_steps'), ('기본계획수립', 'pre_steps'), ('일반분양승인', 'extra_steps')):
            result = build('RECONSTRUCTION', name)
            self.assertFalse(result['current_official']['in_standard_steps'], name)
            rows = result[bucket]
            self.assertTrue(next(r for r in rows if r['official_name'] == name)['is_current'], name)

    def test_pre_stage_current_leaves_every_standard_step_upcoming(self):
        result = build('RECONSTRUCTION', '안전진단')
        self.assertEqual({s['status'] for s in result['steps']}, {'UPCOMING'})
        self.assertEqual(result['progress']['reached'], 0)

    def test_general_sale_approval_current_keeps_steps_one_to_seven_passed(self):
        result = build('REDEVELOPMENT', '일반분양승인')
        self.assertEqual([s['status'] for s in result['steps']][:7],
                         ['REACHED_UNDATED'] * 7)
        self.assertEqual(step(result, 8)['status'], 'UPCOMING')
        self.assertEqual(result['progress']['reached'], 7)

    def test_dissolution_current_makes_no_progress_claim(self):
        result = build('REDEVELOPMENT', '조합해산', {'조합설립인가': '2020-03-04'})
        self.assertIsNone(result['progress'])
        self.assertIn('사업 종료 기록', result['closing_note'])
        self.assertEqual(step(result, 3)['status'], 'REACHED_DATED')
        self.assertEqual(step(result, 4)['status'], 'NOT_RECORDED')
        row = next(r for r in result['closing_steps'] if r['official_name'] == '조합해산')
        self.assertTrue(row['is_current'])

    def test_liquidation_current_is_also_a_closing_record(self):
        result = build('RECONSTRUCTION', '조합청산')
        self.assertIsNone(result['progress'])
        self.assertTrue(result['closing_note'])


class UnverifiedTests(unittest.TestCase):
    def test_list_only_project_draws_no_steps_and_no_progress(self):
        result = tl.process_timeline(project_type='REDEVELOPMENT', program=None, stage_history=[],
                                     current_official_stage='사업시행인가',
                                     verified_level='OFFICIAL_LIST_MAPPED', source=SOURCE)
        self.assertEqual(result['steps'], [])
        self.assertIsNone(result['progress'])
        self.assertFalse(result['verified'])
        self.assertIn('공식 상세 확인 전', result['unverified_note'])
        self.assertEqual(result['current_official']['name'], '사업시행인가')

    def test_missing_stage_is_not_invented(self):
        result = tl.process_timeline(project_type=None, program=None, stage_history=None,
                                     current_official_stage=None, verified_level=None, source=None)
        self.assertEqual(result['steps'], [])
        self.assertIsNone(result['current_official']['name'])


class ProgramAndTextTests(unittest.TestCase):
    def test_program_is_a_badge_not_a_flow(self):
        result = build('REDEVELOPMENT', '사업시행인가', program={'code': 'FAST_TRACK', 'label': '신속통합기획'})
        self.assertEqual(result['flow']['code'], 'REDEVELOPMENT')
        self.assertEqual(result['program_label'], '신속통합기획')

    def test_every_step_has_meaning_next_and_question_form_checks(self):
        result = build('RECONSTRUCTION', '사업시행인가')
        for s in result['steps']:
            self.assertTrue(s['meaning'], s['order'])
            self.assertTrue(s['questions'], s['order'])
            self.assertEqual(s['doc']['state'], 'PROJECT_LEVEL_ONLY')
            self.assertEqual(s['doc']['url'], SOURCE['url'])
        self.assertEqual(step(result, 4)['next_label'], '관리처분계획 인가')
        self.assertIsNone(step(result, 8)['next_label'])

    def test_no_step_text_gives_a_definitive_legal_verdict(self):
        banned = ('거래 가능', '거래 불가', '안전한', '문제 없', '양도할 수 있', '양도할 수 없', '반드시 가능', '확정')
        result = build('REDEVELOPMENT', '관리처분인가')
        text = ' '.join([s['meaning'] + ' '.join(s['questions']) for s in result['steps']])
        for word in banned:
            self.assertNotIn(word, text, word)

    def test_server_text_never_uses_the_phrase_the_product_forbids_on_screen(self):
        # test_zipon_product가 화면에서 금지하는 '확인 필요'는 서버 문구에도 쓰지 않는다.
        # 값이 없을 때의 라벨('정보 없음' 등)은 프런트가 붙인다.
        for kind, current in (('REDEVELOPMENT', '관리처분인가'), ('RECONSTRUCTION', '조합해산'), (None, '안전진단')):
            self.assertNotIn('확인 필요', repr(build(kind, current)), (kind, current))

    def test_source_is_carried_for_the_screen(self):
        result = build('REDEVELOPMENT', '사업시행인가')
        self.assertEqual(result['source']['url'], SOURCE['url'])
        self.assertEqual(result['source']['fetched_at'], SOURCE['fetched_at'])


if __name__ == '__main__':
    unittest.main()
