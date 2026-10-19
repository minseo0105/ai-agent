from pathlib import Path
import sys,json,hashlib
from collections import Counter
T=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(T));sys.path.insert(0,str(T/'scripts'))
from apply_golf_review import apply_review
from services import golf_service as gs
from services.golf_repository import find_active_db
db=find_active_db()
backups=sorted((db.parent/'backups').glob(db.stem+'_before_review_*.json'),key=lambda p:p.stat().st_mtime)
backup=backups[-1]
before=json.loads(backup.read_text(encoding='utf-8-sig'));after=json.loads(db.read_text(encoding='utf-8-sig'))
assert len(before)==len(after)==527
assert [r['id'] for r in before]==[r['id'] for r in after]
allowed={'phone','pricing','operations','sources','field_evidence','enrichment','course_overview'}
changed=Counter();facts=0;records=0
for a,b in zip(before,after):
    for k,v in a.items():
        if k not in allowed: assert b[k]==v,(a['id'],k)
    if a!=b: records+=1
    oldh=len(a.get('enrichment',{}).get('history',[]))
    history=b.get('enrichment',{}).get('history',[])[oldh:]
    if history:facts+=1
    changed.update(h['field'] for h in history)
repeat=apply_review(T/'data/golf/enrichment_review/reviewed_2026-09-24.json',dry_run=True)
assert repeat['changed']==0,repeat['items']
report={'changed_records':records,'facts_changed_records':facts,'field_changes':dict(changed),'total_records':len(after),'runtime_pool_sizes':[len(p) for p in gs.load_pools()],'idempotent':True,'backup':str(backup),'db_sha256':hashlib.sha256(db.read_bytes()).hexdigest()}
(T/'data/golf/enrichment_review/applied_2026-09-24.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
