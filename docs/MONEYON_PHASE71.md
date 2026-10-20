# MONEY:ON Phase 7.1 — 이자니와 모바일 UI 리뉴얼

## 추가 반영 — 100원 단위 실험·다음 주 체험

`ChildExperience.tsx`의 이자 실험 슬라이더, ±100원 버튼, 직접 입력을 모두 100원 단위로 통일했다. 비정상 단위는 안내 후 100원 단위로 내림 보정하고, 통장 잔액 이하의 입력 가능한 최대 100원 배수로 제한한다. 잔액 자체와 이자 결과는 반올림하지 않는다. API 호출 전 200ms 대기를 없애 금액 변경 즉시 기존 계산 API를 호출하며 오래된 응답은 반영하지 않는다. 예: 남은 돈 25,500원에서 333원 입력 → 300원 보정 → 예상 이자 2,520원. +100원은 2,510원, −100원은 다시 2,520원이다.

현재 날짜의 역할을 확인했다. 체험은 방문자별 `moneyon_demo_workspaces.business_date`가 거래의 업무 날짜, 주간 마감과 승인 기준을 결정한다. 실제 시계는 토큰의 24시간 만료 등에 사용한다. 일반 이용 모드의 실제 날짜·주간 마감·부모 승인 경로는 변경하지 않았다.

아이 화면의 날짜 선택란을 없애고 ‘체험 속 날짜’와 ‘1주일 뒤로 이동’을 표시한다. 현재 체험일에 UTC 달력 기준으로 7일을 더한 **절대 목표 날짜**를 기존 `/date` API에 보낸다. 시스템 실제 날짜를 섞지 않는다. 같은 버튼의 네트워크 재시도는 같은 목표 날짜를 사용한다. 진행 중 중복 클릭은 기존 실행 잠금으로 막고, 승인 대기 중에는 먼저 두 이자 승인을 마치도록 다음 이동을 막는다. ‘체험 속 날짜가 실제 오늘과 다르다’는 설명도 표시한다.

영향 범위는 프런트엔드 `ChildExperience.tsx`, `TrialExperience.tsx`, `blue.css` 및 테스트다. 금융 API·날짜 엔진·원장은 수정하지 않았다. 기존 절대 날짜 API는 내부 테스트용으로 보존되며, 새 UI만 주 단위로 제한한다. 서버가 계속 보장하던 마감 원금 고정·주차/유형별 중복 지급 방지·동일 날짜 재시도를 그대로 사용한다.

추가 검증: Python **129개**, 어린이 UI **30개**, 실제 Chrome/Edge 브라우저 **36항목** 통과. 375·390·430·768·1440px에서 금액 보정, 슬라이더/버튼/직접 입력, 정확한 이자 결과, 1주 이동, 승인 대기 중 이동 차단을 확인했다. 날짜 동일 요청의 재시도·동시 요청, 연속 두 주 이동 후 과거 지급 정보 불변, 중복 지급 거부, 초기화와 방문자 격리도 검증했다. UTC 날짜 도우미는 월말·연말·윤년 등 4개 경계 사례를 별도 확인했다.

최신 배포 후보는 `reports/moneyon-phase71-week-release/`이다. 로컬 8118 미리보기도 이 버전을 사용한다. Hugging Face 배포는 하지 않았다. 아래 본문은 최초 7.1 리뉴얼 기록이며, 테스트 개수·최신 후보 경로는 이 추가 반영 내용을 우선한다.

2026-10-16. 실제 동작하는 로컬 앱 구현·검증 완료. Hugging Face 배포 및 Git push 없음. AI LAB 포털과 다른 에이전트 변경 없음.

## 기존 분석과 결과

앱 위치는 `web/src/app/moneyon/`, 체험 진입점은 `TrialExperience.tsx`, 어린이 화면은 `ChildExperience.tsx`, 금융교육 홈은 `WeeklyJourney.tsx`다. 금융 로직은 `services/moneyon*.py`, 체험 API는 `api/moneyon_trial.py`다. 전용 Space는 `deploy/moneyon/space_app.py`와 Dockerfile을 사용한다.

기존 Phase 7을 실제 Chrome에서 실행해 375·390·430·768·1440px 캡처를 저장했다. 주요 문제는 작은 보조 글씨, 민트/초록 카드의 반복, 화면 하단으로 밀리는 캐릭터와 거래 버튼, 긴 안내 및 설정으로 늘어난 스크롤이었다. 숫자와 공식은 정확했지만 ‘내가 지금 쓸 수 있는 돈’과 거래 행동이 분산돼 있었다.

