import importlib.util, json, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('ba', ROOT / 'scripts/zipon_boundary_analysis_readonly.py')
ba = importlib.util.module_from_spec(spec); spec.loader.exec_module(ba)

ROWS = [{'project_id': 'a', 'project_name': '천호3 주택재건축정비사업조합', 'sigungu': '강동구', 'dong': None,
         'project_type': 'RECONSTRUCTION', 'external_id': None, 'official_authority': None, 'address': None, 'lon': 127.1, 'lat': 37.5}]


class AnalysisTests(unittest.TestCase):
    def _write(self, text):
        d = tempfile.mkdtemp(); p = Path(d) / 'x.json'; p.write_text(text, encoding='utf-8'); return p

    def test_plain_json_and_mcp_wrapped_formats(self):
        self.assertEqual(ba.load_export(self._write(json.dumps(ROWS)))[0]['project_id'], 'a')
        wrapped = 'Below is...\n<untrusted-data-abc>\n' + json.dumps(ROWS, ensure_ascii=False) + '\n</untrusted-data-abc>\nUse this'
        self.assertEqual(ba.load_export(self._write(json.dumps({'result': wrapped})))[0]['project_name'], ROWS[0]['project_name'])
        self.assertEqual(ba.load_export(self._write(wrapped))[0]['sigungu'], '강동구')

    def test_projects_use_existing_normalizer(self):
        p = ba.to_projects(ROWS)[0]
        self.assertEqual(p['normalized_name'], '천호3')
        self.assertEqual(p['district'], '강동구')

    def test_summary_groups_and_rates(self):
        rows = [dict(match_status=s, auto_apply_candidate=a, excluded_reason=None, official_source_record_id=r,
                     project_type='X', district='D') for s, a, r in
                (('EXACT', True, 'r1'), ('EXACT', False, 'r1'), ('PROBABLE', False, None), ('AMBIGUOUS', False, None), ('NO_MATCH', False, None))]
        s = ba.summarize(rows)
        self.assertEqual(s['by_group'], {'EXACT': 2, 'REVIEW': 2, 'NO_MATCH': 1})
        self.assertEqual(s['auto_apply_candidates'], 1)
        self.assertEqual(s['official_records_claimed_by_multiple_projects'], {'r1': 2})

    def test_refuses_to_write_inside_repository(self):
        with self.assertRaises(SystemExit):
            ba.main(['--archive', 'x.zip', '--out-dir', str(ROOT / 'data/x')])


if __name__ == '__main__':
    unittest.main()
