"""Incremental update pipeline: cost control, change classification, canonical safety.

Offline only. Official hosts and geocoders are blocked in this environment, so the
listing side is driven by fixtures. No database is contacted and nothing is written.
"""
import copy
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from services import development_notify as notify
from services import development_pipeline as pipeline
from services import development_schedule as schedule
import run_zipon_refresh as refresh

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
RPC_SQL = ROOT / 'supabase/migrations/20260927_zipon_incremental_update_rpc.sql'
LIST_URL = 'https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do?cpage=1&pageSize=100&scupBsnsSttus.signguCode=11740'


def record(project_id='11111111-1111-5111-8111-111111111111', name='테스트구역', stage='조합설립인가',
           address='서울특별시 강동구 고덕동 212', external_id='abc123', district='강동구',
           content_hash=None, dong='고덕동', planned_units=None):
    return {'project_id': project_id, 'project_name': name, 'project_type': 'RECONSTRUCTION',
            'official_authority': 'cleanup.seoul.go.kr' if external_id else None,
            'external_id': external_id, 'sido': '서울특별시', 'sigungu': district, 'dong': dong,
            'address': address, 'stage': None, 'stage_raw': stage, 'status': 'UNKNOWN',
            'validation_status': 'NEEDS_REVIEW', 'area_m2': None, 'planned_units': planned_units,
            'source_date': None, 'location': None, 'geometry': None, 'geometry_verified': False,
            'revision': 1,
            'field_evidence': {'cells': ['1', district, name, stage], 'source_url': LIST_URL,
                               'parser_version': 'seoul-tables-v1', 'observed_dates': []},
            'source': {'source_name': '정보몽땅 사업장 목록 ' + district, 'source_type': 'OFFICIAL_WEBSITE',
                       'source_url': LIST_URL, 'is_official': True, 'external_id': external_id,
                       'published_at': None, 'collected_at': '2026-09-26T23:59:19+00:00',
                       'verified_at': None, 'validation_status': 'UNVERIFIED',
                       'content_hash': content_hash or ('c' * 63 + '1'), 'raw_snapshot': {}}}


def known_for(records, **overrides):
    rows = []
    for item in records:
        row = {'project_id': item['project_id'], 'revision': 1, 'validation_status': 'NEEDS_REVIEW',
               'status': 'UNKNOWN', 'stage_raw': item['stage_raw'], 'project_name': item['project_name'],
               'dong': item['dong'], 'address': item['address'], 'sido': item['sido'],
               'sigungu': item['sigungu'], 'project_type': item['project_type'],
               'official_authority': item['official_authority'], 'external_id': item['external_id'],
               'area_m2': item['area_m2'], 'planned_units': item['planned_units'],
               'content_hash': item['source']['content_hash']}
        rows.append(dict(row, **overrides))
    return pipeline.known_state(rows)


class CostControlTests(unittest.TestCase):
    def test_unchanged_listing_hash_plans_no_detail_and_no_write(self):
        records = [record()]
        known = known_for(records)
        digests = pipeline.listing_digests(records)
        result = pipeline.plan(records, known, previous_digests=digests)
        self.assertEqual(result['counts'], {'UNCHANGED': 1})
        self.assertEqual(result['detail_verification_targets'], [])
        self.assertEqual(result['writes_planned'], 0)
        self.assertEqual(result['unchanged_sources'], list(digests))

    def test_unchanged_content_hash_needs_no_detail_even_without_digests(self):
        records = [record()]
        result = pipeline.plan(records, known_for(records))
        self.assertEqual(result['counts'], {'UNCHANGED': 1})
        self.assertEqual(result['detail_verification_targets'], [])

    def test_only_new_and_changed_rows_reach_detail_verification(self):
        old = record(project_id='22222222-2222-5222-8222-222222222222', external_id='old1')
        changed = record(project_id='33333333-3333-5333-8333-333333333333', external_id='chg1')
        known = known_for([old, changed])
        moved = copy.deepcopy(changed)
        moved['stage_raw'] = '사업시행인가'
        moved['source'] = dict(moved['source'], content_hash='d' * 63 + '2')
        fresh = record(project_id='44444444-4444-5444-8444-444444444444', external_id='new1')
        result = pipeline.plan([old, moved, fresh], known)
        self.assertEqual(result['counts'], {'INITIAL': 1, 'STAGE_CHANGE': 1, 'UNCHANGED': 1})
        self.assertEqual(sorted(result['detail_verification_targets']),
                         sorted([moved['project_id'], fresh['project_id']]))

    def test_detail_budget_caps_the_targets(self):
        records = [record(project_id=f'5555555{i}-5555-5555-8555-555555555555', external_id=f'e{i}')
                   for i in range(5)]
        result = pipeline.plan(records, {}, detail_budget=2)
        self.assertEqual(len(result['detail_verification_targets']), 2)


