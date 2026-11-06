# ZIP:ON 2차(개발구역 경계 활성화)·3차(실거래 연동) 데이터 확보 가능성과 구현 계획 (2026-11-06)

**이 문서는 분석과 계획이다. 2차·3차는 실행하지 않았고 DB·배포·코드 변경은 없다.**
확인한 것과 확인하지 못한 것을 구분해 적는다. 이 세션에서 서울시 포털·Supabase·공공데이터포털에는
접속할 수 없었고, 공식 SHP 원본도 이 컨테이너에 없다(§1.1). 아래 수치의 출처는 각 항목에 적었다.

---

## 1. 서울시 SHP 경계 데이터를 실제로 쓸 수 있는가

### 1.1 확인된 사실

| 항목 | 값 | 출처 |
| --- | --- | --- |
| 데이터셋 | 도시계획사업 현황(서울플랜+) 공간정보, OA-22712, 202609판, 레이어 `UPIS_C_UQ120` | `docs/zipon_polygon_matching_review_2026-09.md` |
| 레코드 | 2,776 (Polygon 2,684 + MultiPolygon 92) | 2026-09-29 사용자 로컬 1차 분석 |
| 좌표계 | EPSG:5174 (`.prj`에서 읽음) — 합성 fixture의 가정(5186)과 달랐고 파이프라인이 `.prj`만 믿어 맞게 처리 | 같은 문서 §2 |
| 속성 | `PRESENT_SN`(원천 레코드 ID), `DGM_NM`(도형/사업명), `SIGNGU_SE`(자치구 코드), `PROPEL_CD`(추진구분 코드), `CREATE_DAT`. **동·주소·법정동 없음** | 같은 문서 §2 |
| 법적 성격 | "법적 효력 없음 / 참고자료" | 포털 표기 |
| 이 컨테이너에 파일 | **없음**(`data/reference/*.zip`은 gitignore, 전체 검색에도 없음) | 이번 세션 `find` |
| 파이프라인 | 분석·매칭·적용 스크립트와 RPC는 구현·테스트 완료(합성 SHP 기준) | `scripts/analyze_seoul_polygon_source.py`, `scripts/apply_zipon_polygons.py`, `supabase/migrations/20260929_zipon_boundary_rpc.sql` |
| 운영 반영 | **0건**(`verified_boundaries = 0`) | 사용자 SQL 결과, canary dry-run |

### 1.2 판단: "쓸 수 있다, 단 일부만 자동 반영되고 1,190건 전체 재실행이 선행되어야 한다"

근거와 한계를 나눠 적는다.

**쓸 수 있는 이유**
- 공식 서울시 공간정보이고, 좌표계·형상(Polygon/MultiPolygon, 구멍 규약)·인코딩 처리와 CRS 서울 범위 검사가 구현·테스트돼 있다.
- 경계를 쓰는 유일한 경로(`zipon_set_project_boundary`)와 화면 안전장치(검증된 경계만 면으로 그림, 대표좌표 120m 원은 구역이 아님을 표시)가 있다.
- 매칭 등급 규칙이 보수적이다: `EXACT`(정규화 이름+자치구 일치, 후보 1개, 이름 3글자 이상, 대표좌표가 폴리곤 안, geometry 유효)만 자동 반영 후보.

**한계 / 아직 모르는 것**
1. **매칭은 130건 기준이었다.** 문서의 매칭 설계와 1차 결과(전부 `NO_MATCH` → `DGM_NM` 프로필 등록으로 해결)는 초기 130건 때 것이다. 현재 1,190건에 대한 매칭 결과는 저장소에 없다. 경계 활성화 전에 1,190건으로 다시 돌려야 한다.
2. **동일성 키가 없다.** `PRESENT_SN`은 ZIP:ON의 `external_id`(서울시 정비사업 정보몽땅 별칭)와 같은 체계인지 확인되지 않았다. 결국 **이름+자치구** 매칭이다. 검토 큐의 `NO_OFFICIAL_IDENTIFIER` 306건은 ID로 검증할 수단이 없어 특히 약하다.
3. **UQ120 레이어가 "정비구역 경계"인지 확인이 필요하다.** 레이어는 "도시계획사업"이며 `DGM_NM`에 가로주택정비·소규모재건축 같은 사업명도 섞여 있다. 재개발/재건축 **정비구역** 경계와 같은 의미인지, `PROPEL_CD` 코드값(`PP0501` 등)의 뜻은 코드정의표에서 확인되지 않았다(문서상 `UNCONFIRMED_CODE`). 모아타운(대상지)·신속통합기획 후보지가 이 레이어에 있는지도 미확인이다.
4. **"참고자료"라는 법적 성격.** 화면에서 "공식 경계(참고용, 법적 효력 없음)"로 표기해야 한다. INSIDE 판정 문구도 "경계 안으로 보임"처럼 단정하지 않아야 한다.
5. **보조 후보:** 국가공간정보포털 "도시및주거환경정비/정비구역"(결정고시관리번호 포함 가능성), 서울도시공간포털 "정비사업구역계"가 조사 단계에서 후보로 올랐으나 **접속 불가로 속성·라이선스를 확인하지 못했다**(`polygon_source_survey_20260928.json`, 상태 `CANDIDATE_NOT_VERIFIED`). UQ120으로 부족하면 대안이다.

