# 서울 25개 자치구 실수집 — 실행 로그 (2026-10-01)

## STEP 1. live 수집 가능 여부 — 실패 (차단)

성동구 1개 구로 실제 요청했고, 4개 source 전부 실패했습니다. 동일 요청을 반복하지
않았습니다.

| endpoint | 결과 |
|---|---|
| `https://news.seoul.go.kr/citybuild/moa-housing-town/policy/status` | `ProxyError` |
| `https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanSttn.do` | `ProxyError` |
| `https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanSttn2.do` | `ProxyError` |
| `https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do?...signguCode=11200` | `ProxyError` |

이 컨테이너의 네트워크 정책이 `cleanup.seoul.go.kr`와 `news.seoul.go.kr` 두 호스트의
CONNECT를 거부합니다(`connect_rejected`, HTTP 000). 자격증명 문제가 아니라 egress
차단입니다. 따라서 STEP 2~5, 7~8의 실수집·적재·지도 확인은 이 환경에서 실행할 수
없고, 아래 명령을 망이 열린 환경에서 실행해야 합니다.

```
git fetch origin claude/keen-clarke-m73n6h && git checkout claude/keen-clarke-m73n6h

# 1) 1개 구로 접근 확인
venv\Scripts\python.exe -B scripts\collect_zipon_pilot.py --district 성동구 ^
  --out data\development\live_probe_성동구.json

# 2) 서울 25개 전체 수집 (페이지네이션 포함)
venv\Scripts\python.exe -B scripts\collect_zipon_pilot.py --all-seoul ^
  --out data\development\seoul25_raw.json

# 3) 커버리지 + 품질 + 기존 130건 중복 검증, Supabase write 없음
venv\Scripts\python.exe -B scripts\dryrun_zipon_districts.py --all-seoul --live ^
  --out data\development\seoul25_coverage.json

# 4) 적재 artifact 생성 (write 아님)
venv\Scripts\python.exe -B scripts\build_zipon_seoul_import.py ^
  --input data\development\seoul25_raw.json ^
  --out data\development\seoul25_import_artifact.json
```

(2)의 수집 결과에서 `runs[].source_complete`와 `pages_fetched`를 먼저 확인하세요.
`PAGE_LIMIT_REACHED` / `DUPLICATE_PAGE` / `NO_NEW_ROWS`가 찍힌 자치구는 끝까지 받지
못한 것이며, 0건과는 다른 사건입니다.

## STEP 2. pageSize=100 — 해결 (오프라인 검증)

구별 사업장 목록은 `cpage`로 페이지를 넘깁니다. 기존 URL은 `cpage=1&pageSize=100`
한 장만 받아 100건이 넘는 자치구가 조용히 잘렸습니다. 이제 `fetch_source_pages()`가
`cpage`만 바꿔가며 모든 장을 받습니다. 종료조건 네 가지 전부 명시적입니다.

| 종료조건 | 판단 | 결과 |
|---|---|---|
| 응답 행 수 < `pageSize` | 마지막 장 | `SUCCEEDED`, `source_complete=true` |
| 문서 해시가 이 source에서 이미 본 것과 같음 | `cpage`를 무시하는 응답 | `DUPLICATE_PAGE`, `PARTIAL` |
| 새 `project_id`가 하나도 늘지 않음 | 더 받을 것이 없음 | `NO_NEW_ROWS`, `PARTIAL` |
| `max_pages`(40, 4,000행) 도달 | 잘림 | `PAGE_LIMIT_REACHED`, `PARTIAL` |

시 전체 page(모아타운·신속통합기획)는 페이지네이션 대상이 아니며 지금처럼 한 번만
받습니다. `source_complete`가 directory에서도 참이 될 수 있게 되었습니다 — 전에는
무조건 `PARTIAL`이었습니다.

**실제 site의 2페이지 이후 응답 동작은 검증하지 못했습니다**(차단). `cpage`가
정상 동작하는 파라미터라는 근거는 기존 수집 URL이 이미 `cpage=1`을 쓰고 있고 그것으로
149행을 실제 수집했다는 것뿐입니다. 그래서 "`cpage`를 무시하는 응답"을 가장 가능성
높은 실패로 보고 `DUPLICATE_PAGE` 방어를 넣었습니다. 무한 loop는 세 겹으로 막혀
있습니다(해시 중복 · 신규 id 없음 · 하드 상한).