class ChangeDetectionTests(unittest.TestCase):
    def test_initial(self):
        change = pipeline.detect_change(None, record())
        self.assertEqual(change['kind'], 'INITIAL')
        self.assertEqual(change['previous_revision'], 0)

    def test_stage_change_records_the_transition(self):
        before = known_for([record()])[record()['project_id']]
        change = pipeline.detect_change(before, record(stage='사업시행인가'))
        self.assertEqual(change['kind'], 'STAGE_CHANGE')
        self.assertEqual(change['changed_fields'], ['stage_raw'])
        self.assertEqual((change['previous_stage'], change['new_stage']), ('조합설립인가', '사업시행인가'))

    def test_status_change(self):
        before = dict(known_for([record()])[record()['project_id']], status='ACTIVE')
        change = pipeline.detect_change(before, record())
        self.assertEqual(change['kind'], 'STATUS_CHANGE')
        self.assertEqual((change['previous_status'], change['new_status']), ('ACTIVE', 'UNKNOWN'))

    def test_data_change_lists_only_the_fields_that_moved(self):
        before = known_for([record()])[record()['project_id']]
        change = pipeline.detect_change(before, record(name='테스트구역 주택재건축정비사업조합'))
        self.assertEqual(change['kind'], 'DATA_CHANGE')
        self.assertEqual(change['changed_fields'], ['project_name'])

    def test_reverification_when_nothing_mapped_changed(self):
        before = known_for([record()])[record()['project_id']]
        self.assertEqual(pipeline.detect_change(before, record())['kind'], 'REVERIFICATION')

    def test_a_blank_candidate_field_never_erases_a_known_value(self):
        before = known_for([record()])[record()['project_id']]
        change = pipeline.detect_change(before, record(address=None, dong=None))
        self.assertEqual(change['changed_fields'], [])

    def test_every_kind_maps_to_an_allowed_update_kind(self):
        allowed = {'INITIAL', 'STATUS', 'STAGE', 'GEOMETRY', 'DETAIL', 'SOURCE_MISSING', 'REVERIFICATION'}
        self.assertLessEqual(set(pipeline.KIND_TO_UPDATE_KIND.values()), allowed)
        self.assertEqual(set(pipeline.KIND_TO_UPDATE_KIND), {
            'INITIAL', 'STAGE_CHANGE', 'STATUS_CHANGE', 'DATA_CHANGE', 'SOURCE_MISSING', 'REVERIFICATION'})


