# 오라클 서버 여러 앱 계획: MONEY:ON을 `/moneyon`으로

작성 2026-10-27. **적용 완료(2026-10-27) — 결과는 7절.** 1~6절은 적용 전 조사·계획 기록.
대상 주소: `https://140-245-88-198.sslip.io/moneyon` (AI LAB과 같은 서버·같은 Caddy).

결정(6절): 원본은 HF Space 커밋 `1b409936`, 체험 기록은 볼륨에 보존, AI LAB 홈 카드 링크는 당분간 HF 유지.

## 0. 결론 요약

- MONEY:ON 체험 Space는 **AI LAB과 별개의 독립 앱**이다(자체 Next.js 화면 + 자체 FastAPI `space_app.py` + 자체 SQLite). AI LAB `web/` 안의 페이지가 아니다.
- 데이터는 **서버 컨테이너 안 SQLite(휘발성)** + **브라우저 sessionStorage의 체험 토큰**뿐. Supabase·비밀키·외부 API 없음.
- `/moneyon`에서 돌리려면 앱 코드는 거의 그대로 두고 **빌드 설정 2가지(`basePath`, `NEXT_PUBLIC_API_URL`)** 와 **Caddy 경로 라우팅**, **compose 서비스 1개**만 추가하면 된다.
- 소스는 `oracle-migration` 브랜치의 새 폴더 `apps/moneyon/`에 둔다. 이 경로는 HF AI LAB 자동 배포·업로드·이미지 어디에도 포함되지 않고, HF MONEY:ON Space에는 아무것도 올리지 않는다.

## 1. HF Space `MINSEO2/moneyon-demo`는 어떻게 빌드되나

확인 방법: HF 공개 API로 메타데이터·파일 목록 조회, 파일 51개를 읽기 전용으로 내려받아 확인(Space 커밋 `1b409936`, 마지막 수정 2026-10-20 06:20 UTC, 상태 RUNNING, SDK `docker`, `app_port: 7860`).

| 구성 | 내용 |
|---|---|
| `Dockerfile` | 2단계. ① `node:22-slim`에서 `web/`을 `npm ci` → `STATIC_EXPORT=1 NEXT_PUBLIC_API_URL="" NEXT_PUBLIC_MONEYON_EPHEMERAL=1 npm run build` (Next.js 16 정적 export → `web/out`) ② `python:3.12-slim`에 `fastapi`·`uvicorn`만 설치, `api/`·`services/`·`space_app.py`·`web/out` 복사, `uvicorn space_app:app --port 7860 --workers 1` |
| 환경변수(이미지 내장) | `MONEYON_TRIAL_ENABLED=1`, `MONEYON_TRIAL_DB=/home/user/app/runtime/trial.sqlite3`, `MONEYON_TRIAL_POOL=120`, `MONEYON_TRIAL_KEEP=3000` 등. **비밀값 없음** |
| `space_app.py` | 체험 라우터(`/api/moneyon/trial/*`)와 `/api/health`만 등록. 그 외 `/api/*`는 404. 화면은 `/`(index.html), `/moneyon`(moneyon.html), `/moneyon/characters/izani-bee.png`, `/_next/*`만 제공하고 나머지 경로는 404. POST/PATCH는 `Origin` 호스트가 `Host`와 같아야 함(교차 사이트 차단), 분당 요청 제한(시작 300, 쓰기 600, 체험별 300), 유휴 시 체험 풀 채우기·만료 정리 스레드 |
| `web/` | Next.js 16 + React 19 + Tailwind 4. 페이지 `app/page.tsx`(=`app/moneyon/page.tsx`와 같은 내용)와 `app/moneyon/*` 컴포넌트. `basePath` 없음 |
| `api/`, `services/` | `moneyon_trial.py`(라우터), `moneyon*.py`(장부·저축·이자 규칙). `access.py`·`config.py`·`supabase_auth.py`도 들어 있지만 `space_app.py`는 체험 라우터만 쓴다 |

