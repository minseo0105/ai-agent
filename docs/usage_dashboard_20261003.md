# AI LAB 운영현황

관리자 설정의 운영현황 링크 또는 `/admin/usage`에서 조회한다. 기존 관리자 로그인 토큰을 재사용하며 공개 사용자와 일반 회원은 API에서 차단한다. 운영 DB에는 이 작업으로 어떤 SQL도 실행하지 않았다.

## 수동 적용

이번 대시보드 migration은 `supabase/migrations/20261003_usage_dashboard.sql`이다. 기존 로그 수집 migration `20261002_usage_events.sql`의 usage_events가 존재하는 프로젝트에서 실행한다. 앞선 로그 구축 migration이 미적용이면 먼저 그 설치를 완료해야 한다. 공유 AI LAB 또는 명시적으로 설정한 전용 analytics 프로젝트를 사용하며 ZIPON 전용 프로젝트는 사용하지 않는다.

함수만 추가한다. 기존 테이블·데이터·RLS 정책은 변경하지 않는다. SECURITY DEFINER 함수의 search_path는 빈 값이며 참조 테이블은 명시적으로 public.usage_events로 한정한다. PUBLIC/anon/authenticated의 실행 권한을 회수하고 service_role에만 부여한다. service_role의 원본 테이블 SELECT 권한을 추가하지 않는다. 검증 쿼리는 `supabase/review/20261003_usage_dashboard_validation.sql`에 있다. 롤백은 이 함수만 삭제한다.

## 조회와 장애 격리

Browser → GET /api/admin/usage → FastAPI → GET Supabase usage_dashboard RPC. 브라우저에는 집계 결과와 개인정보 없는 최근 활동 최대 20개만 전달한다. 서비스 키와 관리자 서명 비밀은 서버에만 있다. 인증 키가 없으면 새 키를 생성하거나 app_settings에 쓰지 않고 실패한다.

기간은 today/7d/30d, Asia/Seoul 자정부터 현재까지다. 최대 30초 서버 캐시를 사용하며 한국 날짜가 바뀌면 무효화한다. 화면 진입·기간 변경·새로고침만 조회한다. 자동 폴링이나 유료 외부 API 호출은 없다. 한 프로세스에서 DB 조회는 한 번만 실행하고 추가 요청을 대기열에 쌓지 않는다. DB 조회 총 제한 2.5초, HTTP 제한 2초, 응답 512 KiB, 실패 후 5초 대기다. 기간 내 이벤트가 100,000개를 넘으면 축약한 잘못된 수치 대신 짧은 기간 선택 안내를 표시한다.

집계 실패/미설치/시간 초과는 503과 안내로 표시한다. 실패를 0건으로 바꾸지 않는다. 핵심 서비스는 대시보드 API나 집계 함수에 의존하지 않는다. 기존 수집 큐·시간 제한·실패 시 폐기 동작은 유지한다.

## PAGE TRACKING

| 경로 | 표시명 |
|---|---|
| / | AI LAB 홈 |
| /realestate | ZIP:ON |
| /golf | Golf |
| /golf/club | Golf · 골프장 상세 |
| /dreamcar | 내차에서 드림카까지 |
| /report | 보고서 작성기 |
| /saju | AI 사주 · 대운 분석 |
| /car-selector | 차량 선택기 |
| /gif | GIF 변환기 |
| /other | 기타 페이지 |

기존 수집기는 미등록 경로를 /other로 정규화하고 쿼리를 제거한다. 따라서 과거 미등록 URL을 복원할 수 없다. DB에 이미 존재하는 안전한 단일 정적 경로는 집계에서 버리지 않고 경로명으로 표시한다. 민감할 수 있는 동적 경로는 /other로 표시한다. 관리자 페이지는 수집하지 않는다. 기존 경로 변경 중복 방지로 StrictMode·일반 재렌더·같은 경로 재마운트는 page_view를 추가하지 않으며 다른 경로를 거쳐 돌아오면 새 조회다.