class StageRegressionTests(unittest.TestCase):
    def test_backwards_stage_is_a_regression(self):
        self.assertIsNotNone(pipeline.stage_regression('이전고시', '추진위원회승인'))
        self.assertIsNotNone(pipeline.stage_regression('관리처분인가', '조합설립인가'))

    def test_forward_stage_is_not(self):
        self.assertIsNone(pipeline.stage_regression('조합설립인가', '사업시행인가'))

    def test_unordered_official_terms_are_not_judged(self):
        for before, after in (('착공', '조합해산'), ('준공인가', '조합청산'), ('조합해산', '조합설립인가')):
            self.assertIsNone(pipeline.stage_regression(before, after), (before, after))

    def test_regression_quarantines_the_canonical_update(self):
        before = known_for([record(stage='이전고시')])
        candidate = record(stage='추진위원회승인', content_hash='e' * 63 + '3')
        result = pipeline.plan([candidate], before)
        entry = result['entries'][0]
        self.assertTrue(entry['review_required'])
        self.assertIn('STAGE_REGRESSION', entry['review_reasons'])
        self.assertEqual(entry['canonical_action'], 'HISTORY_ONLY')
        self.assertEqual(entry['fill_fields'], [])


class CanonicalSafetyTests(unittest.TestCase):
    def test_a_verified_row_is_never_touched(self):
        known = known_for([record()], validation_status='VERIFIED')
        candidate = record(stage='사업시행인가', content_hash='f' * 63 + '4')
        entry = pipeline.plan([candidate], known)['entries'][0]
        self.assertEqual(entry['canonical_action'], 'HISTORY_ONLY')
        self.assertEqual(entry['protected'], ['VERIFIED_MASTER'])
        self.assertEqual(entry['fill_fields'], [])

    def test_an_existing_value_is_never_overwritten(self):
        known = known_for([record()])
        candidate = record(address='서울특별시 강동구 고덕동 999', content_hash='a' * 63 + '5')
        entry = pipeline.plan([candidate], known)['entries'][0]
        self.assertNotIn('address', entry['fill_fields'])
        self.assertIn('EXISTING_VALUE_address', entry['protected'])

    def test_a_blank_is_filled_from_an_official_candidate(self):
        known = known_for([record(planned_units=None)])
        candidate = record(planned_units=480, content_hash='b' * 63 + '6')
        entry = pipeline.plan([candidate], known)['entries'][0]
        self.assertEqual(entry['canonical_action'], 'FILL_BLANKS')
        self.assertEqual(entry['fill_fields'], ['planned_units'])

    def test_status_stage_and_validation_can_never_be_filled(self):
        known = known_for([record()], stage_raw=None, status='UNKNOWN', validation_status='UNVERIFIED')
        candidate = record(stage='사업시행인가', content_hash='c' * 63 + '7')
        entry = pipeline.plan([candidate], known)['entries'][0]
        for field in ('stage_raw', 'stage', 'status', 'validation_status'):
            self.assertNotIn(field, entry['fill_fields'])

    def test_identity_conflict_blocks_the_canonical_update(self):
        known = known_for([record(external_id='abc123')])
        candidate = record(external_id='abc123', content_hash='d' * 63 + '8')
        candidate['project_type'] = 'REDEVELOPMENT'
        entry = pipeline.plan([candidate], known)['entries'][0]
        self.assertIn('OFFICIAL_IDENTITY_CONFLICT', entry['review_reasons'])
        self.assertEqual(entry['canonical_action'], 'HISTORY_ONLY')


