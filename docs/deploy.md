# 디지털전략부 AI LAB 배포 (Hugging Face Spaces)

한 개의 Docker 컨테이너에서 FastAPI가 **API와 화면(Next.js 정적 빌드)을 같은 주소로** 제공합니다.
GitHub `main`에 push하면 GitHub Actions(`deploy-space.yml`)가 Space로 올리고, Space가 Dockerfile로 빌드합니다.

- 무료(CPU basic: 2 vCPU · 16GB RAM). 배경 제거(rembg u2net)에 약 850MB가 필요해 512MB급 무료 서버로는 부족합니다.
- 48시간 동안 방문이 없으면 잠들고, 다음 방문 때 1~2분 걸려 깨어납니다.
- 컨테이너 디스크는 재시작 때 초기화됩니다. 관리자 설정(공개 범위·구성원)은 **Supabase `app_settings` 테이블**에 저장되므로 유지됩니다.

## 처음 한 번 (직접 해 주세요)

1. **Hugging Face 가입** — https://huggingface.co/join
2. **쓰기 토큰 만들기** — Settings → Access Tokens → *Create new token* → Type: **Write** → 복사
3. **GitHub에 등록** — 저장소 → Settings → Secrets and variables → Actions
   - *Secrets* 탭: `HF_TOKEN` = 2번 토큰
   - *Variables* 탭: `HF_SPACE` = `허깅페이스아이디/digital-ai-lab` (원하는 이름)
4. **배포 실행** — Actions → *Deploy to Hugging Face Space* → *Run workflow*
   (Space가 없으면 자동으로 만듭니다. 이후에는 push할 때마다 자동 배포)
5. **Space 비밀값 등록** — `https://huggingface.co/spaces/<HF_SPACE>` → Settings → *Variables and secrets* → **New secret**

   | 이름 | 값 | 비고 |
   |---|---|---|
   | `ADMIN_PASSWORD` | 관리자 비밀번호 | `/admin` 로그인 |
   | `SUPABASE_URL` | GitHub Secrets와 같은 값 | 관리자 설정·부동산 저장 |
   | `SUPABASE_SERVICE_ROLE_KEY` | GitHub Secrets와 같은 값 | |
   | `ANTHROPIC_API_KEY` | | AI 에이전트·보고서 |
   | `OPENAI_API_KEY` | | GPT·사주 |
   | `TAVILY_API_KEY` | | 웹검색·골프 후기 |
   | `DART_API_KEY`, `LAW_OC` | | 공시·법령 |
   | `PUBLIC_DATA_API_KEY` | | 부동산 |
   | `NAVER_API_KEY`, `VWORLD_API_KEY`, `DATA_GO_KR_SERVICE_KEY` 등 | `.streamlit/secrets.toml`과 같은 값 | 쓰는 기능만 |

   비밀값을 저장하면 Space가 자동으로 다시 시작됩니다.
6. **사이트 주소** — `https://<아이디>-<space이름>.hf.space` (Space 화면 오른쪽 위 ⋮ → *Embed this Space*에서도 확인)
7. **Streamlit 자동 이동 연결** — share.streamlit.io → 앱 → Settings → Secrets에
   `NEW_SITE_URL = "https://<아이디>-<space이름>.hf.space"` 추가 → 기존 Streamlit 주소로 들어오면 새 사이트로 이동

## 확인

- `https://<사이트 주소>/api/health` → `{"ok": true, "providers": {...}}` (true면 키 인식)
- 빌드 실패 시: Space 화면 → *Logs* → *Build*

## 선택

- `ACCESS_SECRET`: 토큰 서명 키를 직접 지정 (없으면 Supabase에 자동 생성·보관)
- `REMBG_MODEL`: 배경 제거 모델 (`u2net` 기본 · `silueta` · `u2netp`는 가볍지만 품질 낮음)
