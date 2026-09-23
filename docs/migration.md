# Streamlit → FastAPI + Next.js 이전 가이드

## 구조

```
web/        Next.js 프론트엔드 (화면)          → 배포: Vercel
api/        FastAPI 백엔드 (HTTP 엔드포인트)    → 배포: Render / Railway / Fly.io
services/   실제 기능 로직 (Streamlit 무관)     ← api/와 app.py가 함께 사용
pages/, app.py   기존 Streamlit 앱 (이전 완료 시 제거)
_archive/   정리한 옛 스크립트·중간 산출물 (git 제외, 확인 후 삭제 가능)
```

## 실행

1. Node.js LTS 설치: https://nodejs.org
2. `run_dev.bat` 더블클릭 → API(8000), Streamlit(8501), 웹(3000)이 함께 뜹니다.
3. 브라우저에서 http://localhost:3000

API 키는 지금처럼 `.streamlit/secrets.toml`에서 읽습니다.
배포 환경에서는 같은 이름의 환경변수(`ANTHROPIC_API_KEY` 등)를 설정하면 됩니다 (`services/config.py`).

## 진행 상황

| 서비스 | 상태 |
|---|---|
| 홈 · AI 에이전트 | ✅ Next.js 완료 (`/api/chat`, SSE) |
| 골프장 추천 | ✅ Next.js 완료 (`/golf`, `/api/golf/*`) · Pool 관리(VWorld 갱신)는 Streamlit에 남음 |
| 내차에서 드림카까지 | ✅ `/dreamcar` (이미지는 FastAPI `/media/*` 정적 서빙) |
| 부동산 모니터 | ✅ Next.js 완료 (`/realestate`, `/api/realestate/*`) |
| 보고서 작성기 | ✅ Next.js 완료 (`/report`, `/api/report/*`) |
| AI 사주 · 대운 분석 | ✅ `/saju` (`/api/saju/*`, GPT 해석은 SSE 스트리밍) |
| 차량 선택기 · GIF 변환기 | ⏳ |

## 서비스 하나를 옮기는 순서

1. `pages/X.py` 안의 계산·데이터 로직을 `services/x.py`로 분리 (`st.*` 호출 없이)
2. `api/main.py`(또는 `api/routers/x.py`)에 엔드포인트 추가
3. `web/src/app/x/page.tsx`에 화면 구현
4. `web/src/lib/services.ts`에서 해당 항목의 `streamlitPath`를 `href: "/x"`로 교체
5. 확인 후 `pages/X.py` 삭제
