"""Official verification, cache, geocode and import-planning guarantees.

These cover only what this sprint added. Migrations, REST compatibility,
PostGIS/RPC postchecks and the canary import are not re-run here.
"""
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_geocode as geo
from services import development_official as official
from services import development_verify as verify

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
LIST_URL = 'https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do?cpage=1&pageSize=100&scupBsnsSttus.signguCode=11740'
SHINTONG_URL = 'https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanSttn2.do'


def record(project_id=None, name='테스트구역', district='강동구', address='서울특별시 강동구 고덕동 212',
           stage='조합설립인가', external_id='abc123', url=LIST_URL, cells=None):
    return {'project_id': project_id or str(uuid.uuid5(uuid.NAMESPACE_URL, name + district + str(external_id))),
            'project_name': name, 'project_type': 'RECONSTRUCTION',
            'official_authority': 'cleanup.seoul.go.kr' if external_id else None,
            'external_id': external_id, 'sido': '서울특별시', 'sigungu': district, 'dong': None,
            'address': address, 'stage': None, 'stage_raw': stage, 'status': 'UNKNOWN',
            'validation_status': 'NEEDS_REVIEW', 'area_m2': None, 'planned_units': None,
            'source_date': None, 'location': None, 'geometry': None, 'geometry_verified': False,
            'revision': 1,
            'field_evidence': {'cells': cells or ['1', district, '재건축', name, address, stage],
                               'source_url': url, 'parser_version': 'seoul-tables-v1',
                               'observed_dates': []},
            'source': {'source_name': '정보몽땅 사업장 목록 ' + district, 'source_type': 'OFFICIAL_WEBSITE',
                       'source_url': url, 'is_official': True, 'external_id': external_id,
                       'published_at': None, 'collected_at': '2026-09-26T23:59:19+00:00',
                       'verified_at': None, 'validation_status': 'UNVERIFIED',
                       'content_hash': 'hash-' + str(external_id), 'raw_snapshot': {}}}


def pair(left, right, reason='NORMALIZED_NAME_AND_DISTRICT'):
    return {'candidate_ids': [left['project_id'], right['project_id']],
            'canonical_ids': ['c-' + left['project_id'], 'c-' + right['project_id']],
            'names': [left['project_name'], right['project_name']], 'reason': reason,
            'decision': 'PROBABLE_DUPLICATE', 'auto_merge': False, 'field_differences': [],
            'evidence': []}


def adjudicate(left, right, details=None, reason='NORMALIZED_NAME_AND_DISTRICT'):
    extracted = {r['project_id']: verify.extract(r) for r in (left, right)}
    for pid, bundle in extracted.items():
        bundle['provenance']['detail']['cache_key'] = official.detail_target(
            {'project_id': pid, 'external_id': extracted[pid]['identity']['official_external_id'],
             'official_authority': extracted[pid]['identity']['source_system'],
             'source': {'source_url': extracted[pid]['provenance']['source_url']}})['cache_key']
    return verify.adjudicate(pair(left, right, reason), extracted, details or {})


