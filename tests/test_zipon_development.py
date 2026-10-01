import asyncio
import json
import tempfile
import unittest
import uuid
from collections import Counter
from urllib.parse import parse_qsl, urlsplit
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
        # 좌표 채택은 서울 bbox와 자치구 일치까지 통과해야 하므로 fixture도 그 모양이다.
        cache={};provider=Mock(return_value=dict(result_status='MATCHED',accuracy='PARCEL',longitude=127.0324,latitude=37.4837,source_url='https://example.invalid',address_elements={'SIDO':'서울특별시','SIGUGUN':'서초구'}))
        record={'address':'서울 방배동 1','sigungu':'서초구'}
        r=dc.geocode(record,cache,provider);dc.geocode(record,cache,provider)
        self.assertIn('location',r);provider.assert_called_once()
        self.assertEqual(r['location_sigungu'],'서초구')
    def test_atomic_import_contract(self):
        request=Mock(side_effect=[[{'revision':2}],{'result':'changed'}]);r=dc.parse_page(self.fixture(),dc.SOURCES[-1])[0]
        dc.import_candidate(r,request)
        self.assertEqual(request.call_args.args,('POST','rpc/zipon_ingest_candidate'))
        self.assertEqual(request.call_args.kwargs['payload']['p_expected_revision'],2)
    def test_collection_failure_does_not_cancel(self):
        with patch.object(dc,'SOURCES',[dc.SOURCES[0]]):r=dc.collect(Mock(side_effect=TimeoutError()))
        self.assertEqual(r['records'],[]);self.assertFalse(r['runs'][0]['source_complete'])

class RegionMasterTests(unittest.TestCase):
    """서울 25개 자치구 코드는 REGION_LAWD 하나에서만 온다."""
    def test_single_source_of_truth(self):
        self.assertEqual(dc.SIGNGU_CODE_SOURCE,'services.realestate_monitor.REGION_LAWD')
        expected={k.split(' > ',1)[1]:v for k,v in rm.REGION_LAWD.items() if k.startswith('서울 > ')}
        self.assertEqual(dc.SEOUL_SIGNGU_CODE,expected);self.assertEqual(len(dc.SEOUL_DISTRICTS),25)
    def test_codes_are_five_digit_seoul_and_unique(self):
        codes=list(dc.SEOUL_SIGNGU_CODE.values())
        self.assertTrue(all(len(c)==5 and c.startswith('11') and c.isdigit() for c in codes))
        self.assertEqual(len(set(codes)),25)
    def test_trade_lawd_and_signgu_code_agree_for_loaded_districts(self):
        # 재사용 전제: 실거래 LAWD_CD와 정보몽땅 signguCode가 같은 체계라는 확인.
        for district,code in {'강동구':'11740','송파구':'11710','서초구':'11650'}.items():
            self.assertEqual(rm.REGION_LAWD['서울 > '+district],code)
            self.assertEqual(dc.SEOUL_SIGNGU_CODE[district],code)
            self.assertIn('signguCode='+code,[s['url'] for s in dc.build_sources(district)][-1])
    def test_no_duplicate_region_dictionary(self):
        source=Path('services/development_collector.py').read_text(encoding='utf-8')
        self.assertNotIn("'강동구': '11740', '송파구': '11710', '서초구': '11650'",source)
        self.assertEqual(source.count('11200'),0)  # 25개 코드를 다시 적지 않는다

