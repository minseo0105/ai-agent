"""Official verification, duplicate adjudication and import planning (offline).

Nothing here writes to a database or calls the network. Every promoted value
carries the official URL, content hash and evidence it came from, raw source
observations are copied through untouched, and an identity is only merged on
strong official evidence.
"""
import copy
from collections import Counter, defaultdict
import json

from services.development_geocode import cache_key as geocode_key
from services.development_official import (REGISTRY_PROGRAM, SOURCE_PROGRAMS, compact,
                                           detail_target, dong_from_address, lot_number,
                                           normalize_stage, normalize_status, now)
from services.development_quality import TYPE_MAP, normalize_address, normalize_name, tokens

CANONICAL_VERSION = 'zipon-canonical-v2'


def program_of(record):
    source_url = (record.get('source') or {}).get('source_url') or ''
    return SOURCE_PROGRAMS.get(source_url.split('?')[0], REGISTRY_PROGRAM)


def official_category(record):
    """The 사업구분 cell of the official district list, as published."""
    cells = ((record.get('field_evidence') or {}).get('cells')) or []
    for cell in cells:
        if cell in ('재건축', '재개발', '주택재건축', '주택재개발'):
            return cell
    return None


def extract(record, detail=None):
    """Everything one official read can establish about a single candidate."""
    source = record.get('source') or {}
    detail = detail or {}
    fields = detail.get('parsed_fields') or {}
    verified_detail = detail.get('result_status') == 'FETCHED' and bool(fields)
    program = program_of(record)
    address = fields.get('representative_address') or record.get('address')
    address_from_detail = bool(fields.get('representative_address'))
    raw_stage = fields.get('raw_stage') or record.get('stage_raw')
    stage = normalize_stage(raw_stage)
    status = normalize_status(stage['normalized_stage'])
    evidence_cells = (record.get('field_evidence') or {}).get('cells') or []
    observed = [{'value': value, 'date_role': 'UNKNOWN_OFFICIAL_COLUMN',
                 'source_url': source.get('source_url')}
                for value in ((record.get('field_evidence') or {}).get('observed_dates') or [])]
    dates = {key: fields.get(key) for key in ('designation_date', 'approval_date', 'implementation_date',
                                              'management_disposition_date', 'completion_date')}
    return {
        'project_id': record['project_id'],
        'identity': {
            'official_project_name': fields.get('official_project_name') or record.get('project_name'),
            'official_project_name_source': ('OFFICIAL_DETAIL_PAGE' if fields.get('official_project_name')
                                             else 'OFFICIAL_LIST_ROW'),
            'official_external_id': record.get('external_id'),
            'source_system': record.get('official_authority') or program['program_name'],
            'identity_verified': verified_detail,
            'identity_confidence': ('HIGH' if verified_detail and record.get('external_id')
                                    else 'MEDIUM' if record.get('external_id') else 'LOW'),
            'identity_basis': ([b for b in (
                'OFFICIAL_DETAIL_PAGE' if verified_detail else None,
                'OFFICIAL_SYSTEM_EXTERNAL_ID' if record.get('external_id') else None,
                'OFFICIAL_LIST_ROW') if b]),
        },
        'location': {
            'district': record.get('sigungu'),
            'dong': dong_from_address(address, record.get('sigungu')),
            'dong_source': 'OFFICIAL_ADDRESS_TOKEN' if address else None,
            'dong_recorded_in_pilot': record.get('dong'),
            'road_address': fields.get('road_address'),
            'lot_address': address,
            'lot_number': lot_number(address),
            'representative_address': address,
            'address_type': 'LOT' if address else None,
            'address_source': ('OFFICIAL_DETAIL_PAGE' if address_from_detail
                               else '공식 사업장 목록 대표지번' if address else None),
            'address_source_url': source.get('source_url') if address else None,
            'address_verified': bool(address),
            'address_verified_at': source.get('collected_at') if address else None,
        },
        'classification': {
            'official_project_type': official_category(record),
            'canonical_project_type': (program['canonical_project_type']
                                       or TYPE_MAP.get(record.get('project_type'), 'OTHER')),
            'program': program['program'],
            'program_name': program['program_name'],
            'program_source_url': source.get('source_url'),
            'official_registry_row': program['registry'],
            'db_project_type': record.get('project_type'),
        },
        'progress': dict(stage, raw_stage=raw_stage,
                         stage_verified=stage['stage_confidence'] == 'OFFICIAL_TERM',
                         stage_basis=('OFFICIAL_DETAIL_PAGE' if fields.get('raw_stage')
                                      else 'OFFICIAL_LIST_CELL' if raw_stage else None),
                         stage_source_url=source.get('source_url') if raw_stage else None,
                         stage_verified_at=source.get('collected_at') if raw_stage else None,
                         stage_evidence={'cells': evidence_cells,
                                         'content_hash': source.get('content_hash')} if raw_stage else None),
        'status': dict(status, status_verified=status['status_confidence'] == 'OFFICIAL_TERMINAL_STAGE',
                       status_source_url=(source.get('source_url')
                                          if status['status_confidence'] == 'OFFICIAL_TERMINAL_STAGE' else None)),
        'dates': dict(dates, observed_dates=observed,
                      dates_from_official_detail=bool(any(dates.values()))),
        'measures': {'area_m2': record.get('area_m2'), 'planned_units': record.get('planned_units')},
        'provenance': {'source_name': source.get('source_name'), 'source_url': source.get('source_url'),
                       'is_official': source.get('is_official'), 'fetched_at': source.get('collected_at'),
                       'content_hash': source.get('content_hash'),
                       'evidence_fields': sorted(k for k, v in {
                           'project_name': record.get('project_name'), 'address': record.get('address'),
                           'stage_raw': record.get('stage_raw'), 'external_id': record.get('external_id'),
                           'area_m2': record.get('area_m2'), 'planned_units': record.get('planned_units')}.items() if v),
                       'detail': {'result_status': detail.get('result_status', 'NOT_ATTEMPTED'),
                                  'source_url': detail.get('source_url'),
                                  'fetched_at': detail.get('fetched_at'),
                                  'content_hash': detail.get('content_hash'),
                                  'cache_key': detail.get('cache_key')}},
    }


