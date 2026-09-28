"""신속통합기획 34건을 공식 등록 행과 대조해 동일성을 판정한다. DB write 없음.

이름 유사도만으로는 다른 사업을 같은 사업이라고 부르기 쉽다. 그래서 여러 신호를 함께
본다: 사업명(압축 비교), 자치구, 동 단서, 지번, 공식 ID, 공식 URL, 사업 유형, 등록 행
여부, alias. 신호가 서로 어긋나면 그것을 CONFLICT로 남기고 절대 병합하지 않는다.

  IDENTITY_CONFIRMED  이름이 명확히 포함되고 자치구·유형이 일치하며, 동 단서가 어긋나지
                      않고, 후보 등록 행이 하나뿐이다. 주소 복원 후보로 인정한다.
  IDENTITY_PROBABLE   대부분 맞지만 신호 하나가 비어 있거나 후보가 둘 이상이다.
  IDENTITY_CONFLICT   이름은 이어지는데 동 또는 유형이 어긋난다. 자동 복사 금지.
  NO_MATCH            연결되는 등록 행이 없다.

IDENTITY_CONFIRMED만 address_recoverable=true다. PROBABLE과 CONFLICT는 DB에 반영하지
않는다. 이 스크립트는 주소를 canonical에 쓰지 않는다.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_identity import MIN_PROGRAM_NAME
from services.development_official import compact, now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
OUTPUT = DATA / 'fast_track_identity_review_20260928.json'


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def signals(fast, registry):
    """두 사업이 같다고 볼 근거와 어긋나는 근거를 모두 적는다."""
    key = compact(fast['project_name'])
    other = compact(registry['identity']['official_project_name'])
    location, classification = registry['location'], registry['classification']
    dong_tokens = set(fast['dong_tokens'] or [])
    registry_dong = location['dong']
    return {
        'name_contained': len(key) >= MIN_PROGRAM_NAME and key in other,
        'district_match': fast['district'] == location['district'],
        'type_match': fast['project_type'] == classification['canonical_project_type'],
        'dong_agrees': (not dong_tokens or not registry_dong
                        or registry_dong in dong_tokens),
        'dong_known': bool(dong_tokens and registry_dong),
        'registry_is_official_row': bool(classification['official_registry_row']),
        'registry_address_verified': bool(location['address_verified']),
        'registry_has_official_id': bool(registry['identity']['official_external_id']),
        'fast_track_has_official_id': bool(fast['official_id']),
        'registry_dong': registry_dong,
        'fast_track_dong_tokens': sorted(dong_tokens),
    }


def classify(fast, matches):
    """후보들을 보고 하나로 결론 내릴 수 있는지."""
    if not matches:
        return 'NO_MATCH', None, '같은 자치구에서 이름으로 이어지는 공식 등록 행이 없습니다.'
    conflicting = [m for m in matches if not m['signals']['dong_agrees']
                   or not m['signals']['type_match']]
    agreeing = [m for m in matches if m['signals']['dong_agrees']
                and m['signals']['type_match'] and m['signals']['district_match']
                and m['signals']['name_contained'] and m['signals']['registry_is_official_row']
                and m['signals']['registry_address_verified']]
    if conflicting and not agreeing:
        first = conflicting[0]['signals']
        reasons = []
        if not first['dong_agrees']:
            reasons.append(f"사업명이 가리키는 동 {first['fast_track_dong_tokens']}과(와) "
                           f"등록 행의 동 {first['registry_dong']}이(가) 다릅니다")
        if not first['type_match']:
            reasons.append('사업 유형이 다릅니다')
        return 'IDENTITY_CONFLICT', None, '. '.join(reasons) + '. 주소를 옮겨 적지 않습니다.'
    if len(agreeing) == 1 and len(matches) == 1:
        return ('IDENTITY_CONFIRMED', agreeing[0],
                '이름·자치구·유형·동 단서가 모두 일치하고 후보 등록 행이 하나뿐입니다.')
    if agreeing:
        return ('IDENTITY_PROBABLE', None,
                f'조건을 만족하는 후보가 {len(agreeing)}건(전체 후보 {len(matches)}건)이라 '
                '하나로 좁혀지지 않습니다.')
    return ('IDENTITY_PROBABLE', None,
            '이름은 이어지지만 자치구·유형·등록 행 확인 중 일부 신호가 비어 있습니다.')


def in_database():
    ids = {p['project_id'] for p in load('db_baseline_20260927.json')['projects']}
    return ids | {i for b in load('bulk_import_result_20260927.json')['batches']
                  for i in b['project_ids']}


def build():
    fast_rows = load('fast_track_location_20260927.json')['items']
    canonical = load('pilot_canonical_verified_20260927.json')['projects']
    addressed = [p for p in canonical if p['location']['representative_address']]
    by_id = {p['raw']['candidate_ids'][0]: p for p in canonical}
    stored = in_database()
    rows = []
    for fast in fast_rows:
        key = compact(fast['project_name'])
        matches = []
        for registry in addressed:
            if registry['location']['district'] != fast['district']:
                continue
            if len(key) < MIN_PROGRAM_NAME or key not in compact(
                    registry['identity']['official_project_name']):
                continue
            matches.append({'registry_project_id': registry['raw']['candidate_ids'][0],
                            'registry_project_name': registry['identity']['official_project_name'],
                            'registry_address': registry['location']['representative_address'],
                            'registry_dong': registry['location']['dong'],
                            'registry_type': registry['classification']['canonical_project_type'],
                            'registry_source_url': registry['location']['address_source_url'],
                            'signals': signals(fast, registry)})
        status, chosen, reason = classify(fast, matches)
        project = by_id.get(fast['project_id'], {})
        rows.append({
            'project_id': fast['project_id'], 'project_name': fast['project_name'],
            'official_candidate': (chosen or {}).get('registry_project_name'),
            'district': fast['district'],
            'dong': (chosen or {}).get('registry_dong'),
            'official_address': (chosen or {}).get('registry_address'),
            'official_url': (chosen or {}).get('registry_source_url') or fast['source_url'],
            'identity_evidence': {'fast_track_source': fast['official_source'],
                                  'fast_track_source_url': fast['source_url'],
                                  'fast_track_official_id': fast['official_id'],
                                  'fast_track_raw_row': fast['raw_source_text'],
                                  'fast_track_raw_stage': fast['raw_stage'],
                                  'lot_in_project_name': fast['lot_in_name'],
                                  'dong_tokens': fast['dong_tokens'],
                                  'program': (project.get('classification') or {}).get('program'),
                                  'candidates': matches},
            'identity_status': status,
            'address_recoverable': status == 'IDENTITY_CONFIRMED' or bool(fast['lot_in_name']),
            'conflict_reason': reason if status == 'IDENTITY_CONFLICT' else None,
            'in_database': fast['project_id'] in stored,
            'candidate_in_database': bool(chosen and chosen['registry_project_id'] in stored),
            # 둘 다 DB에 있으면 주소를 옮기는 순간 같은 자리에 마커가 둘 생긴다.
            # 그때 필요한 것은 주소 복원이 아니라 동일 사업 중복 정리다.
            'duplicate_risk': bool(chosen and fast['project_id'] in stored
                                   and chosen['registry_project_id'] in stored),
            'reason': reason})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    rows = build()
    counts = {}
    for row in rows:
        counts[row['identity_status']] = counts.get(row['identity_status'], 0) + 1
    document = {'format': 'zipon-fast-track-identity-v1', 'generated_at': now(),
                'db_write': False,
                'note': ('IDENTITY_CONFIRMED만 주소 복원 후보입니다. PROBABLE과 CONFLICT는 '
                         'DB에 반영하지 않습니다. 이 실행은 canonical을 수정하지 않습니다.'),
                'totals': dict(counts, fast_track_total=len(rows),
                               address_recoverable=sum(1 for r in rows if r['address_recoverable']),
                               duplicate_risk=sum(1 for r in rows if r['duplicate_risk']),
                               in_database=sum(1 for r in rows if r['in_database'])),
                'items': rows}
    if args.write:
        OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n',
                          encoding='utf-8')
    print(json.dumps({'fast_track_total': len(rows), 'counts': counts,
                      'address_recoverable': document['totals']['address_recoverable'],
                      'written': bool(args.write)}, ensure_ascii=False))
    for row in rows:
        print(f"  {row['identity_status']:19s} {row['district']:5s} {row['project_name']:16s} "
              f"{str(row['official_address'] or '-'):30s} {row['reason'][:52]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
