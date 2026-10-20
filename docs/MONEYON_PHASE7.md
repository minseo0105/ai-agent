# MONEY Phase 7 로컬 구현·검증 보고

2026-10-16. 배포 전 검증 완료. Hugging Face 업로드·Git push·AI LAB 포털 변경 없음.

## 화면 변경

기존의 대등한 ‘내 용돈/내 저금통’ 카드 대신 엄마 은행과 아이의 일주일을 홈의 중심으로 배치했다. 이번 주 받은 용돈, 사용한 돈, 남은 용돈, 서버가 계산한 10% 계산식, 큰 예상 이자, 다음 주 마감·부모 승인·통장 입금 순서가 홈에 나타난다. 계산식은 펼치기나 다른 메뉴 이동 없이 표시된다. 체험 버튼은 계산 카드 다음에 배치했다. 저금통과 예상 저금통 이자는 아래 보조 영역으로 분리했다. 홈·통장·저축 메뉴는 유지했다.

소비·저축·지급 후 전후 금액을 비교하는 영수증을 보여 주며 실제 바뀐 항목만 표시한다. 소비를 부정적으로 평가하지 않고 ‘필요한 곳에는 쓰고, 남은 돈도 잘 관리해 보자’로 안내한다. 용돈 지급 화면에는 엄마 은행 → 용돈 보내기 → 아이 통장과 부모·아이의 현재 잔액을 표시한다.

| 항목 | Phase 6 | Phase 7 |
|---|---|---|
| 용돈 보상 | 용돈 아끼기 보너스 1%, 상한 800원 | 용돈 이자 10%, 상한 없음, 1원 미만 버림 |
| 용돈 이자 입금 | 저금통 | 아이 통장 |
| 저금통 이자 | 2%, 상한 2,000원, 저금통 입금 | 유지 |
| 강조 | 두 보상 나란히 표시 | 용돈 이자 계산식과 예상 이자 우선 |
| 거래 안내 | 긴 한 문장 | 우루미 안내 + 항목별 전후 금액 |

## 원장 및 주간 마감

기존 SQLite 원장과 Mock Banking 복식 분개를 재사용한다. 용돈·용돈 이자는 부모 가상 계좌 출금 및 아이 통장 입금, 저금통 이자는 부모 출금 및 저금통 입금이다. 원장·계좌 분개·지급 상태가 한 트랜잭션 안에서 처리된다. 실패 시 전체 롤백된다. 용돈 지급과 용돈 이자 지급은 서로 다른 거래 유형으로 남는다.

월요일 0시에 끝나는 주간의 잔액을 `trial_closings`에 유형별 원금·금액으로 확정한다. 가상 날짜를 여러 주 건너뛰어도 지난 주별 마감 정보를 저장한다. 부모 승인 시 확정된 금액을 사용하며 같은 주차·유형은 한 번만 지급한다. 같은 요청 재시도는 멱등 처리하고 다른 요청의 중복 지급은 거부한다.

이번 주에 새로 지급받은 용돈 이자는 현재 주의 용돈 이자 계산 대상에서 제외한다. 실제 쓸 수 있는 통장 잔액과 계산 대상이 달라지면 두 금액과 제외 이유를 홈에서 설명한다. 다음 주로 이월된 잔액은 그 다음 주의 원금에 포함될 수 있다. 저금통 원금은 용돈 이자 계산에서 제외한다. 예상 금액은 확정 잔액에 더하지 않는다.

## 검증한 계산

샘플은 실제 거래로 통장 28,500원, 저금통 15,000원을 재현한다. 이번 주 용돈 50,000원 − 소비 8,000원 − 저축 이동 15,000원 + 이전 이자 1,500원 = 28,500원이다. 이전 주 원금 15,000원은 기존 회수 거래로 반환한다.

| 단계 | 아이 통장 | 저금통 | 예상 용돈 이자 | 예상 저금통 이자 |
|---|---:|---:|---:|---:|
| 초기 | 28,500 | 15,000 | 2,850 | 300 |
| 3,000원 소비 | 25,500 | 15,000 | 2,550 | 300 |
| 이어 5,000원 저축 | 20,500 | 20,000 | 2,050 | 400 |
| 다음 주 용돈 이자 승인 | 22,550 | 20,000 | 2,050 | 400 |
| 저금통 이자도 승인 | 22,550 | 20,400 | 2,050 | 408 |