class CollectorScopeTests(unittest.TestCase):
    """지역 선택이 수집 범위를 결정하고, 기본값은 기존 세 구 그대로다."""
    def test_default_scope_unchanged(self):
        self.assertEqual(dc.DISTRICTS,{'강동구':'11740','송파구':'11710','서초구':'11650'})
        self.assertEqual([s['id'] for s in dc.SOURCES],
            ['seoul_moa','seoul_shintong_redevelopment','seoul_shintong_reconstruction',
             'cleanup_11740','cleanup_11710','cleanup_11650'])
        self.assertEqual(dc.SOURCES[-1]['kind'],'directory')
    def test_single_district(self):
        sources=dc.build_sources('성동구')
        self.assertEqual([s['id'] for s in sources][-1:],['cleanup_11200'])
        self.assertEqual(len(sources),len(dc.CITYWIDE_SOURCES)+1)
    def test_multiple_districts(self):
        sources=dc.build_sources(['성동구','마포구','용산구'])
        self.assertEqual([s['id'] for s in sources if s['kind']=='directory'],
                         ['cleanup_11200','cleanup_11440','cleanup_11170'])
    def test_all_seoul_is_opt_in_not_the_default(self):
        self.assertEqual(len(dc.build_sources(dc.SEOUL_DISTRICTS)),len(dc.CITYWIDE_SOURCES)+25)
        self.assertEqual(len(dc.SOURCES),len(dc.CITYWIDE_SOURCES)+3)
    def test_region_label_form_accepted(self):
        self.assertEqual(dc.normalize_districts(['서울 > 성동구','성동구']),('성동구',))
    def test_unknown_district_refused(self):
        with self.assertRaises(dc.UnknownDistrict):dc.normalize_districts(['성동'])
        with self.assertRaises(dc.UnknownDistrict):dc.normalize_districts([])
    def test_gyeonggi_not_collectable(self):
        # 경기/전국 확장은 이 단계가 아니다. 코드 체계도 수집원도 다르다.
        with self.assertRaises(dc.UnknownDistrict):dc.normalize_districts(['하남시'])
        with self.assertRaises(dc.UnknownDistrict):dc.normalize_districts(['경기 > 하남시'])
    def test_rows_outside_scope_are_dropped(self):
        html='<table><tr><td>1</td><td>성동구</td><td>재건축</td><td>성동 시험</td><td>행당동 1</td><td>착공</td></tr></table>'
        self.assertEqual(dc.parse_page(html,dc.SOURCES[-1]),[])
        rows=dc.parse_page(html,dc.build_sources('성동구')[-1])
        self.assertEqual(rows[0]['sigungu'],'성동구')
    def test_collect_uses_requested_scope(self):
        fetch=Mock(side_effect=TimeoutError())
        r=dc.collect(fetch,districts=['성동구'])
        self.assertEqual(r['districts'],['성동구'])
        self.assertEqual(len(r['runs']),len(dc.CITYWIDE_SOURCES)+1)

