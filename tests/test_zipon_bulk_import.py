"""Bulk initial load: eligibility gates, batching, failure isolation, reconciliation.

Offline only. The transport is always a stub, so no database is contacted.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import import_zipon_bulk as bulk

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


class Stub:
    """Minimal REST stub. Records every call so writes can be asserted."""

    def __init__(self, projects=(), sources=(), updates=(), fail_ids=()):
        self.projects = [dict(p) for p in projects]
        self.sources = list(sources)
        self.updates = list(updates)
        self.fail_ids = set(fail_ids)
        self.calls = []

    def __call__(self, method, table, payload=None, params=None):
        self.calls.append((method, table))
        if method == 'GET' and table == 'development_projects':
            if params and params.get('external_id') == 'not.is.null':
                return [p for p in self.projects if p.get('external_id')]
            return list(self.projects)
        if method == 'GET' and table == 'development_project_sources':
            return list(self.sources)
        if method == 'GET' and table == 'development_updates':
            return list(self.updates)
        if table == bulk.RPC:
            pid = payload['p_project']['project_id']
            if pid in self.fail_ids:
                raise bulk.ImportDiagnostic('HTTP_STATUS_409')
            self.projects.append({'project_id': pid, 'revision': 1,
                                  'validation_status': 'NEEDS_REVIEW', 'status': 'UNKNOWN',
                                  'stage': None, 'address': payload['p_project'].get('address'),
                                  'official_authority': payload['p_project'].get('official_authority'),
                                  'external_id': payload['p_project'].get('external_id')})
            self.sources.append({'project_id': pid, 'is_official': True,
                                 'content_hash': payload['p_source']['content_hash'],
                                 'validation_status': 'UNVERIFIED'})
            self.updates.append({'project_id': pid, 'update_kind': 'INITIAL', 'to_revision': 1})
            return {'result': 'new', 'project_id': pid, 'revision': 1, 'update_kind': 'INITIAL'}
        return []


class PlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan, cls.quarantine, cls.batches = bulk.build_plan()
        cls.baseline = load('db_baseline_20260927.json')
        cls.canonical = {p['canonical_id']: p for p in load('pilot_canonical_verified_20260927.json')['projects']}

    def rows(self):
        return [r for b in self.batches for r in b['records']]

    def test_every_candidate_is_accounted_for(self):
        totals = self.plan['totals']
        self.assertEqual(totals['total_source'],
                         totals['already_in_db'] + totals['eligible'] + totals['quarantined'])
        self.assertEqual(totals['already_in_db'], 18)
        self.assertEqual(totals['expected_update'], 0)
        self.assertEqual(totals['expected_new'], totals['eligible'])

    def test_batches_never_exceed_ten_and_all_dry_runs_pass(self):
        self.assertEqual(self.plan['dry_run_result'], 'PASS')
        self.assertTrue(self.batches)
        for batch in self.batches:
            self.assertLessEqual(batch['size'], bulk.MAX_IMPORT_BATCH)
            self.assertGreaterEqual(batch['size'], 1)
            self.assertEqual(batch['dry_run']['result'], 'PASS')
        self.assertEqual(sum(b['size'] for b in self.batches), self.plan['totals']['eligible'])

    def test_nothing_already_in_the_database_is_scheduled(self):
        scheduled = {r['project_id'] for r in self.rows()}
        known = {p['project_id'] for p in self.baseline['projects']}
        self.assertEqual(scheduled & known, set())
        canary = {r['project_id'] for r in load('canary_20260927.json')['records']}
        first = {r['project_id'] for r in load('import_batch_01_20260927.json')['records']}
        self.assertEqual(scheduled & canary, set())
        self.assertEqual(scheduled & first, set())

    def test_no_identifier_collides_with_the_database(self):
        known = {p['external_id'] for p in self.baseline['projects'] if p['external_id']}
        identities = {(p['official_authority'], p['external_id']) for p in self.baseline['projects']
                      if p['external_id']}
        for record in self.rows():
            self.assertNotIn(record['external_id'], known)
            self.assertNotIn((record['official_authority'], record['external_id']), identities)
        self.assertEqual(self.plan['totals']['identity_conflict'], 0)

    def test_identifiers_are_unique_inside_the_plan(self):
        ids = [r['project_id'] for r in self.rows()]
        externals = [r['external_id'] for r in self.rows()]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(len(set(externals)), len(externals))
        self.assertTrue(all(externals))

    def test_risky_candidates_are_quarantined_not_scheduled(self):
        reasons = {r for item in self.quarantine['items'] for r in item['reasons']}
        self.assertLessEqual({'QUALITY_STATE_NEEDS_REVIEW', 'IDENTITY_NOT_SETTLED',
                              'LATENT_PROGRAM_IDENTITY_OVERLAP', 'NO_OFFICIAL_EXTERNAL_ID',
                              'NO_OFFICIAL_ADDRESS'}, reasons)
        scheduled = {r['project_id'] for r in self.rows()}
        self.assertEqual(scheduled & {q['project_id'] for q in self.quarantine['items']}, set())

    def test_every_scheduled_candidate_is_payload_safe(self):
        for record in self.rows():
            self.assertEqual(bulk.promotion_risk(record), [])
            self.assertIsNone(record['stage'])
            self.assertEqual(record['status'], 'UNKNOWN')
            self.assertEqual(record['validation_status'], 'NEEDS_REVIEW')
            self.assertEqual(record['source']['validation_status'], 'UNVERIFIED')
            self.assertIsNone(record['geometry'])
            self.assertIsNone(record['location'])

    def test_promotion_risk_catches_each_case(self):
        base = dict(self.rows()[0])
        self.assertIn('PAYLOAD_CARRIES_STAGE', bulk.promotion_risk(dict(base, stage='X')))
        self.assertIn('PAYLOAD_CARRIES_STATUS', bulk.promotion_risk(dict(base, status='ACTIVE')))
        self.assertIn('PAYLOAD_CARRIES_VALIDATION_STATUS',
                      bulk.promotion_risk(dict(base, validation_status='VERIFIED')))
        self.assertIn('PAYLOAD_CARRIES_GEOMETRY',
                      bulk.promotion_risk(dict(base, geometry='POLYGON((0 0,1 0,1 1,0 0))')))
        self.assertIn('SOURCE_CARRIES_VALIDATION_STATUS',
                      bulk.promotion_risk(dict(base, source=dict(base['source'],
                                                                 validation_status='VERIFIED'))))
        self.assertIn('NO_SOURCE_PROVENANCE',
                      bulk.promotion_risk(dict(base, source=dict(base['source'], content_hash=None))))

    def test_the_plan_is_deterministic(self):
        again, _, batches = bulk.build_plan()
        self.assertEqual([r['project_id'] for b in batches for r in b['records']],
                         [r['project_id'] for r in self.rows()])
        self.assertEqual(again['totals'], self.plan['totals'])

    def test_the_order_is_a_district_round_robin(self):
        # The tail is single-district once the smaller districts run out; the head
        # must cycle through every district.
        self.assertEqual(len({r['sigungu'] for r in self.batches[0]['records']}), 3)
        smallest = min(self.plan['by_district'].values())
        head = [r['sigungu'] for r in self.rows()][:3 * smallest]
        districts = sorted(self.plan['by_district'])
        self.assertEqual(head, [districts[i % 3] for i in range(len(head))])

    def test_the_plan_and_quarantine_files_declare_no_write(self):
        self.assertFalse(load('bulk_import_plan_20260927.json')['db_write'])
        self.assertFalse(load('bulk_import_quarantine_20260927.json')['db_write'])
        result = load('bulk_import_result_20260927.json')
        self.assertEqual(result['mode'], 'DRY_RUN')
        self.assertFalse(result['db_write'])


class ApplyTests(unittest.TestCase):
    def setUp(self):
        _, _, self.batches = bulk.build_plan()
        self.small = self.batches[:2]

    def test_every_batch_runs_and_counts_new_rows(self):
        stub = Stub()
        applied = bulk.apply_batches(self.small, stub)
        expected = sum(b['size'] for b in self.small)
        self.assertEqual(applied['counts']['new'], expected)
        self.assertEqual(applied['counts']['failed'], 0)
        self.assertEqual(len(applied['results']), expected)

    def test_one_failure_does_not_stop_the_run(self):
        doomed = self.small[0]['records'][0]['project_id']
        stub = Stub(fail_ids=[doomed])
        applied = bulk.apply_batches(self.small, stub)
        expected = sum(b['size'] for b in self.small)
        self.assertEqual(applied['counts']['failed'], 1)
        self.assertEqual(applied['counts']['new'], expected - 1)
        self.assertEqual(applied['failures'][0]['project_id'], doomed)
        self.assertEqual(applied['failures'][0]['reason'], 'HTTP_STATUS_409')

    def test_a_project_already_present_is_an_idempotent_skip(self):
        present = self.small[0]['records'][0]
        stub = Stub(projects=[{'project_id': present['project_id'], 'revision': 1,
                               'validation_status': 'NEEDS_REVIEW',
                               'official_authority': present['official_authority'],
                               'external_id': present['external_id']}])
        applied = bulk.apply_batches(self.small, stub)
        self.assertEqual(applied['counts']['idempotent_skipped'], 1)
        sent = [c for c in stub.calls if c == ('POST', bulk.RPC)]
        self.assertEqual(len(sent), sum(b['size'] for b in self.small) - 1)

    def test_a_taken_identity_is_skipped_and_reported(self):
        target = self.small[0]['records'][0]
        stub = Stub(projects=[{'project_id': '00000000-0000-5000-8000-000000000000', 'revision': 1,
                               'validation_status': 'NEEDS_REVIEW',
                               'official_authority': target['official_authority'],
                               'external_id': target['external_id']}])
        applied = bulk.apply_batches(self.small, stub)
        self.assertEqual(applied['counts']['identity_skipped'], 1)
        skip = next(s for s in applied['skipped'] if s['kind'] == 'IDENTITY_TAKEN')
        self.assertEqual(skip['existing_project_id'], '00000000-0000-5000-8000-000000000000')

    def test_nothing_destructive_is_ever_sent(self):
        stub = Stub()
        bulk.apply_batches(self.small, stub)
        for method, table in stub.calls:
            self.assertNotEqual(method, 'DELETE')
            self.assertIn((method, table), {('GET', 'development_projects'),
                                            ('POST', 'development_collection_runs'),
                                            ('PATCH', 'development_collection_runs'),
                                            ('POST', bulk.RPC)})

    def test_the_payload_carries_no_promotion_and_the_initial_revision(self):
        sent = []

        def recorder(method, table, payload=None, params=None):
            if table == bulk.RPC:
                sent.append(payload)
            return Stub()(method, table, payload, params)
        bulk.apply_batches(self.small[:1], recorder)
        for payload in sent:
            self.assertEqual(payload['p_expected_revision'], 0)
            self.assertNotIn('stage', payload['p_project'])
            self.assertEqual(payload['p_project']['status'], 'UNKNOWN')
            self.assertEqual(payload['p_project']['validation_status'], 'NEEDS_REVIEW')
            self.assertFalse(payload['p_change']['review_required'])

    def test_an_oversized_batch_is_refused(self):
        oversized = [{'batch_id': 'bad', 'size': 11,
                      'records': self.batches[0]['records'] + self.batches[1]['records'][:1],
                      'candidates': [], 'dry_run': {'result': 'PASS'}}]
        with self.assertRaises(bulk.ImportDiagnostic):
            bulk.apply_batches(oversized, Stub())


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.plan, _, batches = bulk.build_plan()
        self.batches = batches[:1]
        self.baseline = load('db_baseline_20260927.json')['projects']

    def stub_with_baseline(self, **kwargs):
        rows = [{'project_id': p['project_id'], 'revision': p['revision'],
                 'validation_status': p['validation_status'], 'status': 'UNKNOWN', 'stage': None,
                 'address': p['address'], 'official_authority': p['official_authority'],
                 'external_id': p['external_id']} for p in self.baseline]
        return Stub(projects=rows, **kwargs)

    def test_a_clean_run_reconciles(self):
        stub = self.stub_with_baseline()
        applied = bulk.apply_batches(self.batches, stub)
        report = bulk.reconcile(stub, self.plan, applied)
        self.assertEqual(report['result'], 'PASS', report['checks'])
        self.assertEqual(report['expected_project_count'], 18 + applied['counts']['new'])
        names = {c['check'] for c in report['checks']}
        self.assertLessEqual({'expected_vs_actual_project_count', 'no_duplicate_project_id',
                              'no_duplicate_external_identity', 'baseline_eighteen_preserved',
                              'canary_eight_present', 'first_batch_ten_present',
                              'every_loaded_project_has_an_official_source',
                              'every_loaded_project_has_history',
                              'quarantined_never_written'}, names)

    def test_a_missing_row_fails_reconciliation(self):
        stub = self.stub_with_baseline()
        applied = bulk.apply_batches(self.batches, stub)
        stub.projects.pop()
        report = bulk.reconcile(stub, self.plan, applied)
        self.assertEqual(report['result'], 'FAIL')
        self.assertIn('expected_vs_actual_project_count',
                      {c['check'] for c in report['checks'] if c['result'] == 'FAIL'})

    def test_a_changed_baseline_row_fails_reconciliation(self):
        stub = self.stub_with_baseline()
        applied = bulk.apply_batches(self.batches, stub)
        stub.projects[0]['revision'] = 2
        report = bulk.reconcile(stub, self.plan, applied)
        failed = {c['check'] for c in report['checks'] if c['result'] == 'FAIL'}
        self.assertIn('baseline_eighteen_preserved', failed)

    def test_a_duplicate_identity_fails_reconciliation(self):
        stub = self.stub_with_baseline()
        applied = bulk.apply_batches(self.batches, stub)
        first = next(p for p in stub.projects if p['external_id'])
        stub.projects.append(dict(first, project_id='11111111-1111-5111-8111-111111111111'))
        report = bulk.reconcile(stub, self.plan, applied)
        failed = {c['check'] for c in report['checks'] if c['result'] == 'FAIL'}
        self.assertIn('no_duplicate_external_identity', failed)

    def test_reconciliation_only_reads(self):
        stub = self.stub_with_baseline()
        applied = bulk.apply_batches(self.batches, stub)
        before = len(stub.calls)
        bulk.reconcile(stub, self.plan, applied)
        self.assertTrue(all(method == 'GET' for method, _ in stub.calls[before:]))


class SourceTests(unittest.TestCase):
    def test_the_script_reuses_the_existing_gates(self):
        source = (ROOT / 'scripts/import_zipon_bulk.py').read_text(encoding='utf-8')
        self.assertIn('from select_zipon_first_batch import dry_run, eligible, rank, row', source)
        self.assertIn('from import_zipon_candidates import', source)
        self.assertIn('program_identities', source)
        for token in ('uuid5', "'DELETE'", 'seoul-identity-v2'):
            self.assertNotIn(token, source)
        self.assertIn('p_expected_revision', source)

    def test_no_secret_is_printed_or_stored(self):
        source = (ROOT / 'scripts/import_zipon_bulk.py').read_text(encoding='utf-8')
        self.assertNotIn('ZIPON_IMPORT_SUPABASE_KEY', source)
        for name in ('bulk_import_plan_20260927.json', 'bulk_import_result_20260927.json',
                     'bulk_import_quarantine_20260927.json'):
            text = (DATA / name).read_text(encoding='utf-8')
            for pattern in ('sb_secret', 'apikey', 'Authorization', 'supabase.co'):
                self.assertNotIn(pattern, text, name)

    def test_the_rpc_target_is_the_applied_v2_function(self):
        self.assertEqual(bulk.RPC, 'rpc/zipon_ingest_candidate_v2')
        migration = (ROOT / 'supabase/migrations/20260927_zipon_incremental_update_rpc.sql').read_text(encoding='utf-8')
        self.assertIn('zipon_ingest_candidate_v2', migration)


if __name__ == '__main__':
    unittest.main()
