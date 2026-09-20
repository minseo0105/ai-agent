# 골프장 추천 MVP — STEP 1~4

> 현재 화면은 [STEP 5-B 안내](golf_step5b.md)를 따른다. 아래는 초기 단계 기록이며, 현재 페이지에서는 외부 LLM과 후기 JSON 저장을 사용하지 않는다. 현재 검증에 아래의 이전 분석 CLI를 실행하지 않는다.

## 현재 범위

- 기존 AI 실험실에 독립 페이지 추가. 기존 서비스 파일은 변경하지 않음.
- 수도권 골프장 10곳의 공공데이터 기본정보, 이름 검색, 저장 분석 열람.
- 레이크사이드CC 한 곳의 명시적 후기 분석 버튼과 CLI.
- Naver 블로그/웹 검색, 중복·광고 선별, OpenAI 근거 추출, 코드 검증, 로컬 JSON 저장.
- 자연어 추천( STEP 7 ), Kakao 지도( STEP 8 ), 10곳 분석 확대( STEP 6 )는 아직 제공하지 않음.
- STEP 4 실데이터 검증은 Naver 키 등록 전까지 미완료. 모의 결과를 실제 분석으로 등록하지 않음.

## 기본정보 출처

문화체육관광부 전국 골프장 현황, **2024-12-31 기준** CSV에서 추출.
포털 수정일과 자료 기준일은 다르므로 화면에는 자료 기준일을 표시함.

https://www.data.go.kr/data/15118920/fileData.do

레이크사이드CC(54), 남서울CC(18), 태광CC(36), 한성CC(27), 수원CC(36),
골드CC(36), 코리아CC(27), 88CC(36), 기흥CC(36), 아시아나CC(36).
괄호는 원자료 홀수. 레이크사이드/태광은 같은 주소의 회원제·대중제 행을 합산함.
코리아대중CC는 별도 주소이므로 코리아CC에 합산하지 않음.
원본 행의 이름·주소·홀수·구분과 조회 시각을 각 레코드에 보존함.
전화·좌표·Kakao ID·지도 링크는 확인 전이므로 null.
수도권 전체를 대표하는 표본은 아님. 용인권에 편중된 첫 품질검증 표본임.

## 키 등록

기존 `.streamlit/secrets.toml`의 **최상위**에 아래 이름을 사용.
TOML의 `[realestate]` 같은 섹션보다 위에 작성해야 최상위 키가 됨.

```toml
OPENAI_API_KEY = "발급받은 값"
NAVER_CLIENT_ID = "발급받은 값"
NAVER_CLIENT_SECRET = "발급받은 값"
# STEP 8에서 사용
KAKAO_REST_API_KEY = "발급받은 값"
```

기존 OPENAI_API_KEY가 있으면 중복 작성하지 않음. 키를 코드·로그·Git에 넣지 않음.
네이버 개발자센터 애플리케이션의 검색 API 권한이 필요함.
키 변경 후 실행 중인 Streamlit은 재시작이 필요할 수 있음.
선택 설정 `GOLF_OPENAI_MODEL`로 골프 기능의 모델만 변경 가능.
기본값은 현재 앱과 동일한 `gpt-5.6-terra`. 실제 모델 접근권한은 실호출로 확인 필요.

## 실행

프로젝트 루트에서:

```powershell
.venv/Scripts/python.exe -m streamlit run app.py
# 네트워크 호출 없이 키 유무만 확인, runtime/live_test_report.json 작성
.venv/Scripts/python.exe scripts/prepare_golf_data.py --club lakeside
# Naver 최대 12회 + OpenAI 최대 1회. 한 골프장만 분석.
.venv/Scripts/python.exe scripts/prepare_golf_data.py --club lakeside --analyze
# 공공 기본정보 10곳만 재가져오기. 후기 API 호출 없음.
.venv/Scripts/python.exe scripts/prepare_golf_data.py --build-catalog
```

CLI의 기본 대상은 레이크사이드. 다른 ID 지정은 운영자의 명시적 단일 실행이며
현재 UI는 레이크사이드만 분석 가능하게 제한함. 일괄 분석 명령은 없음.

## 호출·저장 정책

- 일반 이름 조회, 카드/상세 열람, 탭 전환: 외부 API 0회.
- 후기·난이도·페어웨이·그린·시설·캐디 6검색어 × blog/webkr = 최대 12회.
- 검색당 10건, 최대 120개 원시 검색 결과. 블로그는 최신순, 웹은 API 제공 순서.
- 페이지네이션/숨은 재시도 없음. 중복 URL의 서로 다른 요약은 한 문서로 병합.
- 명확한 경험 표현 및 게시일로 우선순위를 정해 최대 48개 문서를 AI에 전달.
- 후보가 없으면 OpenAI 호출 없이 모든 항목을 정보 부족으로 저장.
- 실제 원시 수집 수(raw_result_count), 고유 URL 수(unique_result_count),
  AI 입력 문서 수(candidate_count), 채택 후기 수(review_count), 독립 출처 수를 구분.
