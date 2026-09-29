# ZIP:ON 사업구역 폴리곤 매칭 검토 (2026-09)

이 문서는 서울시 공식 도시계획사업 공간정보를 ZIP:ON의 사업 130건과 맞추기 위한
준비 상태를 적는다. **운영 DB에 폴리곤을 쓰지 않았다.** 운영 화면의 폴리곤 수는 여전히 0이다.

## 1. 원천

| 항목 | 값 |
| --- | --- |
| 제공 | 서울특별시 (열린데이터광장) |
| 데이터셋 | 도시계획사업 현황(서울플랜+) 공간정보 |
| 데이터셋 ID | OA-22712 |
| 판 | 202609 |
| 파일 | `532_UQ120_도시계획사업(서울플랜+)_202609.zip` |
| 포털 | https://data.seoul.go.kr/dataList/OA-22712/S/1/datasetView.do |
| 법적 성격 | 법적 효력 없음 / 참고자료 |

원천 파일은 받은 그대로 둔다. 압축을 풀어 저장하거나 좌표를 손보지 않는다.
받은 사실은 `data/reference/source_registry.json`에 적는다. zip 자체는 커밋하지 않는다
(`.gitignore`의 `data/reference/*.zip`).

## 2. 이번 실행환경에서의 상태: 원천 미확보

두 가지가 겹쳐 있다.

1. 포털 차단. 이 컨테이너의 네트워크 정책이 `data.seoul.go.kr`와 `datafile.seoul.go.kr`로의
   연결을 거부한다(CONNECT에 게이트웨이가 403).
2. 로컬에 둔 파일은 여기로 오지 않는다. 이 세션은 GitHub에서 새로 clone한 별도 컨테이너에서
   돌고, `data/reference/*.zip`은 `.gitignore` 대상이다. 로컬 작업본에 zip을 두어도
   컨테이너에는 없다(컨테이너 전체를 검색해 확인했다).

근거는 `data/development/polygon_source_acquisition_20260928.json`에 남겼다.

그래서 **비공식 자료로 대체하지 않았다.** 폴리곤을 만들지도, 대표좌표에 버퍼를 씌우지도 않았다.
원천이 있는 곳에서 아래 한 줄을 돌리면 같은 파이프라인이 그대로 돈다.

```
python scripts/analyze_seoul_polygon_source.py \
  --archive "data/reference/532_UQ120_도시계획사업(서울플랜+)_202609.zip" --write
```

원천이 없으면 스크립트는 아무 일도 하지 않고 `SOURCE_FILE_NOT_PRESENT`와 내려받는 방법만 알린다.
두 번째 판부터는 `--if-changed`를 붙인다. `source_sha256`이 같으면 재분석하지 않는다.

## 3. SHP 읽기와 schema 해석

`scripts/analyze_seoul_polygon_source.py`가 하는 일.

- **DBF 인코딩을 단정하지 않는다.** cp949 / utf-8 / euc-kr / latin-1로 각각 열어 보고,
  필드명 **과 앞쪽 20건의 값**에서 한글이 가장 잘 살아나는 것을 고른다. 값까지 보는 이유가
  있다: UPIS는 필드명이 모두 영문이라 필드명만 채점하면 어느 인코딩이든 0점이 되고, 순서상
  먼저 온 것이 뽑힌 뒤 정작 한글인 사업명이 깨진 채로 넘어간다. 그러면 **오류 없이 조용히
  '매칭 0건'** 이 된다. 이번 작업에서 실제로 두 번 겪은 실패라서 둘 다 테스트로 고정했다.
- **필드명을 추측하지 않는다.** 역할마다 어떤 필드를 어떤 근거로 골랐는지 적고, 근거가
  확인된 것만 매칭에 쓴다.

| 근거 | 뜻 | 매칭 사용 |
| --- | --- | :-: |
| `FIELD_NAME` | 필드명 자체가 뜻을 말한다(`사업명`, `SGG_NM` …) | O |
| `SEOUL_DISTRICT_CODE` | 값이 서울 25개 자치구 코드와 정확히 맞는다 | O |
| `CODE_TABLE` | 값의 뜻이 압축 안 코드정의표에 있다 | O |
| `CODE_TABLE_FIELD_LABEL` | 코드정의표가 그 필드의 설명을 적어 두었다 | O |
| `UNCONFIRMED_TEXT` | 한글 값이지만 필드의 뜻을 확인하지 못했다 | X |
| `UNCONFIRMED_CODE` | 코드값인데 풀 표가 없다 | X |
| `UNRESOLVED` / `EMPTY` | 해당 필드가 없거나 비어 있다 | X |

  `UNCONFIRMED`는 표본 값만 적어 두고 매칭에서 제외한다. 확인되지 않은 필드로 EXACT를
  만들지 않는다. 자치구 코드표는 저장소에 이미 검증되어 있는
  `services/realestate_monitor.py`의 25개 코드를 쓴다(새로 만들지 않는다).
