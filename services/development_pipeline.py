"""Incremental official-data pipeline for ZIP:ON development projects.

COLLECT -> SNAPSHOT -> CONTENT HASH -> CHANGE DETECTION -> VALIDATE ->
CANONICAL UPDATE -> DEVELOPMENT_UPDATES.

Rules this module exists to enforce:
  * a listing whose snapshot hash is unchanged costs nothing: no detail read and
    no write is planned for its rows
  * an unreviewed candidate never overwrites an existing value, never touches a
    VERIFIED row, and never downgrades status or validation_status
  * a stage that runs backwards, an ambiguous identity or a name that overlaps a
    program listing is quarantined for review instead of applied
  * a project missing from a listing produces a SOURCE_MISSING record only; no
    delete and no business-status transition
  * the write path is planned first and can be inspected without a database
"""
import copy
import hashlib
import json
import uuid

from services.development_collector import MAX_IMPORT_BATCH
from services.development_identity import record_overlap
from services.development_official import normalize_stage, now

# Ordered official progress. Unordered terms (dissolution, liquidation, cancelled,
# unknown) deliberately have no rank: they can legitimately follow any stage.
STAGE_ORDER = {'CANDIDATE': 10, 'SAFETY_DIAGNOSIS': 15, 'PLANNING': 20, 'PLAN_DELIBERATION': 25,
               'PLAN_NOTICED': 30, 'DESIGNATED': 35, 'IMPLEMENTER_DESIGNATED': 38, 'COMMITTEE': 40,
               'ASSOCIATION_APPROVED': 50, 'IMPLEMENTATION_APPROVED': 60,
               'MANAGEMENT_DISPOSITION': 70, 'SALES': 75, 'DEMOLITION': 80, 'CONSTRUCTION': 85,
               'PARTIAL_COMPLETION': 90, 'COMPLETED': 95, 'TRANSFER_NOTICE': 97}
# Pipeline kinds and the update_kind the existing schema CHECK accepts.
KIND_TO_UPDATE_KIND = {'INITIAL': 'INITIAL', 'STAGE_CHANGE': 'STAGE', 'STATUS_CHANGE': 'STATUS',
                       'DATA_CHANGE': 'DETAIL', 'SOURCE_MISSING': 'SOURCE_MISSING',
                       'REVERIFICATION': 'REVERIFICATION'}
DIFF_FIELDS = ('project_name', 'dong', 'address', 'stage_raw', 'sido', 'area_m2', 'planned_units')
IDENTITY_FIELDS = ('project_type', 'sigungu', 'official_authority', 'external_id')
DETAIL_WORTHY = ('INITIAL', 'STAGE_CHANGE', 'STATUS_CHANGE', 'DATA_CHANGE')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def listing_digests(records):
    """One snapshot hash per official listing, from the stored row evidence."""
    grouped = {}
    for record in records:
        url = (record.get('source') or {}).get('source_url')
        grouped.setdefault(url, []).append(record['source']['content_hash'])
    return {url: digest(sorted(hashes)) for url, hashes in grouped.items()}


def detect_change(previous, candidate):
    """Compare a collected candidate with the known master row."""
    if previous is None:
        return {'kind': 'INITIAL', 'changed_fields': ['candidate_evidence'],
                'previous_stage': None, 'new_stage': candidate.get('stage_raw'),
                'previous_status': None, 'new_status': candidate.get('status'),
                'previous_revision': 0}
    changed = sorted(field for field in DIFF_FIELDS
                     if candidate.get(field) not in (None, '')
                     and str(previous.get(field)) != str(candidate.get(field)))
    status_changed = (candidate.get('status') or 'UNKNOWN') != (previous.get('status') or 'UNKNOWN')
    kind = ('STAGE_CHANGE' if 'stage_raw' in changed else
            'STATUS_CHANGE' if status_changed else
            'DATA_CHANGE' if changed else 'REVERIFICATION')
    return {'kind': kind, 'changed_fields': changed,
            'previous_stage': previous.get('stage_raw'), 'new_stage': candidate.get('stage_raw'),
            'previous_status': previous.get('status') or 'UNKNOWN',
            'new_status': candidate.get('status') or 'UNKNOWN',
            'previous_revision': previous.get('revision', 0)}