class StageStatusTests(unittest.TestCase):
    def test_official_terms_map_into_the_taxonomy(self):
        for raw, expected in [('조합설립인가', 'ASSOCIATION_APPROVED'), ('관리처분인가', 'MANAGEMENT_DISPOSITION'),
                              ('준공인가', 'COMPLETED'), ('이전고시', 'TRANSFER_NOTICE'),
                              ('추진위원회승인', 'COMMITTEE'), ('후보지선정', 'CANDIDATE')]:
            result = official.normalize_stage(raw)
            self.assertEqual(result['normalized_stage'], expected)
            self.assertEqual(result['stage_confidence'], 'OFFICIAL_TERM')
            self.assertIn(expected, official.STAGE_TAXONOMY)

    def test_every_pilot_stage_is_mapped_and_raw_is_kept(self):
        records = json.loads((DATA / 'pilot_20260927.json').read_text(encoding='utf-8'))['records']
        for row in records:
            result = official.normalize_stage(row['stage_raw'])
            self.assertNotEqual(result['normalized_stage'], 'UNKNOWN', row['stage_raw'])
            self.assertIn(result['normalized_stage'], official.STAGE_TAXONOMY)
            self.assertEqual(verify.extract(row)['progress']['raw_stage'], row['stage_raw'])

    def test_unknown_term_is_not_guessed(self):
        result = official.normalize_stage('사업추진중(추정)')
        self.assertEqual(result['normalized_stage'], 'UNKNOWN')
        self.assertEqual(result['normalization_note'], 'UNMAPPED_OFFICIAL_TERM')

    def test_stage_is_never_taken_from_a_project_name(self):
        row = record(name='둔촌주공 준공인가 예정구역', stage='조합설립인가')
        self.assertEqual(verify.extract(row)['progress']['normalized_stage'], 'ASSOCIATION_APPROVED')

    def test_status_only_from_an_official_terminal_stage(self):
        self.assertEqual(official.normalize_status('COMPLETED')['normalized_status'], 'COMPLETED')
        self.assertEqual(official.normalize_status('TRANSFER_NOTICE')['normalized_status'], 'COMPLETED')
        for stage in ('ASSOCIATION_APPROVED', 'ASSOCIATION_DISSOLVED', 'ASSOCIATION_LIQUIDATION',
                      'DEMOLITION', 'UNKNOWN'):
            result = official.normalize_status(stage)
            self.assertEqual(result['normalized_status'], 'UNKNOWN', stage)
            self.assertIsNotNone(result['status_hypothesis'])

    def test_absence_never_becomes_cancelled(self):
        statuses = {official.normalize_status(s)['normalized_status'] for s in official.STAGE_TAXONOMY}
        self.assertNotIn('CANCELLED', statuses)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.cache = official.DetailCache(self.directory)

    def test_external_id_is_requested_once_across_records(self):
        calls = []

        def transport(url, timeout=None):
            calls.append(url)
            raise AssertionError('no detail endpoint is confirmed, so nothing may be requested')
        rows = [record(project_id='a', external_id='same-id'), record(project_id='b', external_id='same-id')]
        result = official.fetch_details([official.detail_target(r) for r in rows], transport, self.cache)
        self.assertEqual(calls, [])
        self.assertEqual([e['result_status'] for e in result['log']],
                         ['NO_CONFIRMED_DETAIL_ENDPOINT', 'DEDUPED_IN_RUN'])
        self.assertEqual(self.cache.requests_avoided, 1)

    def test_same_url_is_fetched_once_and_then_served_from_cache(self):
        page = b'<table><tr><th>\xec\x82\xac\xec\x97\xad\xeb\xaa\x85</th><td>x</td></tr></table>'
        calls = []

        class Response:
            status_code = 200
            content = page
        def transport(url, timeout=None):
            calls.append(url)
            return Response()
        target = official.detail_target(record(external_id=None, project_id='p1'))
        target['detail_url'] = 'https://cleanup.seoul.go.kr/cleanup/bsnssttus/detail.do?id=1'
        official.fetch_details([target, dict(target)], transport, self.cache)
        self.assertEqual(len(calls), 1)
        second = official.DetailCache(self.directory)
        official.fetch_details([target], transport, second)
        self.assertEqual(len(calls), 1)
        self.assertEqual(second.hits, 1)

    def test_records_without_an_identifier_never_share_a_cache_entry(self):
        keys = {official.detail_target(record(external_id=None, project_id=pid, url=SHINTONG_URL))['cache_key']
                for pid in ('p1', 'p2')}
        self.assertEqual(len(keys), 2)

    def test_a_denied_host_is_not_asked_again(self):
        calls = []

        def transport(url, timeout=None):
            calls.append(url)
            raise OSError('policy denial')
        targets = []
        for index in range(4):
            target = official.detail_target(record(external_id=f'id{index}'))
            target['detail_url'] = f'https://cleanup.seoul.go.kr/cleanup/bsnssttus/detail.do?id={index}'
            targets.append(target)
        result = official.fetch_details(targets, transport, self.cache)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(1 for e in result['log'] if e['result_status'] == 'SKIPPED_HOST_UNAVAILABLE'), 3)

    def test_secrets_are_never_written_to_the_cache(self):
        self.cache.put('k1', {'source_url': 'https://cleanup.seoul.go.kr/x', 'cookie': 'SESSION=1',
                              'authorization': 'Bearer t', 'api_key': 'k', 'result_status': 'FETCHED'})
        stored = json.loads(Path(self.directory, 'k1.json').read_text(encoding='utf-8'))
        self.assertNotIn('cookie', stored)
        self.assertNotIn('authorization', stored)
        self.assertNotIn('api_key', stored)

    def test_non_official_host_is_refused(self):
        target = official.detail_target(record())
        target['detail_url'] = 'https://blog.example.com/post'
        result = official.fetch_details([target], lambda *a, **k: None, self.cache)
        self.assertEqual(result['log'][0]['result_status'], 'NON_OFFICIAL_HOST_REFUSED')

    def test_detail_endpoint_is_discovered_not_invented(self):
        self.assertFalse(official.discover_detail_endpoint('<p>목록</p>')['confirmed'])
        found = official.discover_detail_endpoint(
            '<script>function cafeOpenPopup(id){window.open("/cleanup/x/detail.do?code="+id);}</script>')
        self.assertTrue(found['confirmed'])
        self.assertEqual(found['path'], '/cleanup/x/detail.do')
        self.assertFalse(official.detail_target(record())['detail_lookup']['endpoint_confirmed'])


