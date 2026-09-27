# MIGRATION REVIEW — zipon-realestate

작성일: 2026-09-26. 대상: 사용자가 새로 만든 **zipon-realestate** 빈 DB, PostGIS `extensions` schema.

**파일 작성과 오프라인 정적 검사만 완료했다. 어느 Supabase에도 SQL을 실행하지 않았고 데이터 INSERT, 운영 코드 수정, HF/GitHub Secret 변경, 배포를 하지 않았다.** 기존 SQLite 규칙 5건은 읽기 전용으로 컬럼만 확인했으며 복사하지 않았다.

## 기존 ZIP 테이블

`supabase/schema.sql`의 4개 CREATE TABLE을 그대로 가져왔다. PostgreSQL 구문 트리 비교로 타입·기본값·NULL·제약 동일성을 확인했다. SQLite INTEGER/REAL/TEXT는 기존 Postgres 정의의 bigint/double precision/boolean/jsonb에 이미 대응되어 있으므로 SQLite 타입을 그대로 Postgres에 복제하지 않았다.

|테이블|역할|컬럼 및 타입|
|---|---|---|
|alert_rules|공용 관심지역 규칙|id bigint identity PK; region text NOT NULL; lawd_cd text; max_price_100m/min_area double precision NOT NULL; event_type text NOT NULL; supply_type text 기본 전체; property_type text 기본 아파트; enabled boolean 기본 true; created_at text NOT NULL|
|notifications|공용 알림/읽음 상태|id bigint identity PK; event_key text UNIQUE; category/title/message text; is_read boolean 기본 false; created_at text NOT NULL|
|source_snapshots|원천별 최신 스냅샷|source/item_key text 복합 PK; payload jsonb NOT NULL; first_seen_at/last_seen_at text NOT NULL|
|app_settings|자동 실행 및 사이트 접근 설정|key text PK; value text NOT NULL|

기존 날짜 컬럼은 text 유지: `_now()`가 반환하는 문자열을 기존 코드 그대로 저장한다. 이를 UTC 날짜 컬럼으로 조용히 변경하지 않았다. 신규 날짜·시간 컬럼만 date/timestamptz를 사용한다. 기존 코드가 쓰는 app_settings에는 부동산 토글 외에 사이트 접근 설정도 포함되므로, 향후 전환 때 이 데이터를 별도로 확인해야 한다.

### REST 호환성 매핑

|테이블|기존 요청|SQL 대응|
|---|---|---|
|alert_rules|GET select/order, POST 리스트, PATCH enabled, DELETE id|동일 컬럼; SELECT/INSERT/UPDATE/DELETE; identity sequence USAGE/SELECT|
|notifications|GET, POST `resolution=ignore-duplicates,return=representation`, PATCH is_read|event_key UNIQUE; SELECT/INSERT/UPDATE; identity sequence USAGE/SELECT|
|source_snapshots|GET source/item_key, POST, PATCH payload/last_seen_at|동일 복합 PK, jsonb; SELECT/INSERT/UPDATE|
|app_settings|GET key/value, POST `resolution=merge-duplicates`|key PK, value text; SELECT/INSERT/UPDATE|

`/rest/v1/{table}`는 public schema에 그대로 매핑한다. SDK 추가나 Python 코드 변경은 없다. DELETE **문장은 migration에 없다**. alert_rules의 DELETE **권한**은 기존 규칙 삭제 기능 호환을 위해 service_role에만 유지했다.

## 신규 개발정보 테이블

### development_projects

사업 master: project_id UUID PK, project_type, project_name, official_authority/external_id UNIQUE, parent_project_id FK, related_types, sido/sigungu/dong/legal_dong_code/address.

상태: status(ACTIVE/COMPLETED/CANCELLED/SUSPENDED/UNKNOWN), validation_status(UNVERIFIED/VERIFIED/NEEDS_REVIEW/MISSING_FROM_SOURCE/REJECTED). stage/stage_raw/stage_mapping_version은 사업유형별 실제 절차에 맞춰 수집기가 매핑한다. 필수 공통 단계 순서나 추정 단계는 만들지 않았다.

