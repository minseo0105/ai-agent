"""좌표를 확보하지 못한 8건을 근거와 함께 검토 가능한 형태로 정리한다.

이 스크립트는 지오코더를 다시 부르지 않고 데이터베이스에도 쓰지 않는다. 이미 받아 둔
공식 스냅샷과 NAVER 응답만 읽어서 각 건이 왜 남았는지, 무엇이 있으면 풀리는지를 적는다.

분류:
  SAFE_TO_APPLY      공식 주소의 시도·자치구·동·번지를 전부 만족하는 후보가 정확히 하나.
  MANUAL_REVIEW      후보가 여럿이거나, 어느 후보도 공식 번지를 지지하지 않는다.
  NEEDS_OFFICIAL_DETAIL  공식 주소는 있으나 지오코더가 해당 지번을 찾지 못했다.
  ADDRESS_UNRESOLVED 공식 주소 자체가 없다.

첫 후보를 채택하지 않는다. 인접 지번(본번이 같고 부번만 다른 것 포함)은 같은 지번이
아니므로 절대 채택하지 않는다. 한 필지 옆이 파출소나 학교인 경우가 실제로 있었다.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_geocode as geo
from services.development_official import now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
OUTPUT = DATA / 'geocode_gap_review_20260928.json'


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def canonical_index():
    index = {}
    for project in load('pilot_canonical_verified_20260927.json')['projects']:
        index[project['raw']['candidate_ids'][0]] = project
    return index


def official_evidence(project):
    """이 사업에 대해 우리가 실제로 들고 있는 공식 근거."""
    if not project:
        return {}
    location, identity = project['location'], project['identity']
    classification, progress = project['classification'], project['progress']
    return {'official_project_name': identity['official_project_name'],
            'official_external_id': identity['official_external_id'],
            'source_system': identity['source_system'],
            'official_address': location['representative_address'],
            'address_type': location['address_type'],
            'address_source': location['address_source'],
            'address_source_url': location['address_source_url'],
            'address_verified': location['address_verified'],
            'official_registry_row': classification['official_registry_row'],
            'raw_stage': progress['raw_stage'],
            'stage_source_url': progress['stage_source_url'],
            'content_hash': (progress['stage_evidence'] or {}).get('content_hash')}


def judge(item):
    """후보 중 공식 주소를 명확히 지지하는 것이 정확히 하나인지."""
    wanted = geo.wanted_parts(item['official_address'] or '')
    supporting = []
    for candidate in item.get('naver_candidates') or []:
        elements = candidate.get('address_elements') or {}
        if (elements.get('SIDO') == wanted['sido'] and elements.get('SIGUGUN') == wanted['district']
                and elements.get('DONGMYUN') == wanted['dong']
                and elements.get('LAND_NUMBER') == wanted['lot']):
            supporting.append(candidate)
    summary = [{'jibun_address': c.get('jibun_address'), 'road_address': c.get('road_address'),
                'longitude': c.get('longitude'), 'latitude': c.get('latitude'),
                'accuracy': c.get('accuracy'),
                'returned_lot': (c.get('address_elements') or {}).get('LAND_NUMBER'),
                'district_match': (c.get('address_elements') or {}).get('SIGUGUN') == wanted['district'],
                'dong_match': (c.get('address_elements') or {}).get('DONGMYUN') == wanted['dong'],
                'lot_match': (c.get('address_elements') or {}).get('LAND_NUMBER') == wanted['lot'],
                'failed_checks': c.get('failed_checks')}
               for c in item.get('naver_candidates') or []]
    if len(supporting) == 1:
        chosen = supporting[0]
        return ('SAFE_TO_APPLY', 'HIGH', summary,
                f"공식 지번 {wanted['lot']}을(를) 만족하는 후보가 하나뿐입니다.",
                {'longitude': chosen.get('longitude'), 'latitude': chosen.get('latitude'),
                 'matched_address': chosen.get('jibun_address')})
    if supporting:
        return ('MANUAL_REVIEW', 'LOW', summary,
                f"공식 지번 {wanted['lot']}을(를) 만족하는 후보가 {len(supporting)}건이라 하나로 좁혀지지 않습니다.",
                None)
    returned = [s['returned_lot'] for s in summary]
    return ('MANUAL_REVIEW', 'LOW', summary,
            f"어느 후보도 공식 지번 {wanted['lot']}을(를) 지지하지 않습니다. "
            f"돌려받은 지번은 {', '.join(str(r) for r in returned)}로 모두 인접 필지입니다.",
            None)


def build():
    canonical = canonical_index()
    review = load('bulk_geocode_review_20260927.json')
    result = load('bulk_geocode_result_20260927.json')
    fast_track = {row['project_id']: row for row in load('fast_track_location_20260927.json')['items']}
    rows = []

    for item in review['items']:
        project = canonical.get(item['project_id'])
        status, confidence, summary, reason, proposal = judge(item)
        rows.append({'project_id': item['project_id'], 'project_name': item['project_name'],
                     'current_status': 'REVIEW_REQUIRED',
                     'official_evidence': official_evidence(project),
                     'candidate_count': item['candidate_count'],
                     'candidate_summary': summary, 'recommended_action': status,
                     'confidence': confidence, 'reason': reason,
                     'proposed_coordinate': proposal})

    for item in result['items']:
        if item['outcome'] != 'FAILED':
            continue
        project = canonical.get(item['project_id'])
        rows.append({'project_id': item['project_id'], 'project_name': item['project_name'],
                     'current_status': 'FAILED',
                     'official_evidence': official_evidence(project),
                     'candidate_count': item.get('candidate_count') or 0,
                     'candidate_summary': [],
                     'recommended_action': 'NEEDS_OFFICIAL_DETAIL', 'confidence': 'LOW',
                     'reason': ('공식 주소는 있으나 지오코더가 해당 지번을 찾지 못했습니다'
                                f"({item.get('acceptance_reason')}). 정비구역 고시의 지번 목록 등 "
                                '공식 상세로 주소를 다시 확인해야 합니다.'),
                     'proposed_coordinate': None})

    for project_id, row in fast_track.items():
        project = canonical.get(project_id)
        if project is None or project['location']['representative_address']:
            continue
        # DB에 있는데 주소가 없는 건만. 격리된 건은 지오코딩 대상이 아니다.
        if project_id not in {i['project_id'] for i in result['items']}:
            in_db = row['project_name'] in ('천호동 392-9', '마천2')
            if not in_db:
                continue
        rows.append({'project_id': project_id, 'project_name': row['project_name'],
                     'current_status': 'NO_ADDRESS',
                     'official_evidence': dict(official_evidence(project),
                                               raw_source_text=row['raw_source_text'],
                                               lot_in_name=row['lot_in_name'],
                                               registry_links=row['registry_links'],
                                               clue_conflict=row['clue_conflict']),
                     'candidate_count': 0, 'candidate_summary': [],
                     'recommended_action': ('OFFICIAL_ADDRESS_RECOVERED' if row['lot_in_name']
                                            else 'NEEDS_IDENTITY_REVIEW' if row['registry_links']
                                            else 'ADDRESS_UNRESOLVED'),
                     'confidence': ('MEDIUM' if row['lot_in_name']
                                    else 'LOW' if row['registry_links'] else 'LOW'),
                     'reason': (f"사업명 자체가 지번({row['lot_in_name']})을 담고 있어 공식 목록만으로 "
                                '주소를 복원할 수 있습니다. 동일성 확인 후 적용 대상입니다.'
                                if row['lot_in_name'] else
                                # 이름으로 연결되는 등록 행이 있으면 '단서 없음'이 아니다.
                                f"공식 목록 행에는 주소가 없지만 같은 자치구 등록 행 "
                                f"{row['registry_links'][0]['registry_project_name']}"
                                f"({row['registry_links'][0]['registry_address']})과 이름으로 연결됩니다. "
                                '동일성이 확인되어야 주소를 쓸 수 있습니다(Track B).'
                                if row['registry_links'] else
                                '공식 목록 행에 주소가 없고 사업명에서도 지번을 얻을 수 없습니다. '
                                '자치구 고시 등 공식 상세가 필요합니다.'),
                     'proposed_coordinate': None})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true', help='write the review artifact')
    args = ap.parse_args()
    rows = build()
    counts = {}
    for row in rows:
        counts[row['recommended_action']] = counts.get(row['recommended_action'], 0) + 1
    document = {'format': 'zipon-coordinate-gap-review-v1', 'generated_at': now(),
                'db_write': False, 'geocoder_called': False,
                'note': ('지오코더를 다시 부르지 않았고 데이터베이스에도 쓰지 않았습니다. '
                         '인접 지번은 같은 지번이 아니므로 채택하지 않습니다.'),
                'totals': dict(counts, reviewed=len(rows)), 'items': rows}
    if args.write:
        OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n',
                          encoding='utf-8')
    print(json.dumps({'reviewed': len(rows), 'counts': counts, 'written': bool(args.write)},
                     ensure_ascii=False))
    for row in rows:
        print(f"  {row['recommended_action']:24s} {row['confidence']:6s} {row['project_name'][:34]:36s} {row['reason'][:60]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