class DirectoryPaginationTests(unittest.TestCase):
    """100건이 넘는 자치구가 조용히 잘리지 않고, 무한 loop도 돌지 않는지."""
    def page(self,start,count,district='성동구'):
        rows=''.join('<tr><td>'+str(start+i)+'</td><td>'+district+'</td><td>재건축</td>'
                     '<td>'+district+' 시험 '+str(start+i)+'</td><td>행당동 '+str(start+i)+'</td>'
                     '<td>착공</td><td><a href="javascript:cafeOpenPopup(\'id'+str(start+i)+'\');">지도</a></td></tr>'
                     for i in range(count))
        return '<table>'+rows+'</table>'
    def transport(self,pages):
        """cpage를 읽어 해당 장을 돌려주는 로컬 응답."""
        calls=[]
        def fetch(url,timeout=None):
            query=dict(parse_qsl(urlsplit(url).query))
            page=int(query.get('cpage',1))
            calls.append(page)
            body=pages(page)
            return Mock(url=url,content=body.encode('utf-8'),raise_for_status=Mock())
        return fetch,calls
    def source(self):
        return next(s for s in dc.build_sources('성동구') if s['kind']=='directory')
    def test_page_url_only_changes_the_page_number(self):
        url=dc.page_url(self.source()['url'],'cpage',3)
        self.assertIn('cpage=3',url);self.assertIn('pageSize=100',url)
        self.assertIn('scupBsnsSttus.signguCode=11200',url)
    def test_a_district_over_one_page_is_fully_collected(self):
        full={1:self.page(1,100),2:self.page(101,100),3:self.page(201,30)}
        fetch,calls=self.transport(lambda p:full.get(p,'<table></table>'))
        r=dc.collect(fetch,districts=['성동구'],sources=[self.source()])
        self.assertEqual(calls,[1,2,3])
        self.assertEqual(len(r['records']),230)
        self.assertEqual(r['runs'][0]['pages_fetched'],3)
        self.assertTrue(r['runs'][0]['source_complete'])
        self.assertEqual(r['runs'][0]['status'],'SUCCEEDED')
    def test_a_single_short_page_stops_immediately(self):
        fetch,calls=self.transport(lambda p:self.page(1,12))
        r=dc.collect(fetch,districts=['성동구'],sources=[self.source()])
        self.assertEqual(calls,[1]);self.assertEqual(len(r['records']),12)
    def test_a_site_ignoring_cpage_does_not_loop(self):
        # 같은 장을 계속 주는 응답. 가장 현실적인 실패 방식이다.
        fetch,calls=self.transport(lambda p:self.page(1,100))
        r=dc.collect(fetch,districts=['성동구'],sources=[self.source()])
        self.assertEqual(calls,[1,2])
        self.assertIn('DUPLICATE_PAGE',r['runs'][0]['errors'])
        self.assertEqual(len(r['records']),100)
        self.assertFalse(r['runs'][0]['source_complete'])
    def test_new_document_with_no_new_rows_stops(self):
        # 문서는 매번 다르지만(순번 열이 바뀜) 사업은 그대로인 경우.
        fetch,calls=self.transport(lambda p:self.page(1,100).replace('<table>','<table data-p="'+str(p)+'">'))
        r=dc.collect(fetch,districts=['성동구'],sources=[self.source()])
        self.assertEqual(calls,[1,2])
        self.assertIn('NO_NEW_ROWS',r['runs'][0]['errors'])
    def test_truncation_is_reported_not_hidden(self):
        fetch,calls=self.transport(lambda p:self.page(1+(p-1)*100,100))
        r=dc.collect(fetch,districts=['성동구'],sources=[self.source()])
        self.assertEqual(len(calls),dc.MAX_DIRECTORY_PAGES)
        self.assertIn('PAGE_LIMIT_REACHED',r['runs'][0]['errors'])
        self.assertEqual(r['runs'][0]['status'],'PARTIAL')
    def test_citywide_sources_are_not_paginated(self):
        fetch,calls=self.transport(lambda p:self.page(1,100))
        dc.collect(fetch,districts=['성동구'],sources=[dc.build_sources('성동구')[0]])
        self.assertEqual(len(calls),1)

