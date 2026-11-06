# ZIP:ON 1차 대시보드 — 검증 기록과 실제 NAVER SDK 체크리스트 (2026-11-06)

## 1. 마지막 커밋 기준 재실행 결과

| 검사 | 명령 | 결과 |
| --- | --- | --- |
| TypeScript | `cd web && npx tsc --noEmit` | 통과(오류 0) |
| Next.js 프로덕션 빌드 | `cd web && npm run build` | 통과 |
| JavaScript 단위 테스트 | `node --test tests/js/*.test.mjs` | 86개 통과 / 실패 0 |
| Python ZIP:ON 테스트 | `python -m unittest discover -s tests -p "test_zipon*.py"` | 817개 통과, 실패 0 |
| 골프 정책 테스트 | `python -m unittest discover -s tests -p test_golf_import_policy.py` | 13개 통과 |
| 브라우저 검증(Playwright, 가짜 `naver.maps`) | 샌드박스 스크립트 | 53개 중 53 통과 |
| Python 전체 | `python -m unittest discover -s tests -p "test*.py"` | 1291개 실행, **10건 실패 — main과 동일(§2)** |

## 2. 기존 실패 테스트는 이번 변경과 무관하다

사용자가 지목한 `ServiceGridResponsiveTests` 2건(`test_cards_share_a_height_and_do_not_overflow`,
`test_the_grid_adapts_to_available_width_and_card_count`)을 포함해 전체 실패는 10건이다.

근거:

1. **main에서도 똑같이 실패한다.** PR #1 병합 커밋(`ec5c62f`, 이번 작업 이전)을 별도 worktree로 받아
   같은 명령을 돌렸다. 실패/오류 목록이 이번 브랜치와 **한 줄도 다르지 않았다**
   (main 1207개 실행 중 10건 실패, 이번 브랜치 1291개 중 같은 10건).
2. **이번 브랜치는 해당 파일을 건드리지 않았다.** `git diff origin/main...HEAD --name-only`에
   `ServiceGrid`·`golf`·`stockon`이 들어간 파일이 없다(변경 51개 파일).
3. **원인이 서로 다르다.** ServiceGrid 2건은 테스트가 옛 클래스명
   (`grid-cols-[repeat(auto-fit,minmax(min(100%,16rem),1fr))]`, `flex h-full min-w-0 flex-col`)을 기대하는데
   `web/src/components/ServiceGrid.tsx`는 이미 `grid-cols-2 … lg:grid-cols-4`, `min-h-[176px]`로 바뀐
   상태다(코드가 먼저 바뀌고 테스트가 따라가지 못함). 나머지 8건은 골프 데이터·freshness 테스트(7건)와 StockOn 테스트(1건)다.

| 실패 | 파일 |
| --- | --- |
| ServiceGrid 2건 | `test_frontend_ux.ServiceGridResponsiveTests` |
| 골프 7건 | `test_golf_freshness`(4), `test_golf_master_adapter`(2: 로컬 데이터 553건 기대 vs 527), `test_golf_service_pool`(1) |
| StockOn 1건 | `test_stockon.ServiceTest.test_ai_failures_are_recorded_for_admin_only` |

이번 PR에서 고치지 않았다(범위 밖, 골프는 CLAUDE.md 정책상 별도 검토 필요). 별도 이슈로 다루길 권한다.

## 3. 실제 NAVER 지도 SDK에서 추가 검증할 체크리스트

샌드박스는 NAVER SDK를 불러올 수 없어 위 53개 브라우저 검사는 **가짜 `naver.maps`** 기준이다.
배포 전(스테이징) 실제 키로 확인한다.

**지도 로드와 마커**
- [ ] 실제 지도가 뜨고 콘솔 오류가 없다(인증 실패 시 `ncpKeyId` 도메인 등록 확인).
- [ ] 1,190건 중 좌표 보유 건(운영 기준 849건)이 마커로 보이고, 좌표 없는 건은 목록에만 있다.
- [ ] 유형별 마커 색(재개발/재건축/신속통합/모아타운/기타)과 범례가 맞다.

