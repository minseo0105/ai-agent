# ZIP:ON NAVER Geocoding 연결 (2026-09-27)

개발사업 149건의 주소를 좌표로 바꾸기 위해 NAVER Maps Geocoding을 1순위 provider로
연결했다. 이번 작업에서 **DB write는 하지 않았고, main merge와 운영 배포도 하지 않았다.**
로컬(이 컨테이너)에는 자격증명이 없어 실제 호출은 한 건도 일어나지 않았다.

## 1. 자격증명 (이름만 기록한다)

| 용도 | 환경변수 이름 | 어디에 있어야 하나 |
| --- | --- | --- |
| 지오코딩 Client ID | `NAVER_MAP_CLIENT_ID` | HF Space Secret (서버 전용) |
| 지오코딩 Client Secret | `NAVER_MAP_CLIENT_SECRET` | HF Space Secret (서버 전용) |

값은 이 문서에도, 로그에도, API 응답에도, 캐시 파일에도 남기지 않는다. 자격증명이
없으면 `missing_secrets`에 **이름만** 실린다.

## 2. 엔드포인트와 인증 헤더

```
POST/GET https://maps.apigw.ntruss.com/map-geocode/v2/geocode?query=<주소>&count=10
X-NCP-APIGW-API-KEY-ID: <Client ID>
X-NCP-APIGW-API-KEY:    <Client Secret>
```

- 구 host(`naveropenapi.apigw.ntruss.com`)는 **경로를 못 찾았을 때만**(404 또는 DNS 실패)
  한 번 확인한다. 인증 실패·쿼터 초과로는 재시도하지 않는다. 과금 호출을 두 번 하지 않기 위해서다.
- **확인 못 한 것**: 이 컨테이너의 network egress 정책이 `api.ncloud-docs.com`과
  `docs.ncloud.com`을 차단해서 공식 문서 페이지로 사양을 재확인할 수 없었다. 위 host·경로·헤더는
  문서상 값으로 구현했고, 실제 확인은 자격증명이 있는 Space에서 헬스체크로 해야 한다:
  `GET /api/realestate/geocode/status?probe=true`가 `reachable: true`와
  `coordinate_orientation: "X_IS_LONGITUDE"`를 돌려주면 사양이 맞는 것이다.

## 3. 좌표 축

`x = 경도(longitude)`, `y = 위도(latitude)`. 절대 교환하지 않는다. 응답이 뒤집힌 것처럼
보이면(x가 위도 범위, y가 경도 범위) 조용히 고치지 않고 `SUSPECT_SWAPPED`로 표시해
`GEOCODE_REVIEW`로 보낸다. 서울 밖으로 나가는 좌표도 같이 걸린다.

## 4. 채택 기준 (하나라도 어긋나면 좌표를 버린다)

`addressElements`를 타입별로 펼쳐서 **정확 일치**로 비교한다. substring 비교는
'천호동 3'이 '천호동 30'을 통과시키므로 쓰지 않는다.

| 검사 | 내용 |
| --- | --- |
| `seoul` / `sido_match` | `SIDO`가 서울특별시 |
| `district_match` | `SIGUGUN`이 요청한 자치구와 같음 |
| `dong_match` | `DONGMYUN`이 요청한 동과 같음 |
| `lot_match` | `LAND_NUMBER`가 요청한 번지와 같음 |
| `road_match` / `building_number_match` | 도로명 주소일 때 `ROAD_NAME`·`BUILDING_NUMBER` |
| `not_a_region_centroid` | 번지도 건물번호도 없는 요청은 EXACT가 되지 않음 |
| `accuracy` | 번지→`PARCEL`, 건물번호/도로명→`ROAD_ADDRESS`, 둘 다 없으면 `REGION`(불채택) |
| `axis_order` | x=경도, y=위도 |
| `bounds` | 서울 bbox 내부 |

후보가 2건 이상이면 첫 결과를 채택하지 않고 `MULTIPLE_PROVIDER_CANDIDATES`로 검토한다.
구청·주민센터·동 중심점 수준의 응답은 `REGION`이라 구조적으로 채택되지 않는다.

Provider 우선순위: **NAVER → Kakao → VWorld**. 자격증명이 있는 첫 provider를 쓰고,
없으면 `NO_GEOCODER_CREDENTIAL_CONFIGURED`로 끝낸다(호출하지 않는다).

## 5. 실행 방법