class IdentityTests(unittest.TestCase):
    def test_same_official_identifier_merges(self):
        left = record(project_id='a', name='고덕주공2단지 주택재건축정비사업조합', external_id='in814VyA')
        right = record(project_id='b', name='고덕주공2단지아파트 재건축', external_id='in814VyA')
        result = adjudicate(left, right)
        self.assertEqual(result['decision'], 'SAME_PROJECT')
        self.assertEqual(result['confidence'], 'HIGH')
        self.assertIn('OFFICIAL_EXTERNAL_ID_MATCH', result['basis'])
        self.assertFalse(result['review_required'])

    def test_official_detail_can_confirm_one_business(self):
        left = record(project_id='a', name='방배삼호아파트 주택재건축정비사업', external_id='id-a')
        right = record(project_id='b', name='방배삼호', external_id='id-b')
        fields = {'official_project_name': '방배삼호아파트 주택재건축정비사업',
                  'representative_address': '서울특별시 서초구 방배동 758-4'}
        details = {}
        for row in (left, right):
            details[official.detail_target(row)['cache_key']] = {
                'result_status': 'FETCHED', 'parsed_fields': fields}
        result = adjudicate(left, right, details)
        self.assertEqual(result['decision'], 'SAME_PROJECT')
        self.assertIn('OFFICIAL_DETAIL_SAME_NAME_AND_ADDRESS', result['basis'])

    def test_zone_numbers_are_never_merged(self):
        left = record(project_id='a', name='마천1구역 주택재개발정비사업', external_id='m1')
        right = record(project_id='b', name='마천2구역 주택재개발정비사업', external_id='m2')
        result = adjudicate(left, right)
        self.assertEqual(result['decision'], 'DIFFERENT_PROJECT')
        self.assertIn('OFFICIAL_ZONE_OR_PHASE_MISMATCH', result['basis'])

    def test_zone_letters_are_never_merged(self):
        left = record(project_id='a', name='천호A1구역', external_id='A1')
        right = record(project_id='b', name='천호B1구역', external_id='B1')
        self.assertEqual(adjudicate(left, right)['decision'], 'DIFFERENT_PROJECT')

    def test_different_district_is_never_merged(self):
        left = record(project_id='a', name='현대아파트 재건축', district='강동구',
                      address='서울특별시 강동구 성내동 30-2', external_id='x1')
        right = record(project_id='b', name='현대아파트 재건축', district='송파구',
                       address='서울특별시 송파구 풍납동 30-2', external_id='x2')
        result = adjudicate(left, right)
        self.assertEqual(result['decision'], 'DIFFERENT_PROJECT')
        self.assertIn('OFFICIAL_DISTRICT_MISMATCH', result['basis'])

    def test_different_representative_lot_is_kept_separate(self):
        left = record(project_id='a', name='명일한양 재건축', address='서울특별시 강동구 명일동 54', external_id='h1')
        right = record(project_id='b', name='명일한양 재건축', address='서울특별시 강동구 명일동 99', external_id='h2')
        result = adjudicate(left, right)
        self.assertEqual(result['decision'], 'DIFFERENT_PROJECT')
        self.assertIn('OFFICIAL_REPRESENTATIVE_LOT_MISMATCH', result['basis'])

    def test_program_listing_versus_registry_stays_ambiguous(self):
        registry = record(project_id='a', name='마천2재정비촉진구역 주택재개발정비사업',
                          district='송파구', address='서울특별시 송파구 마천동 183-1', external_id='machun2')
        program = record(project_id='b', name='마천2', district='송파구', address=None,
                         external_id=None, url=SHINTONG_URL)
        result = adjudicate(registry, program)
        self.assertEqual(result['decision'], 'STILL_AMBIGUOUS')
        self.assertIn('PROGRAM_LISTING_VS_BUSINESS_REGISTRY', result['basis'])
        self.assertTrue(result['review_required'])

    def test_name_similarity_alone_never_merges(self):
        left = record(project_id='a', name='서초진흥아파트 주택재건축정비사업조합', external_id=None, url=SHINTONG_URL, address=None)
        right = record(project_id='b', name='서초진흥아파트 주택재건축정비사업', external_id=None, url=SHINTONG_URL, address=None)
        self.assertEqual(adjudicate(left, right)['decision'], 'STILL_AMBIGUOUS')


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.left = record(project_id='a', name='고덕주공2단지 조합', external_id='dup-id')
        self.right = record(project_id='b', name='고덕주공2단지아파트', external_id='dup-id',
                            address='서울특별시 강동구 고덕동 212')
        self.other = record(project_id='c', name='둔촌주공아파트 주택재건축정비사업조합', external_id='dunchon',
                            stage='준공인가')
        self.rows = [self.left, self.right, self.other]
        self.pairs = [pair(self.left, self.right)]

    def build(self, canary=()):
        return verify.build(self.rows, canary, {'projects': []}, self.pairs)

    def test_merge_preserves_every_name_identifier_source_and_raw_record(self):
        projects, resolved = self.build()
        merged = next(p for p in projects if p['raw']['raw_candidate_count'] > 1)
        self.assertEqual(sorted(merged['identity']['original_names']),
                         ['고덕주공2단지 조합', '고덕주공2단지아파트'])
        self.assertEqual(merged['raw']['candidate_ids'], ['a', 'b'])
        self.assertEqual(len(merged['raw']['raw_candidates']), 2)
        self.assertEqual(len(merged['raw']['history']), 2)
        self.assertEqual(merged['duplicate']['class'], 'MERGED_SAME_PROJECT')
        self.assertTrue(merged['duplicate']['merged_evidence'])
        self.assertEqual(merged['raw']['raw_candidates'][0], self.left)

    def test_address_carries_its_official_provenance(self):
        projects, _ = self.build()
        located = next(p for p in projects if p['location']['representative_address'])
        self.assertTrue(located['location']['address_verified'])
        self.assertEqual(located['location']['address_type'], 'LOT')
        self.assertEqual(located['location']['address_source_url'], LIST_URL)
        self.assertEqual(located['location']['dong'], '고덕동')
        self.assertIsNotNone(located['location']['address_verified_at'])

    def test_missing_address_is_not_invented(self):
        rows = [record(project_id='z', name='천호A1-2', external_id=None, address=None, url=SHINTONG_URL)]
        projects, _ = verify.build(rows, (), {'projects': []}, [])
        self.assertIsNone(projects[0]['location']['representative_address'])
        self.assertFalse(projects[0]['location']['address_verified'])
        self.assertIn('NO_OFFICIAL_ADDRESS', projects[0]['quality_reasons'])

    def test_provenance_is_kept_on_every_project(self):
        projects, _ = self.build()
        for project in projects:
            self.assertTrue(project['provenance']['source_url'])
            self.assertTrue(project['provenance']['is_official'])
            self.assertTrue(project['provenance']['content_hash'])
            self.assertTrue(project['provenance']['evidence_fields'])
            self.assertIn('result_status', project['provenance']['detail'])

    def test_presence_in_an_official_list_is_not_verified(self):
        projects, _ = self.build()
        self.assertEqual({p['quality_state'] for p in projects}, {'PARTIALLY_VERIFIED'})
        for project in projects:
            self.assertIn('OFFICIAL_DETAIL_IDENTITY_NOT_READ', project['quality_reasons'])

    def test_representative_point_can_never_claim_inside(self):
        projects, _ = self.build()
        for project in projects:
            self.assertIn(project['spatial_relation_capability'], ('NEARBY_ONLY', 'UNKNOWN'))
        geocoded = {geo.cache_key('서울특별시 강동구 고덕동 212'):
                    {'latitude': 37.55, 'longitude': 127.15, 'coordinate_verified': True,
                     'geocode_confidence': 'EXACT', 'geocode_source': 'vworld:address',
                     'geocoded_at': '2026-09-27T00:00:00+00:00', 'address_used': '서울특별시 강동구 고덕동 212'}}
        projects, _ = verify.build(self.rows, (), {'projects': []}, self.pairs, {}, geocoded)
        located = next(p for p in projects if p['geocoding']['coordinate_verified'])
        self.assertEqual(located['spatial_relation_capability'], 'NEARBY_ONLY')
        self.assertFalse(located['boundary']['boundary_verified'])

    def test_no_polygon_is_produced_without_official_gis(self):
        projects, _ = self.build()
        for project in projects:
            self.assertIsNone(project['boundary']['geometry'])
            self.assertFalse(project['boundary']['boundary_verified'])

    def test_canary_rows_are_excluded_from_import(self):
        projects, _ = self.build(canary=[self.other])
        plan = verify.manifest(projects)
        eligible = [r['project_id'] for batch in plan['batches'] for r in batch['records']]
        self.assertNotIn('c', eligible)
        self.assertEqual(plan['totals']['excluded_existing_canary'], 1)
        self.assertTrue(all(not r['existing_canary'] for batch in plan['batches'] for r in batch['records']))

    def test_batches_never_exceed_ten(self):
        rows = [record(project_id=f'p{i}', name=f'테스트{i}구역', external_id=f'e{i}') for i in range(25)]
        projects, _ = verify.build(rows, (), {'projects': []}, [])
        plan = verify.manifest(projects)
        self.assertEqual(plan['totals']['import_eligible'], 25)
        self.assertEqual([b['size'] for b in plan['batches']], [10, 10, 5])
        self.assertTrue(all(b['requires_operator_approval'] for b in plan['batches']))

    def test_ambiguous_candidates_are_excluded_from_import(self):
        left = record(project_id='x', name='마천2재정비촉진구역 주택재개발정비사업', district='송파구',
                      address='서울특별시 송파구 마천동 183-1', external_id='machun2')
        right = record(project_id='y', name='마천2', district='송파구', address=None,
                       external_id=None, url=SHINTONG_URL)
        projects, resolved = verify.build([left, right], (), {'projects': []}, [pair(left, right)])
        self.assertEqual(resolved[0]['decision'], 'STILL_AMBIGUOUS')
        self.assertTrue(all(p['quality_state'] == 'NEEDS_REVIEW' for p in projects))
        self.assertEqual(verify.manifest(projects)['totals']['import_eligible'], 0)

    def test_rerun_is_deterministic(self):
        def scrub(payload):
            text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            return re.sub(r'"(adjudicated_at|generated_at)": "[^"]*"', '"\\1": ""', text)
        first = self.build()
        second = self.build()
        self.assertEqual(scrub(first), scrub(second))
        self.assertEqual(scrub(verify.manifest(first[0])), scrub(verify.manifest(second[0])))


class GeocodeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.cache = geo.GeocodeCache(self.directory)
        self.response = {'provider': 'vworld:address', 'result_status': 'MATCHED',
                         'candidates': [{'longitude': 127.154, 'latitude': 37.555, 'accuracy': 'PARCEL',
                                         'matched_address': '서울특별시 강동구 고덕동 212'}]}

    def test_one_call_per_normalized_address_then_cache(self):
        calls = []

        def provider(address):
            calls.append(address)
            return self.response
        geo.resolve(['서울특별시 강동구 고덕동 212', '서울시 강동구  고덕동 212',
                     ' 서울특별시 강동구 고덕동 212 '], self.cache, provider)
        self.assertEqual(len(calls), 1)
        again = geo.GeocodeCache(self.directory)
        geo.resolve(['서울특별시 강동구 고덕동 212'], again, provider)
        self.assertEqual(len(calls), 1)
        self.assertEqual(again.hits, 1)

    def test_exact_single_match_is_accepted(self):
        result = geo.evaluate('서울특별시 강동구 고덕동 212', self.response)
        self.assertEqual(result['geocode_confidence'], 'EXACT')
        self.assertTrue(result['coordinate_verified'])
        for field in ('latitude', 'longitude', 'geocode_source', 'geocoded_at', 'address_used'):
            self.assertIsNotNone(result[field])

    def test_multiple_candidates_are_never_auto_accepted(self):
        response = dict(self.response, candidates=self.response['candidates'] * 2)
        result = geo.evaluate('서울특별시 강동구 고덕동 212', response)
        self.assertEqual(result['geocode_confidence'], 'GEOCODE_REVIEW')
        self.assertFalse(result['coordinate_verified'])
        self.assertIsNone(result['latitude'])

    def test_a_mismatching_or_coarse_result_is_not_accepted(self):
        for candidate in ({'matched_address': '서울특별시 송파구 고덕동 212'},
                          {'matched_address': '서울특별시 강동구 고덕동'},
                          {'accuracy': 'DONG_CENTROID'},
                          {'longitude': 139.7, 'latitude': 35.6}):
            response = dict(self.response,
                            candidates=[dict(self.response['candidates'][0], **candidate)])
            self.assertEqual(geo.evaluate('서울특별시 강동구 고덕동 212', response)['geocode_confidence'],
                             'GEOCODE_REVIEW', candidate)

    def test_no_provider_means_unresolved_not_guessed(self):
        result = geo.resolve(['서울특별시 강동구 고덕동 212'], self.cache, None)
        entry = next(iter(result['results'].values()))
        self.assertEqual(entry['geocode_confidence'], 'UNRESOLVED')
        self.assertIsNone(entry['latitude'])
        self.assertEqual(entry['reason'], 'NO_GEOCODE_PROVIDER_CONFIGURED')

    def test_cache_rows_match_the_geocode_cache_contract(self):
        geo.resolve(['서울특별시 강동구 고덕동 212'], self.cache, lambda address: self.response)
        row = self.cache.rows()[0]
        for column in geo.GeocodeCache.COLUMNS:
            self.assertIn(column, row)

    def test_provider_returns_candidates_without_deciding(self):
        payload = {'response': {'status': 'OK', 'refined': {'text': '서울특별시 강동구 고덕동 212'},
                                'result': {'point': {'x': '127.154', 'y': '37.555'}}}}
        provider = geo.vworld_provider('key', 'domain', lambda url, params=None, timeout=None: payload)
        result = provider('서울특별시 강동구 고덕동 212')
        self.assertEqual(result['result_status'], 'MATCHED')
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(geo.evaluate('서울특별시 강동구 고덕동 212', result)['geocode_confidence'], 'EXACT')


