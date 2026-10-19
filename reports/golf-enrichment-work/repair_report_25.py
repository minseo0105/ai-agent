from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2];STAGE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from services import golf_service as gs
from services.golf_repository import find_active_db
applied=json.loads((ROOT/'data/golf/enrichment_review/applied_2026-09-25.json').read_text(encoding='utf-8'))
before_rows=json.loads((ROOT/'data/golf/backups'/applied['backup']).read_text(encoding='utf-8-sig'))
rows=json.loads(find_active_db().read_text(encoding='utf-8-sig'))
changed=sum(r.get('validation_status')=='needs_review' for c in rows if c['id']=='kgba_하이원' for r in c['pricing']['fee_records'])
s=(STAGE/'apply_25.py').read_text(encoding='utf-8')
tail=s[s.index("poolids={"):].replace("sum(r['pages'] for r in collection)","sum(r['pages'] if isinstance(r['pages'],int) else len(r['pages']) for r in collection)").replace("collected.get(r['id'],{}).get('pages',0)","(collected.get(r['id'],{}).get('pages',0) or 0)")
exec(tail)
