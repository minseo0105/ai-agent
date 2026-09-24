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
| 차량 선택기 | ✅ `/car-selector` (`/api/car-selector/*`, 이미지는 `/media/car-*` 정적 서빙) |
| GIF 변환기 | ✅ `/gif` (`/api/gif/preview`·`/generate`, multipart 업로드 · rembg 배경 제거) |

## 공개 범위 · 관리자 설정 (`/admin`)

- `ADMIN_PASSWORD`를 `.streamlit/secrets.toml`(또는 환경변수)에 넣으면 `/admin`에서 로그인할 수 있다.
- 사이트 공개 범위(모두 공개 · 등록된 사람만 · 점검 중), 서비스별 공개(사이트 설정 따름 · 모두 공개 · 등록된 사람만 · 숨김),
  공지 배너, 로그인 유지 기간, 구성원(개인 접속 코드 발급 · 사용 중지 · 재발급 · 삭제)을 관리한다.
- 화면뿐 아니라 FastAPI 미들웨어(`api/access.py`)가 서비스 API 자체를 막는다. 설정과 서명 키는 `data/admin/`(Git 제외)에 저장된다.
- 배포 시 여러 서버에서 같은 토큰을 쓰려면 `ACCESS_SECRET` 환경변수를 지정한다.

## Streamlit (기존 화면)

- 접속하면 새 사이트(`NEW_SITE_URL`, 기본 `http://localhost:3000`)로 자동 이동한다. 모든 사이드바에 이동 버튼이 있다.
- 골프 Pool 관리 등 기존 화면은 `http://localhost:8501/?stay=1` → 관리자 비밀번호 입력으로만 열 수 있다
  (기존 화면은 새 사이트의 공개 범위 설정을 따르지 않기 때문).

## 서비스 하나를 옮기는 순서

1. `pages/X.py` 안의 계산·데이터 로직을 `services/x.py`로 분리 (`st.*` 호출 없이)
2. `api/main.py`(또는 `api/routers/x.py`)에 엔드포인트 추가
3. `web/src/app/x/page.tsx`에 화면 구현
4. `web/src/lib/services.ts`에서 해당 항목의 `streamlitPath`를 `href: "/x"`로 교체
5. 확인 후 `pages/X.py` 삭제
