import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from services import golf_service as gs
from scripts.apply_golf_review import apply_review
from services.golf_review_evidence import detail_block
assert [len(p) for p in gs.load_pools()]==[527,451,243]
for text in ['여주 2인 골프장','야외연습장 PAR3 있는 골프장','페어웨이 넓은 골프장']:
 r=gs.ai_search(text);assert not r['items'] and r['unsupported_conditions']
assert gs.ai_search('여주 골프장')['items']
assert not gs.ai_search('제주 골프장')['items']
detail=gs.club_detail('kgba_하이원');assert detail['fee_block']['is_current'] is False;assert detail['fee_block']['weekday_total'] is None
ladena=next(c for c in gs.load_pools()[0] if '라데나' in c['name']);assert gs.club_detail(ladena['id'])['fee_block']['weekday_total'] is None
cad=gs.club_detail('vworld_마론뉴데이')['operations']['caddie'];assert '160,000' in str(cad)
club=gs.club_detail('kgba_리베라');assert club['contact']['phone']=='031-8047-8000';assert len(club['official_facilities'])==2
assert len(detail_block('clubd_theplayers')['scoped_cards'])==3
assert len(detail_block('lavie')['scoped_cards'])==2
assert detail_block('kgba_천안상록')['dimensions']['fairway']['status']=='single_review'
assert all(dim['status']!='supported' for c in gs.load_pools()[2] for dim in (detail_block(c['id']) or {}).get('dimensions',{}).values())
replay=apply_review(ROOT/'data/golf/enrichment_review/reviewed_2026-09-25.json',dry_run=True)
assert replay['changed']==0,replay
print(json.dumps({'pools':[527,451,243],'new_evidence_idempotent':True,'unsupported_filters_blocked':True,'unknown_total_hidden':True,'monthly_prices_quarantined':True,'facilities_visible':True,'review_scopes_preserved':True},ensure_ascii=False))