규모·일자: selected_date, notice_date, area_m2, planned_units, planned_floor, planned_far.

공간: location, geometry, location_source/location_verified_at, geometry_source/geometry_verified/geometry_verified_at.

증거·갱신: canonical_source_id, canonical_source_official(항상 true), canonical_source_validation(항상 VERIFIED), confidence_level, field_evidence JSON, source_date, last_verified_at, revision, created_at/updated_at.

유형: MOATOWN, MOAHOUSE, REDEVELOPMENT, RECONSTRUCTION, SHINTONG, MAINTENANCE_AREA, STATION_AREA, DISTRICT_UNIT_PLAN, PUBLIC_HOUSING, URBAN_DEVELOPMENT, TRANSPORT, OTHER.

대표점/경계 없는 사업도 UNKNOWN 상태로 저장 가능하다. 알려진 사업 상태/단계, VERIFIED 데이터, geometry_verified=true에는 같은 사업의 검증된 공식 source FK와 확인시각이 필요하다. 정부 공식 출처라는 주장 자체의 진위까지 DB가 검증하지는 않으며 수집기 검증이 필요하다.

### development_project_sources

**사업 1 : 출처 N**. source_id UUID PK, project_id FK, collection_run_id FK, source_name/source_type/source_url/is_official, generated source_priority, external_id/document_title, published_at/effective_at/collected_at/verified_at/verified_by, validation_status, raw_snapshot JSON, content_hash SHA-256, evidence JSON.

같은 사업·URL·hash·공식여부·검증상태 중복 방지. 공식 근거 priority=100, 기타=10으로 DB가 계산한다. SEARCH_RESULT는 is_official=true가 될 수 없고 프로젝트의 canonical evidence가 될 수 없다. Tavily에서 찾은 공식 원문은 원문을 별도로 확인한 후 OFFICIAL_* 증거로 새로 수집한다. 검색 결과를 이름만 바꿔 승인하지 않는다.

service_role는 SELECT/INSERT만 가능하다. 같은 원문이라도 UNVERIFIED에서 VERIFIED로 승인할 때 기존 행을 수정하지 않고 VERIFIED 출처 행을 추가할 수 있다. 공식 여부가 바뀐 별도 검증 증거도 새 행으로 남긴다. canonical_source_id는 검증된 공식 행만 참조한다. 반복 수집에서 같은 검증상태·동일 hash는 중복 저장하지 않는다. 승인 판단과 프로젝트/이력의 원자적 갱신은 후속 수집기 또는 제한적 승인 RPC에서 구현한다.

### development_updates

update_id UUID PK, project_id FK, source_id+project_id 복합 FK, collection_run_id FK, update_kind, previous_stage/new_stage, previous_status/new_status, from_revision/to_revision, title/description, previous_snapshot/new_snapshot JSON, changed_fields, published_at/effective_at/recorded_at/verified_at, event_hash.

사업별 revision/event hash 중복 방지, service_role SELECT/INSERT만 허용. SOURCE_MISSING 이벤트는 사업 상태·단계가 이전과 같아야 한다. 누락은 validation_status=MISSING_FROM_SOURCE로 다루며 자동 삭제/취소 trigger가 없다. 재등장·상충은 재검토 대상이다.

### development_collection_runs

run_id UUID PK, source_name/source_type/source_url, collector_version, scope JSON, started_at/finished_at, status, dry_run(기본 true), source_complete, new_count/changed_count/unchanged_count/validation_failed_count/missing_count, errors JSON 배열. 건수 음수 금지, 종료 시간 일관성 제약.

