"""Deploy reviewed files and fill-only DB enrichment to the explicitly named copy."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
from datetime import datetime

STAGE = Path(__file__).resolve().parent
TARGET = Path(__file__).resolve().parents[2]
FILES = ['services/golf_import_policy.py','services/golf_pricing.py',
         'scripts/apply_golf_review.py','scripts/golf_official_enrich.py',
         'scripts/golf_quarterly_refresh.py','scripts/golf_phone_audit.py',
         '.github/workflows/golf-quarterly-refresh.yml',
         'tests/test_golf_import_policy.py','docs/golf_enrichment_policy.md',
         'data/golf/enrichment_review/reviewed_2026-09-24.json']
DB = 'data/golf/golf_master_precision_checkpoint_2026-09-23_filled.json'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def main():
    manifest_path=STAGE/'deploy_manifest.json'
    if '--prepare' in sys.argv:
        assert sha(TARGET/DB)=='af681800b26f8cd16a5f3fdefd960b4402c1a1e55cd3fcc86ac4b69147f8a327', 'Source DB changed'
        manifest_path.write_text(json.dumps({p:sha(TARGET/p) for p in FILES+[DB]},indent=2),encoding='utf-8')
        print('Manifest prepared; no target changes');return
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    for p,digest in manifest.items():
        assert (TARGET/p).resolve().is_relative_to(TARGET)
        assert sha(TARGET/p)==digest, 'Concurrent change: '+p
    backup=TARGET/'data/golf/backups'/('enrichment_deploy_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True)
    for p in FILES:
        dest=TARGET/p
        if dest.exists():
            saved=backup/p;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(STAGE/p,dest)
    before=json.loads((TARGET/DB).read_text(encoding='utf-8-sig'))
    sys.path.insert(0,str(TARGET));sys.path.insert(0,str(TARGET/'scripts'))
    from apply_golf_review import apply_review
    from services.golf_repository import find_active_db
    assert find_active_db().resolve()==(TARGET/DB).resolve()
    result=apply_review(TARGET/'data/golf/enrichment_review/reviewed_2026-09-24.json')
    after=json.loads((TARGET/DB).read_text(encoding='utf-8-sig'))
    assert len(before)==len(after)==527
    assert [r['id'] for r in before]==[r['id'] for r in after]
    allowed={'phone','pricing','operations','sources','field_evidence','enrichment','course_overview'}
    for a,b in zip(before,after):
        for key,value in a.items():
            if key not in allowed: assert b[key]==value,(a['id'],key)
    from services import golf_service as gs
    result['runtime_pool_sizes']=[len(p) for p in gs.load_pools()]
    result['code_backup']=str(backup)
    result['db_sha256']=sha(TARGET/DB)
    repeat=apply_review(TARGET/'data/golf/enrichment_review/reviewed_2026-09-24.json',dry_run=True)
    assert repeat['changed']==0, 'Import must be idempotent'
    result['idempotent']=True
    report=TARGET/'data/golf/enrichment_review/applied_2026-09-24.json'
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='items'},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
