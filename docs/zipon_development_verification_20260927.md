# ZIP:ON 정비사업 공식 검증 — 2026-09-27

이번 작업은 DB write가 없습니다. migration / RPC / postcheck / REST compatibility / Canary import는
실행하지 않았고, 실제 Supabase(`zipon-realestate`, ref `nnxtkvjpzqqhjlgnprzo`)에 이미 적용된 상태를
그대로 전제했습니다. 산출물은 전부 로컬 파일입니다.

## 외부 공식 소스 접근 결과

이 실행 환경의 egress 정책이 `cleanup.seoul.go.kr`를 차단합니다(프록시 CONNECT 403 → `ProxyError`).
공식 상세정보 1차 소스에 접근할 수 없어 **상세페이지 기반 검증(VERIFIED)은 0건**입니다.
대신 이미 수집해 둔 공식 목록 raw evidence(`pilot_20260927.json`)에서 얻을 수 있는 공식 사실을 전부
추출했고, fetch 경로는 완성해 두었습니다.

- 공식 목록 페이지 요청: 1회 시도 / 0회 성공. 같은 호스트의 남은 4개 URL은 재시도하지 않고
  `SKIPPED_HOST_UNAVAILABLE`로 기록했습니다.
- 상세 endpoint는 추측하지 않습니다. 목록 페이지 markup의 `cafeOpenPopup(external_id)` 정의에서
  실제 경로를 읽어내는 `discover_detail_endpoint()`를 구현했고, 페이지를 못 읽었으므로
  `endpoint_confirmed=false`로 남겨 두었습니다.
- 모아타운(`news.seoul.go.kr/.../policy/status`)은 이전 수집의 `ConnectTimeout` 그대로 NOT DONE입니다.
  확인된 공식 대체 소스가 없어 collector를 바꾸지 않았고, 건수도 만들지 않았습니다.

## 산출물

| 파일 | 내용 |
| --- | --- |
| `data/development/pilot_canonical_verified_20260927.json` | canonical V2 183건 (원본 파일 미변경) |
| `data/development/pilot_duplicate_resolved_20260927.json` | 18쌍 재판정 결과 + 근거 |
| `data/development/pilot_verification_report_20260927.json` | 전체 검증 리포트 |
| `data/development/import_manifest_verified_20260927.json` | import 후보 127건 / 13 batch |
| `data/development/cache/official_detail/` | 공식 조회 cache (fetched_at·status·content_hash·parsed_fields·evidence) |
| `data/development/cache/geocode/` | 주소→좌표 cache (geocode_cache 적재 가능한 컬럼 구조) |

코드: `services/development_official.py`, `services/development_geocode.py`,
`services/development_verify.py`, `scripts/verify_zipon_development.py`,
`tests/test_zipon_verification.py`. `services/development_collector.py`는 회귀 수정(아래).

## Identity 재판정 (18쌍)

SAME_PROJECT 0 / DIFFERENT_PROJECT 0 / STILL_AMBIGUOUS 18.

18쌍은 모두 **같은 구조**입니다. 한쪽은 신속통합기획 목록 행(대표지번·공식 ID 없음), 다른 한쪽은
자치구 사업장 목록 행(대표지번·공식 ID 있음)입니다. 공식 ID가 공유되지 않고 상세페이지도 못 읽었으므로
`PROGRAM_LISTING_VS_BUSINESS_REGISTRY` + `OFFICIAL_DETAIL_READ_REQUIRED`로 남겼습니다.
이름 유사도만으로는 병합하지 않습니다.

판정 엔진(`development_verify.adjudicate`)이 실제로 쓰는 근거는 다음 순서입니다.

1. `OFFICIAL_EXTERNAL_ID_MATCH` — 같은 공식 시스템의 동일 external ID → SAME_PROJECT (HIGH)
2. `OFFICIAL_DETAIL_SAME_NAME_AND_ADDRESS` — 상세페이지 사업명+대표지번 일치 → SAME_PROJECT (HIGH)
3. `OFFICIAL_DISTRICT_MISMATCH` → DIFFERENT_PROJECT (HIGH)
4. `OFFICIAL_ZONE_OR_PHASE_MISMATCH` — 1구역/2구역, A/B구역 → DIFFERENT_PROJECT (HIGH)
5. `OFFICIAL_REPRESENTATIVE_LOT_MISMATCH` — 서로 다른 번지 → DIFFERENT_PROJECT (MEDIUM, 검토 유지)
6. 그 외 → STILL_AMBIGUOUS

1·2번 외에는 병합이 일어나지 않고, 3~5번은 테스트로 고정했습니다.

## 공식정보 추출 (183건)

공식 목록 행에서 확보한 값과 provenance:

- identity: `official_project_name` 183, `official_external_id` 149, `source_system` 183
- location: `district` 183, `dong` 149, `lot_address`/`representative_address` 149,
  `road_address` 0 (목록에 없음)
- classification: `official_project_type`(원문 사업구분) 149, `canonical_project_type` 183,
  `program` FAST_TRACK 34
- progress: `raw_stage` 183, `normalized_stage` 183 (미매핑 0)
- status: 공식 종결 단계 근거 19건만 COMPLETED, 나머지 164건 UNKNOWN
- dates: 공식 상세 날짜 0. 목록의 날짜 32건은 컬럼 의미를 확정할 수 없어
  `date_role: UNKNOWN_OFFICIAL_COLUMN`으로만 보존했습니다(지정일·고시일로 승격하지 않음).
- provenance: `source_url`·`fetched_at`·`content_hash`·`evidence_fields` 183건 전부 보존

원문(`raw_candidates`, `observed_stages`, `original_names`, `original_addresses`, `history`)은
canonical V2 안에 그대로 들어 있습니다.

### stage 체계

원문 `raw_stage`와 `normalized_stage`를 분리했고, 공식 용어 표에만 의존합니다. 사업명 문자열로
stage를 추정하지 않습니다. 기본 체계에 실제 데이터에 나오는 공식 단계를 추가했습니다:
`PLAN_DELIBERATION`(심의/통합심의/통심완료/자문중), `PLAN_NOTICED`(정비계획고시),
`IMPLEMENTER_DESIGNATED`(시행자지정), `SAFETY_DIAGNOSIS`(안전진단), `SALES`(분양),
`PARTIAL_COMPLETION`(부분준공인가), `TRANSFER_NOTICE`(이전고시),
`ASSOCIATION_DISSOLVED`(조합해산), `ASSOCIATION_LIQUIDATION`(조합청산).
공식 소스 오타 `정비계회고시`는 매핑하되 원문을 남기고 `SOURCE_TYPO_NORMALIZED`로 표시합니다.

`stage_verified=true`인 경우 `stage_source_url`, `stage_verified_at`, `stage_evidence`(원문 cells +
content_hash), `stage_basis`를 함께 저장합니다. 현재 근거는 전부 `OFFICIAL_LIST_CELL`이며
상세페이지 근거(`OFFICIAL_DETAIL_PAGE`)는 아직 없습니다.

### status 체계

stage와 분리했습니다. 공식 종결 단계(`준공인가`, `이전고시`)만 COMPLETED로 확정했습니다(19건).
`조합청산`·`조합해산`은 완료 후 절차일 수도 있고 무산일 수도 있어 status는 UNKNOWN으로 두고
`status_hypothesis`(`COMPLETED_PROBABLE_POST_TRANSFER`, `AMBIGUOUS_COMPLETED_OR_CANCELLED`)에만
기록했습니다. 목록에 인가 이력이 있다는 것만으로 ACTIVE로 확정하지 않으며(`ACTIVE_LISTED_UNCONFIRMED`),
공식 사이트에서 검색되지 않는다는 이유로 CANCELLED 처리하는 경로는 코드에 없습니다.

## 주소와 dong

주소는 149/183 그대로입니다. 남은 34건은 신속통합기획 목록 행으로 대표지번 컬럼이 없어,
상세페이지 없이는 보강할 수 없습니다. 구역명에서 주소를 만들어내지 않았습니다.
각 주소에 `address_type`(LOT), `address_source`(공식 사업장 목록 대표지번),
`address_source_url`, `address_verified`, `address_verified_at`을 붙였습니다.

`dong`은 47건을 교정했습니다. 기존 collector 정규식이 `강동구`에서 `강동`을 먼저 잡아
강동구 전체 행의 dong이 `강동`으로 저장돼 있었습니다(`고덕동` 등이 정답). dong은 중복 판정의
차단 조건으로 쓰이므로 판정 신뢰도에 직접 영향이 있습니다.

## Geocoding

좌표 0건, `coordinate_verified` 0건, `GEOCODE_REVIEW` 0건, unresolved 183건.
`api.vworld.kr`도 같은 egress 정책으로 막혀 있고 이 환경에 `VWORLD_API_KEY`가 없습니다.
새 유료 API는 가입하지 않았습니다.

