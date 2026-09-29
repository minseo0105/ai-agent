"""서울시 공식 도시계획사업 SHP를 읽어 ZIP:ON 130건과 맞춰 본다. DB write 없음.

원천: 서울 열린데이터광장 "도시계획사업 현황(서울플랜+) 공간정보" (OA-22712)
파일:  532_UQ120_도시계획사업(서울플랜+)_202609.zip
법적 효력 없음 / 참고자료.

  python scripts/analyze_seoul_polygon_source.py --archive data/reference/<파일>.zip --write
  python scripts/analyze_seoul_polygon_source.py --archive <파일>.zip --if-changed --write

원본은 수정하지 않는다. 폴리곤을 만들어 내지 않는다. 대표좌표에 buffer를 씌우지 않는다.
매칭 등급이 EXACT여도 이 스크립트는 데이터베이스에 아무것도 쓰지 않는다.

필드명을 추측하지 않는다. 뜻이 이름으로 분명한 필드만 매칭에 쓰고, 코드값 필드는
압축 안의 코드정의표로 뜻을 확인한 것만 쓴다. 확인하지 못한 필드는 UNCONFIRMED로
남겨 두고 사람이 볼 수 있게 표본만 적는다.

등급:
  EXACT      공식 식별자가 같거나, 정규화 사업명이 같고 자치구까지 맞으며 후보가 하나뿐이다.
  PROBABLE   신호는 강하지만 자동 반영하기엔 확인이 더 필요하다.
  AMBIGUOUS  후보가 둘 이상이거나 기존 duplicate/identity 충돌이 있다.
  NO_MATCH   안전한 공식 폴리곤 후보가 없다.
이름이 비슷하다는 이유만으로 EXACT가 되지 않는다. 대표좌표의 폴리곤 포함 여부는
보조 확인일 뿐이며 단독으로 동일성을 결정하지 않는다.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_official import compact, now
from services.realestate_monitor import REGION_LAWD

ROOT = Path(__file__).resolve().parents[1]


def shown(path):
    """보고용 경로. 저장소 밖이면 그대로 적는다."""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


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
# 변환 결과가 서울이어야 한다. 이 밖으로 나가면 좌표계를 잘못 읽은 것이므로 매칭하지 않는다.
SANITY_LON = (126.0, 128.0)
SANITY_LAT = (37.0, 38.0)
# 서울 자치구 코드. services/realestate_monitor.py의 검증된 표에서 가져온다(추측 아님).
SEOUL_SGG = {code: label.split(' > ')[1] for label, code in REGION_LAWD.items()
             if label.startswith('서울 > ')}

# 역할별 필드. 앞쪽은 이름 자체로 뜻이 분명한 필드, 뒤쪽은 공식 스펙에서 이름만 아는 필드로
# 코드정의표나 검증된 코드 목록으로 뜻을 확인해야 매칭에 쓴다.
ROLE_FIELDS = {
    'name': (('사업명', '사업명칭', '지구명', 'PRJ_NM', 'BSNS_NM', 'SIGNGNM'),
             ('DGM_NM', 'NAME', 'LDNM')),
    'district': (('자치구', 'SGG_NM', 'SIGNGU_NM', 'GU'),
                 ('SIGNGU_SE', 'SIGNGU_CD', 'SGG_CD')),
    'dong': (('법정동', 'EMD_NM', 'LEGALDONG', 'DONG'), ('EMD_CD', 'LEGALDONG_CD')),
    'type': (('사업구분', '사업유형', 'PRJ_SE', 'BSNS_SE'), ('PROPEL_CD', 'TYPE', 'UQ_CD')),
    'official_id': (('관리번호', '고시번호', 'MNG_NO', 'PRJ_NO', 'NOTI_NO'),
                    ('PRESENT_SN', 'ID')),
    'address': (('주소', '소재지', '위치', 'ADDR', 'LOCATION'), ()),
    'created': (('작성일', '생성일', '고시일'), ('CREATE_DAT', 'CREATE_DT')),
}
# 이름으로 뜻이 분명하거나 코드정의표로 확인된 역할만 매칭에 쓴다.
CONFIRMED_BASES = ('FIELD_NAME', 'OFFICIAL_DATASET_FIELD', 'CODE_TABLE',
                   'CODE_TABLE_FIELD_LABEL', 'SEOUL_DISTRICT_CODE')
# 이 역할들은 값 자체를 읽을 수 있어야 쓸 수 있다. 코드정의표로 풀리지 않은 코드값이면
# 필드의 뜻을 알아도 값을 비교할 수 없으므로 매칭에 쓰지 않는다(PROPEL_CD의 PP0103 같은 경우).
ROLES_NEEDING_DECODED_VALUES = ('name', 'district', 'dong', 'type', 'address')
# 코드정의표가 필드 설명을 줄 때, 그 설명으로 역할을 확인한다. 설명이 없으면 쓰지 않는다.
FIELD_LABEL_KEYWORDS = {
    'name': ('사업명', '지구명', '구역명', '도형명', '명칭'),
    'district': ('자치구', '시군구', '구 코드', '구코드'),
    'dong': ('법정동', '행정동', '읍면동'),
    'type': ('사업구분', '사업유형', '추진구분', '추진', '용도지역지구'),
    'official_id': ('관리번호', '고시번호', '일련번호', '순번'),
    'address': ('주소', '소재지', '위치'),
    'created': ('작성일', '생성일', '고시일', '입력일'),
}
# 이 데이터셋에 한정한 schema mapping. 다른 shapefile에 무조건 적용하지 않는다.
# UQ120 레이어의 DGM_NM은 공식 도형/사업 명칭이고, PRESENT_SN은 원천 record 식별자다.
DATASET_PROFILES = (
    {'id': 'OA-22712/UPIS_C_UQ120',
     'dataset_id': 'OA-22712',
     'layer': 'UPIS_C_UQ120',
     'match': ('UQ120',),
     'roles': {'name': 'DGM_NM'},
     'source_record_id': 'PRESENT_SN',
     'note': '서울시 도시계획사업(서울플랜+) 공간정보 UQ120 레이어. '
             'DGM_NM=공식 도형/사업 명칭, PRESENT_SN=원천 record 식별자(ZIP:ON id와 다른 namespace).'},
)
# 사업명 정규화. 표기 차이만 걷어내고 고유명칭은 남긴다. 규칙을 순서대로 적고 기록한다.
# 너무 많이 지우면 서로 다른 사업이 같은 이름이 되므로, 지운 뒤 2글자 미만이면 되돌린다.
NAME_ORG_SUFFIXES = ('조합설립추진위원회', '주민대표회의', '추진위원회', '준비위원회', '조합')
NAME_SCHEME_SUFFIXES = (
    '주택정비형재개발정비사업', '도시정비형재개발정비사업', '주택정비형재개발사업',
    '도시정비형재개발사업', '주택재개발정비사업', '주택재건축정비사업',
    '소규모재건축정비사업', '가로주택정비사업', '자율주택정비사업', '소규모주택정비사업',
    '도시환경정비사업', '재개발정비사업', '재건축정비사업', '공공재개발정비사업',
    '역세권장기전세주택', '장기전세주택', '정비사업', '재개발사업', '재건축사업', '개발사업')
NAME_AREA_SUFFIXES = ('재정비촉진구역', '재정비촉진지구', '정비구역', '예정구역', '촉진구역',
                      '정비예정구역', '번지일대', '구역', '지구', '일대', '번지')
NAME_BUILDING_SUFFIXES = ('아파트', '연립주택', '연립', '빌라')
NAME_RULES = (('ORG_SUFFIX', NAME_ORG_SUFFIXES),
              ('SCHEME_SUFFIX', NAME_SCHEME_SUFFIXES),
              ('AREA_SUFFIX', NAME_AREA_SUFFIXES),
              ('BUILDING_SUFFIX', NAME_BUILDING_SUFFIXES))
NAME_MIN_LENGTH = 2

# 하위 호환: 기존 호출부/테스트가 쓰는 이름.
NAME_FIELDS = ROLE_FIELDS['name'][0] + ROLE_FIELDS['name'][1]
TYPE_FIELDS = ROLE_FIELDS['type'][0] + ROLE_FIELDS['type'][1]
DISTRICT_FIELDS = ROLE_FIELDS['district'][0] + ROLE_FIELDS['district'][1]
DONG_FIELDS = ROLE_FIELDS['dong'][0] + ROLE_FIELDS['dong'][1]
ID_FIELDS = ROLE_FIELDS['official_id'][0] + ROLE_FIELDS['official_id'][1]
KNOWN_CRS = {'Korea 2000 / Central Belt 2010': 'EPSG:5186',
             'Korea 2000 / Unified Coordinate System': 'EPSG:5179',
             'Korea 2000 / Central Belt': 'EPSG:5181'}


def dataset_profile(stem, archive_name=None):
    """이 원천이 알려진 공식 데이터셋인지. 아니면 None(일반 shapefile로 다룬다).

    레이어 이름으로만 판단한다. 압축 파일명은 바뀌기 쉽고, 파일명만 비슷한 다른 레이어에
    이 데이터셋 전용 mapping을 적용하면 엉뚱한 칸을 사업명으로 읽는다.
    """
    name = (stem or '').upper()
    for profile in DATASET_PROFILES:
        if any(token.upper() in name for token in profile['match']):
            return profile
    return None


def normalize_name(value):
    """사업명 정규화. (정규화된 이름, 적용한 규칙) 을 돌려준다.

    공백과 괄호는 없애지만 괄호 안 내용은 남긴다('(1구역)'을 지우면 서로 다른 구역이
    같은 이름이 된다). 사업 방식·조합 표기 같은 꼬리만 떼고 고유명칭과 숫자는 건드리지
    않는다. 떼어 낸 뒤 너무 짧아지면 되돌린다.
    """
    if not value:
        return None, []
    rules = []
    text = compact(value)
    if text != value:
        rules.append('COMPACT_WHITESPACE')
    unwrapped = re.sub(r'[()\[\]{}〈〉<>「」『』]', '', text)
    if unwrapped != text:
        rules.append('UNWRAP_BRACKETS')
        text = unwrapped
    stripped = text.replace('·', '').replace('.', '').replace(',', '')
    if stripped != text:
        rules.append('DROP_PUNCTUATION')
        text = stripped
    changed = True
    while changed:
        changed = False
        for label, suffixes in NAME_RULES:
            for suffix in sorted(suffixes, key=len, reverse=True):
                if text.endswith(suffix) and len(text) - len(suffix) >= NAME_MIN_LENGTH:
                    text = text[:-len(suffix)]
                    if label not in rules:
                        rules.append(label)
                    changed = True
                    break
            if changed:
                break
    return (text or None), rules


def pick(record, names):
    """필드명이 DBF의 길이 제한으로 잘려 있을 수 있어 양방향으로 본다."""
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


def field_for(fields, names):
    """역할에 해당하는 실제 필드명을 돌려준다. 없으면 None.

    DBF 필드명은 길이 제한으로 잘려 있을 수 있어 포함 관계도 본다. 다만 짧은 조각은
    보지 않는다. 'GU'가 'SIGNGU_SE'에 걸리면 코드값 필드를 이름 필드로 착각한다.
    """
    for name in names:
        if name in fields:
            return name
    for field in fields:
        for name in names:
            if not field or not name:
                continue
            if len(min(field, name, key=len)) < 4:
                continue
            if name in field or field in name:
                return field
    return None


# --------------------------------------------------------------------------- 압축 읽기

def read_archive(archive):
    """압축을 풀지 않고 읽는다. 원본 파일은 건드리지 않는다."""
    import shapefile
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        stems = sorted({n[:-4] for n in names if n.lower().endswith('.shp')})
        if not stems:
            raise SystemExit('NO_SHP_IN_ARCHIVE')
        stem = stems[0]
        parts = {}
        for extension in ('shp', 'dbf', 'shx'):
            match = next((n for n in names if n.lower() == f'{stem}.{extension}'.lower()), None)
            if match is None:
                raise SystemExit(f'MISSING_{extension.upper()}')
            parts[extension] = bundle.read(match)
        prj = next((n for n in names if n.lower() == f'{stem}.prj'.lower()), None)
        projection = bundle.read(prj).decode('utf-8', 'replace') if prj else None
        tables = [n for n in names if n.lower().endswith(('.xlsx', '.xls', '.csv'))
                  and not n.startswith('__MACOSX')]
        code_table_rows, code_table_file = read_code_table(bundle, tables)
        extra_shapefiles = stems[1:]
    # DBF 인코딩을 단정하지 않는다. 틀린 인코딩으로 읽으면 값이 깨지고, 그러면
    # 오류 없이 조용히 '매칭 0건'이 나온다. 한글이 가장 잘 살아나는 것을 고른다.
    # 필드명만 보면 안 된다. UPIS처럼 필드명이 모두 영문이면 어느 인코딩이든 점수가 0이라
    # 순서상 먼저 온 것이 뽑히고, 정작 한글인 값이 깨진 채로 넘어간다. 값까지 본다.
    best, chosen, chosen_encoding = None, None, None
    for encoding in ('cp949', 'utf-8', 'euc-kr', 'latin-1'):
        try:
            candidate = shapefile.Reader(shp=io.BytesIO(parts['shp']), dbf=io.BytesIO(parts['dbf']),
                                         shx=io.BytesIO(parts['shx']), encoding=encoding,
                                         encodingErrors='replace')
            sample = [f[0] for f in candidate.fields[1:]]
            for index, record in enumerate(candidate.iterRecords()):
                if index >= 20:
                    break
                sample.extend(str(value) for value in list(record))
        except Exception:
            continue
        text = ''.join(sample)
        score = sum(1 for ch in text if '가' <= ch <= '힣') - text.count('�') * 2
        if best is None or score > best:
            best, chosen, chosen_encoding = score, candidate, encoding
    if chosen is None:
        raise SystemExit('DBF_UNREADABLE')
    return {'reader': chosen, 'projection': projection, 'shapefile': stem,
            'dbf_encoding': chosen_encoding, 'code_table_rows': code_table_rows,
            'code_table_file': code_table_file, 'archive_files': sorted(names),
            'extra_shapefiles': extra_shapefiles}


def read_code_table(bundle, names):
    """압축 안의 코드정의표를 줄 단위로 읽어 온다. 뜻의 해석은 필드 목록을 안 뒤에 한다."""
    for name in names:
        try:
            rows = table_rows(name, bundle.read(name))
        except Exception:
            continue
        if rows:
            return rows, name
    return [], None


def split_code_table(rows, fields):
    """코드정의표를 (코드값 → 뜻, 필드명 → 설명) 으로 나눈다.

    실제 필드 목록과 맞는 줄만 필드 설명으로 본다. 그렇지 않으면 'PP0103' 같은 코드값이
    영문 토큰처럼 보여 필드 설명으로 잘못 들어간다.
    """
    upper = {field.upper() for field in fields}
    codes, labels = {}, {}
    for row in rows:
        cells = [('' if cell is None else str(cell)).strip() for cell in row]
        cells = [cell for cell in cells if cell]
        if len(cells) < 2:
            continue
        korean = next((c for c in cells[1:]
                       if any('\uac00' <= ch <= '\ud7a3' for ch in c)), None)
        if korean is None:
            continue
        head = cells[0]
        if head.upper() in upper:
            labels.setdefault(head.upper(), korean)
        elif head != korean:
            codes.setdefault(head, korean)
    return codes, labels


def table_rows(name, raw):
    if name.lower().endswith('.csv'):
        for encoding in ('cp949', 'utf-8-sig', 'utf-8'):
            try:
                text = raw.decode(encoding)
            except UnicodeDecodeError:
                continue
            import csv
            return list(csv.reader(io.StringIO(text)))
        return []
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    rows = []
    for sheet in book.worksheets:
        rows.extend(list(sheet.iter_rows(values_only=True)))
    book.close()
    return rows


# --------------------------------------------------------------------------- 좌표계

def source_crs(projection):
    """.prj에서 좌표계를 읽는다. 읽지 못하면 추정하지 않고 None을 돌려준다.

    낮은 신뢰도의 EPSG 추정은 받지 않는다. pyproj가 확신 없이 돌려주는 코드는
    중부원점 계열끼리 서로 바뀌기 쉽고(5181 ↔ 5186), 그러면 좌표가 수백 m 어긋난 채로
    정상처럼 보인다. 코드를 확정할 수 없으면 코드 대신 WKT 정의 자체로 변환한다.
    """
    if not projection:
        return None, 'NO_PRJ_FILE'
    found = re.search(r'AUTHORITY\["EPSG","(\d+)"\]\s*\]\s*$', projection.strip())
    if found:
        return f'EPSG:{found.group(1)}', 'FROM_PRJ_AUTHORITY'
    try:
        from pyproj import CRS
        parsed = CRS.from_wkt(projection)
    except Exception:
        parsed = None
    if parsed is not None:
        code = parsed.to_epsg()  # 기본 신뢰도(70)만 받는다.
        if code:
            return f'EPSG:{code}', 'FROM_PRJ_WKT_EPSG'
    for label, code in KNOWN_CRS.items():
        if label.lower() in projection.lower():
            return code, 'FROM_PRJ_NAME'
    if parsed is not None:
        # 코드는 확정하지 못했지만 WKT가 투영을 온전히 정의한다. 코드를 찍지 않고 그대로 쓴다.
        return None, 'FROM_PRJ_WKT_NO_EPSG'
    return None, 'UNRECOGNISED_PRJ'


def transformers(projection, crs, basis):
    """(정방향, 역방향, 미터 단위 여부). 변환할 수 없으면 (None, None, False)."""
    if basis == 'FROM_PRJ_WKT_NO_EPSG':
        from pyproj import CRS, Transformer
        parsed = CRS.from_wkt(projection)
    elif crs and crs != 'EPSG:4326':
        from pyproj import CRS, Transformer
        parsed = CRS.from_user_input(crs)
    else:
        return None, None, False
    forward = Transformer.from_crs(parsed, 'EPSG:4326', always_xy=True)
    backward = Transformer.from_crs('EPSG:4326', parsed, always_xy=True)
    metres = parsed.is_projected and all(
        axis.unit_name in ('metre', 'meter') for axis in parsed.axis_info)
    return forward.transform, backward.transform, metres


def crs_label(crs, basis, projection):
    if crs:
        return crs
    if basis == 'FROM_PRJ_WKT_NO_EPSG':
        try:
            from pyproj import CRS
            return f'WKT:{CRS.from_wkt(projection).name}'
        except Exception:
            return 'WKT:UNNAMED'
    return None


# --------------------------------------------------------------------------- geometry

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


def segment_distance(point, start, end):
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return ((px - (x1 + t * dx)) ** 2 + (py - (y1 + t * dy)) ** 2) ** 0.5


def distance_to_rings(point, rings):
    """가장 가까운 경계선까지의 거리. 좌표 단위를 그대로 쓴다(미터 좌표계면 미터)."""
    best = None
    for ring in rings:
        for index in range(len(ring) - 1):
            gap = segment_distance(point, ring[index], ring[index + 1])
            best = gap if best is None else min(best, gap)
    return best


def wind(ring, clockwise):
    """GeoJSON(RFC 7946)은 외곽 반시계, 구멍 시계를 요구한다. 좌표는 그대로 두고 순서만 맞춘다."""
    return list(reversed(ring)) if (ring_area(ring) < 0) != clockwise else list(ring)


def split_rings(shape):
    """part 경계로 ring을 나눈다. 점이 4개 미만인 ring은 면이 아니므로 버린다."""
    points = list(shape.points)
    if not points:
        return [], []
    parts = list(shape.parts) + [len(points)]
    rings = [points[parts[i]:parts[i + 1]] for i in range(len(parts) - 1)]
    usable = [ring for ring in rings if len(ring) >= 4]
    return rings, usable


def classify_rings(rings):
    """Shapefile 규약: 외곽은 시계방향(음수 면적), 구멍은 반시계방향."""
    outer = [ring for ring in rings if ring_area(ring) < 0]
    holes = [ring for ring in rings if ring_area(ring) >= 0]
    if not outer:
        # 규약을 지키지 않은 원천. 면적이 가장 큰 ring을 외곽으로 보고 나머지를 구멍으로 둔다.
        largest = max(rings, key=lambda ring: abs(ring_area(ring)))
        outer = [largest]
        holes = [ring for ring in rings if ring is not largest]
    return outer, holes


def to_wgs84(shape, transformer):
    """SHP geometry를 EPSG:4326 GeoJSON으로 바꾼다. 좌표를 만들어 내지 않는다.

    외곽/구멍 판정을 뒤집어 읽으면 서로 떨어진 두 구역이 '구멍 뚫린 한 구역'으로
    바뀐다. 그래서 Shapefile 규약(외곽=시계방향=음수 면적)을 그대로 따른다.
    """
    _, rings = split_rings(shape)
    if not rings:
        return None, [], [], 'NO_RING'
    if transformer:
        rings = [[transformer(x, y) for x, y in ring] for ring in rings]
    closed = all(ring[0] == ring[-1] for ring in rings)
    outer, holes = classify_rings(rings)
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


def within_sanity(rings):
    """변환된 좌표가 서울 범위인지. 하나라도 벗어나면 좌표계를 잘못 읽은 것이다."""
    for ring in rings:
        for lng, lat in ring:
            if not (SANITY_LON[0] <= lng <= SANITY_LON[1]):
                return False
            if not (SANITY_LAT[0] <= lat <= SANITY_LAT[1]):
                return False
    return True


# --------------------------------------------------------------------------- schema

def interpret_schema(fields, records, code_table, field_labels=None, profile=None):
    """역할마다 어떤 필드를 어떤 근거로 골랐는지 적는다. 근거 없이 매칭에 쓰지 않는다."""
    report = {}
    field_labels = field_labels or {}
    mapped = (profile or {}).get('roles') or {}
    record_id_field = (profile or {}).get('source_record_id')
    for role, (plain, coded) in ROLE_FIELDS.items():
        field = field_for(fields, plain)
        basis, decode = ('FIELD_NAME', None) if field else ('UNRESOLVED', None)
        if field is None and mapped.get(role) in fields:
            # 이 데이터셋에 한정한 공식 mapping. 다른 shapefile에는 적용되지 않는다.
            field, basis = mapped[role], 'OFFICIAL_DATASET_FIELD'
        if field is None:
            field = field_for(fields, coded)
        if field is None:
            report[role] = {'field': None, 'basis': 'UNRESOLVED', 'field_label': None,
                            'values_decoded': False, 'used_for_matching': False,
                            'samples': [], 'decode': None}
            continue
        values = [str(row[field]).strip() for row in records
                  if row.get(field) not in (None, '', ' ')]
        distinct = sorted(set(values))
        label = field_labels.get(field.upper())
        keywords = FIELD_LABEL_KEYWORDS.get(role, ())
        if role == 'official_id' and record_id_field and field == record_id_field:
            # 원천 record 식별자다. ZIP:ON id와 같은 namespace라고 확인되지 않았으므로
            # 보존만 하고 동일성 신호로 쓰지 않는다.
            basis = 'SOURCE_RECORD_ID'
        elif basis not in ('FIELD_NAME', 'OFFICIAL_DATASET_FIELD'):
            if not distinct:
                basis = 'EMPTY'
            elif role == 'district' and all(value in SEOUL_SGG for value in distinct):
                # 서울 자치구 코드 목록과 정확히 맞는다. 검증된 표로 풀어 쓴다.
                basis, decode = 'SEOUL_DISTRICT_CODE', dict(SEOUL_SGG)
            elif code_table and all(value in code_table for value in distinct):
                basis, decode = 'CODE_TABLE', {v: code_table[v] for v in distinct}
            elif label and any(word in label for word in keywords):
                # 코드정의표가 이 필드의 뜻을 적어 두었다. 추측이 아니라 표를 따른다.
                basis = 'CODE_TABLE_FIELD_LABEL'
            elif any(any('\uac00' <= ch <= '\ud7a3' for ch in value) for value in distinct):
                # 한글 값이지만 이 필드가 무엇을 뜻하는지 확인하지 못했다. 매칭에 쓰지 않는다.
                basis = 'UNCONFIRMED_TEXT'
            else:
                basis = 'UNCONFIRMED_CODE'
        samples = []
        for value in values:
            if value not in samples:
                samples.append(value)
            if len(samples) >= 5:
                break
        readable = bool(decode) or any(
            any('\uac00' <= ch <= '\ud7a3' for ch in value) for value in distinct)
        decoded = readable or role not in ROLES_NEEDING_DECODED_VALUES
        if role in ROLES_NEEDING_DECODED_VALUES and not readable and distinct \
                and basis in CONFIRMED_BASES:
            # 필드의 뜻은 알지만 값이 아직 코드다. 추측해서 풀지 않는다.
            basis = 'UNCONFIRMED_CODE'
        report[role] = {'field': field, 'basis': basis, 'field_label': label,
                        'values_decoded': decoded,
                        'used_for_matching': basis in CONFIRMED_BASES and decoded,
                        'samples': samples, 'decode': decode}
    if record_id_field and record_id_field in fields:
        samples = []
        for row in records:
            value = row.get(record_id_field)
            if value in (None, '', ' '):
                continue
            text = str(value).strip()
            if text not in samples:
                samples.append(text)
            if len(samples) >= 5:
                break
        report['source_record_id'] = {
            'field': record_id_field, 'basis': 'SOURCE_RECORD_ID',
            'field_label': field_labels.get(record_id_field.upper()),
            'values_decoded': True, 'used_for_matching': False,
            'samples': samples, 'decode': None,
            'note': 'ZIP:ON project identity를 바꾸는 근거로 쓰지 않는다.'}
    return report


def role_value(row, schema, role):
    """확인된 근거가 있는 역할만 값을 돌려준다. 코드값은 표로 풀어서 돌려준다."""
    entry = schema.get(role) or {}
    if not entry.get('used_for_matching') or not entry.get('field'):
        return None
    value = row.get(entry['field'])
    if value in (None, '', ' '):
        return None
    text = str(value).strip()
    decode = entry.get('decode')
    return decode.get(text, text) if decode else text


def schema_fingerprint(reader_fields):
    """필드 이름·형식·길이를 한 줄로 요약한다. 다음 판과 비교할 때 쓴다."""
    spec = ';'.join(f'{f[0]}:{f[1]}:{f[2]}' for f in reader_fields[1:])
    return hashlib.sha256(spec.encode('utf-8')).hexdigest()


# --------------------------------------------------------------------------- ZIP:ON

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
        name = project['identity']['official_project_name']
        normalized, rules = normalize_name(name)
        projects.append({
            'project_id': project_id,
            'project_name': name,
            'normalized_name': normalized,
            'normalization_rules': rules,
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


def match(project, records, protected, collisions=None, identity_comparable_id=False):
    """정규화 사업명 + 자치구로 후보를 만들고, 모순이 없을 때만 EXACT로 본다.

    geometry는 후보를 만든 뒤의 보조 검증이다. 여기서는 쓰지 않는다.
    PRESENT_SN 같은 원천 record 식별자는 ZIP:ON id와 같은 namespace라고 확인되지 않으면
    동일성 신호가 되지 않는다(identity_comparable_id=False).
    """
    collisions = collisions or {}
    candidates = []
    key = project['normalized_name']
    raw = compact(project['project_name'])
    for record in records:
        hit = []
        if identity_comparable_id and project['official_external_id'] and record['official_id'] \
                and project['official_external_id'] == record['official_id']:
            hit.append('OFFICIAL_ID')
        official_key = record['normalized_name']
        if key and official_key and official_key == key:
            hit.append('NAME_NORMALIZED_EXACT')
        elif record['name'] and compact(record['name']) == raw:
            hit.append('NAME_EXACT')
        elif key and official_key and len(key) >= 3 and key in official_key:
            hit.append('NAME_CONTAINED')
        if record['district'] and project['district'] and record['district'] == project['district']:
            hit.append('DISTRICT')
        elif record['district'] and project['district']:
            hit.append('DISTRICT_MISMATCH')
        if record['dong'] and project['dong'] and record['dong'] == project['dong']:
            hit.append('DONG')
        if project['lot_number'] and record['address'] and project['lot_number'] in record['address']:
            hit.append('LOT')
        named = any(s in hit for s in ('OFFICIAL_ID', 'NAME_NORMALIZED_EXACT', 'NAME_EXACT',
                                       'NAME_CONTAINED'))
        # 자치구가 서로 다르면 이름이 같아도 같은 사업으로 보지 않는다.
        if named and 'DISTRICT_MISMATCH' not in hit:
            candidates.append({'record': record, 'signals': hit})
    if not candidates:
        return 'NO_MATCH', None, [], '정규화 사업명으로 이어지는 공식 record가 없습니다.'
    if project['project_id'] in protected:
        return ('AMBIGUOUS', None, [c['signals'] for c in candidates],
                '기존 duplicate/identity 검토 대상이라 폴리곤으로 동일성을 정하지 않습니다.')
    if len(candidates) > 1:
        return ('AMBIGUOUS', None, [c['signals'] for c in candidates],
                f'같은 자치구에서 공식 record 후보가 {len(candidates)}건이라 하나로 좁혀지지 않습니다.')
    single = candidates[0]
    signals = single['signals']
    if collisions.get((key, project['district']), 0) > 1:
        return ('AMBIGUOUS', None, signals,
                'ZIP:ON 안에서 정규화 사업명이 같은 사업이 둘 이상이라 어느 쪽인지 정할 수 없습니다.')
    strong = 'OFFICIAL_ID' in signals or 'NAME_NORMALIZED_EXACT' in signals \
        or 'NAME_EXACT' in signals
    if strong and 'DISTRICT' in signals and key and len(key) >= 3:
        return ('EXACT', single, signals,
                '정규화 사업명과 자치구가 일치하고 같은 자치구 후보가 하나뿐이며 모순 신호가 없습니다.')
    if not key or len(key) < 3:
        return ('PROBABLE', single, signals,
                f'정규화 사업명이 {len(key or "")}자로 짧아 이름만으로 확정하기 어렵습니다.')
    if strong and 'DISTRICT' not in signals:
        return ('PROBABLE', single, signals,
                '정규화 사업명은 일치하지만 공식 record에 자치구가 없어 확인이 더 필요합니다.')
    return ('PROBABLE', single, signals,
            '이름이 부분적으로만 일치해 표기 차이인지 다른 사업인지 확인이 더 필요합니다.')


# --------------------------------------------------------------------------- 분석

def analyse(archive):
    bundle = read_archive(archive)
    reader = bundle['reader']
    profile = dataset_profile(bundle['shapefile'])
    crs, crs_basis = source_crs(bundle['projection'])
    forward, backward, metres = transformers(bundle['projection'], crs, crs_basis)
    fields = [f[0] for f in reader.fields[1:]]
    code_table, field_labels = split_code_table(bundle['code_table_rows'], fields)
    raw_rows, shapes = [], []
    for shape_record in reader.iterShapeRecords():
        raw_rows.append(dict(zip(fields, list(shape_record.record))))
        shapes.append(shape_record.shape)
    schema = interpret_schema(fields, raw_rows, code_table, field_labels, profile)

    records, kinds, invalid, empty, converted, outside = [], {}, 0, 0, 0, 0
    for attributes, shape in zip(raw_rows, shapes):
        geometry, outer, holes, validity = to_wgs84(shape, forward)
        _, source_usable = split_rings(shape)
        kind = geometry['type'] if geometry else 'NONE'
        kinds[kind] = kinds.get(kind, 0) + 1
        if geometry is None:
            empty += 1
        if validity != 'VALID':
            invalid += 1
        sane = bool(geometry) and within_sanity(outer + holes)
        if geometry is not None:
            converted += 1
            if not sane:
                outside += 1
        name = role_value(attributes, schema, 'name')
        normalized, rules = normalize_name(name)
        source_record_id = None
        if 'source_record_id' in schema:
            source_record_id = attributes.get(schema['source_record_id']['field'])
            source_record_id = (str(source_record_id).strip()
                                if source_record_id not in (None, '', ' ') else None)
        records.append({
            'name': name,
            'normalized_name': normalized,
            'normalization_rules': rules,
            'source_record_id': source_record_id,
            'official_id': role_value(attributes, schema, 'official_id'),
            'type': role_value(attributes, schema, 'type'),
            'district': role_value(attributes, schema, 'district'),
            'dong': role_value(attributes, schema, 'dong'),
            'address': role_value(attributes, schema, 'address'),
            'attributes': attributes, 'geometry': geometry,
            'outer_rings': outer, 'hole_rings': holes,
            'source_rings': source_usable,
            'geometry_valid': validity == 'VALID' and sane,
            'validity': validity, 'within_seoul': sane})

    identifiers = [r['source_record_id'] or r['official_id'] for r in records
                   if r['source_record_id'] or r['official_id']]
    shapes_seen = {}
    for record in records:
        if not record['geometry']:
            continue
        digest = hashlib.sha256(json.dumps(
            [[[round(v, 7) for v in p] for p in ring] for ring in record['outer_rings']],
            sort_keys=True).encode('utf-8')).hexdigest()
        shapes_seen[digest] = shapes_seen.get(digest, 0) + 1
    return {'shapefile': bundle['shapefile'], 'dbf_encoding': bundle['dbf_encoding'],
            'dataset_profile': (profile or {}).get('id'),
            'dataset_profile_note': (profile or {}).get('note'),
            'archive_files': bundle['archive_files'],
            'extra_shapefiles': bundle['extra_shapefiles'],
            'code_table_file': bundle['code_table_file'],
            'code_table_entries': len(code_table),
            'code_table_field_labels': len(field_labels),
            'fields': fields, 'field_spec': [list(f) for f in reader.fields[1:]],
            'schema_fingerprint': schema_fingerprint(reader.fields),
            'schema': schema, 'record_count': len(records), 'geometry_types': kinds,
            'invalid_geometry': invalid, 'empty_geometry': empty,
            'converted_to_epsg4326': converted, 'outside_seoul': outside,
            'duplicate_identifiers': len(identifiers) - len(set(identifiers)),
            'duplicate_geometry': sum(count - 1 for count in shapes_seen.values() if count > 1),
            'source_crs': crs, 'source_crs_basis': crs_basis,
            'source_crs_label': crs_label(crs, crs_basis, bundle['projection']),
            'projection_wkt': bundle['projection'], 'converted_crs': 'EPSG:4326',
            'source_units_metre': metres, 'to_source': backward, 'records': records}


def build(archive):
    survey = analyse(archive)
    projects = load_projects()
    protected = conflicted_ids()
    # ZIP:ON 안에서 정규화 이름이 겹치는 사업은 어느 쪽인지 정할 수 없다.
    collisions = {}
    for project in projects:
        pair = (project['normalized_name'], project['district'])
        collisions[pair] = collisions.get(pair, 0) + 1
    identity_id = bool((survey['schema'].get('official_id') or {}).get('used_for_matching'))
    rows, features = [], []
    for project in projects:
        status, chosen, signals, reason = match(project, survey['records'], protected,
                                               collisions, identity_id)
        record = (chosen or {}).get('record') if chosen else None
        inside, distance, basis = None, None, None
        if record and record['outer_rings'] and project['longitude'] is not None:
            point = (project['longitude'], project['latitude'])
            inside = contains(point, record['outer_rings'], record['hole_rings'])
            distance, basis = point_distance(project, record, survey)
        excluded = None
        if status == 'EXACT':
            if not record['geometry_valid']:
                excluded = 'GEOMETRY_NOT_VALID'
            elif inside is False:
                excluded = 'REPRESENTATIVE_POINT_OUTSIDE_POLYGON'
            elif inside is None:
                excluded = 'NO_REPRESENTATIVE_POINT'
        rows.append({
            'zipon_project_id': project['project_id'],
            'zipon_project_name': project['project_name'],
            'zipon_normalized_name': project['normalized_name'],
            'zipon_normalization_rules': project['normalization_rules'],
            'district': project['district'], 'dong': project['dong'],
            'project_type': project['project_type'], 'program': project['program'],
            'official_record_id': (record or {}).get('official_id'),
            'official_source_record_id': (record or {}).get('source_record_id'),
            'official_name': (record or {}).get('name'),
            'official_normalized_name': (record or {}).get('normalized_name'),
            'official_normalization_rules': (record or {}).get('normalization_rules'),
            'official_type': (record or {}).get('type'),
            'match_status': status, 'match_signals': signals, 'confidence_reason': reason,
            'geometry_type': ((record or {}).get('geometry') or {}).get('type'),
            'geometry_valid': (record or {}).get('geometry_valid'),
            'geometry_validity': (record or {}).get('validity'),
            'source_crs': survey['source_crs_label'], 'converted_crs': survey['converted_crs'],
            'representative_point_inside_polygon': inside,
            'distance_to_polygon_m': distance, 'distance_basis': basis,
            'auto_apply_candidate': status == 'EXACT' and excluded is None,
            'excluded_reason': excluded,
            'source_dataset': SOURCE['dataset'], 'source_version': SOURCE['version']})
        if status == 'EXACT' and excluded is None and record['geometry']:
            features.append({'type': 'Feature', 'geometry': record['geometry'],
                             'properties': {'zipon_project_id': project['project_id'],
                                            'zipon_project_name': project['project_name'],
                                            'official_name': record['name'],
                                            'official_normalized_name': record['normalized_name'],
                                            'official_source_record_id': record['source_record_id'],
                                            'official_record_id': record['official_id'],
                                            'representative_point_inside_polygon': inside,
                                            'distance_to_polygon_m': distance,
                                            'review_only': True,
                                            'legal_note': SOURCE['legal_note']}})
    return survey, rows, features


def point_distance(project, record, survey):
    """대표좌표에서 폴리곤 경계까지의 거리(m). 단위를 확신할 수 없으면 None."""
    inside = contains((project['longitude'], project['latitude']),
                      record['outer_rings'], record['hole_rings'])
    if inside:
        return 0.0, 'INSIDE_POLYGON'
    if survey['source_units_metre'] and survey['to_source'] and record['source_rings']:
        x, y = survey['to_source'](project['longitude'], project['latitude'])
        gap = distance_to_rings((x, y), record['source_rings'])
        return (round(gap, 1) if gap is not None else None), 'SOURCE_CRS_METRES'
    try:
        from pyproj import Geod
        geod = Geod(ellps='WGS84')
        best = None
        for ring in record['outer_rings']:
            for lng, lat in ring:
                _, _, gap = geod.inv(project['longitude'], project['latitude'], lng, lat)
                best = gap if best is None else min(best, gap)
        return (round(best, 1) if best is not None else None), 'GEOD_NEAREST_VERTEX'
    except Exception:
        return None, 'UNKNOWN_UNITS'


# --------------------------------------------------------------------------- 산출

def archive_digest(archive):
    digest = hashlib.sha256()
    with open(archive, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def registry_entry(archive):
    if not REGISTRY_FILE.exists():
        return None
    registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
    return next((s for s in registry.get('sources', [])
                 if s.get('dataset_id') == SOURCE['dataset_id']), None)


def register(archive, survey=None):
    """어떤 원천을 어떤 판으로 받았는지 적는다. 원천 파일은 수정하지 않는다.

    다음 판이 들어왔을 때 hash만 비교해서 다시 분석할지 판단할 수 있게 남긴다.
    """
    registry = {'format': 'zipon-source-registry-v1', 'sources': []}
    if REGISTRY_FILE.exists():
        registry = json.loads(REGISTRY_FILE.read_text(encoding='utf-8'))
    entry = dict(SOURCE, archive=archive.name, acquired=True,
                 acquisition_status='PRESENT', modified=False,
                 place_under=shown(REFERENCE),
                 source_sha256=archive_digest(archive),
                 source_bytes=archive.stat().st_size,
                 recorded_at=now())
    if survey:
        entry.update({'shapefile': survey['shapefile'], 'dbf_encoding': survey['dbf_encoding'],
                      'source_crs': survey['source_crs_label'],
                      'source_crs_basis': survey['source_crs_basis'],
                      'record_count': survey['record_count'],
                      'schema_fingerprint': survey['schema_fingerprint'],
                      'code_table_file': survey['code_table_file'],
                      'analysed_at': now()})
    others = [s for s in registry.get('sources', [])
              if s.get('dataset_id') != SOURCE['dataset_id']]
    registry['sources'] = others + [entry]
    registry['recorded_at'] = now()
    registry['note'] = ('원천 파일은 수정하지 않는다. 다음 판이 오면 source_sha256을 비교해서 '
                        '같으면 재분석하지 않고, 다르면 다시 분석한다.')
    REGISTRY_FILE.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n',
                             encoding='utf-8')
    return entry


def summarise(survey, rows, features, archive):
    counts = {}
    for row in rows:
        counts[row['match_status']] = counts.get(row['match_status'], 0) + 1
    exact = [r for r in rows if r['match_status'] == 'EXACT']
    totals = dict(counts, zipon_projects=len(rows),
                  exact_with_valid_polygon=sum(1 for r in exact if r['geometry_valid']),
                  exact_valid_inside=sum(1 for r in exact if r['geometry_valid']
                                         and r['representative_point_inside_polygon']),
                  exact_valid_outside=sum(1 for r in exact if r['geometry_valid']
                                          and r['representative_point_inside_polygon'] is False),
                  exact_valid_no_point=sum(1 for r in exact if r['geometry_valid']
                                           and r['representative_point_inside_polygon'] is None),
                  exact_invalid_geometry=sum(1 for r in exact if not r['geometry_valid']),
                  auto_apply_candidates=sum(1 for r in rows if r['auto_apply_candidate']),
                  representative_point_inside=sum(
                      1 for r in rows if r['representative_point_inside_polygon']))
    shapefile_keys = ('shapefile', 'dataset_profile', 'dataset_profile_note',
                      'dbf_encoding', 'fields', 'field_spec', 'schema_fingerprint',
                      'record_count', 'geometry_types', 'invalid_geometry', 'empty_geometry',
                      'converted_to_epsg4326', 'outside_seoul', 'duplicate_identifiers',
                      'duplicate_geometry', 'source_crs', 'source_crs_basis', 'source_crs_label',
                      'source_units_metre', 'converted_crs', 'archive_files',
                      'extra_shapefiles', 'code_table_file', 'code_table_entries',
                      'code_table_field_labels')
    return {'format': 'zipon-polygon-match-review-v1', 'generated_at': now(),
            'db_write': False, 'polygon_written_to_production': False,
            'source': dict(SOURCE, archive=archive.name,
                           source_sha256=archive_digest(archive),
                           source_bytes=archive.stat().st_size),
            'shapefile': {k: survey[k] for k in shapefile_keys},
            'schema': survey['schema'],
            'totals': totals,
            'exact': [r for r in exact],
            'items': rows,
            'review_geojson_features': len(features)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--archive', type=Path, help='서울시 공식 SHP zip 경로')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--if-changed', action='store_true',
                    help='registry의 source_sha256과 같으면 재분석하지 않는다')
    args = ap.parse_args()
    if args.archive is None or not args.archive.exists():
        print(json.dumps({'status': 'SOURCE_FILE_NOT_PRESENT', 'db_write': False,
                          'expected_file': SOURCE['file'],
                          'portal_url': SOURCE['portal_url'],
                          'place_under': shown(REFERENCE)}, ensure_ascii=False))
        return 0
    if args.if_changed:
        known = registry_entry(args.archive)
        if known and known.get('source_sha256') == archive_digest(args.archive) \
                and REVIEW_FILE.exists():
            print(json.dumps({'status': 'SOURCE_UNCHANGED', 'db_write': False,
                              'source_sha256': known['source_sha256'],
                              'review_file': shown(REVIEW_FILE)},
                             ensure_ascii=False))
            return 0
    survey, rows, features = build(args.archive)
    review = summarise(survey, rows, features, args.archive)
    sane = survey['outside_seoul'] == 0 and survey['converted_to_epsg4326'] > 0
    if not sane:
        # 좌표계를 잘못 읽었다. 이 상태로 매칭 결과를 산출물로 남기지 않는다.
        print(json.dumps({'status': 'CRS_SANITY_FAILED', 'db_write': False,
                          'source_crs': survey['source_crs_label'],
                          'source_crs_basis': survey['source_crs_basis'],
                          'converted_to_epsg4326': survey['converted_to_epsg4326'],
                          'outside_seoul': survey['outside_seoul'],
                          'expected_longitude': list(SANITY_LON),
                          'expected_latitude': list(SANITY_LAT)}, ensure_ascii=False))
        return 2
    if args.write:
        REFERENCE.mkdir(parents=True, exist_ok=True)
        REVIEW_FILE.write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        GEOJSON_FILE.write_text(json.dumps(
            {'type': 'FeatureCollection', 'review_only': True,
             'legal_note': SOURCE['legal_note'], 'features': features},
            ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        register(args.archive, survey)
    print(json.dumps({'status': 'ANALYSED', 'record_count': survey['record_count'],
                      'geometry_types': survey['geometry_types'],
                      'source_crs': survey['source_crs_label'],
                      'source_crs_basis': survey['source_crs_basis'],
                      'totals': review['totals'],
                      'exact_features': len(features), 'db_write': False,
                      'written': bool(args.write)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
