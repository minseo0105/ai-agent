"""서울시 공식 도시계획사업 SHP를 읽어 ZIP:ON 130건과 맞춰 본다. DB write 없음.

원천: 서울 열린데이터광장 "도시계획사업 현황(서울플랜+) 공간정보" (OA-22712)
파일:  532_UQ120_도시계획사업(서울플랜+)_202609.zip
법적 효력 없음 / 참고자료.

  python scripts/analyze_seoul_polygon_source.py --archive data/reference/<파일>.zip --write

원본은 수정하지 않는다. 폴리곤을 만들어 내지 않는다. 대표좌표에 buffer를 씌우지 않는다.
매칭 등급이 EXACT여도 이 스크립트는 데이터베이스에 아무것도 쓰지 않는다.

등급:
  EXACT      공식 식별자가 같거나, 정규화 사업명이 같고 자치구까지 맞으며 후보가 하나뿐이다.
  PROBABLE   신호는 강하지만 자동 반영하기엔 확인이 더 필요하다.
  AMBIGUOUS  후보가 둘 이상이거나 기존 duplicate/identity 충돌이 있다.
  NO_MATCH   안전한 공식 폴리곤 후보가 없다.
이름이 비슷하다는 이유만으로 EXACT가 되지 않는다. 대표좌표의 폴리곤 포함 여부는
보조 확인일 뿐이며 단독으로 동일성을 결정하지 않는다.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_official import compact, now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
REFERENCE = ROOT / 'data/reference'
REVIEW_FILE = DATA / 'polygon_match_review_20260928.json'
GEOJSON_FILE = DATA / 'polygon_match_exact_20260928.geojson'
REGISTRY_FILE = REFERENCE / 'source_registry.json'
SOURCE = {'provider': '서울특별시',
          'dataset': '도시계획사업 현황(서울플랜+) 공간정보',
          'dataset_id': 'OA-22712', 'version': '202609',
          'file': '532_UQ120_도시계획사업(서울플랜+)_202609.zip',
          'portal_url': 'https://data.seoul.go.kr/dataList/OA-22712/S/1/datasetView.do',
          'legal_note': '법적 효력 없음 / 참고자료'}
# 국내 공간정보가 흔히 쓰는 좌표계. .prj를 읽어 정하고, 못 읽으면 추정하지 않는다.
KNOWN_CRS = {'Korea 2000 / Central Belt 2010': 'EPSG:5186',
             'Korea 2000 / Unified Coordinate System': 'EPSG:5179',
             'Korea 2000 / Central Belt': 'EPSG:5181'}
NAME_FIELDS = ('사업명', 'SIGGNM', 'PRJ_NM', 'BSNS_NM', 'NAME', 'LDNM')
TYPE_FIELDS = ('사업구분', '사업유형', 'PRJ_SE', 'BSNS_SE', 'TYPE')
DISTRICT_FIELDS = ('자치구', 'SGG_NM', 'SIGNGU_NM', 'GU')
DONG_FIELDS = ('법정동', 'EMD_NM', 'LEGALDONG', 'DONG')
ID_FIELDS = ('관리번호', '고시번호', 'MNG_NO', 'PRJ_NO', 'NOTI_NO', 'ID')


def pick(record, names):
    """필드명이 DBF의 10바이트 제한으로 잘려 있을 수 있어 양방향으로 본다."""
    for name in names:
        value = record.get(name)
        if value not in (None, '', ' '):
            return str(value).strip()
    for key, value in record.items():
        if value in (None, '', ' '):
            continue
        if any(name in key or key in name for name in names if key):
            return str(value).strip()
    return None


def read_archive(archive):
    """압축을 풀지 않고 읽는다. 원본 파일은 건드리지 않는다."""
    import shapefile
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        stem = next((n[:-4] for n in names if n.lower().endswith('.shp')), None)
        if stem is None:
            raise SystemExit('NO_SHP_IN_ARCHIVE')
        parts = {}
        for extension in ('shp', 'dbf', 'shx'):
            match = next((n for n in names if n.lower() == f'{stem}.{extension}'.lower()), None)
            if match is None:
                raise SystemExit(f'MISSING_{extension.upper()}')
            parts[extension] = bundle.read(match)
        prj = next((n for n in names if n.lower() == f'{stem}.prj'.lower()), None)
        projection = bundle.read(prj).decode('utf-8', 'replace') if prj else None
    import io
    # DBF 인코딩을 단정하지 않는다. 틀린 인코딩으로 읽으면 필드명이 깨지고, 그러면
    # 오류 없이 조용히 '매칭 0건'이 나온다. 한글이 가장 잘 살아나는 것을 고른다.
    best, chosen = None, None
    for encoding in ('cp949', 'utf-8', 'euc-kr', 'latin-1'):
        try:
            candidate = shapefile.Reader(shp=io.BytesIO(parts['shp']), dbf=io.BytesIO(parts['dbf']),
                                         shx=io.BytesIO(parts['shx']), encoding=encoding,
                                         encodingErrors='replace')
            names = ''.join(f[0] for f in candidate.fields[1:])
        except Exception:
            continue
        score = sum(1 for ch in names if '\uac00' <= ch <= '\ud7a3') - names.count('\ufffd') * 2
        if best is None or score > best:
            best, chosen, chosen_encoding = score, candidate, encoding
    if chosen is None:
        raise SystemExit('DBF_UNREADABLE')
    return chosen, projection, stem, chosen_encoding


def source_crs(projection):
    """.prj에서 좌표계를 읽는다. 읽지 못하면 추정하지 않고 None을 돌려준다."""
    if not projection:
        return None, 'NO_PRJ_FILE'
    found = re.search(r'AUTHORITY\["EPSG","(\d+)"\]\s*\]\s*$', projection.strip())
    if found:
        return f'EPSG:{found.group(1)}', 'FROM_PRJ_AUTHORITY'
    for label, code in KNOWN_CRS.items():
        if label.lower() in projection.lower():
            return code, 'FROM_PRJ_NAME'
    return None, 'UNRECOGNISED_PRJ'


def ring_area(ring):
    """부호 있는 면적. Shapefile 규약에서 외곽 ring은 시계방향이라 음수가 된다."""
    total = 0.0
    for index in range(len(ring) - 1):
        x1, y1 = ring[index]
        x2, y2 = ring[index + 1]
        total += x1 * y2 - x2 * y1
    return total / 2


def point_in_ring(point, ring):
    x, y = point
    inside = False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index]
        x2, y2 = ring[index + 1]
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x < crossing:
                inside = not inside
    return inside


def contains(point, outer, holes):
    """외곽 ring 안에 있고 그 구멍에는 들어 있지 않을 때만 True."""
    for ring in outer:
        if not point_in_ring(point, ring):
            continue
        if any(point_in_ring(point, hole) for hole in holes
               if point_in_ring(hole[0], ring)):
            continue
        return True
    return False


def wind(ring, clockwise):
    """GeoJSON(RFC 7946)은 외곽 반시계, 구멍 시계를 요구한다. 좌표는 그대로 두고 순서만 맞춘다."""
    return list(reversed(ring)) if (ring_area(ring) < 0) != clockwise else list(ring)


def to_wgs84(shape, transformer):
    """SHP geometry를 EPSG:4326 GeoJSON으로 바꾼다. 좌표를 만들어 내지 않는다.

    외곽/구멍 판정을 뒤집어 읽으면 서로 떨어진 두 구역이 '구멍 뚫린 한 구역'으로
    바뀐다. 그래서 Shapefile 규약(외곽=시계방향=음수 면적)을 그대로 따른다.
    """
    points = [transformer(x, y) for x, y in shape.points] if transformer else list(shape.points)
    parts = list(shape.parts) + [len(points)]
    rings = [points[parts[i]:parts[i + 1]] for i in range(len(parts) - 1)]
    rings = [ring for ring in rings if len(ring) >= 4]
    if not rings:
        return None, [], [], 'NO_RING'
    closed = all(ring[0] == ring[-1] for ring in rings)
    outer = [ring for ring in rings if ring_area(ring) < 0]
    holes = [ring for ring in rings if ring_area(ring) >= 0]
    if not outer:
        # 규약을 지키지 않은 원천. 면적이 가장 큰 ring을 외곽으로 보고 나머지를 구멍으로 둔다.
        largest = max(rings, key=lambda ring: abs(ring_area(ring)))
        outer = [largest]
        holes = [ring for ring in rings if ring is not largest]
    groups = [[wind(ring, False)] for ring in outer]
    for hole in holes:
        index = next((i for i, ring in enumerate(outer) if point_in_ring(hole[0], ring)), 0)
        groups[index].append(wind(hole, True))
    if len(groups) == 1:
        geometry = {'type': 'Polygon',
                    'coordinates': [[list(p) for p in ring] for ring in groups[0]]}
    else:
        geometry = {'type': 'MultiPolygon',
                    'coordinates': [[[list(p) for p in ring] for ring in group]
                                    for group in groups]}
    return geometry, outer, holes, ('VALID' if closed else 'RING_NOT_CLOSED')


def load_projects():
    canonical = json.loads((DATA / 'pilot_canonical_verified_20260927.json')
                           .read_text(encoding='utf-8'))['projects']
    baseline = json.loads((DATA / 'db_baseline_20260927.json').read_text(encoding='utf-8'))['projects']
    bulk = json.loads((DATA / 'bulk_import_result_20260927.json').read_text(encoding='utf-8'))
    stored = {p['project_id'] for p in baseline} | {i for b in bulk['batches'] for i in b['project_ids']}
    coordinates = {row['project_id']: row for row in
                   json.loads((DATA / 'bulk_geocode_result_20260927.json')
                              .read_text(encoding='utf-8'))['items']}
    projects = []
    for project in canonical:
        project_id = project['raw']['candidate_ids'][0]
        if project_id not in stored:
            continue
        located = coordinates.get(project_id) or {}
        projects.append({
            'project_id': project_id,
            'project_name': project['identity']['official_project_name'],
            'official_external_id': project['identity']['official_external_id'],
            'project_type': project['classification']['canonical_project_type'],
            'program': project['classification']['program'],
            'district': project['location']['district'], 'dong': project['location']['dong'],
            'address': project['location']['representative_address'],
            'lot_number': project['location']['lot_number'],
            'latitude': located.get('latitude') if located.get('outcome') == 'ACCEPTED' else None,
            'longitude': located.get('longitude') if located.get('outcome') == 'ACCEPTED' else None,
        })
    return projects


def conflicted_ids():
    """기존에 사람이 판단하기로 남겨 둔 건은 자동 등급을 올리지 않는다."""
    ids = set()
    review = DATA / 'fast_track_identity_review_20260928.json'
    if review.exists():
        for row in json.loads(review.read_text(encoding='utf-8'))['items']:
            if row['identity_status'] == 'IDENTITY_CONFLICT' or row.get('duplicate_risk'):
                ids.add(row['project_id'])
                for candidate in row['identity_evidence']['candidates']:
                    ids.add(candidate['registry_project_id'])
    gaps = DATA / 'geocode_gap_review_20260928.json'
    if gaps.exists():
        for row in json.loads(gaps.read_text(encoding='utf-8'))['items']:
            if row['recommended_action'] in ('MANUAL_REVIEW', 'NEEDS_IDENTITY_REVIEW'):
                ids.add(row['project_id'])
    return ids


def match(project, records, protected):
    """식별자 → 정규화 사업명 → 사업명+자치구+동 → 주소 순으로 본다."""
    signals, candidates = [], []
    key = compact(project['project_name'])
    for record in records:
        hit = []
        if project['official_external_id'] and record['official_id'] \
                and project['official_external_id'] == record['official_id']:
            hit.append('OFFICIAL_ID')
        if record['name'] and compact(record['name']) == key:
            hit.append('NAME_EXACT')
        elif record['name'] and len(key) >= 3 and key in compact(record['name']):
            hit.append('NAME_CONTAINED')
        if record['district'] and project['district'] and record['district'] == project['district']:
            hit.append('DISTRICT')
        if record['dong'] and project['dong'] and record['dong'] == project['dong']:
            hit.append('DONG')
        if project['lot_number'] and record['address'] and project['lot_number'] in record['address']:
            hit.append('LOT')
        if any(s in hit for s in ('OFFICIAL_ID', 'NAME_EXACT', 'NAME_CONTAINED')):
            candidates.append({'record': record, 'signals': hit})
    if not candidates:
        return 'NO_MATCH', None, signals, '이름이나 식별자로 이어지는 공식 record가 없습니다.'
    if project['project_id'] in protected:
        return ('AMBIGUOUS', None, [c['signals'] for c in candidates],
                '기존 duplicate/identity 검토 대상이라 폴리곤으로 동일성을 정하지 않습니다.')
    strong = [c for c in candidates
              if 'OFFICIAL_ID' in c['signals']
              or ('NAME_EXACT' in c['signals'] and 'DISTRICT' in c['signals'])]
    if len(strong) == 1 and len(candidates) == 1:
        return 'EXACT', strong[0], strong[0]['signals'], '공식 식별자 또는 정규화 사업명과 자치구가 일치하고 후보가 하나뿐입니다.'
    if len(candidates) > 1:
        return ('AMBIGUOUS', None, [c['signals'] for c in candidates],
                f'공식 record 후보가 {len(candidates)}건이라 하나로 좁혀지지 않습니다.')
    single = candidates[0]
    return ('PROBABLE', single, single['signals'],
            '신호는 있으나 자동 반영에 필요한 식별자 또는 정규화 사업명 일치가 부족합니다.')


def analyse(archive):
    reader, projection, stem, encoding = read_archive(archive)
    crs, crs_basis = source_crs(projection)
    transformer = None
    if crs and crs != 'EPSG:4326':
        from pyproj import Transformer
        converter = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
        transformer = lambda x, y: converter.transform(x, y)
    fields = [f[0] for f in reader.fields[1:]]
    records, geometry_kinds, invalid = [], {}, 0
    for shape_record in reader.iterShapeRecords():
        attributes = dict(zip(fields, list(shape_record.record)))
        geometry, outer, holes, validity = to_wgs84(shape_record.shape, transformer)
        geometry_kinds[geometry['type'] if geometry else 'NONE'] = \
            geometry_kinds.get(geometry['type'] if geometry else 'NONE', 0) + 1
        if validity != 'VALID':
            invalid += 1
        records.append({'name': pick(attributes, NAME_FIELDS),
                        'official_id': pick(attributes, ID_FIELDS),
                        'type': pick(attributes, TYPE_FIELDS),
                        'district': pick(attributes, DISTRICT_FIELDS),
                        'dong': pick(attributes, DONG_FIELDS),
                        'address': pick(attributes, ('주소', '소재지', 'ADDR', 'LOCATION')),
                        'attributes': attributes, 'geometry': geometry,
                        'outer_rings': outer, 'hole_rings': holes,
                        'geometry_valid': validity == 'VALID', 'validity': validity})
    return {'shapefile': stem, 'dbf_encoding': encoding, 'fields': fields, 'record_count': len(records),
            'geometry_types': geometry_kinds, 'invalid_geometry': invalid,
            'source_crs': crs, 'source_crs_basis': crs_basis, 'projection_wkt': projection,
            'converted_crs': 'EPSG:4326', 'records': records}


def build(archive):
    survey = analyse(archive)
    projects = load_projects()
    protected = conflicted_ids()
    rows, features = [], []
    for project in projects:
        status, chosen, signals, reason = match(project, survey['records'], protected)
        record = (chosen or {}).get('record') if chosen else None
        inside, distance = None, None
        if record and record['outer_rings'] and project['longitude'] is not None:
            point = (project['longitude'], project['latitude'])
            inside = contains(point, record['outer_rings'], record['hole_rings'])
            distance = 0.0 if inside else None
        rows.append({
            'zipon_project_id': project['project_id'],
            'zipon_project_name': project['project_name'],
            'project_type': project['project_type'], 'program': project['program'],
            'official_record_id': (record or {}).get('official_id'),
            'official_name': (record or {}).get('name'),
            'official_type': (record or {}).get('type'),
            'match_status': status, 'match_signals': signals, 'confidence_reason': reason,
            'geometry_type': ((record or {}).get('geometry') or {}).get('type'),
            'geometry_valid': (record or {}).get('geometry_valid'),
            'source_crs': survey['source_crs'], 'converted_crs': survey['converted_crs'],
            'representative_point_inside_polygon': inside,
            'distance_to_polygon_m': distance,
            'source_dataset': SOURCE['dataset'], 'source_version': SOURCE['version']})
        if status == 'EXACT' and record and record['geometry']:
            features.append({'type': 'Feature', 'geometry': record['geometry'],
                             'properties': {'zipon_project_id': project['project_id'],
                                            'zipon_project_name': project['project_name'],
                                            'official_name': record['name'],
                                            'official_record_id': record['official_id'],
                                            'representative_point_inside_polygon': inside,
                                            'review_only': True,
                                            'legal_note': SOURCE['legal_note']}})
    return survey, rows, features


def register(archive):
    """어떤 원천을 어떤 판으로 받았는지만 적는다. 원천 파일은 수정하지 않는다."""
    registry = {'format': 'zipon-source-registry-v1', 'sources': []}
    if REGISTRY_FILE.exists():
        registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
    entry = dict(SOURCE, archive=archive.name, acquired=True,
                 acquisition_status='PRESENT', modified=False,
                 place_under=str(REFERENCE.relative_to(ROOT)))
    others = [s for s in registry.get('sources', [])
              if (s.get('dataset_id'), s.get('version')) != (SOURCE['dataset_id'], SOURCE['version'])]
    registry['sources'] = others + [entry]
    registry['recorded_at'] = now()
    REGISTRY_FILE.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n',
                             encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--archive', type=Path, help='서울시 공식 SHP zip 경로')
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    if args.archive is None or not args.archive.exists():
        print(json.dumps({'status': 'SOURCE_FILE_NOT_PRESENT', 'db_write': False,
                          'expected_file': SOURCE['file'],
                          'portal_url': SOURCE['portal_url'],
                          'place_under': str(REFERENCE.relative_to(ROOT))}, ensure_ascii=False))
        return 0
    survey, rows, features = build(args.archive)
    counts = {}
    for row in rows:
        counts[row['match_status']] = counts.get(row['match_status'], 0) + 1
    review = {'format': 'zipon-polygon-match-review-v1', 'generated_at': now(),
              'db_write': False, 'polygon_written_to_production': False,
              'source': dict(SOURCE, archive=args.archive.name),
              'shapefile': {k: survey[k] for k in
                            ('shapefile', 'dbf_encoding', 'fields', 'record_count', 'geometry_types',
                             'invalid_geometry', 'source_crs', 'source_crs_basis',
                             'converted_crs')},
              'totals': dict(counts, zipon_projects=len(rows),
                             exact_with_valid_polygon=sum(
                                 1 for r in rows if r['match_status'] == 'EXACT'
                                 and r['geometry_valid']),
                             representative_point_inside=sum(
                                 1 for r in rows if r['representative_point_inside_polygon'])),
              'items': rows}
    if args.write:
        REFERENCE.mkdir(parents=True, exist_ok=True)
        REVIEW_FILE.write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        GEOJSON_FILE.write_text(json.dumps(
            {'type': 'FeatureCollection', 'review_only': True,
             'legal_note': SOURCE['legal_note'], 'features': features},
            ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        register(args.archive)
    print(json.dumps({'record_count': survey['record_count'],
                      'geometry_types': survey['geometry_types'],
                      'source_crs': survey['source_crs'], 'totals': review['totals'],
                      'exact_features': len(features), 'db_write': False,
                      'written': bool(args.write)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
