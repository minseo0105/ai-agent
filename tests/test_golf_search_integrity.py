import unittest
from unittest.mock import patch
from services import golf_service as gs
from services.golf_pricing import team_fee, green_fee, fee_summary

class SearchIntegrityTests(unittest.TestCase):
    def test_quarantined_period_price_remains_reference_only(self):
        club={'pricing':{'fee_records':[{'day_type':'weekday','member_type':'nonmember','greenfee':100000,'validation_status':'needs_review'}]}}
        self.assertIsNone(green_fee(club,False))
        self.assertFalse(fee_summary(club)['is_current'])
    def test_facility_proof_and_readable_structured_value(self):
        club={'enrichment':{'facts':{'driving_range':{'available':True,'bays':5,'length_yd':135,'closed_weekday':'Wednesday'}}}}
        self.assertEqual(gs._official_facilities(club),[])
        club['field_evidence']={'enrichment.facts.driving_range':{'source_url':'https://club.test/','checked_at':'2026-09-25'}}
        card=gs._official_facilities(club)[0]
        self.assertEqual(card['value'],'5타석 · 135야드 · 수요일 휴무')
    def test_unsupported_requests_are_not_silently_ignored(self):
        for text in ('여주 2인 골프장', '야외연습장과 PAR3 있는 곳', '페어웨이 넓은 골프장', '둘이 라운딩'):
            with self.subTest(text=text):
                result=gs.ai_search(text, include_unknown=True)
                self.assertEqual(result['items'], [])
                self.assertEqual(result['applied'], [])
                self.assertTrue(result['unsupported_conditions'])
                self.assertIn('지원하지 않습니다', result['notice'])
    def test_missing_side_fee_is_not_zero(self):
        club={'operations':{'cart':{'fee_team':100000}}}
        with patch.object(gs,'green_fee',return_value=200000):
            self.assertIsNone(gs.estimate_per_person(club))
            club['operations']['caddie']={'fee_team':150000}
            self.assertEqual(gs.estimate_per_person(club),262500)
            club['operations']['caddie']={'fee_team':0}
            self.assertEqual(gs.estimate_per_person(club),225000)
    def test_expired_side_fee_not_revived_by_legacy(self):
        club={'operations':{'cart':{'fee_team':100000,'fresh_until':'2020-01-01'}},'fee':{'verified':True,'cart_team':100000}}
        self.assertIsNone(gs._known_team_fee(club,'cart'))
    def test_verified_legacy_fees_survive_empty_operation_placeholder(self):
        club={'operations':{'cart':{'fee_team':None},'caddie':{'mode':'unknown'}},'fee':{'verified':True,'weekday_green':100000,'cart_team':100000,'caddie_team':150000}}
        self.assertEqual(gs.estimate_per_person(club),162500)
    def test_explicit_free_and_unknown_are_distinct(self):
        self.assertEqual(team_fee({'operations':{'caddie':{'fee_team':0}}},'caddie'),0)
        self.assertIsNone(team_fee({'operations':{'caddie':{'fee_team':False}}},'caddie'))
        self.assertIsNone(team_fee({},'caddie'))
    def test_badge_uses_new_evidence_without_mutating_assessment(self):
        club={'precision_assessment':{'categories':{'cart':'missing'}},'operations':{'cart':{'fee_team':100000}}}
        self.assertEqual(gs._completeness_block(club)['items'][0]['status'],'partial')
        self.assertEqual(club['precision_assessment']['categories']['cart'],'missing')
    def test_detail_no_total_when_fee_unknown_or_historical(self):
        summary=dict(weekday=[200000,220000],weekend=None,unspecified=None,weekday_sessions={},weekend_sessions={},is_current=True,checked_at='',latest_notice_month='',source_url='')
        club={'operations':{'cart':{'fee_team':100000}}}
        with patch.object(gs,'fee_summary',return_value=summary):
            self.assertIsNone(gs._fee_block(club)['weekday_total'])
            self.assertIn('총액 계산 보류',gs._fee_block(club)['note'])
            club['operations']['caddie']={'fee_team':0}
            self.assertEqual(gs._fee_block(club)['weekday_total'],[225000,245000])
            summary['is_current']=False
            self.assertIsNone(gs._fee_block(club)['weekday_total'])

if __name__=='__main__':unittest.main()