소스 위치 주의:
- **`main`/`oracle-migration`에는 MONEY:ON 코드가 없다.** 원본 개발 브랜치는 `origin/moneyon-wip`(마지막 2026-10-20, `scripts/prepare_moneyon_space.py`·`deploy/moneyon/` 포함, main과 36/12커밋 갈라짐).
- 그런데 **현재 Space와 `moneyon-wip`은 일치하지 않는다**(SHA-256 비교: `Dockerfile`·`moneyon_banking.py`·`page.tsx`·`layout.tsx`는 같음, `space_app.py`·`api/moneyon_trial.py`·`services/moneyon_trial.py`·`TrialExperience.tsx`·`TrialHome.tsx`·`next.config.ts`는 다름). 로컬 `reports/moneyon-*` 묶음 중에도 완전히 같은 것은 없음(가장 가까운 `moneyon-v10-rollback`도 4개 중 2개만 일치).
- Space의 `manifest.json`도 실제 파일과 다름(`TrialActions.tsx`, `TrialHome.tsx`가 목록에 없음).
- → **강의 시연 중인 동작과 똑같이 맞추려면 HF Space 저장소의 현재 파일(커밋 `1b409936`)을 원본으로 삼는다.**

## 2. AI LAB과의 관계

- **별개의 앱.** AI LAB(`api/main.py` + `web/`)과 프로세스·화면 빌드·DB가 모두 따로다.
- AI LAB 쪽 연결은 홈 카드 링크 하나뿐: `web/src/lib/services.ts:106` `href: "https://minseo2-moneyon-demo.hf.space/"`. AI LAB에는 `/moneyon` 페이지나 `/api/moneyon` 라우트가 없음 → Caddy에서 `/moneyon`을 머니온으로 보내도 AI LAB 경로와 겹치지 않음.
- 참고: `/dreamcar`는 **이미 AI LAB 안의 페이지**(`web/src/app/dreamcar`)라 별도 앱으로 라우팅하면 안 됨. 드림카는 지금도 `https://140-245-88-198.sslip.io/dreamcar`로 열린다.

## 3. 데이터 저장

| 저장소 | 내용 | 수명 |
|---|---|---|
| 서버 SQLite `runtime/trial.sqlite3` (컨테이너 내부 디스크) | 방문자별 체험 장부(가상 돈) | 컨테이너가 **다시 만들어지면(재빌드·recreate) 사라짐**. 단순 재시작·재부팅은 유지. HF에서도 같은 성격(README: "Space 재시작·재빌드로 서버 디스크가 사라지면 체험 종료") |
| 브라우저 `sessionStorage["moneyon-trial-v1"]` | 체험 토큰 | 탭 단위, 서버 쪽 24시간 유효 |
| 브라우저 `localStorage["ailab-access-token"]` | **읽기만 함** — `web/src/lib/access.ts`의 `apiFetch`가 있으면 `Authorization: Bearer`로 붙여 보냄. 지우거나 바꾸지 않음 | — |
| Supabase / 외부 API / 비밀키 | **없음** | — |

같은 주소(origin)로 합칠 때의 주의: 오라클에서는 AI LAB과 MONEY:ON이 같은 origin이라 **AI LAB 로그인 토큰이 머니온 요청에 `Authorization` 헤더로 실려 감**(머니온 서버는 쓰지 않음). Caddy에서 `/moneyon` 요청의 `Authorization` 헤더를 지워 차단한다(4-3). sessionStorage 키는 서로 달라 충돌 없음.

## 4. `/moneyon`에서 동작시키려면

### 4-1. 경로가 어떻게 바뀌나

Caddy가 `/moneyon/...`의 접두사를 떼고(`handle_path`) 머니온 컨테이너로 넘기면, 컨테이너 안 `space_app.py`는 지금처럼 루트 기준 경로를 그대로 받는다 → **`space_app.py`는 수정 불필요.**

