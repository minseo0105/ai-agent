import json
from pathlib import Path
import unittest
from unittest.mock import patch
from services import development_stage as stage
from services import development_presentation as presentation

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://cleanup.seoul.go.kr/assc/scrin-bbs/execute.do?cafeId=example'

def page(current='관리처분인가'):
    return f'''<div class="progress-cont"><div class="progress"><div class="step">현재단계</div><p>{current}</p></div>
      <ul><li><div class="txt">조합설립인가</div><div class="date">2015.01.23</div></li>
      <li class="active"><div class="txt">관리처분인가</div><div class="date">25.07.25</div></li>
      <li><div class="txt">철거신고</div></li></ul></div>'''

def evidence():
    return dict(stage.parse_progress(page()), stage_verified_level='OFFICIAL_DETAIL_VERIFIED',
                evidence_url=URL,content_hash='a'*64,fetched_at='2026-09-27T00:00:00Z')

class OfficialStageTests(unittest.TestCase):
    def test_rpc_metadata_is_hydrated_with_one_read_only_get(self):
        from services import development as dev
        pid='02b9c94c-8b6c-5297-affa-1e827181afb0'
        with patch.object(dev.rm,'_remote_request',return_value=[{'project_id':pid,'stage_raw':'철거신고'}]) as request:
            rows=dev.stage_metadata([{'project_id':pid,'project_stage':None}])
        self.assertEqual(rows[0]['stage_raw'],'철거신고')
        request.assert_called_once()
        self.assertEqual(request.call_args.args,('GET','development_projects'))

    def test_current_and_dates_are_read_from_official_section(self):
        parsed=stage.parse_progress(page())
        self.assertEqual(parsed['current_stage'],'관리처분인가')
        self.assertEqual([m['stage_date'] for m in parsed['milestones']],['2015-01-23','25.07.25',None])
        self.assertEqual([m['is_current'] for m in parsed['milestones']],[False,True,False])

    def test_invalid_date_and_century_are_never_inferred(self):
        parsed=stage.parse_progress(page().replace('2015.01.23','2015.02.31'))
        self.assertIsNone(parsed['milestones'][0]['stage_date'])
        self.assertEqual(parsed['milestones'][1]['date_precision'],'SOURCE_SHORT_YEAR')

    def test_conflicting_current_marker_is_not_verified(self):
        self.assertIsNone(stage.parse_progress(page('철거신고'))['current_stage'])

    def test_menu_or_snippet_is_not_current_stage(self):
        self.assertIsNone(stage.parse_progress('<p>관리처분인가</p>')['current_stage'])

    def test_sequence_is_from_this_business_not_global_taxonomy(self):
        view=stage.stage_view(evidence())
        self.assertEqual(view['timeline']['steps'],['조합설립인가','관리처분인가','철거신고'])
        self.assertEqual(view['timeline']['current_index'],1)

    def test_no_detail_promotion_without_source(self):
        self.assertIsNone(stage.stage_view(dict(evidence(),evidence_url='https://example.com')))
        self.assertIsNone(stage.stage_view(dict(evidence(),stage_verified_level='OFFICIAL_LIST_MAPPED')))

    def test_official_identity_is_required_before_frame_fetch(self):
        target={'detail_url':'https://cleanup.seoul.go.kr/cafe/mainIndx.do?cafeUrl=example','project_name':'A1구역'}
        calls=[]
        def fetch(url):
            calls.append(url)
            return '<h1>A2구역</h1><iframe id="contentFrame" src="'+URL+'"></iframe>'
        self.assertEqual(stage.collect(target,fetch)['result_status'],'IDENTITY_OR_FRAME_UNRESOLVED')
        self.assertEqual(len(calls),1)

    def test_detail_wins_but_original_row_is_unchanged(self):
        row={'project_id':'test','stage_raw':'조합설립인가'}
        with patch.object(stage,'catalog',return_value={'test':evidence()}):
            p=presentation.present_project(row)
        self.assertEqual(row['stage_raw'],'조합설립인가')
        self.assertEqual(p['stage']['label'],'관리처분인가')
        self.assertEqual(p['stage_verified_level'],'OFFICIAL_DETAIL_VERIFIED')
        self.assertIn('권리배분',p['stage_description'])
        self.assertEqual(p['stage_history'][0]['stage_date'],'2015-01-23')

    def test_newer_stored_detail_is_protected(self):
        old=evidence();new=dict(evidence(),current_stage='철거신고',fetched_at='2026-10-01')
        with patch.object(stage,'catalog',return_value={'test':old}):
            detail,_=stage.observation({'project_id':'test','field_evidence':{'official_stage':new}})
        self.assertEqual(detail['current_stage'],'철거신고')

    def test_list_only_and_missing_remain_distinct(self):
        p=presentation.present_project({'stage_raw':'착공신고'})
        self.assertEqual(p['stage_verified_level'],'OFFICIAL_LIST_MAPPED')
        self.assertEqual(p['stage_timeline']['total'],1)
        self.assertEqual(presentation.present_project({})['stage']['label'],'세부 진행단계 확인 중')

    def test_enum_rpc_stage_is_not_rendered_as_raw_enum_label(self):
        p=presentation.present_project({'project_stage':'ASSOCIATION_APPROVED'})
        self.assertEqual(p['stage']['label'],'조합설립 인가')

    def test_mobile_and_desktop_have_accessible_distinct_layouts(self):
        source=(ROOT/'web/src/components/realestate/StageTimeline.tsx').read_text(encoding='utf-8')
        self.assertIn('sm:hidden',source)
        self.assertIn('sm:block',source)
        self.assertIn('aria-current',source)
        card=(ROOT/'web/src/components/realestate/DevelopmentCard.tsx').read_text(encoding='utf-8')
        self.assertIn('공식 진행이력',card)
        for raw in ('NEEDS_REVIEW','OFFICIAL_LIST_MAPPED','UNKNOWN'):
            self.assertNotIn(raw,card)

    def test_real_collection_counts_and_catalog_match_without_db(self):
        report=json.loads((ROOT/'data/development/stage_reconciliation_20260927.json').read_text(encoding='utf-8'))
        catalog=stage.catalog()
        self.assertEqual(len(catalog),130)
        self.assertEqual(sum(stage.stage_view(v) is not None for v in catalog.values()),report['coverage']['direct_detail'])
        self.assertFalse(report['coverage']['db_write'])

    def test_all_130_rpc_unknown_placeholders_preserve_known_stage(self):
        for pid in stage.catalog():
            result=presentation.present_project({'project_id':pid,'project_stage':'UNKNOWN',
                                                'normalized_stage':'UNKNOWN','stage_raw':'  '})
            self.assertNotEqual(result['stage']['label'],'세부 진행단계 확인 중',pid)

    def test_shinbanpo25_has_independent_official_identity_and_evidence(self):
        entry=stage.catalog()['0164b2b0-1b21-51e3-8b8d-f97bda852a18']
        self.assertEqual(entry['cafe_id'],'650900000613q27')
        self.assertTrue(all(entry['identity_evidence']['identity_checks'].values()))
        self.assertIn('61-1',entry['identity']['address'])
        self.assertIsNotNone(stage.stage_view(entry))
        self.assertIn('current_stage_evidence',entry)
        self.assertIn('milestone_evidence',entry)

if __name__=='__main__':
    unittest.main()
