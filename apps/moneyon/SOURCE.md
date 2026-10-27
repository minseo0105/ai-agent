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
- 원본의 `.gitattributes`(HF LFS 규칙)는 넣지 않음. `README.md`(HF 메타데이터)와 `manifest.json`(실제 파일과 일부 다름)은 원본 그대로 보관.

배포·경로 규칙은 `docs/MULTI_APP_PLAN.md` 참고.
