"""신속통합기획(FAST_TRACK) 34건은 왜 주소가 없는지, 무엇이면 복원되는지 분류한다.

이 34건은 geocoder에 보내지 않는다. 주소가 없는 채로 검색을 던지면 동 중심점이나
구청 좌표가 돌아오고, 그게 대표 위치로 굳는 것이 이 프로젝트에서 가장 피하려는 일이다.
그래서 여기서는 좌표를 만들지 않고, 우리가 이미 가진 공식 텍스트만으로 위치 단서를
어디까지 되짚을 수 있는지 판정한다. 추정 주소는 canonical에 쓰지 않는다.

분류:
  ADDRESS_RECOVERABLE_FROM_OFFICIAL_SOURCE
      이미 가진 공식 텍스트에서 동+번지가 나온다. 사업명 자체에 지번이 있거나,
      같은 자치구의 사업장 등록 행(주소 검증됨)과 이름으로 연결된다. 연결은
      동일성 검토를 거쳐야 하며 자동 채택하지 않는다.
  LOCATION_NAME_ONLY
      자치구 등록 행들에서 실제로 관측된 동 이름이 사업명에 있으나 번지가 없고
      등록 행 연결도 없다. 동 수준까지만 아는 상태다.
  NEEDS_OFFICIAL_DETAIL
      동 단서도 등록 행 연결도 없다. 다만 정비계획 관련 단계가 공식 목록에 있어
      자치구 고시/정보몽땅 상세를 받아오면 주소를 얻을 수 있다.
  INSUFFICIENT_LOCATION
      자치구 외에 쓸 수 있는 단서가 없다.

번지 패턴은 사업명에서만 찾는다. 공식 목록 행에는 면적·세대수·연번 같은 숫자가 들어
있어서 행 전체에 정규식을 걸면 '풍납극동 37'처럼 세대수를 지번으로 읽는다.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_identity import MIN_PROGRAM_NAME
from services.development_official import compact, now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
OUTPUT = DATA / 'fast_track_location_20260927.json'
# 사업명 안의 '천호동 392-9' 같은 지번. 목록 행의 숫자에는 적용하지 않는다.
LOT_IN_NAME = re.compile(r'([가-힣]+[동리가])\s*(\d+(?:-\d+)?)')
PLAN_STAGES = ('정비계획', '고시', '지정', '자문', '기획')


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def registry_dong(projects):
    """자치구별로 등록 행에서 실제 관측된 동 이름. 사전을 새로 만들지 않는다."""
    observed = {}
    for project in projects:
        location = project['location']
        if location['representative_address'] and location['dong']:
            observed.setdefault(location['district'], set()).add(location['dong'])
    return observed


def registry_links(name, district, addressed):
    """같은 자치구 등록 행 중 이 사업명을 포함하는 것. 동일성 검토 대상이지 결론이 아니다."""
    key = compact(name)
    if len(key) < MIN_PROGRAM_NAME:
        return []
    return [{'registry_project_name': other['identity']['official_project_name'],
             'registry_address': other['location']['representative_address'],
             'registry_project_id': other['raw']['candidate_ids'][0],
             'address_verified': other['location']['address_verified']}
            for other in addressed
            if other['location']['district'] == district
            and key in compact(other['identity']['official_project_name'])]


def classify(row):
    if row['lot_in_name'] or row['registry_links']:
        return 'ADDRESS_RECOVERABLE_FROM_OFFICIAL_SOURCE'
    if row['dong_tokens']:
        return 'LOCATION_NAME_ONLY'
    if any(token in (row['raw_stage'] or '') + ' '.join(row['raw_source_text'])
           for token in PLAN_STAGES):
        return 'NEEDS_OFFICIAL_DETAIL'
    return 'INSUFFICIENT_LOCATION'


def analyse():
    projects = load('pilot_canonical_verified_20260927.json')['projects']
    addressed = [p for p in projects if p['location']['representative_address']]
    dongs = registry_dong(projects)
    rows = []
    for project in projects:
        if project['classification']['program'] != 'FAST_TRACK':
            continue
        identity, location = project['identity'], project['location']
        classification, progress = project['classification'], project['progress']
        name, district = identity['official_project_name'], location['district']
        found = LOT_IN_NAME.search(name)
        row = {
            'project_id': project['raw']['candidate_ids'][0],
            'project_name': name, 'district': district, 'dong': location['dong'],
            'project_type': classification['canonical_project_type'],
            'program': classification['program'],
            'program_name': classification['program_name'],
            'official_source': project['source']['source_name']
                               if isinstance(project.get('source'), dict)
                               else classification['program_name'],
            'source_url': classification['program_source_url'],
            'official_id': identity['official_external_id'],
            'official_registry_row': classification['official_registry_row'],
            'raw_stage': progress['raw_stage'],
            'raw_source_text': progress['stage_evidence']['cells'],
            'content_hash': progress['stage_evidence'].get('content_hash'),
            'address_in_source': location['representative_address'],
            'lot_in_name': found.group(0) if found else None,
            'dong_tokens': sorted(d for d in dongs.get(district, ())
                                  if d and d[:-1] and d[:-1] in name),
            'registry_links': registry_links(name, district, addressed),
        }
        row['classification'] = classify(row)
        # 이름이 가리키는 동과 연결된 등록 행의 동이 다르면 검토자가 먼저 봐야 한다.
        linked_dongs = sorted({(link['registry_address'] or '').split()[2]
                               for link in row['registry_links']
                               if len((link['registry_address'] or '').split()) > 2})
        row['linked_dong'] = linked_dongs
        row['clue_conflict'] = bool(row['dong_tokens'] and linked_dongs
                                    and not set(row['dong_tokens']) & set(linked_dongs))
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true', help='write the analysis file')
    args = ap.parse_args()
    rows = analyse()
    counts = {}
    for row in rows:
        counts[row['classification']] = counts.get(row['classification'], 0) + 1
    document = {
        'format': 'zipon-fast-track-location-v1', 'generated_at': now(),
        'db_write': False, 'geocoder_called': False,
        'note': ('주소가 없는 사업을 geocoder에 보내지 않는다. 동 중심점·구청 좌표가 '
                 '대표 위치로 굳는 것을 막기 위한 것이다. 추정 주소는 canonical에 쓰지 않는다.'),
        'method': ['번지 패턴은 사업명에서만 찾는다 (목록 행 숫자는 면적·세대수·연번이다)',
                   '동 이름은 같은 자치구 등록 행에서 실제 관측된 것만 인정한다',
                   '등록 행 연결은 동일성 검토 대상이며 주소를 자동으로 가져오지 않는다'],
        'totals': dict(counts, fast_track=len(rows),
                       clue_conflict=sum(1 for r in rows if r['clue_conflict'])),
        'items': rows}
    if args.write:
        OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n',
                          encoding='utf-8')
    print(json.dumps({'fast_track': len(rows), 'counts': counts, 'written': bool(args.write),
                      'file': str(OUTPUT.relative_to(ROOT))}, ensure_ascii=False))
    for row in rows:
        link = row['registry_links'][0]['registry_address'] if row['registry_links'] else '-'
        print(f"  {row['classification']:42s} {row['district']:5s} {row['project_name']:16s} "
              f"lot_in_name={row['lot_in_name'] or '-':14s} link_addr={link:28s}"
              f"{' CLUE_CONFLICT' if row['clue_conflict'] else ''}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
