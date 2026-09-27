# ZIP:ON 자동 업데이트 1차 구현 — 2026-09-27

기준선: 실DB(`zipon-realestate`, ref `nnxtkvjpzqqhjlgnprzo`)에 Canary 8건 + First Batch 10건 = 18건이
적재된 상태. 이번 작업은 **구현과 테스트까지이며 DB write가 없습니다.** migration/RPC/RLS 재실행도 없습니다.

목표는 "공식 데이터의 변경을 안전하게 탐지·기록하되, 검증되지 않은 정보가 기존 canonical 데이터를
훼손하지 않는" incremental pipeline입니다.

## 1. 파이프라인 연결

`services/development_pipeline.py`가 전 단계를 잇습니다.

```
COLLECT            development_collector.collect() / 저장된 공식 snapshot
  ↓
SNAPSHOT           record.source.raw_snapshot, field_evidence
  ↓
CONTENT HASH       listing_digests()  = 목록별 snapshot hash
  ↓
CHANGE DETECTION   detect_change()    = kind + changed_fields + stage/status 전이
  ↓
VALIDATE           review_decision()  = 격리 사유 판정
  ↓
CANONICAL UPDATE   canonical_update() = 빈 칸만 채움 / HISTORY_ONLY / INSERT
  ↓
DEVELOPMENT_UPDATES  zipon_ingest_candidate_v2 · zipon_record_source_missing
```

### 비용 절감이 1순위

`plan()`은 목록 snapshot hash를 먼저 비교합니다. hash가 그대로인 목록의 행은 **상세 검증 대상에서
빠지고 write도 계획되지 않습니다.** 행별 `content_hash`가 같은 경우도 같습니다. 상세 검증은
`INITIAL / STAGE_CHANGE / STATUS_CHANGE / DATA_CHANGE`만 받고, job별 `detail_budget`으로 한 번 더 제한합니다.

18건 기준선에 동일 목록을 넣은 dry run 결과: `UNCHANGED 18`, 상세 검증 0건, write 0건.

## 2. 새 RPC (기존 RPC 미수정)

`supabase/migrations/20260927_zipon_incremental_update_rpc.sql`

- `public.zipon_ingest_candidate_v2(p_project, p_source, p_expected_revision, p_change, p_run_id)`
- `public.zipon_record_source_missing(p_project_id, p_reason, p_run_id)`

기존 `public.zipon_ingest_candidate`는 그대로 남아 있고 이 파일에서 재정의하지 않습니다.
두 함수 모두 SECURITY INVOKER, `search_path=pg_catalog,public,extensions,pg_temp` 고정,
PUBLIC/anon/authenticated REVOKE + service_role만 EXECUTE입니다. `ALTER TABLE`, `CREATE POLICY`,
`DROP`, `DELETE FROM`, `TRUNCATE`는 없습니다. 아직 적용하지 않았습니다.

v1과 달라진 점:

1. 필드 diff를 **서버에서 계산**해 `changed_fields`에 기록합니다. 호출자가 보낸 분류는 참고값이고,
   서버 계산이 우선입니다.
2. `update_kind`를 분류하고 `previous_stage`/`new_stage`/`previous_status`/`new_status`를 채웁니다.
3. 빈 master 컬럼만 공식 후보값으로 채웁니다(`dong`, `address`, `area_m2`, `planned_units`).
   기존 값은 덮지 않고, `validation_status='VERIFIED'` 행은 건드리지 않습니다.
4. 후보가 `status`/`stage`/`validation_status`를 올려 보내면 `22023`으로 거부합니다.
5. 검토 필요(`p_change.review_required`)면 master를 건드리지 않고 `review_required`를 반환합니다.

master UPDATE가 손대는 컬럼은 `dong, address, area_m2, planned_units, revision, updated_at` 6개뿐이며
테스트가 이를 고정합니다. `status`, `stage`, `validation_status`, `geometry`, `location`은 어떤 경로로도
쓰이지 않습니다.

### update_kind 이름 매핑

스키마의 `development_updates.update_kind` CHECK는
`INITIAL / STATUS / STAGE / GEOMETRY / DETAIL / SOURCE_MISSING / REVERIFICATION`만 허용합니다.
제약을 바꾸는 것은 base schema 변경이라 이번 범위에서 제외했고, 파이프라인 이름을 그대로 유지하면서
DB에는 허용값으로 저장합니다. 파이프라인 이름은 `new_snapshot.change.pipeline_kind`에 함께 남습니다.