dry_run은 실행기 계약이다. DB 컬럼만으로 실행기의 쓰기를 막지는 않는다. 후속 수집기는 dry-run에서 사업/출처/이력을 반영하지 않고 실행 보고만 남기는 구조가 필요하다. 이번에는 실행 보고 INSERT도 하지 않았다.

### geocode_cache

geocode_id UUID PK, normalized_address/address_hash/normalizer_version, provider/provider_version, result_status, location, matched_address/legal_dong_code/pnu/building_id, accuracy, source_url/raw_snapshot/content_hash, collected_at/verified_at/expires_at/retry_after/error_code.

주소hash+정규화버전+provider+provider버전 UNIQUE. 실패/미발견도 TTL 캐시. MATCHED만 좌표 허용, MATCHED면 주소·좌표 필수. 제공자의 좌표 정밀도(건물/필지/도로/동)를 별도 관리한다. locality 수준 좌표로 필지 내부를 확정하면 안 된다. Secret이 포함된 URL/원문/오류를 저장하지 않도록 수집기에서 정제한다.

## PostGIS

- location: `extensions.geography(Point,4326)`. 대표점 거리 및 캐시 좌표.
- geometry: `extensions.geometry(Geometry,4326)` + CHECK로 Polygon/MultiPolygon, 2D, 비어 있지 않음, valid, 경위도 범위 제약.
- SRID 4326(WGS84), 좌표 순서는 경도 x / 위도 y. 국내 투영자료는 원래 SRID를 확인해 ST_Transform으로 변환한 뒤 저장하며, 숫자에 SRID만 붙여 바꾸지 않는다.
- GiST: 프로젝트 location, geometry, `(geometry::extensions.geography)`; 캐시 location.
- 내부: 검증된 경계 + ST_Contains. 정확한 경계 위는 NEARBY(0m)로 분리한다.
- 주변: ST_DWithin(geography, geography, 반경m). 대표점만 있어도 NEARBY는 가능하지만 INSIDE는 금지. 경계 기반인지 대표점 기반인지 UI가 표시해야 한다.
- UNKNOWN: 주소/좌표/경계가 불충분. 완전한 좌표로 반경 밖이라는 결과와 자료가 없다는 결과를 후속 API에서 구분한다.
- 불확실한 경계로 0m가 나와도 NEARBY 참고값이며, 내부 확정 아님. 검증 상태를 함께 표시한다.
- 이번 migration은 타입·제약·인덱스만 만든다. 공간 RPC/새 API는 아직 구현하지 않았다. postcheck에는 가상 geometry CTE 6종의 판정 예제가 있으며 INSERT하지 않는다.

## Security

- 9개 테이블 모두 RLS 활성화. PUBLIC/anon/authenticated/service_role의 기존 테이블 권한을 해당 9개 테이블에서만 회수한 후 필요한 service_role 권한만 재부여한다.
- 기본 4개 테이블은 위 REST 매핑에 필요한 권한. master/run/geocode는 SELECT/INSERT/UPDATE. 출처/history는 SELECT/INSERT만. 신규 테이블에는 DELETE/TRUNCATE 권한을 주지 않는다.
- public/extensions schema USAGE, 기존 identity sequence 2개 USAGE/SELECT만 service_role에 부여한다.
- anon/authenticated 정책을 생성하지 않는다. schema 전체·미래 테이블의 default privilege를 바꾸지 않는다. 외부 API에 extension schema를 노출할 필요가 없다.
- service_role은 RLS를 우회하므로 RLS만으로 append-only를 주장하지 않는다. UPDATE/DELETE/TRUNCATE 권한 미부여가 백엔드 역할의 변경을 막는다. postgres 관리자/소유자의 직접 SQL 수정은 막지 않는다.
- 브라우저는 기존 FastAPI만 호출한다. SERVICE_ROLE_KEY를 NEXT_PUBLIC_*에 넣지 않는다. service_role REST를 쓰는 현재 코드의 데이터 구조를 유지하고 복잡한 Auth/사용자 테이블은 추가하지 않는다. watchlist 사용자별 소유권은 후속 별도 migration에서 nullable owner reference를 검토한다.
- ‘Automatically expose new tables OFF’는 explicit GRANT로 처리한다. Data API ON + public이 Exposed schemas에 있어야 `/rest/v1/table`이 동작한다.
- 참고: https://supabase.com/docs/guides/api/securing-your-api

