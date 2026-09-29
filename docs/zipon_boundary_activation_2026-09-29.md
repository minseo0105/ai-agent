# ZIP:ON 공식 사업구역 반영 — 설치와 실행 순서 (2026-09-29)

공식 SHP 매칭에서 나온 EXACT 건을 운영 DB에 넣고, 지도에 면으로 그리고, INSIDE 판정을
켜는 경로다. 매칭 규칙과 등급은 `docs/zipon_polygon_matching_review_2026-09.md`에 있다.

**이 컨테이너에서는 DB에 아무것도 쓰지 않았다.** Supabase와 서울시 포털 모두 이 실행환경의
네트워크 정책이 막고 있다. 아래 순서는 원본과 자격증명이 있는 로컬에서 사람이 실행한다.

## 0. 무엇이 들어가고 무엇이 안 들어가는가

`auto_apply_candidate`인 건만 들어간다. 즉 **등급이 EXACT이고, geometry가 유효하고,
대표좌표가 그 polygon 안에 있는** 건이다. 나머지는 journal에 이유와 함께 남고 DB에 닿지 않는다.

| 제외 | 이유 |
| --- | --- |
| `PROBABLE` / `AMBIGUOUS` / `NO_MATCH` | 사람이 확인할 일이다 |
| `exact_valid_outside` | 대표좌표가 polygon 밖이다. 다른 사업의 구역일 수 있다 |
| `exact_invalid_geometry` | ring이 닫히지 않았거나 유효하지 않다 |
| identity conflict / duplicate risk 15건 | 매칭 단계에서 이미 `AMBIGUOUS`다 |

## 1. 설치 (한 번)

```
supabase/migrations/20260929_zipon_boundary_rpc.sql
```

이 파일이 세 가지를 만든다.

- `zipon_set_project_boundary(...)` — 경계를 쓰는 **유일한** 경로. service_role만 실행한다.
- `zipon_development_map(p_sigungu, p_limit)` — 지도용 읽기. 확인된 경계만 GeoJSON으로 준다.
- `zipon_development_search(...)` — 경계와 provenance를 함께 돌려주도록 교체. 반환 컬럼이
  늘어나므로 `DROP FUNCTION` 뒤에 다시 만든다. **INSIDE 판정 규칙은 그대로다.**

설치 뒤 확인:

```
supabase/review/20260929_zipon_boundary_postcheck.sql
```

전부 실행하면 13개 항목을 확인하고 **모든 fixture를 롤백한다.** 거절 경로 7개,
정상 반영 1개, 재실행 시 건너뛰기, INSIDE/NEARBY, 지도 RPC의 GeoJSON을 본다.

## 2. 반영

```
python scripts/apply_zipon_polygons.py --check-config   # 자격증명·산출물만 확인
python scripts/apply_zipon_polygons.py --dry-run        # 계획만 (기본값)
python scripts/apply_zipon_polygons.py --apply          # 한 건씩 RPC로
python scripts/apply_zipon_polygons.py --apply --limit 1  # 먼저 한 건만
```

`--apply` 없이는 아무것도 쓰지 않는다. 먼저 `--dry-run`으로
`data/development/polygon_apply_journal_20260929.json`의 `selected`와 `not_selected`를 읽고,
`--limit 1`로 한 건을 반영해 화면까지 확인한 뒤 나머지를 넣는 순서를 권한다.

환경변수는 좌표 반영 때와 같다: `ZIPON_IMPORT_SUPABASE_URL`,
`ZIPON_IMPORT_SUPABASE_KEY`(service role 키). 키는 출력하지 않고 journal에도 남지 않는다.

### 두 겹의 확인

스크립트가 먼저 보고, RPC가 다시 본다. 어느 한쪽만 통과해서는 쓰이지 않는다.