def stage_regression(previous_stage, new_stage):
    before = STAGE_ORDER.get(normalize_stage(previous_stage)['normalized_stage'])
    after = STAGE_ORDER.get(normalize_stage(new_stage)['normalized_stage'])
    if before is None or after is None:
        return None
    return {'from': previous_stage, 'to': new_stage, 'from_rank': before, 'to_rank': after} \
        if after < before else None


def review_decision(previous, candidate, change, *, identities=()):
    """Why this candidate must not reach the master row unreviewed."""
    reasons, evidence = [], {}
    overlap = record_overlap(candidate, identities)
    if overlap:
        reasons.append('LATENT_PROGRAM_IDENTITY_OVERLAP')
        evidence['overlaps'] = overlap
    if not candidate.get('external_id'):
        reasons.append('NO_OFFICIAL_IDENTIFIER')
    if previous is not None:
        conflicting = [f for f in IDENTITY_FIELDS
                       if previous.get(f) is not None and candidate.get(f) is not None
                       and previous[f] != candidate[f]]
        if conflicting:
            reasons.append('OFFICIAL_IDENTITY_CONFLICT')
            evidence['identity_fields'] = conflicting
        regression = stage_regression(change['previous_stage'], change['new_stage'])
        if regression:
            reasons.append('STAGE_REGRESSION')
            evidence['stage_regression'] = regression
        if normalize_stage(candidate.get('stage_raw'))['normalized_stage'] == 'UNKNOWN' \
                and candidate.get('stage_raw'):
            reasons.append('UNMAPPED_OFFICIAL_STAGE')
    return {'review_required': bool(reasons), 'review_reasons': reasons, 'evidence': evidence,
            # A new candidate with an unsettled identity must not be inserted at all.
            'quarantine': bool(reasons) and previous is None}


def canonical_update(previous, candidate, decision):
    """Which master columns may be touched. Blanks only, never a VERIFIED row."""
    if previous is None:
        return {'action': 'INSERT_CANDIDATE', 'fill_fields': [], 'protected': []}
    if decision['review_required']:
        return {'action': 'HISTORY_ONLY', 'fill_fields': [],
                'protected': ['REVIEW_REQUIRED_' + r for r in decision['review_reasons']]}
    if previous.get('validation_status') == 'VERIFIED':
        return {'action': 'HISTORY_ONLY', 'fill_fields': [], 'protected': ['VERIFIED_MASTER']}
    fill = sorted(field for field in ('dong', 'address', 'area_m2', 'planned_units')
                  if previous.get(field) in (None, '') and candidate.get(field) not in (None, ''))
    occupied = sorted(field for field in DIFF_FIELDS
                      if previous.get(field) not in (None, '')
                      and candidate.get(field) not in (None, '')
                      and str(previous[field]) != str(candidate[field]))
    return {'action': 'FILL_BLANKS' if fill else 'HISTORY_ONLY', 'fill_fields': fill,
            'protected': ['EXISTING_VALUE_' + f for f in occupied]}


