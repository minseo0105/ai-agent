"""All-122 gate around the existing location RPC. Default is read-only dry-run."""
import argparse, json, sys
from pathlib import Path
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
import apply_zipon_geocode as existing
from build_zipon_geocode_targets import in_database
from zipon_coordinate_diagnostics import safe_error
from services.development import _point
from services.development_geocode import normalize_address, coordinate_orientation, candidate_checks, wanted_parts

DATA=ROOT/'data/development'
REPORT=DATA/'coordinate_apply_guarded_result.json'

def validate_queue(queue,bulk):
    rows=queue.get('items') or []
    accepted={r['project_id']:r for r in bulk['items'] if r['outcome']=='ACCEPTED'}
    if not (len(rows)==122 and len(accepted)==122):raise ValueError('EXACTLY_122_REQUIRED')
    if not (len({r['project_id'] for r in rows})==122):raise ValueError('DUPLICATE_ID')
    if not ({r['project_id'] for r in rows}==set(accepted)):raise ValueError('ACCEPTED_SET_MISMATCH')
    for row in rows:
        UUID(row['project_id'])
        source=accepted[row['project_id']]
        for key in ('canonical_address','district','longitude','latitude'):
            if not (row[key]==source[key]):raise ValueError('ARTIFACT_CHANGED')
        if not (row['geocode_status']=='ACCEPTED' and row['coordinate_verified'] is True):raise ValueError('NOT_VERIFIED')
        if not (row['geocode_source']=='naver:geocode' and row['geocode_confidence']=='EXACT'):raise ValueError('NOT_EXACT_NAVER')
        if not (row['coordinate_orientation']==coordinate_orientation(row['longitude'],row['latitude'])=='X_IS_LONGITUDE'):raise ValueError('AXIS')
        if not (row.get('checks') and all(v is True for v in row['checks'].values())):raise ValueError('EVIDENCE_CHECKS')
        checks,_=candidate_checks(wanted_parts(row['canonical_address']),dict(row,accuracy=source['accuracy']))
        if not (all(checks.values())):raise ValueError('RECOMPUTED_ADDRESS_CHECKS')
    return rows

def preflight_all(rows,stored):
    if len(stored)!=130 or {r['project_id'] for r in stored}!=set(in_database()):
        return [{'reason':'CANONICAL_ID_SET_MISMATCH'}]
    by_id={r['project_id']:r for r in stored};issues=[]
    for row in rows:
        db=by_id.get(row['project_id'])
        reasons=existing.preflight(row,db)
        if db and normalize_address(db.get('address'))!=normalize_address(row['canonical_address']):
            reasons.append('ADDRESS_MISMATCH')
        if db and db['project_id']!=row['project_id']:reasons.append('PROJECT_ID_MISMATCH')
        if reasons:issues.append({'project_id':row['project_id'],'reasons':reasons})
    return issues

