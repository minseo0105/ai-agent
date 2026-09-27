import copy
import json
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import canary_zipon_coordinate as canary


class SingleCanaryTests(unittest.TestCase):
    def setUp(self):
        rows=json.loads((canary.guard.DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8'))['items']
        self.candidate=next(r for r in rows if r['project_id']==canary.TARGET)
        self.row=dict(project_id=canary.TARGET,address=self.candidate['canonical_address'],sigungu=self.candidate['district'],
                      revision=1,location=None,geometry=None,geometry_verified=False,stage_raw='조합설립인가',
                      field_evidence={'official_stage':{'preserve':True}})
        self.posts=0;self.reads=0;self.journal=[]

    def request(self,method,table,params=None,payload=None):
        if method=='GET':
            self.reads+=1
            self.assertEqual(params['project_id'],'eq.'+canary.TARGET)
            return [copy.deepcopy(self.row)]
        self.posts+=1
        self.assertEqual(table,canary.guard.existing.RPC)
        self.assertEqual(payload['p_project_id'],canary.TARGET)
        self.assertEqual(payload['p_expected_revision'],1)
        self.row.update(location=struct.pack('<BIIdd',1,0x20000001,4326,payload['p_longitude'],payload['p_latitude']).hex(),
                        revision=2,location_source=payload['p_geocode_source'],location_verified_at='2026-09-27T00:00:00Z')
        return {'result':'location_set'}

    def execute(self,request=None):
        return canary.run(self.candidate,request or self.request,lambda r:self.journal.append(copy.deepcopy(r)))

    def test_exactly_one_write_and_readback_success(self):
        result=self.execute()
        self.assertEqual(result['result'],'SUCCESS')
        self.assertEqual(self.posts,1)
        self.assertEqual(self.reads,2)
        self.assertTrue(self.journal[0]['write_attempted'])

    def test_existing_point_polygon_and_revision_block(self):
        for key,value in [('location','existing'),('geometry_verified',True),('revision',2)]:
            old=self.row[key];self.row[key]=value
            self.assertEqual(self.execute()['result'],'BLOCKED')
            self.assertEqual(self.posts,0)
            self.row[key]=old

    def test_timeout_after_commit_never_retries_or_reports_success(self):
        def request(method,*a,**kw):
            response=self.request(method,*a,**kw)
            if method=='POST':raise TimeoutError('secret')
            return response
        result=self.execute(request)
        self.assertTrue(result['location_present'])
        self.assertEqual(result['result'],'STOPPED_RECONCILIATION_REQUIRED')
        self.assertEqual(self.posts,1)
        self.assertNotIn('secret',json.dumps(result))

    def test_stage_mutation_fails_reconciliation(self):
        def request(method,*a,**kw):
            response=self.request(method,*a,**kw)
            if method=='POST':self.row['stage_raw']='changed'
            return response
        self.assertFalse(self.execute(request)['protected_fields_unchanged'])

    def test_journal_failure_prevents_write(self):
        def fail(report):raise OSError('disk unavailable')
        with self.assertRaises(OSError):canary.run(self.candidate,self.request,fail)
        self.assertEqual(self.posts,0)

if __name__=='__main__':unittest.main()