### 1.3 구현 계획(2차)

| 단계 | 내용 | 완료 기준 | 승인 필요 |
| --- | --- | --- | --- |
| 2-0 | 로컬에서 zip 재분석: `analyze_seoul_polygon_source.py --archive … --write`. 코드정의표로 `PROPEL_CD` 값 의미와 UQ120의 대상 범위 확인 | `CRS_SANITY_FAILED` 없음, schema 블록의 UNCONFIRMED 역할 목록 확정 | 아니오(로컬, 읽기) |
| 2-1 | **1,190건 대상** 매칭 재실행(현재 DB 스냅샷을 입력으로). 등급별·유형별·자치구별 집계, `exact_valid_outside` 원인 분석 | review JSON, EXACT 비율 보고 | 아니오 |
| 2-2 | 사람 검토: `auto_apply_candidate` 표본 검수(예: 30건 지도 대조), `마천2` 등 보호 대상 15건 제외 확인 | 표본 오매칭 0건 | 사용자 |
| 2-3 | 스테이징 DB에서 `--dry-run` → `--apply --limit 1` → 화면 확인 → 전체 | 스테이징 `verified_boundaries` = 검수한 EXACT 수 | **스테이징 승인** |
| 2-4 | 운영 반영(`ZIPON_REFRESH_SPATIAL_ENABLED` 게이트는 일일 갱신용이므로 별개; 이 반영은 `apply_zipon_polygons.py`) | 운영 SQL 정합성 점검 통과, 롤백 방법 준비 | **운영 DB 변경 승인** |
| 2-5 | 화면: 경계가 있는 구역에서 면 표시, "참고용" 배지, INSIDE 문구, 실제 NAVER SDK 체크리스트(§3 of 검증 문서) | 체크리스트 통과 | 배포 승인 |

롤백: `zipon_set_project_boundary`는 geometry/`geometry_verified`를 쓰는 RPC이므로, 반영 전 대상 `project_id`와 이전 값을 journal로 저장하고, 되돌림 SQL을 미리 검토한다(별도 승인).

**예상 범위(추정, 확인 안 됨):** 2,776개 폴리곤 중 정비 관련 비중과 1,190건 중 EXACT 비율은 모른다. 2-1 결과가 나오기 전에는 목표 수치를 약속하지 않는다.

---

## 2. 검토 대기 994건의 원인

**먼저: 994는 큐에 쌓인 행이 아니다.** 2026-11-06 canary **dry-run** 보고(`status PARTIAL`, `dry_run true`,
`counts: new 12 / changed 99 / unchanged 137 / review_required 994`)의 후보 수다. dry-run은
`development_review_queue`에 쓰지 않는다. 같은 보고의 `new 12 / changed 99 / unchanged 137`은 상태 변화 분류이고 994와 합산되는 값이 아니다(두 집계의 관계는 보고서만으로는 확인하지 못했다).
→ 운영 큐에는 apply 전까지 이 행이 없다(SQL [7]로 확인).

사유별 분해(보고서 `reviews Counter`, 합 994):

