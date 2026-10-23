# Hugging Face Space → 오라클 클라우드 VM 이전

> 파일명 안내: 요청하신 `docs/MIGRATION.md`는 Windows에서 기존 `docs/migration.md`(Streamlit→FastAPI 가이드, Git 추적 중)와 같은 파일로 취급돼 덮어쓰게 되므로 `MIGRATION_ORACLE.md`로 만들었습니다.

대상: Oracle Linux 9, 사용자 `opc`. 구성: 컨테이너 1개(FastAPI가 API + Next.js 정적 화면을 같은 포트로 제공).

## 1. Hugging Face에만 의존하는 부분

| 항목 | 위치 | 이전 시 처리 |
|---|---|---|
| 포트 7860 | `Dockerfile` EXPOSE/CMD, `deploy/space_README.md`(`app_port`) | 앱은 7860 유지하되 외부에 열지 않음. 외부는 Caddy가 80/443만 받음 |
| uid 1000 사용자 | `Dockerfile`(`useradd -m -u 1000 user`) | 그대로 사용 가능. named volume을 쓰므로 호스트(`opc`) 권한 문제 없음 |
| 시크릿 | HF Settings → *Variables and secrets* (`docs/deploy.md` 5번) | `.env.docker`(템플릿 `.env.example`) → compose `env_file` |
| 컨테이너 디스크 초기화 | `docs/deploy.md`, `services/access.py` | `SUPABASE_*`가 있으면 Supabase 저장(변화 없음). 없으면 `data/admin`을 named volume `ailab-admin`에 보관 |
| 자동 배포 | `.github/workflows/deploy-space.yml`, `scripts/deploy_space.py` (`HF_TOKEN`, `HF_SPACE`) | VM 이전 후 불필요. VM에서는 `git pull && docker compose up -d --build`. 워크플로는 비활성화 권장 |
| 하드코딩 주소 | `services/map_providers.py:19` `NAVER_WEB_SERVICE_URL = 'https://minseo2-digital-ai-lab.hf.space'` | **환경변수 `NAVER_WEB_SERVICE_URL`로 변경 가능(비우면 HF 주소 그대로).** 이전 시 새 주소를 넣고 네이버 지도 콘솔의 웹 서비스 URL 등록도 같이 변경 |
| 하드코딩 주소 | `web/src/lib/services.ts:77` `minseo2-moneyon-demo.hf.space` | MONEY:ON은 별도 Space. 이번 이전 대상이 아니면 그대로 |
| 외부 연동 | Streamlit 쪽 `NEW_SITE_URL` | 새 주소로 변경 |
| `/data` 경로, HF 캐시 | 해당 없음 | 코드에 `/data`(HF 영구 스토리지) 사용 없음. `HF_HOME` 등 HF 캐시 설정도 없음. rembg 모델은 빌드 때 `/home/user/app/.rembg`에 이미지 내장 |
| 프록시 헤더 (해결) | `Dockerfile` CMD `--proxy-headers --forwarded-allow-ips "*"` | Dockerfile은 HF용 그대로 두고, compose가 `command`로 덮어써 Caddy 고정 IP(172.28.0.2)만 신뢰 |

## 2. 변경/추가한 파일