def adjudicate(pair, extracted, details=None):
    """Re-decide one probable-duplicate pair. SAME_PROJECT needs strong official
    evidence: a shared official identifier, or a detail page that shows one
    business. Name similarity alone never merges, and a program listing is not
    the same record as a business-registry entry until an official read says so."""
    details = details or {}
    left, right = (extracted[i] for i in pair['candidate_ids'])
    basis, evidence = [], []
    for side in (left, right):
        evidence.append({'project_id': side['project_id'],
                         'official_project_name': side['identity']['official_project_name'],
                         'official_external_id': side['identity']['official_external_id'],
                         'district': side['location']['district'], 'dong': side['location']['dong'],
                         'lot_address': side['location']['lot_address'],
                         'program': side['classification']['program'],
                         'official_registry_row': side['classification']['official_registry_row'],
                         'raw_stage': side['progress']['raw_stage'],
                         'source_url': side['provenance']['source_url'],
                         'content_hash': side['provenance']['content_hash'],
                         'detail_status': side['provenance']['detail']['result_status']})

    def decide(decision, confidence, reason, review):
        return {'candidate_ids': pair['candidate_ids'], 'canonical_ids': pair['canonical_ids'],
                'names': pair['names'], 'previous_reason': pair.get('reason'),
                'decision': decision, 'confidence': confidence, 'basis': basis + [reason],
                'official_evidence': evidence, 'review_required': review,
                'field_differences': pair.get('field_differences', []),
                'adjudicated_at': now()}

    ids = [side['identity']['official_external_id'] for side in (left, right)]
    systems = [side['identity']['source_system'] for side in (left, right)]
    if all(ids) and ids[0] == ids[1] and systems[0] == systems[1]:
        return decide('SAME_PROJECT', 'HIGH', 'OFFICIAL_EXTERNAL_ID_MATCH', False)
    verified = [details.get(side['provenance']['detail'].get('cache_key'), {}) for side in (left, right)]
    if all(v.get('result_status') == 'FETCHED' for v in verified):
        names = [compact((v.get('parsed_fields') or {}).get('official_project_name')) for v in verified]
        addresses = [normalize_address((v.get('parsed_fields') or {}).get('representative_address'))
                     for v in verified]
        if all(names) and names[0] == names[1] and all(addresses) and addresses[0] == addresses[1]:
            return decide('SAME_PROJECT', 'HIGH', 'OFFICIAL_DETAIL_SAME_NAME_AND_ADDRESS', False)
    if compact(left['location']['district']) != compact(right['location']['district']):
        return decide('DIFFERENT_PROJECT', 'HIGH', 'OFFICIAL_DISTRICT_MISMATCH', False)
    left_tokens, right_tokens = (tokens(side['identity']['official_project_name']) for side in (left, right))
    if left_tokens and right_tokens and left_tokens != right_tokens:
        return decide('DIFFERENT_PROJECT', 'HIGH', 'OFFICIAL_ZONE_OR_PHASE_MISMATCH', False)
    lots = [side['location']['lot_address'] for side in (left, right)]
    if all(lots) and normalize_address(lots[0]) != normalize_address(lots[1]):
        return decide('DIFFERENT_PROJECT', 'MEDIUM', 'OFFICIAL_REPRESENTATIVE_LOT_MISMATCH', True)
    registry = [side['classification']['official_registry_row'] for side in (left, right)]
    programs = [side['classification']['program'] for side in (left, right)]
    if registry[0] != registry[1] or programs[0] != programs[1]:
        basis.append('PROGRAM_LISTING_VS_BUSINESS_REGISTRY')
        return decide('STILL_AMBIGUOUS', 'LOW', 'OFFICIAL_DETAIL_READ_REQUIRED', True)
    if not all(ids):
        basis.append('ONE_SIDE_HAS_NO_OFFICIAL_IDENTIFIER')
    return decide('STILL_AMBIGUOUS', 'LOW', 'OFFICIAL_DETAIL_READ_REQUIRED', True)


