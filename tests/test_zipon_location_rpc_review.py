"""Offline SQL/runner contracts; no database connection or SQL execution."""
import json
from pathlib import Path
import re
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import apply_zipon_geocode as runner


class LocationRpcReviewTests(unittest.TestCase):
    def setUp(self):
        self.sql=(ROOT/'supabase/migrations/20260927_zipon_geocode_location_rpc.sql').read_text(encoding='utf-8')

    def test_all_122_payloads_have_required_accepted_proof(self):
        rows=json.loads((ROOT/'data/development/geocode_apply_ready_20260927.json').read_text(encoding='utf-8'))['items']
        for row in rows:
            p=runner.payload_for(row,{'sigungu':row['district'],'revision':1})
            evidence=p['p_evidence']
            self.assertEqual(evidence['geocode_status'],'ACCEPTED')
            self.assertIs(evidence['coordinate_verified'],True)
            self.assertEqual(evidence['coordinate_orientation'],'X_IS_LONGITUDE')
            self.assertTrue(all(v is True for v in evidence['checks'].values()))
            for key in ('accuracy','bounds','axis_order','seoul','sido_match','district_match','dong_match','lot_match'):
                self.assertIs(evidence['checks'][key],True)

    def test_unaccepted_payload_is_not_promoted(self):
        rows=json.loads((ROOT/'data/development/geocode_apply_ready_20260927.json').read_text(encoding='utf-8'))['items']
        row=dict(rows[0],geocode_status='REVIEW_REQUIRED',coordinate_verified=False)
        evidence=runner.payload_for(row,{'sigungu':row['district'],'revision':1})['p_evidence']
        self.assertEqual(evidence['geocode_status'],'REVIEW_REQUIRED')
        self.assertFalse(evidence['coordinate_verified'])

    def test_boundary_and_acceptance_guards_before_update(self):
        for marker in ('ACCEPTED_EVIDENCE_REQUIRED','GEOCODE_CHECKS_NOT_PASSED','VERIFIED_BOUNDARY_PRESENT',
                       'REVISION_CONFLICT','LOCATION_ALREADY_SET','DISTRICT_MISMATCH','COORDINATE_OUTSIDE_SEOUL'):
            self.assertLess(self.sql.index(marker),self.sql.index('UPDATE public.development_projects'))
        self.assertIn('FOR UPDATE',self.sql)
        self.assertIn('p_geocode_source IS NULL',self.sql)
        self.assertIn('SECURITY INVOKER',self.sql)
        self.assertNotIn('SECURITY DEFINER',self.sql)
        self.assertIn('FROM PUBLIC,anon,authenticated',self.sql)
        self.assertIn('TO service_role',self.sql)
        update=self.sql.split('UPDATE public.development_projects SET',1)[1].split('WHERE project_id',1)[0]
        self.assertNotRegex(update,r'\b(?:geometry|geometry_verified|stage|status)\s*=')

    def test_postcheck_is_select_only_and_does_not_invoke_rpc(self):
        sql=(ROOT/'supabase/review/20260927_zipon_location_rpc_readonly_postcheck.sql').read_text(encoding='utf-8')
        # SQL parser validation is separately run with pglast; this checks the safety contract.
        scrubbed=re.sub(r'--[^\n]*|\'(?:\'\'|[^\'])*\'', '',sql)
        self.assertNotRegex(scrubbed,r'(?i)\b(?:INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|DO|CALL|NOTIFY)\b')
        self.assertNotRegex(scrubbed,r'(?i)\bzipon_set_project_location\s*\(')
        self.assertIn('ALL_CHECKS',sql)

if __name__=='__main__':unittest.main()
