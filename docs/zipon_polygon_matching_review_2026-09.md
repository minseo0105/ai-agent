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

이 컨테이너의 네트워크 정책이 `data.seoul.go.kr`와 `datafile.seoul.go.kr`로의 연결을
거부한다(CONNECT에 게이트웨이가 403). 근거는 `data/development/polygon_source_acquisition_20260928.json`에
남겼다.

그래서 **비공식 자료로 대체하지 않았다.** 폴리곤을 만들지도, 대표좌표에 버퍼를 씌우지도 않았다.
사람이 포털에서 직접 내려받아 `data/reference/`에 두면 같은 스크립트가 그대로 돈다.

```
python scripts/analyze_seoul_polygon_source.py \
  --archive "data/reference/532_UQ120_도시계획사업(서울플랜+)_202609.zip" --write
```

원천이 없으면 스크립트는 아무 일도 하지 않고 `SOURCE_FILE_NOT_PRESENT`와 내려받는 방법만 알린다.

## 3. SHP 읽기

`scripts/analyze_seoul_polygon_source.py`가 하는 일.

- **DBF 인코딩을 단정하지 않는다.** cp949 / utf-8 / euc-kr / latin-1로 각각 열어 보고,
  필드명에 한글이 가장 잘 살아나는 것을 고른다. 인코딩을 잘못 잡으면 필드명이 깨지고,
  그러면 **오류 없이 조용히 '매칭 0건'** 이 나온다. 이번 작업에서 실제로 한 번 겪은 실패라서
  탐지 자체를 테스트로 고정했다.
- **필드명이 잘려 있어도 찾는다.** DBF 필드명은 길이 제한이 있어 `사업명`이 `사업`으로
  줄어 있을 수 있다. 이름을 양방향(포함 관계 둘 다)으로 본다.
- **좌표계는 `.prj`에서 읽는다.** `AUTHORITY["EPSG","####"]`가 있으면 그것을 쓰고,
  없으면 알려진 이름(Korea 2000 중부/통합)과 맞춰 본다. 둘 다 안 되면 **추정하지 않고**
  좌표계 미상으로 두고 변환하지 않는다. 국내 공간정보는 대개 EPSG:5186이다.
- 변환은 pyproj로 EPSG:4326(경도, 위도)으로만 한다.

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

| 등급 | 조건 |
| --- | --- |
| `EXACT` | 공식 식별자가 같거나, 정규화 사업명이 같고 자치구까지 맞으며 **후보가 하나뿐** |
| `PROBABLE` | 신호는 강하지만 식별자/정규화 사업명 일치가 부족 |
| `AMBIGUOUS` | 후보가 둘 이상이거나, 기존 duplicate/identity 검토 대상 |
| `NO_MATCH` | 안전한 공식 후보가 없음 |

이름이 비슷하다는 이유만으로 `EXACT`가 되지 않는다.
**대표좌표의 폴리곤 포함 여부는 보조 확인일 뿐이며 동일성을 결정하지 않는다.** 그래서
포함 여부는 신호 목록에 넣지 않고 별도 칸(`representative_point_inside_polygon`)에만 적는다.

### 기존 위험 사례 보호

`fast_track_identity_review_20260928.json`의 IDENTITY_CONFLICT / duplicate_risk 건과
`geocode_gap_review_20260928.json`의 MANUAL_REVIEW 건은 폴리곤이 딱 맞아도 `AMBIGUOUS`로
내린다. 폴리곤으로 동일성을 정하지 않는다. 지금 15건이 여기에 해당한다. 그중 `마천2`와
`마천2재정비촉진구역 주택재개발정비사업`은 둘 다 이미 DB에 있고, 서로 다른 사업인지
같은 사업의 두 표기인지는 사람이 판단할 일로 남아 있다.

## 6. 산출물 (모두 검토용, DB write 없음)

| 파일 | 내용 |
| --- | --- |
| `data/development/polygon_source_acquisition_20260928.json` | 원천 확보 시도와 차단 근거 |
| `data/reference/source_registry.json` | 어떤 원천을 어떤 판으로 받았는지 |
| `data/development/polygon_match_review_20260928.json` | 130건 전체 등급·신호·근거 (원천 확보 후 생성) |
| `data/development/polygon_match_exact_20260928.geojson` | `EXACT` 건만, `review_only: true` (원천 확보 후 생성) |

`polygon_match_review_20260928.json`에는 `db_write: false`와
`polygon_written_to_production: false`가 항상 들어간다.

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

공식 파일을 받을 수 없어서, **같은 모양의 합성 SHP**(cp949 DBF / EPSG:5186 / 시계방향 외곽 ring)를
만들어 파이프라인을 돌렸다. 합성 원천은 공식 결과가 아니고 폴리곤으로 쓰이지도 않는다.
`tests/test_zipon_product.py::PolygonPipelineTests`가 매번 그것을 만들어 확인한다.

- 인코딩 탐지(cp949 / utf-8), 잘린 필드명 해석
- `.prj`에서 좌표계 읽기, `.prj`가 없으면 변환하지 않음
- 변환된 좌표가 서울 범위의 (경도, 위도) 순서인지
- `Polygon` / `MultiPolygon` / 구멍 / 닫히지 않은 ring
- 구멍 안의 점은 '내부'가 아님
- 화면 쪽 경계 helper(`Polygon` / `MultiPolygon` / 구멍 / 확인되지 않은 값 / 깨진 좌표)
- `EXACT` / `PROBABLE` / `AMBIGUOUS`(후보 2건) / `NO_MATCH` 네 등급
- `마천2` 두 건이 폴리곤으로 정리되지 않는지
- `EXACT`만 GeoJSON에 들어가고 `review_only`가 붙는지
- 스크립트에 DB / Supabase 호출 경로가 없는지

## 9. 사람이 해야 하는 일

1. 포털에서 `532_UQ120_도시계획사업(서울플랜+)_202609.zip`을 내려받는다.
2. `data/reference/`에 그대로 둔다. 압축을 풀거나 수정하지 않는다.
3. 위 스크립트를 `--write`로 돌린다.
4. `polygon_match_review_20260928.json`의 `EXACT` 건만 사람이 확인한다.
   DB write는 그 확인 뒤의 별도 단계다. 이 스프린트에는 포함되지 않는다.