def _union(pairs, ids):
    parent = {i: i for i in ids}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for pair in pairs:
        if pair['decision'] == 'SAME_PROJECT':
            a, b = (find(i) for i in pair['candidate_ids'])
            if a != b:
                parent[a] = b
    groups = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    return groups


def unique(values):
    indexed = {json.dumps(v, ensure_ascii=False, sort_keys=True): v
               for v in values if v not in (None, '', [], {})}
    return [indexed[k] for k in sorted(indexed)]


def quality_state(project):
    """VERIFIED requires an official identity read, not mere presence in a list."""
    reasons = []
    identity = project['identity']
    location = project['location']
    if project['duplicate']['unresolved']:
        reasons.append('UNRESOLVED_DUPLICATE_CANDIDATE')
    if not identity['official_external_id']:
        reasons.append('NO_OFFICIAL_IDENTIFIER')
    if not identity['identity_verified']:
        reasons.append('OFFICIAL_DETAIL_IDENTITY_NOT_READ')
    if not location['address_verified']:
        reasons.append('NO_OFFICIAL_ADDRESS')
    if not project['progress']['stage_verified']:
        reasons.append('STAGE_NOT_OFFICIALLY_MAPPED')
    if not project['status']['status_verified']:
        reasons.append('STATUS_NOT_OFFICIALLY_ESTABLISHED')
    if not project['provenance']['is_official']:
        reasons.append('NO_OFFICIAL_SOURCE')
    blocking = {'UNRESOLVED_DUPLICATE_CANDIDATE', 'NO_OFFICIAL_IDENTIFIER', 'NO_OFFICIAL_ADDRESS',
                'NO_OFFICIAL_SOURCE'}
    if not reasons:
        return 'VERIFIED', reasons
    if blocking & set(reasons):
        return 'NEEDS_REVIEW', reasons
    return 'PARTIALLY_VERIFIED', reasons


