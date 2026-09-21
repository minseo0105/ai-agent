import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from services.golf_catalog import prepare_service_pool, service_status, find_clubs
from services import golf_pool_updater as updater
from services.golf_public_data import match_public_records, fetch_public_golf_records


class ServicePoolTests(unittest.TestCase):
    def test_status(self):
        candidate = dict(id='v', name='시험CC', vworld_x=127, vworld_y=37, pool_source='VWorld', play={'three_person':'확인 필요'})
        self.assertEqual(service_status(candidate), 'candidate')
        detailed = dict(candidate, holes=18, official_url='https://example.com')
        self.assertEqual(service_status(detailed), 'service')
        self.assertEqual(service_status(dict(detailed, holes=9)), 'excluded')
        self.assertEqual(service_status(dict(detailed, holes=9, play={'nine_hole_twice':True})), 'service')
        self.assertEqual(service_status(dict(candidate, holes=None)), 'candidate')

    def test_regions_and_details_preserved(self):
        original = dict(id='a',name='시험CC',area='강원권',subregion='검증지역',city='검증도시',vworld_x=127,vworld_y=37.7,official_url='https://example.com',holes=18,website='extra',fee={'verified':True})
        merged = updater.merge_with_existing([dict(original, area='',official_url='',fee={})], [original])
        self.assertEqual(merged[0], original | {'pool_source':'VWorld LT_P_SGISGOLF','pool_checked':None})
        result = prepare_service_pool(copy.deepcopy(merged))[0]
        self.assertEqual(result['subregion'], '검증지역')
        other = prepare_service_pool([dict(id='b',name='후보',vworld_y=33.4,vworld_x=126.5)])[0]
        self.assertEqual(other['area'],'제주권')
        self.assertEqual(other['region_source'],'coordinate_estimate')
        self.assertEqual(other['service_status'],'candidate')

    def test_direct_search_and_public_failure_preservation(self):
        rows=prepare_service_pool([dict(id='a',name='골프후보'),dict(id='b',name='골프9홀',holes=9)])
        self.assertEqual([c['id'] for c in find_clubs('골프',rows)], ['a'])
        verified=dict(name='검증CC',verification={'public_data':{'matched':True}})
        self.assertTrue(match_public_records([verified],[])[0][0]['verification']['public_data']['matched'])
        record={'BPLC_NM':'검증CC','ROAD_NM_ADDR':'경기 용인','TELNO':'031-000-0000','SALS_STTS_NM':'영업/정상','DTL_SALS_STTS_NM':'영업'}
        club=match_public_records([{'name':'검증CC'}],[record])[0][0]
        self.assertEqual(service_status(club),'candidate')

    def test_public_contract(self):
        response=Mock(status_code=200)
        response.json.return_value={'response':{'header':{'resultCode':'00'},'body':{'totalCount':1,'items':{'item':[{'BPLC_NM':'시험'}]}}}}
        with patch('requests.get',return_value=response) as get:
            self.assertEqual(len(fetch_public_golf_records('synthetic')),1)
            self.assertTrue(get.call_args.args[0].endswith('/golf_courses/info'))
            self.assertEqual(get.call_args.kwargs['params']['numOfRows'],100)

    def test_transaction_rollback_and_optional_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); cat=root/'catalog.json'; meta=root/'catalog_meta.json'
            original=[dict(id='a',name='원장CC',official_url='https://example.com',holes=18)]
            cat.write_text(json.dumps(original),encoding='utf-8'); meta.write_text('{}')
            with patch.multiple(updater,DATA_DIR=root,CATALOG_PATH=cat,META_PATH=meta):
                old=cat.read_bytes(); backup=updater.backup_catalog()
                writer=updater._write_json
                def fail_meta(path,value):
                    if path==meta: raise OSError('synthetic')
                    writer(path,value)
                with patch.object(updater,'_write_json',side_effect=fail_meta):
                    with self.assertRaises(OSError): updater.save_pool(prepare_service_pool(copy.deepcopy(original)),{},backup)
                self.assertEqual(cat.read_bytes(),old)
                self.assertEqual(meta.read_text(),'{}')
                with patch.object(updater,'fetch_vworld_golf_pool',return_value=[dict(id='v',name='새후보',vworld_x=127,vworld_y=37)]), patch('services.golf_public_data.fetch_public_golf_records',side_effect=RuntimeError('synthetic')):
                    result=updater.refresh_pool_dual('synthetic','synthetic','synthetic',force=True)
                self.assertEqual(result['count'],2)
                self.assertEqual(result['service'],1)
                self.assertEqual(result['candidate'],1)
                self.assertEqual(result['public_data']['status'],'warning')

    def test_ui_routing_sort_preserved(self):
        import subprocess
        p=Path('pages/6_골프장_추천.py')
        text=p.read_text(encoding='utf-8'); current=ast.parse(text)
        prior=ast.parse(subprocess.check_output(['git','show','HEAD:pages/6_골프장_추천.py']).decode('utf-8'))
        function=lambda tree: next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_condition_sort_key')
        self.assertEqual(ast.dump(function(current)),ast.dump(function(prior)))
        self.assertEqual(text.count('search_clubs = list(condition_search_clubs)'),2)
        self.assertIn('기본정보 확인 중',text)
        self.assertIn('page_clubs = filtered[start_idx:start_idx + 12]',text)


if __name__=='__main__': unittest.main()