- `.env.example` — 환경변수 **이름만**(값 없음). `services/config.py`의 `get_secret`과 `os.environ` 사용처를 조사해 만들었음. `docs/deploy.md`에만 있고 코드에서는 못 찾은 `NAVER_API_KEY`, `DATA_GO_KR_SERVICE_KEY`도 포함(안 쓰면 삭제 가능).
- `docker-compose.yml` — `restart: always`, healthcheck(`/api/health`), 로그 로테이션, named volume.
- `.dockerignore` — 신규. 허용 목록 방식(`deploy_space.py`의 ALLOW와 같은 범위). 없으면 로컬 `docker build`가 `.env`, `secrets.toml`, venv, `reports/`까지 이미지에 넣게 됨.
- `Dockerfile` — `RUN mkdir -p data/admin` 한 줄 추가(볼륨이 uid 1000 소유로 생성되도록). HF 빌드에는 영향 없음.
- `.gitignore` — `.env.docker` 추가.
- `Caddyfile` + compose `caddy` 서비스 — 80/443(+443/udp)만 외부 공개, 앱은 `expose`만. 고정 서브넷 172.28.0.0/24(Caddy .2, 앱 .10). 도메인은 `.env`의 `SITE_ADDRESS`(없으면 `:80` HTTP). 도메인을 넣으면 인증서 자동 발급.
- `services/map_providers.py` — `NAVER_WEB_SERVICE_URL` 환경변수 지원(기본 HF 주소).
- compose는 기존 `.env` 대신 `.env.docker`를 씁니다. 로컬 `.env`에 `HF_TOKEN`이 있어 컨테이너로 들어가는 것을 막기 위함입니다.

## 3. VM 설치 (Oracle Linux 9, opc)

Oracle Linux 9에는 기본으로 podman이 있습니다. Docker CE를 쓰는 경우:

```bash
sudo dnf -y install dnf-plugins-core git
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker   # 재부팅 후 자동 시작의 전제 (restart: always만으로는 부족)
sudo usermod -aG docker opc          # 재로그인 필요
```

```bash
git clone <저장소 주소> ailab && cd ailab
cp .env.example .env.docker && chmod 600 .env.docker   # 값 채우기
docker compose up -d --build
docker compose ps                   # STATUS가 healthy 인지
curl -s localhost/api/health            # Caddy 경유
```

네트워크(둘 다 열어야 접속됨):
1. OCI 콘솔: VCN → Security List(또는 NSG) Ingress에 TCP 80, 443 추가
2. VM 방화벽: `sudo firewall-cmd --permanent --add-service={http,https} && sudo firewall-cmd --reload` (7860은 열지 않음)

도메인 연결: `.env`에 `SITE_ADDRESS=도메인` 후 `docker compose up -d`. 네이버 지도는 보통 도메인 등록이 필요하므로 `NAVER_WEB_SERVICE_URL`도 함께 바꿉니다.

아키텍처: Ampere(ARM) 인스턴스면 `node:22-slim`, `python:3.12-slim`, `onnxruntime`, `rembg`의 aarch64 이미지/휠이 대체로 있지만 **ARM에서는 빌드해 보지 못했습니다.** rembg 때문에 메모리는 2GB 이상(또는 스왑)을 권장합니다.

## 4. 테스트 결과 (내 PC, 2026-10-23)

- **Docker 테스트는 하지 못했습니다.** 이 PC에는 Docker(및 podman)가 없습니다. 따라서 `docker-compose.yml` 문법, 이미지 빌드, healthcheck, 볼륨 권한, `restart: always` 동작은 **미검증**입니다.
- 대신 같은 코드를 `.venv`의 uvicorn으로 직접 실행해 확인했습니다.
  - `GET /api/health` → 200, `{"ok":true,"service":"ailab-api",...}`
  - `GET /` → 200 (기존 `web/out` 화면 제공)
  - `GET /api/ready` → `not_ready` (`supabase: not_configured`). 로컬에 Supabase 키가 없어서이며, 운영에서는 `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`를 넣어야 ready가 됩니다. healthcheck는 `/api/health`만 쓰므로 영향 없음.
- Docker 설치 후 확인 순서: `cp .env.example .env.docker` → `docker compose config` → `docker compose up -d --build` → `docker compose ps`(healthy) → `docker kill ailab` 후 자동 재기동 확인.

## 5. 남은 일

- 이전 후 HF Space·GitHub `HF_TOKEN` 정리, 자동 배포 워크플로 비활성화.
- `reports/` 아래 `moneyon-*` Dockerfile들은 다른 Space용이며 이번 구성과 무관.
