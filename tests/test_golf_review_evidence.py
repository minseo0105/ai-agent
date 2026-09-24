import copy
from datetime import date
import unittest
from services.golf_review_evidence import canonical, extract, summarize

TODAY=date(2026,9,24)
def source(author,label='wide',day='2026-06-01',scope='whole_course',status='human_reviewed'):
    return {'source':'https://'+author+'.test/post','author_key':author,'title':'시험골프 후기','published_at':day,'full_text_available':True,'content_hash':author,'observations':[{'dimension':'fairway','label':label,'scope':scope,'status':status,'reviewed_at':'2026-09-24','evidence':'페어웨이가 넓어요.'}]}
class ReviewEvidenceTests(unittest.TestCase):
    def test_candidate_never_becomes_consensus(self):
        result=summarize({'sources':[source('a',status='needs_review'),source('b',status='needs_review')]},TODAY)
        self.assertEqual(result['fairway']['status'],'insufficient')
    def test_independent_authors_and_conflict(self):
        rows=[source('a'),source('b')]
        self.assertEqual(summarize({'sources':rows},TODAY)['fairway']['status'],'supported')
        rows.append(source('c','narrow'))
        self.assertEqual(summarize({'sources':rows},TODAY)['fairway']['status'],'mixed')
    def test_same_author_counts_once(self):
        a=source('a');b=copy.deepcopy(a);b['source']+='2';b['content_hash']='second'
        self.assertEqual(summarize({'sources':[a,b]},TODAY)['fairway']['authors'],1)
    def test_date_unknown_future_expired_and_scope(self):
        rows=[source('a',day=''),source('b',day='2030-01-01'),source('c',day='2020-01-01'),source('d',scope='park_course')]
        self.assertEqual(summarize({'sources':rows},TODAY)['fairway']['authors'],0)
    def test_canonical_naver_identity(self):
        self.assertEqual(canonical('https://m.blog.naver.com/author/123?x=1'),canonical('https://blog.naver.com/PostView.naver?blogId=author&logNo=123'))
    def test_wrong_course_and_official_page_excluded(self):
        raw={'title':'다른클럽 후기','url':'https://a.test/post','content':'페어웨이가 넓다.'}
        self.assertIsNone(extract(raw,{'id':'x','name':'시험골프CC'},'2026-09-24'))
        raw['title']='시험골프CC 후기'
        self.assertIsNone(extract(raw,{'id':'x','name':'시험골프CC','official_url':'https://a.test'},'2026-09-24'))
    def test_negation_and_hole_remain_unreviewed(self):
        raw={'title':'시험골프CC 후기','url':'https://a.test/post','raw_content':'2026. 6. 1.\n페어웨이가 넓지는 않습니다.\n1번홀은 페어웨이가 넓어요.'}
        out=extract(raw,{'id':'x','name':'시험골프CC'},'2026-09-24')
        self.assertTrue(out['observations'])
        self.assertTrue(all(o['status']=='needs_review' for o in out['observations']))
        self.assertTrue(all(o['scope']=='needs_scope_review' for o in out['observations']))
    def test_body_date_not_publication(self):
        raw={'title':'시험골프CC 후기','url':'https://a.test/post','raw_content':'골프장 개장일은 2025. 1. 1.입니다.\n페어웨이가 넓다.'}
        self.assertEqual(extract(raw,{'id':'x','name':'시험골프CC'},'2026-09-24')['published_at'],'')
if __name__=='__main__':unittest.main()