class NoDatabaseWriteTests(unittest.TestCase):
    MODULES = ('services/development_verify.py', 'services/development_official.py',
               'services/development_geocode.py', 'scripts/verify_zipon_development.py')

    def test_modules_cannot_reach_a_database(self):
        for name in self.MODULES:
            source = (ROOT / name).read_text(encoding='utf-8')
            for token in ('psycopg', 'supabase', 'rpc/', 'INSERT ', 'UPDATE ', 'DELETE ',
                          "'POST'", "'PATCH'", 'import_batch', 'import_candidate'):
                self.assertNotIn(token, source, f'{name} must not be able to write: {token}')

    def test_reports_declare_no_database_write(self):
        for name in ('pilot_verification_report_20260927.json', 'import_manifest_verified_20260927.json',
                     'pilot_canonical_verified_20260927.json'):
            payload = json.loads((DATA / name).read_text(encoding='utf-8'))
            self.assertFalse(payload['db_write'])

    def test_build_needs_no_transport(self):
        rows = [record(project_id='a')]
        projects, _ = verify.build(rows, (), {'projects': []}, [])
        self.assertEqual(len(projects), 1)


class CollectorRegressionTests(unittest.TestCase):
    """The committed collector lost three regex escapes; identity stays frozen."""

    def setUp(self):
        self.records = json.loads((DATA / 'pilot_20260927.json').read_text(encoding='utf-8'))['records']

    def test_observed_dates_are_reproducible_from_stored_cells(self):
        for row in self.records:
            cells = ' '.join(row['field_evidence']['cells'])
            self.assertEqual(re.findall(r'\d{4}-\d{2}-\d{2}', cells),
                             row['field_evidence']['observed_dates'])

    def test_identity_normalizer_still_reproduces_every_pilot_project_id(self):
        from services.development_collector import IDENTITY_NORMALIZER_VERSION
        self.assertEqual(IDENTITY_NORMALIZER_VERSION, 'seoul-identity-v1')
        sources = {'정보몽땅 신속통합기획 재개발': 'seoul_shintong_redevelopment',
                   '정보몽땅 신속통합기획 재건축': 'seoul_shintong_reconstruction'}
        for row in self.records:
            if row['external_id']:
                identity = 'cleanup:' + row['external_id']
            else:
                identity = f"{sources[row['source']['source_name']]}:{row['sigungu']}:{row['project_name']}"
            self.assertEqual(str(uuid.uuid5(uuid.NAMESPACE_URL, identity)), row['project_id'])

    def test_dong_is_read_past_the_district_token(self):
        self.assertEqual(official.dong_from_address('서울특별시 강동구 고덕동 212', '강동구'), '고덕동')
        self.assertEqual(official.dong_from_address('서울특별시 송파구 송파동 151', '송파구'), '송파동')
        self.assertIsNone(official.dong_from_address(None, '강동구'))
        corrected = [r for r in self.records
                     if r['address'] and official.dong_from_address(r['address'], r['sigungu']) != r['dong']]
        self.assertEqual(len(corrected), 47)

    def test_a_lot_shaped_zone_name_is_an_official_address(self):
        self.assertTrue(re.search(r'[동리가]\s*\d', '천호동 392-9'))
        self.assertIsNone(re.search(r'[동리가]\s*\d', '올림픽훼밀리타운'))


if __name__ == '__main__':
    unittest.main()