class SourceMissingTests(unittest.TestCase):
    def setUp(self):
        self.kept = record(project_id='66666666-6666-5666-8666-666666666666', external_id='keep')
        self.gone = record(project_id='77777777-7777-5777-8777-777777777777', external_id='gone',
                           stage='준공인가')
        self.known = known_for([self.kept, self.gone])
        self.result = pipeline.plan([self.kept], self.known)

    def test_absence_is_recorded_once_and_only_as_history(self):
        entry = next(e for e in self.result['entries'] if e['kind'] == 'SOURCE_MISSING')
        self.assertEqual(entry['project_id'], self.gone['project_id'])
        self.assertEqual(entry['canonical_action'], 'HISTORY_ONLY')
        self.assertEqual(entry['update_kind'], 'SOURCE_MISSING')

    def test_absence_does_not_change_stage_or_status(self):
        entry = next(e for e in self.result['entries'] if e['kind'] == 'SOURCE_MISSING')
        self.assertEqual(entry['previous_stage'], entry['new_stage'])
        self.assertEqual(entry['previous_status'], entry['new_status'])
        self.assertEqual(entry['new_status'], 'UNKNOWN')

    def test_no_delete_call_is_ever_planned(self):
        calls = pipeline.build_calls(self.result, [self.kept])['calls']
        self.assertNotIn('DELETE', {c['method'] for c in calls})
        self.assertNotIn('development_projects', {c['table'] for c in calls})
        self.assertIn('rpc/zipon_record_source_missing', {c['table'] for c in calls})


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.identities = [('강동구', '천호A1-2')]

    def test_a_new_overlapping_candidate_is_not_inserted(self):
        candidate = record(project_id='88888888-8888-5888-8888-888888888888',
                           name='천호동 461-31번지 일대 재개발정비사업(천호 A1-2)', external_id='cheonhoA1-2')
        result = pipeline.plan([candidate], {}, identities=self.identities)
        entry = result['entries'][0]
        self.assertTrue(entry['quarantine'])
        self.assertIn('LATENT_PROGRAM_IDENTITY_OVERLAP', entry['review_reasons'])
        calls = pipeline.build_calls(result, [candidate])['calls']
        self.assertEqual([c['table'] for c in calls if c['table'].startswith('rpc/')], [])
        report = pipeline.quarantine_report(result, [candidate])
        self.assertEqual(len(report['items']), 1)
        self.assertFalse(report['db_write'])

    def test_a_candidate_without_an_official_identifier_is_quarantined_when_new(self):
        candidate = record(project_id='99999999-9999-5999-8999-999999999999', external_id=None,
                           address=None, dong=None)
        entry = pipeline.plan([candidate], {})['entries'][0]
        self.assertTrue(entry['quarantine'])
        self.assertIn('NO_OFFICIAL_IDENTIFIER', entry['review_reasons'])

    def test_an_existing_project_still_records_evidence_under_review(self):
        candidate = record(name='천호동 461-31번지 일대 재개발정비사업(천호 A1-2)', external_id='cheonhoA1-2',
                           content_hash='e' * 63 + '9')
        known = known_for([record(name='천호동 461-31번지 일대 재개발정비사업(천호 A1-2)',
                                  external_id='cheonhoA1-2')])
        result = pipeline.plan([candidate], known, identities=self.identities)
        entry = result['entries'][0]
        self.assertFalse(entry['quarantine'])
        self.assertTrue(entry['review_required'])
        payload = next(c['payload'] for c in pipeline.build_calls(result, [candidate])['calls']
                       if c['table'] == 'rpc/zipon_ingest_candidate_v2')
        self.assertTrue(payload['p_change']['review_required'])
        self.assertIn('LATENT_PROGRAM_IDENTITY_OVERLAP', payload['p_change']['review_reasons'])

    def test_project_ids_are_never_recomputed(self):
        candidate = record(project_id='12345678-1234-5678-8234-567812345678')
        result = pipeline.plan([candidate], {})
        self.assertEqual(result['entries'][0]['project_id'], candidate['project_id'])
        payload = next(c['payload'] for c in pipeline.build_calls(result, [candidate])['calls']
                       if c['table'].startswith('rpc/'))
        self.assertEqual(payload['p_project']['project_id'], candidate['project_id'])
        source = (ROOT / 'services/development_pipeline.py').read_text(encoding='utf-8')
        self.assertNotIn('uuid5', source)


