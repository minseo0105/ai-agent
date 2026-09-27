# ZIP:ON 첫 검토 배치 — 2026-09-27

목표는 "Supabase → Backend → ZIP:ON API" 흐름을 안전한 10건으로 확인하는 것입니다.
이번 문서 작성 시점까지 **DB write는 실행되지 않았습니다**(자격증명 미설정). 배치 파일과 dry-run,
사후 검증 스크립트까지 준비돼 있고 명령 한 개만 남았습니다.

## Backlog: 공식 상세 검증 blocker

`cleanup.seoul.go.kr`가 이 실행 환경의 egress 정책에서 계속 거부됩니다
(CONNECT 403, `connect_rejected`, 2026-09-27T01:42:51Z 확인). 재조사·재시도하지 않습니다.

- 막힌 작업: STILL_AMBIGUOUS 18쌍 공식 판정, 주소 없는 34건 보강, 공식 stage/status/date 보강,
  마천2 reconciliation 판정, VERIFIED 승격.
- 해제 조건: 해당 호스트 허용 후 `python3 -B scripts/verify_zipon_development.py --fetch-official`.
- 이번 배치는 이 blocker와 무관하게 진행 가능한 범위(PARTIALLY_VERIFIED)만 씁니다.

## 1. 선정 10건

`scripts/select_zipon_first_batch.py`가 `pilot_canonical_verified_20260927.json`에서 고릅니다.
필수 조건: `VERIFIED`/`PARTIALLY_VERIFIED`, Canary 아님, `duplicate.class == UNIQUE` 이고 미해결 아님,
공식 external ID·공식 주소·공식 단계·공식 provenance 존재, raw 후보 1건.
순서는 결정적입니다(자치구 round-robin → 재개발 우선 → status 확정 우선 → canonical_id).

적격 pool 122건 중 10건: 강동 4 / 서초 3 / 송파 3, 재개발 7 / 재건축 3.

### 선정 중 발견: 잠재 중복 identity 5건 보류

기존 중복 탐지는 사업명의 구역 토큰이 다르면 쌍으로 묶지 않습니다. 그래서 등록 사업명 안에
프로그램 목록 사업명이 그대로 들어 있는 경우를 놓칩니다. 예:
`천호동 461-31번지 일대 재개발정비사업(천호 A1-2)` ↔ 신속통합기획 목록의 `천호A1-2`.
이 5건은 import하면 같은 사업이 두 행으로 남을 위험이 있어 배치에서 제외하고 공식 상세 확인 대상으로
남겼습니다. 18쌍 판정 파일은 이번에 다시 만들지 않았고, 목록은
`import_batch_01_dryrun_20260927.json`의 `deferred_latent_identity_overlap`에 있습니다.

| 자치구 | 등록 사업명 | 프로그램 목록 사업명 |
| --- | --- | --- |
| 강동구 | 고덕주공9단지아파트 재건축정비사업 | 고덕주공9 |
| 강동구 | 상일동 빌라단지 통합 재건축 | 상일동빌라 |
| 강동구 | 천호동 214-19번지 일대 재개발정비사업(천호 3-1구역) | 천호3-1 |
| 강동구 | 천호동 461-31번지 일대 재개발정비사업(천호 A1-2) | 천호A1-2 |
| 서초구 | 방배대우효령아파트 주택재건축정비사업 조합설립추진위원회 | 대우효령 |

## 2. Dry run — PASS

`data/development/import_batch_01_dryrun_20260927.json`에 14개 필드와 검사 결과가 있습니다.
project_id UUID·유일성, external_id 존재·유일성, 필수 필드, content_hash sha256,
공식 호스트, Canary project_id/external_id 충돌, 배치 내 사업명 포함관계,
그리고 payload가 stage/status/validation_status를 승격하지 않는지 확인합니다.

Canary 충돌 0건, 대체 0건. 배치 레코드는 원본 pilot 레코드와 **완전히 동일**합니다
(`stage: null`, `status: UNKNOWN`, `validation_status: NEEDS_REVIEW`).
정규화된 stage/status는 canonical V2에만 있고 DB로 승격하지 않습니다. 업무상태 승인 워크플로가
아직 없기 때문입니다.

## 3. 안전장치

- `services/development_collector.import_batch`에 `MAX_IMPORT_BATCH = 10`을 추가했습니다.
  요청을 보내기 **전에** 11건 이상이면 `IMPORT_BATCH_LIMIT_1_TO_10`으로 중단합니다.
- 기존 CLI 안전장치(`CANARY_LIMIT_1_TO_10`, 신규 project ref 고정, publishable key 거부,
  기본 실행은 로컬 검사)는 그대로입니다.
- DB delete, Canary update/delete, migration, RPC 변경, RLS 변경은 이번 범위에 없습니다.

## 4. Import — 대기 중

`ZIPON_IMPORT_SUPABASE_URL` / `ZIPON_IMPORT_SUPABASE_KEY`가 이 환경에 없습니다. Secret은 출력하거나
파일에 저장하지 않았습니다. 설정된 환경에서 아래 한 줄만 실행하면 됩니다.

```
python3 -B scripts/import_zipon_candidates.py data/development/import_batch_01_20260927.json --apply-new-db
```

## 5~7. 사후 검증

`scripts/verify_zipon_first_batch.py`가 import 직후 실행할 검증을 담고 있습니다. 모두 읽기 전용(GET)입니다.

