# MONEY Hugging Face 배포 결과

검증일: 2026-10-16 (한국 시간)

- 공개 앱: https://minseo2-moneyon-demo.hf.space/
- Space: https://huggingface.co/spaces/MINSEO2/moneyon-demo
- 소유자: 웹 로그인 계정 MINSEO2
- 구성: Public / Docker Blank / 무료 CPU Basic / 포트 7860
- 배포 커밋: 1a3f9d43b9156c8c7fa5b00def9d930103b06667
- 브라우저 로그인으로 생성·업로드 완료. CLI 로그인, 토큰 발급, GitHub 동기화 불필요.
- HF 화면에서 Building 이후 Running 확인. Docker 빌드와 서비스 시작 성공.

## 배포 내용

`reports/moneyon-web-upload/huggingface-upload`의 검토된 파일 40개를 원래 상대 경로로 업로드했다. HF가 생성한 `.gitattributes`는 유지했다. 전용 Dockerfile은 Next.js 정적 화면을 빌드하고 FastAPI에서 화면과 체험 API를 같은 출처로 제공한다. `MONEYON_TRIAL_ENABLED=1`은 Dockerfile에 설정되어 있으며 별도 비밀키가 필요 없다.

기존 AI LAB Space, 다른 에이전트, 기존 GitHub 저장소에는 변경을 수행하지 않았다. 운영 DB·개인정보·환경변수 파일·비밀키·실제 은행 연결은 업로드하지 않았다. 실제 사용자 및 부모 API는 전용 앱에 등록하지 않는다.

## 실제 배포 환경 검증

모킹 없이 공개 URL에 연결했다.

- `tests/test_moneyon_space_browser.cjs`: 15개 시나리오 통과, JavaScript 오류 없음.
- Chrome 및 별도 Edge 브라우저에서 독립 거래·초기화 확인.
- 375px, 768px, 1440px 화면에서 가로 넘침 없이 표시 확인 및 캡처.
- PIN 없이 바로 체험 진입, 통장 28,500원·저금통 15,000원·총액 43,500원·예상 보상 800원 확인.
- 용돈 1,000원 받기 → 통장 29,500원.
- 소비 2,000원 → 통장 27,500원.
- 저축 1,000원 → 통장 26,500원·저금통 16,000원.
- 새로고침 후 거래 상태 유지, 새 탭은 독립 체험 확인.
- 가상 날짜 2026-10-19로 이동 후 부모 승인 시뮬레이션 → 보상 800원 지급·통장 27,300원.
- 초기화 후 통장 28,500원 복원.
- 실제 사용자·관리자 API, 문서·DB 파일 경로는 404 응답.
- `scripts/check_moneyon_space.py --url https://minseo2-moneyon-demo.hf.space`: seed/isolation/allowance/reset/trial_only 모두 통과.

결과: `reports/moneyon-live/browser-result.json`
캡처: `reports/moneyon-live/space-home-375.png`, `space-home-768.png`, `space-home-1440.png`, `edge-isolated-375.png`

## 데이터 유지 정책과 한계

체험 접근 권한은 브라우저 탭의 sessionStorage에 저장한다. 새로고침은 유지하고 새로운 탭·브라우저는 독립 체험이다. 복제·복원 탭은 브라우저 동작에 따라 세션을 복사해 공유할 수 있다. 권한은 24시간 후 만료한다. 탭 종료·브라우저 재접속은 새 체험이 원칙이며 브라우저의 탭 복원 동작은 예외다.

무료 Space의 체험 SQLite는 임시 디스크에만 있다. Space 재시작·재빌드 등으로 상태가 소실될 수 있으며 영구 보관 서비스가 아니다. 모바일 검증은 실제 Chrome·Edge의 화면 크기 테스트이며 실물 휴대전화 테스트는 수행하지 않았다. 공개 배포 후 기존 로컬 전체 회귀 테스트를 다시 실행하지 않았으며, 이번에는 공개 환경 통합 테스트를 실행했다.
