"""Offline archive boundaries and dedicated GitHub sync protections."""
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from scripts.prepare_moneyon_web_upload import package

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('moneyon_sync',ROOT/'deploy/moneyon/github/sync_moneyon.py')
sync_module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_module)


class WebPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.output=Path(self.temp.name)/'release'
        self.summary=package(self.output)
        self.api=Mock()
        self.api.whoami.return_value={'name':'money-owner'}
        self.api.space_info.return_value=SimpleNamespace(sdk='docker')
        self.api.list_repo_files.return_value=['README.md','Dockerfile','.gitattributes']

    def tearDown(self):self.temp.cleanup()

    def test_exact_web_archive_and_no_wrapper_folder(self):
        with zipfile.ZipFile(self.output/'moneyon-huggingface-web.zip') as z:
            files=z.namelist()
        self.assertEqual(len(files),49)
        self.assertIn('Dockerfile',files)
        self.assertIn('web/src/app/moneyon/TrialExperience.tsx',files)
        self.assertIn('web/src/app/moneyon/TrialHome.tsx',files)
        self.assertEqual(sorted(files),(self.output/'UPLOAD_FILES.txt').read_text(encoding='utf-8').splitlines())
        self.assertFalse(any('.github' in p or 'tools/' in p or '.env' in p or 'sqlite' in p or 'secrets' in p for p in files))

    def test_github_archive_is_separate(self):
        with zipfile.ZipFile(self.output/'moneyon-github-web.zip') as z:files=z.namelist()
        self.assertEqual(len(files),52)
        self.assertIn('.github/workflows/deploy-moneyon.yml',files)
        self.assertIn('tools/sync_moneyon.py',files)
        self.assertEqual(len(sync_module.validate(self.output/'github-upload')),49)

    def test_sync_never_uploads_controller_or_deletes_or_creates(self):
        sync_module.sync(self.output/'github-upload','money-owner/moneyon-demo',self.api)
        args=self.api.upload_folder.call_args.kwargs
        self.assertEqual(args['repo_id'],'money-owner/moneyon-demo')
        self.assertEqual(len(args['allow_patterns']),49)
        self.assertFalse(any(p.startswith(('tools/','.github/')) for p in args['allow_patterns']))
        self.assertNotIn('delete_patterns',args)
        self.api.create_repo.assert_not_called()
        self.api.add_space_secret.assert_not_called()

    def test_other_agent_target_refused_before_remote_access(self):
        with self.assertRaises(ValueError):sync_module.sync(self.output/'github-upload','money-owner/digital-ai-lab',self.api)
        self.api.whoami.assert_not_called()
        self.api.upload_folder.assert_not_called()

    def test_wrong_owner_refused(self):
        with self.assertRaises(ValueError):sync_module.sync(self.output/'github-upload','someone-else/moneyon-demo',self.api)
        self.api.upload_folder.assert_not_called()

    def test_non_docker_and_unexpected_files_refused(self):
        self.api.space_info.return_value=SimpleNamespace(sdk='gradio')
        with self.assertRaises(ValueError):sync_module.sync(self.output/'github-upload','money-owner/moneyon-demo',self.api)
        self.api.space_info.return_value=SimpleNamespace(sdk='docker')
        self.api.list_repo_files.return_value=['README.md','another-agent.py']
        with self.assertRaises(ValueError):sync_module.sync(self.output/'github-upload','money-owner/moneyon-demo',self.api)
        self.api.upload_folder.assert_not_called()

    def test_changed_source_refused(self):
        (self.output/'github-upload'/'space_app.py').write_text('changed')
        with self.assertRaises(ValueError):sync_module.sync(self.output/'github-upload','money-owner/moneyon-demo',self.api)
        self.api.upload_folder.assert_not_called()


if __name__=='__main__':unittest.main()
