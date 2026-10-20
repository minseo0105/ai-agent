# MONEY Phase 7.2 구현 및 배포 검증

## 변경 원인과 결과

기존 결산은 과거 원금 회수와 이자 입금을 기초 잔액에 섞고, 저축 입금에서 출금을 차감한 순액을 표시했다. 이제 같은 주/용돈통장 거래를 기준으로 기초 잔액 + 용돈 + 용돈 이자 + 기타 입금 + 저축 출금 − 소비 − 저축 입금 − 기타 출금을 대조한다. 합계가 실제 wallet과 다르면 상태 조회에서 오류로 감지한다. seed는 15,000 + 50,000 + 1,500 − 15,000(이전 원금 회수) − 8,000 − 15,000 = 28,500원이다. 화면 상세는 접어서 제공한다.

Phase 7.1에서 수정한 현재 wallet 기준 10% 계산을 유지한다. 14,250원은 1,425원, 소비 3,000원 뒤 11,250원은 1,125원이다. 원 미만 절사, 마감 금액 고정, 저축통장 2%/주간 전체 상한 2,000원은 보존했다.

종료된 미승인 주차가 있으면 소비·저축·용돈 지급을 거부하는 guard가 실제 거래를 막고 있었다. 이를 해제하고 종료된 주차의 eligible 값은 이후 지출 배분에서 제외해 고정했다. 기존 실제 가족 API는 실제 KST 날짜와 부모 인증을 유지하며 공개 Space에서는 계속 비활성화한다.

## 보존 방식과 기능

- TrialLedger에 moneyon_books, moneyon_book_entries, moneyon_reward_choices, moneyon_payment_rules 4개 테이블만 추가한다. 기존 transaction 행과 ID는 수정·삭제하지 않는다.
- 기존 vault 거래를 기본 저축통장에 한번 연결한다. 기존 goals 행도 보존하며 첫 목표 금액을 기본 통장 목표로 사용한다. 이 과정을 반복해도 배분 기록이 중복되지 않는다.
- 새 통장은 고유 ID, 이름, 목표, 아이콘, 색, 별명을 갖고 0원에서 시작한다. 목표는 100~10,000,000원, 100원 단위다. 최대 20개다. 기존 저축이 새 통장에 옮겨지지 않는다.
- 통장별 저축·출금·목표 달성률·내역·예상/지급 저축 이자를 제공한다. 전체 vault 은행 계좌와 복식부기 원장은 그대로 사용하고 통장별 배분 합이 반드시 vault와 일치해야 한다.
- 저축 이자는 전체 금액을 한번 계산한 뒤 원금 비율로 배분한다. 원 단위 나머지는 최대 나머지/ID 순서로 배분한다. 지급 이자는 현재 통장 잔액이 아니라 마감 시점 원금 배분으로 나누므로 승인 전에 출금해도 확정 이자가 바뀌지 않는다.
- 새 체험은 자동 지급이다. 정책 행이 없는 기존 체험은 manual이다. 체험 전용 부모 동의로 변경한 설정은 다음 주 시작부터 적용한다. 여러 주 이동은 경계마다 마감·자동 지급을 순서대로 처리한다. 잔액 부족인 보상은 지급하지 않고 대기로 남긴다. 두 보상 유형은 각각 한번 지급한다.
- 실제로 지급된 allowance_bonus만 받은 이자 저축 선택에 사용한다. all은 1,425원 같은 정확한 전액, partial은 100원 단위, keep은 0원이다. 지급 건별 선택은 한번 확정한다. 이자 지급과 저축은 별도 원장 거래이고 payout→choice→deposit ID로 추적한다.
- 이미 쓴 이자를 다시 저축 대상으로 제시하지 않도록 지급 뒤 wallet 출금을 먼저 이자를 사용한 것으로 보수적으로 처리한다. 나중에 용돈을 받아도 소진된 지급 건의 자격이 회복되지 않는다. 실패한 이체는 choice·배분·은행 postings까지 같은 트랜잭션에서 롤백한다.
- 기존 블루 스타일, 이자니 PNG, 홈 구조와 하단 3개 메뉴는 유지한다. 필요한 통장 개설/이자 저축 화면만 추가했다.

## 변경 파일

배포한 고유 변경 파일 15개 (기능 13개, 안내 보완 시 경로 2개 추가):

1. api/moneyon_trial.py
2. deploy/moneyon/README.md → Space README.md
3. services/moneyon.py
4. services/moneyon_trial.py
5. services/moneyon_savings.py (추가)
6. web/src/app/moneyon/WeeklyJourney.tsx
7. web/src/app/moneyon/ChildExperience.tsx
8. web/src/app/moneyon/TrialExperience.tsx
9. web/src/app/moneyon/SavingsBooks.tsx (추가)
10. web/src/app/moneyon/RewardSaving.tsx (추가)
11. web/src/app/moneyon/types.ts
12. web/src/app/moneyon/blue.css
13. manifest.json (패키지에서 생성)
14. deploy/moneyon/page.tsx → Space web/src/app/page.tsx
15. deploy/moneyon/page.tsx → Space web/src/app/moneyon/page.tsx