- **코드정의표(xlsx / csv)가 있으면 함께 읽는다.** 코드값의 뜻과 필드 설명은 여기서만 온다.
  `PRESENT_SN` / `DGM_NM` / `SIGNGU_SE` / `PROPEL_CD` / `CREATE_DAT`처럼 이름만으로는
  뜻을 알 수 없는 필드가 여기서 해석된다.
- **필드명이 잘려 있어도 찾는다.** 다만 네 글자 미만의 조각으로는 필드를 주장하지 않는다.
  `GU`가 `SIGNGU_SE`에 걸리면 코드값 필드를 이름 필드로 착각하고 자치구가 영영 맞지 않는다.
- **좌표계는 `.prj`에서만 읽는다.** 순서는 ① WKT의 `AUTHORITY["EPSG",n]`, ② pyproj
  `CRS.from_wkt(...).to_epsg()`의 **기본 신뢰도** 결과, ③ 알려진 좌표계 이름,
  ④ 코드는 못 정하더라도 WKT 정의 자체로 변환(`FROM_PRJ_WKT_NO_EPSG`).
  **낮은 신뢰도의 EPSG 추정은 받지 않는다.** 중부원점 계열은 서로 바뀌기 쉽고(5181 ↔ 5186),
  바뀌면 좌표가 수백 m 어긋난 채로 정상처럼 보인다. `.prj`가 없으면 변환하지 않는다.
- **변환 결과가 서울이어야 한다.** 경도 126~128, 위도 37~38을 벗어난 record가 하나라도
  있으면 `CRS_SANITY_FAILED`로 멈추고 **산출물을 쓰지 않는다.** 좌표계를 잘못 읽은 상태로
  매칭 결과를 남기지 않는다.
- record 단위로 다음을 센다: 전체 / Polygon / MultiPolygon / invalid / empty /
  EPSG:4326 변환 성공 / 서울 범위 밖 / 중복 식별자 / 중복 geometry.

## 4. geometry 해석

Shapefile 규약에서 외곽 ring은 시계방향(부호 있는 면적이 음수), 구멍은 반시계방향이다.
이 판정을 뒤집어 읽으면 **서로 떨어진 두 개의 구역이 '구멍 뚫린 한 구역'으로 바뀐다.**
그래서 규약을 그대로 따른다.

- 외곽 ring이 하나면 `Polygon`, 둘 이상이면 `MultiPolygon`.
- 구멍은 자기를 포함하는 외곽 ring에 붙인다.
- 내보내는 GeoJSON은 RFC 7946대로 외곽 반시계 / 구멍 시계로 방향만 맞춘다. 좌표값은 그대로다.
- ring이 닫혀 있지 않으면 `RING_NOT_CLOSED`로 **보고**한다. 닫아서 고치지 않는다.
- 점 4개 미만의 ring은 버린다.

## 5. 130건과의 매칭

신호는 이 순서로 본다: 공식 식별자 → 정규화 사업명 → 사업명 + 자치구 + 법정동 → 지번.
`used_for_matching`이 아닌 필드는 신호를 만들지 않는다.

| 등급 | 조건 |
| --- | --- |
| `EXACT` | 공식 식별자가 같거나, 정규화 사업명이 같고 자치구까지 맞으며 **후보가 하나뿐** |
| `PROBABLE` | 신호는 강하지만 식별자/정규화 사업명 일치가 부족 |
| `AMBIGUOUS` | 후보가 둘 이상이거나, 기존 duplicate/identity 검토 대상 |
| `NO_MATCH` | 안전한 공식 후보가 없음 |

이름이 비슷하다는 이유만으로 `EXACT`가 되지 않는다.
**대표좌표의 폴리곤 포함 여부는 보조 확인일 뿐이며 동일성을 결정하지 않는다.** 그래서
포함 여부는 신호 목록에 넣지 않고 별도 칸(`representative_point_inside_polygon`)에만 적는다.
`seoul-identity-v1`은 FROZEN이고 project identity는 이 작업에서 바뀌지 않는다.
`project_type`과 `program`(FAST_TRACK = 신속통합기획)은 그대로 분리해서 둔다.

