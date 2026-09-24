import unittest
from services import golf_service as gs

class SearchScopeTests(unittest.TestCase):
    def test_unsupported_regions_return_notice_without_results(self):
        for text in ['제주 주말 골프장','부산 골프장','광주광역시 골프장','전라도 골프장','경상남도 골프장']:
            with self.subTest(text=text):
                result=gs.ai_search(text)
                self.assertEqual(result['items'],[])
                self.assertIn('현재 추천 지원 지역이 아닙니다',result['notice'])
    def test_default_scope_is_not_nationwide(self):
        result=gs.ai_search('골프장 추천')
        self.assertEqual(result['parsed']['area'],'지원 지역 전체')
        self.assertNotIn('전국',result['applied'])
        self.assertIn('수도권·충청권·강원권',result['applied'])
        self.assertTrue(result['items'])
    def test_supported_city_stays_supported(self):
        result=gs.ai_search('여주 골프장')
        self.assertTrue(result['items'])
        self.assertFalse(result['notice'])
        self.assertEqual(result['parsed']['city'],'여주')
if __name__=='__main__':unittest.main()