로컬 지원 변경: scripts/prepare_moneyon_space.py, tests/test_moneyon.py, tests/test_moneyon_trial.py, tests/test_moneyon_weekly_education.py, tests/test_moneyon_web_package.py. 신규 tests/test_moneyon_phase72.py, tests/test_moneyon_phase72_summary.py, tests/test_moneyon_phase72_browser.cjs.

## 로컬 검증

- `python -m unittest discover -s tests -p 'test_moneyon*.py' -q`: 150개 통과.
- `node tests/test_moneyon_child_ui.cjs`: 30개 통과.
- 별도 MONEY 패키지 Next.js production export/typecheck: 통과.
- `node tests/test_moneyon_phase72_browser.cjs`: Chrome/Edge, 375·390·430·768·1440px, 36개 검사 통과. API mock 없음, 분리된 임시 DB 사용.
- 검증 내용: 원장 보존 마이그레이션, 신규/기존 지급 정책, 다음 주 정책 적용, 여러 주 마감, 부족한 부모 잔액, 대기 중 거래, 통장별 입출금과 이자 배분, 1,425원 전액/1,000원 일부/그대로 두기, 중복 요청, 실패 롤백, 새로고침, 초기화, 방문자 격리.
- 증거: reports/moneyon-phase72-browser/result.json 및 같은 폴더 PNG. 새 DB는 reports 아래에만 생성했다. 기존 사용자 preview DB는 변경하지 않았다.

## 배포

대상: MINSEO2/moneyon-demo만 변경. 공개 주소: https://minseo2-moneyon-demo.hf.space/

기능 커밋: 35a1d257f90387fc13d73442108a7f15c178c8bc

최종 커밋: 0c436ff33ef7bc37ac8dd80d57068ce10414b6e2 (시작/저축 화면의 지급 안내 문구 보완)

복구 기준: c83910699ba7ca484a3c450e93a27ead5e0797d9. 이전 정상 소스 45개를 reports/moneyon-phase72-rollback/source에 보관했다. 해당 버전의 캐시 수정 space_app.py는 이번 배포에서도 보존했다. 업로드 소스 47개 + manifest 중 변경된 13개만 웹 인증으로 업로드했다. 이후 안내 문구 4개 경로를 추가 커밋했다. 최종 공개 커밋에서 소스 47개 해시를 다시 읽어 로컬 최종 패키지와 일치함을 확인했다.

DB·세션·환경변수 파일·비밀키는 업로드하지 않았다. AI LAB 포털과 다른 에이전트는 수정하거나 배포하지 않았다. 공개 Space는 체험 전용이며 서버 재생성/재배포 시 일시적인 체험 DB가 사라질 수 있는 기존 정책은 유지한다.

## 최종 공개 검증 결과

- 최종 커밋 0c436ff33ef7bc37ac8dd80d57068ce10414b6e2: Docker 빌드 성공, Running 확인.
- 공개 URL에서 Phase 7.2 Chrome/Edge 검사 37개 통과. 다섯 화면 크기, PIN 없는 진입, 이자니 이미지, 용돈/소비/저축, 자동 지급, 100원 단위 이자 알아보기 조절, 원 단위 정확한 계산, 1,425원 전액을 신규 통장에 저축, 1,000원 일부 저축, 중복 선택 차단, 새로고침, 방문자 격리 및 초기화를 확인했다. 브라우저 JS 오류 없음.
- 별도 공개 부모 승인 시나리오 7개 통과. 다음 주부터 매주 승인으로 전환, 첫 주 자동 지급 유지, 다음 주 승인 대기 중 1,000원 소비, 확정 이자 3,135원 불변, 부모 계좌에서 3,135원+306원 차감, 지급 후 wallet 33,485원/vault 15,606원, 중복 승인 409 확인.
- 증거: reports/moneyon-phase72-live/result.json, manual-result.json, PNG 파일. 전체 소스 무결성은 reports/moneyon-phase72-source-verification.json에 기록했다.
- 모바일 공개 캡처: exact-14250-375.png, exact-all-saved-375.png, books-375.png, manual-approval-375.png. 홈/통장 화면은 390·430·768·1440px 캡처도 보관했다.

미해결 금융 오류는 발견되지 않았다. 공개 환경은 체험 전용이며 실제 가족 데이터/은행 연결은 제공하지 않는다. 기존 이용자 보존 마이그레이션은 분리된 테스트 DB에서 검증했으며 운영 가족 DB를 열거나 변경하지 않았다. 일시적 Space 디스크의 재생성 시 체험이 종료될 수 있는 제약은 그대로다.
