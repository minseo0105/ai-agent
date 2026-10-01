"""서울 25개 적재 artifact — 안전 속성만 확인한다. DB도 네트워크도 쓰지 않는다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_collector as dc

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build_zipon_seoul_import.py'
CAPTURE = ROOT / 'data/development/pilot_20260927.json'
BASELINE = ROOT / 'data/development/lifecycle_audit_20260929.json'


class ImportArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        out = Path(cls.folder.name) / 'artifact.json'
        subprocess.run([sys.executable, str(SCRIPT), '--input', str(CAPTURE),
                        '--baseline', str(BASELINE), '--out', str(out)],
                       check=True, capture_output=True, cwd=ROOT)
        cls.artifact = json.loads(out.read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_it_never_claims_a_write(self):
        self.assertFalse(self.artifact['db_write'])
        self.assertEqual(self.artifact['supabase_write'], 'NONE')
        policy = self.artifact['write_policy']
        for word in ('DELETE', 'TRUNCATE', 'bulk UPDATE'):
            self.assertIn(word, policy)

    def test_the_existing_130_are_updates_not_new_projects(self):
        baseline = self.artifact['existing_baseline']
        self.assertEqual(baseline['rows'], 130)
        self.assertEqual(baseline['by_district'], {'강동구': 40, '서초구': 56, '송파구': 34})
        self.assertEqual(baseline['matched_as_update'], 130)
        # 하나라도 insert로 분류되면 중복 프로젝트가 생긴다.
        self.assertEqual(baseline['recreated_as_insert'], 0)

    def test_every_upsert_row_names_its_operation(self):
        rows = self.artifact['upsert']
        self.assertEqual(len(rows), self.artifact['totals']['valid_projects'])
        self.assertEqual(sum(r['operation'] == 'update' for r in rows), 130)
        self.assertTrue(all(r['operation'] in ('insert', 'update') for r in rows))
        self.assertEqual(len({r['project_id'] for r in rows}), len(rows))

    def test_identity_version_is_unchanged(self):
        self.assertEqual(self.artifact['identity_normalizer'], 'seoul-identity-v1')
        self.assertEqual(dc.IDENTITY_NORMALIZER_VERSION, 'seoul-identity-v1')

    def test_zero_districts_distinguish_no_data_from_failure(self):
        reasons = {v['zero_reason'] for d, v in self.artifact['coverage'].items()
                   if v['raw'] == 0}
        self.assertTrue(reasons)
        # '사업이 없음'과 '수집 실패'가 같은 값으로 뭉쳐지면 안 된다.
        self.assertTrue(reasons <= {'NO_DATA_AT_SOURCE', 'COLLECTION_FAILED',
                                    'INCOMPLETE_COLLECTION', 'NOT_COLLECTED'})
        # 건수가 있는 자치구에 0건 사유가 붙으면 안 된다.
        for district, row in self.artifact['coverage'].items():
            if row['raw']:
                self.assertIsNone(row['zero_reason'], district)

    def test_a_project_without_a_coordinate_still_reaches_the_db(self):
        """좌표가 없어도 공식 개발정보다. 적재 대상에서 빼지 않는다."""
        rows = self.artifact['upsert']
        without = [r for r in rows if not r['has_coordinate']]
        self.assertTrue(without)
        # no_coordinate는 별도 집계일 뿐이고, upsert에서 빠지지 않는다.
        self.assertEqual(self.artifact['buckets']['no_coordinate'], len(without))
        self.assertEqual(len(rows), self.artifact['totals']['valid_projects'])
        self.assertEqual(self.artifact['buckets']['insert'] + self.artifact['buckets']['update'],
                         len(rows))

    def test_duplicate_pairs_are_preserved_not_merged(self):
        pairs = self.artifact['duplicate_review']
        self.assertEqual(len(pairs), self.artifact['buckets']['duplicate_review'])
        self.assertTrue(all(pair['auto_merge'] is False for pair in pairs))
        # 쌍에 걸린 사업도 upsert에 남는다. 자동 삭제/병합하지 않는다.
        flagged = {pid for pair in pairs for pid in pair['candidate_ids']}
        present = {row['project_id'] for row in self.artifact['upsert']}
        self.assertEqual(flagged - present, set())

    def test_a_wrong_district_coordinate_is_rejected(self):
        record = {'project_id': 'x', 'project_name': 'n', 'project_type': 'RECONSTRUCTION',
                  'sigungu': '성동구', 'location': 'SRID=4326;POINT(126.9 37.56)',
                  'location_sigungu': '마포구', 'source': {'source_url': 'https://x.invalid'}}
        import importlib.util
        spec = importlib.util.spec_from_file_location('builder', SCRIPT)
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        self.assertIn('LOCATION_SIGUNGU_MISMATCH',
                      builder.row_rejections(record, {'성동구'}))
        # 좌표가 아예 없는 것은 reject가 아니다. 목록에는 남아야 한다.
        self.assertEqual(builder.row_rejections(
            dict(record, location=None, location_sigungu=None), {'성동구'}), [])


if __name__ == '__main__':
    unittest.main()