class WritePathTests(unittest.TestCase):
    def setUp(self):
        self.records = [record(project_id=f'aaaaaaa{i}-aaaa-5aaa-8aaa-aaaaaaaaaaaa', external_id=f'x{i}')
                        for i in range(3)]
        self.result = pipeline.plan(self.records, {})

    def test_dry_run_touches_no_transport(self):
        transport = Mock()
        summary = pipeline.run(self.result, self.records, transport=transport, dry_run=True)
        transport.assert_not_called()
        self.assertFalse(summary['db_write'])
        self.assertEqual(summary['planned_writes'], 3)

    def test_only_allowlisted_calls_are_produced(self):
        for call in pipeline.build_calls(self.result, self.records)['calls']:
            self.assertIn((call['method'], call['table']), pipeline.ALLOWED_CALLS)

    def test_a_forbidden_call_is_refused(self):
        original = pipeline.ALLOWED_CALLS
        try:
            pipeline.ALLOWED_CALLS = set()
            with self.assertRaises(ValueError):
                pipeline.build_calls(self.result, self.records)
        finally:
            pipeline.ALLOWED_CALLS = original

    def test_the_write_ceiling_stops_a_large_run(self):
        records = [record(project_id=f'bbbbbbb{i:x}-bbbb-5bbb-8bbb-bbbbbbbbbbbb', external_id=f'y{i}')
                   for i in range(11)]
        result = pipeline.plan(records, {})
        with self.assertRaises(ValueError) as caught:
            pipeline.run(result, records, transport=Mock(), dry_run=False)
        self.assertIn('REFRESH_WRITE_LIMIT_10_EXCEEDED_11', str(caught.exception))

    def test_applying_counts_the_rpc_results(self):
        transport = Mock(side_effect=[[], {'result': 'new'}, {'result': 'changed'},
                                      {'result': 'review_required'}, []])
        summary = pipeline.run(self.result, self.records, transport=transport, dry_run=False)
        self.assertTrue(summary['db_write'])
        self.assertEqual(summary['counts']['new'], 1)
        self.assertEqual(summary['counts']['changed'], 1)
        self.assertEqual(summary['counts']['review_required'], 1)
        self.assertEqual(summary['errors'], [])

    def test_a_failing_call_is_recorded_without_leaking_details(self):
        transport = Mock(side_effect=[[], RuntimeError('secret must not leak'), {'result': 'new'},
                                      {'result': 'new'}, []])
        summary = pipeline.run(self.result, self.records, transport=transport, dry_run=False)
        self.assertEqual(len(summary['errors']), 1)
        self.assertNotIn('secret', json.dumps(summary, ensure_ascii=False))


class BaselineTests(unittest.TestCase):
    """Canary 8 + first batch 10 must not be modified by an unchanged refresh."""

    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads((DATA / 'db_baseline_20260927.json').read_text(encoding='utf-8'))
        cls.records = json.loads((DATA / 'pilot_20260927.json').read_text(encoding='utf-8'))['records']

    def test_the_baseline_holds_the_eighteen_known_rows(self):
        self.assertEqual(self.baseline['counts'], {'canary': 8, 'first_batch': 10, 'total': 18})
        self.assertEqual(len({p['project_id'] for p in self.baseline['projects']}), 18)
        self.assertFalse(self.baseline['db_write'])

    def test_an_unchanged_refresh_plans_no_write_against_the_baseline(self):
        known = pipeline.known_state(self.baseline['projects'])
        rows = [r for r in self.records if r['project_id'] in known]
        result = pipeline.plan(rows, known, previous_digests=self.baseline['listing_digests'])
        self.assertEqual(result['counts'], {'UNCHANGED': 18})
        self.assertEqual(result['writes_planned'], 0)
        self.assertEqual(pipeline.build_calls(result, rows)['calls'][1]['table'],
                         'development_collection_runs')

    def test_the_official_scenario_refuses_to_exceed_the_write_limit(self):
        report = refresh.entry('weekly', scenario='official')
        self.assertEqual(report['run']['status'], 'WRITE_LIMIT_EXCEEDED')
        self.assertFalse(report['run']['db_write'])

    def test_every_job_plans_offline_without_a_write(self):
        for name in schedule.names():
            report = refresh.entry(name, scenario='unchanged')
            self.assertFalse(report['run'].get('db_write', False))
            self.assertEqual(report['plan']['writes_planned'], 0)

    def test_the_simulated_scenario_is_labelled_as_a_fixture(self):
        report = refresh.entry('weekly', scenario='simulated-change')
        self.assertFalse(report['official_data'])
        self.assertEqual(report['listing_kind'], 'SIMULATED_LOCAL_FIXTURE')
        kinds = {e['kind'] for e in report['entries']}
        self.assertLessEqual({'STAGE_CHANGE', 'SOURCE_MISSING', 'INITIAL'}, kinds)