마지막 두 행은 새 주의 예상 금액이다. 지난 주 확정 지급액은 각각 2,050원·400원이며 승인 이후에도 바뀌지 않는다. 새 주 저금통 이자는 저금통에 적립된 금액에 따라 다시 계산된다. 엄마 은행 잔액은 각각 2,050원·400원 감소한다. 별도 검증으로 30,000원 추가 용돈의 부모 출금·아이 입금, 일요일 소비→월요일 마감, 늦은 승인, 부모 잔액 부족 롤백, 서버 재접속 시 확정 정보 유지도 확인했다.

## 검증 결과

- MONEY Python 회귀 125개 통과. Phase 6의 117개에 주간 금융교육 검증 8개 추가. 기존 정책 변경에 해당하는 기대값만 10%·통장 지급 기준으로 갱신했다.
- 기존 어린이 UI·우루미 검사 28개 통과.
- MONEY 전용 Next.js 프로덕션 정적 빌드 및 TypeScript 검사 통과.
- 실제 Chrome·Edge 23개 브라우저 검증 통과. API 응답을 모킹하지 않았다.
- 375·768·1440px에서 홈·저축 변경 화면 확인, 가로 넘침 및 JavaScript 오류 없음.
- 부모 용돈 이체, 소비 후 전후 금액, 저축, 마감 전 승인 차단, 부모 승인 동의, 각각의 지급 계좌·부모 출금, 중복 승인 차단, 통장 이자 입금 내역, 입력 100원 배수, 실패 시 불변, 초기화, 새로고침, 일반 새 탭 및 Chrome/Edge 격리 확인.
- 독립 Space 앱의 가족·관리자·다른 에이전트 API 및 DB 파일 URL은 404임을 확인했다.

명령:
```powershell
.venv/Scripts/python.exe -m unittest tests.test_moneyon tests.test_moneyon_banking tests.test_moneyon_trial tests.test_moneyon_dual_rewards tests.test_moneyon_weekly_education tests.test_moneyon_space tests.test_moneyon_web_package -q
node tests/test_moneyon_child_ui.cjs
node tests/test_moneyon_weekly_browser.cjs
```

결과: `reports/moneyon-phase7/validation-summary.json`, `browser-result.json`.

## 화면 변경 전후 캡처

- 이전 홈: `reports/moneyon-phase7/before-home-375.png`, `before-home-768.png`, `before-home-1440.png`.
- 변경 홈: `reports/moneyon-phase7/after-home-375.png`, `after-home-768.png`, `after-home-1440.png`.
- 거래: `allowance-transfer-375.png`, `expense-change-375.png`, `savings-change-375.png`, `savings-change-768.png`, `savings-change-1440.png`.
- 마감·지급: `approval-pending-375.png`, `interest-received-375.png`, `interest-ledger-375.png`.

## 변경 파일 및 배포 대기

런타임: `services/moneyon_trial.py`, `services/moneyon.py`, `api/moneyon_trial.py`.
화면: `ChildExperience.tsx`, `TrialExperience.tsx`, 신규 `WeeklyJourney.tsx`, `types.ts`, `child.css`.
MONEY 배포 전용: `deploy/moneyon/page.tsx`, `deploy/moneyon/README.md`, `scripts/prepare_moneyon_space.py`, `scripts/check_moneyon_space.py`.
검증: `test_moneyon_trial.py`, `test_moneyon_dual_rewards.py`, `test_moneyon_web_package.py`, 신규 `test_moneyon_weekly_education.py`, `test_moneyon_weekly_browser.cjs`.

소스 배포 후보: `reports/moneyon-phase7-release/`. 허용된 소스 40개 + manifest 1개. 검증한 정적 빌드 결과는 `web/out`에 별도 포함했으며 일반 소스 업로드 대상에는 포함하지 않는다. Docker에서는 소스로 다시 빌드한다. 런타임 데이터·비밀키·운영 DB는 패키지에 없다. `MONEYON_TRIAL_ENABLED=1`과 체험 전용 앱 구성은 유지한다.

새 정책은 새 체험 또는 초기화부터 적용된다. 기존 체험 주차의 정책 스냅샷 및 기존 등록 가족 정책을 강제로 변경하지 않았다. 기존 Phase 4~6 화면 전용 브라우저 스크립트는 과거 문구·정책 기준이며 현재 검증 진입점은 `test_moneyon_weekly_browser.cjs`다. 실제 어린이 대상 사용성 조사 및 실물 휴대전화 테스트는 하지 않았다. 모바일 검증은 실제 데스크톱 Chrome의 반응형 화면 기준이다.

사용자 승인 후 `MINSEO2/moneyon-demo`에만 재배포하고 공개 URL에서 같은 시나리오를 재검증해야 한다. 현재 공개 서비스는 아직 Phase 6이다.