def build(records, canary, previous_canonical, pairs, details=None, geocodes=None):
    details = details or {}
    geocodes = geocodes or {}
    rows = sorted(copy.deepcopy(records), key=lambda r: r['project_id'])
    by_id = {r['project_id']: r for r in rows}
    extracted = {r['project_id']: extract(r, details.get(detail_target(r)['cache_key'])) for r in rows}
    for pid, bundle in extracted.items():
        bundle['provenance']['detail']['cache_key'] = detail_target(by_id[pid])['cache_key']
    resolved = [adjudicate(pair, extracted, details) for pair in pairs]
    previous = {p['canonical_id']: p for p in (previous_canonical or {}).get('projects', [])}
    previous_by_candidate = {cid: p for p in previous.values() for cid in p.get('candidate_ids', [])}
    unresolved_ids = {i for pair in resolved if pair['decision'] == 'STILL_AMBIGUOUS'
                      for i in pair['candidate_ids']}
    review_ids = {i for pair in resolved if pair['review_required'] for i in pair['candidate_ids']}
    canary_ids = {r['project_id'] for r in canary}

    projects = []
    for root, members in sorted(_union(resolved, [r['project_id'] for r in rows]).items(),
                                key=lambda item: sorted(item[1])):
        members = sorted(members)
        bundles = [extracted[i] for i in members]
        anchor = bundles[0]
        pairs_here = [p for p in resolved if set(p['candidate_ids']) & set(members)]
        merged_from = [p for p in pairs_here if p['decision'] == 'SAME_PROJECT']
        previous_ids = unique([previous_by_candidate.get(i, {}).get('canonical_id') for i in members])
        address = anchor['location']['representative_address']
        geo = (geocodes.get(geocode_key(address)) if address else None) or {}
        project = {
            'canonical_id': previous_ids[0] if len(previous_ids) == 1 else 'merged:' + '+'.join(previous_ids),
            'canonical_version': CANONICAL_VERSION,
            'previous_canonical_ids': previous_ids,
            'identity': dict(anchor['identity'],
                             official_external_ids=unique([b['identity']['official_external_id'] for b in bundles]),
                             original_names=unique([by_id[i].get('project_name') for i in members]),
                             normalized_name=normalize_name(anchor['identity']['official_project_name'])),
            'location': dict(anchor['location'],
                             original_addresses=unique([by_id[i].get('address') for i in members])),
            'classification': anchor['classification'],
            'programs': unique([b['classification']['program'] for b in bundles]),
            'progress': anchor['progress'],
            'observed_stages': unique([b['progress']['raw_stage'] for b in bundles]),
            'status': anchor['status'],
            'dates': anchor['dates'],
            'measures': anchor['measures'],
            'provenance': dict(anchor['provenance'],
                               sources=unique([by_id[i].get('source') for i in members]),
                               source_urls=unique([b['provenance']['source_url'] for b in bundles])),
            'geocoding': {'latitude': geo.get('latitude'), 'longitude': geo.get('longitude'),
                          'geocode_source': geo.get('geocode_source'),
                          'geocode_confidence': geo.get('geocode_confidence', 'UNRESOLVED'),
                          'geocoded_at': geo.get('geocoded_at'),
                          'address_used': geo.get('address_used') or anchor['location']['representative_address'],
                          'coordinate_verified': bool(geo.get('coordinate_verified')),
                          'reason': geo.get('reason')},
            'boundary': {'geometry': None, 'boundary_verified': False, 'boundary_source': None,
                         'boundary_policy': 'OFFICIAL_GIS_ONLY; no buffer, no inferred polygon'},
            'duplicate': {'class': ('MERGED_SAME_PROJECT' if len(members) > 1 else
                                    'AMBIGUOUS' if set(members) & unresolved_ids else
                                    'DISTINGUISHED' if set(members) & review_ids else 'UNIQUE'),
                          'unresolved': bool(set(members) & unresolved_ids),
                          'pairs': [{'candidate_ids': p['candidate_ids'], 'decision': p['decision'],
                                     'confidence': p['confidence']} for p in pairs_here],
                          'merged_evidence': [p['basis'] for p in merged_from]},
            'raw': {'candidate_ids': members, 'raw_candidate_count': len(members),
                    'raw_candidates': [by_id[i] for i in members],
                    'history': [{'canonical_version': 'zipon-canonical-v1',
                                 'canonical_id': previous_by_candidate.get(i, {}).get('canonical_id'),
                                 'candidate_id': i,
                                 'observed_stage': by_id[i].get('stage_raw'),
                                 'collected_at': (by_id[i].get('source') or {}).get('collected_at'),
                                 'content_hash': (by_id[i].get('source') or {}).get('content_hash')}
                                for i in members]},
            'detail_lookup': detail_target(by_id[members[0]])['detail_lookup'],
        }
        project['spatial_relation_capability'] = (
            'INSIDE_AND_NEARBY' if project['boundary']['boundary_verified']
            else 'NEARBY_ONLY' if project['geocoding']['coordinate_verified'] else 'UNKNOWN')
        state, reasons = quality_state(project)
        project['quality_state'] = state
        project['quality_reasons'] = reasons
        existing = sorted(canary_ids & set(members))
        project['import_plan'] = {
            'db_project_ids': members,
            'db_project_type': anchor['classification']['db_project_type'],
            'existing_canary': bool(existing),
            'existing_canary_ids': existing,
            'import_eligible': state in ('VERIFIED', 'PARTIALLY_VERIFIED') and not existing,
            'payload_source': 'data/development/pilot_20260927.json#records[project_id]',
            'source_policy': 'PRESERVE_ALL_SOURCE_OBSERVATIONS; canonical JSON is not an importer payload',
        }
        projects.append(project)
    projects.sort(key=lambda p: (p['location']['district'] or '', p['identity']['official_project_name'] or ''))
    return projects, resolved


