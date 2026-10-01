"""서울 25개 수집 결과 -> 검증된 upsert artifact. Supabase에 쓰지 않는다.

  python scripts/build_zipon_seoul_import.py --input data/development/seoul25_raw.json \
      --out data/development/seoul25_import_artifact.json

이 스크립트는 네트워크도 DB도 쓰지 않습니다. 하는 일은 수집 결과를 받아
적재해도 되는 것과 안 되는 것으로 가르고, 기존 project_id와 비교해 insert/update를
정하고, 자치구별 coverage 표를 내는 것까지입니다. 실제 적재는 기존 reviewed
경로(scripts/import_zipon_candidates.py, 배치 10건)로만 합니다.

reject 사유는 버리지 않습니다. 0건인 자치구도 '사업이 없음'과 '수집 실패'를
runs의 status/source_complete로 구분해 남깁니다.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_collector as dc
from services.development_quality import refine

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / 'data/development/lifecycle_audit_20260929.json'
# 코드가 아는 project URL은 Production 하나뿐이다. 여기에 쓰지 않는다는 사실을 박아 둔다.
PRODUCTION_URL = 'https://nnxtkvjpzqqhjlgnprzo.supabase.co'


def existing_projects(path):
    if not Path(path).exists():
        return {}
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    items = payload.get('items') or payload.get('projects') or []
    return {i['project_id']: (i.get('district') or i.get('sigungu'))
            for i in items if i.get('project_id')}


def row_rejections(record, scope):
    """이 행을 적재 대상에서 빼야 하는 이유. 전부 모아서 돌려준다."""
    reasons = []
    if record.get('sigungu') not in scope:
        reasons.append('SIGUNGU_OUT_OF_SCOPE')
    if not record.get('project_name'):
        reasons.append('NO_PROJECT_NAME')
    if record.get('project_type') not in ('REDEVELOPMENT', 'RECONSTRUCTION', 'SHINTONG', 'MOATOWN'):
        reasons.append('UNKNOWN_PROJECT_TYPE')
    if not (record.get('source') or {}).get('source_url'):
        reasons.append('NO_OFFICIAL_SOURCE_URL')
    # 좌표가 없는 것은 reject가 아니다. 목록에는 남고 marker만 없다.
    # 좌표가 '틀린' 것만 뺀다.
    if record.get('location') and record.get('location_sigungu') != record.get('sigungu'):
        reasons.append('LOCATION_SIGUNGU_MISMATCH')
    return reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', required=True, type=Path, help='collect() 결과 JSON')
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE,
                        help='기존 project_id 비교용 읽기 전용 snapshot')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    collected = json.loads(args.input.read_text(encoding='utf-8'))
    records = collected.get('records') or []
    scope = set(collected.get('districts') or dc.SEOUL_DISTRICTS)
    known = existing_projects(args.baseline)

    accepted, rejected = [], []
    for record in records:
        reasons = row_rejections(record, scope)
        (rejected if reasons else accepted).append(
            dict(record, reject_reasons=reasons) if reasons else record)

    canonical_doc, review_doc, quality = refine(accepted)
    seen, inserts, updates, duplicates = set(), [], [], []
    for record in accepted:
        pid = record['project_id']
        if pid in seen:
            duplicates.append(pid)
            continue
        seen.add(pid)
        (updates if pid in known else inserts).append(record)

    # 자치구별 수집 완결성. 0건의 두 사정을 여기서 가른다.
    # run은 source id만 들고 있다. directory는 cleanup_<코드>라 구를 특정할 수 있고,
    # 시 전체 page는 범위 전체에 걸린다.
    code_to_district = {code: name for name, code in dc.SEOUL_SIGNGU_CODE.items()}
    run_by_district = {district: [] for district in scope}
    for run in collected.get('runs') or []:
        source_id = run.get('source') or ''
        if source_id.startswith('cleanup_'):
            district = code_to_district.get(source_id.split('_', 1)[1])
            if district in run_by_district:
                run_by_district[district].append(run)
        else:
            for district in run_by_district:
                run_by_district[district].append(run)
    source_state = {}
    for district in sorted(scope):
        runs = run_by_district.get(district) or []
        failed = [r['source'] for r in runs if r.get('status') == 'FAILED']
        partial = [r['source'] for r in runs if r.get('status') == 'PARTIAL']
        source_state[district] = {
            'failed_sources': failed, 'partial_sources': partial,
            'complete': bool(runs) and not failed and all(r.get('source_complete') for r in runs)}

    coverage = {}
    for district in sorted(scope):
        rows = [r for r in records if r.get('sigungu') == district]
        ok = [r for r in accepted if r.get('sigungu') == district]
        state = source_state.get(district, {})
        coverage[district] = {
            'signgu_code': dc.SEOUL_SIGNGU_CODE.get(district),
            'raw': len(rows),
            'normalized': len([c for c in canonical_doc['projects'] if c['district'] == district]),
            'geocoded': sum(bool(r.get('location')) for r in ok),
            'insert_candidate': sum(1 for r in inserts if r.get('sigungu') == district),
            'update_candidate': sum(1 for r in updates if r.get('sigungu') == district),
            'duplicate': len(ok) - len({r['project_id'] for r in ok}),
            'reject': sum(1 for r in rejected if r.get('sigungu') == district),
            # 0건일 때: 수집은 끝났는지, 실패했는지.
            'zero_reason': None if len(rows) else (
                'COLLECTION_FAILED' if state.get('failed_sources')
                else 'INCOMPLETE_COLLECTION' if state.get('partial_sources')
                else 'NO_DATA_AT_SOURCE' if state.get('complete')
                else 'NOT_COLLECTED'),
        }

    empty = [d for d, v in coverage.items() if v['raw'] == 0]
    artifact = {
        'format': 'zipon-seoul-import-artifact-v1',
        'generated_from': str(args.input.name),
        'collected_at': collected.get('collected_at'),
        'db_write': False,
        'supabase_write': 'NONE',
        'write_target_known': PRODUCTION_URL,
        'write_policy': ('PRODUCTION_ONLY_TARGET_KNOWN; artifact only. '
                         'Import through scripts/import_zipon_candidates.py in reviewed '
                         'batches of %d. No DELETE, no TRUNCATE, no bulk UPDATE.'
                         % dc.MAX_IMPORT_BATCH),
        'identity_normalizer': dc.IDENTITY_NORMALIZER_VERSION,
        'districts': sorted(scope),
        'totals': {'raw': len(records), 'accepted': len(accepted), 'rejected': len(rejected),
                   'valid_projects': len(seen), 'insert': len(inserts), 'update': len(updates),
                   'duplicate_rows': len(duplicates),
                   'canonical': len(canonical_doc['projects']),
                   'probable_duplicate_pairs': len(review_doc['pairs'])},
        'reject_reasons': dict(sorted(Counter(
            reason for r in rejected for reason in r['reject_reasons']).items())),
        'existing_baseline': {'rows': len(known),
                              'by_district': dict(sorted(Counter(known.values()).items())),
                              'matched_as_update': len(updates),
                              'recreated_as_insert': sum(1 for r in inserts
                                                         if r['project_id'] in known)},
        'coverage': coverage,
        'zero_districts': empty,
        'quality': quality['quality'],
        'upsert': [{'project_id': r['project_id'], 'operation':
                    'update' if r['project_id'] in known else 'insert',
                    'project': {k: v for k, v in r.items()
                                if k not in ('source', 'revision') and v is not None},
                    'source': r['source']}
                   for r in inserts + updates],
        'rejected': [{'project_id': r['project_id'], 'sigungu': r.get('sigungu'),
                      'project_name': r.get('project_name'),
                      'reasons': r['reject_reasons']} for r in rejected],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    summary = {k: artifact[k] for k in ('totals', 'reject_reasons', 'existing_baseline',
                                        'zero_districts')}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