def execute(rows,request,apply=False,persist=lambda report: None):
    select='project_id,address,sigungu,revision,location,geometry,geometry_verified,stage,stage_raw,project_type,canonical_source_id'
    def snapshot():return request('GET','development_projects',params={'select':select,'limit':1000,'order':'project_id'})
    before=snapshot();issues=preflight_all(rows,before)
    report={'preflight':'FAIL' if issues else 'PASS','dry_run':'BLOCKED' if issues else 'PASS',
            'db_write':False,'write_attempted':False,'issues':issues,'results':[],'before':before}
    persist(report)
    if issues or not apply:return report
    # Complete second read before any write: a failed row or changed revision blocks every write.
    fresh=snapshot();issues=preflight_all(rows,fresh)
    original={r['project_id']:r for r in before}
    issues += [{'project_id':r['project_id'],'reasons':['REVISION_CONFLICT']} for r in fresh
               if r['revision']!=original.get(r['project_id'],{}).get('revision')]
    if issues:
        report.update(preflight='FAIL',issues=issues)
        persist(report)
        return report
    baseline={r['project_id']:r for r in fresh}
    for row in rows:
        report['write_attempted']=True
        report['pending_project_id']=row['project_id']
        persist(report)  # Crash/timeout leaves the exact attempted ID, never a credential.
        try:
            answer=request('POST',existing.RPC,payload=existing.payload_for(row,baseline[row['project_id']]))
            if isinstance(answer,list):answer=answer[0] if answer else {}
            result={'project_id':row['project_id'],'result':answer.get('result'),'reason':answer.get('reason')}
            report['results'].append(result)
            report['db_write']=report['db_write'] or result['result']=='location_set'
            report['pending_project_id']=None
            persist(report)
            if result['result']!='location_set':break
        except Exception as exc:
            report['results'].append({'project_id':row['project_id'],'result':'UNKNOWN_AFTER_REQUEST',
                                      **safe_error(exc)})
            report['db_write']='UNKNOWN'  # Server may have committed before a lost response.
            persist(report)
            break
    try:
        after=snapshot()
    except Exception as exc:
        report.update(final='RECONCILIATION_REQUIRED',reconciliation_error=type(exc).__name__)
        persist(report)
        return report
    report['after']=after
    results=report['results'];success=sum(r['result']=='location_set' for r in results)
    report.update(success=success,
        failed=sum(r['result'] not in ('location_set','skipped') and r.get('reason')!='REVISION_CONFLICT' for r in results),
        skipped=sum(r['result']=='skipped' for r in results),
        conflict=sum(r.get('reason')=='REVISION_CONFLICT' for r in results),
        not_attempted=len(rows)-len(results),located=sum(r['location'] is not None for r in after),
        verified_polygons=sum(bool(r['geometry_verified']) for r in after))
    targets={r['project_id']:r for r in rows}
    unchanged={r['project_id'] for r in after}==set(baseline) and len(after)==130
    coordinates=True
    for db in after:
        old=baseline.get(db['project_id'])
        if old is None:
            unchanged=False
            continue
        if db['project_id'] not in targets:
            unchanged &= db==old
        else:
            unchanged &= all(db[k]==old[k] for k in ('address','sigungu','geometry','geometry_verified','stage','stage_raw','project_type','canonical_source_id'))
            lon,lat=_point(db['location']);row=targets[db['project_id']]
            coordinates &= lon is not None and abs(lon-row['longitude'])<1e-8 and abs(lat-row['latitude'])<1e-8 and db['revision']==old['revision']+1
    report['protected_fields_unchanged']=unchanged
    report['final']='PASS' if success==122 and unchanged and coordinates else 'INCOMPLETE_RECONCILIATION_REQUIRED'
    persist(report)
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--apply',action='store_true');ap.add_argument('--offline',action='store_true');args=ap.parse_args()
    queue=json.loads((DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8'))
    bulk=json.loads((DATA/'bulk_geocode_result_20260927.json').read_text(encoding='utf-8'))
    rows=validate_queue(queue,bulk)
    if args.offline:print('OFFLINE ARTIFACT: PASS (122; no network)');return 0
    try:url,headers=existing.configuration()
    except existing.ApplyBlocked as exc:
        print('USER ACTION REQUIRED: '+exc.reason);return 2
    import requests
    def request(method,table,params=None,payload=None):
        response=requests.request(method,url+'/rest/v1/'+table,headers=headers,params=params,json=payload,timeout=30)
        response.raise_for_status();return response.json()
    if REPORT.exists():
        previous=json.loads(REPORT.read_text(encoding='utf-8'))
        if previous.get('write_attempted'):
            print('STOPPED: PRIOR_WRITE_RUN_REQUIRES_READ_ONLY_RECONCILIATION; retained journal');return 2
    def persist(report):
        temporary=REPORT.with_suffix('.tmp')
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(REPORT)
    try:report=execute(rows,request,args.apply,persist)
    except Exception as exc:
        print('STOPPED: '+type(exc).__name__+'; no automatic retry; reconcile before another apply');return 1
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('before','after','results','issues')},ensure_ascii=False))
    return 0 if report.get('final')=='PASS' or (not args.apply and report['preflight']=='PASS') else 1

if __name__=='__main__':sys.exit(main())