- Naver `total`은 검색어별 추정 전체 결과 수로만 보관하며 실제 수집 수로 합산하지 않음.
- 런타임 파일: `data/golf/runtime/<club_id>.json`. 실제 시도 보고서: `runtime/live_test_report.json`.
- 배포 포함 seed: `data/golf/analysis_seed.json`. 검증 전에는 빈 analyses 유지.
- 같은 골프장 분석의 프로세스/세션 중복은 파일 잠금으로 차단. 성공 후 5분 재호출 제한.
- API/검증 오류 시 기존 JSON 유지. 임시 파일 작성 후 원자적으로 교체.
- 프로세스 강제 종료로 `.lock`이 남으면 실행 중인 분석이 없는지 확인한 뒤 해당 lock만 삭제.
- Streamlit Cloud 재배포/인스턴스 변경 시 runtime 파일은 유실 가능.
  `AnalysisRepository`의 get/save/analysis_lock 경계로 향후 영구 저장소 교체.

## 분석 규칙과 한계

Naver description은 원문 전체가 아닌 검색 요약이다. 원문 크롤링은 하지 않는다.
https://developers.naver.com/docs/serviceapi/search/blog/blog.md
https://developers.naver.com/docs/serviceapi/search/web/web.md

1. URL 정규화: 모바일/PC Naver 블로그 및 PostView 주소 통합.
2. 동일 URL의 검색어별 요약 병합, 다른 URL의 거의 동일한 요약도 중복 제외.
3. 대상 이름 불일치, 유사 골프장 혼동, 광고/협찬/예약·회원권 홍보, 짧은 요약 제외.
4. AI가 실제 경험 여부와 평가항목별 직접 인용문을 구조화 출력.
5. 입력 ID의 누락/중복/발명은 전체 분석 실패 처리.
6. 인용문이 실제 요약에 없거나 경험 표현·항목·코스명이 확인되지 않으면 해당 근거 제외.
7. 동일 작성자는 항목당 1회 기여. 작성자를 알 수 없는 동일 사이트는 1개 출처로 보수적으로 계산.
8. 독립 근거 2개 미만이면 정보 부족. 의견이 분산되거나 큰 반대 의견이 있으면 평가가 엇갈림.
9. 결과 라벨·건수·신뢰도·요약은 검증한 근거로 코드에서 계산.
   snippet 분석 신뢰도는 최대 medium이며, high/매우 긍정적 등 강한 결론은 제공하지 않음.
10. 코스별로도 독립 근거 2개 이상인 항목만 저장.

항목 필드: label / evidence_count / confidence / evidence_ids / summary.
evidence에는 출처 URL·제목·요약·게시일·experience_quote 등을 보존.
observations에는 aspect / value / quote / course / evidence_id를 저장.
summary는 AI가 추출한 근거를 코드에서 요약한 문장으로, 별도 자유 생성하지 않음.
넓은 페어웨이나 빠른 그린은 무조건 장점/단점으로 간주하지 않음.

한계: 정규식 광고 판별은 오탐/누락 가능. 경험표현 기준이 엄격하여 유효 후기도 제외될 수 있음.
인용문 일치 검사는 의미 해석의 정확성까지 보증하지 않으므로 수동 리뷰가 필요.
발행일이 실제 라운딩 날짜는 아님. 오래된 글은 최신 운영 상태를 보증하지 않음.
회원제·대중제/코스별 경험이 섞일 수 있으므로 첫 검증에서 코스 구분을 특히 확인해야 함.
실제 Naver/API 응답과 모델 동작은 키 등록 후 검증해야 하며 모의 테스트로 대체할 수 없음.

## 검증

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_golf.py -v
```

테스트는 합성 입력만 사용하고 임시 저장소에서 실행한다. 실제 후기 API를 호출하지 않는다.
Streamlit AppTest로 키 누락 상태의 페이지·검색·상세·추천 준비 화면 및 API 무호출을 확인한다.
모바일 실제 브라우저 QA와 전체 기존 서비스 기능 회귀 검증은 STEP 9~10에서 수행한다.

## 다음 단계 진입 기준

Naver 키 등록 후 레이크사이드 실수집 실행 → 검색어별 수집량, 제외 근거, 항목별 인용문 수동 확인.
6개 핵심 항목의 근거 커버리지, 광고 누락/정상 후기 오탐, 코스 혼동 여부를 기록한다.
캐디/시설 등 지속적으로 정보 부족인 항목은 그대로 노출하며 숫자를 채우지 않는다.
검색어 보완·수집 상한 조정은 실제 결과에 근거해서 결정한다.
검증한 레이크사이드 JSON만 seed에 반영한 다음 10개 확대를 진행한다.
