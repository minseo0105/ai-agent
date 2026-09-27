import copy
import json
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import reconcile_zipon_resume as resume


class ResumeReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.bulk=json.loads((resume.guard.DATA/'bulk_geocode_result_20260927.json').read_text(encoding='utf-8'))
        self.rows=resume.guard.validate_queue(json.loads((resume.guard.DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8')),self.bulk)
        ids=resume.guard.in_database()
        self.live=[dict(project_id=r['project_id'],address=r['canonical_address'],sigungu=r['district'],revision=1,
                        location=None,geometry=None,geometry_verified=False,stage_raw='original',field_evidence={'stage':'keep'}) for r in self.rows]
        self.live += [dict(self.live[0],project_id=pid) for pid in ids-{r['project_id'] for r in self.rows}]
        self.old={'before':copy.deepcopy(self.live),'after':copy.deepcopy(self.live),
                  'pending_project_id':resume.canary.TARGET,'results':[{'project_id':resume.canary.TARGET,'result':'UNKNOWN_AFTER_REQUEST'}]}
        self.target=next(r for r in self.live if r['project_id']==resume.canary.TARGET)
        before=copy.deepcopy(self.target)
        candidate=next(r for r in self.rows if r['project_id']==resume.canary.TARGET)
        self.target.update(location=struct.pack('<BIIdd',1,0x20000001,4326,candidate['longitude'],candidate['latitude']).hex(),revision=2)
        self.canary={'project_id':resume.canary.TARGET,'result':'SUCCESS','rpc_result':'location_set',
                     'before':before,'after':copy.deepcopy(self.target)}

    def check(self):return resume.reconcile(self.rows,self.bulk,self.canary,self.old,self.live)

    def test_success_skips_exactly_one_without_authorizing_write(self):
        result=self.check()
        self.assertEqual(result['canary_reconciliation'],'PASS')
        self.assertEqual(result['remaining_eligible_count'],121)
        self.assertEqual(result['canary_action'],'ALREADY_APPLIED_SKIP')
        self.assertFalse(result['write_retry_authorized'])
        self.assertEqual((result['review_excluded'],result['failed_excluded']),(5,1))
        self.assertNotIn(resume.canary.TARGET,{r['project_id'] for r in result['remaining']})

    def test_modified_coordinate_revision_geometry_or_stage_blocks(self):
        for k,v in [('location',None),('revision',3),('geometry_verified',True),('stage_raw','changed')]:
            old=self.target[k];self.target[k]=v
            self.assertEqual(self.check()['canary_reconciliation'],'FAIL')
            self.target[k]=old

    def test_remaining_row_changed_blocks(self):
        row=next(r for r in self.live if r['project_id']!=resume.canary.TARGET)
        row['revision']=2
        self.assertEqual(self.check()['canary_reconciliation'],'FAIL')

    def test_extra_uncertain_attempt_blocks(self):
        self.old['results'].append({'project_id':'another','result':'UNKNOWN_AFTER_REQUEST'})
        self.assertEqual(self.check()['canary_reconciliation'],'FAIL')

    def test_original_journals_not_mutated(self):
        before=copy.deepcopy((self.canary,self.old))
        self.check()
        self.assertEqual(before,(self.canary,self.old))

if __name__=='__main__':unittest.main()
