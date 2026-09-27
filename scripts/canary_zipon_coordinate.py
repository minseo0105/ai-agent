"""Exactly one reviewed coordinate RPC, expected revision 1. Never retries."""
import json
import sys
from pathlib import Path
import apply_zipon_verified_coordinates as guard
from reconcile_zipon_coordinate import TARGET
from zipon_coordinate_diagnostics import safe_error

REPORT = guard.DATA/'coordinate_first_canary_result.json'
ALLOWED = {'location','location_source','location_verified_at','revision','updated_at','field_evidence'}


def run(candidate, request, persist):
    report = {'project_id':TARGET,'write_attempted':False,'db_write':False,'result':'BLOCKED'}
    if candidate.get('project_id') != TARGET:
        report['reason']='WRONG_TARGET'; return report
    def read():
        rows=request('GET','development_projects',params={'select':'*','project_id':'eq.'+TARGET,'limit':2})
        if not isinstance(rows,list) or len(rows)!=1 or rows[0].get('project_id')!=TARGET:
            raise ValueError('PROJECT_LOOKUP_NOT_UNIQUE')
        return rows[0]
    try:
        before=read()
        reasons=guard.existing.preflight(candidate,before)
        if before.get('revision')!=1:reasons.append('EXPECTED_REVISION_MUST_BE_1')
        if guard.normalize_address(before.get('address'))!=guard.normalize_address(candidate['canonical_address']):
            reasons.append('ADDRESS_MISMATCH')
        if reasons:
            report['reasons']=reasons; return report
        payload=guard.existing.payload_for(candidate,before)
        payload['p_expected_revision']=1
    except Exception as exc:
        report.update(stage='PREFLIGHT',error=safe_error(exc)); return report
    report.update(write_attempted=True,db_write='UNKNOWN',stage='RPC',before=before)
    persist(report)  # Must succeed before issuing the only POST.
    try:
        answer=request('POST',guard.existing.RPC,payload=payload)
        if isinstance(answer,list):answer=answer[0] if len(answer)==1 else None
        if not isinstance(answer,dict):raise ValueError('INVALID_RPC_RESPONSE')
        report['rpc_result']=answer.get('result') if answer.get('result') in ('location_set','refused','skipped') else 'UNKNOWN'
        reason=answer.get('reason')
        allowed_reasons={'REVISION_CONFLICT','LOCATION_ALREADY_SET','VERIFIED_BOUNDARY_PRESENT','PROJECT_NOT_FOUND',
                         'DISTRICT_MISMATCH','ACCEPTED_EVIDENCE_REQUIRED','GEOCODE_CHECKS_NOT_PASSED',
                         'COORDINATE_OUTSIDE_SEOUL','NO_GEOCODE_EVIDENCE','UNKNOWN_GEOCODE_SOURCE','CONFIDENCE_NOT_EXACT'}
        report['rpc_reason']=reason if reason in allowed_reasons else None
    except Exception as exc:
        report['error']=safe_error(exc)
    # Even an HTTP error/timeout may have committed. Re-read once, never resend.
    try:
        after=read()
        lon,lat=guard._point(after.get('location'))
        protected={k:v for k,v in before.items() if k not in ALLOWED} == {k:v for k,v in after.items() if k not in ALLOWED}
        old_evidence=before.get('field_evidence') or {}
        new_evidence=after.get('field_evidence') or {}
        protected &= {k:v for k,v in old_evidence.items() if k!='location'} == {k:v for k,v in new_evidence.items() if k!='location'}
        point_matches=lon is not None and abs(lon-candidate['longitude'])<1e-8 and abs(lat-candidate['latitude'])<1e-8
        report.update(after=after,location_present=after.get('location') is not None,
                      revision_after=after.get('revision'),protected_fields_unchanged=protected,
                      coordinate_matches=point_matches,db_write=after!=before,
                      geometry_verified_unchanged=after.get('geometry_verified')==before.get('geometry_verified'))
        success=(report.get('rpc_result')=='location_set' and not report.get('error') and point_matches
                 and after.get('revision')==2 and protected
                 and after.get('location_source')==payload['p_geocode_source']
                 and bool(after.get('location_verified_at')))
        report['result']='SUCCESS' if success else 'STOPPED_RECONCILIATION_REQUIRED'
    except Exception as exc:
        report.update(result='STOPPED_RECONCILIATION_REQUIRED',reconciliation_error=safe_error(exc))
    persist(report)
    return report


def main():
    if REPORT.exists() and json.loads(REPORT.read_text(encoding='utf-8')).get('write_attempted'):
        print('STOPPED: CANARY_ALREADY_ATTEMPTED; read-only reconciliation required');return 2
    rows=guard.validate_queue(
        json.loads((guard.DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8')),
        json.loads((guard.DATA/'bulk_geocode_result_20260927.json').read_text(encoding='utf-8')))
    candidate=next(r for r in rows if r['project_id']==TARGET)
    url,headers=guard.existing.configuration()
    import requests
    def request(method,table,params=None,payload=None):
        if method=='POST' and (table!=guard.existing.RPC or payload.get('p_project_id')!=TARGET or payload.get('p_expected_revision')!=1):
            raise ValueError('WRITE_SCOPE_VIOLATION')
        response=requests.request(method,url+'/rest/v1/'+table,headers=headers,params=params,json=payload,
                                  timeout=30,allow_redirects=False)
        response.raise_for_status();return response.json()
    def persist(report):
        temporary=REPORT.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        temporary.replace(REPORT)
    report=run(candidate,request,persist)
    persist(report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('before','after')},ensure_ascii=False))
    print(report['result'])
    return 0 if report['result']=='SUCCESS' else 2


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'result':'STOPPED','error':safe_error(exc)}));sys.exit(2)