def plan(records, known, *, previous_digests=None, identities=(), detail_budget=None):
    """Decide what the run would do. No request is issued here.

    Rows from a listing whose snapshot hash is unchanged are settled without any
    detail read, which is what keeps a refresh cheap.
    """
    previous_digests = previous_digests or {}
    digests = listing_digests(records)
    unchanged_sources = sorted(url for url, value in digests.items()
                               if previous_digests.get(url) == value)
    entries, seen = [], set()
    for record in sorted(records, key=lambda r: r['project_id']):
        seen.add(record['project_id'])
        previous = known.get(record['project_id'])
        source_url = (record.get('source') or {}).get('source_url')
        if source_url in unchanged_sources and previous is not None:
            entries.append({'project_id': record['project_id'], 'kind': 'UNCHANGED',
                            'reason': 'LISTING_SNAPSHOT_HASH_UNCHANGED', 'detail_required': False,
                            'changed_fields': [], 'review_required': False, 'quarantine': False,
                            'canonical_action': 'NONE'})
            continue
        change = detect_change(previous, record)
        if previous is not None and previous.get('content_hash') == record['source']['content_hash'] \
                and change['kind'] == 'REVERIFICATION':
            entries.append({'project_id': record['project_id'], 'kind': 'UNCHANGED',
                            'reason': 'CONTENT_HASH_UNCHANGED', 'detail_required': False,
                            'changed_fields': [], 'review_required': False, 'quarantine': False,
                            'canonical_action': 'NONE'})
            continue
        decision = review_decision(previous, record, change, identities=identities)
        canonical = canonical_update(previous, record, decision)
        entries.append({'project_id': record['project_id'], 'kind': change['kind'],
                        'update_kind': KIND_TO_UPDATE_KIND[change['kind']],
                        'reason': 'CONTENT_CHANGED' if previous else 'NOT_IN_DATABASE',
                        'detail_required': change['kind'] in DETAIL_WORTHY,
                        'changed_fields': change['changed_fields'],
                        'previous_stage': change['previous_stage'], 'new_stage': change['new_stage'],
                        'previous_status': change['previous_status'], 'new_status': change['new_status'],
                        'expected_revision': change['previous_revision'],
                        'review_required': decision['review_required'],
                        'review_reasons': decision['review_reasons'],
                        'review_evidence': decision['evidence'],
                        'quarantine': decision['quarantine'],
                        'canonical_action': canonical['action'],
                        'fill_fields': canonical['fill_fields'], 'protected': canonical['protected']})
    missing = [{'project_id': pid, 'kind': 'SOURCE_MISSING', 'update_kind': 'SOURCE_MISSING',
                'reason': 'ABSENT_FROM_OFFICIAL_LISTING', 'detail_required': False,
                'changed_fields': ['source_presence'], 'review_required': False,
                'quarantine': False, 'canonical_action': 'HISTORY_ONLY',
                'review_reasons': [], 'review_evidence': {}, 'fill_fields': [],
                'protected': ['STATUS_AND_STAGE_UNCHANGED'],
                'previous_stage': known[pid].get('stage_raw'), 'new_stage': known[pid].get('stage_raw'),
                'previous_status': known[pid].get('status'), 'new_status': known[pid].get('status'),
                'expected_revision': known[pid].get('revision', 0),
                'note': 'absence is not a cancellation; status and stage stay as they are'}
               for pid in sorted(known) if pid not in seen]
    detail = [e['project_id'] for e in entries if e['detail_required']]
    if detail_budget is not None:
        detail = detail[:detail_budget]
    return {'generated_at': now(), 'digests': digests, 'unchanged_sources': unchanged_sources,
            'entries': entries + missing,
            'counts': {kind: sum(1 for e in entries + missing if e['kind'] == kind)
                       for kind in sorted({e['kind'] for e in entries + missing})},
            'detail_verification_targets': detail,
            'detail_verification_skipped': len(entries) - len([e for e in entries if e['detail_required']]),
            'quarantined': [e['project_id'] for e in entries if e['quarantine']],
            'review_required': [e['project_id'] for e in entries if e['review_required']],
            'writes_planned': sum(1 for e in entries + missing
                                  if not e['quarantine'] and e['kind'] != 'UNCHANGED')}


ALLOWED_CALLS = {('POST', 'development_collection_runs'), ('PATCH', 'development_collection_runs'),
                 ('POST', 'rpc/zipon_ingest_candidate_v2'), ('POST', 'rpc/zipon_record_source_missing')}


