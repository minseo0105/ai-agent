"""ZIP:ON 개발정보 수집범위 확대 dry-run. Supabase에 아무것도 쓰지 않는다.

  python scripts/dryrun_zipon_districts.py --districts 성동구,마포구,용산구
  python scripts/dryrun_zipon_districts.py --district 성동구
  python scripts/dryrun_zipon_districts.py --all-seoul
  python scripts/dryrun_zipon_districts.py --districts 서초구,송파구,강동구 --replay <captured.json>

입력 모드
  --live      공식 페이지를 실제로 받아온다. 망이 열린 환경에서만 동작한다.
  --replay    이전에 캡처한 수집 artifact의 field_evidence.cells로 공식 표를
              다시 만들어 파서를 통과시킨다. 실데이터 회귀 검증용이다.
  --fixture   캡처가 없는 구를 위한 구조 fixture. 행 내용은 합성이며 artifact에
              synthetic=true로 표시된다. 건수를 공식 실적으로 쓰면 안 된다.

이 스크립트는 읽기만 한다. REST/RPC write 경로를 import하지 않고, --live에서도
수집 결과를 로컬 artifact로만 남긴다. 기존 DB 중복 판정은 baseline id 집합과의
비교이며, 그 집합도 읽기 전용으로만 쓴다.
"""
import argparse
from collections import Counter, defaultdict
import html
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_collector as dc
from services.development_quality import refine

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
DEFAULT_BASELINE = DATA / 'lifecycle_audit_20260929.json'
DEFAULT_CAPTURE = DATA / 'pilot_20260927.json'

# 정보몽땅/모아타운 표의 실제 열 구성. 캡처된 cells에서 그대로 확인한 모양이다.
TYPE_LABEL = {'REDEVELOPMENT': '재개발', 'RECONSTRUCTION': '재건축',
              'SHINTONG': '신속통합기획', 'FAST_TRACK': '신속통합기획', 'MOATOWN': '모아타운'}
STAGE_SAMPLES = ('조합설립인가', '사업시행인가', '관리처분계획인가', '구역지정', '추진위원회승인')


def baseline_ids(path):
    """기존 DB에 이미 있는 project_id 집합. 비교에만 쓰고 수정하지 않는다."""
    if not path or not Path(path).exists():
        return {}, 'BASELINE_UNAVAILABLE'
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    items = payload.get('items') or payload.get('projects') or []
    rows = {}
    for item in items:
        pid = item.get('project_id')
        if pid:
            rows[pid] = item.get('district') or item.get('sigungu')
    return rows, 'BASELINE_SNAPSHOT:' + Path(path).name


def cell(value):
    return '<td>' + html.escape(str(value)) + '</td>'


def table(rows):
    body = ''.join('<tr>' + ''.join(cell(c) for c in cells) + extra + '</tr>'
                   for cells, extra in rows)
    return '<table>' + body + '</table>'


def popup(external_id):
    if not external_id:
        return '<td>-</td>'
    return ('<td><a href="javascript:cafeOpenPopup(\'' + html.escape(external_id)
            + '\');">사업장 지도</a></td>')


def replay_pages(capture, scope):
    """캡처된 cells를 공식 표 모양으로 되돌린다. 셀 값은 캡처 원본 그대로다."""
    by_url = defaultdict(list)
    for record in capture.get('records') or []:
        evidence = record.get('field_evidence') or {}
        cells = evidence.get('cells')
        if not cells or record.get('sigungu') not in scope:
            continue
        by_url[evidence['source_url']].append((list(cells), popup(record.get('external_id'))))
    return {url: table(rows) for url, rows in by_url.items()}


def fixture_pages(scope, per_district=6):
    """캡처가 없는 구용 구조 fixture. 실제 열 구성만 같고 행 내용은 합성이다."""
    pages, index = {}, 0
    directory = defaultdict(list)
    citywide = {'shintong': [], 'reconstruction': [], 'moa': []}
    for district in scope:
        for n in range(per_district):
            index += 1
            stage = STAGE_SAMPLES[index % len(STAGE_SAMPLES)]
            kind = ('재개발', '재건축')[n % 2]
            name = f'{district} FIXTURE-{n + 1:02d} 정비사업조합'
            lot = f'FIXTURE{n + 1}동 {100 + n}-{n + 1}'
            external = f'fixture-{district}-{n + 1:02d}' if n % 3 != 2 else None
            directory[district].append(([str(index), district, kind, name, lot, stage,
                                         f'{index}건', '-', '-', '사업장 지도'], popup(external)))
        citywide['shintong'].append(([str(index), district, f'{district} FIXTURE동 1-1',
                                      '30,700', '781', '시행자지정(조합)', '2026-03-14'], ''))
        citywide['reconstruction'].append(([str(index), '자문', district,
                                            f'{district} FIXTURE단지', '120,000', '2,100',
                                            '통합심의', '2026-09-05'], ''))
        citywide['moa'].append(([str(index), district, f'{district} FIXTURE 모아타운',
                                 '42,000'], ''))
    for source in dc.CITYWIDE_SOURCES:
        pages[source['url']] = table(citywide[source['kind']])
    for district in scope:
        pages[dc.DIRECTORY_URL + dc.SEOUL_SIGNGU_CODE[district]] = table(directory[district])
    return pages