```bash
# 자격증명만 확인. HTTP 호출 없음
python scripts/geocode_zipon_development.py --check-config

# 무해한 샘플 주소(서울시청) 1건으로 인증·엔드포인트·좌표 축 확인
python scripts/geocode_zipon_development.py --check-connectivity

# 149건 큐만 만든다. provider 호출 없음 (기본값)
python scripts/geocode_zipon_development.py --dry-run

# provider 실제 호출. 그래도 DB write는 없다
python scripts/geocode_zipon_development.py --live
```

출력은 `TOTAL / ACCEPTED / GEOCODE_REVIEW_REQUIRED / GEOCODE_FAILED / PENDING_PROVIDER`
집계와 채택 건별 `project_id · canonical_address · latitude · longitude · matched_address ·
geocode_confidence`이며, 전체는 `data/development/geocode_queue_20260927.json`에 남는다.

헬스체크: `GET /api/realestate/geocode/status` → `{provider, configured, reachable, ...}`.
`probe=true`를 주면 샘플 주소 1건을 실제로 호출한다(유료 쿼터를 쓰므로 결과를 5분간 재사용).

### 2026-09-27 로컬 실행 결과

```
{"mode": "DRY_RUN", "db_write": false, "provider": null,
 "blocker": "NO_GEOCODER_CREDENTIAL_CONFIGURED",
 "total": 149, "accepted": 0, "review_required": 0, "failed": 0, "pending": 149}
```

이 컨테이너에는 NAVER/Kakao/VWorld 자격증명이 하나도 없다. 그래서 149건 전부
`PENDING_PROVIDER`이고 좌표는 한 건도 만들지 않았다. 실제 조회는 Secret이 등록된
Space에서 해야 한다.

## 6. DB 반영은 별도 단계 (아직 실행하지 않음)

`scripts/apply_zipon_geocode.py --check-config | --dry-run | --apply`

- 쓰기 경로는 새 RPC `public.zipon_set_project_location` **하나뿐**이다
  (`supabase/migrations/20260927_zipon_geocode_location_rpc.sql`, **아직 적용 안 함**).
  RPC는 `location`, `location_source`, `location_verified_at`, `field_evidence.location`,
  `revision`만 쓴다. `geometry`·`geometry_verified`·`status`·`stage`·`validation_status`·
  `canonical_source_id`는 건드리지 않는다.
- 거부 사유는 고치지 않고 그대로 돌려준다: `CONFIDENCE_NOT_EXACT`,
  `UNKNOWN_GEOCODE_SOURCE`, `COORDINATE_OUTSIDE_SEOUL`, `NO_GEOCODE_EVIDENCE`,
  `PROJECT_NOT_FOUND`, `REVISION_CONFLICT`, `LOCATION_ALREADY_SET`, `DISTRICT_MISMATCH`.
- 스크립트 쪽 보호: `project_id` 정확 매칭만(이름·주소 매칭 없음), 이미 좌표가 있으면 skip,
  검증된 폴리곤이 있으면 skip, 자치구 불일치 차단, 배치 10건 상한, 한 건 실패가 전체를
  멈추지 않음, 적용 후 좌표 보유 행수 reconciliation.
- 쓰기 자격증명은 읽기 설정과 섞이지 않는다: `ZIPON_IMPORT_SUPABASE_URL` /
  `ZIPON_IMPORT_SUPABASE_KEY`만 본다.
- 적용 직후 검증용 rollback-only postcheck:
  `supabase/review/20260927_zipon_geocode_location_postcheck.sql` (전부 ROLLBACK).

## 7. 실거래(MOLIT) 주소도 같은 provider

`services/trade_geocode.py`가 같은 provider·같은 판정 기준·같은 캐시를 쓴다. MOLIT
`canonical_address`에는 시도·자치구가 없어서(예: `천호동 423-1`) `region_label`을 붙여
전체 주소를 만든 뒤에만 조회하고, 자치구를 못 만들면 조회하지 않는다. `/api/realestate/trades`의
`include_coordinates=true`일 때만 동작한다(기본 false, 유료 쿼터 보호).

## 8. Dynamic Map(웹 지도) 노출 검토

- NAVER Dynamic Map은 웹 지도 SDK라 **Client ID가 브라우저에 실리는 것을 구조적으로 피할 수 없다.**
  실제 보호 장치는 NAVER 콘솔의 Web 서비스 URL 등록(도메인 제한)이다:
  `https://minseo2-digital-ai-lab.hf.space`