| 사유 | 건수 | 원인(코드 근거 `services/development_refresh.py`) | 해결 방향 |
| --- | ---: | --- | --- |
| `AMBIGUOUS_DATE` | 376 | 서울시 상세의 단계 날짜가 `yy.mm.dd`(2자리 연도)이거나 형식이 달라 ISO 날짜로 확정 못 함. **세기를 추측하지 않는다**(`parse_progress`) | 2자리 연도 표기를 "원문 보존 + 기준일 문맥으로 해석 가능한 경우만 승격" 규칙 설계 후 사람 검토, 또는 날짜 없는 단계로 표시 유지 |
| `NO_OFFICIAL_IDENTIFIER` | 306 | 레코드에 `external_id`(서울시 별칭)가 없어 상세 페이지·공식 동일성을 연결 못 함 | 공식 목록과의 재대조로 ID 확보, 불가하면 "공식 ID 없음" 상태로 유지(타임라인 비활성) |
| `DUPLICATE_SUSPECTED` | 159 | 같은 자치구에서 이름이 서로 포함 관계(3글자 이상). 정규화 수준의 의심이라 **오탐 가능성이 큼**(예: `천호3` ⊂ `천호3-1`) | 이름 포함 규칙을 숫자·구역번호 경계까지 고려하도록 정밀화 후 재분류, 나머지는 사람 판정. 자동 병합 금지(CLAUDE.md 정책과 동일) |
| `STATUS_REVIEW_REQUIRED` | 60 | 취소/해산/청산 단계로의 전환은 자동 반영하지 않고 검토(`decision`) | 사람 검토(의도된 안전장치) |
| `IDENTITY_OR_FRAME_UNRESOLVED` | 50 | 상세 페이지의 사업 정체·프레임이 일치하지 않음 | 개별 확인 |
| `SOURCE_MISSING` | 16 | 이번 수집 목록에서 사라짐. 상태 변화가 아님 | 일정 기간 반복 시 `MISSING_FROM_SOURCE` 표시 |
| `MOA_CANCELLATION_REVIEW` | 11 | 모아타운 해제 의심 | 사람 검토 |
| `OFFICIAL_NOTICE_REVIEW` | 6 | 고시 문서 확인 필요 | 사람 검토 |
| `PROTECTED_IDENTITY` | 5 | 보호 대상 identity(마천2 등) | 건드리지 않음 |
| `PROJECT_NAME_CHANGED` | 5 | 같은 ID에서 이름이 바뀜 | 이름 변경 이력 기록 후 승인 |

요약: **약 69%(AMBIGUOUS_DATE+NO_OFFICIAL_IDENTIFIER 682건)는 "정보 부족"이고 시스템 오류가 아니다**.
이 안전장치가 잘못된 날짜·동일성을 DB에 넣지 않게 막고 있다. 1차 대시보드에서 타임라인이 빈 구역이 많은
이유이기도 하다(상세 이력 있는 사업 약 119건).

### 개선 계획(2차와 병행 가능, 읽기·분석 위주)
1. 사유별 샘플 20건씩 뽑아 사람이 정답 라벨링 → 규칙의 오탐률 측정(`DUPLICATE_SUSPECTED`부터).
2. `AMBIGUOUS_DATE` 원문 분포 조사(2자리 연도 vs 형식 이상).
3. `NO_OFFICIAL_IDENTIFIER` 306건: 서울시 목록과 이름+자치구로 ID를 찾을 수 있는지 시험(읽기).
4. 규칙 변경은 단위 테스트 + dry-run 비교 후에만 반영. **큐 승인/거절 UI(운영자 도구)는 별도 하위 과제.**

---

## 3. 국토부 실거래 API 4종을 구역별로 매칭하기 위한 DB 구조와 처리 방식 (3차)

### 3.1 현재 상태(코드 사실)
- API 4종: 아파트 `RTMSDataSvcAptTradeDev`, 연립·다세대 `RTMSDataSvcRHTrade`, 단독·다가구 `RTMSDataSvcSHTrade`, 오피스텔 `RTMSDataSvcOffiTrade` (`services/realestate_monitor.py` `TRADE_APIS`). 요청 파라미터는 `LAWD_CD`(시군구 5자리)·`DEAL_YMD`(계약년월).
- 현재는 **조회 시점에 API를 호출해 화면에 보여 줄 뿐 DB에 저장하지 않는다**. 구역과의 연결도 없다(`ZONE_TRADES_IMPLEMENTED = False`).
- 응답에서 쓰는 위치 단서: 법정동명(`umdNm`), 지번(`jibun`), 도로명(`address_road` 계열), 단지명. **좌표는 없다.** `services/trade_geocode.py`가 "자치구+주소" 단일 정확 일치만 좌표로 만드는 규칙을 이미 갖고 있다.
- 서버에 공공데이터 키가 있는지(`api_key_configured`)는 `connections`로 알 수 있다.

