"""Read-only coverage and local domain smoke check. No API calls, no DB writes."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.golf_repository import find_active_db
from services import golf_service as gs
from services.golf_pricing import green_fee

def get(r,path):
    for key in path.split('.'): r=r.get(key) if isinstance(r,dict) else None
    return r
def present(v): return v is not None and v not in ('',[],{},'unknown','확인 필요')
def main():
    db=find_active_db();rows=json.loads(db.read_text(encoding='utf-8-sig'))
    pools=gs.load_pools();ids={r['id'] for r in pools[2]}
    fields=['official_url','phone','address','holes','pricing.fee_records','operations.caddie.fee_team','operations.cart.fee_team','sources','operations.players.two_person.allowed','operations.players.three_person.allowed']
    coverage={p:{'all':sum(present(get(r,p)) for r in rows),'recommendation':sum(present(get(r,p)) for r in rows if r['id'] in ids)} for p in fields}
    placeholders={'상세 코스정보는 공식 홈페이지에서 확인합니다.','상세 코스정보는 공식 홈페이지에서 확인할 수 있습니다.'}
    meaningful=lambda r:present(r.get('course_overview')) and (not isinstance(r['course_overview'],str) or r['course_overview'] not in placeholders)
    coverage['meaningful_course_overview']={'all':sum(meaningful(r) for r in rows),'recommendation':sum(meaningful(r) for r in rows if r['id'] in ids)}
    coverage['renderable_hole_details']={'all':sum(bool(gs._hole_rows(r['course_details'])) for r in rows if isinstance(r.get('course_details'),list))}
    examples=[]
    for name in ['기흥','라데나','캐슬파인','링크나인']:
        r=next(r for r in rows if name in r['name']);detail=gs.club_detail(r['id'])
        assert detail and detail['contact']['phone']==r['phone']
        assert detail['sources']
        examples.append({'id':r['id'],'name':r['name'],'phone':detail['contact']['phone'],'fee_block':detail['fee_block']})
    search=gs.condition_search({'departure':'','day':'주중','budget':'전체','players':'전체','caddie':'전체','areas':[]})
    assert search['items']
    print(json.dumps({'db':str(db),'records':len(rows),'pools':[len(p) for p in pools],'coverage':coverage,'current_normalizable_greenfee':sum(green_fee(r,False) is not None or green_fee(r,True) is not None for r in rows),'default_search_results':len(search['items']),'detail_examples':examples},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