class GeocodeSigunguTests(unittest.TestCase):
    """서울 bbox만으로는 통과하지 못한다. 사업 자치구와 응답 자치구가 같아야 한다."""
    def matched(self,**over):
        base=dict(result_status='MATCHED',accuracy='PARCEL',longitude=127.0369,latitude=37.5633,
                  source_url='https://example.invalid',
                  address_elements={'SIDO':'서울특별시','SIGUGUN':'성동구'})
        base.update(over);return base
    def record(self,district='성동구'):
        return {'address':'서울특별시 '+district+' 행당동 1','sigungu':district}
    def test_matching_district_accepted(self):
        r=dc.geocode(self.record(),{},lambda _:self.matched())
        self.assertIn('location',r);self.assertEqual(r['location_sigungu'],'성동구')
    def test_mismatched_district_rejected(self):
        r=dc.geocode(self.record('마포구'),{},lambda _:self.matched())
        self.assertNotIn('location',r)
        self.assertIn('GEOCODE_SIGUNGU_MISMATCH',r['location_review'])
    def test_outside_seoul_rejected_even_when_inside_korea(self):
        r=dc.geocode(self.record(),{},lambda _:self.matched(longitude=127.2,latitude=37.0,
            address_elements={'SIDO':'서울특별시','SIGUGUN':'성동구'}))
        self.assertIn('OUTSIDE_SEOUL_BBOX',r['location_review'])
    def test_unreadable_district_is_review_not_pass(self):
        r=dc.geocode(self.record(),{},lambda _:self.matched(address_elements=None))
        self.assertIn('GEOCODE_SIGUNGU_UNVERIFIABLE',r['location_review'])
    def test_district_read_from_returned_address_when_no_elements(self):
        r=dc.geocode(self.record(),{},lambda _:self.matched(address_elements=None,
            matched_address='서울특별시 성동구 행당동 1'))
        self.assertIn('location',r)
    def test_axis_swapped_rejected(self):
        r=dc.geocode(self.record(),{},lambda _:self.matched(longitude=37.5633,latitude=127.0369))
        self.assertIn('OUTSIDE_KOREA_BBOX',r['location_review'])
    def test_rejection_reasons_are_kept_not_silently_dropped(self):
        r=dc.geocode(self.record('마포구'),{},lambda _:self.matched())
        self.assertTrue(r['location_review']);self.assertIsNone(r.get('location'))

class ExistingDataRegressionTests(unittest.TestCase):
    """이미 적재된 130건의 identity가 확대 후에도 그대로여야 한다."""
    BASELINE=Path('data/development/lifecycle_audit_20260929.json')
    CAPTURE=Path('data/development/pilot_20260927.json')
    def load(self,path):
        return json.loads(path.read_text(encoding='utf-8'))
    def test_baseline_counts(self):
        rows=self.load(self.BASELINE)['items']
        self.assertEqual(len(rows),130)
        self.assertEqual(Counter(r['district'] for r in rows),
                         Counter({'서초구':56,'강동구':40,'송파구':34}))
    def test_identity_reproduced_for_every_existing_row(self):
        """캡처된 공식 근거를 지금 코드로 다시 통과시켜도 같은 project_id가 나온다."""
        capture=self.load(self.CAPTURE)
        by_url={s['url']:s for s in dc.build_sources(dc.SEOUL_DISTRICTS)}
        regenerated=set()
        for record in capture['records']:
            source=by_url[record['field_evidence']['source_url']]
            identity=('cleanup:'+record['external_id'] if record['external_id']
                      else f"{source['id']}:{record['sigungu']}:{record['project_name']}")
            regenerated.add(str(uuid.uuid5(uuid.NAMESPACE_URL,identity)))
        existing={r['project_id'] for r in self.load(self.BASELINE)['items']}
        self.assertEqual(existing-regenerated,set())
    def test_expanding_scope_does_not_change_pilot_identities(self):
        html=('<table><tr><td>58</td><td>강동구</td><td>재건축</td>'
              '<td>고덕주공2단지아파트 주택재건축정비사업조합</td><td>고덕동 212</td>'
              '<td>조합청산</td><td>3004건</td><td>-</td><td>-</td>'
              '<td><a href="javascript:cafeOpenPopup(\'in814VyA\');">사업장 지도</a></td></tr></table>')
        pick=lambda scope:next(s for s in dc.build_sources(scope) if s['id']=='cleanup_11740')
        narrow=dc.parse_page(html,pick('강동구'))[0]
        wide=dc.parse_page(html,pick(dc.SEOUL_DISTRICTS))[0]
        self.assertEqual(narrow['project_id'],wide['project_id'])
        self.assertEqual(narrow['source']['source_url'],wide['source']['source_url'])
        self.assertEqual(narrow['source']['content_hash'],wide['source']['content_hash'])
        self.assertIn(narrow['project_id'],{r['project_id'] for r in self.load(self.BASELINE)['items']})

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
