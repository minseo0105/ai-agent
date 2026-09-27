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
