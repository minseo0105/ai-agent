# ZIP 대시보드 1단계 구현 계획

설계: `docs/superpowers/specs/2026-11-06-zip-dashboard-phase1-design.md` (조건부 승인, 보완 6개 반영)
원칙: 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다. 작업마다 집온 Python 테스트 전체와(프론트 변경 시) typecheck를 돌린다. DB 변경·배포·PR·병합·강제 푸시는 하지 않는다.

## 작업 순서와 파일

### T1. 8단계 타임라인 빌더 (백엔드, 순수 함수)
- 신규 `services/development_timeline.py`: `process_timeline(project_type, program, stage_history, current_official_stage, verified_level, source)` → 설계 §3 구조.
- 신규 `tests/test_zipon_timeline.py`: 공식 14단계 전수 매핑 / 재개발·재건축·기타 유형 흐름 / 공식 우선(재개발인데 안전진단 날짜 있음, 현재 단계가 8단계 밖, 해산·청산, 날짜가 현재 단계 뒤에 있음) / 진행 문구 / 목록 기반 사업 / 알 수 없는 단계명 / 입력 불변(원본 수정 안 함).

### T2. 상세 API
- 신규 `services/development_detail.py`: 사업 1건 REST 조회(UUID 검증), 출처·이력 병렬 조회, 60초 캐시, `connections` 계산(실제 설정에서).
- 변경 `api/realestate.py`: `GET /development/projects/{project_id}` 1개(기존 라우터·미들웨어 상속).
- 신규 `tests/test_zipon_detail_api.py`: 접근 권한(`check_api` 공개·구성원·숨김·점검 × 토큰 없음/구성원/관리자) / UUID 검증 422 / 404 / 503 / 부분 실패 / 병렬·캐시 / 응답 크기 상한 / RPC 행과 REST 행의 `present_project` 공통 필드 일치 / `connections` 상태가 실제 설정과 구현 여부와 일치.

### T3. 투자금 계산 (프론트 순수 함수)
- 신규 `web/src/lib/investmentCalc.ts`, `tests/js/investment_calc.test.mjs`(Node 내장 테스트 러너), `tests/test_zipon_dashboard_js.py`(unittest에서 node 테스트 실행, node가 없으면 건너뜀).
- 테스트: 설계 §5 관계 검증식 4개(중복 계산 방지) / 음수·0·양수 분담금 / 필수값 없음 / 시나리오 조정 / 비정상 입력.

### T4. 클러스터·마커 계획 (프론트 순수 함수)
- 신규 `web/src/lib/clusterPoints.ts`, `web/src/lib/markerPlan.ts`(개별 마커·클러스터·선택 보존을 한 번에 계산), `tests/js/cluster_points.test.mjs`.
- 테스트: 설계 §7-1 정확성 7개 + 성능(1,190점·10,000점) + **1,190건 고정 데이터 회귀**(마커 수 = 좌표 있는 사업 수, 개별+클러스터 구성원 합 = 좌표 있는 사업 수).

### T5. 타입과 API 클라이언트
- 변경 `web/src/lib/realestate.ts`: `ZoneDetail`·`ProcessTimeline`·`Connections` 타입, `estateApi.developmentDetail(id)`.
- 신규 `web/src/lib/zipTypes.ts`: `ZoneTrade`·`RightsAssessment`·`ListingRecord`(2·3·6단계용 자리).

### T6. 상세 패널 컴포넌트
- 신규 `web/src/components/realestate/zip/`: `ProcessTimeline`, `CheckpointCard`, `FeatureStatusCard`, `InvestmentSimulator`, `tabs/{ProjectInfoTab,TradesTab,InvestmentTab,TradeGuideTab}`, `ZoneDetailPanel`.

### T7. 대시보드 셸과 지도
- 변경 `DevelopmentTab.tsx`: 데이터·필터 로직을 훅 `useZiponDevelopment`로 분리(동작 변경 없음).
- 신규 `zip/ZipDashboard`, `DashboardToolbar`, `ZoneList`, `MobileSheet`.
- 변경 `ZiponMap.tsx`: `fill` 모드, `focusId`, 클러스터 렌더, 선택 시 중심 보정, `tradeMarkers?` 자리, 크기 변경 알림.
- 변경 `EstateMonitor.tsx`·`realestate/page.tsx`: 개발지도 탭만 넓은 폭, 소개 영역 축소. 변경 `globals.css`: `--zip` 퍼플 토큰(라이트·다크).

### T8. 회귀와 화면
- `tests/test_frontend_ux.py` 등 소스 문자열 검사 영향 확인, 의도된 변경만 이유를 적고 갱신.
- 집온 Python 전체, 골프 정책, 프론트 typecheck·build, 기존 탭 렌더 확인.
- Playwright 캡처 1440 / 768 / 390px(API 가짜 응답, 지도는 SDK 접속 불가로 대체 영역).

### T9. 문서·보고
- 실제 변경 파일, 화면 캡처, 테스트 결과, 남은 제약을 정리해 보고. 운영 정합성 대조용 읽기 전용 SQL을 문서로 제공.

## 커밋 단위
T1, T2, T3+T4, T5+T6, T7, T8 순으로 작업 단위마다 커밋하고 일반 푸시한다(강제 푸시 없음).

## 위험과 대응
- 소스 문자열 검사(`test_frontend_ux.py`)가 구조 변경에 깨질 수 있음 → T8에서 목록화 후 의도된 항목만 갱신
- 지도 컨테이너 크기 변경을 NAVER가 따라오지 못함 → 크기 변경 시 `resize` 이벤트 통지(기존 `Event.trigger` 사용)
- 샌드박스에서 NAVER SDK 접속 불가 → 마커·클러스터 계산은 순수 함수로, 지도 연동은 가짜 `naver.maps`로 검증하고 실제 렌더링은 배포 후 확인 필요로 보고