- DB: 10건 존재, `validation_status != VERIFIED`, `status == UNKNOWN`, `stage` 미승격, `stage_raw`·주소 보존,
  프로젝트별 공식 source 연결, source `content_hash` 존재, source `validation_status != VERIFIED`,
  프로젝트별 `development_updates` 행 존재, 최신 `to_revision == projects.revision`,
  `development_projects` 총 행 수.
- API: `services.development.search_projects`가 `rpc/zipon_development_search`를 호출하고
  자치구 단독 조회 시 좌표를 보내지 않는지, 사업명/유형/stage/status/validation_status/공식 source가
  응답에 노출되는지.
- 공간 안전성: 검증된 경계 없이 `INSIDE`가 나오면 FAIL. 좌표 없는 사업은 `UNKNOWN`.
- 실거래 연계: 좌표 없는 거래행은 조회를 하지 않고 `relation UNKNOWN` / `status needs_geocode` /
  `EXACT_ADDRESS_COORDINATES_REQUIRED`.

자격증명 없이 지금 실행한 결과: API·연계·공간 안전성 **20개 검사 PASS**, DB 구간 `SKIPPED`.
이 구간은 stub 기반 계약 검증이며 실DB 검증이 아닙니다. import 후 같은 명령을 다시 실행하면
DB 구간까지 채워집니다.

```
python3 -B scripts/verify_zipon_first_batch.py
```

## 8. 자동 업데이트 준비 상태 — CHANGES_REQUIRED

이번 스프린트에서 scheduler는 구현하지 않았습니다. 연결점 점검 결과입니다.

| 단계 | 상태 | 근거 / 부족한 점 |
| --- | --- | --- |
| COLLECT | 있음 | `development_collector.collect()`. 모아타운 소스는 실패 상태로 남아 있음 |
| SNAPSHOT | 있음 | `source.raw_snapshot`, `development_updates.new_snapshot` |
| CONTENT HASH | 있음 | `digest(field_evidence)`, RPC가 직전 update의 hash·URL·candidate를 비교 |
| CHANGE DETECTION | 부족 | `update_kind`가 INITIAL / REVERIFICATION 두 가지만 기록됨. 스키마의 STAGE / STATUS / DETAIL / SOURCE_MISSING 미사용, `previous_stage`·`new_stage`·`previous_status`·`new_status` 미기록, `changed_fields`가 항상 `{candidate_evidence}` 고정 → 무엇이 바뀌었는지 알 수 없음 |
| VALIDATE | 부족 | `validate_records`가 CLI에만 있음. `collect()` 경로에는 검증·격리 없음 |
| CANONICAL UPDATE | 없음 | `development_verify.build`는 수동 스크립트. canonical_id를 담을 DB 컬럼/테이블 없음, 재수집 → canonical 갱신 경로 미연결 |
| DEVELOPMENT_UPDATES | 있음 | RPC가 append-only로 기록, `(project_id, to_revision)` 유일 |
| NOTIFICATION | 없음 | `alert_rules`/`notifications`는 실거래(`신규실거래`) 전용. development_updates 소비자와 규칙 종류 없음 |
| 스케줄 | 없음 | `scheduler.py`에 development job 없음 |
| geocode_cache | 미연결 | 로컬 cache만 있음(적재 가능한 컬럼 구조로 저장) |

### 필요한 변경 (다음 스프린트)

1. 변경 분류용 새 ingest RPC 버전: 실제 필드 diff로 `changed_fields`, stage/status 전이 컬럼,
   `update_kind`를 STAGE/STATUS/DETAIL로 기록. 기존 RPC는 건드리지 않고 새 버전으로 추가.
2. 목록 누락 시 `SOURCE_MISSING` 기록 경로. 행 삭제·상태 전이 금지 제약은 스키마에 이미 있음.
3. `collect()` → `validate_records` → 격리 → canonical 갱신을 한 경로로 연결하고 canonical_id의 DB 위치 결정.
4. development 전용 알림 규칙과 `development_updates` 소비자, scheduler job 등록.

### 권장 운영 주기

| 주기 | 대상 |
| --- | --- |
| DAILY | 공식 신규 고시·공고 탐지 |
| WEEKLY | 사업 목록 및 stage/status 변경 감지 |
| MONTHLY | 전체 정합성·누락·중복 검사 |
| HALF_YEARLY | 전체 source 재검증 |
| 주소/geocode | 최초 또는 주소 변경 시에만 |
| polygon | 신규 사업 또는 boundary 변경 시에만 |

## 9. 테스트

- `tests/test_zipon_first_batch.py` — 27개. write 상한(11건 사전 차단, 빈 배치 차단, 10건 허용),
  선정 조건·결정성·자치구 커버리지, 잠재 중복 보류, dry-run 실패 감지(중복 ID, Canary 충돌,
  stage/status 승격, content_hash, 비공식 호스트, 초과 크기, 사업명 포함관계),
  배치 파일이 원본과 동일함, importer 수용/거부, 경계 없는 INSIDE는 FAIL.
- `tests/test_zipon_verification.py` 46개, `tests/test_zipon_development.py` + `test_development_quality.py` 39개 회귀 통과.
- 골프 테스트, migration/RPC 재테스트, 공식 호스트 접근은 실행하지 않았습니다.