### 3.2 확인하지 못한 것(먼저 확인해야 하는 위험)
1. **응답 필드의 실제 가용성:** 유형별로 `jibun`이 마스킹/생략되는지, 단독·다가구·연립의 지번 공개 범위, 오피스텔 필드명. **실제 키로 샘플 응답을 받아 유형·자치구별 지번 공개율을 먼저 측정**해야 한다(이 세션에서 외부 API에 접속하지 않았다).
2. **지오코딩 성공률:** 지번 → 좌표 단일 정확 일치율이 낮으면 "위치 확인 불가" 거래가 많아진다.
3. **재개발 구역의 핵심 거래 유형:** 입주권·분양권 거래(`RTMSDataSvcSilvTrade`)는 4종에 **포함되지 않는다.** 투자 관점에서는 중요하므로 범위 포함 여부를 사용자와 결정해야 한다.
4. **API 호출 한도:** 개발계정은 일일 호출 제한이 있다(정확한 한도는 키 종류별로 확인 필요). 서울 25개 구 × 4유형 × 24개월 ≈ 2,400회 + 페이지네이션이 백필 최소치다.
5. **해제 거래(취소):** 응답의 해제 표시 필드를 저장·제외 처리해야 한다(필드명 확인 필요).

### 3.3 DB 구조(제안, 신규 테이블 3개 + 기존 테이블 재사용)

```
trade_transactions            -- 원자료. 유형별 API 응답을 정규화해 보관(중복 방지)
  trade_id uuid PK
  property_type text CHECK (아파트|연립다세대|단독다가구|오피스텔)
  lawd_cd char(5), deal_ymd char(6), deal_date date
  amount_manwon bigint, area_m2 numeric, area_basis text        -- 전용/연면적 구분 보존
  floor int, build_year int, name text, umd_nm text, jibun text, road_address text
  canonical_address text          -- 시도·자치구 포함 전체 주소(trade_geocode.full_address 규칙)
  is_cancelled boolean, cancelled_date date
  raw jsonb, source_hash char(64) UNIQUE      -- 재수집 멱등성
  collection_run_id uuid -> development_collection_runs 유사 수집 기록, collected_at timestamptz

trade_locations               -- 거래 주소 → 좌표(캐시)
  trade_id uuid PK -> trade_transactions
  location geography(Point,4326) NULL
  accuracy text CHECK (BUILDING|PARCEL|ROAD|NONE)   -- 단일 정확 일치만 PARCEL 이상
  provider text, geocoded_at, status text           -- OK / AMBIGUOUS / NOT_FOUND

development_project_trade_links   -- 구역과 거래의 연결(재계산 가능한 파생 데이터)
  project_id uuid -> development_projects, trade_id uuid -> trade_transactions
  relation text CHECK (INSIDE_VERIFIED_BOUNDARY | NEAR_ESTIMATED | LOCATION_UNKNOWN)
  distance_m numeric NULL, method text, boundary_version/at timestamptz, computed_at
  PRIMARY KEY (project_id, trade_id)
인덱스: trade_transactions(lawd_cd, deal_ymd), GIST(trade_locations.location),
        GIST(development_projects.geometry) WHERE geometry_verified
```

- 기존 `geocode_cache`·수집 실행 기록 패턴을 재사용하고, RLS 켠 채 `service_role`만 접근(검토 큐와 동일 정책).
- `links`는 **파생 테이블**이다. 경계가 새로 확정되면 해당 구역 거래만 재계산한다(원자료 불변).
- 경계가 없는 구역의 거래는 `INSIDE`로 분류하지 않는다(현재 `connections`의 `BLOCKED_NO_VERIFIED_BOUNDARY`와 같은 원칙).

### 3.4 처리 방식