리뉴얼 홈은 남은 용돈 → 예상 이자와 계산식 → 돈 쓰기/저금하기/용돈 받기 → 이번 주 현황 순서다. 375px 첫 화면에서 두 핵심 금액과 세 행동 버튼을 볼 수 있다. 상세 규칙·체험 관리·성장 메뉴는 펼쳐 보도록 정리했다. 기본 홈 길이는 최종 캡처의 `validation-summary.json`에 기록했다. 기존 2,672px에서 약 1,700px대로 줄었다.

## 디자인 시스템

`blue.css`에 색상·그림자·둥근 모서리·간격·본문/금액 크기 토큰을 정의했다. `.mk`, `.mk-sheet`, `.mk-entry`에만 적용해 포털에 영향을 주지 않는다.

| 토큰 | 값 | 적용 |
|---|---|---|
| Primary | #0067AC | 주요 버튼·금액·강조 |
| Bright | #2497E3 | 보조 아이콘·포커스·캐릭터 |
| Deep | #084A86 | 잔액 카드·제목 |
| Light | #DCEFFF | 예상 이자·보조 영역 |
| Background / White | #F5FAFF / #FFFFFF | 화면·입력·카드 |
| Yellow / Pink | #FFCB57 / #FF8FB3 | 동전·작은 캐릭터 포인트 |

그라데이션은 주요 잔액 카드에 사용한다. 금액은 32~48px, 일반 입력은 16px, 주요 본문은 14~15px로 표시한다. 키보드 포커스, 최소 44px 버튼, 하단 safe-area, 모션 감소 설정을 적용했다. 제안 디자인이며 우리금융 공식 브랜드 적용을 주장하지 않는다.

## 이자니

`Izani.tsx`는 흰색·하늘색 몸체, 파란 귀, 동전 목걸이의 오리지널 강아지 SVG다. 동일한 실루엣과 비율에 표정·소품을 바꿔 기본 인사, 용돈 도착, 소비 안내, 이자 계산, 이자 지급 축하, 저축 성공, 격려의 7가지 상태를 제공한다. 지급 축하는 짧게 한 번 재생하며 모션 감소 설정에서는 정지한다.

기존 `Woorumi.tsx`는 수정하지 않았다. 원본 사본도 `reports/moneyon-phase71/Woorumi.original.tsx`에 보존했다. 새 표시 이름·대사·상태는 `moneyonCoach.ts`에서 관리한다. 공식 금융회사 캐릭터가 아니라는 설명을 유지한다.

이자니 결과물: `reports/moneyon-phase71/izani-gallery.png`, `izani/index.html`, 7개 개별 SVG. `scripts/preview_moneyon_izani.cjs`로 실제 앱 컴포넌트에서 재생성할 수 있다.

## 6개 주요 화면

| 화면 | 실제 구현 |
|---|---|
| 홈 | 블루 잔액 카드, 연결된 예상 이자·10% 공식, 세 행동 버튼, 실제 주간 현황, 별도 저금통 |
| 엄마 은행 | 보내는 부모 계좌/받는 아이 계좌, 현재 잔액, 송금 화살표, 직접 입력·빠른 금액 버튼, 이체 완료 영수증 |
| 돈 쓰기 | 이자니 안내, 용도·금액·분류, 100원 배수, 소비 후 잔액·예상 이자 전후 비교 |
| 이자 계산 | 실제 정책 엔진과 연결된 실험 금액 및 결과, 실제 원장에 영향을 주지 않는 설명 |
| 이자 지급 | 주간 마감→부모 승인→입금, 두 이자 탭 분리, 지급 상태/내역, 지급 직후 보이는 이자니 축하 |
| 저금통 | 저축액·목표·달성률·저축 이동·별도 이자·지급 내역 |

`TrialSheet.tsx`는 네이티브 dialog를 사용한다. 배경의 조작을 막고 포커스를 내부에 유지하며 Escape/닫기와 포커스 복귀를 지원한다. 길어진 승인 내용은 시트 안에서 스크롤한다. 승인 직후에는 맨 위로 돌아가 축하가 보인다.

Canva 정적 시안은 제작하지 않았다. 실제 앱의 HTML/CSS로 6개 화면을 구현하고 390×844px 브라우저 캡처를 디자인 검토본으로 제공한다. 정적 이미지를 앱 UI로 붙이지 않았다. 화면 모음은 `reports/moneyon-phase71/screens.html`이다.

## 금융 로직 유지

`services/moneyon.py`, `services/moneyon_trial.py`, `services/moneyon_accounts.py`, `api/moneyon_trial.py`의 작업 전후 SHA-256이 일치한다. 계산 API, 지급 목적 계좌, 주간 마감, 중복 지급 방지, 세션·초기화 정책을 변경하지 않았다. 포털 `web/src/app/page.tsx`, `web/src/lib/services.ts`도 해시가 일치한다.