## SERVICE FUNNEL / DEFINITIONS

- 방문 세션: 선택 기간에 page_view가 있는 익명 session_id의 distinct 수. 사람 수가 아니다. 페이지별 세션은 해당 경로, 서비스별 세션은 해당 서비스 기준이다.
- 페이지 조회: page_view 이벤트 수. 한 세션의 재방문은 조회를 늘릴 수 있다.
- 기능 실행: ZIPON address_search/trade_search/subscription_search와 Golf golf_search 이벤트 수. 반복 실행을 포함한다.
- 기능 사용률: 해당 서비스를 방문한 세션과 기능을 실행한 세션의 교집합 / 서비스 방문 세션. 기간 내 방문이 없는 검색 세션은 분자에서 제외한다. 분모 0은 —다.
- ZIPON 이벤트 흐름: 진입 세션 → 부동산 검색 횟수 → 지도 클릭 횟수 → 사업카드 선택 횟수 → 네이버부동산 링크 이동 횟수. 서로 다른 단위이므로 감소형 전환율 퍼널로 해석하지 않는다.
- Golf 이벤트 흐름: 진입 세션 → 골프장 검색 횟수.
- 별도 세션 퍼널: 같은 서비스·세션에서 기간 안에 진입 → 검색 → 지도 또는 카드 → 네이버 이동 순서로 발생해야 다음 단계에 포함한다. Golf는 앞 두 단계다. created_at, id 순으로 판정하며 단계별 한 번만 센다. 기간 이전 진입이나 누락 이벤트 때문에 실제보다 적게 집계될 수 있다.
- 일별 세션은 날짜별 distinct이므로 기간 distinct와 일별 합계가 다를 수 있다. 최근 활동은 한국 시간으로 표시한다.

## EVENT COVERAGE

COLLECTED: 등록 페이지의 page_view, ZIPON 검색/지도/카드/네이버·공식 링크, Golf 검색, 서버가 수집한 API 오류.

NOT_INSTRUMENTED: 다른 서비스의 핵심 기능, ZIPON 지역 선택만 변경하는 동작, Golf 출발지·정렬 방식별 메타데이터. Golf 정렬 변경으로 검색이 다시 실행되면 검색 횟수에는 포함된다. 상세 확인은 사업카드 선택 기준이다. 미수집 기능은 null/NOT_INSTRUMENTED와 ‘준비 중’, 수집 중이지만 이벤트가 없으면 실제 0으로 구분한다.

NEW_EVENTS_ADDED = NONE. 기존 수집 방식을 늘리지 않았다. 검색어·주소·IP·User-Agent·사용자 식별정보는 추가 수집하지 않고 세션 ID도 화면에 노출하지 않는다.

## 검증

- 로컬 PostgreSQL 호환 PGlite: 34개 가상 이벤트로 경로/세션/액션/순서 퍼널, 한국 날짜 경계, 최근 20개, RLS와 역할별 권한, read-only 트랜잭션, 100,001건 거부 검증 통과.
- Python 신규 16개 테스트 통과: 인증·개인정보 제외·집계·캐시·조회 격리·실패 처리.
- Chrome production export: 공개/일반 회원 차단, 관리자 KPI·66.7% 사용률, 7/30일, 추가 API 없는 서비스 필터, 최근 20개, 오류 시 수치 제거, 360/390/1280px 가로 넘침 없음. 모바일/데스크톱 스크린샷은 로컬 reports에 보관.
- 정적 production build 및 TypeScript 검사 통과.
- 전체 Python 1,023개: 1,014 통과, 기존 실패 6개·오류 1개, 누락된 공식 경계 자료로 skip 2개. 기존 golf_freshness/golf_master_adapter/golf_service_pool 실패이며 이전 기준 코드에서도 확인된 항목이다.

테스트는 로컬 가상 자료와 외부망 차단 환경에서 실행했다. 운영 DB/실사용 자료 검증과 배포 후 확인은 수동 적용 이후에 한다.
