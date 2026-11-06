"""대시보드의 프런트 순수 함수(투자금 계산·클러스터·마커 계획)를 Node 내장 테스트 러너로 실행한다.

Node 22.18+ 는 TypeScript 파일을 그대로 불러올 수 있어 별도 의존성이 필요 없다.
Node가 없거나 오래된 환경에서는 건너뛴다(실패로 만들지 않고 이유를 남긴다).
"""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS_TESTS = sorted((ROOT / 'tests' / 'js').glob('*.test.mjs'))


def node_ready():
    node = shutil.which('node')
    if not node:
        return False, 'node 없음'
    out = subprocess.run([node, '--version'], capture_output=True, text=True).stdout.strip()
    match = re.match(r'v(\d+)\.(\d+)', out)
    if not match or (int(match.group(1)), int(match.group(2))) < (22, 18):
        return False, f'Node {out}는 TypeScript 직접 실행을 지원하지 않음(22.18+ 필요)'
    return True, out


READY, REASON = node_ready()


@unittest.skipUnless(READY, REASON)
class DashboardPureFunctionTests(unittest.TestCase):
    def test_every_js_test_file_passes(self):
        self.assertTrue(JS_TESTS, 'tests/js/*.test.mjs 가 없습니다')
        for path in JS_TESTS:
            with self.subTest(file=path.name):
                result = subprocess.run(['node', '--test', str(path)], capture_output=True, text=True, cwd=ROOT, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-1500:])


if __name__ == '__main__':
    unittest.main()
