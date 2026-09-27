"""GET-only reconciliation and resume plan. Does not authorize or execute writes."""
import json
import sys
from hashlib import sha256
import apply_zipon_verified_coordinates as guard
import canary_zipon_coordinate as canary
from zipon_coordinate_diagnostics import safe_error

OUTPUT=guard.DATA/'coordinate_resume_readonly_result.json'


def reconcile(rows,bulk,canary_journal,old_journal,live):
    result={'db_write':False,'write_retry_authorized':False,'canary_reconciliation':'FAIL',
            'remaining_eligible_count':None,'canary_action':'BLOCKED','issues':[]}
    issues=result['issues']
    if {r['project_id'] for r in live}!=set(guard.in_database()) or len(live)!=130:
        issues.append('CANONICAL_ID_SET_MISMATCH');return result
    by_id={r['project_id']:r for r in live}
    candidate=next(r for r in rows if r['project_id']==canary.TARGET)
    before=canary_journal.get('before') or {};after=canary_journal.get('after') or {}
    current=by_id[canary.TARGET]
    if (canary_journal.get('project_id')!=canary.TARGET or canary_journal.get('result')!='SUCCESS'
            or canary_journal.get('rpc_result')!='location_set' or before.get('revision')!=1
            or after.get('revision')!=2):issues.append('CANARY_JOURNAL_INVALID')
    attempts=old_journal.get('results') or []
    if (old_journal.get('pending_project_id')!=canary.TARGET or len(attempts)!=1
            or attempts[0].get('project_id')!=canary.TARGET
            or attempts[0].get('result')!='UNKNOWN_AFTER_REQUEST'
            or not old_journal.get('before') or old_journal.get('before')!=old_journal.get('after')):
        issues.append('OLD_UNCERTAIN_RUN_REQUIRES_SEPARATE_REVIEW')
    lon,lat=guard._point(current.get('location'))
    checks={'location_present':current.get('location') is not None,
            'exact_accepted_coordinates':(lon,lat)==(candidate['longitude'],candidate['latitude']),
            'revision_is_2':current.get('revision')==2,
            'geometry_protected':current.get('geometry')==before.get('geometry') and
                current.get('geometry_verified') is False and before.get('geometry_verified') is False,
            'live_matches_success_journal':current==after,
            'other_fields_protected':{k:v for k,v in current.items() if k not in canary.ALLOWED}==
                {k:v for k,v in before.items() if k not in canary.ALLOWED},
            'other_evidence_protected':{k:v for k,v in (current.get('field_evidence') or {}).items() if k!='location'}==
                {k:v for k,v in (before.get('field_evidence') or {}).items() if k!='location'}}
    result['canary_checks']=checks
    issues.extend(k for k,v in checks.items() if not v)
    remaining=[r for r in rows if r['project_id']!=canary.TARGET]
    issues.extend(guard.preflight_all(remaining,live))
    baseline={r['project_id']:r for r in old_journal.get('before',[])}
    for row in live:
        if row['project_id']==canary.TARGET:continue
        old=baseline.get(row['project_id'])
        if not old or any(row.get(k)!=v for k,v in old.items()):
            issues.append({'project_id':row['project_id'],'reason':'OTHER_ROW_CHANGED_SINCE_BASELINE'})
    review={r['project_id'] for r in bulk['items'] if r['outcome']=='REVIEW_REQUIRED'}
    failed={r['project_id'] for r in bulk['items'] if r['outcome']=='FAILED'}
    target_ids={r['project_id'] for r in remaining}
    if len(remaining)!=121 or target_ids & (review|failed) or len(review)!=5 or len(failed)!=1:
        issues.append('REMAINING_OR_EXCLUSIONS_MISMATCH')
    result.update(review_excluded=len(review),failed_excluded=len(failed),remaining_candidate_count=len(remaining))
    if not issues:
        result.update(canary_reconciliation='PASS',canary_action='ALREADY_APPLIED_SKIP',
                      remaining_eligible_count=121,resume_plan='READ_ONLY_VALIDATED',
                      remaining=[{'project_id':r['project_id'],'expected_revision':by_id[r['project_id']]['revision']} for r in remaining])
    return result


def main():
    files=[guard.REPORT,canary.REPORT]
    raw=[p.read_bytes() for p in files]
    old_journal,canary_journal=map(json.loads,raw)
    bulk=json.loads((guard.DATA/'bulk_geocode_result_20260927.json').read_text(encoding='utf-8'))
    rows=guard.validate_queue(json.loads((guard.DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8')),bulk)
    try:url,headers=guard.existing.configuration()
    except guard.existing.ApplyBlocked as exc:
        print('USER ACTION REQUIRED: '+exc.reason);return 2
    import requests
    try:
        response=requests.get(url+'/rest/v1/development_projects',headers=headers,
            params={'select':'*','limit':1000,'order':'project_id'},timeout=30,allow_redirects=False)
        response.raise_for_status()
        result=reconcile(rows,bulk,canary_journal,old_journal,response.json())
    except Exception as exc:
        result={'db_write':False,'canary_reconciliation':'UNAVAILABLE','error':safe_error(exc),'write_retry_authorized':False}
    result['source_journal_sha256']=[sha256(b).hexdigest() for b in raw]
    result['journals_unchanged']=all(p.read_bytes()==b for p,b in zip(files,raw))
    if not result['journals_unchanged']:result['canary_reconciliation']='FAIL'
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='remaining'},ensure_ascii=False))
    return 0 if result['canary_reconciliation']=='PASS' else 2


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'result':'STOPPED','db_write':False,'error':safe_error(exc)}));sys.exit(2)
