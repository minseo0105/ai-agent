import json,sys,shutil,hashlib,os,tempfile
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[2];STAGE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from scripts.apply_golf_review import apply_review
from services.golf_repository import find_active_db
files=['services/golf_service.py','services/golf_pricing.py','web/src/lib/golf.ts','web/src/components/golf/GolfDetail.tsx','scripts/build_golf_review_evidence.py','tests/test_golf_search_integrity.py','data/golf/review_evidence.json','data/golf/enrichment_review/review_validation_2026-09-25.json','data/golf/enrichment_review/reviewed_2026-09-25.json']
backup=ROOT/'data/golf/backups'/('improvements_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(parents=True)
for file in files:
 target=ROOT/file;prior=backup/file
 if target.exists():prior.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,prior)
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(STAGE/file,target)
db=find_active_db();before=db.read_bytes();before_rows=json.loads(before.decode('utf-8-sig'))
applied=apply_review(ROOT/'data/golf/enrichment_review/reviewed_2026-09-25.json')
(ROOT/'data/golf/enrichment_review/applied_2026-09-25.json').write_text(json.dumps(applied,ensure_ascii=False,indent=2),encoding='utf-8')
# Quarantine unbounded monthly rows without changing any price/source/evidence.
raw=db.read_bytes();rows=json.loads(raw.decode('utf-8-sig'));club=next(r for r in rows if r['id']=='kgba_하이원');changed=0
for row in club['pricing']['fee_records']:
 if row.get('record_type')=='official_homepage_extract' and not row.get('valid_from') and row.get('validation_status')!='needs_review':
  row.update(validation_status='needs_review',validation_reason='월별·시간별 요금을 유효기간 없이 저장한 행. 현재 예산 검색 사용 보류.',validation_checked_at='2026-09-25');changed+=1
if changed:
 club.setdefault('enrichment',{}).setdefault('history',[]).append({'field':'pricing.fee_records.validation_status','previous':'unbounded monthly rows','value':'needs_review','checked_at':'2026-09-25','source_url':'https://www.high1.com/golf/contents.do?key=762','evidence_quote':'2026년 월별 가격 및 시간 할증, 금요일·일요일 2부 예외를 공식 페이지에서 재확인. 기존 금액은 보존.','confidence':'official_source_context_reviewed'})
 shutil.copy2(db,backup/'before_price_quarantine.json')
 fd,name=tempfile.mkstemp(dir=db.parent,suffix='.tmp')
 with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(rows,f,ensure_ascii=False,indent=1)
 if db.read_bytes()!=raw:raise RuntimeError('Concurrent DB change')
 os.replace(name,db)
assert len(rows)==len(before_rows)==527
assert {r['id'] for r in rows}=={r['id'] for r in before_rows}
originals=ROOT/'data/golf/runtime/official_2026-09-25';originals.mkdir(parents=True,exist_ok=True)
for p in (STAGE/'official-pages-25').glob('*.json'):shutil.copy2(p,originals/p.name)
from services import golf_service as gs
poolids={r['id'] for r in gs.load_pools()[2]};assert len(poolids)==243
fields=['official_url','phone','address','holes','pricing.fee_records','operations.caddie.fee_team','operations.cart.fee_team']
def get(r,path):
 for k in path.split('.'):r=r.get(k) if isinstance(r,dict) else None
 return r
def present(v):return v is not None and v not in ('',[],{},'unknown','확인 필요')
def coverage(data):return {p:sum(present(get(r,p)) for r in data if r['id'] in poolids) for p in fields}
collection=json.loads((STAGE/'official-pages-25/audit.json').read_text(encoding='utf-8'));collected={r['id']:r for r in collection}
items=[]
for r in rows:
 if r['id'] not in poolids:continue
 items.append({'id':r['id'],'name':r['name'],'missing_fields':[p for p in fields if not present(get(r,p))],'official_audit':collected.get(r['id'],{}).get('status','not_targeted_phone_and_greenfee_present'),'pages_fetched':collected.get(r['id'],{}).get('pages',0)})
report={'as_of':'2026-09-25','records':527,'recommendation_records':243,'before':coverage(before_rows),'after':coverage(rows),'facts_changed':applied['facts_changed'],'changed_fields':sum(len([c for c in s['changes'] if c!='evidence_only']) for s in applied['items']),'official_research':{'target_records':len(collection),'fetched_homepages':sum(r['status']=='fetched' for r in collection),'fetched_pages':sum(r['pages'] for r in collection),'no_official_url':sum(r['status']=='no_official_url' for r in collection),'unavailable':sum(r['status']=='unavailable' for r in collection)},'quarantined_monthly_price_rows':changed,'identity_review_groups':[['vworld_해비치','vworld_해비치_2'],['vworld_여주','kgba_여주클래식'],['kgba_신안','vworld_신안퍼블릭c_c']],'identity_review_note':'동일 시설/회원제·대중제 분리 여부 검토 필요. ID 병합이나 Pool 변경은 하지 않음. 파주프리스틴밸리와 노스팜 연결도 명칭 검토 보류.','paid_api_calls':0,'items':items}
(ROOT/'data/golf/enrichment_review/refinement_243_2026-09-25.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='items'},ensure_ascii=False,indent=2))