def offline_fetch(pages):
    """fetch 계약만 흉내내는 로컬 응답. 네트워크를 타지 않는다."""
    class Response:
        def __init__(self, url, text):
            self.url, self.content = url, text.encode('utf-8')

        def raise_for_status(self):
            return None

    def fetch(url, timeout=None):
        if url not in pages:
            raise LookupError('NO_LOCAL_PAGE_FOR_SOURCE')
        return Response(url, pages[url])
    return fetch


def classify(project_type):
    return TYPE_LABEL.get(project_type, '기타 개발사업')


# 자치구 일치 검증 경로를 돌려보기 위한 로컬 좌표. 유료 API를 부르지 않으며,
# 여기서 나온 좌표는 검토용도 적재용도 아니다. 네 번째 주소마다 일부러 다른
# 자치구로 답해서 GEOCODE_SIGUNGU_MISMATCH가 실제로 걸러지는지 확인한다.
SELFTEST_POINT = {'성동구': (127.0369, 37.5633), '마포구': (126.9087, 37.5638),
                  '용산구': (126.9654, 37.5326), '서초구': (127.0324, 37.4837),
                  '송파구': (127.1059, 37.5145), '강동구': (127.1238, 37.5301)}


def selftest_provider(scope):
    wrong = {district: list(scope)[(index + 1) % len(scope)]
             for index, district in enumerate(scope)}
    seen = {'n': 0}

    def call(address):
        district = next((d for d in SELFTEST_POINT if d in (address or '')), None)
        if district is None:
            return {'result_status': 'NO_MATCH'}
        seen['n'] += 1
        answered = wrong.get(district, district) if seen['n'] % 4 == 0 else district
        longitude, latitude = SELFTEST_POINT[answered]
        return {'result_status': 'MATCHED', 'accuracy': 'PARCEL',
                'longitude': longitude, 'latitude': latitude,
                'source_url': 'local://selftest',
                'address_elements': {'SIDO': '서울특별시', 'SIGUGUN': answered}}
    return call


def geocode_stage(records, provider):
    """좌표 판정 단계. provider가 없으면 시도 자체를 하지 않는다(추측 금지)."""
    summary = {'attempted': 0, 'accepted': 0, 'rejected': 0, 'no_address': 0,
               'provider': 'NOT_CONFIGURED' if provider is None else 'CONFIGURED',
               'reasons': Counter()}
    out = []
    cache = {}
    for record in records:
        if not record.get('address'):
            summary['no_address'] += 1
            out.append(record)
            continue
        if provider is None:
            out.append(record)
            continue
        summary['attempted'] += 1
        resolved = dc.geocode(record, cache, provider)
        if resolved.get('location'):
            summary['accepted'] += 1
        else:
            summary['rejected'] += 1
            for reason in resolved.get('location_review') or ['NO_GEOCODE_RESULT']:
                summary['reasons'][reason] += 1
        out.append(resolved)
    summary['reasons'] = dict(sorted(summary['reasons'].items()))
    return out, summary


