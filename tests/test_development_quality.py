import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from services.development_quality import refine,normalize_name,normalize_address

ROOT=Path(__file__).resolve().parents[1]
def row(i,name='방배1구역',district='서초구',kind='RECONSTRUCTION',external=None,**kw):
    value={'project_id':str(i),'project_name':name,'sigungu':district,'dong':'방배동',
      'project_type':kind,'official_authority':'official.example' if external else None,
      'external_id':external,'address':'서울특별시 서초구 방배동 1번지','stage':None,
      'stage_raw':'준비','status':'UNKNOWN','validation_status':'NEEDS_REVIEW',
      'source':{'is_official':True,'source_url':'https://official.example/'+str(i),
                'collected_at':'2026-09-27T00:00:00Z','content_hash':str(i)}}
    value.update(kw);return value

class QualityTests(unittest.TestCase):
    def test_external_exact(self):
        c,_,q=refine([row(1,external='a'),row(2,external='a')])
        self.assertEqual(len(c['projects']),1);self.assertEqual(q['exact_duplicates_merged'],1)
    def test_same_name_probable_only(self):
        c,r,_=refine([row(1),row(2)])
        self.assertEqual(len(c['projects']),2);self.assertEqual(len(r['pairs']),1)
    def test_zone_numbers_distinct(self):
        c,r,_=refine([row(1),row(2,name='방배2구역')])
        self.assertEqual(len(c['projects']),2);self.assertFalse(r['pairs'])
    def test_zone_letters_distinct(self):
        c,r,_=refine([row(1,name='천호A구역'),row(2,name='천호B구역')])
        self.assertEqual(len(c['projects']),2)
        self.assertFalse(r['pairs'])
    def test_district_distinct(self):
        c,_,q=refine([row(1,external='a'),row(2,external='a',district='강동구')])
        self.assertEqual(len(c['projects']),2)
        self.assertTrue(any(a['issue']=='external_id_multiple_canonical' for a in q['anomalies']))
    def test_type_distinct(self):
        c,_,_=refine([row(1,external='a'),row(2,external='a',kind='MOATOWN')])
        self.assertEqual(len(c['projects']),2)
    def test_sources_preserved(self):
        c,_,_=refine([row(1,external='a'),row(2,external='a')]);self.assertEqual(c['projects'][0]['source_count'],2)
    def test_original_names(self):
        names=['방배1구역 주택재건축정비사업','방배1구역 재건축사업']
        c,_,_=refine([row(1,name=names[0],external='a'),row(2,name=names[1],external='a')])
        self.assertEqual(set(c['projects'][0]['original_names']),set(names))
    def test_conflicts_no_arbitrary_pick(self):
        c,_,q=refine([row(1,external='a'),row(2,external='a',address='서울 서초구 방배동 2번지',status='COMPLETED',stage_raw='완료')])
        p=c['projects'][0];self.assertIsNone(p['address']);self.assertIsNone(p['status'])
        self.assertGreaterEqual(q['conflict_count'],3)
    def test_id_order_stable(self):
        rows=[row(1,external='a'),row(2,external='a')]
        self.assertEqual(refine(rows),refine(list(reversed(rows))))
    def test_repeat_stable(self):
        rows=[row(1),row(2)];self.assertEqual(refine(rows),refine(rows))
    def test_input_unchanged(self):
        rows=[row(1)];before=copy.deepcopy(rows);refine(rows);self.assertEqual(rows,before)
    def test_no_network(self):
        with patch('socket.socket',side_effect=AssertionError('No network')):refine([row(1)])
    def test_address_and_name_normalization(self):
        self.assertEqual(normalize_address('서울특별시 서초구 방배동 1번지'),normalize_address('서울시  서초구 방배동 1'))
        self.assertEqual(normalize_name('방배(1)구역 주택재건축정비사업'),normalize_name(' 방배1구역 재건축사업 '))
    def test_type_mapping_and_canary(self):
        a=row(1,kind='SHINTONG');c,_,q=refine([a],[a]);p=c['projects'][0]
        self.assertEqual(p['project_type'],'FAST_TRACK');self.assertEqual(p['import_plan']['db_project_type'],'SHINTONG')
        self.assertEqual(p['import_plan']['db_project_id'],'1');self.assertEqual(q['canary_preserved'],1)
    def test_official_id_zone_conflict_blocked(self):
        c,_,_=refine([row(1,external='a'),row(2,external='a',name='방배2구역')]);self.assertEqual(len(c['projects']),2)
    def test_actual_183_immutable_and_deterministic(self):
        path=ROOT/'data/development/pilot_20260927.json';raw=path.read_bytes()
        rows=json.loads(raw)['records'];self.assertEqual(len(rows),183)
        result=refine(rows);self.assertEqual(result,refine(rows[::-1]))
        self.assertEqual(hashlib.sha256(raw).digest(),hashlib.sha256(path.read_bytes()).digest())
        self.assertEqual(sum(r['raw_candidate_count'] for r in result[0]['projects']),183)

if __name__=='__main__':unittest.main()
