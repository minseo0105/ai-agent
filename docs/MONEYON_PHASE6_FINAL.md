# MONEY Phase 6 최종 거래 검증 및 전용 Space 배포

## 최종 수정

체험 용돈 받기·소비·저금통 입출금의 입력 화면과 API에 100원 배수 제한을 적용했다. 333원, 5,050원 등은 거래 전에 차단한다. 자동 계산 보상은 205원처럼 1원 단위로 지급할 수 있다. 기존 가족 계정의 입력 정책은 변경하지 않았다.

거래 성공 시 우루미 안내에 통장, 저금통, 두 예상 보상의 이전 금액 → 이후 금액을 표시한다. 보상 승인 시 저금통의 전후 금액도 표시한다. 잔액 카드의 변화 애니메이션을 유지했다.

## 요청 시나리오

| 단계 | 통장 | 저금통 | 용돈 보너스 예상 | 저금통 이자 예상 |
|---|---:|---:|---:|---:|
| 초기 | 28,500 | 15,000 | 285 | 300 |
| 3,000원 소비 | 25,500 | 15,000 | 255 | 300 |
| 이어서 5,000원 저축 | 20,500 | 20,000 | 205 | 400 |

주간 마감 후 용돈 보너스 205원을 승인하면 저금통 20,205원, 저금통 이자 400원을 승인하면 20,605원이 된다. 통장은 20,500원으로 유지한다. 지급 후 새 주차의 예상 금액은 새 원금으로 다시 계산되며 위 표의 마감 주차 지급액과 구분한다. 중복 승인 요청은 409, 100원 단위가 아닌 API 거래는 422이며 원장 변경이 없다.

## 로컬 검증

- MONEY Python 117개 통과: `reports/moneyon-phase6/final-python.log`.
- 기존 어린이 UI 검사 28개 및 TypeScript 검사 통과.
- 독립 Space 정적 화면 프로덕션 빌드 성공(Windows 로컬 webpack).
- Chrome·Edge, 375/768/1440px, 실제 API 사용 브라우저 검사 21항목 통과: `reports/moneyon-phase6-final/browser-result.json`.
- 소비/저축의 전후 금액 안내, 새로고침, 새 탭 격리, 다른 브라우저 거래·초기화 격리, 두 승인, 중복 지급 차단, 입력 제한, 실패 시 원장 보존, 초기화 복원을 확인했다.

## 배포 범위와 AI LAB 테스트 실패 영향

배포 대상은 `MINSEO2/moneyon-demo` 하나이며 웹 로그인 인증으로 변경 파일 8개만 커밋했다. CLI 로그인이나 토큰 발급은 사용하지 않았다. 전용 Dockerfile과 `MONEYON_TRIAL_ENABLED=1` 설정을 유지했다.

검토한 체험 패키지에는 허용 목록의 소스 39개와 manifest만 있다. AI LAB의 `api/main.py`, Streamlit 앱 및 다른 에이전트 소스·의존성·운영 DB·비밀키는 포함하지 않는다. 실제 사용자 API는 등록하지 않으며 외부 경로와 DB 파일 요청은 차단한다.

이전 전체 AI LAB 테스트 실패(347개 중 실패 6·오류 24)는 해결되었다고 주장하지 않는다. MONEY는 통합 진입점을 로드하지 않는 독립 앱이며 해당 패키지의 빌드·실행 및 실제 거래 검증을 별도로 수행한다. 다른 에이전트의 실패를 고치기 위한 변경은 하지 않았다.

## 배포 증거

- Space: https://huggingface.co/spaces/MINSEO2/moneyon-demo
- 공개 앱: https://minseo2-moneyon-demo.hf.space/
- 배포 커밋: `d7d2b2769e98c675c2a4a2f1c06141734c99391b`
- 배포 소스 39개 SHA-256이 검토 패키지와 모두 일치: `reports/moneyon-phase6-final/remote-source-check.json`.
- Hugging Face Docker 빌드 성공. runtime SHA가 위 커밋과 일치하고 `RUNNING`, 공개 도메인 `READY`를 확인했다. Linux Docker 환경에서 기존 기본 Next 빌드도 성공했다.
- 공개 URL에 연결한 Chrome·Edge 최종 브라우저 검사 21항목 통과, JavaScript 오류 없음: `reports/moneyon-phase6-live-final/browser-result.json`.
- 공개 URL에서도 위 표와 같은 3,000원 소비 → 5,000원 저축 → 205원·400원 별도 승인 → 저금통 20,605원을 확인했다. 100원 단위 제한, 실패 시 원장 보존, 중복 지급 차단, 초기화, 새로고침, 브라우저별 데이터 격리가 통과했다.
- 375px·768px·1440px 화면 캡처 및 가로 넘침 검사 통과. 전후 금액 안내와 별도 금융 영역을 시각적으로 확인했다.
- 공개 API 추가 점검 `scripts/check_moneyon_space.py --url https://minseo2-moneyon-demo.hf.space` 통과: 체험 전용, 샘플 원장, 타 방문자의 자녀 접근 거부, 용돈 이체, 초기화 확인.
- 공개 캡처: `reports/moneyon-phase6-live-final/after-expense-375.png`, `after-savings-375.png`, `after-savings-768.png`, `after-savings-1440.png`, `after-both-approvals-375.png`.

## 데이터 유지 한계

탭 새로고침은 체험을 유지한다. 새 탭과 다른 브라우저는 독립 체험이다. 브라우저의 탭 복제·복원 기능은 sessionStorage를 복사할 수 있다. 무료 Space의 임시 디스크는 재빌드·재시작 후 유지가 보장되지 않는다. 모바일 검증은 실제 데스크톱 브라우저의 화면 크기 검사이며 실물 휴대전화 검증은 아니다.
