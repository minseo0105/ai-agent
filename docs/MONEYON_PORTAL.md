# AI LAB 메인 포털 MONEY 카드

## 배포 대상과 범위

- 대상 Space: `MINSEO2/digital-ai-lab` (기존 protected Docker Space).
- 공개 포털: https://minseo2-digital-ai-lab.hf.space/
- MONEY 연결: https://minseo2-moneyon-demo.hf.space/
- MONEY Space는 이번 작업에서 변경하지 않았다.

로컬 작업본은 아직 배포하지 않은 새 홈 디자인을 포함하고 있어 그대로 업로드하지 않았다. 운영 파일 뷰어에서 확인한 커밋 `7d5a06f1ec6a7006fcc2b3dd82eb0e286888f1f4`의 소스를 검증용 사본으로 저장하고, 그 서비스 목록에만 MONEY를 추가했다.

운영 반영 파일은 정확히 두 개다.

1. `web/src/lib/services.ts`: 마지막에 MONEY 등록, 절대 HTTPS 링크를 외부 링크로 판별.
2. `web/public/ailab/money.svg`: 새 저금통 아이콘.

검토된 업로드 파일은 `reports/moneyon-portal/publish/`, SHA-256 목록은 `reports/moneyon-portal/publish-manifest.json`에 있다. 루트 전체 업로드, Git push, 기존 배포 스크립트의 대량 동기화는 실행하지 않았다. 운영 DB, 관리자 공개 설정, API, 비밀키, 다른 에이전트 소스는 변경하지 않았다.

## 기존 렌더링 구조

`services.ts`의 `SERVICES` 배열을 `ServiceGrid.tsx`가 사용한다. 접근 상태의 visible 설정으로 걸러내고 분류 필터를 적용한다. 모든 카드는 같은 `ServiceLink` 및 Tailwind 클래스로 렌더링한다. 제목의 ` · ` 구분자를 기준으로 이름과 설명을 분리한다. MONEY는 이 기존 구조를 그대로 사용한다.

현재 공개 순서 ZIP:ON → 보고서 작성기 → AI 사주를 보존하고 마지막에 MONEY를 배치했다. 기존 숨김 서비스는 숨김 상태를 유지한다. MONEY 분류는 Prototype이다. 모바일 2열, 태블릿 3열, 데스크톱 4열의 기존 그리드를 유지한다.

MONEY 표시 이름은 `MONEY`, 설명은 `우루미와 함께하는 어린이 금융 놀이터`, 보조 문구는 `용돈을 받고, 쓰고, 저축하면서 이자 보너스를 배워요.`이다. 기존 카드의 한 설명 영역에서 두 문구를 이어 표시한다. 링크는 `target=_blank`, `rel=noopener noreferrer`로 열린다.

## 로컬 검증

- 운영 홈 소스를 사용하는 독립 검증본 프로덕션 빌드 성공. 운영 포털에 없는 로컬 미배포 홈 컴포넌트는 검증본 타입 검사 대상에서 제외했다.
- 주 작업본 TypeScript 검사도 통과했다.
- 실제 Chrome에서 375px, 768px, 1440px 검증 통과.
- 기존 세 카드의 링크·텍스트·CSS 클래스·순서 일치, MONEY 1개만 추가, 같은 카드 폭, 2/3/4열, 가로 넘침 없음, 새 아이콘 정상 로드 확인.
- MONEY 클릭 시 실제 공개 체험 URL의 `바로 체험하기` 버튼까지 확인. opener 분리와 Prototype 필터도 통과.
- 로컬 접근 상태만 기존 공개 상태의 읽기 전용 사본을 사용했고, 운영 설정에는 쓰지 않았다. 다른 에이전트의 생성·검색 API는 호출하지 않았다.

검사: `tests/test_moneyon_portal_browser.cjs`
결과: `reports/moneyon-portal/local-result.json`
캡처: `reports/moneyon-portal/local-375.png`, `local-768.png`, `local-1440.png`.

## 공개 검증

- 배포 커밋: `a01299276222a56e7db3c6265aa4b3e174cefa88`.
- Hugging Face에서 Building → Running 전환 확인. Docker 빌드 및 공개 서비스 기동 성공.
- 실제 공개 포털의 Chrome 375px·768px·1440px 검사 모두 통과: `reports/moneyon-portal/live-result.json`.
- MONEY 카드 1개 표시, 요청한 이름·설명·보조 문구, 저금통 SVG, 같은 카드 폭·스타일, 2/3/4열, 가로 넘침 없음, Prototype 필터를 확인했다.
- 실제 카드 클릭 후 새 탭 URL이 MONEY 공개 도메인이고 `바로 체험하기`가 표시됨을 세 화면 크기 모두 확인했다. 원래 포털은 열린 상태로 유지되고 새 탭의 opener는 없다.
- 기존 세 카드의 전체 문구·링크·클래스·순서가 배포 전 기록과 일치한다. JavaScript 오류 없음.
- 공개 캡처: `reports/moneyon-portal/live-375.png`, `live-768.png`, `live-1440.png`.
- MONEY 전용 Space의 커밋 `d7d2b2769e98c675c2a4a2f1c06141734c99391b`가 그대로임을 별도 조회로 확인했다.
- 모바일 검증은 실제 Chrome의 반응형 화면 검사이며 실물 휴대전화 검증은 아니다.

## 소스 유지

기존 GitHub 자동 배포는 저장소의 전체 허용 파일을 Space에 동기화한다. 최초 HF 직접 반영 후 GitHub 원본에 MONEY가 없어 UI 자동 배포가 카드를 제거했다.

2026-10-16 복원: GitHub main 커밋 `32c3a70c56a13f7d5818b59624eb8145c706e6a2`에 `web/src/lib/services.ts`, `web/public/ailab/money.svg` 두 파일만 반영했다. 최신 남색·코발트 히어로와 파스텔 카드 렌더러는 변경하지 않았다. 이후 자동 배포에도 MONEY 서비스 정의가 포함된다. 배포 워크플로: https://github.com/minseo0105/ai-agent/actions/runs/38778164902

자동 배포 성공 및 HF Running 확인. 공개 URL 실제 Chrome 375px·768px·1440px 모두 통과: 카드 표시, MONEY 체험 화면 연결, 기존 카드와 색상 유지, 필터, 가로 넘침 없음, JavaScript 오류 없음. `source-fix-checks/live-result.json` 및 `live-375.png`, `live-768.png`, `live-1440.png`에 기록했다. 초기 확인은 HF 재시작 중 시간 초과했으며 Running 후 재검증은 모두 통과했다.

최신 UI 기준 독립 프로덕션 빌드 및 실제 Chrome 375px·768px·1440px 로컬 검증 통과. 기존 카드 순서·문구·링크·파스텔 배경색, MONEY 카드 폭·외부 링크·Prototype 필터·가로 넘침·JavaScript 오류를 검사했다. 검사 스크립트: `tests/test_moneyon_portal_source_fix.cjs`, 결과와 캡처: `reports/moneyon-portal/source-fix-checks/`.