| 브라우저 요청 | Caddy가 넘기는 경로 | 처리 | 필요한 것 |
|---|---|---|---|
| `/moneyon` | → `/moneyon/`로 308 | | Caddy `redir` |
| `/moneyon/` | `/` | `index.html` | — |
| `/moneyon/_next/static/...` | `/_next/static/...` | 정적 파일 | **Next `basePath: "/moneyon"`** (없으면 `/_next/...`로 요청돼 AI LAB 파일과 충돌) |
| `/moneyon/api/moneyon/trial/...` | `/api/moneyon/trial/...` | 체험 API | **빌드 시 `NEXT_PUBLIC_API_URL=/moneyon`** (코드가 `${API_URL}/api/moneyon/trial...`로 만듦) |
| `/moneyon/characters/izani-bee.png` | (접두사 유지) `/moneyon/characters/izani-bee.png` | 이미지 | `Izani.tsx`가 `<img src="/moneyon/characters/izani-bee.png">`로 고정 → 이 경로만 **접두사를 떼지 않고** 넘기면 `space_app.py`가 이미 허용하는 경로와 일치. 코드 수정 불필요 |
| 헤더의 `<a href="/">` (AI LAB으로 가기) | — | 오라클에선 AI LAB 홈으로 감 | 의도에 맞음(HF에선 Space 첫 화면) |

POST 출처 검사: Caddy는 `Host`를 그대로 넘기고 `Origin`도 `https://140-245-88-198.sslip.io`(경로 없음)라 통과. 요청 제한: 모든 방문자가 Caddy 한 주소로 보이므로 HF 공용 프록시와 같은 조건(분당 시작 300·쓰기 600 합산) — 강의 규모에서는 충분, 필요하면 나중에 조정.

### 4-2. 빌드 설정 변경 (오라클용 사본에서만)

`apps/moneyon/`에 HF Space 파일을 그대로 복사한 뒤, 아래만 바꾼다. **HF Space 파일 자체는 수정하지 않는다.**

1. `apps/moneyon/web/next.config.ts` — 환경변수가 있을 때만 basePath 적용(없으면 지금과 동일):
   ```ts
   const basePath = process.env.NEXT_BASE_PATH || undefined;
   const nextConfig: NextConfig = {
     ...(basePath ? { basePath } : {}),
     // 기존 설정 그대로
   };
   ```
2. `apps/moneyon/Dockerfile.oracle` — 원본 `Dockerfile`은 Space와 똑같이 두고, 오라클용을 따로 만든다. 차이는 web 빌드 단계 ENV 한 줄:
   ```dockerfile
   ENV STATIC_EXPORT=1 NEXT_BASE_PATH=/moneyon NEXT_PUBLIC_API_URL=/moneyon \
       NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_MONEYON_EPHEMERAL=0
   ```
   (`NEXT_PUBLIC_MONEYON_EPHEMERAL=1`이면 화면에 "Hugging Face Space 서버가…" 문구가 나오므로 오라클에선 0. 체험 기록 보존 범위는 아래 볼륨 선택에 따름)
3. `apps/moneyon/SOURCE.md` — 원본이 HF Space 커밋 `1b409936`이라는 것과 바꾼 파일 목록 기록.

### 4-3. Caddyfile에 추가

```caddyfile
{$SITE_ADDRESS::80} {
	encode zstd gzip

	# MONEY:ON 체험 (별도 컨테이너)
	redir /moneyon /moneyon/ 308
	handle /moneyon/characters/* {
		request_header -Authorization
		reverse_proxy moneyon:7860
	}
	handle_path /moneyon/* {
		# 같은 origin의 AI LAB 로그인 토큰이 머니온으로 넘어가지 않게 한다
		request_header -Authorization
		reverse_proxy moneyon:7860
	}

	# 나머지는 AI LAB
	handle {
		reverse_proxy ailab:7860 {
			flush_interval -1
		}
	}
}
```

### 4-4. docker-compose.yml에 추가