class ScheduleTests(unittest.TestCase):
    def test_four_jobs_are_declared_with_their_cadence(self):
        self.assertEqual(schedule.names(), ['daily', 'weekly', 'monthly', 'half_yearly'])
        for name in schedule.names():
            definition = schedule.job(name)
            for key in ('cadence', 'cron_hint', 'purpose', 'detail_budget', 'write_limit', 'steps'):
                self.assertIn(key, definition)
            self.assertLessEqual(definition['write_limit'], 10)

    def test_monthly_is_report_only(self):
        monthly = schedule.job('monthly')
        self.assertEqual(monthly['write_limit'], 0)
        self.assertIn('REPORT_ONLY', monthly['steps'])

    def test_geocode_and_polygon_are_event_driven(self):
        self.assertEqual(set(schedule.EVENT_DRIVEN), {'geocode', 'polygon'})

    def test_unknown_job_is_refused(self):
        with self.assertRaises(KeyError):
            schedule.job('hourly')

    def test_nothing_is_registered_with_the_app_scheduler(self):
        source = (ROOT / 'scheduler.py').read_text(encoding='utf-8')
        self.assertNotIn('development', source)


class NotificationTests(unittest.TestCase):
    def update(self, kind='STAGE', **extra):
        row = {'project_id': 'p1', 'to_revision': 2, 'update_kind': kind,
               'previous_stage': '조합설립인가', 'new_stage': '사업시행인가',
               'previous_status': 'UNKNOWN', 'new_status': 'UNKNOWN',
               'changed_fields': ['stage_raw'], 'event_hash': 'a' * 64,
               'new_snapshot': {'master': {'project_name': '테스트구역'},
                                'change': {'pipeline_kind': 'STAGE_CHANGE'}}}
        return dict(row, **extra)

    def test_stage_change_renders_the_transition(self):
        event = notify.render_event(self.update())
        self.assertEqual(event['severity'], 'HIGH')
        self.assertIn('조합설립인가 → 사업시행인가', event['message'])
        self.assertEqual(event['event_key'], 'zipon-dev:p1:2')

    def test_absence_is_never_reported_as_a_cancellation(self):
        event = notify.render_event(self.update('SOURCE_MISSING'))
        self.assertEqual(event['severity'], 'REVIEW')
        self.assertTrue(event['requires_human_review'])
        # The message must state the absence and explicitly deny a business outcome.
        self.assertIn('공식 목록에 나타나지 않음', event['message'])
        self.assertIn('의미하지 않음', event['message'])
        for claim in ('취소되', '취소됨', '종료됨', '해제됨', 'CANCELLED', 'COMPLETED'):
            self.assertNotIn(claim, event['message'])
        self.assertEqual(event['update_kind'], 'SOURCE_MISSING')

    def test_a_quarantined_change_is_marked_for_review(self):
        row = self.update()
        row['new_snapshot']['change']['review_required'] = True
        row['new_snapshot']['change']['review_reasons'] = ['STAGE_REGRESSION']
        event = notify.render_event(row)
        self.assertEqual(event['severity'], 'REVIEW')
        self.assertIn('검토 필요', event['message'])
        self.assertEqual(event['review_reasons'], ['STAGE_REGRESSION'])

    def test_repeated_delivery_is_skipped_by_event_hash(self):
        consumer = notify.CollectingConsumer()
        rows = [self.update(), self.update()]
        result = notify.consume(rows, consumer)
        self.assertEqual((result['delivered'], result['skipped_duplicates']), (1, 1))
        self.assertEqual(len(consumer.events), 1)
        self.assertFalse(result['db_write'])

    def test_the_draft_consumer_writes_nothing(self):
        drafts = notify.NotificationDraftConsumer()
        notify.consume([self.update()], drafts)
        self.assertEqual(len(drafts.drafts), 1)
        self.assertEqual(set(drafts.drafts[0]),
                         {'event_key', 'category', 'title', 'message', 'is_read', 'requires_human_review'})
        source = (ROOT / 'services/development_notify.py').read_text(encoding='utf-8')
        for token in ('requests', 'psycopg', 'INSERT', 'rpc/'):
            self.assertNotIn(token, source)

    def test_the_interface_must_be_implemented(self):
        with self.assertRaises(NotImplementedError):
            notify.DevelopmentUpdateConsumer().handle({})


