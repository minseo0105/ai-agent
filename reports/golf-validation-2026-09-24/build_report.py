"""Read-only source DB audit; writes only adjacent verification artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'data/golf/golf_master_precision_checkpoint_2026-09-23_filled.json'
OUT = Path(__file__).resolve().parent
DATE = '2026-09-24'
FIELDS = {'phone': 'phone', 'green_fee': 'pricing.fee_records',
          'caddie_fee': 'operations.caddie.fee_team', 'cart_fee': 'operations.cart.fee_team'}

def fact(value, source, evidence, condition=None, method='official_page_text'):
    return dict(value=value, source=source, evidence=evidence,
                evidence_type='paraphrase_of_observed_source',
                confidence='official_source_observed', checked_at=DATE,
                effective_period=None, condition=condition, method=method,
                status='conditional_candidate' if condition else 'supported_candidate',
                auto_apply=False)

GH='https://www.ghcc.kr/mobile/manage/manage02.asp'
PC='https://www.pinecreek.co.kr/html_creek/company02.asp'
PC_MONTH='https://www.pinecreek.co.kr/html_creek/board/notice_view.asp?b_idx=87'
LA='https://www.ladena.co.kr/guide/charge'
LN='https://www.linknine.co.kr/admin/board/news/img/26.9%EC%88%98.jpg'
AL='https://www.alpensia.com/golf/gc700/use-info.do'

results = [
 dict(id='kgba_기흥', findings={
  'phone':fact('031-376-4001',GH,'화성시 골프장 주소 옆 대표전화. 서울 본사 전화와 구분.'),
  'green_fee':fact({'weekday':230000,'weekend':300000,'currency':'KRW','holes':18,'customer':'nonmember'},GH,'18홀 비회원 행의 평일 및 주말 입장료. 유효 종료일 미표기; 실시간 예약가 아님.'),
  'caddie_fee':fact(150000,GH,'18홀 도우미 봉사료 15만원.'),
  'cart_fee':fact(100000,GH,'5인승 전동카트 한 대 이용료 10만원.')}, blockers=[]),
 dict(id='vworld_파인크리크c_c', findings={
  'green_fee':fact({'period':'2026-09-14/2026-09-30','currency':'KRW','rows':[
      {'time':'<=06:59','mon_thu':165000,'fri':170000,'sat':270000,'sun':270000},
      {'time':'07:00-07:30','mon_thu':175000,'fri':180000,'sat':270000,'sun':270000},
      {'time':'1부 07:31 이후','mon_thu':190000,'fri':190000,'sat':280000,'sun':280000},
      {'time':'2부 13:30 이전','mon_thu':205000,'fri':205000,'sat':250000,'sun':250000},
      {'time':'2부 13:31 이후','mon_thu':205000,'fri':205000,'sat':220000,'sun':220000}]},PC_MONTH,
      '2026년 9월 공지 이미지의 14~30일 구간을 시각 확인.',
      '공휴일은 주말 요금, 9월 25일 휴장. 이전 기간 요금과 분리. 고객 구분 적용범위는 반영 전 재확인.', 'browser_image_visual'),
  'caddie_fee':fact({'general':150000,'designated':170000},PC,'18홀 일반 및 지정 캐디 비용이 별도 표기.', '캐디 유형별 요금 분리 필요.', 'browser_rendered_text'),
  'cart_fee':fact(100000,PC,'18홀 카트비 10만원. 월별 공지에서도 팀 카트비로 확인.',method='browser_rendered_text')},
  blockers=['웹 검색 도구 403; 일반 브라우저는 정상 접근. 같은 도메인의 파인밸리 요금 혼입 주의.']),
 dict(id='kgba_라데나', findings={
  'green_fee':fact({'weekday':220000,'weekend_holiday':270000,'currency':'KRW','customer':'nonmember'},LA,'비회원 공시요금 행. 근로자의 날 주말 적용. 실시간 예약가 아님.',method='browser_rendered_text'),
  'caddie_fee':fact({'new':120000,'experienced':150000},LA,'신입 및 경력 캐디의 요금 분리 표기.', '경력 구분 없이 단일 비용으로 저장하지 않음.', 'browser_rendered_text'),
  'cart_fee':fact({'with_caddie':100000,'self':120000},LA,'캐디 동반 및 셀프 카트비를 구분한 요금표.', '라운드 방식별 분리 필요.', 'browser_rendered_text')},
  blockers=['웹 텍스트 추출 0줄; 브라우저 렌더링 후 이용요금 메뉴에서 확인.']),
 dict(id='vworld_링크나인', findings={
  'phone':fact('031-831-0900','https://www.linknine.co.kr/','골프장 주소 옆 대표전화 확인.'),
  'green_fee':fact({'period':'2026-09-14/2026-09-30','holes':18,'round_format':'9x2','customer':'internet_member','currency':'KRW','weekday_range':[95000,115000],'weekend_holiday_range':[130000,145000]},LN,
      '9월 공지 이미지의 후반 기간 표. 인터넷 회원 18홀(9홀 두 차례) 기준.',
      '시간대별 차등. 9월 24~25일 공휴일 요금 적용. 범위만으로 예산 충족 판정 금지.', 'browser_image_visual'),
  'caddie_fee':fact(140000,LN,'9월 2인 이벤트 주석에 팀 캐디피 14만원 표기.', '해당 2인 이벤트에만 근거가 있음. 일반 4인 캐디피로 확대 적용 금지.', 'browser_image_visual'),
  'cart_fee':fact(80000,LN,'이미지 하단에 카트 1대당 8만원 별도 표기.',method='browser_image_visual')},
  blockers=['월별 공지 본문이 이미지. 캐디피는 이벤트 조건 한정.']),
 dict(id='vworld_알펜시아700', findings={}, blockers=[
  '그린피는 통합예약 실시간 가격 적용; 정적 금액 확정 불가.',
  '추출 본문의 카트피 행이 공란. 이번 확인으로 금액을 확정하지 못함.',
  '같은 공식 페이지에 2~3인 불가와 3인 시 4인 요금 적용 문구가 함께 존재. 3인 허용은 충돌 검토 필요.']),
 dict(id='vworld_젠스필드', findings={}, blockers=[
  '웹 접근 502, 브라우저 ERR_SSL_VERSION_OR_CIPHER_MISMATCH. 보안 설정 변경 없이 조사 보류.',
  '제3자 요금은 공식 검증값으로 채택하지 않음. 정보가 없다는 의미는 아님.'])
]

extras=[
 dict(id='kgba_라데나',field='three_person',**fact(True,'https://www.ladena.co.kr/guide/use','공식 이용안내에 3~4인 플레이 가능 표시.',method='browser_rendered_text')),
 dict(id='vworld_링크나인',field='two_person',**fact(True,LN,'9월 한가위 이벤트에 2인 플레이 조건 명시.',
      '일~목 14시 이후 3부; 추석 전 시간대는 선착순 5팀. 2026년 9월 이벤트로 한정하고 상세 이벤트 재확인 필요.', 'browser_image_visual')),
 dict(id='vworld_알펜시아700',field='three_person',value=None,source=AL,
      evidence='예약 안내는 2~3인 불가, 요금 안내는 3인 시 4인 요금 적용으로 상충.',
      confidence='conflict',checked_at=DATE,status='conflict_hold',auto_apply=False)
]

raw=DB.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
records=json.loads(raw.decode('utf-8-sig')); index={r['id']:r for r in records}
def get(r,path):
    for key in path.split('.'):
        r=r.get(key) if isinstance(r,dict) else None
    return r
for item in results:
    r=index[item['id']]; item['name']=r['name']; item['area']=r.get('area')
    item['baseline']={k:get(r,p) for k,p in FIELDS.items()}
    item['missing_fields']=[k for k,v in item['baseline'].items() if v in (None,'',[])]
    assert set(item['findings']) <= set(item['missing_fields']), item['id']
    for f in item['findings'].values():
        assert f['source'].startswith('https://') and f['evidence'] and f['confidence']
        if isinstance(f['value'],dict) and f['value'].get('period'):
            f['effective_period']=f['value']['period']
summary={k:{'missing':sum(k in r['missing_fields'] for r in results),
            'supported_including_conditional':sum(k in r['findings'] for r in results)} for k in FIELDS}
payload=dict(checked_at=DATE, source_project=str(ROOT), source_db=str(DB), source_db_sha256=digest,
 sample_method='목적 표본 6곳', scope='기본정보 4항목', limits=[],
 summary=summary,results=results,extra_findings=extras)
# Korean descriptions for the user-facing artifact.
payload['sample_method']='공식 URL이 있고 기본 4항목 중 2개 이상 누락된 곳에서 목적 표본 6곳 선정(수도권 3, 강원 2, 충청 1). 무작위 표본 아님.'
payload['scope']='전화번호·그린피·캐디피·카트비의 빈값 검증. 부가조건은 탐색 확인만 수행.'
payload['limits']=['브라우저 및 이미지 수동 확인을 포함하므로 자동수집 성공률이 아님.','조건부 후보 포함, 운영 DB 미반영, 전체 DB 보완율로 일반화 불가.','PAR3·야외 연습장 보유율은 이번 조사에서 검증하지 않음.']
(OUT/'verification.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
assert hashlib.sha256(DB.read_bytes()).hexdigest()==digest
print(json.dumps({'db_unchanged':True,'summary':summary,'candidate_count':sum(len(r['findings']) for r in results),'conditional_count':sum(f['status']=='conditional_candidate' for r in results for f in r['findings'].values())},ensure_ascii=False))
