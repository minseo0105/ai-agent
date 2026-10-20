# 이자니 — 첨부된 Canva 3D 꿀벌 적용

로컬 구현·검증 완료. Hugging Face 배포 및 AI LAB 포털 변경 없음.

## 이미지 처리 및 적용

사용자가 제공한 1,264×1,264 JPEG를 원본 그대로 보존했다. Canva의 배경 제거 기능만 사용했으며 재생성·표정 변경·포즈 변형을 하지 않았다. 앱은 Canva에서 제공하는 투명 PNG 200×200을 사용한다. 알파 채널 범위는 0~255, 캐릭터 영역은 (34,21)~(161,176)으로 더듬이·날개·손·동전·발 주위 여백이 남아 있다. 현재 74~180px 표시 용도이며, 대형 인쇄·확대용 원본 해상도 출력물은 아니다.

- 첨부 원본: `web/public/moneyon/characters/izani-bee-original.jpg`.
- 실제 앱: `web/public/moneyon/characters/izani-bee.png`.
- Canva 배경 제거 결과: https://www.canva.com/M/MAHYK5NiPxY

`Izani.tsx`는 모든 안내 상황에서 같은 이미지 URL과 비율을 사용한다. 상황별 안내 문구만 달라지며 이미지 자체의 표정·색상·모양은 바꾸지 않는다. 홈 상단, 이자 계산 안내, 용돈 받기, 저축 안내, 지급 완료 및 진입 화면에 적용된다. 블루/화이트 디자인, 금융 계산, 100원 단위 실험 및 다음 주 체험 UX는 유지했다. 표시 이름은 기존 공통 설정의 ‘이자니’를 사용한다.

## 복구 가능 자산

기존 우루미 `web/src/app/moneyon/Woorumi.tsx`는 그대로 보존했다. 직전 강아지 시안은 `web/src/app/moneyon/legacy/IzaniPuppy.tsx`와 `reports/moneyon-izani-bee/Izani.puppy.original.tsx`에 보관했다. 첨부 JPEG도 프로젝트에 보존했다. 사용하지 않는 원본 JPEG와 과거 시안은 MONEY 전용 소스 업로드 허용 목록에 넣지 않았다.

## 정적 파일 경계

전용 Space 앱이 원래 `_next` 외의 정적 파일을 차단해 PNG가 404가 되는 문제를 수정했다. `deploy/moneyon/space_app.py`에 `moneyon/characters/izani-bee.png` **정확히 한 경로**만 추가 허용했다. 다른 파일·가족/관리자 API·실제 은행 API의 접근 범위는 확대하지 않았다. 금융 원장과 계산 API, 날짜 엔진 및 포털 주요 파일은 이전 SHA-256과 일치한다.

## 검증 및 캡처

- 프로덕션 빌드·TypeScript 통과.
- 어린이 UI 30개: 같은 PNG를 모든 안내 상황과 두 브랜드 설정에서 사용하는지 검증.
- Chrome/Edge 실제 브라우저 38항목 통과. 금융 거래·10% 계산·부모 승인·중복 차단·저축·초기화·세션 격리 및 PNG 로드/금액 비겹침 확인.
- 375·390·430px 모바일 검증 및 캡처 완료. 768·1440px도 확인.
- 전용 정적 파일 경계 16개 테스트 통과. PNG 응답의 바이트 일치 및 다른 이미지 파일은 404 확인.
- 기존 금융 회귀는 전체 Python 테스트로 확인. 실제 휴대전화 검증은 하지 않았고 Chrome 반응형 화면을 사용했다.

홈 캡처:
`reports/moneyon-izani-bee/home-viewport-375.png`, `home-viewport-390.png`, `home-viewport-430.png`.

다른 화면:
`design-mom-bank-390.png`, `design-interest-calculation-390.png`, `design-piggy-bank-390.png`, `design-interest-payment-390.png`.

브라우저 결과: `reports/moneyon-izani-bee/browser-result.json`.

## 변경 파일 목록

1. `web/public/moneyon/characters/izani-bee-original.jpg` — 첨부 원본 보존.
2. `web/public/moneyon/characters/izani-bee.png` — 실제 투명 이미지.
3. `web/src/app/moneyon/Izani.tsx` — 공통 이미지 컴포넌트.
4. `web/src/app/moneyon/legacy/IzaniPuppy.tsx` — 이전 시안 보존.
5. `web/src/app/moneyon/blue.css` — 이미지 contain/비율/홈 상단 크기.
6. `deploy/moneyon/space_app.py` — 캐릭터 PNG 정확한 경로만 허용.
7. `scripts/prepare_moneyon_space.py` — PNG를 소스 패키지에 포함.
8. `scripts/preview_moneyon_izani.cjs` — 단일 꿀벌 미리보기 생성.
9. `tests/test_moneyon_child_ui.cjs`, `tests/test_moneyon_blue_browser.cjs`, `tests/test_moneyon_space.py`, `tests/test_moneyon_web_package.py` — 이미지 및 경계 회귀 검사.
10. 이 보고서.

최종 후보: `reports/moneyon-bee-release/`. 허용 소스 44개 + manifest 1개. 로컬 검토용 정적 결과는 `web/out`에 별도 포함한다. 로컬 미리보기는 http://127.0.0.1:8118/ 이며 기존 체험 DB를 유지했다. 새로고침하면 새 꿀벌이 보인다. 승인 전까지 Hugging Face에 업로드하지 않는다.
