"""Verify the first reviewed batch: database relations, then the ZIP:ON API.

Read-only. Every database call is a GET and the spatial invariants are asserted,
not assumed. --offline runs the parts that need no database (API contract,
transaction context, spatial safety) against stubs.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
BATCH_FILE = DATA / 'import_batch_01_20260927.json'
REPORT_FILE = DATA / 'import_batch_01_verification_20260927.json'
NEW_PROJECT_URL = 'https://nnxtkvjpzqqhjlgnprzo.supabase.co'


def checker():
    checks = []

    def check(name, ok, detail=None):
        checks.append({'check': name, 'result': 'PASS' if ok else 'FAIL', 'detail': detail})
        return ok
    return checks, check


def spatial_safety(rows):
    """A project with no verified boundary can never be reported as INSIDE."""
    checks, check = checker()
    inside = [r for r in rows if r.get('relation') == 'INSIDE' or r.get('spatial_relation') == 'INSIDE']
    unverified_inside = [r for r in inside if not r.get('evidence_verified')]
    check('no_inside_without_verified_boundary', not unverified_inside, unverified_inside)
    check('relation_values_are_known',
          all((r.get('relation') or r.get('spatial_relation')) in ('INSIDE', 'NEARBY', 'UNKNOWN', None)
              for r in rows))
    return checks


def offline_contract():
    """The API surface and the trade join, with the database stubbed out."""
    from unittest.mock import patch
    from services import development as dev, realestate_monitor as rm
    checks, check = checker()
    batch = json.loads(BATCH_FILE.read_text(encoding='utf-8'))['records']
    # What the RPC returns for these rows: no coordinates, no boundary -> UNKNOWN.
    stub = [{'project_id': r['project_id'], 'project_name': r['project_name'],
             'project_type': r['project_type'], 'stage': r['stage_raw'],
             'status': r['status'], 'validation_status': r['validation_status'],
             'spatial_relation': 'UNKNOWN', 'meters': None,
             'source_name': r['source']['source_name'], 'evidence_url': r['source']['source_url'],
             'evidence_verified': False} for r in batch]
    with patch.object(rm, '_using_remote_db', return_value=True), \
         patch.object(rm, '_remote_request', return_value=stub) as request:
        result = dev.search_projects(sigungu='강동구', limit=100)
    check('api_status_ok', result['status'] == 'ok', result['status'])
    rpc_call = request.call_args_list[0]
    check('api_calls_the_spatial_rpc', rpc_call.args == ('POST', 'rpc/zipon_development_search'))
    check('api_sends_no_coordinates_for_a_district_query',
          rpc_call.kwargs['payload']['p_longitude'] is None)
    check('stage_metadata_is_read_only', all(call.args == ('GET', 'development_projects')
          for call in request.call_args_list[1:]))
    rows = result['nearby_projects']
    check('api_returns_the_batch', len(rows) == len(batch), len(rows))
    for field in ('project_name', 'project_type', 'stage', 'status', 'validation_status',
                  'source_name', 'evidence_url'):
        check('api_exposes_' + field, all(r.get(field) is not None for r in rows))
    check('api_never_reports_verified_validation_status',
          all(r['validation_status'] != 'VERIFIED' for r in rows))
    check('api_relation_unknown_without_coordinates',
          all(r['spatial_relation'] == 'UNKNOWN' for r in rows))
    checks += spatial_safety(rows)
    # Trade rows have no coordinates today: the join must say so instead of guessing.
    with patch.object(dev, 'search_projects') as search:
        joined = dev.attach_context([{'name': 'trade', 'region': '천호동'}])
        no_lookup = not search.called
    context = joined[0]['development_context']
    check('trade_without_coordinates_does_not_query', no_lookup)
    check('trade_relation_unknown', context['relation'] == 'UNKNOWN', context['relation'])
    check('trade_status_needs_geocode', context['status'] == 'needs_geocode', context['status'])
    check('trade_reason_requires_exact_address',
          context['reason'] == 'EXACT_ADDRESS_COORDINATES_REQUIRED')
    check('trade_join_has_no_projects_attached', context['nearby_projects'] == [])
    return checks


def database_verification(url, headers):
    """Read back the ten rows and their source/history relations. GET only."""
    import requests
    checks, check = checker()
    batch = json.loads(BATCH_FILE.read_text(encoding='utf-8'))['records']
    ids = [r['project_id'] for r in batch]

    def get(table, params):
        response = requests.get(f'{url}/rest/v1/{table}', params=params, headers=headers,
                                timeout=30, allow_redirects=False)
        if not 200 <= response.status_code < 300:
            raise RuntimeError('HTTP_STATUS_' + str(response.status_code))
        return response.json()

    filter_ids = 'in.(' + ','.join(ids) + ')'
    projects = get('development_projects', {'project_id': filter_ids, 'select': '*'})
    sources = get('development_project_sources',
                  {'project_id': filter_ids, 'select': 'project_id,is_official,source_url,content_hash,validation_status'})
    updates = get('development_updates',
                  {'project_id': filter_ids, 'select': 'project_id,update_kind,from_revision,to_revision'})
    total = get('development_projects', {'select': 'project_id'})
    by_id = {p['project_id']: p for p in projects}
    check('all_ten_rows_present', len(by_id) == len(ids), sorted(set(ids) - set(by_id)))
    check('no_row_marked_verified', all(p['validation_status'] != 'VERIFIED' for p in projects))
    check('status_stays_unknown', all(p['status'] == 'UNKNOWN' for p in projects))
    check('stage_not_promoted', all(p.get('stage') in (None, '') for p in projects))
    check('stage_raw_kept', all(p.get('stage_raw') for p in projects))
    check('address_kept', all(p.get('address') for p in projects))
    check('every_project_has_an_official_source',
          all(any(s['project_id'] == pid and s['is_official'] for s in sources) for pid in by_id))
    check('every_source_has_a_content_hash', all(s['content_hash'] for s in sources))
    check('sources_stay_unverified', all(s['validation_status'] != 'VERIFIED' for s in sources))
    check('every_project_has_a_history_row',
          all(any(u['project_id'] == pid for u in updates) for pid in by_id))
    check('history_matches_revision',
          all(max((u['to_revision'] for u in updates if u['project_id'] == pid), default=None)
              == by_id[pid]['revision'] for pid in by_id))
    return checks, {'projects_read': len(projects), 'sources_read': len(sources),
                    'updates_read': len(updates), 'development_projects_total': len(total)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--offline', action='store_true', help='stubbed API/join checks only')
    args = ap.parse_args()
    report = {'format': 'zipon-first-batch-verification-v1', 'db_write': False,
              'batch_file': str(BATCH_FILE.relative_to(ROOT))}
    report['api_and_join'] = offline_contract()
    url = os.environ.get('ZIPON_IMPORT_SUPABASE_URL', '').strip().rstrip('/')
    key = os.environ.get('ZIPON_IMPORT_SUPABASE_KEY', '').strip()
    if args.offline or not (url and key):
        report['database'] = {'status': 'SKIPPED',
                              'reason': 'OFFLINE_REQUESTED' if args.offline
                                        else 'ZIPON_IMPORT_ENV_NOT_SET'}
    elif url != NEW_PROJECT_URL:
        report['database'] = {'status': 'REFUSED', 'reason': 'NEW_PROJECT_URL_MISMATCH'}
    else:
        from services.supabase_auth import supabase_headers
        try:
            checks, counts = database_verification(url, supabase_headers(key))
            report['database'] = {'status': 'CHECKED', 'checks': checks, 'counts': counts}
        except Exception as exc:
            report['database'] = {'status': 'ERROR', 'error_type': type(exc).__name__}
    sections = [report['api_and_join']] + ([report['database']['checks']]
                                           if report['database'].get('checks') else [])
    failures = [c for section in sections for c in section if c['result'] == 'FAIL']
    report['result'] = 'FAIL' if failures else 'PASS'
    report['failures'] = failures
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result': report['result'], 'api_and_join_checks': len(report['api_and_join']),
                      'database': report['database']['status'],
                      'failures': [f['check'] for f in failures]}, ensure_ascii=False, indent=2))
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