| 파이프라인 | DB update_kind |
| --- | --- |
| INITIAL | INITIAL |
| STAGE_CHANGE | STAGE |
| STATUS_CHANGE | STATUS |
| DATA_CHANGE | DETAIL |
| SOURCE_MISSING | SOURCE_MISSING |
| REVERIFICATION | REVERIFICATION |

CHECK에 `STAGE_CHANGE` 등을 추가하고 싶으면 별도 승인된 schema 변경으로 진행하면 됩니다.

## 3. canonical 안전장치

| 상황 | 결과 |
| --- | --- |
| `validation_status='VERIFIED'` 행 | `HISTORY_ONLY`, `protected: [VERIFIED_MASTER]` — downgrade 경로 없음 |
| 기존 값이 있는 필드 | 덮지 않음, `protected: [EXISTING_VALUE_<field>]` |
| 빈 칸 + 공식 후보값 | `FILL_BLANKS`, 채운 필드를 `changed_fields`에 기록 |
| 후보 필드가 비어 있음 | 기존 값 유지(공백으로 지우지 않음) |
| stage 역행 | `REVIEW_REQUIRED: STAGE_REGRESSION`, master 미변경 |
| identity 충돌(project_type/sigungu/공식 ID) | `OFFICIAL_IDENTITY_CONFLICT`, master 미변경 |
| 공식 ID 없음 | `NO_OFFICIAL_IDENTIFIER` — 신규는 quarantine, 기존은 history만 |
| 매핑되지 않은 공식 단계 | `UNMAPPED_OFFICIAL_STAGE`, master 미변경 |

stage 역행 판정은 공식 단계 순위표(`STAGE_ORDER`)로 합니다. 조합해산·조합청산·취소·미확인처럼
순위를 매길 수 없는 용어는 역행으로 판정하지 않습니다(완료 후에도 나타날 수 있는 단계이기 때문).

## 4. SOURCE_MISSING

공식 목록에서 사라진 사업은 `zipon_record_source_missing`으로 **기록만** 합니다.
행 삭제 없음, `status`/`stage`/`validation_status` 변경 없음, 스키마 CHECK가 상태 전이를 금지합니다.
직전 이력이 이미 `SOURCE_MISSING`이면 새 행을 만들지 않고 `unchanged`를 반환해 revision과 이력이
무한히 늘지 않게 합니다. 기록 문구는 `ABSENCE_IS_NOT_CANCELLATION`으로 시작합니다.

파이프라인이 만들 수 있는 호출은 allowlist로 제한됩니다
(`development_collection_runs` POST/PATCH, 두 RPC POST). `DELETE`와 `development_projects` 직접 쓰기는
목록에 없어서 계획 자체가 불가능하고, 테스트가 이를 확인합니다.

## 5. identity quarantine

`services/development_identity.py`를 배치 선정과 파이프라인이 공유합니다.
등록 사업명 안에 프로그램 목록 사업명이 그대로 들어 있으면(`천호동 461-31번지 일대 재개발정비사업(천호 A1-2)`
↔ `천호A1-2`) 신규 후보는 **ingest 전에 격리**하고 RPC 호출을 만들지 않습니다.
이미 DB에 있는 사업이면 증거는 이력으로 남기고 master는 건드리지 않습니다.

`seoul-identity-v1`은 frozen 상태이며 파이프라인은 `project_id`를 재계산하지 않습니다
(`development_pipeline.py`에 `uuid5` 호출이 없다는 것을 테스트로 고정).
Canary 8건과 First Batch 10건은 수정·삭제 대상이 아니고, 동일 목록 refresh는 write를 0건으로 계획합니다.

## 6. Scheduler 구조 (등록은 하지 않음)

`services/development_schedule.py` + `scripts/run_zipon_refresh.py`.
`scheduler.py`는 건드리지 않았습니다.

| job | cadence | 목적 | detail budget | write limit |
| --- | --- | --- | --- | --- |
| daily | `0 7 * * *` | 공식 신규 고시·공고 탐지 | 10 | 10 |
| weekly | `0 8 * * 1` | 사업 목록 및 stage/status 변경 감지 | 30 | 10 |
| monthly | `0 9 1 * *` | 전체 정합성·누락·중복 검사 | 0 | 0 (보고 전용) |
| half_yearly | `0 9 1 1,7 *` | 전체 source 재검증 | 제한 없음 | 10 |

주소/geocode는 최초 또는 주소 변경 시에만, polygon은 신규 사업 또는 boundary 변경 시에만
(`EVENT_DRIVEN`). 정기 sweep에 포함하지 않습니다.

실행 entry point:

```
python3 -B scripts/run_zipon_refresh.py --job weekly            # dry run, 3개 시나리오
python3 -B scripts/run_zipon_refresh.py --job daily --scenario unchanged
```

`--apply`는 `ZIPON_IMPORT_*`를 요구하고, 이번 스프린트에서는 적용을 명시적으로 거부합니다.
계획된 write가 job의 write limit을 넘으면 `WRITE_LIMIT_EXCEEDED`로 멈추고 아무 것도 실행하지 않습니다.

### dry run 결과 (`data/development/refresh_weekly_dryrun_20260927.json`)

| 시나리오 | 결과 |
| --- | --- |
| `official` (공식 pilot 183행 vs 18건) | `UNCHANGED 18`, `INITIAL 165`, quarantine 52, write 113 → `WRITE_LIMIT_EXCEEDED`로 정지 |
| `unchanged` (동일 목록) | `UNCHANGED 18`, 상세 0, write 0 |
| `simulated-change` (로컬 fixture) | `STAGE_CHANGE 3`, `SOURCE_MISSING 1`, `INITIAL 1`, quarantine 1, write 4 |

`simulated-change`는 공식 데이터가 아니라 분기 검증용 로컬 fixture이며
(`official_data: false`, `listing_kind: SIMULATED_LOCAL_FIXTURE`) 다음을 한 번에 보여줍니다.

- 정상 전진(정비계획 수립 → 관리처분인가): `FILL_BLANKS`(planned_units), 기존 `stage_raw`는 보호
- 역행(이전고시 → 추진위원회승인): `REVIEW_REQUIRED: STAGE_REGRESSION`, master 미변경
- VERIFIED 행의 단계 변경: `HISTORY_ONLY`, `VERIFIED_MASTER` 보호
- 목록에서 사라진 사업: `SOURCE_MISSING`, stage/status 동일
- `(천호 A1-2)` 신규 후보: quarantine, RPC 호출 없음

## 7. 알림 consumer (DB write 미연결)

`services/development_notify.py`는 `development_updates` 행을 이벤트로 바꾸는 인터페이스까지만
구현합니다. DB write, requests, rpc 호출이 모듈에 없습니다(테스트로 고정).

- `render_event(update)` → `event_key`, `severity`, `title`, `message`, `changed_fields`,
  `review_required`, `requires_human_review`
- severity: STAGE/STATUS `HIGH`, SOURCE_MISSING `REVIEW`, DETAIL/REVERIFICATION `LOW`,
  검토 필요면 `REVIEW`
- `consume(updates, consumer, seen=...)`는 append-only `event_hash`로 중복 전송을 막습니다
- `CollectingConsumer`(테스트·dry run), `NotificationDraftConsumer`(기존 `notifications` 테이블 모양으로
  만들지만 쓰지 않음)
- SOURCE_MISSING 문구는 "공식 목록에 나타나지 않음 · 사업 취소나 종료를 의미하지 않음"으로,
  부재를 결과로 바꾸지 않습니다

다음 단계는 consumer를 실제 `notifications` insert와 알림 규칙에 연결하는 것이며, 별도 검토가 필요합니다.

## 8. 테스트

- `tests/test_zipon_pipeline.py` 55개: 비용 절감(hash 동일 → 상세·write 0), 변경 분류 6종,
  stage 역행·비순위 용어, VERIFIED 보호, 기존 값 보호, 빈 칸 채움, status/stage/validation 채움 금지,
  identity 충돌, SOURCE_MISSING(삭제 호출 없음·상태 유지), quarantine(신규 미삽입·기존 이력 기록),
  project_id 재계산 없음, allowlist 외 호출 거부, write 상한, 실행 시 결과 집계, 오류 상세 누출 없음,
  18건 기준선 무변경, job 4종 구조, 알림 렌더링·중복 제거, 새 RPC SQL 정적 검사(파싱·권한·허용 컬럼).
- 외부 네트워크 접근은 없습니다. `cleanup.seoul.go.kr`와 VWorld는 차단 상태이며 재시도하지 않습니다.

## 남은 일

1. 새 RPC 2개를 실DB에 적용하고 rollback 가능한 postcheck로 검증(적용 전 검토 필요).
2. 18건 기준선에 `--apply`로 소규모 변경 1회를 실제 기록해 v2 경로를 실DB에서 확인.
3. 알림 consumer를 `notifications`에 연결 + development 전용 알림 규칙.
4. `cleanup.seoul.go.kr` 허용 후 실제 목록 수집을 파이프라인 COLLECT에 연결(현재는 저장된 snapshot).