def run(args):
    scope = dc.normalize_districts(dc.SEOUL_DISTRICTS if args.all_seoul
                                   else (args.districts or args.district))
    sources = dc.build_sources(scope)
    mode, synthetic, pages = 'LIVE', False, None
    if args.replay:
        capture = json.loads(Path(args.replay).read_text(encoding='utf-8'))
        pages = replay_pages(capture, set(scope))
        mode, synthetic = 'REPLAY_CAPTURED_EVIDENCE', False
    elif not args.live:
        pages = fixture_pages(scope, args.rows)
        mode, synthetic = 'STRUCTURAL_FIXTURE', True
    fetch = None if pages is None else offline_fetch(pages)

    result = dc.collect(fetch, districts=scope)
    raw = result['records']
    runs = result['runs']
    raw_rows = sum(run['new_count'] + run['unchanged_count'] for run in runs)

    canonical_doc, review_doc, quality = refine(raw)
    canonical = canonical_doc['projects']
    review = review_doc['pairs']
    provider = selftest_provider(scope) if args.geocode_selftest else None
    geocoded, geo = geocode_stage(raw, provider)
    if args.geocode_selftest:
        geo['provider'] = 'LOCAL_SELFTEST_NOT_FOR_IMPORT'
    raw = geocoded

    known, baseline_note = baseline_ids(args.baseline)
    existing = [r for r in raw if r['project_id'] in known]
    fresh = [r for r in raw if r['project_id'] not in known]

    per_region, per_type = {}, Counter()
    for district in scope:
        rows = [r for r in raw if r['sigungu'] == district]
        canon = [c for c in canonical if c['district'] == district]
        per_region[district] = {
            'signgu_code': dc.SEOUL_SIGNGU_CODE[district],
            'raw_rows': len(rows),
            'normalized': len(canon),
            'geocoded': sum(bool(r.get('location')) for r in rows),
            'duplicates_merged': len(rows) - len(canon),
            'new_projects': sum(1 for r in rows if r['project_id'] not in known),
            'update_projects': sum(1 for r in rows if r['project_id'] in known),
            'reject_unknown': sum(1 for r in rows if r.get('status') != 'UNKNOWN'
                                  or r.get('validation_status') != 'NEEDS_REVIEW'),
        }
    for record in raw:
        per_type[classify(record['project_type'])] += 1

    # 지도 안전성: sigungu가 scope 밖이거나 좌표의 자치구와 다른 행은 적재 대상이 아니다.
    map_block = [{'project_id': r['project_id'], 'sigungu': r.get('sigungu'),
                  'reasons': r.get('location_review')}
                 for r in geocoded
                 if r.get('sigungu') not in scope
                 or (r.get('location') and r.get('location_sigungu') != r.get('sigungu'))]

    report = {
        'format': 'zipon-district-expansion-dryrun-v1',
        'generated_at': result['collected_at'],
        'db_write': False,
        'supabase_write': 'NONE',
        'input_mode': mode,
        'synthetic_rows': synthetic,
        'districts': list(scope),
        'signgu_code_system': result['signgu_code_system'],
        'signgu_code_source': result['signgu_code_source'],
        'baseline': baseline_note,
        'stages': {
            '1_raw_rows': raw_rows,
            '2_normalized_canonical': len(canonical),
            '3_deduplicated_removed': quality['exact_duplicates_merged'],
            '3b_probable_duplicate_pairs': quality['probable_duplicate_pairs'],
            '4_geocode': geo,
            '5_type_classification': dict(sorted(per_type.items())),
            '6_identity_generated': len({r['project_id'] for r in raw}),
            '7_existing_db_duplicates': len(existing),
            '8_expected_insert': len(fresh),
            '8_expected_update': len(existing),
        },
        'per_region': per_region,
        'map_safety': {'blocked_rows': len(map_block), 'detail': map_block[:20]},
        'runs': [{k: v for k, v in run.items() if k != 'document_hash'} for run in runs],
        'quality': quality['quality'],
        'duplicate_review_pairs': len(review),
        'identity_normalizer': dc.IDENTITY_NORMALIZER_VERSION,
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                                 encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--district', help='자치구 1개')
    scope.add_argument('--districts', help='쉼표로 구분한 자치구 목록')
    scope.add_argument('--all-seoul', action='store_true', help='서울 25개 자치구 전체')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--live', action='store_true', help='공식 페이지를 실제로 받아온다')
    source.add_argument('--replay', help='캡처된 수집 artifact로 재생')
    parser.add_argument('--rows', type=int, default=6, help='fixture 모드의 구별 사업장 행 수')
    parser.add_argument('--geocode-selftest', action='store_true',
                        help='로컬 좌표로 자치구 일치 검증 경로만 확인한다. 유료 API 호출 없음')
    parser.add_argument('--baseline', default=str(DEFAULT_BASELINE),
                        help='기존 DB project_id 비교용 읽기 전용 snapshot')
    parser.add_argument('--out', help='dry-run artifact 경로')
    args = parser.parse_args()
    if args.districts:
        args.districts = [d for d in re.split(r'[,\s]+', args.districts) if d]
    run(args)


if __name__ == '__main__':
    main()