def build_calls(plan_result, records, *, run_id=None, source_name='ZIP:ON incremental refresh'):
    """The exact REST calls a run would make, in order. Nothing destructive can
    appear here: the allowlist has no DELETE and no write to development_projects."""
    by_id = {r['project_id']: r for r in records}
    run_id = run_id or str(uuid.uuid4())
    calls = [{'method': 'POST', 'table': 'development_collection_runs',
              'payload': {'run_id': run_id, 'source_name': source_name,
                          'source_type': 'OFFICIAL_WEBSITE', 'collector_version': 'seoul-tables-v1',
                          'dry_run': False, 'source_complete': False}}]
    for entry in plan_result['entries']:
        if entry['kind'] == 'UNCHANGED' or entry['quarantine']:
            continue
        if entry['kind'] == 'SOURCE_MISSING':
            calls.append({'method': 'POST', 'table': 'rpc/zipon_record_source_missing',
                          'payload': {'p_project_id': entry['project_id'],
                                      'p_reason': entry['reason'], 'p_run_id': run_id}})
            continue
        record = by_id[entry['project_id']]
        project = {k: v for k, v in record.items() if k not in ('source', 'revision') and v is not None}
        calls.append({'method': 'POST', 'table': 'rpc/zipon_ingest_candidate_v2',
                      'payload': {'p_project': project, 'p_source': record['source'],
                                  'p_expected_revision': entry['expected_revision'],
                                  'p_change': {'kind': entry['kind'],
                                               'changed_fields': entry['changed_fields'],
                                               'review_required': entry['review_required'],
                                               'review_reasons': entry['review_reasons']},
                                  'p_run_id': run_id}})
    calls.append({'method': 'PATCH', 'table': 'development_collection_runs',
                  'params': {'run_id': 'eq.' + run_id}, 'payload': {'finished_at': None}})
    for call in calls:
        if (call['method'], call['table']) not in ALLOWED_CALLS:
            raise ValueError('FORBIDDEN_CALL_' + call['method'] + '_' + call['table'])
    return {'run_id': run_id, 'calls': calls}


def run(plan_result, records, *, transport=None, dry_run=True, max_writes=MAX_IMPORT_BATCH,
        run_id=None):
    """Execute the planned calls. dry_run keeps everything local."""
    built = build_calls(plan_result, records, run_id=run_id)
    writes = [c for c in built['calls'] if c['table'].startswith('rpc/')]
    if len(writes) > max_writes:
        raise ValueError(f'REFRESH_WRITE_LIMIT_{max_writes}_EXCEEDED_{len(writes)}')
    summary = {'run_id': built['run_id'], 'dry_run': dry_run, 'planned_writes': len(writes),
               'quarantined': plan_result['quarantined'],
               'calls': [{k: v for k, v in c.items() if k != 'payload'} for c in built['calls']]}
    if dry_run or transport is None:
        summary['db_write'] = False
        return summary
    results, errors = [], []
    counts = {'new': 0, 'changed': 0, 'unchanged': 0, 'review_required': 0,
              'source_missing_recorded': 0}
    for call in built['calls']:
        try:
            response = transport(call['method'], call['table'], payload=call.get('payload'),
                                 **({'params': call['params']} if 'params' in call else {}))
        except Exception as exc:
            errors.append({'table': call['table'], 'error_type': type(exc).__name__,
                           'reason': getattr(exc, 'safe_reason', 'DETAILS_SUPPRESSED')})
            continue
        if call['table'].startswith('rpc/') and isinstance(response, dict):
            counts[response.get('result', 'unchanged')] = counts.get(response.get('result'), 0) + 1
            results.append(response)
    summary.update(db_write=True, counts=counts, errors=errors, rpc_results=results)
    return summary


def quarantine_report(plan_result, records):
    by_id = {r['project_id']: r for r in records}
    return {'generated_at': now(), 'db_write': False,
            'policy': 'quarantined candidates are never inserted; they wait for the official detail read',
            'items': [{'project_id': e['project_id'],
                       'project_name': by_id[e['project_id']]['project_name'],
                       'district': by_id[e['project_id']].get('sigungu'),
                       'external_id': by_id[e['project_id']].get('external_id'),
                       'reasons': e['review_reasons'], 'evidence': e['review_evidence']}
                      for e in plan_result['entries'] if e['quarantine']]}


def known_state(project_rows):
    """Baseline shape the pipeline needs from development_projects."""
    return {row['project_id']: {field: row.get(field) for field in
                                ('revision', 'validation_status', 'status', 'stage_raw', 'project_name',
                                 'dong', 'address', 'sido', 'sigungu', 'project_type',
                                 'official_authority', 'external_id', 'area_m2', 'planned_units',
                                 'content_hash')}
            for row in copy.deepcopy(project_rows)}
