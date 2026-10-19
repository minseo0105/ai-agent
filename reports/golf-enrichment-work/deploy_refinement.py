from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
S=Path(__file__).resolve().parent;T=Path(__file__).resolve().parents[2]
files={p:p for p in ['services/golf_review_evidence.py','services/golf_service.py','scripts/golf_refine_243.py','scripts/build_golf_review_evidence.py','tests/test_golf_review_evidence.py','docs/golf_refinement_243_2026-09-24.md']}
files.update({'review-output/review_evidence.json':'data/golf/review_evidence.json','review-output/refinement_243_audit.json':'data/golf/enrichment_review/refinement_243_audit.json','review-output/review_curation_2026-09-24.json':'data/golf/enrichment_review/review_curation_2026-09-24.json'})
backup=T/'data/golf/backups'/('review_refinement_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
master=T/'data/golf/golf_master_precision_checkpoint_2026-09-23_filled.json';before=hashlib.sha256(master.read_bytes()).hexdigest()
for src,dest in files.items():
    target=T/dest
    assert target.resolve().is_relative_to(T.resolve())
    if target.exists():
        saved=backup/dest;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(S/src,target)
p=T/'CLAUDE.md';text=p.read_text(encoding='utf-8');addition='\nAlso read `docs/golf_refinement_243_2026-09-24.md`: 243-record review evidence audit, paid search cost, candidate vs reviewed opinions, and scoped UI integration. Do not promote unreviewed review candidates to filters.\n'
if addition not in text:
    backup.mkdir(parents=True,exist_ok=True);shutil.copy2(p,backup/'CLAUDE.md');p.write_text(text+addition,encoding='utf-8')
sys.path.insert(0,str(T))
from services import golf_service as gs
assert [len(p) for p in gs.load_pools()]==[527,451,243]
for club in ['kgba_남여주','vworld_드림파크골프장','southsprings']:
    d=gs.club_detail(club)
    print(json.dumps({'id':club,'analysis':d['reviews']['analysis'],'links':len(d['reviews']['links'])},ensure_ascii=False))
assert hashlib.sha256(master.read_bytes()).hexdigest()==before
print('Master DB unchanged; service/detail smoke passed; backup: '+str(backup))