## 생성 파일

1. `supabase/migrations/20260926_zipon_base_and_development.sql` — 단일 트랜잭션 forward migration.
2. `supabase/review/20260926_zipon_rollback_review.sql` — 검토용 비파괴 접근 차단 rollback. migration 디렉터리에 넣지 않아 자동 forward 실행 방지.
3. `supabase/review/20260926_zipon_postcheck.sql` — 적용 후 읽기 전용 검사/가상 공간 예시.
4. `scripts/validate_zipon_migration.py` — 오프라인 파서·호환성 검사.
5. 이 문서.

rollback은 **스키마 원복이 아니라 API 접근 차단**이다. 테이블/데이터/인덱스를 보존하며 9개 테이블과 2개 sequence의 접근 권한을 회수한다. 실패한 forward는 BEGIN/COMMIT 트랜잭션이 원자적으로 처리하며, Dashboard에 열린 실패 트랜잭션이 남으면 ROLLBACK으로 정리한다. 성공 후 forward를 재실행하면 명시된 권한을 복구한다. 기존 타 프로젝트에 rollback 실행 금지.

`IF NOT EXISTS`는 동일 파일 재실행을 지원하지만 이미 존재하는 서로 다른 테이블/제약을 자동 교정하지 않는다. 새 빈 DB 또는 이 migration이 만든 스키마에서만 사용한다. 적용 전 같은 이름 테이블이 예상과 다르면 중단하고 비교한다.

## 검증 결과

- PostgreSQL parser pglast 7.10으로 forward 65문장, rollback 5문장, postcheck 9문장 파싱 성공. 포함된 DO 블록 PL/pgSQL도 파싱 성공.
- 기존 4개 테이블 CREATE AST 전체(위치정보 제외) 동일: 컬럼·타입·기본값·제약 보존.
- FK 생성 순서: runs → projects → sources → canonical source 복합 FK → updates. geocode 독립.
- 9개 public 테이블, 공간 타입 extensions 명시, geometry/geography용 GiST 및 FK/조회 인덱스 확인.
- RLS·GRANT 범위·append-only·공식 evidence discriminator FK 확인.
- DROP/TRUNCATE/INSERT/UPDATE/DELETE SQL 문장 없음. 일부 GRANT의 UPDATE/DELETE는 권한명이며 데이터 조작 실행이 아님.
- 기존 SQLite를 mode=ro로 스키마만 대조. 앱 런타임 파일/Secrets/DB 변경 없음.
- 제한: 로컬 PostgreSQL/PostGIS 서버 및 psql/Docker 실행기가 확인되지 않아 실제 DDL 실행, 함수/타입 서버 해석, RLS/REST 동작 검증은 하지 않았다. ‘정적 검사 통과’를 ‘새 DB 적용 성공’으로 표현하지 않는다.

재검증: 별도 환경에 `pglast==7.10` 설치 후 `venv/Scripts/python.exe -B scripts/validate_zipon_migration.py --parser-path <파서설치폴더>`. 앱 requirements에는 추가하지 않았다.

## USER ACTION REQUIRED

현재 요청은 작성/검증 단계이므로 **아래는 검토 후 사용자가 직접 적용할 때의 절차**다. 지금 운영 연결을 바꾸지 않는다.