def manifest(projects, *, batch_size=10, project_ref=None):
    eligible = [p for p in projects if p['import_plan']['import_eligible']]
    eligible.sort(key=lambda p: ({'VERIFIED': 0, 'PARTIALLY_VERIFIED': 1}[p['quality_state']],
                                 p['location']['district'] or '', p['canonical_id']))
    batches = []
    for index in range(0, len(eligible), batch_size):
        chunk = eligible[index:index + batch_size]
        batches.append({'batch_id': f'batch-{len(batches) + 1:02d}', 'size': len(chunk),
                        'requires_operator_approval': True,
                        'records': [{'project_id': p['import_plan']['db_project_ids'][0],
                                     'canonical_id': p['canonical_id'],
                                     'official_project_name': p['identity']['official_project_name'],
                                     'official_external_id': p['identity']['official_external_id'],
                                     'district': p['location']['district'], 'dong': p['location']['dong'],
                                     'representative_address': p['location']['representative_address'],
                                     'db_project_type': p['import_plan']['db_project_type'],
                                     'raw_stage': p['progress']['raw_stage'],
                                     'normalized_stage': p['progress']['normalized_stage'],
                                     'normalized_status': p['status']['normalized_status'],
                                     'quality_state': p['quality_state'],
                                     'source_url': p['provenance']['source_url'],
                                     'content_hash': p['provenance']['content_hash'],
                                     'existing_canary': False,
                                     'payload_source': p['import_plan']['payload_source']}
                                    for p in chunk]})
    excluded = {'needs_review': [p['canonical_id'] for p in projects if p['quality_state'] == 'NEEDS_REVIEW'],
                'existing_canary': [{'canonical_id': p['canonical_id'],
                                     'project_ids': p['import_plan']['existing_canary_ids'],
                                     'quality_state': p['quality_state'],
                                     'reconciliation': 'already imported in the canary run; never re-insert'}
                                    for p in projects if p['import_plan']['existing_canary']]}
    return {'generated_at': now(), 'format': 'zipon-import-manifest-v1',
            'target_project_ref': project_ref, 'db_write': False,
            'policy': ['no automatic import', 'operator approves every batch',
                       'NEEDS_REVIEW excluded', 'canary rows never re-inserted',
                       'importer builds payloads from the raw pilot record, not from canonical JSON'],
            'maximum_batch_size': batch_size,
            'totals': {'canonical_projects': len(projects), 'import_eligible': len(eligible),
                       'batches': len(batches), 'excluded_needs_review': len(excluded['needs_review']),
                       'excluded_existing_canary': len(excluded['existing_canary'])},
            'batches': batches, 'excluded': excluded}


