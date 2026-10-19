import json,hashlib,re,sys
from pathlib import Path
from datetime import date
from collections import Counter
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent/'data/golf'
sys.path.insert(0,str(ROOT))
from services.golf_review_evidence import clean
data=json.loads((ROOT/'data/golf/review_evidence.json').read_text(encoding='utf-8'))
today=date(2026,9,25)
# Decisions follow inspection of saved full article headers and adjacent paragraphs.
accepted={
 '63ac65a33389249e80cd1c67':('Lake 2번 홀','2025-05-24 방문일과 2번 홀 소제목 확인. 높고 많은 벙커라는 해당 홀 의견.'),
 '69891c86ce9c2579c94742ca':('Lake 4번 홀','4번 홀 소제목 아래의 페어웨이 설명. 전체 코스에 일반화하지 않음.'),
 '7df2c4e141dca6c606eef4ea':('Mountain 17번 홀','17번 홀 소제목과 이벤트 홀 문맥 확인.'),
 '2bb076abccdc07e549052d9d':('락커룸·카트','실제 라운드 중 관찰한 노후 의견. 다른 시설에는 긍정 의견도 있어 시설 전체 평가로 확대하지 않음.'),
 '90787380afdfd292e53984eb':('whole_course','천안상록 27홀 소개에 이어 직접 라운딩한 전체적 인상을 명시. 독립 후기 1명으로만 표시.'),
 '7bb2fdc042276cda7bf1e0a6':('올드코스','제목과 본문이 올드코스 방문을 명시. 듄스코스에 일반화하지 않음.'),
 '7f78d6f9b06394b9c3d0b8d1':('올드코스','비가 온 라운드 당일 그린 체감. 대회 직전이라는 문맥이며 상시 속도가 아님.'),
 '150e8e922216e086001aa3ae':('버치코스 1번 홀','버치코스 시작 및 첫 홀 티샷 바로 뒤의 수사적 질문. 해당 홀 넓이 의견만 인정.'),
 '02d5edcd9d17a62f27d93651':('whole_course','가평 프리스틴밸리 전체 공략 단락의 체감. 넓어도 도그레그·해저드에서 부담 있다는 제한 보존.'),
 'ffd3945f8e9dafec70a2275f':('whole_course','필로스 반복 방문자의 전체적인 체감. 넓지만 공략이 어려웠다는 반대 맥락 보존.'),
}
rejected={
 '3afb5629ca26deaf7e392ebb':'미국코스 2번 홀은 다른 홀보다 벙커가 많지 않다는 문장. many 추출은 부정문 반전 오류.',
 'c5081f02d22b516545766218':'음식 준비가 깔끔하다는 문장으로 시설 품질 근거가 아님.',
 'd285e2ef3eacf54e53aa4e20':'골프 전문 여행사의 판매 패키지 소개. 독립 방문 후기 아님. 코스 명칭도 같은 본문에서 상충.',
}
manual_holds={
 '21ab61ab585c35ded12ab35a':'바로 뒤에 시각적으로 좁아 보이지만 실제로는 넓다는 설명이 있어 단순 narrow 분류 보류.',
 '057434406b1b2848198ba46e':'동코스 한정이며 절대 OB가 안 난다는 과장 표현 포함. 일반 특징으로 반영 보류.',
 '7597ff027d5234f9be0de091':'첫 버디의 수년 전 기억과 2025년 재방문이 섞여 특징 관찰 시점 불명확.',
 '893c8a91013536042b44d39f':'수년 전 첫 버디 경험 문단으로 게시일을 경험일로 볼 수 없음.',
 '7f08c23e746355813057a6cb':'동일 작성자 반복 특징이며 실제 관찰 시점 추가 확인 필요.',
}
audit=[];decisions=[]
for c in data['clubs'].values():
 rawfile=ROOT/'data/golf/runtime/refinement_2026-09-24'/(hashlib.sha256(c['id'].encode()).hexdigest()[:20]+'.json')
 raw=json.loads(rawfile.read_text(encoding='utf-8')) if rawfile.exists() else {}
 authors=Counter(s['author_key'] for s in c['sources'])
 hashes=Counter(s.get('content_hash') for s in c['sources'])
 for s in c['sources']:
  rr=next((r for r in raw.get('results',[]) if r['url']==s['original_url']),{})
  body=clean(rr.get('raw_content') or rr.get('content') or '')
  for o in s['observations']:
   oid=o['id'];reasons=[]
   try:age=(today-date.fromisoformat(s['published_at'])).days
   except ValueError:age=None
   if not s.get('full_text_available'):reasons.append('full_text_missing')
   if age is None:reasons.append('publication_date_missing')
   elif age<0:reasons.append('future_publication_date')
   elif age>(365 if o['dimension'] in ('maintenance','green','facilities') else 730):reasons.append('outside_freshness_window')
   if s.get('sponsored_suspected'):reasons.append('sponsorship_suspected')
   if not s.get('first_person_signal'):reasons.append('firsthand_context_needs_review')
   if o['evidence'] not in body:reasons.append('quote_not_found_in_saved_text')
   if authors[s['author_key']]>1:reasons.append('same_author_multiple_sources')
   if hashes[s.get('content_hash')]>1:reasons.append('duplicate_content_hash')
   if oid in accepted:
    scope,reason=accepted[oid]
    assert o['evidence'] in body,oid
    assert age is not None and 0<=age<=(365 if o['dimension'] in ('maintenance','green','facilities') else 730)
    o.update(status='human_reviewed',scope=scope,confidence='single_review_opinion',reviewed_at=today.isoformat(),review_method='source_context_inspection',reason=reason)
    if c['id']=='clubd_theplayers':s['first_person_signal']=True;s['first_person_review_note']='본문 방문일 2025-05-24 및 실제 홀 순서 진행 확인'
    decisions.append({'club_id':c['id'],'observation_id':oid,'status':o['status'],'scope':scope,'reason':reason})
   elif oid in rejected:
    o.update(status='rejected',confidence='rejected_extraction',reviewed_at=today.isoformat(),review_method='source_context_inspection',reason=rejected[oid])
    decisions.append({'club_id':c['id'],'observation_id':oid,'status':o['status'],'reason':rejected[oid]})
   if oid in manual_holds:reasons.append('context_ambiguity');o['review_note']=manual_holds[oid]
   o['screening']={'checked_at':today.isoformat(),'method':'offline_rules_v1','flags':reasons,'scope_verified':o.get('status')=='human_reviewed'}
   state=o.get('status')
   audit.append({'club_id':c['id'],'observation_id':oid,'source':s['source'],'author_key':s['author_key'],'dimension':o['dimension'],'status':state,'flags':reasons,'reason':o.get('reason') or o.get('review_note') or '원문·시점·대상 범위 확인 전 표시 보류'})
data['curated_at']=today.isoformat()
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'review_evidence.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
review=OUT/'enrichment_review';review.mkdir(exist_ok=True)
stats={'as_of':today.isoformat(),'scope':243,'observations':len(audit),'statuses':dict(Counter(a['status'] for a in audit)),'flags':dict(Counter(f for a in audit for f in a['flags'])),'new_context_decisions':decisions,'items':audit,'note':'235건 모두 규칙 점검. 원문 문맥 판정은 new_context_decisions 및 기존 reviewed/rejected만. 전체 수작업 검증 완료 아님.'}
(review/'review_validation_2026-09-25.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in stats.items() if k not in ('items','new_context_decisions')},ensure_ascii=False))