| 확인 | 스크립트 | RPC |
| --- | :-: | :-: |
| 산출물의 원천 판·해시가 `source_registry.json`과 같다 | O | 근거로 받음 |
| 등급 EXACT · 자동반영 후보 · 검사 전부 통과 | O | O |
| Polygon / MultiPolygon이고 ring이 닫혀 있다 | O | O (`ST_IsValid`) |
| 서울 bounding box 안이다 | O | O |
| 면적이 100 m² ~ 5 km² | 어림값 | 정확값 (`ST_Area`) |
| 저장된 자치구가 산출물과 같다 | O | O |
| 저장된 대표좌표가 polygon 안이다 | O | O (`ST_Contains`) |
| revision이 읽은 값과 같다 | O | O (행 잠금) |
| 이미 확인된 경계가 있으면 건너뛴다 | O | O |
| `canonical_source_id`가 있다 | — | O |

RPC가 바꾸는 것은 `geometry`, `geometry_source`, `geometry_verified`,
`geometry_verified_at`, `field_evidence.boundary`, `revision`뿐이다. 좌표·단계·상태·
검증상태·identity·`canonical_source_id`는 손대지 않고, 반영 뒤 스크립트가 한 건씩 다시 읽어
그대로인지 확인해 journal의 `unexpected_changes`에 남긴다. 비어 있어야 정상이다.

## 3. 화면까지

- **API**: `map_projects()`가 `zipon_development_map` RPC를 먼저 쓴다. 이 RPC가 아직 없는
  서버에서는 이전 REST 조회로 되돌아가고 경계 없이 좌표만 그린다. 그래서 설치 순서가
  어긋나도 지도가 비지 않는다(`boundary_source`가 `RPC` / `NONE`로 나온다).
- **presentation**: `boundary_layer()`가 `geometry_verified`이고 경계가 있을 때만
  `OFFICIAL_VERIFIED`로 내보낸다. 그 외에는 `boundary`를 `null`로 지운다.
- **NAVER 지도**: `verifiedBoundaryPolygons()`가 `OFFICIAL_VERIFIED`인 경계만 ring으로
  바꾼다. `Polygon`과 `MultiPolygon`을 모두 그리고, 구멍을 반영하며, 읽을 수 없는 ring은
  모양을 짐작하지 않고 버린다. 경계가 있으면 반경 120m 원을 그리지 않고 경계에 화면을 맞춘다.
- **카드↔지도**: 카드를 누르면 그 카드 안 지도가 같은 point를 받아 경계까지 그린다.
  경계가 있을 때만 "공식 사업구역"이라고 쓰고, 없으면 "사업 대표위치"로 남는다.
  범례의 "공식 사업구역"은 실제로 그려지는 건이 있을 때만 나온다.

## 4. INSIDE 판정

규칙은 처음부터 하나다: **`geometry_verified`이고 그 polygon이 점을 담을 때만 INSIDE다.**
경계가 들어오면 그 조건이 충족되기 시작하므로, 이 스프린트에서 INSIDE 문구를 새로 만들지
않았다. 대신 잘못된 지름길 하나를 없앴다.

`present_project()`가 `evidence_verified`(공식 출처를 언제 확인했는지)를 경계 검증 신호로
함께 보고 있었다. 출처 확인 시각은 경계 확인이 아니다. 지금까지는 경계가 0건이라 드러나지
않았지만, 경계가 들어오는 순간 "정비구역 내부"가 근거 없이 나올 수 있는 자리였다. 이제
`geometry_verified`만 본다.

대표좌표만 있는 사업은 여전히 `NOT_DETERMINED`와 안내문이 나온다.

## 5. 확인 순서

1. postcheck SQL 전부 실행 → 13개 항목 통과, 롤백 확인
2. `--dry-run` journal의 `selected` 수가 review의 `auto_apply_candidates`와 같은지
3. `--apply --limit 1` → journal의 `result: boundary_set`, `unexpected_changes: []`
4. 그 사업 카드에서 면이 그려지고 "공식 사업구역"이 나오는지
5. 그 구역 안 좌표로 거래를 조회해 "정비구역 내부"가 나오고, 밖에서는 나오지 않는지
6. 나머지 반영 → `applied` 수와 `refused: 0` 확인
7. `POLYGON` 수가 예상과 같은지, `PROJECTS 130` / `COORDINATES 122` / `STAGE 119·11`이
   그대로인지

어느 단계든 `refused`가 나오면 이유를 보고 멈춘다. 이유는 모두 journal에 남는다.