def report(projects, resolved, *, inputs, detail_stats, geocode_stats, failures):
    def count(predicate):
        return sum(1 for p in projects if predicate(p))
    decisions = Counter(p['decision'] for p in resolved)
    return {
        'generated_at': now(), 'format': 'zipon-verification-report-v1', 'db_write': False,
        'inputs': inputs,
        'identity': {'same_project': decisions['SAME_PROJECT'],
                     'different_project': decisions['DIFFERENT_PROJECT'],
                     'still_ambiguous': decisions['STILL_AMBIGUOUS'],
                     'pairs_reviewed': len(resolved),
                     'canonical_projects_after_verified_merge': len(projects),
                     'merged_projects': count(lambda p: p['raw']['raw_candidate_count'] > 1)},
        'quality_state': dict(sorted(Counter(p['quality_state'] for p in projects).items())),
        'quality_reasons': dict(sorted(Counter(r for p in projects for r in p['quality_reasons']).items())),
        'stage': {'officially_mapped': count(lambda p: p['progress']['stage_verified']),
                  'unresolved': count(lambda p: not p['progress']['stage_verified']),
                  'distribution': dict(sorted(Counter(p['progress']['normalized_stage'] for p in projects).items()))},
        'status': {'verified': count(lambda p: p['status']['status_verified']),
                   'unknown': count(lambda p: p['status']['normalized_status'] == 'UNKNOWN'),
                   'distribution': dict(sorted(Counter(p['status']['normalized_status'] for p in projects).items())),
                   'hypotheses': dict(sorted(Counter(p['status']['status_hypothesis'] or 'NONE' for p in projects).items()))},
        'address': {'verified': count(lambda p: p['location']['address_verified']),
                    'unresolved': count(lambda p: not p['location']['address_verified']),
                    'road_address': count(lambda p: p['location']['road_address']),
                    'dong_resolved': count(lambda p: p['location']['dong']),
                    'dong_corrected_from_pilot': count(
                        lambda p: p['location']['dong'] and p['location']['dong'] != p['location']['dong_recorded_in_pilot'])},
        'geocoding': {'coordinates_obtained': count(lambda p: p['geocoding']['latitude'] is not None),
                      'coordinate_verified': count(lambda p: p['geocoding']['coordinate_verified']),
                      'geocode_review': count(lambda p: p['geocoding']['geocode_confidence'] == 'GEOCODE_REVIEW'),
                      'unresolved': count(lambda p: p['geocoding']['geocode_confidence'] == 'UNRESOLVED'),
                      'provider': geocode_stats},
        'boundary': {'verified_polygons': count(lambda p: p['boundary']['boundary_verified']),
                     'unresolved': count(lambda p: not p['boundary']['boundary_verified']),
                     'spatial_relation_capability': dict(sorted(Counter(
                         p['spatial_relation_capability'] for p in projects).items()))},
        'official_cache': detail_stats,
        'by_district': dict(sorted(Counter(p['location']['district'] for p in projects).items())),
        'by_canonical_type': dict(sorted(Counter(p['classification']['canonical_project_type'] for p in projects).items())),
        'by_program': dict(sorted(Counter(p['classification']['program'] or 'NONE' for p in projects).items())),
        'failures': failures,
    }