- **Client Secret은 브라우저로 내려가지 않는다.** 서버 지오코딩 전용이다.
  `/api/realestate/map/config`의 `browser_exposure.never_sent_to_browser`에 그 구분을 기록했고,
  프론트엔드 소스에 지오코딩 자격증명 이름이 없다는 것을 테스트로 고정했다.
- 현재 basemap은 여전히 키가 필요 없는 OpenStreetMap이다. NAVER Client ID를 등록해도
  `js_sdk` provider가 조용히 타일 소스로 바뀌지는 않는다(별도 결정 사항).

## 9. 보존 확인

seoul-identity-v1 고정, 기존 130건 canonical / 53건 quarantine / Canary 8 / First Batch 10,
기존 RPC 3종, AI LAB `SUPABASE_*` 설정 — 모두 그대로다. 이번 변경으로 지운 데이터 파일은 없다.

---

# Geocoding Canary 10건 (2026-09-27)

149건 전체 실행 전에 주소 품질이 가장 좋은 10건만 먼저 조회해 좌표 품질과 지도 표시
가능성을 본다. **DB write 없음, migration 없음, 149건 실행 없음.**

## 선정 (`scripts/select_zipon_geocode_canary.py --write`)

DB에 있는 canonical 130건 중 128건이 기본 품질 조건을 통과한다(주소 검증됨 · 지번 주소 ·
동이 주소 토큰에서 나옴 · 원본 주소 1개 · 번지 형태 단순 · 주소가 130건 안에서 유일).
여기서 자치구 quota(강동구 4 · 송파구 3 · 서초구 3)를 `project_id` 순으로 채우되 같은 동은
한 번만 고른다. 결과: **동 10개 전부 다름, 정비사업 유형 2종(재건축 8 · 재개발 2),
번지형(`123-4`) 6건.** 동이 겹치지 않아야 좌표 쏠림 검사와 bbox가 의미를 갖는다.

신속통합기획(FAST_TRACK) 기록은 구조적으로 빠진다 — **34건 모두 주소가 없어서** 애초에
지오코딩 대상이 아니다.

선정 결과는 `data/development/geocode_canary_20260927.json`에 요구된 6개 필드
(`project_id`, `project_name`, `canonical_address`, `district`, `project_type`, `program`)만
담는다. `program`은 10건 모두 null이다(위 이유).

## 실행 (production 1회 호출)

```
GET /api/realestate/geocode/status?probe=true    # 연결 확인 (이미 PASS)
GET /api/realestate/geocode/canary               # 이 10건만 조회
```

10건은 `services/development_canary.py`의 `CANARY`에 고정돼 있다. 배포는 `api/`·`services/`·
`web/`만 Space로 올리고 `data/`는 올리지 않는데, NAVER 자격증명은 Space에만 있으므로
목록이 `services/`에 있어야 실행이 가능하다. 같은 10건을 canonical 파일에서 다시 뽑는
선정 스크립트와 어긋나지 않도록 테스트로 고정했다.

응답 1건당 기록: `candidate_count`, `matched_road_address`, `matched_jibun_address`,
`longitude`, `latitude`, `in_seoul_bounds`, `district_match`, `dong_match`, `lot_match`,
`road_match`, `building_number_match`, `accuracy`, `coordinate_orientation`,
`geocode_confidence`, `outcome`, `acceptance_reason`.

분류는 **ACCEPTED / REVIEW_REQUIRED / FAILED**이고, 자격증명이 없어 아예 호출하지 못한
건은 `PENDING_PROVIDER`로 따로 센다. 시도하지 않은 것을 FAILED로 세면 품질 문제로 읽힌다.

## sanity check

- `district_match` — NAVER `addressElements.SIGUGUN`과 저장된 자치구의 정확 일치.
  **한계를 분명히 한다: 검증된 자치구 경계가 없어 point-in-polygon 판정은 하지 않는다.**
- `district_spread` — 자치구별 채택 좌표의 중심에서 5km를 넘는 점을 표시한다. 경계
  판정이 아니라 분포 점검이다.
- `duplicate_coordinates` — 6자리(약 0.1m)와 4자리(약 11m) 두 격자로 여러 사업이 한 점에
  몰렸는지 본다.
- `coordinate_orientation` — 채택 좌표가 모두 `X_IS_LONGITUDE`인지 다시 확인한다.

채택 좌표가 0건이면 이 검사들의 `passed`는 `true`가 아니라 `null`이다. 빈 집합에
통과 도장을 찍지 않는다.

## 지도 payload

