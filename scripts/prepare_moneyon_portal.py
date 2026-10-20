"""Prepare a two-file portal patch against the inspected production source.

Never uploads the unrelated local checkout or changes backend/access settings.
The baseline files were read from MINSEO2/digital-ai-lab's file viewer.
"""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'reports/moneyon-portal/baseline'
OUTPUT = ROOT / 'reports/moneyon-portal/publish'


def prepare():
    if OUTPUT.exists():
        raise ValueError('Use an empty output folder')
    original = (BASE / 'services.ts').read_text(encoding='utf-8')
    assert 'moneyon' not in original
    marker = '\n];'
    entry = '''
  {
    id: "moneyon",
    category: "Prototype",
    image: "/ailab/money.svg",
    icon: "🐷",
    title: "MONEY · 우루미와 함께하는 어린이 금융 놀이터",
    desc: "용돈을 받고, 쓰고, 저축하면서 이자 보너스를 배워요.",
    href: "https://minseo2-moneyon-demo.hf.space/",
  },'''
    # The first closing array is SERVICES; CATEGORIES is a single line.
    assert original.count(marker) == 1
    updated = original.replace(marker, entry + marker, 1)
    updated = updated.replace('href: s.href, external: false',
                              'href: s.href, external: /^https?:\\/\\//.test(s.href)')
    target = OUTPUT / 'web/src/lib/services.ts'
    target.parent.mkdir(parents=True)
    target.write_text(updated, encoding='utf-8')
    icon = OUTPUT / 'web/public/ailab/money.svg'
    icon.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'web/public/ailab/money.svg', icon)
    manifest = {str(p.relative_to(OUTPUT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in OUTPUT.rglob('*') if p.is_file()}
    (OUTPUT.parent / 'publish-manifest.json').write_text(json.dumps({
        'space': 'MINSEO2/digital-ai-lab',
        'baseline_revision': '7d5a06f1ec6a7006fcc2b3dd82eb0e286888f1f4',
        'files': manifest,
    }, indent=2), encoding='utf-8')
    print(json.dumps({'space': 'MINSEO2/digital-ai-lab', 'files': list(manifest), 'uploaded': False}))


if __name__ == '__main__':
    prepare()
