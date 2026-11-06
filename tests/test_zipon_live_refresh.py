"""Offline failure and policy tests. These do not claim production/live success."""
import copy
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from services.development_refresh import identity, decision, refresh, Database, RefreshError, validate_survey
from services.development_sources import discover_archive, validate_zip, labeled_dates, SourceError, OfficialHTTP, collect_notices
from services.development_stage import observation
from services.development_collector import fetch_source_pages, build_sources

PID='11111111-1111-5111-8111-111111111111'


def project(**overrides):
    return dict({'project_id':PID,'project_name':'테스트구역','sigungu':'강동구',
      'project_type':'RECONSTRUCTION','external_id':'abc','official_authority':'cleanup.seoul.go.kr',
      'revision':1,'validation_status':'NEEDS_REVIEW','stage_raw':'조합설립인가'},**overrides)


class SourceTests(unittest.TestCase):
    def test_notice_registration_date_is_not_a_notice_date(self):
        date=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).date().isoformat()
        http=Mock()
        http.text.side_effect=[f'<a href="/cleanup/bbs/vscr.do?bbs.bbsSn=12">사업 고시 등록일 : {date}</a>',
                              '<h1>공식 고시</h1><p>불명확한 첨부 문서</p>']
        result=collect_notices(http)
        self.assertTrue(result['source_complete'])
        self.assertEqual(result['items'][0]['date_meaning'],'BOARD_REGISTRATION_ONLY')
        self.assertNotIn('notice_date',result['items'][0])

    def test_access_denial_is_not_followed_or_retried(self):
        session=Mock();session.request.return_value=Mock(status_code=302,headers={'Location':'https://www.seoul.go.kr/common/errorAccess.html'})
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(SourceError,'SOURCE_ACCESS_DENIED'):
                OfficialHTTP(folder,session=session).get('https://news.seoul.go.kr/source')
        self.assertEqual(session.request.call_count,1)
    def test_filtered_row_count_does_not_truncate_official_pagination(self):
        source=build_sources(['강동구'])[-1]
        rows='<table>'+''.join(f'<tr><td>강동구</td><td>재건축</td><td>사업{i}</td><td>고덕동 1</td><td>조합설립인가</td></tr>' for i in range(85))+'</table>'
        next_link='<a href="/cleanup/bsnssttus/lscrMainIndx.do?cpage=2&pageSize=100">2</a>'
        second='<table><tr><td>강동구</td><td>재건축</td><td>마지막사업</td><td>고덕동 2</td><td>조합설립인가</td></tr></table>'
        def response(html):
            r=Mock();r.content=html.encode();return r
        fetch=Mock(side_effect=[response(rows+next_link),response(second)])
        pages=list(fetch_source_pages(source,fetch))
        self.assertEqual(len(pages),2);self.assertEqual(pages[-1][2],None)
    def test_discovery_uses_actual_form_and_seq(self):
        html='''<form name="frmFile"><input name="infId" value="OA-22712"><input name="infSeq" value="1"></form>
        <script>document.frmFile.action="//datafile.seoul.go.kr/official-download";</script>
        <a title="UQ120_202602.zip" href="javascript:downloadFile('4');"></a>
        <a title="UQ120_202609.zip" href="javascript:downloadFile('5');"></a>'''
        result=discover_archive(html)
        self.assertEqual(result['form']['seq'],'5')
        self.assertEqual(result['download_url'],'https://datafile.seoul.go.kr/official-download')
        with self.assertRaises(SourceError):
            discover_archive(html.replace('datafile.seoul.go.kr','evil.example'))

    def test_html_and_incomplete_or_unsafe_zip_refused(self):
        with self.assertRaises(SourceError):validate_zip(b'<html>error</html>')
        for missing in (True,False):
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as bundle:
                for e in ('shp','dbf','shx') + (() if missing else ('prj',)):
                    bundle.writestr('UQ120.'+e,b'fixture')
                if not missing:bundle.writestr('../escape',b'unsafe')
            with self.assertRaises(SourceError):validate_zip(out.getvalue())

    def test_dates_keep_meanings_and_never_guess_short_year(self):
        dates=labeled_dates('<table><tr><th>고시일</th><td>2026.10.01</td></tr><tr><th>기준일</th><td>26.10.01</td></tr></table>')
        self.assertEqual(dates,{'notice_date':'2026-10-01','source_date':None})
        with self.assertRaises(SourceError):
            labeled_dates('<dt>고시일</dt><dd>2026-01-01</dd><dt>고시일</dt><dd>2026-02-01</dd>')

    def test_redirect_to_unofficial_host_refused(self):
        session=Mock();r=Mock(status_code=302,headers={'Location':'https://evil.example/file'})
        session.request.return_value=r
        with tempfile.TemporaryDirectory() as folder:
            http=OfficialHTTP(folder,session=session,sleeper=lambda _:None)
            with self.assertRaises(SourceError):http.get('https://data.seoul.go.kr/start')
        self.assertEqual(session.request.call_count,1)

    def test_network_retry_is_bounded(self):
        session=Mock();session.request.side_effect=requests.Timeout()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(SourceError):OfficialHTTP(folder,session=session,sleeper=lambda _:None).get('https://data.seoul.go.kr/start')
        self.assertEqual(session.request.call_count,3)


