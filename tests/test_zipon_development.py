import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from services.supabase_auth import supabase_headers
from services import realestate_monitor as rm, development as dev, access
from services import development_collector as dc
with patch.object(rm,'init_db'):
    from api.realestate import TradeQuery, trades, DevelopmentQuery, development_search, SubscriptionQuery, subscriptions

class AuthTests(unittest.TestCase):
    def test_secret(self):
        self.assertNotIn('Authorization',supabase_headers('sb_secret_fake'))
        self.assertEqual(supabase_headers('sb_secret_fake')['apikey'],'sb_secret_fake')
    def test_legacy(self):
        self.assertEqual(supabase_headers('fake.jwt.key')['Authorization'],'Bearer fake.jwt.key')
    def test_public_rejected(self):
        with self.assertRaises(ValueError):supabase_headers('sb_publishable_fake')
    def test_monitor_wire(self):
        response=Mock(content=b'[]');response.json.return_value=[]
        with patch.object(rm,'_supabase_config',return_value=('https://example.invalid','sb_secret_fake')),patch.object(rm.requests,'request',return_value=response) as req:
            rm._remote_request('GET','alert_rules')
            self.assertNotIn('Authorization',req.call_args.kwargs['headers'])
    def test_access_wire(self):
        response=Mock();response.json.return_value=[]
        with patch.object(access,'_supabase',return_value=('https://example.invalid','sb_secret_fake')),patch('requests.get',return_value=response) as get,patch('requests.post',return_value=response) as post:
            access._remote_get('test');access._remote_put('test','value')
            for call in (get,post):self.assertNotIn('Authorization',call.call_args.kwargs['headers'])
    def test_sqlite_fallback(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(rm,'_supabase_config',return_value=None):
            root=Path(folder);rm.save_alert_rules(root,['서울 > 서초구'],['신규실거래'],5,60,[],['아파트'])
            self.assertEqual(len(rm.get_alert_rules(root)),1)

class CollectorTests(unittest.TestCase):
    def fixture(self,stage='조합설립인가'):
        return '<table><tr><td>1</td><td>서초구</td><td>재건축</td><td>방배 시험</td><td>방배동 1</td><td>'+stage+"""</td><td><a href="javascript:cafeOpenPopup('cafe123');">사업장</a></td></tr></table>"""
    def test_identity_provenance(self):
        r=dc.parse_page(self.fixture(),dc.SOURCES[-1])[0]
        self.assertEqual(r['external_id'],'cafe123');self.assertEqual(r['status'],'UNKNOWN')
        self.assertIsNone(r['stage']);self.assertEqual(r['stage_raw'],'조합설립인가')
        self.assertTrue(r['source']['is_official']);self.assertIsNone(r['geometry'])
    def test_change_hash_identity_stable(self):
        a=dc.parse_page(self.fixture(),dc.SOURCES[-1])[0];b=dc.parse_page(self.fixture('착공'),dc.SOURCES[-1])[0]
        self.assertEqual(a['project_id'],b['project_id']);self.assertNotEqual(a['source']['content_hash'],b['source']['content_hash'])
    def test_unchanged_collection_time(self):
        a=dc.parse_page(self.fixture(),dc.SOURCES[-1],'2026-01-01')[0];b=dc.parse_page(self.fixture(),dc.SOURCES[-1],'2026-02-01')[0]
        self.assertEqual(a['source']['content_hash'],b['source']['content_hash'])
    def test_cp949(self):
        self.assertEqual(len(dc.parse_page(self.fixture().encode('cp949'),dc.SOURCES[-1])),1)
    def test_rowspan(self):
        html='<table><tr><td rowspan="2">강동구</td><td>천호동 1</td><td>100</td></tr><tr><td>천호동 2</td><td>200</td></tr></table>'
        self.assertEqual(len(dc.parse_page(html,dc.SOURCES[0])),2)
    def test_no_centroid_geocode(self):
        r={'address':'서울특별시 서초구 방배동'}
        self.assertNotIn('location',dc.geocode(r,{},lambda _:dict(result_status='MATCHED',accuracy='LOCALITY',longitude=127,latitude=37,source_url='https://example.invalid')))
    def test_exact_geocode_cache(self):
        cache={};provider=Mock(return_value=dict(result_status='MATCHED',accuracy='PARCEL',longitude=127,latitude=37,source_url='https://example.invalid'))
        r=dc.geocode({'address':'서울 방배동 1'},cache,provider);dc.geocode({'address':'서울 방배동 1'},cache,provider)
        self.assertIn('location',r);provider.assert_called_once()
    def test_atomic_import_contract(self):
        request=Mock(side_effect=[[{'revision':2}],{'result':'changed'}]);r=dc.parse_page(self.fixture(),dc.SOURCES[-1])[0]
        dc.import_candidate(r,request)
        self.assertEqual(request.call_args.args,('POST','rpc/zipon_ingest_candidate'))
        self.assertEqual(request.call_args.kwargs['payload']['p_expected_revision'],2)
    def test_collection_failure_does_not_cancel(self):
        with patch.object(dc,'SOURCES',[dc.SOURCES[0]]):r=dc.collect(Mock(side_effect=TimeoutError()))
        self.assertEqual(r['records'],[]);self.assertFalse(r['runs'][0]['source_complete'])

class ApiTests(unittest.TestCase):
    def test_unavailable_fallback(self):
        with patch.object(rm,'_using_remote_db',return_value=True),patch.object(rm,'_remote_request',side_effect=RuntimeError('secret must not leak')):
            self.assertNotIn('secret',str(dev.search_projects(longitude=127,latitude=37)))
    def test_point_without_coordinates_unknown(self):
        with patch.object(dev,'search_projects') as search:
            rows=dev.attach_context([{'name':'trade','region':'방배동'}]);search.assert_not_called()
            self.assertEqual(rows[0]['development_context']['relation'],'UNKNOWN')
    def test_budget(self):
        with patch.object(dev,'search_projects',return_value={'nearby_projects':[]}) as search:
            dev.attach_context([{'longitude':127+i/100,'latitude':37} for i in range(20)],budget=3)
            self.assertEqual(search.call_count,3)
    def test_rpc_payload(self):
        with patch.object(rm,'_using_remote_db',return_value=True),patch.object(rm,'_remote_request',return_value=[{'relation':'NEARBY'}]) as request:
            self.assertEqual(dev.search_projects(longitude=127,latitude=37)['nearby_projects'][0]['relation'],'NEARBY')
            self.assertEqual(request.call_args.args,('POST','rpc/zipon_development_search'))
    def test_trades_survive_rpc_failure(self):
        q=TradeQuery(regions=['서울 > 서초구'],property_types=['아파트'],month='202609',include_development=True)
        with patch.object(rm,'fetch_trades_multi',return_value=([{'name':'A','latitude':37,'longitude':127,'property_type':'아파트'}],[])),patch.object(rm,'_using_remote_db',return_value=True),patch.object(rm,'_remote_request',side_effect=RuntimeError()):
            result=asyncio.run(trades(q))
        self.assertEqual(len(result['items']),1);self.assertEqual(result['items'][0]['development_context']['status'],'unavailable')
    def test_subscriptions_regression(self):
        rows=[{'name':'A','region':'서울','address':'서초구','status':'접수중'}]
        with patch('api.realestate._cached',return_value=rows):result=asyncio.run(subscriptions(SubscriptionQuery(regions=['서울 > 서초구'])))
        self.assertEqual(len(result['items']),1)
    def test_partial_coordinates_rejected(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):asyncio.run(development_search(DevelopmentQuery(longitude=127)))

if __name__=='__main__':unittest.main()
