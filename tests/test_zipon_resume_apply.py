import copy
import struct
import unittest
from tests import test_zipon_resume_reconciliation as fixtures
import resume_zipon_coordinates as runner
from services.development_presentation import map_point,present_project
from services.development import _point


class ResumeApplyTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ResumeReconciliationTests();self.fixture.setUp()
        self.live=copy.deepcopy(self.fixture.live);self.posts=[];self.journal=[]

    def request(self,method,table,params=None,payload=None):
        if method=='GET':return copy.deepcopy(self.live)
        pid=payload['p_project_id'];self.posts.append(pid)
        self.assertNotEqual(pid,runner.review.canary.TARGET)
        self.assertEqual(table,'rpc/zipon_set_project_location')
        row=next(r for r in self.live if r['project_id']==pid)
        self.assertEqual(row['revision'],payload['p_expected_revision'])
        row['location']=struct.pack('<BIIdd',1,0x20000001,4326,payload['p_longitude'],payload['p_latitude']).hex()
        row['revision']+=1
        return {'result':'location_set'}

    def run_apply(self,request=None):
        f=self.fixture
        return runner.run(f.rows,f.bulk,f.canary,f.old,request or self.request,lambda r:self.journal.append(copy.deepcopy(r)))

    def test_121_only_success_and_map_payload(self):
        result=self.run_apply()
        self.assertEqual(result['result'],'SUCCESS')
        self.assertEqual(len(set(self.posts)),121)
        self.assertEqual((result['located'],result['already_applied'],result['verified_polygons']),(122,1,0))
        markers=[]
        for row in self.live:
            lon,lat=_point(row['location'])
            markers.append(map_point(dict(row,longitude=lon,latitude=lat,boundary=None)))
            self.assertNotEqual(present_project(row)['spatial']['code'],'INSIDE')
        self.assertEqual(sum(p['mappable'] for p in markers),122)
        self.assertEqual(present_project({'project_id':'0164b2b0-1b21-51e3-8b8d-f97bda852a18'})['stage']['label'],'조합설립추진위원회승인')

    def test_bad_remaining_row_blocks_all_writes(self):
        self.live[-1]['revision']=9
        result=self.run_apply()
        self.assertEqual(result['result'],'BLOCKED')
        self.assertEqual(self.posts,[])

    def test_conflict_stops_at_first_request(self):
        def req(method,*a,**kw):
            if method=='POST':
                self.posts.append(kw['payload']['p_project_id'])
                return {'result':'refused','reason':'REVISION_CONFLICT'}
            return self.request(method,*a,**kw)
        result=self.run_apply(req)
        self.assertEqual(len(self.posts),1)
        self.assertEqual(result['conflict'],1)
        self.assertNotEqual(result['result'],'SUCCESS')

    def test_lost_response_stops_and_keeps_uncertain_id(self):
        def req(method,*a,**kw):
            answer=self.request(method,*a,**kw)
            if method=='POST':raise TimeoutError('DO_NOT_LOG')
            return answer
        result=self.run_apply(req)
        self.assertEqual(len(self.posts),1)
        self.assertEqual(result['db_write'],'UNKNOWN')
        self.assertEqual(result['located'],2)
        self.assertEqual(result['pending_project_id'],self.posts[0])

if __name__=='__main__':unittest.main()