### EXACT 추가 검증

EXACT라도 자동 반영 후보가 되려면 geometry가 유효하고 대표좌표가 폴리곤 안에 있어야 한다.
그래서 EXACT를 갈라서 센다.

| 집계 | 뜻 |
| --- | --- |
| `exact_valid_inside` | geometry 유효 + 대표좌표가 폴리곤 안. 자동 반영 후보 |
| `exact_valid_outside` | geometry는 유효하지만 대표좌표가 폴리곤 밖. **후보에서 제외** |
| `exact_valid_no_point` | 좌표가 없어 확인 불가. 후보에서 제외 |
| `exact_invalid_geometry` | geometry가 유효하지 않다. 후보에서 제외 |

제외된 건은 `excluded_reason`에 이유를 적는다. 대표좌표가 폴리곤 밖이면
`distance_to_polygon_m`에 경계까지의 거리를 **원천 좌표계(미터)에서 실제로 재서** 남긴다
(`distance_basis: SOURCE_CRS_METRES`). 미터 좌표계가 아니면 거리를 짐작하지 않고
근거를 `GEOD_NEAREST_VERTEX` 또는 `UNKNOWN_UNITS`로 적는다. 폴리곤 밖으로 나온 EXACT는
자동 반영하지 않고 원인부터 본다: 대표좌표가 대표점일 뿐이라 구역 밖 도로변에 찍혔을 수도,
동명 사업을 잘못 물었을 수도 있다.

### 기존 위험 사례 보호

`fast_track_identity_review_20260928.json`의 IDENTITY_CONFLICT / duplicate_risk 건과
`geocode_gap_review_20260928.json`의 MANUAL_REVIEW 건은 폴리곤이 딱 맞아도 `AMBIGUOUS`로
내린다. 폴리곤으로 동일성을 정하지 않는다. 지금 15건이 여기에 해당한다. 그중 `마천2`와
`마천2재정비촉진구역 주택재개발정비사업`은 둘 다 이미 DB에 있고, 서로 다른 사업인지
같은 사업의 두 표기인지는 사람이 판단할 일로 남아 있다. 자동 병합하지 않는다.

## 6. 산출물 (모두 검토용, DB write 없음)

| 파일 | 내용 |
| --- | --- |
| `data/development/polygon_source_acquisition_20260928.json` | 원천 확보 시도와 차단 근거 |
| `data/reference/source_registry.json` | 어떤 원천을 어떤 판으로 받았는지 + 변경 판정용 hash |
| `data/development/polygon_match_review_20260928.json` | 130건 전체 등급·신호·근거 (원천 확보 후 생성) |
| `data/development/polygon_match_exact_20260928.geojson` | 안전한 EXACT만, `review_only: true` (원천 확보 후 생성) |

`polygon_match_review_20260928.json`에는 `db_write: false`와
`polygon_written_to_production: false`가 항상 들어간다.
GeoJSON에는 `auto_apply_candidate`인 EXACT만 들어간다. 대표좌표가 폴리곤 밖인 EXACT는
review JSON에는 남지만 GeoJSON에는 들어가지 않는다.

### 다음 판을 위한 source metadata

`source_registry.json`에 provider / dataset / dataset_id / 파일명 / 판(version) /
`source_sha256` / 파일 크기 / 기록 시각 / 좌표계와 그 근거 / record 수 /
`schema_fingerprint`(필드 이름·형식·길이의 해시) / 코드정의표 파일명 / 분석 시각을 남긴다.

다음 서울시 ZIP이 들어오면 `--if-changed`로 돌린다. `source_sha256`이 같고 review 산출물이
있으면 `SOURCE_UNCHANGED`로 끝내고, 다르면 다시 분석한다. 자동 다운로드는 이번 작업 범위가
아니다. schema를 먼저 확정하는 것이 목적이다.

## 7. 화면 쪽 안전장치

경계 해석은 `web/src/lib/projectBoundary.ts` 한 곳에서만 한다.
`boundary_status === "OFFICIAL_VERIFIED"`이고 `boundary`를 읽을 수 있을 때만 ring을 돌려주고,
그 외에는 빈 배열이다. 그러면 지도는 면을 그리지 않고 대표 위치를 나타내는 반경 120m 원만 그린다.
구역인 척하는 표현을 만들지 않는다. 검토용 GeoJSON은 운영 화면에 연결하지 않는다.

