"""정규화 v2와 중복 레이어 근거. EXACT 판정 기준은 완화되지 않았는지도 함께 고정한다."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import analyze_seoul_polygon_source as pipe  # noqa: E402

try:
    import shapely  # noqa: F401
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def project(name, district='동대문구', ptype='REDEVELOPMENT'):
    n, rules = pipe.normalize_name(name)
    return {'project_id': name, 'project_name': name, 'normalized_name': n, 'normalization_rules': rules,
            'official_external_id': None, 'project_type': ptype, 'program': None, 'district': district,
            'dong': None, 'address': None, 'lot_number': None, 'latitude': None, 'longitude': None}


def record(name, district='동대문구', code='BZ103', ring=None, sid=None):
    n, rules = pipe.normalize_name(name)
    return {'name': name, 'normalized_name': n, 'normalization_rules': rules, 'district': district, 'dong': None,
            'address': None, 'official_id': None, 'source_record_id': sid or name + code,
            'attributes': {'SCLAS_CL': code}, 'outer_rings': [ring] if ring else [], 'hole_rings': []}


SQUARE = [(127.0, 37.0), (127.0, 37.01), (127.01, 37.01), (127.01, 37.0), (127.0, 37.0)]
SHIFTED = [(127.02, 37.0), (127.02, 37.01), (127.03, 37.01), (127.03, 37.0), (127.02, 37.0)]


class NameRulesV2Tests(unittest.TestCase):
    def test_new_notation_differences_collapse(self):
        pairs = (('미아제3구역 주택재개발정비사업조합', '미아3'), ('청파제1구역 재개발정비사업조합', '청파1'),
                 ('69. 양평제12구역 도시환경정비사업조합', '양평12'),
                 ('(가칭)개봉동 153-19번지 일대 주택정비형 재개발사업', '개봉동153-19'),
                 ('전농제9구역 주택정비형 공공재개발사업(LH)', '전농9'),
                 ('(임시)면목동 174-1 일대 민간재개발사업', '면목동174-1'))
        for raw, expected in pairs:
            self.assertEqual(pipe.normalize_name(raw)[0], expected, raw)

    def test_official_and_zipon_spellings_meet(self):
        self.assertEqual(pipe.normalize_name('미아제3구역 주택재개발정비사업조합')[0], pipe.normalize_name('미아3')[0])
        self.assertEqual(pipe.normalize_name('청파제1구역')[0], pipe.normalize_name('청파1구역')[0])

    def test_numbers_and_distinct_names_stay_distinct(self):
        self.assertNotEqual(pipe.normalize_name('미아제3구역')[0], pipe.normalize_name('미아제30구역')[0])
        self.assertNotEqual(pipe.normalize_name('천호3')[0], pipe.normalize_name('천호3-1')[0])
        # 숫자 앞이 아닌 '제'와 이름 전체인 '제N구역'은 건드리지 않는다.
        self.assertEqual(pipe.normalize_name('제일')[0], '제일')
        self.assertEqual(pipe.normalize_name('제1구역')[0], '제1')

    def test_v2_never_changes_names_v1_already_handled(self):
        for raw in ('천호1 도시환경정비사업조합', '천호3 주택재건축정비사업조합', '마천2재정비촉진구역 주택재개발정비사업',
                    '신반포5차아파트 주택재건축정비사업 조합', '구로동 451번지 일대 가로주택정비사업',
                    '천호동 397-419번지 일대 주택정비형재개발사업조합', '천호 A1-1구역 공공재개발 정비사업 주민대표회의'):
            self.assertEqual(pipe.normalize_name(raw)[0], pipe.normalize_name_v1(raw)[0], raw)

    def test_new_rules_are_recorded(self):
        self.assertIn('ORDINAL_JE', pipe.normalize_name('미아제3구역')[1])
        self.assertIn('LEADING_SERIAL', pipe.normalize_name('69. 양평제12구역')[1])
        self.assertIn('PROVISIONAL_PREFIX', pipe.normalize_name('(가칭)개봉동 153-19')[1])


class ExactCriteriaUnchangedTests(unittest.TestCase):
    def test_exact_still_needs_unique_candidate_and_district(self):
        status, chosen, _, _ = pipe.match(project('미아제3구역 주택재개발정비사업조합', '강북구'),
                                           [record('미아3', '강북구')], set())
        self.assertEqual(status, 'EXACT')
        # 자치구가 다르면 이름이 같아도 후보가 아니다.
        self.assertEqual(pipe.match(project('미아제3구역', '강북구'), [record('미아3', '성북구')], set())[0], 'NO_MATCH')

    def test_two_same_name_rows_stay_ambiguous_even_when_geometry_is_identical(self):
        recs = [record('상도15', '동작구', 'BZ103', SQUARE, 'a'), record('상도15구역', '동작구', 'BZ101', SQUARE, 'b')]
        status, chosen, _, reason = pipe.match(project('상도15구역 주택정비형 재개발사업', '동작구'), recs, set())
        self.assertEqual((status, chosen), ('AMBIGUOUS', None))
        self.assertIn('후보', reason)

    def test_short_names_still_cannot_reach_exact(self):
        status, _, _, _ = pipe.match(project('현대연립 주택재건축정비사업조합', '송파구', 'RECONSTRUCTION'),
                                     [record('현대', '송파구', 'BZ105')], set())
        self.assertEqual(status, 'PROBABLE')

    def test_a_zipon_side_name_collision_is_still_ambiguous(self):
        a, b = project('미아제3구역', '강북구'), project('미아3구역 재개발', '강북구')
        collisions = {(a['normalized_name'], '강북구'): 2}
        self.assertEqual(pipe.match(a, [record('미아3', '강북구')], set(), collisions)[0], 'AMBIGUOUS')


@unittest.skipUnless(HAS_SHAPELY, 'shapely not available')
class DuplicateLayerEvidenceTests(unittest.TestCase):
    def cands(self, *recs):
        return [{'record': r, 'signals': []} for r in recs]

    def test_identical_stacked_rows_are_flagged_but_never_merged(self):
        ev = pipe.layer_duplicate_evidence(self.cands(record('상도15', code='BZ103', ring=SQUARE, sid='a'),
                                                       record('상도15구역', code='BZ101', ring=SQUARE, sid='b')))
        self.assertTrue(ev['looks_like_stacked_rows'])
        self.assertEqual(ev['min_pairwise_iou'], 1.0)
        self.assertIs(ev['auto_merge'], False)
        self.assertEqual(sorted(ev['candidate_record_ids']), ['a', 'b'])

    def test_distinct_shapes_are_not_flagged(self):
        ev = pipe.layer_duplicate_evidence(self.cands(record('상도15', ring=SQUARE, sid='a'),
                                                       record('상도15구역', ring=SHIFTED, sid='b')))
        self.assertFalse(ev['looks_like_stacked_rows'])

    def test_same_shape_but_different_names_is_not_flagged(self):
        ev = pipe.layer_duplicate_evidence(self.cands(record('상도15', ring=SQUARE, sid='a'),
                                                       record('상도151', ring=SQUARE, sid='b')))
        self.assertFalse(ev['looks_like_stacked_rows'])


class TypeConsistencyTests(unittest.TestCase):
    def test_family_and_consistency(self):
        self.assertEqual(pipe.type_consistency('REDEVELOPMENT', record('a', code='BZ103')), 'CONSISTENT')
        self.assertEqual(pipe.type_consistency('REDEVELOPMENT', record('a', code='BZ105')), 'MISMATCH')
        self.assertEqual(pipe.type_consistency('RECONSTRUCTION', record('a', code='BZ202')), 'MISMATCH')
        self.assertEqual(pipe.type_consistency('SHINTONG', record('a', code='BZ105')), 'CONSISTENT')
        self.assertEqual(pipe.type_consistency('REDEVELOPMENT', {'attributes': {}}), 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()


class ExactExclusionTests(unittest.TestCase):
    ok = {'geometry_valid': True, 'attributes': {'SCLAS_CL': 'BZ103'}}

    def test_exclusions_only_ever_add_to_the_old_ones(self):
        self.assertIsNone(pipe.exact_exclusion('EXACT', self.ok, True, 'REDEVELOPMENT'))
        self.assertEqual(pipe.exact_exclusion('EXACT', {**self.ok, 'geometry_valid': False}, True, 'REDEVELOPMENT'), 'GEOMETRY_NOT_VALID')
        self.assertEqual(pipe.exact_exclusion('EXACT', self.ok, False, 'REDEVELOPMENT'), 'REPRESENTATIVE_POINT_OUTSIDE_POLYGON')
        self.assertEqual(pipe.exact_exclusion('EXACT', self.ok, None, 'REDEVELOPMENT'), 'NO_REPRESENTATIVE_POINT')
        self.assertIsNone(pipe.exact_exclusion('PROBABLE', self.ok, True, 'REDEVELOPMENT'))

    def test_official_type_mismatch_is_not_auto_applied(self):
        street = {'geometry_valid': True, 'attributes': {'SCLAS_CL': 'BZ202'}}
        self.assertEqual(pipe.exact_exclusion('EXACT', street, True, 'SHINTONG'), 'OFFICIAL_TYPE_MISMATCH')