1. Supabase Dashboard에 로그인 → 해당 Organization → **zipon-realestate** 카드 클릭. 화면 상단 프로젝트 이름을 재확인한다. 기존 운영 DB가 아니다.
2. 왼쪽 **Database → Extensions** → postgis 검색 → Enabled 및 schema `extensions` 확인. 이미 켜져 있으므로 다시 설치/이동하지 않는다.
3. **Project Settings → Data API**(UI에서 Integrations → Data API로 표시될 경우 해당 메뉴)에서 Enabled, Exposed schemas에 public 포함 확인. Automatically expose new tables는 OFF 유지. anon/authenticated 권한을 추가하지 않는다.
4. 왼쪽 **SQL Editor → New query**. 먼저 아래 읽기 전용 preflight를 붙여넣고 Run:

```sql
select e.extname,n.nspname as extension_schema
from pg_catalog.pg_extension e
join pg_catalog.pg_namespace n on n.oid=e.extnamespace
where e.extname='postgis';
select table_name from information_schema.tables
where table_schema='public' and table_name in
('alert_rules','notifications','source_snapshots','app_settings','development_projects',
'development_project_sources','development_updates','development_collection_runs','geocode_cache');
```

새 빈 DB면 postgis/extensions 한 행, 대상 테이블 0행이어야 한다. 이미 존재하면 내용을 확인하기 전 forward를 실행하지 않는다.

5. 실행을 결정했을 때 SQL Editor → New query → forward 파일 전체 내용을 붙여넣는다. 쿼리 이름 `ZIPON base and development`. 대상 zipon-realestate 및 postgres 역할 확인 → Run. SQL 파일은 migration만 선택하고 rollback 파일을 함께 붙이지 않는다.
6. 오류가 나면 추가 부분 실행/임의 테이블 수정하지 않고 Secret 없는 오류문과 SQL 위치를 기록한다. 필요 시 SQL Editor에서 `ROLLBACK;` 실행 후 원인 확인. 기존 HF 연결은 계속 유지.
7. 성공하면 **Table Editor → public**에서 9개 테이블 확인. 데이터는 각 0건이어야 한다. 기본 5개 규칙을 수동 입력하지 않는다.
8. SQL Editor → New query → postcheck 파일 전체 → Run. 기대값: 모든 RLS=true, anon/authenticated SELECT=false, service 권한 표대로, 공간 6개 passed=true, 모든 테이블 row_count=0.
9. 여기서 멈추고 결과를 검토한다. HF/GitHub Secrets는 아직 그대로 둔다. 테스트를 위해 공개 정책을 만들거나 service key를 브라우저에 넣지 않는다.

## 다음 단계

1. schema/권한/공간 postcheck 결과 확인. PostGIS 타입·함수 실제 해석이 이때 검증된다.
2. 신규 DB 전용 격리 환경의 requests 클라이언트로 GET `/rest/v1/{table}?select=*&limit=0` 4개 및 새 5개를 확인. 인증값을 로깅하지 않는다. 운영 앱에서 실행하지 않는다.
3. INSERT/PATCH/upsert 호환성은 이번에 실제 실행하지 않았다. 새 DB와 구분된 테스트 환경에서 synthetic 데이터를 사용하는 별도 승인된 smoke test로 확인한다. 이번 작업에는 seed/DML 테스트 SQL을 포함하지 않는다.
4. 사업 최초 적재는 UNKNOWN master → 검증된 source → master 승인/이력 순서. master+history 원자성, revision 충돌, source priority 및 dry-run은 후속 transactional 승인 RPC/수집기에서 구현해야 한다. 지금 schema만으로 자동수집이 작동하는 것은 아니다.
5. 검증 후 기존 로컬 5개 규칙 및 운영 데이터·app_settings 이전 계획을 별도 작성한다. 기존 app_settings는 접근 제어/서명 관련 정보도 사용할 수 있어 무턱대고 복사·공개하지 않는다.
6. 데이터 이전/회귀 검증까지 끝난 뒤에만 사용자의 별도 운영 전환 지시에 따라 HF와 GitHub 연결을 변경한다. 이번 작업은 그 전 단계에서 종료한다.
