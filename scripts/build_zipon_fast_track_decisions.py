"""IDENTITY_CONFIRMED 18건을 사람이 바로 판단할 수 있는 표로 정리한다.

동일성 분석을 다시 하지 않는다. fast_track_identity_review_20260928.json의 결과를
그대로 읽어서 결정에 필요한 것만 한 줄로 펴 놓는다. DB write 없음.

recommended_action의 뜻:
  RESOLVE_DUPLICATE_FIRST  두 기록이 모두 이미 DB에 있다. 주소를 옮기면 같은 자리에
                           마커가 둘 생긴다. 주소 복원이 아니라 중복 정리가 먼저다.
  IMPORT_WITH_ADDRESS      격리 상태라 DB 밖에 있다. 등록을 승인하면 주소까지 함께
                           들어갈 수 있다. 자동 등록하지 않는다.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_official import now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
SOURCE = DATA / 'fast_track_identity_review_20260928.json'
OUTPUT = DATA / 'fast_track_decisions_20260928.json'


def build():
    review = json.loads(SOURCE.read_text(encoding='utf-8'))
    rows = []
    for item in review['items']:
        if item['identity_status'] != 'IDENTITY_CONFIRMED':
            continue
        candidate = (item['identity_evidence']['candidates'] or [{}])[0]
        signals = candidate.get('signals') or {}
        rows.append({
            'fast_track_project': item['project_name'],
            'fast_track_project_id': item['project_id'],
            'matched_official_project': item['official_candidate'],
            'matched_official_project_id': candidate.get('registry_project_id'),
            'official_address': item['official_address'],
            'district': item['district'], 'dong': item['dong'],
            'identity_evidence': {
                'name_contained': signals.get('name_contained'),
                'district_match': signals.get('district_match'),
                'type_match': signals.get('type_match'),
                'dong_agrees': signals.get('dong_agrees'),
                'registry_is_official_row': signals.get('registry_is_official_row'),
                'registry_address_verified': signals.get('registry_address_verified'),
                'single_candidate': len(item['identity_evidence']['candidates']) == 1,
                'fast_track_source_url': item['identity_evidence']['fast_track_source_url'],
                'fast_track_raw_row': item['identity_evidence']['fast_track_raw_row'],
                'registry_source_url': candidate.get('registry_source_url'),
            },
            'existing_canonical': item['in_database'],
            'matched_in_canonical': item['candidate_in_database'],
            'duplicate_risk': item['duplicate_risk'],
            'recommended_action': ('RESOLVE_DUPLICATE_FIRST' if item['duplicate_risk']
                                  else 'IMPORT_WITH_ADDRESS'),
            'blocking_question': ('두 기록이 같은 사업인가? 같다면 어느 쪽을 남길 것인가?'
                                 if item['duplicate_risk'] else
                                 '이 신속통합기획 기록과 등록 행이 같은 사업인가?'),
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    rows = build()
    counts = {}
    for row in rows:
        counts[row['recommended_action']] = counts.get(row['recommended_action'], 0) + 1
    document = {'format': 'zipon-fast-track-decisions-v1', 'generated_at': now(),
                'db_write': False, 'auto_import': False,
                'source_artifact': SOURCE.name,
                'note': ('IDENTITY_CONFIRMED만 담았습니다. 자동 등록하지 않고 주소도 '
                         '옮겨 적지 않았습니다. 사람이 한 줄씩 판단하기 위한 표입니다.'),
                'totals': dict(counts, confirmed=len(rows)), 'items': rows}
    if args.write:
        OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n',
                          encoding='utf-8')
    print(json.dumps({'confirmed': len(rows), 'counts': counts, 'written': bool(args.write)},
                     ensure_ascii=False))
    for row in rows:
        print(f"  {row['recommended_action']:22s} {row['district']:5s} "
              f"{row['fast_track_project']:14s} -> {str(row['official_address']):28s} "
              f"in_db={row['existing_canonical']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