구현은 해 두었습니다. 이 프로젝트가 골프에서 이미 쓰는 VWorld를 provider adapter로 재사용하되,
**첫 결과를 좌표로 확정하는 기존 로직은 복사하지 않았습니다.** provider는 후보 목록만 돌려주고,
`evaluate()`가 후보 1건 + accuracy(PARCEL/BUILDING/ROAD_ADDRESS) + 자치구 일치 + 번지 일치 +
서울 bbox를 모두 만족할 때만 EXACT로 인정합니다. 후보가 여러 건이거나 하나라도 어긋나면
`GEOCODE_REVIEW`로 남기고 좌표를 비웁니다. 동일 정규화 주소는 1회만 조회하며,
cache는 `geocode_cache` 컬럼과 같은 모양(`normalized_address`, `latitude`, `longitude`,
`geocode_source`, `geocode_confidence`, `geocoded_at`, `address_used`, `coordinate_verified`)으로
저장해 나중에 그대로 적재할 수 있습니다. 이번에는 Supabase write를 하지 않았습니다.

## 경계(polygon)와 공간 관계

공식 GIS 경계가 없으므로 `verified polygon` 0건, `geometry`는 전부 null입니다. 대표좌표 buffer나
추정 polygon을 만드는 코드 경로가 없습니다. 각 프로젝트의 `spatial_relation_capability`는
좌표가 검증되면 `NEARBY_ONLY`, 없으면 `UNKNOWN`이며, 경계 검증 없이 `INSIDE`가 되는 경로는 없습니다
(테스트로 고정).

## 품질 상태와 import

- `VERIFIED` 0 — 공식 상세페이지로 identity를 읽어야 부여합니다. 목록에 있다는 사실만으로는 부여하지 않습니다.
- `PARTIALLY_VERIFIED` 131 — 공식 소스 + 공식 ID + 공식 주소 + 공식 단계 확인, 상세 identity 미확인
- `NEEDS_REVIEW` 52 — 공식 ID/주소 없음(34) 또는 미해결 중복 후보(36, 중복 포함)

`import_manifest_verified_20260927.json`: import 후보 127건, batch 13개(최대 10건),
`NEEDS_REVIEW` 52건 제외, 이미 DB에 있는 Canary 8건 제외(`existing_canary`로 식별, 재insert 대상 아님).
manifest는 payload를 직접 담지 않고 `payload_source`로 원본 pilot 레코드를 가리킵니다.
canonical JSON을 그대로 importer 입력으로 쓰지 않습니다.

## collector 회귀 (중요)

커밋된 `services/development_collector.py`에서 정규식 escape 3개가 유실돼 있었습니다.

| 위치 | 커밋 상태 | 영향 |
| --- | --- | --- |
| `observed_dates` | `r'd{4}-d{2}-d{2}'` | 날짜 추출 0건 — 저장된 pilot 값(32건)을 재현 불가 |
| 신통 구역명 주소 판정 | `r'[동리가]s*d'` | `천호동 392-9` 같은 지번형 구역명의 공식 주소 유실 |
| identity 공백 처리 | `re.sub(r's+', '', name)` | 실제로는 공백을 지우지 않는 no-op |

날짜·주소 정규식은 수정했습니다. identity는 **수정하지 않고 고정**했습니다
(`IDENTITY_NORMALIZER_VERSION = 'seoul-identity-v1'`). 공백을 지우도록 고치면
`천호동 392-9`, `명일 신동아` 2건의 `project_id`가 바뀌고, 그중 `천호동 392-9`는 이미 실제 DB에
Canary로 들어가 있어 중복 행이 생깁니다. 고정된 identity로 pilot 183건의 `project_id`가
모두 재현되는지 테스트로 검증합니다. 향후 identity 규칙을 바꾸려면 새 버전과 매핑 마이그레이션이
필요합니다.

## 테스트

`python3 -B -m unittest tests.test_zipon_verification` — 46 tests.
official cache / URL·external ID 중복 요청 방지 / 차단 호스트 재시도 금지 / cache secret 미저장 /
stage·status 정규화 / provenance / SAME_PROJECT 강한 근거 / 1구역·2구역·A·B구역 오병합 방지 /
다른 자치구 오병합 방지 / canonical merge provenance / address provenance / geocode cache /
ambiguous geocode 보호 / 대표좌표 INSIDE 금지 / 공식 polygon만 verified / 결정적 재실행 /
DB write 경로 부재 / collector 회귀를 덮습니다.

기존 migration, REST compatibility, PostGIS·RPC postcheck, Canary import는 재실행하지 않았습니다.

## 남은 일

1. `cleanup.seoul.go.kr`를 환경 network 정책에 허용하고 `scripts/verify_zipon_development.py
   --fetch-official` 재실행 → 상세 endpoint 자동 발견 → 18쌍 재판정과 VERIFIED 승격이 한 번에 진행됩니다.
2. 상세페이지로 34건 주소 보강, 공식 날짜(지정/인가/준공) 확보.
3. `api.vworld.kr` 허용 + 기존 VWorld 키로 `--geocode` 실행 → 좌표 및 `GEOCODE_REVIEW` 분류.
4. 공식 GIS 경계 소스 확인 후 boundary 적재(있을 때만).
