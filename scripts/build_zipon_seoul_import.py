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

# public.development_projects의 컬럼(20260926_zipon_base_and_development.sql).
# 수집·지오코딩이 만든 작업용 필드(location_sigungu, location_review 등)는 컬럼이
# 아니므로 payload에서 떨어뜨리고, 무엇을 떨어뜨렸는지 artifact에 남긴다.
PROJECT_COLUMNS = frozenset((
    'project_id', 'project_type', 'project_name', 'official_authority', 'external_id',
    'parent_project_id', 'related_types', 'sido', 'sigungu', 'dong', 'legal_dong_code',
    'address', 'status', 'validation_status', 'stage', 'stage_raw', 'stage_mapping_version',
    'selected_date', 'notice_date', 'area_m2', 'planned_units', 'planned_floor', 'planned_far',
    'location', 'geometry', 'location_source', 'location_verified_at', 'geometry_source',
    'geometry_verified', 'geometry_verified_at', 'canonical_source_id', 'confidence_level',
    'field_evidence', 'source_date', 'last_verified_at', 'revision'))


def attach_coordinates(records, path):
    """좌표 검증을 통과한 것만 붙인다. 통과하지 못한 사업은 좌표 없이 남는다."""
    if not path or not Path(path).exists():
        return records, {'applied': 0, 'source': None}
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    accepted = {i['project_id']: i for i in report.get('items') or []
                if i.get('bucket') == 'geocoded' and i.get('location')}
    applied = 0
    out = []
    for record in records:
        hit = accepted.get(record['project_id'])
        if hit and not record.get('location'):
            record = dict(record, location=hit['location'],
                          location_source=hit.get('geocode_source'),
                          location_sigungu=hit.get('answered_sigungu') or record.get('sigungu'))
            applied += 1
        out.append(record)
    return out, {'applied': applied, 'source': Path(path).name,
                 'totals': report.get('totals'), 'mode': report.get('mode')}


def payload(record):
    """schema 컬럼만 남긴다. 알 수 없는 키는 조용히 보내지 않고 빼서 보고한다."""
    kept = {k: v for k, v in record.items()
            if k in PROJECT_COLUMNS and k != 'revision' and v is not None}
    dropped = sorted(k for k in record if k not in PROJECT_COLUMNS and k != 'source')
    return kept, dropped


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
    parser.add_argument('--geocode', type=Path, default=None,
                        help='geocode_zipon_seoul25.py 결과. 검증 통과한 좌표만 붙인다')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--batch-dir', type=Path, default=None,
                        help='기존 importer가 그대로 받는 배치 파일을 여기에 쓴다')
    args = parser.parse_args()

    collected = json.loads(args.input.read_text(encoding='utf-8'))
    records = collected.get('records') or []
    records, geocoding = attach_coordinates(records, args.geocode)
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
    no_coordinate = [r for r in inserts + updates if not r.get('location')]
    dropped_keys = set()
    upsert = []
    for record in inserts + updates:
        project, dropped = payload(record)
        dropped_keys |= set(dropped)
        upsert.append({'project_id': record['project_id'],
                       'operation': 'update' if record['project_id'] in known else 'insert',
                       'has_coordinate': bool(record.get('location')),
                       'project': project, 'source': record['source']})
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
        'geocoding': geocoding,
        'buckets': {'insert': len(inserts), 'update': len(updates),
                    'reject': len(rejected), 'no_coordinate': len(no_coordinate),
                    'duplicate_review': len(review_doc['pairs'])},
        'schema': {'table': 'public.development_projects',
                   'upsert_key': 'project_id',
                   'method': 'rpc/zipon_ingest_candidate (project_id UPSERT, expected_revision)',
                   'columns_checked': len(PROJECT_COLUMNS),
                   'non_column_fields_dropped': sorted(dropped_keys),
                   'unknown_columns_sent': []},
        'duplicate_review': review_doc['pairs'],
        'import_command': ('python scripts/import_zipon_candidates.py '
                           '<batch-dir>/batch_0001.json --apply-new-db'
                           '   # project_id UPSERT via rpc/zipon_ingest_candidate, %d rows max'
                           % dc.MAX_IMPORT_BATCH),
        'upsert': upsert,
        'rejected': [{'project_id': r['project_id'], 'sigungu': r.get('sigungu'),
                      'project_name': r.get('project_name'),
                      'reasons': r['reject_reasons']} for r in rejected],
    }
    # 기존 reviewed importer(scripts/import_zipon_candidates.py)가 받는 모양 그대로,
    # MAX_IMPORT_BATCH 단위로 쪼개 쓴다. 한 파일이 한 번의 승인 단위다.
    batches = []
    if args.batch_dir:
        args.batch_dir.mkdir(parents=True, exist_ok=True)
        flat = [dict(row['project'], source=row['source']) for row in upsert]
        for index in range(0, len(flat), dc.MAX_IMPORT_BATCH):
            chunk = flat[index:index + dc.MAX_IMPORT_BATCH]
            name = 'batch_%04d.json' % (index // dc.MAX_IMPORT_BATCH + 1)
            (args.batch_dir / name).write_text(
                json.dumps({'records': chunk}, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8')
            batches.append({'file': name, 'records': len(chunk)})
        artifact['batches'] = {'directory': str(args.batch_dir), 'count': len(batches),
                               'batch_size': dc.MAX_IMPORT_BATCH, 'files': batches}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    summary = {k: artifact[k] for k in ('totals', 'buckets', 'geocoding', 'schema',
                                        'reject_reasons', 'existing_baseline',
                                        'zero_districts')}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
