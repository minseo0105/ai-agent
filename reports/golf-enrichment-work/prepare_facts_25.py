from pathlib import Path
import json,re,hashlib,sys
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
rows=json.loads((ROOT/'data/golf/golf_master_precision_checkpoint_2026-09-23_filled.json').read_text(encoding='utf-8-sig'));byid={r['id']:r for r in rows}
contacts=json.loads((OUT/'phone-context-25.json').read_text(encoding='utf-8'))
approved={
 'vworld_인터불고원주g_c':'033)769-8280', 'kgba_여주클래식':'031-883-7000',
 'vworld_해비치':'031-579-3000','vworld_해비치_2':'031-579-3000',
 'vworld_신안퍼블릭c_c':'031)8046-0777','kgba_신안':'031)8046-0777',
 'vworld_해솔리아':'031)329-8100','kgba_리베라':'031)8047-8000',
 'kgba_감곡':'043)882-1600','vworld_드림파크골프장':'032)560-1700',
 'vworld_여주':'031-883-7000','kgba_동원썬밸리':'033)344-5308',
 'vworld_솔트베이_대중':'031-400-0000','vworld_석천':'031-332-3323'}
results={}
def item(id):
 if id not in results:results[id]={'id':id,'name':byid[id]['name'],'official_url':byid[id].get('official_url'),'observed_at':'2026-09-25','schema_version':2,'review_method':'human_official_source','extraction':{}}
 return results[id]['extraction']
def evidence(url,quote,**kw):return {'source_url':url,'quote':quote,'reviewed':True,'condition':'','evidence_type':'paraphrase_of_observed_source',**kw}
for id,number in approved.items():
 source=next(r for r in contacts if r['id']==id and r['phone']==number)
 quote='공식 페이지의 해당 골프장 주소·지점명 옆 문의 또는 대표 번호 확인. 그룹 본사·팩스와 구분.'
 if id=='vworld_해솔리아':quote='해솔리아 골프장 공식 예약번호. 개인정보관리 담당 번호와 구분.'
 item(id)['phone']=evidence(source['url'],quote,value=number.replace(')','-'))
pages=json.loads((OUT/'fee-pages.txt').read_text(encoding='utf-8'));maron=next(r for r in pages if r['id']=='vworld_마론뉴데이')
for kind,amount in [('cart',100000),('caddie',160000)]:
 item('vworld_마론뉴데이')[kind+'_fee']=evidence(maron['url'],'공식 일반 이용요금의 '+('카트비 100,000원' if kind=='cart' else '캐디피 160,000원')+'. 18홀 중도정산 안내와 구분.',fee_team_krw=amount)
for id in ('kgba_신안','vworld_신안퍼블릭c_c','kgba_리베라'):
 url=byid[id]['official_url'];isriver=id=='kgba_리베라'
 item(id)['official_features']=[evidence(url,'신안그룹의 해당 골프장 부대시설 안내. 그룹 내 다른 지점과 구분.',field='driving_range',value='골프연습장 2개동(체리·밸리)' if isriver else '골프연습장'),evidence(url,'해당 골프장 부대시설 목록에 PAR3코스 명시.',field='par3_course',value='PAR3코스')]
 item(id)['course_description']=evidence(url,'공식 그룹 페이지의 해당 지점 규모·개장일·부대시설을 요약.',value='공식 안내 기준 36홀 회원제 골프장으로 1972년 11월 개장. 골프연습장 2개동(체리·밸리)과 PAR3코스를 안내합니다.' if isriver else '공식 안내 기준 회원제 18홀과 대중 9홀, 총 27홀 구성. 1999년 2월 개장했으며 골프연습장과 PAR3코스를 안내합니다.')
# Record conditional prices as candidates, not unconditional filter values.
for id,amount,day,reason in [('vworld_오너스g_c',190000,'weekday','인터넷 회원 가입 여부와 계절·시간별 변동. 정상가와 예약가 구분 필요.'),('vworld_솔트베이_대중',150000,'weekday','2026년 9월 1부 05:46~05:59 범위 150000~170000원. 인터넷회원 요건·시간별 범위.'),('kgba_하이원',160000,'weekday','2026년 9월 기본 요금. 6시 할인·8시 할증, 금요일/일요일 2부 요일 예외.')]:
 p=next(r for r in pages if r['id']==id)
 item(id)['green_fees']=[evidence(p['url'],'현재 공식 표의 조건부 가격이며 일반 고정요금으로 반영하지 않음.',condition=reason,day=day,session='all',customer='nonmember',holes=18,price_krw=amount)]
dest=OUT/'data/golf/enrichment_review/reviewed_2026-09-25.json';dest.parent.mkdir(parents=True,exist_ok=True)
dest.write_text(json.dumps({'created_at':'2026-09-25','results':list(results.values()),'note':'94개 공식 홈페이지 본문 및 32개 연결 페이지 조사. 검토한 빈값만 채움. 조건부 그린피는 후보.'},ensure_ascii=False,indent=2),encoding='utf-8')
print('reviewed records',len(results))