def assignments(block):
    names, depth, current = [], 0, ''
    for char in block:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        if char == ',' and depth == 0:
            names.append(current)
            current = ''
        else:
            current += char
    names.append(current)
    return [re.match(r'\s*([a-z_]+)\s*=', name).group(1) for name in names if re.match(r'\s*([a-z_]+)\s*=', name)]


class NewRpcSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = RPC_SQL.read_text(encoding='utf-8')

    def test_the_existing_ingest_function_is_not_redefined(self):
        self.assertIn('zipon_ingest_candidate_v2', self.sql)
        self.assertNotIn('FUNCTION public.zipon_ingest_candidate(', self.sql)
        self.assertNotIn('DROP ', self.sql.upper())

    def test_security_and_grants_follow_the_existing_pattern(self):
        self.assertEqual(self.sql.count('SECURITY INVOKER'), 2)
        self.assertEqual(self.sql.count('SET search_path=pg_catalog,public,extensions,pg_temp'), 2)
        self.assertEqual(self.sql.count('FROM PUBLIC,anon,authenticated'), 2)
        self.assertEqual(self.sql.count('TO service_role'), 2)
        self.assertNotIn('ALTER TABLE', self.sql)
        self.assertNotIn('CREATE POLICY', self.sql)
        self.assertNotIn('TRUNCATE', self.sql)
        self.assertNotIn('DELETE FROM', self.sql)

    def test_master_updates_only_touch_allowed_columns(self):
        allowed = {'dong', 'address', 'area_m2', 'planned_units', 'revision', 'updated_at'}
        blocks = re.findall(r'UPDATE public\.development_projects SET(.*?)WHERE', self.sql, re.S)
        self.assertEqual(len(blocks), 3)
        for block in blocks:
            self.assertTrue(set(assignments(block)))
            self.assertLessEqual(set(assignments(block)), allowed, block)

    def test_the_verified_guard_and_review_guard_are_present(self):
        self.assertIn("oldrow.validation_status<>'VERIFIED'", self.sql)
        self.assertIn('NOT review', self.sql)
        self.assertIn('Candidate may not promote status, stage or validation', self.sql)

    def test_source_missing_keeps_stage_and_status(self):
        block = self.sql[self.sql.index('zipon_record_source_missing'):]
        self.assertIn("'SOURCE_MISSING',oldrow.stage_raw,oldrow.stage_raw,", block)
        self.assertIn('ABSENCE_IS_NOT_CANCELLATION', block)
        self.assertIn("update_kind='SOURCE_MISSING' THEN", block)

    def test_both_functions_parse(self):
        try:
            from pglast import parse_plpgsql, parser
        except ImportError:
            self.skipTest('pglast is not installed in this environment')
        parser.parse_sql(self.sql)
        bodies = re.findall(r'AS \$fn\$(.*?)\$fn\$', self.sql, re.S)
        self.assertEqual(len(bodies), 2)
        for body in bodies:
            parse_plpgsql('CREATE FUNCTION x() RETURNS jsonb LANGUAGE plpgsql AS $x$' + body + '$x$')


if __name__ == '__main__':
    unittest.main()
