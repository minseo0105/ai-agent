import copy
from datetime import date
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.golf_import_policy import apply_item, trusted
from services.golf_pricing import green_fee, fee_summary, team_fee

TODAY='2026-09-24'
def evidence(**kw):
    return {'source_url':'https://club.test/fees','quote':'카트비 100,000원','reviewed':True,'condition':'',**kw}
def item(**ex):
    return {'id':'club','name':'Club','observed_at':TODAY,'review_method':'human_official_source','extraction':ex}

class ImportPolicyTests(unittest.TestCase):
    def test_identical_greenfees_do_not_create_conflicts(self):
        r={};payload=item(green_fees=[evidence(customer='nonmember',holes=18,price_krw=150000,day='weekday',session='all')])
        apply_item(r,payload,TODAY)
        before=copy.deepcopy(r)
        self.assertEqual(apply_item(r,payload,TODAY),([],[]))
        self.assertEqual(r,before)

    def test_fill_preserves_other_fields_and_provenance(self):
        r={'id':'club','phone':'031-111-2222','operations':{'cart':{'type':'electric'}}}
        apply_item(r,item(cart_fee=evidence(fee_team_krw=100000)),TODAY)
        self.assertEqual(r['operations']['cart']['fee_team'],100000)
        self.assertEqual(r['operations']['cart']['type'],'electric')
        self.assertEqual(r['field_evidence']['operations.cart.fee_team']['source_url'],'https://club.test/fees')
        self.assertEqual(r['sources'][0]['fields'],['operations.cart.fee_team'])
        self.assertEqual(r['enrichment']['history'][0]['previous'],None)

    def test_conflicting_auto_value_not_overwritten(self):
        r={'operations':{'cart':{'fee_team':90000,'confidence':'official_homepage_extracted_quote_verified'}}}
        changes,conflicts=apply_item(r,item(cart_fee=evidence(fee_team_krw=100000)),TODAY,refresh=True)
        self.assertEqual(r['operations']['cart']['fee_team'],90000)
        self.assertEqual(conflicts[0]['kind'],'existing_value_conflict')

    def test_condition_stays_candidate(self):
        r={};apply_item(r,item(cart_fee=evidence(fee_team_krw=100000,condition='셀프만')),TODAY)
        self.assertNotIn('operations',r)
        self.assertTrue(r['enrichment']['candidates'][0]['condition'])

    def test_false_zero_and_same_source_reconfirmation(self):
        r={};payload=item(cart_fee=evidence(fee_team_krw=0))
        apply_item(r,payload,TODAY);before=copy.deepcopy(r)
        changes,_=apply_item(r,payload,TODAY,refresh=True)
        self.assertEqual(changes,[]);self.assertEqual(before,r)

    def test_replay_does_not_relabel_old_evidence(self):
        r={};payload=item(cart_fee=evidence(fee_team_krw=100000));payload['observed_at']='2025-09-01'
        apply_item(r,payload,TODAY);self.assertNotIn('operations',r)

    def test_exact_page_and_approved_scope_required(self):
        f=evidence(reviewed=False,verified_quote=True)
        i={'schema_version':2,'observed_at':TODAY,'official_url':'https://club.test/',
           'approved_source_urls':['https://club.test/fees'],'page_evidence':[{'url':'https://club.test/other','text':f['quote']}]}
        self.assertFalse(trusted(f,i,TODAY));i['page_evidence'][0]['url']=f['source_url']
        self.assertTrue(trusted(f,i,TODAY));f['from_image']=True
        self.assertFalse(trusted(f,i,TODAY))

    def test_unknown_customer_and_invalid_period_held(self):
        r={};f=evidence(customer='unknown',holes=18,price_krw=150000,day='weekday',session='all')
        apply_item(r,item(green_fees=[f]),TODAY);self.assertNotIn('pricing',r)
        f.update(customer='nonmember',valid_to='not-a-date')
        apply_item(r,item(green_fees=[f]),TODAY);self.assertNotIn('pricing',r)

    def test_fees_age_out_of_budget_filter_but_remain_in_detail(self):
        r={};f=evidence(customer='nonmember',holes=18,price_krw=150000,day='weekday',session='all')
        apply_item(r,item(green_fees=[f]),TODAY)
        class Future(date):
            @classmethod
            def today(cls): return date(2027,2,1)
        with patch('services.golf_pricing.date',Future):
            self.assertIsNone(green_fee(r,False))
            self.assertFalse(fee_summary(r)['is_current'])

    def test_team_fee_age_and_no_mutation(self):
        r={'operations':{'cart':{'fee_team':100000,'fresh_until':'2020-01-01'}}}
        self.assertIsNone(team_fee(r,'cart'))
        self.assertEqual(r['operations']['cart']['fee_team'],100000)

    def test_meaningful_description_preserved_placeholder_replace(self):
        f=evidence(value='파인·크리크·밸리 코스 구성')
        r={'course_overview':'기존 검증 설명'}
        apply_item(r,item(course_description=f),TODAY);self.assertEqual(r['course_overview'],'기존 검증 설명')
        r={'course_overview':'상세 코스정보는 공식 홈페이지에서 확인합니다.'}
        apply_item(r,item(course_description=f),TODAY);self.assertEqual(r['course_overview'],f['value'])

    def test_candidates_idempotent(self):
        r={};payload=item(cart_fee=evidence(fee_team_krw=100000,condition='행사'))
        apply_item(r,payload,TODAY);a=copy.deepcopy(r)
        apply_item(r,payload,TODAY);self.assertEqual(r,a)

    def test_atomic_file_import_supports_wrapped_db_and_dry_run(self):
        spec=importlib.util.spec_from_file_location('apply_review',Path('scripts/apply_golf_review.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as d:
            self.assertTrue(Path(d).resolve().is_relative_to(Path.cwd().resolve()))
            db=Path(d)/'db.json';review=Path(d)/'review.json'
            db.write_text(json.dumps({'schema':'keep','clubs':[{'id':'club','name':'Club'}]}),encoding='utf-8')
            payload=item(phone=evidence(value='031-123-4567'));payload['observed_at']=date.today().isoformat()
            review.write_text(json.dumps({'results':[payload]}),encoding='utf-8')
            before=db.read_bytes()
            with patch.object(module,'find_active_db',return_value=db):
                module.apply_review(review,dry_run=True);self.assertEqual(db.read_bytes(),before)
                result=module.apply_review(review);self.assertTrue(result['backup'])
                self.assertEqual(json.loads(db.read_text(encoding='utf-8'))['schema'],'keep')
                self.assertEqual((Path(d)/'backups'/result['backup']).read_bytes(),before)
                self.assertEqual(module.apply_review(review)['changed'],0)

if __name__=='__main__': unittest.main()
