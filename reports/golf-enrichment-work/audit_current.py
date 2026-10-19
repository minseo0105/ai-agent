import sys,json,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from services import golf_service as gs
from scripts.golf_phone_audit import inspect
pool=gs.load_pools()[2]
targets=[r for r in pool if not r.get('phone') and str(r.get('official_url') or '').startswith('http')]
with ThreadPoolExecutor(max_workers=6) as ex: rows=list(ex.map(inspect,targets))
Path(__file__).with_name('phone-audit-25.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'scope':len(pool),'attempted':len(rows),'candidates':sum(bool(r['candidates']) for r in rows)},ensure_ascii=False))
