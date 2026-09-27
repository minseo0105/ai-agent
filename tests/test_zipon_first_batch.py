"""First reviewed import batch: selection, dry-run gates, write ceiling, API safety.

Scope is this sprint only. No migration, RPC, canary or official-host access here.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from services import development_collector as dc
import select_zipon_first_batch as sel
import verify_zipon_first_batch as ver
from scripts.import_zipon_candidates import ImportDiagnostic, validate_records

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


class WriteCeilingTests(unittest.TestCase):
    def record(self, index):
        return {'project_id': f'{index:08d}-0000-0000-0000-000000000000', 'project_name': 'x',
                'project_type': 'RECONSTRUCTION', 'sigungu': '강동구', 'revision': 1,
                'source': {'content_hash': 'a' * 64}}

    def test_eleven_records_are_refused_before_any_request(self):
        transport = Mock()
        with self.assertRaises(ValueError) as caught:
            dc.import_batch([self.record(i) for i in range(11)], transport)
        self.assertIn('IMPORT_BATCH_LIMIT_1_TO_10', str(caught.exception))
        transport.assert_not_called()

    def test_empty_batch_is_refused(self):
        transport = Mock()
        with self.assertRaises(ValueError):
            dc.import_batch([], transport)
        transport.assert_not_called()

    def test_ten_records_are_allowed(self):
        transport = Mock(side_effect=[[]] + [[], {'result': 'new'}] * 10 + [[]])
        result = dc.import_batch([self.record(i) for i in range(10)], transport)
        self.assertEqual(result['new'], 10)
        self.assertEqual(result['errors'], [])

    def test_cli_keeps_its_own_ceiling(self):
        self.assertEqual(dc.MAX_IMPORT_BATCH, 10)
        source = (ROOT / 'scripts/import_zipon_candidates.py').read_text(encoding='utf-8')
        self.assertIn('CANARY_LIMIT_1_TO_10', source)
        self.assertIn('if not 1 <= len(records) <= 10', source)


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = load('pilot_canonical_verified_20260927.json')['projects']
        cls.identities = sel.program_identities(cls.canonical)

    def test_needs_review_and_canary_are_never_eligible(self):
        for project in self.canonical:
            reasons = sel.eligible(project, self.identities)
            if project['quality_state'] == 'NEEDS_REVIEW':
                self.assertIn('QUALITY_STATE_NEEDS_REVIEW', reasons)
            if project['import_plan']['existing_canary']:
                self.assertIn('ALREADY_IMPORTED_AS_CANARY', reasons)

    def test_latent_program_overlap_is_deferred(self):
        risky = [p for p in self.canonical if sel.latent_overlap(p, self.identities)
                 and p['quality_state'] != 'NEEDS_REVIEW']
        self.assertEqual(len(risky), 5)
        for project in risky:
            self.assertIn('LATENT_PROGRAM_IDENTITY_OVERLAP', sel.eligible(project, self.identities))
        names = {p['identity']['official_project_name'] for p in risky}
        self.assertIn('천호동 461-31번지 일대 재개발정비사업(천호 A1-2)', names)

    def test_selection_is_deterministic_and_covers_every_district(self):
        first, _ = sel.select(self.canonical)
        second, _ = sel.select(self.canonical)
        self.assertEqual([p['canonical_id'] for p in first], [p['canonical_id'] for p in second])
        self.assertEqual(len(first), 10)
        self.assertEqual(len({p['location']['district'] for p in first}), 3)
        self.assertGreaterEqual(len({p['classification']['canonical_project_type'] for p in first}), 2)

    def test_every_selected_project_carries_official_evidence(self):
        chosen, _ = sel.select(self.canonical)
        for project in chosen:
            self.assertTrue(project['identity']['official_external_id'])
            self.assertTrue(project['location']['address_verified'])
            self.assertTrue(project['progress']['stage_verified'])
            self.assertTrue(project['provenance']['content_hash'])
            self.assertFalse(project['duplicate']['unresolved'])
            self.assertFalse(project['import_plan']['existing_canary'])

    def test_size_cannot_exceed_the_ceiling(self):
        self.assertEqual(len(sel.select(self.canonical, 10)[0]), 10)
        self.assertEqual(len(sel.select(self.canonical, 3)[0]), 3)


class DryRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load('import_batch_01_dryrun_20260927.json')
        cls.canary = load('canary_20260927.json')['records']

    def rows(self):
        return [dict(row) for row in self.report['candidates']]

    def test_the_committed_dry_run_passes(self):
        self.assertEqual(self.report['dry_run']['result'], 'PASS')
        self.assertEqual(self.report['selected'], 10)
        self.assertEqual(self.report['dry_run']['canary_collisions'], [])

    def test_duplicate_project_id_fails(self):
        rows = self.rows()
        rows[1]['project_id'] = rows[0]['project_id']
        result = sel.dry_run(rows, self.canary)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('project_id_unique', [c['check'] for c in result['checks'] if c['result'] == 'FAIL'])

    def test_duplicate_external_id_fails(self):
        rows = self.rows()
        rows[1]['external_id'] = rows[0]['external_id']
        failed = [c['check'] for c in sel.dry_run(rows, self.canary)['checks'] if c['result'] == 'FAIL']
        self.assertIn('external_id_unique', failed)

    def test_canary_project_id_collision_is_detected(self):
        rows = self.rows()
        rows[0]['project_id'] = self.canary[0]['project_id']
        result = sel.dry_run(rows, self.canary)
        self.assertEqual(result['result'], 'FAIL')
        self.assertEqual(result['canary_collisions'][0]['kind'], 'CANARY_PROJECT_ID')

    def test_canary_external_id_collision_is_detected(self):
        rows = self.rows()
        rows[0]['external_id'] = next(r['external_id'] for r in self.canary if r['external_id'])
        result = sel.dry_run(rows, self.canary)
        self.assertEqual(result['canary_collisions'][0]['kind'], 'CANARY_EXTERNAL_ID')

    def test_promoted_stage_or_status_fails(self):
        for field, value, check in (('stage', 'ASSOCIATION_APPROVED', 'stage_not_promoted_in_payload'),
                                    ('status', 'ACTIVE', 'status_not_promoted_in_payload'),
                                    ('validation_status', 'VERIFIED',
                                     'validation_status_stays_needs_review'),
                                    ('source_validation_status', 'VERIFIED',
                                     'source_validation_status_stays_unverified')):
            rows = self.rows()
            rows[0][field] = value
            failed = [c['check'] for c in sel.dry_run(rows, self.canary)['checks'] if c['result'] == 'FAIL']
            self.assertIn(check, failed)

    def test_bad_content_hash_and_unofficial_source_fail(self):
        rows = self.rows()
        rows[0]['content_hash'] = 'short'
        rows[1]['source_url'] = 'https://blog.example.com/post'
        failed = [c['check'] for c in sel.dry_run(rows, self.canary)['checks'] if c['result'] == 'FAIL']
        self.assertIn('content_hash_is_sha256', failed)
        self.assertIn('official_source_host', failed)

    def test_oversized_batch_fails(self):
        rows = self.rows() * 2
        failed = [c['check'] for c in sel.dry_run(rows, self.canary)['checks'] if c['result'] == 'FAIL']
        self.assertIn('batch_size_within_limit', failed)

    def test_name_containment_inside_the_batch_fails(self):
        rows = self.rows()
        rows[1]['project_name'] = rows[0]['project_name'][:6]
        failed = [c['check'] for c in sel.dry_run(rows, self.canary)['checks'] if c['result'] == 'FAIL']
        self.assertIn('no_name_containment_inside_batch', failed)


class BatchFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = load('import_batch_01_20260927.json')
        cls.raw = {r['project_id']: r for r in load('pilot_20260927.json')['records']}

    def test_records_are_the_raw_pilot_records_verbatim(self):
        self.assertEqual(len(self.batch['records']), 10)
        for record in self.batch['records']:
            self.assertEqual(record, self.raw[record['project_id']])

    def test_the_importer_accepts_the_batch(self):
        validate_records(self.batch['records'])

    def test_the_importer_rejects_a_tampered_batch(self):
        records = [dict(r) for r in self.batch['records']]
        records[0] = dict(records[0], source=dict(records[0]['source'], is_official=False))
        with self.assertRaises(ImportDiagnostic):
            validate_records(records)

    def test_the_batch_declares_no_write_and_the_new_project(self):
        self.assertFalse(self.batch['db_write'])
        self.assertEqual(self.batch['target_project_ref'], 'nnxtkvjpzqqhjlgnprzo')
        self.assertEqual(self.batch['maximum_batch_size'], 10)


class ApiSafetyTests(unittest.TestCase):
    def test_offline_contract_passes(self):
        checks = ver.offline_contract()
        self.assertTrue(checks)
        self.assertEqual([c for c in checks if c['result'] == 'FAIL'], [])

    def test_inside_without_a_verified_boundary_is_a_failure(self):
        rows = [{'project_name': 'x', 'spatial_relation': 'INSIDE', 'evidence_verified': False}]
        failed = [c['check'] for c in ver.spatial_safety(rows) if c['result'] == 'FAIL']
        self.assertIn('no_inside_without_verified_boundary', failed)

    def test_inside_with_a_verified_boundary_is_allowed(self):
        rows = [{'project_name': 'x', 'spatial_relation': 'INSIDE', 'evidence_verified': True}]
        self.assertEqual([c for c in ver.spatial_safety(rows) if c['result'] == 'FAIL'], [])

    def test_unknown_relation_is_accepted(self):
        rows = [{'project_name': 'x', 'spatial_relation': 'UNKNOWN', 'evidence_verified': False}]
        self.assertEqual([c for c in ver.spatial_safety(rows) if c['result'] == 'FAIL'], [])

    def test_database_section_is_skipped_without_credentials(self):
        report = load('import_batch_01_verification_20260927.json')
        self.assertIn(report['database']['status'], ('SKIPPED', 'CHECKED'))
        self.assertFalse(report['db_write'])


if __name__ == '__main__':
    unittest.main()
