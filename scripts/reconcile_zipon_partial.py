"""Read-only, all-project reconciliation after an interrupted resume. Never writes DB."""
import json
import sys
from hashlib import sha256
import resume_zipon_coordinates as resume
from zipon_coordinate_diagnostics import safe_error
from zipon_journal import save as save_journal
guard=resume.guard
OUTPUT=guard.DATA/'coordinate_partial_readonly_result.json'


def reconcile(rows,bulk,journal,live):
    targets={r['project_id']:r for r in rows}
    baseline={r['project_id']:r for r in journal['before']}
    acknowledged={r['project_id'] for r in journal['results'] if r['result']=='location_set'}
    acknowledged.add(resume.review.canary.TARGET)
    result={'db_write':False,'write_retry_authorized':False,'result':'BLOCKED',
            'mismatches':[],'issues':[],'already_applied':[],'remaining':[]}
    if len(live)!=130 or {r['project_id'] for r in live}!=set(baseline) or set(baseline)!=set(guard.in_database()):
        result['issues'].append('CANONICAL_IDS_CHANGED');return result
    for db in live:
        pid=db['project_id'];old=baseline[pid]
        if pid not in targets:
            if db!=old:result['issues'].append({'project_id':pid,'reason':'EXCLUDED_PROJECT_CHANGED'})
            continue
        row=targets[pid];actual=guard._point(db.get('location'));expected=(row['longitude'],row['latitude'])
        if db.get('location') is None:
            if pid in acknowledged or db!=old:
                result['issues'].append({'project_id':pid,'reason':'MISSING_ACKNOWLEDGED_LOCATION_OR_CHANGED_PENDING_ROW'})
            else:result['remaining'].append({'project_id':pid,'expected_revision':db['revision']})
            continue
        expected_revision=old['revision'] if pid==resume.review.canary.TARGET else old['revision']+1
        protected={k:v for k,v in db.items() if k not in resume.review.canary.ALLOWED}=={k:v for k,v in old.items() if k not in resume.review.canary.ALLOWED}
        protected &= {k:v for k,v in (db.get('field_evidence') or {}).items() if k!='location'}=={k:v for k,v in (old.get('field_evidence') or {}).items() if k!='location'}
        checks={'coordinates_exact':actual==expected,'revision':db['revision']==expected_revision,
                'protected_fields':protected,'not_verified_polygon':db.get('geometry_verified') is False,
                'rpc_acknowledged':pid in acknowledged}
        entry={'project_id':pid,'expected':{'longitude':expected[0],'latitude':expected[1]},
               'actual':{'longitude':actual[0],'latitude':actual[1]},'revision':db['revision'],
               'expected_revision':expected_revision,'checks':checks,'coordinate_order':'longitude,latitude',
               'comparison':'EXACT_DOUBLE_EQUALITY_NO_TOLERANCE_CHANGE'}
        if all(checks.values()):result['already_applied'].append(dict(entry,action='ALREADY_APPLIED_SKIP'))
        else:result['mismatches'].append(entry)
    excluded={r['project_id'] for r in bulk['items'] if r['outcome']!='ACCEPTED'}
    if excluded & set(targets):result['issues'].append('UNACCEPTED_TARGET')
    result.update(accepted_total=len(targets),normal_applied_count=len(result['already_applied']),remaining_count=len(result['remaining']),
                  mismatch_count=len(result['mismatches']),
                  review_excluded=sum(r['outcome']=='REVIEW_REQUIRED' for r in bulk['items']),
                  failed_excluded=sum(r['outcome']=='FAILED' for r in bulk['items']),
                  located=sum(r.get('location') is not None for r in live),
                  verified_polygons=sum(r.get('geometry_verified') is True and r.get('geometry') is not None for r in live))
    result['accepted_points_match']=not result['mismatches']
    result['protected_fields_ok']=not result['issues'] and all(r['checks']['protected_fields'] for r in result['mismatches'])
    if not result['mismatches'] and not result['issues'] and result['normal_applied_count']+result['remaining_count']==122:
        result.update(result='PASS',resume_plan='READ_ONLY_VALIDATED_NO_WRITE_AUTHORIZATION')
    return result


def main():
    raw=resume.REPORT.read_bytes();journal=json.loads(raw)
    bulk=json.loads((guard.DATA/'bulk_geocode_result_20260927.json').read_text(encoding='utf-8'))
    rows=guard.validate_queue(json.loads((guard.DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8')),bulk)
    try:url,headers=guard.existing.configuration()
    except guard.existing.ApplyBlocked as exc:
        print('USER ACTION REQUIRED: '+exc.reason);return 2
    import requests
    response=requests.get(url+'/rest/v1/development_projects',headers=headers,
                          params={'select':'*','limit':1000,'order':'project_id'},timeout=30,allow_redirects=False)
    response.raise_for_status()
    result=reconcile(rows,bulk,journal,response.json())
    result['source_journal_sha256']=sha256(raw).hexdigest()
    result['journal_unchanged']=resume.REPORT.read_bytes()==raw
    if not result['journal_unchanged']:result['result']='BLOCKED'
    save_journal(OUTPUT,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('already_applied','remaining')},ensure_ascii=False))
    return 0 if result['result']=='PASS' else 2

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'result':'STOPPED','db_write':False,'error':safe_error(exc)}));sys.exit(2)