`map`은 기존 `presentation.map_point()`이 만드는 것과 **키 구성이 완전히 동일**하다.
그래서 `ZiponMap.tsx`가 프론트엔드 수정 없이 그대로 marker로 쓸 수 있다.
`bbox` · `center` · `suggested_zoom`(화면은 `fitBounds`를 쓰므로 참고값)도 함께 계산한다.

대표 위치이므로 `boundary_status`는 미확인으로 남고 `allows_inside`는 false가 된다.
`inside_judgement: NOT_PERMITTED_WITHOUT_VERIFIED_BOUNDARY` — 이 Canary에서 INSIDE 판정을
만들 수 있는 경로는 없다. 좌표는 NEARBY와 거리 계산에만 쓴다.

## 2026-09-27 상태

로컬(이 컨테이너)에서는 실행할 수 없다. 두 가지가 각각 막는다:

1. NAVER 자격증명은 Space에만 있다(설계대로).
2. egress 정책이 `minseo2-digital-ai-lab.hf.space`와 `maps.apigw.ntruss.com`을 모두 막는다.

그래서 provider 호출 0회, 10건 전부 `PENDING_PROVIDER`이고 좌표는 만들지 않았다.
판정·분류·지도 payload·sanity 로직은 실제 NAVER 응답 형태를 넣은 18개 테스트로 검증했다
(10건 전부 채택되는 경우, 후보 2건, 동 중심점, 자치구 불일치, 축 뒤집힘, 좌표 중복,
자치구 이탈, provider 오류, 자격증명 없음, 캐시 재사용, 비밀값 비노출).

`/api/realestate/geocode/canary`는 main에 배포된 뒤에 호출할 수 있다.

---

# 전체 개발사업 Geocoding (2026-09-27)

Canary 10건이 9 ACCEPTED / 1 REVIEW_REQUIRED로 끝난 뒤, 주소가 확보된 개발사업 전체로
넘어가는 단계. **DB write 없음, migration 없음, 배포 없음(코드 준비까지).**

## 1. 숫자 정리 (서로 다른 scope를 섞지 않는다)

| 수 | 무엇인가 |
| --- | --- |
| 183 | 공식 목록에서 수집한 원본 후보 레코드. canonical과 1:1이며 병합된 것은 없다 |
| 149 | canonical 중 **주소를 가진** 것 |
| 34 | canonical 중 **주소가 아예 없는** 것 — 전부 신속통합기획(FAST_TRACK) |
| 130 | 이미 Supabase에 들어간 canonical |
| **128** | **DB에 있고 + 주소가 있는 것 = 이번 지오코딩 대상** |
| 2 | DB에 있으나 주소가 없는 것 (둘 다 FAST_TRACK: 천호동 392-9, 마천2) |
| 21 | 주소는 있으나 아직 quarantine이라 DB에 없는 것 |

`130 = 128 + 2`, `149 = 128 + 21`, `183 = 149 + 34`, `53 quarantine = 21 + 32`으로 모두 맞는다.
이전에 말한 "주소 품질 통과 128"은 이 표의 128과 같은 집합이다(그 128건은 전부 주소 검증
완료·지번 주소·단순 번지·동 확보 상태라 추가 품질 필터로 더 걸러지는 것이 없었다).
이전의 "149 source candidates"는 **DB 여부를 따지지 않은** 주소 보유 canonical 전체였다.

대상 128건은 `services/development_geocode_targets.py`에 생성돼 있다. `data/`는 Space로
올리지 않고 NAVER 자격증명은 Space에만 있으므로 목록이 `services/`에 있어야 실행된다.
`scripts/build_zipon_geocode_targets.py`가 canonical 파일에서 같은 표를 다시 만들고,
테스트가 둘이 어긋나지 않는지 확인한다.

DB의 현재 좌표 보유 행 수는 이번 단계에서 조회하지 않았다. apply 단계가 행마다
preflight GET으로 다시 확인하므로 거기서 판단한다.

## 2. 실행 (production, slice 단위)

```
GET /api/realestate/geocode/bulk?offset=0&size=32
GET /api/realestate/geocode/bulk?offset=32&size=32
GET /api/realestate/geocode/bulk?offset=64&size=32
GET /api/realestate/geocode/bulk?offset=96&size=32
GET /api/realestate/geocode/bulk?aggregate=true     # provider 호출 0회
```

- 한 요청 최대 50건(`MAX_SLICE`), 기본 32건. 128건을 한 요청에 태우면 요청이 너무 길다.
- 같은 slice 재호출은 1시간 동안 같은 결과. 주소 캐시가 있으면 provider를 부르지 않는다.
- `aggregate=true`는 **provider를 한 번도 부르지 않고** 캐시만 읽어 전체 보고서를 만든다.
  아직 조회되지 않은 행은 `PENDING_PROVIDER`로 남는다.