```yaml
  moneyon:
    build:
      context: ./apps/moneyon
      dockerfile: Dockerfile.oracle
    image: moneyon:latest
    container_name: moneyon
    restart: always
    expose:
      - "7860"
    networks:
      web:
        ipv4_address: 172.28.0.11
    # 선택: 체험 기록을 재빌드 후에도 남기려면 (HF처럼 휘발성으로 두려면 이 두 줄을 빼면 됨)
    volumes:
      - moneyon-runtime:/home/user/app/runtime
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```
- `caddy.depends_on`에 `moneyon` 추가, `volumes:`에 `moneyon-runtime:` 추가(볼륨을 쓸 경우).
- `env_file` 없음(비밀값 불필요). healthcheck는 원본 Dockerfile의 `HEALTHCHECK`(`/api/health`)를 그대로 씀.
- 메모리: FastAPI 단일 프로세스라 수십 MB 수준. 빌드 시 Next 빌드가 한 번 더 돈다(ARM에서 AI LAB 빌드보다 짧을 것으로 예상).

## 5. 작업 방식 — HF의 AI LAB·MONEY:ON Space에 영향 없게

| 확인 항목 | 근거 | 영향 |
|---|---|---|
| HF AI LAB 자동 배포 트리거 | `.github/workflows/deploy-space.yml`은 `main` push + 경로 `api/** services/** web/** data/golf/** Dockerfile requirements-api.txt deploy/** ...`일 때만 | `oracle-migration` push는 무관. 나중에 `main` 병합해도 `apps/**`, `Caddyfile`, `docker-compose.yml`은 트리거 경로가 아님 → **배포 안 됨** |
| HF AI LAB 업로드 범위 | `scripts/deploy_space.py`의 `ALLOW` = `api/** services/** web/** data/golf/** ...` | `apps/moneyon/`은 업로드되지 않음 |
| AI LAB 이미지 | `.dockerignore`가 허용 목록 방식(`api/ services/ web/ data/ ...`만) | `apps/`는 AI LAB 이미지에 안 들어감 |
| HF MONEY:ON Space | 이 계획은 Space에 push·업로드하지 않음. `moneyon-wip`의 Space 배포 워크플로(`deploy-moneyon.yml`, `moneyon-space-check.yml`)는 복사하지 않음 | **변화 없음** |
| AI LAB 홈 카드 링크 | `web/src/lib/services.ts`는 `web/**` → main 병합 시 HF AI LAB 배포 트리거 | **이번에는 바꾸지 않음**(HF 링크 유지). 나중에 바꾸려면 빌드 환경변수로 오라클에서만 `/moneyon`을 가리키게 하는 별도 작업 |

진행 순서(승인 후):
1. `oracle-migration`에서 `apps/moneyon/` 추가(HF Space 커밋 `1b409936` 파일 그대로) → 4-2 변경 → 커밋. `README.md`의 HF 메타데이터와 `manifest.json`은 참고용으로 두거나 제외.
2. `docker-compose.yml`·`Caddyfile` 변경(4-3, 4-4) → 커밋 → push.
3. 서버: `git pull` → `docker compose build moneyon` → `docker compose up -d moneyon` (AI LAB 컨테이너는 그대로).
4. Caddy 반영: `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`(무중단). 실패하면 이전 설정이 유지됨.
5. 확인: `/moneyon` 308→200, `/moneyon/_next/...` 200, 꿀벌 이미지 200, 체험 시작 POST 200, 헤드리스 Chrome으로 화면·콘솔 오류 확인. **AI LAB `/`, `/api/ready`, `/realestate` 지도, `/_next/` 정적 파일이 그대로인지도 같이 확인.**
6. `docs/MIGRATION_ORACLE.md`에 결과 기록 → 커밋·push.

되돌리기: Caddyfile에서 머니온 블록 제거 후 `caddy reload` → `docker compose stop moneyon`. AI LAB 컨테이너는 이 작업 내내 재시작하지 않는다.

## 6. 결정이 필요한 것

1. **원본 기준**: HF Space 현재 파일(`1b409936`, 권장 — 시연 버전과 동일) vs `origin/moneyon-wip` 브랜치(개발 원본이지만 Space와 다름).
2. **체험 기록 보존**: 휘발성(HF와 동일, 재빌드 시 초기화) vs 볼륨(`moneyon-runtime`, 재빌드 후에도 유지 — 24시간 만료·`KEEP=3000` 정리는 그대로).
3. **AI LAB 홈 카드 링크**: 당분간 HF 머니온 유지(권장) vs 오라클 `/moneyon`으로 변경(별도 작업, main 병합 시 HF AI LAB 배포 발생).

