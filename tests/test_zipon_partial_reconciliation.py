import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
from tests import test_zipon_resume_apply as fixtures
import reconcile_zipon_partial as partial
import zipon_journal


class PartialReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ResumeApplyTests();self.f.setUp()

    def interrupted(self):
        failed_once=False
        def persist(report):
            nonlocal failed_once
            if report['newly_written']==41 and not failed_once:
                failed_once=True
                raise PermissionError('PRIVATE_PATH_NOT_TO_BE_LOGGED')
        f=self.f.fixture
        return partial.resume.run(f.rows,f.bulk,f.canary,f.old,self.f.request,persist)

    def test_journal_error_does_not_duplicate_success_or_miscount_remaining(self):
        report=self.interrupted()
        self.assertEqual(len(report['results']),41)
        self.assertEqual(report['newly_written'],41)
        self.assertEqual(report['failed'],0)
        self.assertEqual(report['not_attempted'],80)
        self.assertTrue(report['located_accepted_points_match'])
        self.assertTrue(report['accepted_points_match'])
        self.assertFalse(report['all_accepted_complete'])
        self.assertEqual(report['journal_error']['stage'],'LOCAL_JOURNAL_PERSIST')
        self.assertNotEqual(report['result'],'SUCCESS')

    def test_all_saved_points_match_while_pending_points_are_not_mismatches(self):
        report=self.interrupted();f=self.f.fixture
        # Historical duplicate entry is preserved and must not distort read-only counts.
        report['results'].append({'project_id':report['results'][-1]['project_id'],'result':'UNKNOWN_AFTER_REQUEST'})
        original=copy.deepcopy(report)
        result=partial.reconcile(f.rows,f.bulk,report,self.f.live)
        self.assertEqual((result['normal_applied_count'],result['remaining_count'],result['mismatch_count']),(42,80,0))
        self.assertEqual(result['result'],'PASS')
        self.assertFalse(result['write_retry_authorized'])
        self.assertEqual(original,report)

    def test_wrong_point_and_revision_both_found_in_one_pass(self):
        report=self.interrupted();f=self.f.fixture
        ids=[r['project_id'] for r in report['results'][:2]]
        next(r for r in self.f.live if r['project_id']==ids[0])['location']='bad-ewkb'
        next(r for r in self.f.live if r['project_id']==ids[1])['revision']=99
        result=partial.reconcile(f.rows,f.bulk,report,self.f.live)
        self.assertEqual(result['mismatch_count'],2)
        self.assertEqual({r['project_id'] for r in result['mismatches']},set(ids))
        self.assertEqual(result['result'],'BLOCKED')

    def test_remaining80_skips_all42_with_fresh_gates(self):
        previous=self.interrupted();f=self.f.fixture
        applied={r['project_id'] for r in self.f.live if r['location'] is not None}
        self.f.posts=[]
        result=partial.resume.run(f.rows,f.bulk,f.canary,f.old,self.f.request,lambda r:None,previous)
        self.assertEqual(result['result'],'SUCCESS')
        self.assertEqual(result['already_applied'],42)
        self.assertEqual(result['newly_written'],80)
        self.assertEqual(result['located'],122)
        self.assertFalse(applied & set(self.f.posts))

    def test_unique_checkpoint_retries_only_file_replace(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'journal.json'
            path.write_text('old',encoding='utf-8')
            original=os.replace
            calls=[]
            def replace(source,target):
                calls.append(source)
                if len(calls)<3:raise PermissionError(13,'locked')
                original(source,target)
            with patch.object(zipon_journal.os,'replace',side_effect=replace),patch.object(zipon_journal.time,'sleep'):
                zipon_journal.save(path,{'rpc_result':'location_set'})
            self.assertEqual(len(calls),3)
            self.assertIn('location_set',path.read_text(encoding='utf-8'))

    def test_persistent_lock_keeps_old_and_complete_new_checkpoint(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'journal.json';path.write_text('old',encoding='utf-8')
            with patch.object(zipon_journal.os,'replace',side_effect=PermissionError(13,'locked')),patch.object(zipon_journal.time,'sleep'):
                with self.assertRaises(PermissionError):zipon_journal.save(path,{'rpc_result':'location_set'})
            self.assertEqual(path.read_text(encoding='utf-8'),'old')
            checkpoints=list(Path(directory).glob('*.pending'))
            self.assertEqual(len(checkpoints),1)
            self.assertIn('location_set',checkpoints[0].read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