**클러스터(`clusterPoints`, gridSize 64, maxZoom 14)**
- [ ] 줌 아웃 시 숫자 클러스터, 줌 인 시 개별 마커로 풀린다(줌 14 이상은 개별).
- [ ] 클러스터 클릭 시 해당 구성원 bounds로 `fitBounds`된다.
- [ ] 선택한 사업은 클러스터에 묻히지 않고 항상 개별 마커다.
- [ ] 1,190건에서 줌/팬 중 끊김이 없다(계산은 0.7ms지만 DOM 마커 수가 변수다).

**선택·동기화**
- [ ] 마커 클릭 → 패널 상세 열림, 목록 클릭 → 지도 이동·강조(양방향).
- [ ] `panBy`(데스크톱 패널·모바일 시트에 가려지지 않게 밀기)가 실제 SDK에서 동작한다.
- [ ] 모바일 peek 시트 뒤에서 선택 마커가 화면 안에 남는다(가짜 SDK에서는 통과).
- [ ] `#zone=<id>` 해시로 직접 접속하면 해당 구역이 선택되고, 새로고침해도 유지된다.

**기기**
- [ ] 아이폰 Safari/안드로이드 Chrome에서 시트 드래그가 지도 팬과 충돌하지 않는다(`touch-action`).
- [ ] 주소창이 접히는 모바일 브라우저에서 `100svh` 높이가 맞다.
- [ ] 다크 모드에서 마커·시트·보라색 브랜드 색 대비가 충분하다.

**경계(2차 대비)**
- [ ] 확인된 경계가 있는 구역(현재 0건)에서 Polygon/MultiPolygon이 올바르게 그려진다 — 2차에서 확인.

## 4. 이번 PR에서 정리한 "미연동" 표시(요구 5)

- 실거래 탭: 연결 배지 `미연동 · 연결되지 않음` / `이 구역 실거래 미연동 · 자치구 조회만 가능`. 상태는 서버 `connections.trades`만 근거로 하고, 구역 거래 목록·구역 안/밖 분류는 `아직 제공하지 않음`.
- 거래가이드 탭: 일반 확인 질문만 제공. 사전진단 엔진 배지 `미연동 · 연결되지 않음`, "거래 가능/안전한 매물"을 표시하지 않음.
- 가상 데이터 금지를 테스트로 고정했다: `tests/test_zipon_unconnected_tabs.py`(금액·면적 숫자 리터럴, `random/sample/mock` 문자열, 단정 문구 부재).
- 스크린샷의 "예시 거여동14구역"은 **검증용 목(mock) API의 데이터**이며 실제 사업이 아니다. 지도 안내 문구도 "지도 SDK 대체 화면(샌드박스 검증용)"이다.

## 5. 운영 DB 정합성 읽기 전용 SQL(요구 4)

- 파일: `supabase/review/20261106_zipon_dashboard_consistency_readonly.sql` (`BEGIN TRANSACTION READ ONLY` … `ROLLBACK`, SELECT만. `tests/test_zipon_consistency_sql.py`가 쓰기·DDL·쓰기 RPC 부재를 검사하고, `pglast`로 구문을 파싱해 SELECT/트랜잭션 문만 있음을 확인했다.)
- 이 세션에서는 **실행하지 않았다.** 운영 DB에 접속하지 않았다.
- 기대값(2026-11-06 canary dry-run): `projects 1190`, `locations 849`, `verified_boundaries 0`, `verified_projects 0`.
- **상세 이력 119건**은 DB가 아니라 저장소의 `services/development_stage_catalog.json`(130건 중 유효 119건)에서 온다. DB 쪽은 SQL [4], 패키지 쪽은 `python scripts/checks/zipon_catalog_counts.py`(출력 `catalog_projects=130 usable_stage_view=119 with_milestones=121`)로 센다.
- **검토 대기 994건**은 canary **dry-run**이 보고한 `review_required` 건수다. dry-run은 큐 테이블에 쓰지 않으므로 SQL [7]의 큐 행 수가 0이어도 정상이다. 사유별 분해와 해석은 `docs/zipon_phase2_3_plan_2026-11-06.md` §2.
