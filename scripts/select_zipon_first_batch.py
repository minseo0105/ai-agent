"""Pick the first reviewed import batch and dry-run it. No DB connection, no write.

Selection draws only on the verified canonical artifacts. Every candidate must
already be import-eligible; the ten are then chosen for district and type
coverage in a deterministic order, so rerunning produces the same batch.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_collector import MAX_IMPORT_BATCH
from services.development_identity import latent_overlap, program_identities
from services.development_official import compact, now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
BATCH_FILE = DATA / 'import_batch_01_20260927.json'
DRYRUN_FILE = DATA / 'import_batch_01_dryrun_20260927.json'
DRY_RUN_FIELDS = ('canonical_id', 'project_id', 'external_id', 'project_name', 'project_type',
                  'program', 'district', 'dong', 'address', 'stage', 'stage_raw', 'status',
                  'validation_status', 'source_name', 'source_url', 'content_hash')


def eligible(project, identities=()):
    """Highest-trust tier: official identity, official address, official stage, and
    no unresolved identity question of any kind."""
    reasons = []
    if latent_overlap(project, identities):
        # The pair detector compares zone tokens, so "(천호 A1-2)" inside a registry
        # name was never paired with the program row "천호A1-2". Importing it would
        # plant a duplicate identity, so it waits for the official detail read.
        reasons.append('LATENT_PROGRAM_IDENTITY_OVERLAP')
    if project['quality_state'] not in ('VERIFIED', 'PARTIALLY_VERIFIED'):
        reasons.append('QUALITY_STATE_' + project['quality_state'])
    if project['import_plan']['existing_canary']:
        reasons.append('ALREADY_IMPORTED_AS_CANARY')
    if project['duplicate']['unresolved'] or project['duplicate']['class'] != 'UNIQUE':
        reasons.append('IDENTITY_NOT_SETTLED')
    if not project['identity']['official_external_id']:
        reasons.append('NO_OFFICIAL_EXTERNAL_ID')
    if not project['location']['address_verified']:
        reasons.append('NO_OFFICIAL_ADDRESS')
    if not project['progress']['stage_verified']:
        reasons.append('STAGE_NOT_OFFICIALLY_MAPPED')
    if not project['provenance']['is_official'] or not project['provenance']['content_hash']:
        reasons.append('NO_OFFICIAL_PROVENANCE')
    if project['raw']['raw_candidate_count'] != 1:
        reasons.append('MERGED_IDENTITY_NEEDS_DB_DECISION')
    return reasons


def rank(project):
    """Deterministic order inside a district: cover 재개발 as well as 재건축, then by id."""
    return (0 if project['classification']['canonical_project_type'] == 'REDEVELOPMENT' else 1,
            0 if project['status']['status_verified'] else 1,
            project['canonical_id'])


def select(projects, size=MAX_IMPORT_BATCH):
    identities = program_identities(projects)
    pool = [p for p in projects if not eligible(p, identities)]
    districts = sorted({p['location']['district'] for p in pool})
    queues = {d: sorted([p for p in pool if p['location']['district'] == d], key=rank)
              for d in districts}
    chosen, index = [], 0
    while len(chosen) < size and any(queues.values()):
        district = districts[index % len(districts)]
        if queues[district]:
            chosen.append(queues[district].pop(0))
        index += 1
    return chosen, pool


def row(project, record):
    return {'canonical_id': project['canonical_id'], 'project_id': record['project_id'],
            'external_id': record['external_id'], 'project_name': record['project_name'],
            'project_type': record['project_type'],
            'program': project['classification']['program'],
            'district': record['sigungu'],
            'dong': project['location']['dong'], 'dong_in_raw_record': record['dong'],
            'address': record['address'], 'stage': record['stage'],
            'stage_raw': record['stage_raw'], 'normalized_stage': project['progress']['normalized_stage'],
            'status': record['status'], 'normalized_status': project['status']['normalized_status'],
            'validation_status': record['validation_status'],
            'source_name': record['source']['source_name'],
            'source_url': record['source']['source_url'],
            'content_hash': record['source']['content_hash'],
            'source_validation_status': record['source']['validation_status']}


def dry_run(rows, canary):
    """Everything that must hold before a single write is attempted."""
    canary_ids = {r['project_id'] for r in canary}
    canary_externals = {r['external_id'] for r in canary if r['external_id']}
    checks, collisions = [], []
    project_ids = [r['project_id'] for r in rows]
    externals = [r['external_id'] for r in rows]

    def check(name, ok, detail=None):
        checks.append({'check': name, 'result': 'PASS' if ok else 'FAIL', 'detail': detail})
        return ok

    check('batch_size_within_limit', 1 <= len(rows) <= MAX_IMPORT_BATCH, len(rows))
    check('project_id_is_uuid', all(str(uuid.UUID(i)) == i for i in project_ids))
    check('project_id_unique', len(set(project_ids)) == len(project_ids))
    check('external_id_present', all(externals))
    check('external_id_unique', len(set(externals)) == len(externals))
    for field in ('project_name', 'project_type', 'district', 'address', 'stage_raw',
                  'source_name', 'source_url', 'content_hash'):
        check('field_present_' + field, all(r[field] for r in rows))
    check('content_hash_is_sha256', all(re.fullmatch(r'[0-9a-f]{64}', r['content_hash'] or '')
                                        for r in rows))
    check('official_source_host', all(re.match(r'https://(cleanup|news)\.seoul\.go\.kr/', r['source_url'])
                                      for r in rows))
    check('stage_not_promoted_in_payload', all(r['stage'] is None for r in rows))
    check('status_not_promoted_in_payload', all(r['status'] == 'UNKNOWN' for r in rows))
    check('validation_status_stays_needs_review',
          all(r['validation_status'] == 'NEEDS_REVIEW' for r in rows))
    check('source_validation_status_stays_unverified',
          all(r['source_validation_status'] == 'UNVERIFIED' for r in rows))
    for candidate in rows:
        if candidate['project_id'] in canary_ids:
            collisions.append({'project_id': candidate['project_id'], 'kind': 'CANARY_PROJECT_ID'})
        if candidate['external_id'] in canary_externals:
            collisions.append({'project_id': candidate['project_id'], 'kind': 'CANARY_EXTERNAL_ID'})
    check('no_canary_collision', not collisions, collisions)
    contained = [[a['project_name'], b['project_name']] for a in rows for b in rows
                 if a is not b and compact(a['project_name']) in compact(b['project_name'])]
    check('no_name_containment_inside_batch', not contained, contained)
    return {'result': 'PASS' if all(c['result'] == 'PASS' for c in checks) else 'FAIL',
            'checks': checks, 'canary_collisions': collisions,
            'canary_rows_in_database': len(canary_ids)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--size', type=int, default=MAX_IMPORT_BATCH)
    args = ap.parse_args()
    if not 1 <= args.size <= MAX_IMPORT_BATCH:
        raise SystemExit(f'size must be 1..{MAX_IMPORT_BATCH}')
    canonical = json.loads((DATA / 'pilot_canonical_verified_20260927.json').read_text(encoding='utf-8'))
    canary = json.loads((DATA / 'canary_20260927.json').read_text(encoding='utf-8'))['records']
    raw = {r['project_id']: r for r in
           json.loads((DATA / 'pilot_20260927.json').read_text(encoding='utf-8'))['records']}

    chosen, pool = select(canonical['projects'], args.size)
    identities = program_identities(canonical['projects'])
    deferred = [{'canonical_id': p['canonical_id'],
                 'official_project_name': p['identity']['official_project_name'],
                 'official_external_id': p['identity']['official_external_id'],
                 'district': p['location']['district'],
                 'overlaps': latent_overlap(p, identities),
                 'reason': 'LATENT_PROGRAM_IDENTITY_OVERLAP',
                 'action': 'needs the official detail read before any import'}
                for p in canonical['projects']
                if p['quality_state'] != 'NEEDS_REVIEW' and not p['import_plan']['existing_canary']
                and latent_overlap(p, identities)]
    records, rows = [], []
    for project in chosen:
        record = raw[project['raw']['candidate_ids'][0]]
        records.append(record)
        rows.append(row(project, record))
    result = dry_run(rows, canary)

    # A collision would have to be replaced by the next candidate; none is expected
    # because the canary rows are excluded before ranking.
    replaced = []
    while result['canary_collisions'] and pool:
        bad = {c['project_id'] for c in result['canary_collisions']}
        keep = [(p, r, w) for p, r, w in zip(chosen, records, rows) if r['project_id'] not in bad]
        for project in sorted(pool, key=rank):
            if len(keep) >= args.size:
                break
            if project in chosen:
                continue
            record = raw[project['raw']['candidate_ids'][0]]
            keep.append((project, record, row(project, record)))
            replaced.append({'excluded': sorted(bad), 'replacement': project['canonical_id']})
        chosen, records, rows = (list(part) for part in zip(*keep))
        result = dry_run(rows, canary)

    batch = {'format': 'zipon-import-batch-v1', 'generated_at': now(),
             'batch_id': 'batch-01', 'target_project_ref': 'nnxtkvjpzqqhjlgnprzo',
             'db_write': False, 'maximum_batch_size': MAX_IMPORT_BATCH,
             'selection_policy': [
                 'import-eligible only: official identity, official address, official stage, official provenance',
                 'canary rows and unresolved identities excluded before ranking',
                 'deterministic district round-robin so the batch covers all three districts',
                 'raw pilot records are sent verbatim; derived stage/status are not promoted'],
             'records': records}
    BATCH_FILE.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {'format': 'zipon-import-dryrun-v1', 'generated_at': batch['generated_at'],
              'batch_file': str(BATCH_FILE.relative_to(ROOT)), 'db_write': False,
              'eligible_pool': len(pool), 'selected': len(rows),
              'by_district': {d: sum(1 for r in rows if r['district'] == d)
                              for d in sorted({r['district'] for r in rows})},
              'by_project_type': {t: sum(1 for r in rows if r['project_type'] == t)
                                  for t in sorted({r['project_type'] for r in rows})},
              'replacements': replaced,
              'deferred_latent_identity_overlap': deferred,
              'dry_run': result, 'candidates': rows}
    DRYRUN_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('eligible_pool', 'selected', 'by_district',
                                             'by_project_type', 'replacements')}, ensure_ascii=False))
    print('DEFERRED (latent identity overlap):', len(deferred))
    print('DRY RUN:', result['result'])
    for entry in result['checks']:
        if entry['result'] == 'FAIL':
            print('  FAIL', entry['check'], entry['detail'])
    print('CANARY COLLISION:', len(result['canary_collisions']))
    return 0 if result['result'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
