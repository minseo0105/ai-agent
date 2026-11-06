"""활성화 사전점검 스크립트: 읽기 전용이며 Secret 값을 출력하지 않는다."""
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import zipon_activation_preflight as pre


class PreflightTests(unittest.TestCase):
    def test_repository_is_ready_and_exit_code_is_zero(self):
        out = io.StringIO()
        self.assertEqual(pre.main(ROOT, {}, out), 0)
        self.assertIn('이상 없음', out.getvalue())
        self.assertIn('LIVE_VERIFIED가 아닙니다', out.getvalue())

    def test_user_steps_are_always_listed(self):
        out = io.StringIO()
        pre.main(ROOT, {}, out)
        for where, _ in pre.USER_STEPS:
            self.assertIn(where, out.getvalue())

    def test_secret_values_are_never_printed(self):
        out = io.StringIO()
        pre.main(ROOT, {'ZIPON_IMPORT_SUPABASE_KEY': 'super-secret-value',
                        'ZIPON_IMPORT_SUPABASE_URL': 'https://secret.example'}, out)
        self.assertNotIn('super-secret-value', out.getvalue())
        self.assertNotIn('secret.example', out.getvalue())

    def test_missing_file_fails_the_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            self.assertEqual(pre.main(Path(tmp), {}, out), 1)
            self.assertIn('없음:', out.getvalue())

    def test_removed_safety_gate_fails_the_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp)
            for relative in pre.REQUIRED_FILES:
                target = copy / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / relative, target)
            workflow = copy / pre.WORKFLOW
            workflow.write_text(workflow.read_text(encoding='utf-8')
                                .replace('ZIPON_CANARY_VERIFIED', 'X'), encoding='utf-8')
            problems, _, _ = pre.check(copy, {})
            self.assertTrue(any('ZIPON_CANARY_VERIFIED' in p for p in problems))

    def test_script_has_no_network_or_write_calls(self):
        source = (ROOT / 'scripts/zipon_activation_preflight.py').read_text(encoding='utf-8')
        for word in ('requests', 'urllib', 'subprocess', 'socket', '.write_text', 'open('):
            self.assertNotIn(word, source.split('"""', 2)[2], word)


if __name__ == '__main__':
    unittest.main()