→ 결정: 1 HF Space `1b409936`, 2 볼륨 보존, 3 HF 유지.

## 7. 적용 결과 (2026-10-27)

### 7-1. 바꾼 것 (커밋 `d2619034`, `oracle-migration`)

| 파일 | 내용 |
|---|---|
| `apps/moneyon/` | HF Space `1b409936` 파일 50개를 바이트 그대로 복사(`git clone`으로 커밋 확인, 개별 다운로드본과 비교해 동일). `.gitattributes`(HF LFS 규칙)만 제외 |
| `apps/moneyon/web/next.config.ts` | `NEXT_BASE_PATH`가 있을 때만 `basePath` |
| `apps/moneyon/Dockerfile.oracle` | 원본 `Dockerfile`과 web 빌드 ENV 한 줄만 다름(`NEXT_BASE_PATH=/moneyon NEXT_PUBLIC_API_URL=/moneyon NEXT_PUBLIC_MONEYON_EPHEMERAL=0`) |
| `apps/moneyon/SOURCE.md` | 원본 출처·변경점 |
| `docker-compose.yml` | `moneyon` 서비스(172.28.0.11, `moneyon-runtime` 볼륨), `caddy.depends_on`에 moneyon 추가 |
| `Caddyfile` | 4-3 그대로(redir → `/moneyon/characters/*` 접두사 유지 → `/moneyon/*` 접두사 제거 → 나머지 AI LAB, 머니온 두 경로 모두 `Authorization` 제거) |

HF 영향 점검: 바뀐 파일 중 HF AI LAB 배포 트리거 경로(`api/ services/ web/ data/golf/ Dockerfile requirements-api.txt deploy/ scripts/deploy_space.py .github/`)에 해당하는 것 **없음**. HF MONEY:ON Space에는 아무것도 올리지 않음. AI LAB 홈 카드 링크(`web/src/lib/services.ts`)는 그대로.

### 7-2. 서버 적용 순서와 결과

1. `git pull` (커밋 `d261903`).
2. `caddy adapt`를 **일회용 caddy 컨테이너**로 실행해 규칙 순서 확인: `/moneyon` 308 → `/moneyon/characters/*`(Authorization 삭제, 접두사 유지) → `/moneyon/*`(`strip_path_prefix /moneyon`, Authorization 삭제) → 나머지 `ailab:7860`.
3. `docker compose build moneyon` — ARM 빌드 성공, 이미지 236MB. 빌드 결과 `index.html`의 정적 파일 참조 29개 모두 `/moneyon/_next/...`(접두사 없는 `/_next/` 0개), JS에 `/moneyon` API 접두사 포함.
4. `docker compose up -d --no-deps moneyon` — 6초 뒤 healthy. **`--no-deps` 필수**(compose에서 caddy 설정이 바뀌어 없으면 caddy가 재생성됨).
5. Caddy 반영: `docker exec -i ailab-caddy caddy reload --config /dev/stdin --adapter caddyfile < Caddyfile` — 무중단, 실행 중 설정에 머니온 규칙·`strip_path_prefix`·`Authorization` 삭제 2곳 확인.
6. AI LAB(`ailab`)·Caddy 컨테이너는 작업 내내 **재시작 없음**(시작 시각 그대로).

### 7-3. 확인 (내 PC → 외부 주소)

