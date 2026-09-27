"""Authorized 121-row resume. Old journals remain immutable; no automatic retries."""
import json
import sys
import argparse
from hashlib import sha256
from zipon_journal import save as save_journal
import reconcile_zipon_resume as review
from zipon_coordinate_diagnostics import safe_error

guard=review.guard
REPORT=guard.DATA/'coordinate_resume_apply_result.json'


def run(rows,bulk,canary_journal,old_journal,request,persist,partial_journal=None):
    report={'db_write':False,'write_attempted':False,'result':'BLOCKED','results':[],
            'accepted_total':122,'already_applied':0,'newly_written':0,'failed':0,'conflict':0}
    def snapshot():
        return request('GET','development_projects',params={'select':'*','limit':1000,'order':'project_id'})
    before=snapshot()
    def make_plan(snapshot):
        if partial_journal is None:return review.reconcile(rows,bulk,canary_journal,old_journal,snapshot)
        from reconcile_zipon_partial import reconcile
        found=reconcile(rows,bulk,partial_journal,snapshot)
        valid=(found['result']=='PASS' and found['normal_applied_count']==42 and found['remaining_count']==80)
        return dict(found,canary_reconciliation='PASS' if valid else 'FAIL')
    plan=make_plan(before)
    report['preflight']=plan
    persist(report)
    if plan['canary_reconciliation']!='PASS':return report
    # One additional complete gate just before the first write catches concurrent changes.
    fresh=snapshot()
    fresh_plan=make_plan(fresh)
    if fresh_plan['canary_reconciliation']!='PASS' or before!=fresh:
        report['reason']='STATE_CHANGED_BEFORE_WRITE';persist(report);return report
    baseline={r['project_id']:r for r in before}
    targets={r['project_id']:r for r in rows}
    skip={review.canary.TARGET} if partial_journal is None else {r['project_id'] for r in plan['already_applied']}
    pending=[r for r in rows if r['project_id'] not in skip]
    expected_count=121 if partial_journal is None else 80
    if len(pending)!=expected_count:raise ValueError('EXACT_PENDING_COUNT_REQUIRED')
    report.update(already_applied=len(skip),canary_action='ALREADY_APPLIED_SKIP',before=before)
    for row in pending:
        report.update(write_attempted=True,pending_project_id=row['project_id'],db_write='UNKNOWN')
        persist(report)
        try:
            payload=guard.existing.payload_for(row,baseline[row['project_id']])
            answer=request('POST',guard.existing.RPC,payload=payload)
            if isinstance(answer,list):answer=answer[0] if len(answer)==1 else None
            if not isinstance(answer,dict):raise ValueError('INVALID_RPC_RESPONSE')
            kind=answer.get('result')
            entry={'project_id':row['project_id'],'result':kind if kind in ('location_set','refused','skipped') else 'UNKNOWN',
                   'revision_conflict':answer.get('reason')=='REVISION_CONFLICT'}
            report['results'].append(entry)
            if kind=='location_set':
                report['newly_written']+=1
            elif entry['revision_conflict']:report['conflict']+=1
            else:report['failed']+=1
            report['pending_project_id']=None
            report['db_write']=report['newly_written']>0
        except Exception as exc:
            report['failed']+=1
            report['results'].append({'project_id':row['project_id'],'result':'UNKNOWN_AFTER_REQUEST',**safe_error(exc)})
            persist(report)
            break
        # Local journal I/O errors are NOT RPC failures. Retain the acknowledgement
        # exactly once and stop before another request; never retry a write.
        try:
            persist(report)
        except OSError as exc:
            report['journal_error']={'stage':'LOCAL_JOURNAL_PERSIST',**safe_error(exc)}
            print(json.dumps({'stage':'LOCAL_JOURNAL_PERSIST','rpc_result':kind,
                              'newly_written':report['newly_written'],'failed':report['failed'],
                              'project_id':row['project_id']}))
            break
        if kind!='location_set':break
    try:
        after=snapshot()
        report['after']=after
        after_by={r['project_id']:r for r in after}
        all_points=len(after)==130 and set(after_by)==set(baseline)
        located_points_match=all_points
        protected=all_points
        for pid,old in baseline.items():
            new=after_by.get(pid)
            if new is None:protected=False;continue
            if pid not in targets or pid in skip:
                protected &= new==old
            else:
                protected &= {k:v for k,v in old.items() if k not in review.canary.ALLOWED}=={k:v for k,v in new.items() if k not in review.canary.ALLOWED}
                protected &= {k:v for k,v in (old.get('field_evidence') or {}).items() if k!='location'}=={k:v for k,v in (new.get('field_evidence') or {}).items() if k!='location'}
            if pid in targets:
                row=targets[pid]
                all_points &= guard._point(new.get('location'))==(row['longitude'],row['latitude'])
                expected=old['revision'] if pid in skip else old['revision']+1
                all_points &= new.get('revision')==expected
                if new.get('location') is not None:
                    located_points_match &= guard._point(new['location'])==(row['longitude'],row['latitude']) and new.get('revision')==expected
        report.update(located=sum(r.get('location') is not None for r in after),
                      verified_polygons=sum(r.get('geometry_verified') is True and r.get('geometry') is not None for r in after),
                      protected_fields_unchanged=protected,accepted_points_match=located_points_match,
                      located_accepted_points_match=located_points_match,all_accepted_complete=all_points,
                      not_attempted=expected_count-len({r['project_id'] for r in report['results']}),review_excluded=5,failed_excluded=1)
        report['result']='SUCCESS' if all_points and protected and report['newly_written']==expected_count and not report['failed'] and not report['conflict'] and not report.get('journal_error') else 'STOPPED_RECONCILIATION_REQUIRED'
    except Exception as exc:
        report.update(result='STOPPED_RECONCILIATION_REQUIRED',reconciliation_error=safe_error(exc))
    persist(report)
    return report


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--remaining80',action='store_true');args=ap.parse_args()
    output=guard.DATA/'coordinate_remaining80_apply_result.json' if args.remaining80 else REPORT
    if output.exists() and json.loads(output.read_text(encoding='utf-8')).get('write_attempted'):
        print('STOPPED: RESUME_ALREADY_ATTEMPTED; read-only reconciliation required');return 2
    inputs=[guard.REPORT,review.canary.REPORT,review.OUTPUT]
    raw=[p.read_bytes() for p in inputs]
    old,canary,approval=map(json.loads,raw)
    if (approval.get('canary_reconciliation')!='PASS' or approval.get('remaining_eligible_count')!=121
        or approval.get('source_journal_sha256')!=[sha256(b).hexdigest() for b in raw[:2]]):
        print('STOPPED: VALIDATED_RESUME_PLAN_REQUIRED');return 2
    partial_journal=None
    if args.remaining80:
        from reconcile_zipon_partial import OUTPUT
        inputs.extend([REPORT,OUTPUT]);raw.extend([REPORT.read_bytes(),OUTPUT.read_bytes()])
        partial_journal=json.loads(raw[-2]);partial_plan=json.loads(raw[-1])
        if (partial_plan.get('result')!='PASS' or partial_plan.get('normal_applied_count')!=42
            or partial_plan.get('remaining_count')!=80 or partial_plan.get('mismatch_count')!=0
            or partial_plan.get('source_journal_sha256')!=sha256(raw[-2]).hexdigest()):
            print('STOPPED: LIVE_PARTIAL_RECONCILIATION_REQUIRED');return 2
    bulk=json.loads((guard.DATA/'bulk_geocode_result_20260927.json').read_text(encoding='utf-8'))
    rows=guard.validate_queue(json.loads((guard.DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8')),bulk)
    url,headers=guard.existing.configuration()
    permitted=({r['project_id'] for r in partial_plan['remaining']} if args.remaining80 else
               {r['project_id'] for r in rows}-{review.canary.TARGET})
    import requests
    def request(method,table,params=None,payload=None):
        if method=='POST' and (table!=guard.existing.RPC or payload.get('p_project_id') not in permitted):
            raise ValueError('WRITE_SCOPE_VIOLATION')
        response=requests.request(method,url+'/rest/v1/'+table,params=params,json=payload,headers=headers,
                                  timeout=30,allow_redirects=False)
        response.raise_for_status();return response.json()
    def persist(report):
        if any(p.read_bytes()!=b for p,b in zip(inputs,raw)):raise ValueError('SOURCE_JOURNAL_CHANGED')
        report['source_journal_sha256']=[sha256(b).hexdigest() for b in raw]
        save_journal(output,report)
    result=run(rows,bulk,canary,old,request,persist,partial_journal)
    print(json.dumps({k:v for k,v in result.items() if k not in ('before','after','preflight','results')},ensure_ascii=False))
    return 0 if result['result']=='SUCCESS' else 2


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'result':'STOPPED','error':safe_error(exc)}));sys.exit(2)
