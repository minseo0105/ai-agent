"""Bulk initial load for ZIP:ON development projects. One command, ten at a time.

Reuses the validated first-batch gates (services.development_identity plus the
selector's eligible/rank/row/dry_run) and the existing credential handling from
scripts/import_zipon_candidates.py. Nothing new is invented here.

  python scripts/import_zipon_bulk.py --check-config   # credentials only, no HTTP
  python scripts/import_zipon_bulk.py --dry-run        # plan, 0 database writes
  python scripts/import_zipon_bulk.py --apply          # runs every batch in sequence

Safety: batches never exceed ten, a failing candidate is quarantined and the run
continues, an identity collision is skipped, a project already in the database is
an idempotent skip, and only rpc/zipon_ingest_candidate_v2 plus the collection-run
rows are ever written. No DELETE, no PATCH of development_projects, no secret in
any output.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from select_zipon_first_batch import dry_run, eligible, rank, row
from services.development_collector import MAX_IMPORT_BATCH
from services.development_identity import program_identities
from services.development_official import now
from import_zipon_candidates import ImportDiagnostic, import_configuration, validate_records

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
PLAN_FILE = DATA / 'bulk_import_plan_20260927.json'
RESULT_FILE = DATA / 'bulk_import_result_20260927.json'
QUARANTINE_FILE = DATA / 'bulk_import_quarantine_20260927.json'
PROJECT_REF = 'nnxtkvjpzqqhjlgnprzo'
RPC = 'rpc/zipon_ingest_candidate_v2'


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def promotion_risk(record):
    """The payload must not carry an approval decision into the master row."""
    reasons = []
    if record.get('stage') is not None:
        reasons.append('PAYLOAD_CARRIES_STAGE')
    if record.get('status') != 'UNKNOWN':
        reasons.append('PAYLOAD_CARRIES_STATUS')
    if record.get('validation_status') != 'NEEDS_REVIEW':
        reasons.append('PAYLOAD_CARRIES_VALIDATION_STATUS')
    source = record.get('source') or {}
    if source.get('validation_status') != 'UNVERIFIED':
        reasons.append('SOURCE_CARRIES_VALIDATION_STATUS')
    if source.get('is_official') is not True or not source.get('source_url') \
            or not source.get('content_hash') or not isinstance(source.get('raw_snapshot'), dict):
        reasons.append('NO_SOURCE_PROVENANCE')
    if record.get('geometry') is not None or record.get('location') is not None:
        reasons.append('PAYLOAD_CARRIES_GEOMETRY')
    return reasons


def build_plan():
    """Everything that is safe to load, ordered and cut into batches of ten."""
    canonical = load('pilot_canonical_verified_20260927.json')['projects']
    raw = {r['project_id']: r for r in load('pilot_20260927.json')['records']}
    baseline = load('db_baseline_20260927.json')
    canary = load('canary_20260927.json')['records']
    first_batch = load('import_batch_01_20260927.json')['records']
    identities = program_identities(canonical)

    known_ids = {p['project_id'] for p in baseline['projects']}
    known_externals = {p['external_id'] for p in baseline['projects'] if p['external_id']}
    known_identity = {(p['official_authority'], p['external_id']) for p in baseline['projects']
                      if p['external_id']}
    canary_ids = {r['project_id'] for r in canary}
    first_ids = {r['project_id'] for r in first_batch}

    eligible_rows, quarantined, skipped = [], [], []
    for project in canonical:
        record = raw[project['raw']['candidate_ids'][0]]
        reasons = eligible(project, identities) + promotion_risk(record)
        identity = (record.get('official_authority'), record.get('external_id'))
        if record['project_id'] in known_ids:
            skipped.append({'project_id': record['project_id'], 'canonical_id': project['canonical_id'],
                            'project_name': record['project_name'], 'kind': 'ALREADY_IN_DATABASE',
                            'origin': 'canary' if record['project_id'] in canary_ids
                                      else 'first_batch' if record['project_id'] in first_ids else 'baseline'})
            continue
        if record.get('external_id') in known_externals or identity in known_identity:
            # A different project_id reusing an identifier already in the database
            # would break UNIQUE (official_authority, external_id).
            quarantined.append({'project_id': record['project_id'], 'canonical_id': project['canonical_id'],
                                'project_name': record['project_name'],
                                'reasons': ['IDENTITY_COLLISION_WITH_DATABASE'],
                                'detail': {'external_id': record.get('external_id')}})
            continue
        if reasons:
            quarantined.append({'project_id': record['project_id'], 'canonical_id': project['canonical_id'],
                                'project_name': record['project_name'], 'district': record['sigungu'],
                                'reasons': reasons,
                                'quality_state': project['quality_state']})
            continue
        eligible_rows.append((project, record))

    # Deterministic district round-robin over the whole pool, so each batch of ten
    # still spans districts. Same ordering rule as the first batch.
    districts = sorted({p['location']['district'] for p, _ in eligible_rows})
    queues = {d: sorted([pair for pair in eligible_rows if pair[0]['location']['district'] == d],
                        key=lambda pair: rank(pair[0])) for d in districts}
    ordered, index = [], 0
    while any(queues.values()):
        district = districts[index % len(districts)]
        if queues[district]:
            ordered.append(queues[district].pop(0))
        index += 1

    batches = []
    for start in range(0, len(ordered), MAX_IMPORT_BATCH):
        chunk = ordered[start:start + MAX_IMPORT_BATCH]
        rows = [row(project, record) for project, record in chunk]
        batches.append({'batch_id': f'bulk-{len(batches) + 1:02d}', 'size': len(chunk),
                        'records': [record for _, record in chunk],
                        'candidates': rows, 'dry_run': dry_run(rows, canary)})
    identity_conflicts = [q for q in quarantined
                          if 'IDENTITY_COLLISION_WITH_DATABASE' in q['reasons']]
    duplicate_risk = [q for q in quarantined if {'IDENTITY_NOT_SETTLED',
                                                 'LATENT_PROGRAM_IDENTITY_OVERLAP'} & set(q['reasons'])]
    plan = {'format': 'zipon-bulk-import-plan-v1', 'generated_at': now(),
            'target_project_ref': PROJECT_REF, 'db_write': False, 'rpc': RPC,
            'maximum_batch_size': MAX_IMPORT_BATCH,
            'policy': ['eligible only: official identity, address, stage and provenance',
                       'projects already in the database are idempotent skips',
                       'identity collisions and unsettled identities are quarantined',
                       'payload never carries stage, status, validation_status or geometry',
                       'seoul-identity-v1 is frozen: project_id is used as collected'],
            'totals': {'total_source': len(canonical), 'already_in_db': len(skipped),
                       'eligible': len(ordered), 'quarantined': len(quarantined),
                       'batch_count': len(batches), 'expected_new': len(ordered),
                       'expected_update': 0, 'identity_conflict': len(identity_conflicts),
                       'duplicate_risk': len(duplicate_risk)},
            'by_district': {d: sum(1 for p, _ in ordered if p['location']['district'] == d)
                            for d in districts},
            'by_type': {t: sum(1 for _, r in ordered if r['project_type'] == t)
                        for t in sorted({r['project_type'] for _, r in ordered})},
            'baseline': baseline['counts'],
            'dry_run_result': 'PASS' if all(b['dry_run']['result'] == 'PASS' for b in batches) else 'FAIL',
            'batches': [{k: v for k, v in b.items() if k != 'records'} for b in batches]}
    quarantine = {'format': 'zipon-bulk-quarantine-v1', 'generated_at': plan['generated_at'],
                  'db_write': False,
                  'policy': 'quarantined candidates are never written; they wait for review',
                  'totals': {'quarantined': len(quarantined), 'already_in_db': len(skipped),
                             'identity_conflict': len(identity_conflicts),
                             'duplicate_risk': len(duplicate_risk)},
                  'items': sorted(quarantined, key=lambda q: q['project_id']),
                  'already_in_database': sorted(skipped, key=lambda s: s['project_id'])}
    return plan, quarantine, batches


def transport(url, headers):
    import requests

    def request(method, table, payload=None, params=None):
        response = requests.request(method, f'{url}/rest/v1/{table}', json=payload, params=params,
                                    headers=headers, timeout=30, allow_redirects=False)
        if not 200 <= response.status_code < 300:
            raise ImportDiagnostic('HTTP_STATUS_' + str(response.status_code))
        return response.json() if response.content else []
    return request


def live_state(request, project_ids):
    """Current revision per project_id, plus the identities already taken."""
    state, identities = {}, {}
    for start in range(0, len(project_ids), 50):
        chunk = project_ids[start:start + 50]
        rows = request('GET', 'development_projects',
                       params={'project_id': 'in.(' + ','.join(chunk) + ')',
                               'select': 'project_id,revision,validation_status,external_id,official_authority'})
        for item in rows:
            state[item['project_id']] = item
    taken = request('GET', 'development_projects',
                    params={'select': 'project_id,official_authority,external_id',
                            'external_id': 'not.is.null'})
    for item in taken:
        identities[(item['official_authority'], item['external_id'])] = item['project_id']
    return state, identities


def apply_batches(batches, request):
    """Run every batch in sequence. One bad candidate never stops the run."""
    counts = {'new': 0, 'changed': 0, 'unchanged': 0, 'review_required': 0,
              'idempotent_skipped': 0, 'identity_skipped': 0, 'failed': 0}
    results, failures, skipped = [], [], []
    all_ids = [r['project_id'] for batch in batches for r in batch['records']]
    state, identities = live_state(request, all_ids)
    for batch in batches:
        if not 1 <= len(batch['records']) <= MAX_IMPORT_BATCH:
            raise ImportDiagnostic('BULK_BATCH_LIMIT_1_TO_10')
        run_id = str(uuid.uuid4())
        request('POST', 'development_collection_runs', payload={
            'run_id': run_id, 'source_name': 'ZIP:ON bulk initial load ' + batch['batch_id'],
            'source_type': 'OFFICIAL_WEBSITE', 'collector_version': 'seoul-tables-v1',
            'dry_run': False, 'source_complete': False})
        for record in batch['records']:
            identity = (record.get('official_authority'), record.get('external_id'))
            if record['project_id'] in state:
                counts['idempotent_skipped'] += 1
                skipped.append({'project_id': record['project_id'], 'kind': 'ALREADY_IN_DATABASE'})
                continue
            if identity in identities:
                counts['identity_skipped'] += 1
                skipped.append({'project_id': record['project_id'], 'kind': 'IDENTITY_TAKEN',
                                'existing_project_id': identities[identity]})
                continue
            project = {k: v for k, v in record.items()
                       if k not in ('source', 'revision') and v is not None}
            try:
                answer = request('POST', RPC, payload={
                    'p_project': project, 'p_source': record['source'], 'p_expected_revision': 0,
                    'p_change': {'kind': 'INITIAL', 'review_required': False, 'review_reasons': []},
                    'p_run_id': run_id})
                outcome = (answer or {}).get('result', 'unchanged')
                counts[outcome] = counts.get(outcome, 0) + 1
                results.append({'project_id': record['project_id'], 'batch_id': batch['batch_id'],
                                'result': outcome, 'revision': (answer or {}).get('revision'),
                                'update_kind': (answer or {}).get('update_kind')})
                if outcome in ('new', 'changed'):
                    identities[identity] = record['project_id']
                    state[record['project_id']] = {'project_id': record['project_id'], 'revision': 1}
            except Exception as exc:
                counts['failed'] += 1
                failures.append({'project_id': record['project_id'], 'batch_id': batch['batch_id'],
                                 'error_type': type(exc).__name__,
                                 'reason': getattr(exc, 'safe_reason', 'DETAILS_SUPPRESSED')})
        request('PATCH', 'development_collection_runs', params={'run_id': 'eq.' + run_id},
                payload={'finished_at': now(), 'status': 'PARTIAL' if failures else 'SUCCEEDED',
                         'new_count': counts['new'], 'changed_count': counts['changed'],
                         'unchanged_count': counts['unchanged'],
                         'validation_failed_count': counts['failed']})
    return {'counts': counts, 'results': results, 'failures': failures, 'skipped': skipped}


def reconcile(request, plan, applied):
    """Read the database back. GET only."""
    checks = []

    def check(name, ok, detail=None):
        checks.append({'check': name, 'result': 'PASS' if ok else 'FAIL', 'detail': detail})

    baseline = load('db_baseline_20260927.json')
    canary_ids = sorted(r['project_id'] for r in load('canary_20260927.json')['records'])
    first_ids = sorted(r['project_id'] for r in load('import_batch_01_20260927.json')['records'])
    expected_total = baseline['counts']['total'] + applied['counts']['new']
    projects = request('GET', 'development_projects',
                       params={'select': 'project_id,official_authority,external_id,revision,'
                                         'validation_status,status,stage,address'})
    by_id = {p['project_id']: p for p in projects}
    check('expected_vs_actual_project_count', len(projects) == expected_total,
          {'expected': expected_total, 'actual': len(projects)})
    check('no_duplicate_project_id', len({p['project_id'] for p in projects}) == len(projects))
    identities = [(p['official_authority'], p['external_id']) for p in projects if p['external_id']]
    check('no_duplicate_external_identity', len(set(identities)) == len(identities))
    loaded = [r['project_id'] for r in applied['results'] if r['result'] == 'new']
    if loaded:
        sources = request('GET', 'development_project_sources',
                          params={'project_id': 'in.(' + ','.join(loaded) + ')',
                                  'select': 'project_id,is_official,content_hash,validation_status'})
        updates = request('GET', 'development_updates',
                          params={'project_id': 'in.(' + ','.join(loaded) + ')',
                                  'select': 'project_id,update_kind,to_revision'})
        check('every_loaded_project_has_an_official_source',
              all(any(s['project_id'] == pid and s['is_official'] and s['content_hash']
                      for s in sources) for pid in loaded))
        check('no_loaded_source_is_verified', all(s['validation_status'] != 'VERIFIED' for s in sources))
        check('every_loaded_project_has_history',
              all(any(u['project_id'] == pid for u in updates) for pid in loaded))
        check('loaded_rows_are_not_verified',
              all(by_id.get(pid, {}).get('validation_status') != 'VERIFIED' for pid in loaded))
        check('loaded_rows_did_not_promote_status_or_stage',
              all(by_id.get(pid, {}).get('status') == 'UNKNOWN'
                  and by_id.get(pid, {}).get('stage') in (None, '') for pid in loaded))
    preserved = []
    for item in baseline['projects']:
        live = by_id.get(item['project_id'])
        if live is None or live['revision'] != item['revision'] \
                or live['validation_status'] != item['validation_status']:
            preserved.append(item['project_id'])
    check('baseline_eighteen_preserved', not preserved, preserved)
    check('canary_eight_present', all(pid in by_id for pid in canary_ids))
    check('first_batch_ten_present', all(pid in by_id for pid in first_ids))
    check('quarantined_never_written',
          not any(q['project_id'] in by_id for q in load_quarantine_ids()))
    return {'result': 'FAIL' if any(c['result'] == 'FAIL' for c in checks) else 'PASS',
            'checks': checks, 'actual_project_count': len(projects),
            'expected_project_count': expected_total}


def load_quarantine_ids():
    if not QUARANTINE_FILE.exists():
        return []
    return json.loads(QUARANTINE_FILE.read_text(encoding='utf-8'))['items']


def write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return str(path.relative_to(ROOT))


def summary_lines(plan):
    totals = plan['totals']
    return '\n'.join([
        f"TOTAL SOURCE      {totals['total_source']}",
        f"ALREADY IN DB     {totals['already_in_db']}",
        f"ELIGIBLE          {totals['eligible']}",
        f"QUARANTINED       {totals['quarantined']}",
        f"BATCH COUNT       {totals['batch_count']}",
        f"EXPECTED NEW      {totals['expected_new']}",
        f"EXPECTED UPDATE   {totals['expected_update']}",
        f"IDENTITY CONFLICT {totals['identity_conflict']}",
        f"DUPLICATE RISK    {totals['duplicate_risk']}",
        f"DRY RUN           {plan['dry_run_result']}"])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group()
    group.add_argument('--check-config', action='store_true', help='credentials only, no HTTP')
    group.add_argument('--dry-run', action='store_true', help='plan only, zero database writes')
    group.add_argument('--apply', action='store_true', help='run every batch, then reconcile')
    args = ap.parse_args()

    plan, quarantine, batches = build_plan()
    for batch in batches:
        validate_records(batch['records'])
    files = [write(PLAN_FILE, plan), write(QUARANTINE_FILE, quarantine)]
    print(summary_lines(plan))

    if args.check_config:
        import_configuration()
        print('CONFIGURATION     PASS; no HTTP requests or database writes')
        return 0
    if not args.apply:
        result = {'format': 'zipon-bulk-import-result-v1', 'generated_at': now(), 'mode': 'DRY_RUN',
                  'db_write': False, 'target_project_ref': PROJECT_REF,
                  'planned': plan['totals'], 'dry_run_result': plan['dry_run_result'],
                  'batches': [{'batch_id': b['batch_id'], 'size': b['size'],
                               'dry_run': b['dry_run']['result'],
                               'project_ids': [r['project_id'] for r in b['records']]}
                              for b in batches],
                  'reconciliation': {'status': 'SKIPPED', 'reason': 'DRY_RUN'}}
        files.append(write(RESULT_FILE, result))
        print('MODE              DRY_RUN; 0 database writes')
        print('FILES             ' + ', '.join(files))
        return 0 if plan['dry_run_result'] == 'PASS' else 1

    if plan['dry_run_result'] != 'PASS':
        raise ImportDiagnostic('DRY_RUN_MUST_PASS_BEFORE_APPLY')
    url, headers = import_configuration()
    request = transport(url, headers)
    applied = apply_batches(batches, request)
    result = {'format': 'zipon-bulk-import-result-v1', 'generated_at': now(), 'mode': 'APPLY',
              'db_write': True, 'target_project_ref': PROJECT_REF, 'planned': plan['totals'],
              'counts': applied['counts'], 'results': applied['results'],
              'skipped': applied['skipped'], 'failures': applied['failures'],
              'reconciliation': reconcile(request, plan, applied)}
    files.append(write(RESULT_FILE, result))
    print('MODE              APPLY')
    for key, value in result['counts'].items():
        print(f'{key.upper():18}{value}')
    print('RECONCILIATION    ' + result['reconciliation']['result'])
    for entry in result['reconciliation']['checks']:
        if entry['result'] == 'FAIL':
            print('  FAIL ' + entry['check'], entry['detail'])
    print('FILES             ' + ', '.join(files))
    return 0 if result['reconciliation']['result'] == 'PASS' and not applied['failures'] else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('BULK IMPORT FAILED')
        print('TYPE:', type(exc).__name__)
        print('REASON:', getattr(exc, 'safe_reason', 'DETAILS_SUPPRESSED'))
        sys.exit(1)