| 대상 | 결과 |
|---|---|
| `/moneyon` | 308 → `/moneyon/` |
| `/moneyon/` | 200, 제목 "MONEY — 어린이 용돈 체험" |
| `/moneyon/_next/static/*.js` | 200, `immutable` 캐시 |
| `/moneyon/characters/izani-bee.png` | 200 `image/png` 35,603B |
| `POST /moneyon/api/moneyon/trial/start` | 200, 체험 토큰 발급 |
| `GET /moneyon/api/moneyon/trial/state` (가짜 `Authorization` 포함) | 200 |
| 다른 출처(`Origin: https://evil.example`) POST | 403 "이 체험 화면에서 요청해 주세요." (출처 검사 정상) |
| `/moneyon/api/access/status` (체험 외 API) | 404 (원본과 같이 차단) |
| 헤드리스 Chrome `/moneyon/` | 화면 정상, 꿀벌 이미지 로드, "바로 체험하기" 클릭 → `POST /moneyon/api/moneyon/trial/start` 200, 체험 화면 표시 |
| AI LAB `/`, `/realestate`, `/dreamcar` | 모두 200, AI LAB `/_next/static` 200, `/api/ready` ready, 지도 `naver` |
| 서버 | 체험 DB `trial.sqlite3`가 볼륨 `ailab_moneyon-runtime`에 생성. 메모리: moneyon 40MiB, ailab 103MiB, caddy 79MiB, 사용 가능 9.6GiB |

브라우저 콘솔 오류는 둘 다 **HF에서도 똑같이 나는 기존 동작**(HF Space·HF AI LAB에서 같은 방법으로 확인):
- 머니온 `/favicon.ico` 404 — 원본에 아이콘 없음.
- AI LAB `/realestate`에서 `HEAD /`, `HEAD /admin` 405 — Next 링크 사전 확인(HEAD)을 AI LAB 서버가 GET만 받음.

`Authorization` 제거는 외부에서 직접 관찰할 수 없어 실행 중 Caddy 설정(JSON)에 두 경로 모두 `headers.request.delete: ["Authorization"]`가 있는 것으로 확인.

### 7-4. 주의사항

- **Caddyfile은 파일 하나만 bind mount**되어 있어 `git pull`로 파일이 교체되면(새 inode) 실행 중 Caddy 컨테이너는 옛 파일을 계속 본다. 그래서 `caddy reload --config /etc/caddy/Caddyfile`로는 새 규칙이 반영되지 않는다 → 위 5번처럼 **표준입력으로 reload**. 컨테이너가 재시작·재생성되면 새 파일을 다시 연결하므로 그 뒤엔 일치한다.
- compose의 caddy 설정(`depends_on`)이 바뀐 상태라 다음에 서비스 이름 없이 `docker compose up -d`를 하면 caddy가 재생성됨(수 초 중단). 의도할 때만.
- Caddy 관리 API는 컨테이너 안에서 `localhost`가 아니라 `127.0.0.1:2019`로 접근(busybox wget이 IPv6로 시도해 거부됨).
- 체험 기록은 볼륨에 남는다(재빌드 후에도 유지). 24시간 만료·`KEEP=3000` 정리는 앱이 함. `/api/health`의 `"storage":"ephemeral"`은 원본 코드의 고정 문구.
- 요청 제한은 모든 방문자가 Caddy 주소 하나로 보여 합산(HF 공용 프록시와 같은 조건).

### 7-5. 되돌리기

1. 이전 Caddyfile로 reload: `git show d2619034~1:Caddyfile | docker exec -i ailab-caddy caddy reload --config /dev/stdin --adapter caddyfile`
2. `docker compose stop moneyon` (필요하면 `docker compose rm -f moneyon`, 볼륨은 남음)
3. AI LAB 컨테이너는 손대지 않아도 됨.

### 7-6. 남은 일

- AI LAB 홈 카드 링크를 오라클 `/moneyon`으로 바꿀지(지금은 HF 유지, 바꾸면 `web/**` 변경이라 main 병합 시 HF AI LAB 배포).
- 머니온 원본 갱신 절차: HF Space가 바뀌면 같은 방식(Space 커밋 기준 복사 → 해시 확인 → `next.config.ts`만 재적용)으로 `apps/moneyon/` 갱신.
- 선택: Caddy를 디렉터리 bind mount로 바꾸면 `git pull` 후 일반 `caddy reload`가 가능(바꿀 때 caddy 재생성 1회).