오프라인 검증 7건 (`DirectoryPaginationTests`):
230행/3페이지 완전수집 · 단일 짧은 페이지 즉시 종료 · cpage 무시 응답 2회에서 중단 ·
문서는 바뀌는데 사업은 같은 경우 중단 · 상한 도달 시 오류 기록 · 시 전체 source 미분할 ·
URL이 page 번호만 바뀜.

## STEP 3. 개발사업 유형

기존 분류 체계를 그대로 씁니다. 새 유형을 만들지 않았습니다.

| source | kind | project_type |
|---|---|---|
| 정보몽땅 사업장 목록 (구별, 페이지네이션) | directory | `REDEVELOPMENT` / `RECONSTRUCTION` |
| 정보몽땅 신속통합기획 재개발 (시 전체) | shintong | `SHINTONG` (정제 시 `FAST_TRACK`) |
| 정보몽땅 신속통합기획 재건축 (시 전체) | reconstruction | `RECONSTRUCTION` |
| 서울시 모아타운 추진현황 (시 전체) | moa | `MOATOWN` |

## STEP 4~5. Coverage / 품질 — 미실행

실수집이 안 되었으므로 자치구별 raw·normalized·geocoded·insert·update·duplicate·
reject 실측값이 없습니다. `dryrun_zipon_districts.py --all-seoul --live`가 이 표와
`0건 자치구` 목록을 그대로 냅니다. 0건의 두 사정은 artifact에서 구분됩니다.

* 실제로 사업이 없는 구: `status=SUCCEEDED`, `source_complete=true`, `new_count=0`
* 수집 실패한 구: `status=FAILED`, `errors`에 예외 종류

지역 정확성(STEP 5)과 identity 중복(STEP 5)의 검증 로직은 지난 커밋에서 이미 들어가
있고 오프라인 검증도 끝나 있습니다 — 자치구 불일치 좌표는 `GEOCODE_SIGUNGU_MISMATCH`로
reject되고, 기존 130건은 재수집 시 insert가 아니라 update로 분류됩니다.

## STEP 6. 개발지도 성능 — 검토 결과

**결론: 제한값을 올릴 필요가 없습니다. 서버는 이미 지역/bbox 조회를 지원하고,
화면만 전체를 받아오고 있습니다.**

`GET /api/realestate/development/map`은 이미 `sigungu`와 `north/south/east/west`를
받습니다(`api/realestate.py:286`). RPC `zipon_development_map`도 같은 인자를 받습니다.

그런데 `DevelopmentTab.tsx`는 `developmentMap(undefined, 500, undefined, ...)`로
**서울 전체를 한 번 받아 브라우저에서 거릅니다.** 자치구 선택은 화면 필터일 뿐입니다.
130건에서는 문제가 없지만 1,000건대가 되면 그대로 1,000건이 브라우저로 내려옵니다.

필요한 변경은 한 곳입니다. `useEffect`의 의존성에 선택지역을 넣고
`developmentMap(districts.join(','), ...)`로 바꾸면 "선택지역 → 해당 지역 API 조회 →
marker" 구조가 됩니다. 이번에는 바꾸지 않았습니다 — 이유:

1. 현재 적재된 데이터가 3개 구 130건이라 지금 바꾸면 운영 화면 동작만 바뀌고 얻는
   것이 없습니다.
2. 코드 주석에 적힌 기존 설계 의도가 "자치구별 응답을 합치면 한 자치구가 실패했을 때
   그 사업들이 조용히 빠진 합계가 전체로 보인다"입니다. 지역별 조회로 바꾸려면
   **부분 실패를 합계에 숨기지 않는 처리를 같이** 넣어야 하고, 그건 실데이터가
   들어온 뒤에 할 일입니다.
3. `MAX_DISTRICTS=5`는 이 구조에서 자연스러운 상한이 됩니다(한 번에 5개 구).
   `MAX_CARDS=200`도 5개 구 기준이면 유지 가능합니다. `limit=500`은 5개 구
   합계로는 충분하고, 서울 전체 조회만 포기하면 됩니다.

즉 실적재 전에 할 일은 숫자 상향이 아니라 **조회 단위를 지역으로 바꾸고 부분 실패를
드러내는 것**입니다.