1. **수집(주 1~2회 배치, GitHub Actions 등):** 서울 25구 × 4유형 × 최근 N개월. 월 단위 증분(최근 2~3개월 재수집으로 정정·해제 반영), `source_hash`로 멱등 upsert. 요청 간격·재시도·일일 한도 가드. 실패한 구·월은 기록하고 부분 성공을 성공으로 보고하지 않는다.
2. **주소 정규화 → 좌표:** 기존 `trade_geocode.full_address` 규칙(자치구 모르면 좌표 안 붙임, 단일 정확 일치만). 실패는 `LOCATION_UNKNOWN`으로 남기고 화면에 "위치 확인 불가"로 구분 표시.
3. **구역 연결(구분 3단계, 섞어 표시 금지):**
   - `INSIDE_VERIFIED_BOUNDARY`: **확인된 경계**가 있고 `ST_Covers(boundary, point)`.
   - `NEAR_ESTIMATED`: 경계가 없거나 밖일 때 대표좌표/경계로부터 반경(예: 300m, 설정 가능) 이내 — 라벨에 "인근 추정" 명시, 구역 내부라고 쓰지 않음.
   - `LOCATION_UNKNOWN`: 좌표 없음.
   - 지번 단위 대안: 구역에 속한 필지 목록(연속지적도)이 확보되면 지오코딩 없이 지번 일치로 INSIDE를 판정할 수 있어 더 정확하다. 필지 데이터 확보 가능성은 미확인이므로 2차 이후 선택지로 둔다.
4. **API 설계:** 기존 상세 API에 구역 거래 요약을 추가하거나 `/development/projects/{id}/trades?type=&months=`를 신설. 응답마다 `relation` 분포, 기준일, 출처, 위치 정확도를 포함하고 `connections.trades.zone_panel/zone_matching`을 그때 `IMPLEMENTED/AVAILABLE`로 바꾼다(코드 상수 변경 + 테스트).
5. **화면:** 실거래 탭의 "미연동" 카드를 실제 목록으로 교체(계약일·금액·면적·층·건축연도, 위치 정확도 배지, 최근 추이). 지도 위 거래 마커는 후속.
6. **검증:** 단위 테스트(정규화·멱등·해제 처리·3단계 분류), 합성 지오메트리로 INSIDE/NEAR 경계 테스트, 샘플 구역 3곳을 사람이 지도와 대조, 지번 공개율·지오코딩 성공률 리포트를 PR에 첨부.

### 3.5 3차 단계표

| 단계 | 내용 | 승인 필요 |
| --- | --- | --- |
| 3-0 | 실제 키로 4종 샘플 응답을 받아 필드·지번 공개율·해제 필드 확인(소량, 읽기). 입주권/분양권 포함 여부 결정 | 사용자(키·범위) |
| 3-1 | 스키마 마이그레이션 작성·리뷰(스테이징) | **스테이징 DB 변경 승인** |
| 3-2 | 수집 배치 + 멱등/한도/실패 보고 구현, 스테이징 백필 | 스테이징 승인 |
| 3-3 | 지오코딩 + 연결 계산, 정확도 리포트 | 아니오(스테이징 내) |
| 3-4 | API·화면 연결, `connections` 갱신 | 배포 승인 |
| 3-5 | 운영 마이그레이션·백필 | **운영 DB 변경 승인** |

---

## 4. 2차와 3차의 순서와 의존성

- **3차의 "구역 안" 판정은 2차의 확인된 경계에 의존한다.** 2차 전에는 `NEAR_ESTIMATED`(인근 추정)와 지역 단위 조회만 가능하다.
- 그래서 권장 순서: 2-0~2-2(로컬 분석·검수) ∥ 3-0(API 샘플 확인) → 2-3~2-4 → 3-1~3-5.
- 2차·3차 모두 DB 스키마·데이터 변경은 **스테이징 → 운영** 순서로, 각 단계에서 별도 승인을 받는다.

## 5. 사용자 결정이 필요한 항목

1. 로컬에 있는 공식 SHP zip으로 2-0/2-1(읽기 전용 분석)을 돌려 결과(`schema` 블록, 등급별 집계)를 공유해 주실 수 있는가.
2. 거래 범위에 입주권·분양권(`RTMSDataSvcSilvTrade`)을 포함할지.
3. 인근 추정 반경 기본값(제안 300m)과 거래 보존 기간(제안 24개월).
4. 스테이징 Supabase 프로젝트를 2·3차 마이그레이션 시험에 계속 쓸지.