초기 통장 28,500원·예상 용돈 이자 2,850원. 3,000원 소비 시 25,500원·2,550원. 이어서 5,000원 저축 시 통장 20,500원·저금통 20,000원, 예상 용돈 이자 2,050원·저금통 이자 400원. 마감 후 승인하면 용돈 이자는 통장, 저금통 이자는 저금통에 각각 적립된다. 이번 주 받은 용돈 이자의 같은 주 중복 계산 제외도 유지한다.

## 테스트

- MONEY Python 125개 통과: 원장·이체·마감·부모 승인·중복 지급·별도 이자·정산 실패 롤백·초기화·격리·배포 패키지.
- 어린이 UI/캐릭터 30개 통과: 기존 28항목에 새 7번째 상태를 브랜드 2가지 조건으로 검증한 2항목 추가.
- 전용 Next.js 프로덕션 빌드·TypeScript 검사 통과.
- 실제 Chrome·Edge 브라우저 32항목 통과. API 모킹 없음.
- 375·390·430·768·1440px: 가로 넘침·금액 잘림 없음, 거래 버튼 최소 44×44, 정상 거래와 새로고침, 다른 탭/Chrome·Edge의 데이터 격리 확인.
- 390×844px의 6개 주요 화면 캡처. 입력 화면 높이를 520px로 줄여 입력·스크롤 가능, native dialog 포커스 유지/복귀, 모션 감소, 지급 후 축하 가시성 확인.
- 100원 배수의 HTML 입력 검증 및 API 422, 중복 지급 409, 실패 시 원장 불변, 비체험 API/DB URL 404 확인.

실행:
```powershell
.venv/Scripts/python.exe -m unittest tests.test_moneyon tests.test_moneyon_banking tests.test_moneyon_trial tests.test_moneyon_dual_rewards tests.test_moneyon_weekly_education tests.test_moneyon_space tests.test_moneyon_web_package -q
node tests/test_moneyon_child_ui.cjs
node tests/test_moneyon_blue_browser.cjs
```

결과: `reports/moneyon-phase71/browser-result.json`, `validation-summary.json`, `untouched-baseline.json`.

## 변경 파일

- 신규: `Izani.tsx`, `TrialSheet.tsx`, `blue.css`.
- 화면/브랜드: `ChildExperience.tsx`, `WeeklyJourney.tsx`, `TrialExperience.tsx`, `web/src/lib/moneyonCoach.ts`, `deploy/moneyon/page.tsx`.
- 전용 패키지: `scripts/prepare_moneyon_space.py`에 신규 UI 파일만 추가.
- 검증: `tests/test_moneyon_child_ui.cjs`, `tests/test_moneyon_web_package.py`, 신규 `tests/test_moneyon_blue_browser.cjs`.
- 캐릭터 미리보기 생성: `scripts/preview_moneyon_izani.cjs`.

정확한 경로 목록은 `reports/moneyon-phase71/changed-files.json`에 저장했다.

## 캡처 및 남은 확인

변경 전후: `before-home-{375,390,430,768,1440}.png`, `after-home-{375,390,430,768,1440}.png`.
모바일 첫 화면: `home-viewport-{375,390,430,768,1440}.png`.
6개 화면: `design-{home,mom-bank,spend,interest-calculation,interest-payment,piggy-bank}-390.png`.
전후 금액: `expense-change-375.png`, `savings-change-375.png`. 지급 내역: `interest-ledger-375.png`.

알려진 기능 오류는 최종 검증에서 발견되지 않았다. 실물 Android/iPhone의 실제 소프트 키보드·노치와 어린이 대상 사용성 조사는 미실시다. 모바일 검증은 실제 Chrome의 반응형/축소 화면 기준이다. 정적 캡처의 하단 고정 메뉴가 전체 페이지 중간에 나타나는 경우는 캡처 당시 뷰포트 위치 때문이며, 실제 화면에서는 하단에 고정된다.

## 배포 준비

최종 소스 후보는 `reports/moneyon-phase71-release/`다. 소스 43개 + manifest 1개를 허용 목록으로 관리하며, 검증한 정적 결과 `web/out`은 로컬 검토용으로 별도 포함했다. Docker에서는 소스로 다시 빌드한다. 테스트 DB·토큰·비밀키는 소스 허용 목록에 없다. MONEY 체험 전용 구성과 `MONEYON_TRIAL_ENABLED=1`, 7860 포트를 유지한다.

아직 재배포하지 않았다. 승인 후 대상은 `MINSEO2/moneyon-demo` 하나이며 AI LAB 포털에는 업로드하지 않는다. 공개 서비스 검증은 승인 후 실제 재배포 단계에서 수행해야 한다.