class PolicyTests(unittest.TestCase):
    def test_schema_drift_and_invalid_crs_never_reach_boundary_apply(self):
        survey={'outside_seoul':0,'converted_to_epsg4326':1,'schema_fingerprint':'new',
                'schema':{'name':{'used_for_matching':True},'district':{'used_for_matching':True}}}
        with self.assertRaisesRegex(SourceError,'SHP_SCHEMA_CHANGED'):
            validate_survey(survey,{'schema_fingerprint':'old'})
        with self.assertRaisesRegex(SourceError,'CRS_SANITY_FAILED'):
            validate_survey(dict(survey,outside_seoul=1))
    def test_canonical_id_is_preserved_by_official_identifier(self):
        old=project();new=project(project_id='22222222-2222-5222-8222-222222222222')
        row,reason=identity(new,[old],[new])
        self.assertEqual(row['project_id'],PID);self.assertIsNone(reason)

    def test_name_overlap_cannot_merge_or_insert(self):
        old=project(project_name='마천2',external_id='one')
        new=project(project_id='22222222-2222-5222-8222-222222222222',project_name='마천2재정비촉진구역',external_id='two')
        self.assertEqual(identity(new,[old],[new])[1],'DUPLICATE_SUSPECTED')

    def test_regression_and_verified_replacement_require_review(self):
        obs={'stage':'COMMITTEE','stage_raw':'추진위원회승인'}
        self.assertEqual(decision(project(),project(),obs),'STAGE_REGRESSION')
        obs={'stage':'IMPLEMENTATION_APPROVED','stage_raw':'사업시행인가'}
        self.assertEqual(decision(project(validation_status='VERIFIED'),project(),obs),'VERIFIED_PROTECTED')
        self.assertIsNone(decision(project(),project(),obs))

    def test_live_master_beats_static_catalog(self):
        with patch('services.development_stage.catalog',return_value={PID:{'list_stage':{'raw_stage':'착공'}}}):
            self.assertEqual(observation(project(stage_mapping_version='zipon-refresh-policy-v1')),(None,{}))

    def test_no_shared_db_fallback_and_write_gate(self):
        with patch.dict('os.environ',{'SUPABASE_URL':'https://other.example','SUPABASE_SERVICE_ROLE_KEY':'secret'},clear=True):
            with self.assertRaises(RefreshError):Database()
        with patch.dict('os.environ',{'ZIPON_IMPORT_SUPABASE_URL':'https://nnxtkvjpzqqhjlgnprzo.supabase.co','ZIPON_IMPORT_SUPABASE_KEY':'test'},clear=True):
            with self.assertRaises(RefreshError):Database(apply=True)