## STEP 7. 환경 판정 및 적재

이 환경에는 Supabase 자격증명이 **하나도 설정되어 있지 않습니다.**
`ZIPON_IMPORT_SUPABASE_URL` / `ZIPON_IMPORT_SUPABASE_KEY` / `SUPABASE_URL` /
`SUPABASE_KEY` 모두 unset이고, `rm._supabase_config()`도 `None`입니다.
DEV Supabase는 저장소 어디에도 설정되어 있지 않고, 코드가 아는 project URL은
`scripts/apply_zipon_geocode.py`에 가드로 박힌 **Production 하나뿐**입니다.

따라서 적재 대상으로 확인되는 것은 Production뿐이고, 규칙대로 **write하지 않습니다.**
DELETE / TRUNCATE / 대량 UPDATE도 하지 않았습니다. `scripts/build_zipon_seoul_import.py`가
검증된 upsert artifact까지만 만듭니다(아래).

## STEP 8. 지도 확인 — 미실행

DEV 환경이 없고 적재도 하지 않았으므로 9개 자치구의 지역선택→API→개발정보→좌표→
marker 연결을 실데이터로 확인하지 못했습니다. 기존 3개 구(서초·송파·강동)의 이 경로는
현재 Production에서 동작 중이며 이번 변경이 건드리지 않았습니다. 신규 6개 구는
`region-no-data` 빈 화면이 뜨는 상태가 정상입니다.

---

# 1,190건 좌표·적재 준비 (2026-10-01, 2차)

로컬 PC 수집 결과를 전달받았습니다: raw 1190 / accepted 1190 / rejected 0 /
valid 1190 / insert 1060 / update 130 / duplicate 0 / canonical 1190 /
probable_duplicate 102쌍 / zero_districts 0, 기존 130건 전부 update 매칭
(`recreated_as_insert=0`).

**두 artifact는 이 컨테이너에 없습니다** (`seoul25_raw_20261001.json`,
`seoul25_import_artifact_20261001.json`은 로컬 PC에만 존재). 그리고 지오코딩
자격증명이 이 환경에 하나도 없습니다 — `NAVER_MAP_CLIENT_ID/SECRET`,
`KAKAO_REST_API_KEY`, `VWORLD_API_KEY` 전부 unset. 따라서 좌표 생성은 로컬에서
실행해야 하고, 이번에는 **실행 도구와 검증만** 만들었습니다.

## 1. 좌표 생성 — `scripts/geocode_zipon_seoul25.py`

새 geocoder를 만들지 않았습니다. `services/development_geocode.py`를 그대로 씁니다:
provider 우선순위 NAVER → Kakao → VWorld, 정규화 주소 1건당 호출 1회, 파일 캐시
재사용, 후보가 여럿이면 채택하지 않음.

그 위에 `development_collector.location_rejections()`를 그대로 통과시켜 **사업
district와 지오코딩이 답한 자치구를 비교**합니다. 집계는 네 갈래입니다.

| bucket | 뜻 |
|---|---|
| `geocoded` | EXACT + 서울 bbox + 자치구 일치 → 좌표 채택 |
| `sigungu_mismatch` | 다른 자치구 좌표 → 버림 |
| `unverifiable` | GEOCODE_REVIEW 또는 자치구를 읽을 수 없음 → 검토 |
| `failed` | provider 오류·미해결 |

좌표가 없어도 실행은 실패하지 않습니다. 해당 사업은 좌표 없이 목록에만 남습니다.
`--check-config`(HTTP 없음) / `--dry-run`(호출 없음) / `--live` / `--limit N`
(비용 통제)를 지원합니다. 실데이터 183건으로 dry-run 검증했습니다
(with_address 149 / no_address 34).

## 2. probable duplicate 102쌍

자동 병합·삭제하지 않습니다. 1,190건을 identity 기준 그대로 유지하고, 102쌍은
artifact의 `duplicate_review` 배열에 근거(이름·주소·유형·external_id·source_url)와
함께 보존합니다. `auto_merge: false`가 각 쌍에 붙어 있습니다.

## 3~4. 최종 artifact와 Supabase 반영 준비

`scripts/build_zipon_seoul_import.py`에 추가한 것:

* `--geocode` — 좌표 검증을 통과한 것만 붙입니다(`bucket == geocoded`). 이미 좌표가
  있는 사업은 덮지 않습니다.
* `buckets` — `insert` / `update` / `reject` / `no_coordinate` / `duplicate_review`
* `schema` — `public.development_projects`의 36개 컬럼과 대조해 컬럼이 아닌 작업용
  필드(`location_sigungu`, `location_review` 등)를 payload에서 떨어뜨리고 무엇을
  떨어뜨렸는지 `non_column_fields_dropped`에 남깁니다.
* `--batch-dir` — 기존 reviewed importer가 **그대로 받는** 배치 파일을 10건 단위로
  씁니다.

반영 방식: `rpc/zipon_ingest_candidate`의 **project_id UPSERT**
(`p_expected_revision`으로 낙관적 잠금). DELETE·TRUNCATE·대량 UPDATE 없음.
기존 130건은 update, 신규는 insert로 분류된 채 들어갑니다.

실데이터 183건으로 검증: 19개 배치 파일 생성 → **19개 전부 기존
`scripts/import_zipon_candidates.py`의 `validate_records`를 통과**했습니다
(project_id UUID, project_name/type/sigungu, OFFICIAL_WEBSITE source,
공식 host URL, 64자 content_hash, raw_snapshot). 즉 schema 호환이 말이 아니라
기존 검증기로 확인된 상태입니다.

## 5. 개발지도 조회 — 지역 단위로 변경

`DevelopmentTab`이 더 이상 `developmentMap(undefined, 500, ...)`로 서울 전체를
받지 않습니다.

* 자치구를 고르면 **고른 자치구만** 각각 조회해 `project_id`로 합칩니다
  (`MAX_DISTRICTS=5`이므로 최대 5요청). 카드가 두 장 생기지 않게 중복을 막습니다.
* **실패한 자치구는 이름을 화면에 적습니다.** 기존 설계 주석이 경고한 "한 자치구가
  실패하면 빠진 합계가 전체로 보인다"는 함정을 막는 조건입니다. 전부 실패하면
  `ready`를 내려 숫자를 아예 보여주지 않습니다.
* 아무 지역도 고르지 않으면 지금처럼 서울 전체를 한 번 받지만, `limit`에 닿으면
  서버가 새로 보내는 `truncated` 신호로 "미리보기"라고 적습니다. 잘린 목록을
  "전체 N건"이라고 말하지 않습니다.
* `MAX_DISTRICTS=5` · `MAX_CARDS=200` · `limit=500` 모두 그대로입니다. 올리지
  않았습니다 — 5개 구 기준에서는 충분합니다.

서버 변경은 `truncated` 한 줄입니다(`services/development.py`, `api/realestate.py`).

## 로컬 PC 실행 순서

```bat
cd "C:\Users\user\Desktop\ai-agent - 복사본"
git pull origin claude/keen-clarke-m73n6h

REM 1) 지오코더 자격증명 확인 (HTTP 없음)
venv\Scripts\python.exe -B scripts\geocode_zipon_seoul25.py ^
  --input data\development\seoul25_raw_20261001.json --check-config

REM 2) 좌표 생성 (유료 호출. --limit으로 먼저 소규모 확인 권장)
venv\Scripts\python.exe -B scripts\geocode_zipon_seoul25.py ^
  --input data\development\seoul25_raw_20261001.json --live ^
  --out data\development\seoul25_geocode_20261001.json

REM 3) 최종 import artifact + 배치 파일
venv\Scripts\python.exe -B scripts\build_zipon_seoul_import.py ^
  --input data\development\seoul25_raw_20261001.json ^
  --geocode data\development\seoul25_geocode_20261001.json ^
  --out data\development\seoul25_import_artifact_20261001.json ^
  --batch-dir data\development\seoul25_batches

REM 4) 배치 검증 (DB 접속 없음). 통과 후에만 적재를 판단한다.
venv\Scripts\python.exe -B scripts\import_zipon_candidates.py ^
  data\development\seoul25_batches\batch_0001.json
```

4번까지가 이번 범위입니다. 실제 적재는 `--apply-new-db`와
`ZIPON_IMPORT_SUPABASE_URL` / `ZIPON_IMPORT_SUPABASE_KEY`가 필요하며, 아직
실행하지 않았습니다.
