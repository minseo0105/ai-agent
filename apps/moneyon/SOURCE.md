# MONEY:ON 체험 (오라클 `/moneyon`용 사본)

원본: Hugging Face Space `MINSEO2/moneyon-demo` 커밋 `1b40993634a938c3a72ef155fe7a7e3ffcda84cc`
(2026-10-20, "MONEY:ON 용돈기록장 중심 개편 (moneyon-wip 7733aca4)"). 2026-10-27 복사.
`origin/moneyon-wip` 브랜치·`reports/moneyon-*` 묶음과는 파일이 달라 Space 파일을 기준으로 삼았다.

이 폴더는 HF Space로 업로드하지 않는다. HF Space는 강의 시연용으로 그대로 둔다.
`apps/`는 AI LAB의 HF 자동 배포 경로·업로드 목록·이미지(.dockerignore)에 포함되지 않는다.

원본과 다른 점:
- `web/next.config.ts`: `NEXT_BASE_PATH`가 있을 때만 `basePath` 적용(없으면 원본과 동일).
- `Dockerfile.oracle` 추가: web 빌드 ENV만 `NEXT_BASE_PATH=/moneyon NEXT_PUBLIC_API_URL=/moneyon NEXT_PUBLIC_MONEYON_EPHEMERAL=0`.
  원본 `Dockerfile`은 그대로 둠.
- `web/src/app/moneyon/desktop.css` 추가(2026-10-27): PC(1024px 이상) 전용 배치. 본문 1120px, 하단 탭바 → 왼쪽 세로 메뉴,
  첫 화면·홈·기록·저축(통장 2개 이상)·엄마 화면을 두 칸으로. 모든 규칙이 `@media (min-width:1024px)` 안에 있어
  1023px 이하(휴대폰·태블릿)는 원본과 픽셀 단위로 같음. `page.tsx`, `moneyon/page.tsx`에 import 한 줄씩 추가.
- AI 기능 추가(2026-10-27, 오라클 전용, HF Space에는 올리지 않음): `services/moneyon_ai.py`, `api/moneyon_ai.py`(space_app에 라우터 등록),
  `web/src/app/moneyon/AiCard.tsx`·`AiCoach.tsx`·`ai.css`, 홈·저축·엄마 화면과 첫 화면 '시연 데이터로 시작' 연결, `requirements.txt`에 `anthropic`,
  `Dockerfile.oracle`에 `data/ai_prepared.json` 복사. `MONEYON_AI_ENABLED`가 없으면 화면·동작은 원본과 같음(픽셀 비교 0). 계획·결과는 `docs/MONEYON_AI_PLAN.md`.
- 원본의 `.gitattributes`(HF LFS 규칙)는 넣지 않음. `README.md`(HF 메타데이터)와 `manifest.json`(실제 파일과 일부 다름)은 원본 그대로 보관.

배포·경로 규칙은 `docs/MULTI_APP_PLAN.md` 참고.