- 판정 정책은 Canary와 동일. 후보가 여러 개일 때는 **주소 구성요소 검증을 모두 통과하는
  후보가 정확히 하나일 때만** 그것을 쓰고, 0개거나 2개 이상이면 REVIEW_REQUIRED다.
  첫 후보를 쓰는 경로는 없다.

캐시 관련 실제 결함을 하나 고쳤다: 캐시 행이 10개 열만 저장해서, 캐시에서 되살린 행은
`matched_address`·`accuracy`·`checks`를 잃고 있었다. 그 상태로 sanity를 돌리면 자치구
일치와 좌표 축 검사가 **실패한 것처럼** 보인다. 캐시 열에 `matched_address`, `accuracy`,
`result_status`, `raw_snapshot`을 추가해(모두 Supabase `geocode_cache`에 있는 열) 판정
근거를 함께 저장한다.

## 3. 산출물

| 파일 | 내용 |
| --- | --- |
| `bulk_geocode_result_20260927.json` | 전 행 결과. 요구된 15개 열 |
| `bulk_geocode_review_20260927.json` | REVIEW_REQUIRED만. 공식주소 + NAVER 후보 나란히 |
| `geocode_apply_ready_20260927.json` | ACCEPTED만. apply 단계 입력 |

`scripts/save_zipon_bulk_geocode.py <응답.json> --write`가 만든다. 형식이 다르거나,
`db_write`가 true이거나, 자격증명 모양이 섞였거나, apply 목록에 ACCEPTED 아닌 행이
있거나, 채택되지 않은 행에 좌표가 붙어 있으면 **파일을 만들지 않고 거부**한다.

apply 단계는 `python scripts/apply_zipon_geocode.py --queue data/development/geocode_apply_ready_20260927.json --dry-run`.
기존 좌표·검증된 폴리곤 보호, 자치구 불일치 차단, 배치 10건, reviewed RPC 경유는 그대로다.

## 4. 신속통합기획 34건 (geocoder에 보내지 않는다)

주소가 없는 사업을 검색에 던지면 동 중심점이나 구청 좌표가 돌아온다. 그것이 대표 위치로
굳는 것이 이 프로젝트에서 가장 피하려는 일이므로, 34건은 따로 분석만 한다
(`scripts/analyze_zipon_fast_track.py`, `data/development/fast_track_location_20260927.json`).

| 분류 | 건수 | 뜻 |
| --- | --- | --- |
| ADDRESS_RECOVERABLE_FROM_OFFICIAL_SOURCE | 23 | 이미 가진 공식 텍스트에서 동+번지가 나온다 |
| LOCATION_NAME_ONLY | 10 | 동 이름까지만 알 수 있다 |
| NEEDS_OFFICIAL_DETAIL | 1 | 단서가 없어 자치구 고시/상세를 받아와야 한다 |
| INSUFFICIENT_LOCATION | 0 | — |

23건 중 1건(`천호동 392-9`)은 **사업명 자체가 지번**이고, 22건은 같은 자치구의 사업장
등록 행(주소 검증 완료)과 이름으로 연결된다. **연결은 동일성 검토 대상이며 주소를
canonical로 자동 복사하지 않는다.** 그중 4건은 이름이 가리키는 동과 연결된 등록 행의
동이 달라 `clue_conflict`로 표시했다(고덕주공9↔명일동, 고덕현대↔명일동, 신반포2차↔잠원동,
가락우창↔오금동). 검토자가 먼저 봐야 하는 건들이다.

번지 패턴은 **사업명에서만** 찾는다. 공식 목록 행에는 면적·세대수·연번이 들어 있어
행 전체에 정규식을 걸면 `풍납극동 37`처럼 세대수를 지번으로 읽는다. 실제로 첫 시도에서
그렇게 잘못 읽혔고, 테스트로 고정했다.

## 5. 지도 readiness

`map_readiness`가 ACCEPTED만으로 `mappable_projects`, `bbox`, `center`, `suggested_zoom`,
자치구별·유형별·프로그램별 마커 수를 낸다. point는 대표 위치이므로
`inside_judgement: NOT_PERMITTED_WITHOUT_VERIFIED_BOUNDARY`이고 `allows_inside`는 false다.
FAST_TRACK과 모아타운은 좌표가 없으므로 지도 카운트에서 0이다.
