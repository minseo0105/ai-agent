"""머니온 정적 화면: 아이콘 세 파일만 더 열고 그 밖의 경로는 그대로 막는다(오프라인)."""

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp()
os.environ.setdefault('MONEYON_TRIAL_ENABLED', '1')
os.environ.setdefault('MONEYON_TRIAL_DB', f'{TMP}/trial.sqlite3')

import space_app  # noqa: E402


class StaticIconsTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        for name in ('index.html', 'icon.png', 'apple-icon.png', 'opengraph-image.png', 'secret.txt'):
            (self.dir / name).write_bytes(b'x')
        self.site = space_app.ExportedSite(directory=str(self.dir), html=True)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def status(self, path):
        scope = {'type': 'http', 'method': 'GET', 'headers': [], 'path': '/' + path}
        return asyncio.run(self.site.get_response(path, scope)).status_code

    def test_icons_are_served_and_other_files_stay_blocked(self):
        for name in space_app.ICON_FILES:
            self.assertEqual(self.status(name), 200, name)
        self.assertEqual(self.status('secret.txt'), 404)
        self.assertEqual(self.status(''), 200)


if __name__ == '__main__':
    unittest.main()
