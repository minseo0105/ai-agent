import copy
import importlib.util
import json
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('coordinate_guard',ROOT/'scripts/apply_zipon_verified_coordinates.py')
guard=importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class CoordinateGuardTests(unittest.TestCase):
    def setUp(self):
        self.queue=json.loads((guard.DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8'))
        self.bulk=json.loads((guard.DATA/'bulk_geocode_result_20260927.json').read_text(encoding='utf-8'))
        self.rows=guard.validate_queue(self.queue,self.bulk)
        self.stored=[dict(project_id=r['project_id'],address=r['canonical_address'],sigungu=r['district'],
                          revision=3,location=None,geometry=None,geometry_verified=False,stage=None,
                          stage_raw='추진위원회승인',project_type='RECONSTRUCTION',canonical_source_id='source')
                     for r in self.rows]
        self.stored += [dict(self.stored[0],project_id=pid) for pid in
                        sorted(set(guard.in_database())-{r['project_id'] for r in self.rows})]
        self.calls=[]
        self.gets=0
        self.journal=[]

    def request(self,method,table,params=None,payload=None):
        self.calls.append(method)
        if method=='GET':
            self.gets+=1
            return copy.deepcopy(self.stored)
        self.assertEqual(table,'rpc/zipon_set_project_location')
        db=next(r for r in self.stored if r['project_id']==payload['p_project_id'])
        self.assertEqual(db['revision'],payload['p_expected_revision'])
        db['location']=struct.pack('<BIIdd',1,0x20000001,4326,payload['p_longitude'],payload['p_latitude']).hex()
        db['revision']+=1
        return {'result':'location_set','project_id':db['project_id']}

    def test_frozen_set_and_tampering(self):
        self.assertEqual(len(self.rows),122)
        for field,value in [('latitude',0),('geocode_status','REVIEW_REQUIRED'),('canonical_address','wrong')]:
            modified=copy.deepcopy(self.queue)
            modified['items'][0][field]=value
            with self.assertRaises((AssertionError,ValueError)):
                guard.validate_queue(modified,self.bulk)

    def test_last_row_failure_blocks_every_write(self):
        for field,value in [('geometry_verified',True),('address','wrong'),('location','existing'),('sigungu','wrong')]:
            saved=self.stored[121][field]
            self.stored[121][field]=value
            result=guard.execute(self.rows,self.request,True)
            self.assertEqual(result['preflight'],'FAIL')
            self.assertNotIn('POST',self.calls)
            self.stored[121][field]=saved

    def test_revision_race_blocks_every_write(self):
        def request(*a,**kw):
            if self.gets==1:self.stored[0]['revision']+=1
            return self.request(*a,**kw)
        result=guard.execute(self.rows,request,True)
        self.assertEqual(result['preflight'],'FAIL')
        self.assertNotIn('POST',self.calls)

    def test_dry_run_never_posts(self):
        result=guard.execute(self.rows,self.request)
        self.assertEqual(result['dry_run'],'PASS')
        self.assertEqual(self.calls,['GET'])

    def test_all_success_reconciles_coordinates_revision_and_protected_rows(self):
        result=guard.execute(self.rows,self.request,True)
        self.assertEqual(result['final'],'PASS')
        self.assertEqual(result['located'],122)
        self.assertEqual(result['verified_polygons'],0)
        self.assertEqual(self.calls.count('POST'),122)

    def test_uncertain_response_stops_and_retains_attempted_id(self):
        def request(method,*a,**kw):
            if method=='POST':
                self.request(method,*a,**kw)  # commit with a lost response
                raise TimeoutError('secret-must-never-be-recorded')
            return self.request(method,*a,**kw)
        result=guard.execute(self.rows,request,True,lambda r:self.journal.append(copy.deepcopy(r)))
        self.assertEqual(result['db_write'],'UNKNOWN')
        self.assertEqual(self.calls.count('POST'),1)
        self.assertEqual(result['located'],1)
        self.assertEqual(result['pending_project_id'],self.rows[0]['project_id'])
        self.assertNotIn('secret-must-never',json.dumps(self.journal))

    def test_failed_postwrite_read_keeps_journal(self):
        def request(method,*a,**kw):
            if method=='GET' and self.gets==2:raise TimeoutError()
            return self.request(method,*a,**kw)
        result=guard.execute(self.rows,request,True,lambda r:self.journal.append(copy.deepcopy(r)))
        self.assertEqual(result['final'],'RECONCILIATION_REQUIRED')
        self.assertEqual(len(result['results']),122)
        self.assertTrue(result['db_write'])

if __name__=='__main__':unittest.main()
