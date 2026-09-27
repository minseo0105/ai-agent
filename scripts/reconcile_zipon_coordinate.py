"""Read-only inspection of the interrupted first coordinate request. Never invokes RPC."""
import json
import sys
from pathlib import Path
from hashlib import sha256
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apply_zipon_verified_coordinates as guard
from zipon_coordinate_diagnostics import safe_error

TARGET = '0922ac26-1436-5158-853d-49d3c5aed7fb'
OUTPUT = guard.DATA / 'coordinate_first_readonly_reconciliation.json'


def inspect(request, candidate, journal):
    """The injectable request receives GET only, including the OpenAPI document."""
    result = {'project_id': TARGET, 'db_write': False, 'rpc_invoked': False}
    previous = next((r for r in journal.get('before', []) if r['project_id'] == TARGET), None)
    historical = next((r for r in journal.get('after', []) if r['project_id'] == TARGET), None)
    result['journal_post_failure'] = {
        'location_present': historical.get('location') is not None if historical else None,
        'revision': historical.get('revision') if historical else None,
        'selected_fields_unchanged': historical == previous if historical and previous else None}
    try:
        rows = request('GET', 'development_projects', params={
            'select': 'project_id,address,sigungu,revision,location,geometry,geometry_verified,location_source,location_verified_at',
            'project_id': 'eq.' + TARGET, 'limit': 2})
        if not isinstance(rows, list) or len(rows) != 1 or rows[0].get('project_id') != TARGET:
            result.update(preflight='BLOCKED', reason='PROJECT_LOOKUP_NOT_UNIQUE')
            return result
        row = rows[0]
        reasons = guard.existing.preflight(candidate, row)
        if guard.normalize_address(row.get('address')) != guard.normalize_address(candidate['canonical_address']):
            reasons.append('ADDRESS_MISMATCH')
        if previous and row['revision'] != previous['revision']:
            reasons.append('REVISION_CHANGED_SINCE_JOURNAL')
        result['live_project'] = {'location_present': row['location'] is not None,
            'revision': row['revision'], 'geometry_verified': row['geometry_verified'],
            'same_location_as_before': row['location'] == previous.get('location') if previous else None,
            'same_geometry_as_before': row['geometry'] == previous.get('geometry') if previous else None}
        result['preflight'] = 'BLOCKED' if reasons else 'PASS'
        result['preflight_reasons'] = reasons
        payload = guard.existing.payload_for(candidate, row)
    except Exception as exc:
        result.update(preflight='UNAVAILABLE', project_read_error=safe_error(exc))
        return result
    try:
        schema = request('GET', '', headers={'Accept': 'application/openapi+json'})
        operation = schema.get('paths', {}).get('/rpc/zipon_set_project_location', {}).get('post')
        if operation is None:
            result['rpc_schema'] = 'NOT_ADVERTISED_TO_THIS_ROLE'
            result['diagnosis'] = 'RPC_ABSENT_FROM_EXPOSED_SCHEMA_OR_NOT_VISIBLE; original HTTP cause not recoverable'
        else:
            body = next((p.get('schema', {}) for p in operation.get('parameters', []) if p.get('in') == 'body'), {})
            if '$ref' in body and body['$ref'].startswith('#/definitions/'):
                body = schema.get('definitions', {}).get(body['$ref'].split('/')[-1], {})
            properties = body.get('properties', {})
            required = set(body.get('required', []))
            if not properties:
                result['rpc_schema'] = 'PRESENT_SIGNATURE_UNREADABLE'
            elif set(payload) - set(properties) or required - set(payload):
                result['rpc_schema'] = 'PAYLOAD_SIGNATURE_MISMATCH'
            else:
                expected = {'p_project_id':'string', 'p_longitude':'number', 'p_latitude':'number',
                    'p_expected_sigungu':'string', 'p_geocode_source':'string', 'p_confidence':'string',
                    'p_expected_revision':'integer', 'p_evidence':'object'}
                bad = [k for k,v in expected.items() if properties[k].get('type') not in (None, v)]
                result['rpc_schema'] = 'PAYLOAD_TYPE_MISMATCH' if bad else 'PARAMETERS_MATCH'
                result['type_mismatch_parameters'] = bad
    except Exception as exc:
        result.update(rpc_schema='UNAVAILABLE', schema_read_error=safe_error(exc))
    result['dry_run'] = 'PASS' if result['preflight']=='PASS' and result['rpc_schema']=='PARAMETERS_MATCH' else 'BLOCKED'
    result['write_retry_authorized'] = False
    return result


def main():
    raw = guard.REPORT.read_bytes()
    journal = json.loads(raw)
    if journal.get('pending_project_id') != TARGET:
        print('STOPPED: JOURNAL_TARGET_MISMATCH'); return 2
    queue = json.loads((guard.DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8'))
    bulk = json.loads((guard.DATA/'bulk_geocode_result_20260927.json').read_text(encoding='utf-8'))
    candidate = next(r for r in guard.validate_queue(queue, bulk) if r['project_id']==TARGET)
    try:
        url, headers = guard.existing.configuration()
    except guard.existing.ApplyBlocked as exc:
        print('USER ACTION REQUIRED: '+exc.reason); return 2
    import requests
    def request(method, table, params=None, headers=None):
        if method != 'GET': raise ValueError('READ_ONLY_ONLY')
        response = requests.get(url+'/rest/v1/'+table, params=params,
            headers=dict(auth_headers, **(headers or {})), timeout=30, allow_redirects=False)
        response.raise_for_status()
        return response.json()
    auth_headers = headers
    result = inspect(request, candidate, journal)
    result['journal_sha256'] = sha256(raw).hexdigest()
    result['journal_unchanged'] = guard.REPORT.read_bytes()==raw
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result.get('dry_run')=='PASS' else 2


if __name__=='__main__':sys.exit(main())