`Polygon`과 `MultiPolygon`을 모두 받는다. MultiPolygon은 구역마다 면을 하나씩 그린다.
첫 구역만 그리거나 떨어진 두 구역을 '구멍 뚫린 한 구역'으로 합치지 않는다. ring 안에 읽을 수
없는 좌표가 한 점이라도 있으면 그 ring 전체를 버린다. 모양을 짐작해서 이어 붙이지 않는다.

`INSIDE`(정비구역 내부)는 여전히 확인된 경계가 있을 때만 나온다. 대표좌표만으로는
`NOT_DETERMINED`와 안내문("아직 정확한 구역 경계를 확보하지 못해…")이 나온다.

## 8. 파이프라인 검증 방법

공식 파일이 이 환경에 없어서, **UPIS와 같은 모양의 합성 SHP**로 파이프라인을 돌렸다.
영문 필드명(`PRESENT_SN` / `DGM_NM` / `SIGNGU_SE` / `PROPEL_CD` / `CREATE_DAT`),
코드정의표, cp949 및 utf-8 DBF, EPSG:5186, 시계방향 외곽 ring까지 같은 모양이다.
합성 원천은 공식 결과가 아니고 폴리곤으로 쓰이지도 않는다.
`tests/test_zipon_product.py`의 `PolygonPipelineTests` / `PolygonSourceChangeTests`가
매번 그것을 만들어 확인한다.

- 인코딩 탐지(cp949 / utf-8, 값까지 채점), 잘린 필드명, 짧은 조각 거부
- 코드정의표로 코드값과 필드 뜻 해석, 확인 안 된 필드는 매칭에서 제외
- 자치구 코드 → 자치구명(검증된 25개 표)
- `.prj`에서 좌표계 읽기, 낮은 신뢰도 EPSG 거부, WKT 정의만으로 변환, `.prj` 없으면 변환 안 함
- 좌표계가 틀린 원천은 `CRS_SANITY_FAILED`로 멈추고 산출물을 쓰지 않음
- 변환된 좌표가 서울 범위의 (경도, 위도) 순서인지
- `Polygon` / `MultiPolygon` / 구멍 / 닫히지 않은 ring / 빈 geometry
- 중복 식별자·중복 geometry 집계
- 구멍 안의 점은 '내부'가 아님, 경계까지의 거리(미터)
- `EXACT` / `PROBABLE` / `AMBIGUOUS`(후보 2건) / `NO_MATCH` 네 등급
- EXACT인데 대표좌표가 폴리곤 밖이면 후보에서 제외되고 이유가 남는지
- `마천2` 두 건이 폴리곤으로 정리되지 않는지 (보호 대상 15건)
- 안전한 EXACT만 GeoJSON에 들어가고 `review_only`가 붙는지
- 화면 쪽 경계 helper(`Polygon` / `MultiPolygon` / 구멍 / 확인되지 않은 값 / 깨진 좌표)
- 천호1 상세 지도가 서울 기본 중심이 아니라 사업 좌표에서 열리는지
- 스크립트에 DB / Supabase 호출 경로가 없는지

## 9. 사람이 해야 하는 일

1. 공식 zip이 있는 곳(로컬 작업본)에서 아래를 돌린다. 이 컨테이너에서 돌리려면 zip을
   `git add -f`로 올려야 하고, 그러면 대용량 원본이 히스토리에 남는다. 로컬 실행을 권한다.
   ```
   python scripts/analyze_seoul_polygon_source.py \
     --archive "data/reference/532_UQ120_도시계획사업(서울플랜+)_202609.zip" --write
   ```
2. `CRS_SANITY_FAILED`가 나오면 매칭 결과를 보지 말고 좌표계부터 확인한다.
3. `polygon_match_review_20260928.json`의 `schema` 블록을 먼저 읽는다.
   `UNCONFIRMED` / `UNRESOLVED`인 역할이 있으면 코드정의표를 보고 어떤 필드가 그 역할인지
   확인한 뒤 `ROLE_FIELDS`에 이름을 추가한다(추측으로 채우지 않는다).
4. `auto_apply_candidate`인 EXACT만 사람이 확인한다.
   `exact_valid_outside`는 왜 밖으로 나왔는지 따로 본다.
5. DB write는 그 확인 뒤의 별도 단계다. 이 스프린트에는 포함되지 않는다.