class RunnerTests(unittest.TestCase):
    def test_failed_source_never_marks_unseen_project_missing_and_finishes_partial(self):
        db=Mock()
        db.rows.side_effect=lambda table,*a,**k: [project()] if table=='development_projects' else [
            {'source_id':'source','project_id':PID,'source_url':'https://cleanup.seoul.go.kr/list','content_hash':'a'*64}]
        http=Mock(objects=[]);http.text.side_effect=SourceError('SOURCE_HTTP_403')
        collection={'records':[],'districts':['강동구'],'runs':[{'source':'cleanup','source_url':'https://cleanup.seoul.go.kr/list',
            'status':'FAILED','source_complete':False,'errors':['SOURCE_HTTP_403']}]}
        with tempfile.TemporaryDirectory() as folder,patch('services.development_refresh.collector.collect',return_value=collection):
            report=refresh(db=db,http=http,directory=folder,shp=False)
            self.assertEqual(report['status'],'PARTIAL');self.assertEqual(report['reviews'],[])
            self.assertTrue(report['finished_at']);db.request.assert_not_called()

    def test_db_failure_still_writes_safe_failed_report(self):
        db=Mock();db.rows.side_effect=RefreshError('DATABASE_REQUEST_FAILED')
        with tempfile.TemporaryDirectory() as folder:
            result=refresh(db=db,directory=folder,shp=False)
            self.assertEqual(result['status'],'FAILED')
            self.assertTrue(Path(folder,'report.json').is_file())

    def test_successful_notice_collection_does_not_pollute_the_collectors_run_list(self):
        # 보고서 전용 항목(공지·모아 취소)에는 source_url이 없다. 이것이 수집기의
        # runs 목록에 섞이면 완료된 소스 URL 집합을 만들다가 KeyError가 난다.
        db=Mock()
        db.rows.side_effect=lambda table,*a,**k: []
        runs=[{'source':'seoul_moa','source_url':'https://cleanup.seoul.go.kr/moa','status':'FAILED',
               'source_complete':False,'errors':['SOURCE_ACCESS_DENIED']},
              {'source':'cleanup_11740','source_url':'https://cleanup.seoul.go.kr/list','status':'SUCCEEDED',
               'source_complete':True,'errors':[]}]
        collection={'records':[],'districts':['강동구'],'runs':runs}
        notices={'source':'official_notices','status':'SUCCEEDED','source_complete':True,
                 'scope':'NEW_IDS_OR_LAST_30_DAYS','errors':[],'items':[],'seen':['1'],'target_aliases':[]}
        with tempfile.TemporaryDirectory() as folder,\
             patch('services.development_refresh.collector.collect',return_value=collection),\
             patch('services.development_refresh.collect_moa_cancellations',return_value=[]),\
             patch('services.development_refresh.collect_notices',return_value=notices):
            report=refresh(db=db,http=Mock(objects=[]),directory=folder,shp=False)
            # 기록되는 오류는 소스 자체의 접근 거부 하나뿐이다(코드 오류 KeyError가 아니다).
            self.assertEqual(report['errors'],[{'source':'seoul_moa','code':'SOURCE_ACCESS_DENIED'}])
            self.assertEqual(report['status'],'PARTIAL')  # 접근 거부는 실패가 아니라 부분 성공
            self.assertEqual([r['source'] for r in runs],['seoul_moa','cleanup_11740'])
            self.assertIn('official_notices',[s['source'] for s in report['sources']])
            self.assertIn('moa_official_cancellations',[s['source'] for s in report['sources']])

    def test_unexpected_error_report_names_the_failing_line_and_missing_key(self):
        # 예상하지 못한 오류가 'KeyError' 한 단어로만 남으면 원인을 찾을 수 없다.
        db=Mock();db.rows.return_value=[]
        def broken(*args,**kwargs):
            return {'source':{}}['content_hash']
        with tempfile.TemporaryDirectory() as folder,patch('services.development_refresh.collector.collect',side_effect=broken):
            result=refresh(db=db,http=Mock(objects=[]),directory=folder,shp=False)
            self.assertEqual(result['status'],'FAILED')
            error=result['errors'][0]
            self.assertEqual(error['code'],'KeyError')
            self.assertEqual(error['key'],"'content_hash'")
            self.assertRegex(error['where'],r'^test_zipon_live_refresh\.py:\d+ in broken$')
            saved=json.loads(Path(folder,'report.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['errors'][0]['where'],error['where'])

    def test_expected_errors_keep_their_plain_code_without_location(self):
        db=Mock();db.rows.side_effect=RefreshError('DATABASE_REQUEST_FAILED')
        with tempfile.TemporaryDirectory() as folder:
            result=refresh(db=db,directory=folder,shp=False)
            self.assertEqual(result['errors'],[{'code':'DATABASE_REQUEST_FAILED'}])

    def test_concurrent_apply_refused_before_collection_or_project_write(self):
        db=Mock();db.request.return_value=False
        with tempfile.TemporaryDirectory() as folder,patch('services.development_refresh.collector.collect') as collect:
            result=refresh(db=db,directory=folder,apply=True,shp=False)
            self.assertEqual(result['status'],'FAILED');collect.assert_not_called()
            self.assertEqual(db.request.call_count,1)


if __name__=='__main__':unittest.main()
