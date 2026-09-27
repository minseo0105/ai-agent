import copy
import importlib.util
import json
from pathlib import Path
import unittest
import requests

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reconcile_coordinate',ROOT/'scripts/reconcile_zipon_coordinate.py')
module=importlib.util.module_from_spec(spec)
# Match direct-script execution without importing configuration/secrets.
import sys
sys.path.insert(0,str(ROOT/'scripts'))
spec.loader.exec_module(module)


class ReadonlyCoordinateTests(unittest.TestCase):
    def setUp(self):
        queue=json.loads((module.guard.DATA/'geocode_apply_ready_20260927.json').read_text(encoding='utf-8'))
        self.candidate=next(r for r in queue['items'] if r['project_id']==module.TARGET)
        self.row=dict(project_id=module.TARGET,address=self.candidate['canonical_address'],
                      sigungu=self.candidate['district'],revision=1,location=None,geometry=None,geometry_verified=False)
        self.journal={'before':[copy.deepcopy(self.row)],'after':[copy.deepcopy(self.row)]}
        payload=module.guard.existing.payload_for(self.candidate,self.row)
        self.schema={'paths':{'/rpc/zipon_set_project_location':{'post':{'parameters':[
            {'in':'body','schema':{'properties':{k:{} for k in payload},'required':list(payload)}}]}}}}
        self.calls=[]

    def request(self,method,table,**kwargs):
        self.assertEqual(method,'GET')
        self.calls.append(table)
        if table=='development_projects':
            self.assertEqual(kwargs['params']['project_id'],'eq.'+module.TARGET)
            return [copy.deepcopy(self.row)]
        self.assertEqual(table,'')
        return self.schema

    def test_single_project_readonly_success_preserves_journal(self):
        before=copy.deepcopy(self.journal)
        result=module.inspect(self.request,self.candidate,self.journal)
        self.assertEqual(result['dry_run'],'PASS')
        self.assertFalse(result['rpc_invoked'])
        self.assertFalse(result['db_write'])
        self.assertEqual(self.calls,['development_projects',''])
        self.assertEqual(before,self.journal)

    def test_missing_rpc_is_not_asserted_to_be_original_http_cause(self):
        self.schema={'paths':{}}
        result=module.inspect(self.request,self.candidate,self.journal)
        self.assertEqual(result['rpc_schema'],'NOT_ADVERTISED_TO_THIS_ROLE')
        self.assertIn('not recoverable',result['diagnosis'])
        self.assertEqual(result['dry_run'],'BLOCKED')

    def test_location_or_revision_changes_block_preflight(self):
        self.row.update(location='existing',revision=2)
        result=module.inspect(self.request,self.candidate,self.journal)
        self.assertEqual(result['preflight'],'BLOCKED')
        self.assertTrue(result['live_project']['location_present'])
        self.assertIn('REVISION_CHANGED_SINCE_JOURNAL',result['preflight_reasons'])

    def test_signature_mismatch_blocks(self):
        self.schema['paths']['/rpc/zipon_set_project_location']['post']['parameters'][0]['schema']['properties'].pop('p_evidence')
        result=module.inspect(self.request,self.candidate,self.journal)
        self.assertEqual(result['rpc_schema'],'PAYLOAD_SIGNATURE_MISMATCH')

    def test_http_diagnostics_exclude_response_text_and_headers(self):
        for status,code,category in [(404,'PGRST202','RPC_SIGNATURE_OR_SCHEMA_CACHE'),
                                     (401,'PGRST301','AUTHENTICATION'),(403,'42501','AUTHORIZATION'),
                                     (400,'22023','PAYLOAD_OR_CONSTRAINT')]:
            response=requests.Response();response.status_code=status
            response._content=json.dumps({'code':code,'message':'sb_secret_SENSITIVE','details':'password=SENSITIVE'}).encode()
            error=requests.HTTPError('Authorization: SENSITIVE',response=response)
            result=module.safe_error(error)
            self.assertEqual(result['failure_category'],category)
            self.assertEqual(result['http_status'],status)
            self.assertNotIn('SENSITIVE',json.dumps(result))

    def test_network_vs_response_parsing(self):
        self.assertEqual(module.safe_error(requests.Timeout('SENSITIVE'))['failure_category'],'NETWORK')
        self.assertEqual(module.safe_error(ValueError('SENSITIVE'))['failure_category'],'RESPONSE_PARSING')

    def test_powershell_reconcile_is_mutually_exclusive_with_apply(self):
        text=(ROOT/'scripts/run_zipon_verified_coordinates.ps1').read_text(encoding='utf-8')
        self.assertIn('if ($Apply -and $ReconcileFirst)',text)
        self.assertIn("'reconcile_zipon_coordinate.py'",text)

if __name__=='__main__':unittest.main()
