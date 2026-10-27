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

## 6. 이전 대상 서버 (2026-10-26 확인)

| 항목 | 내용 |
|---|---|
| IP | `140.245.88.198` (호스트명 `instance-20261026-1648`, 사용자 `opc`) |
| OS | Oracle Linux Server 9.8 |
| Shape | **VM.Standard.A1.Flex (aarch64)**, 2 OCPU, 12GB (OS에서 보이는 메모리 약 10.6GiB, 사용 가능 약 9.9GiB) |
| 스왑 | 4GB (`/.swapfile`) |
| 디스크 | `/` 30GB 중 9.9GB 사용 (20GB 여유) |
| 접속 | 이 PC에서 `ssh ailab` (`~/.ssh/config`, 키 `~/.ssh/ailab-a1.key`) |

향후 같은 서버에 드림카(`/dreamcar`), MONEY:ON(`/moneyon`)을 경로로 함께 올릴 계획입니다(Caddyfile 경로 라우팅 추가 필요).

### 6-1. 기본 세팅 (2026-10-26 완료)

| 단계 | 결과 |
|---|---|
| 0. 디스크 확장 | **불필요.** 부트 볼륨 46.6G = `/boot/efi` 100M + `/boot` 2G + LVM PV 44.5G(VG 여유 0). PV가 `root` 29.5G(XFS, `/`)와 `oled` 15G(`/var/oled`, 오라클 기본 진단 로그 볼륨)로 전부 할당돼 있어 `oci-growfs`로 늘릴 미할당 공간 없음 |
| 1. 시스템 업데이트 | `dnf -y update` 완료. 커널 `6.12.0-207.111.5.1` → `6.12.0-207.111.5.6.el9uek` (재부팅으로 적용) |
| 2. Docker | Docker 공식 RHEL 저장소(`docker-ce.repo`)로 설치: docker-ce 29.9.2, containerd.io 2.4.2, buildx 0.38.1, compose 플러그인 v5.6.1 (모두 aarch64). podman 미설치 |
| 3. 자동 시작 | `systemctl enable --now docker containerd` → 재부팅 후 `enabled/active` 확인 |
| 4. sudo 없이 docker | `usermod -aG docker opc` (opc 그룹: opc, adm, systemd-journal, docker) |
| 5. firewalld | `http`, `https` 영구 허용 → 허용 서비스 `dhcpv6-client http https ssh` (재부팅 후 유지 확인). 7860은 열지 않음 |
| 6. git | git 2.52.0 |
| 확인 | 재부팅 후 opc로 sudo 없이 `docker run --rm hello-world` → "Hello from Docker!" (arm64v8 이미지), exit 0 |

세팅 후 디스크 `/` 30G 중 11G 사용, 메모리 사용 가능 약 9.9GiB.

### 6-2. 첫 배포 (2026-10-27)

주소: **https://140-245-88-198.sslip.io** (도메인 없이 sslip.io로 IP를 이름으로 씀)

| 항목 | 결과 |
|---|---|
| 코드 | 서버 `~/ailab`에 `git clone -b oracle-migration` (커밋 `5dd9d12`) |
| `.env.docker` | 내 PC 파일을 이름만 점검(템플릿 항목 모두 있음, 필수 `ADMIN_PASSWORD`·`SUPABASE_URL`·`SUPABASE_SERVICE_ROLE_KEY` 채워짐, 따옴표 없음) 후 업로드, 권한 600. 올리는 사본만 CRLF→LF, `NAVER_API_KEY` 앞 공백 제거(코드에서 안 쓰는 키) |
| `.env` (compose용) | 내 PC `.env`를 복사하지 않고 서버에서 새로 만듦: `SITE_ADDRESS=140-245-88-198.sslip.io` 한 줄, 권한 600 |
| 빌드 | `docker compose up -d --build` ARM(aarch64) 빌드 성공. Next.js·onnxruntime·rembg(u2net 176MB 내장) 포함 |
| 컨테이너 | `ailab` healthy, `ailab-caddy` Up. 볼륨 `ailab_ailab-admin`, `ailab_caddy-data`, `ailab_caddy-config` |
| HTTPS | Caddy가 Let's Encrypt 인증서 자동 발급(만료 2027-01-24, 자동 갱신). http → https 308 |
| 외부 확인(내 PC) | `/` 200(gzip), `/api/health` 200, 7860 직접 접속 차단 |
| `/api/ready` | **ready** (supabase ok 163ms, naver/tavily/llm ok) |
| 메모리 | 실행 중 사용 약 1.1GiB, 사용 가능 약 9.5GiB |

배포 중 발견·해결:
- 처음 `.env.docker`의 `SUPABASE_SERVICE_ROLE_KEY`·`ZIPON_SUPABASE_SERVICE_ROLE_KEY`가 **공개용 키(`sb_publishable_…`)**여서 `services/supabase_auth.py`가 거부 → `/api/ready` not_ready(`ValueError`). 둘 다 비밀 키(`sb_secret_…`)로 바꾼 뒤 `docker compose up -d --force-recreate --no-deps ailab`(재빌드 없음)로 해결. 점검 스크립트는 이름만 보므로 **키 종류(sb_secret/JWT/publishable)도 따로 확인**해야 함.
- `docker compose run`으로 임시 컨테이너를 띄우면 앱의 고정 IP(172.28.0.10)와 충돌함 → 일회성 점검은 `docker run --rm --env-file .env.docker ailab:latest ...` 사용.
- 서버를 띄우자마자 `/api/.env`를 찾는 외부 스캔이 들어옴(404). 비밀값 파일은 이미지·정적 경로에 없음.

### 6-3. HF와 같은 운영 Supabase를 함께 쓰는 동안 (병행 기간)

`SUPABASE_URL`·`ZIPON_SUPABASE_URL` 모두 `nnxtkvjpzqqhjlgnprzo`로 HF와 같은 프로젝트.

| 작업 | 실행 위치 | 오라클 추가로 중복? |
|---|---|---|
| 부동산 모니터 (`scheduler.py --once`, 6시간마다) | GitHub Actions `realestate-monitor.yml` | 아니오 — 앱 서버 안에서 돌지 않음 |
| ZIP:ON 개발사업 갱신 (매일/매주/매월) | GitHub Actions `zipon-development-refresh.yml` (`ZIPON_IMPORT_*` 사용, 오라클 `.env.docker`에 없음) | 아니오 |
| 골프 분기 갱신 | GitHub Actions `golf-quarterly-refresh.yml` (저장소 파일 갱신, Supabase 아님) | 아니오 |
| 알림 발송 | 없음 — `notifications` 테이블에 저장만 하고 메일·메신저 발송 코드 없음 | 해당 없음 |
| 앱 시작 시 백그라운드 | `usage_events` 수집기 하나(`api/main.py` lifespan) — 그 서버에 온 실제 방문(브라우저 이벤트)과 서비스 API 오류만 기록. healthcheck·정적 파일은 기록 안 함 | 중복은 아니지만 **오라클 접속(테스트 포함)이 HF와 같은 사용량 통계에 섞임** |
| 접속 관리 서명 키 | Supabase `app_settings.access_secret`에 이미 있음(존재만 확인, 값 조회 안 함). 오라클 `ACCESS_SECRET`은 비어 있어 이 값을 읽음 → 새로 만들지 않음 | 아니오. 단 HF가 `ACCESS_SECRET`을 Secrets로 따로 쓰고 있다면 두 서버 서명 키가 달라짐 → 오라클에서 기존 접속 코드로 로그인되는지 한 번 확인 |
| 관리자 화면 수정(접속 코드·구성원, 부동산 알림 규칙) | 사람이 직접 | 두 곳에서 동시에 고치면 마지막 저장이 이김(`access_settings`는 한 JSON 통째 저장) → **병행 기간에는 관리자 수정을 HF 한 곳에서만** |

결론: 자동 작업이 두 곳에서 중복 실행되는 것은 없어서 지금 꺼 둘 것은 없음. 사용량 통계 섞임을 피하고 싶다면 선택지:
1. 오라클 `.env.docker`에 별도 분석용 프로젝트 `ANALYTICS_SUPABASE_URL`/`ANALYTICS_SUPABASE_SERVICE_ROLE_KEY`를 넣기 (코드가 이미 지원, 운영 통계와 분리)
2. 수집기를 끄는 환경변수(예: `USAGE_EVENTS_DISABLED=1`)를 `services/usage_events.py`에 추가 — 코드 변경이라 별도 작업
3. 병행 기간이 짧으면 그대로 두고, 전환 후 HF를 끄면 자연히 해결

### 6-4. 재시작 테스트 (2026-10-27)

| 테스트 | 결과 |
|---|---|
| `docker kill ailab` | **자동 재기동 안 됨(정상 동작).** Docker는 `docker kill`/`docker stop`처럼 사용자가 직접 멈춘 컨테이너에는 `restart: always`를 적용하지 않음(데몬 재시작·수동 시작 전까지 꺼진 채 유지). 90초 동안 `exited`(137), 그 사이 외부 502. `docker start ailab`으로 복구(약 2분 중단, 그 동안 `/realestate` 사용 중이던 실제 방문 요청이 502를 받음) |
| 장애 흉내: 호스트에서 컨테이너 메인 프로세스 `sudo kill -9 <PID>` | **자동 재기동 확인.** 즉시 재시작(RestartCount 0→1), 6초 뒤 healthy, 외부 `/api/ready` ready |
| 서버 재부팅 `sudo systemctl reboot` | **자동 기동 확인.** SSH 40초, 외부 `/api/ready` ready 53초. `ailab`(healthy)·`ailab-caddy` 모두 부팅 후 자동 시작(시작 시각 갱신), 인증서는 볼륨(`caddy-data`)에 남아 재발급 없음(만료 2027-01-24 그대로) |

주의: 운영 중 컨테이너를 일부러 멈출 때는 `docker kill`/`stop` 후 반드시 `docker start` 또는 `docker compose up -d`로 다시 켜야 함. 재시작 정책 테스트는 `docker kill`이 아니라 프로세스 강제 종료로 해야 함.

### 6-5. 네이버 지도 설정 (2026-10-27)

처음 배포 때 지도 설정 응답이 `active: osm`, `sdk.configured: False` — 네이버 지도 대신 기본 지도(OSM)로 떴음.
원인: `.env.docker`에 `NAVER_MAP_NCP_KEY_ID`/`NAVER_MAP_NCP_KEY`만 있고 `NAVER_MAP_CLIENT_ID`/`NAVER_MAP_CLIENT_SECRET`이 비어 있었음.

| 조치 | 결과 |
|---|---|
| 네이버 클라우드 콘솔 Maps Application의 Web 서비스 URL에 `https://140-245-88-198.sslip.io` 추가 | 사용자가 직접 등록 |
| `.env.docker`에 `NAVER_MAP_CLIENT_ID`, `NAVER_MAP_CLIENT_SECRET`, `NAVER_WEB_SERVICE_URL=https://140-245-88-198.sslip.io` 추가 | 이름·형식만 점검(공백·따옴표 없음, URL 일치·끝 `/` 없음). 새 Client ID/Secret은 기존 NCP_KEY 값과 다른 Application 키 |
| 업로드 후 `docker compose up -d --force-recreate --no-deps ailab` | 6초 뒤 healthy, `/api/ready` ready |
| `/api/realestate/map/config` | `active: naver`, `sdk.configured: True`, `web_service_url` 새 주소, Client Secret은 브라우저로 안 내려감 |
| 헤드리스 Chrome으로 `/realestate` 열기 | `maps.js` 200, `oapi.map.naver.com/v3/auth` 200, 인증 실패 문구·콘솔 오류 없음, 네이버 타일 25개와 개발사업 마커(306/454건) 표시 |

주의사항:
- **지도 SDK는 `NAVER_MAP_CLIENT_ID`만 읽음**(`services/map_providers.py` `sdk_config`). `NAVER_MAP_NCP_KEY_ID`는 쓰지 않음.
- **`/api/ready`의 naver 점검은 `NCP_KEY_ID`도 인정**하므로 ready가 ok여도 지도는 OSM일 수 있음 → 지도는 `/api/realestate/map/config`의 `active`/`sdk.configured`로 확인.
- **`NAVER_WEB_SERVICE_URL`은 안내용**: 지도 설정 응답에 표시만 하고 인증에 쓰이지 않음. 네이버는 브라우저의 실제 페이지 주소를 콘솔 Web 서비스 URL 목록과 비교하므로, **새 주소(도메인)로 옮길 때마다 콘솔 등록이 실제로 필요한 작업**이고 이 값은 맞춰 적어 두는 것.
- `NAVER_MAP_CLIENT_SECRET`은 ZIP:ON 개발사업 서버 지오코딩(`services/development_geocode.py`)에도 필요.
- `.env.example`에 위 내용을 주석으로 추가함.

### 6-6. 남은 일

필수(전환 전):
- 오라클 주소에서 기존 접속 코드로 로그인 확인 — HF가 `ACCESS_SECRET`을 Secrets로 따로 쓰면 서명 키가 달라 실패함(6-3).
- 병행 기간 동안 관리자 수정(접속 코드·구성원, 부동산 알림 규칙)은 HF 한 곳에서만(6-3).
- 전환 결정 후: `oracle-migration`을 `main`에 병합(병합 시 HF 자동 배포 1회 실행) → 서버를 `main`으로 전환(`git checkout main && git pull && docker compose up -d --build`) → HF Space·GitHub `HF_TOKEN` 정리, `deploy-space.yml` 비활성화.

선택:
- 사용량 통계 분리: 오라클에 `ANALYTICS_SUPABASE_*` 별도 프로젝트 지정, 또는 HF 종료 후 자연 해결(6-3).
- 도메인 연결: 서버 `.env`의 `SITE_ADDRESS`를 도메인으로 바꾸고 `docker compose up -d`(인증서 자동 발급) → 네이버 콘솔 Web 서비스 URL과 `NAVER_WEB_SERVICE_URL`도 함께 변경.
- 드림카(`/dreamcar`)·MONEY:ON(`/moneyon`) 경로 추가: Caddyfile 경로 라우팅과 compose 서비스 추가.
- `.env.docker`의 `NAVER_API_KEY` 앞 공백은 업로드 사본에서만 지우고 있음 → 내 PC 원본도 정리하면 이후 업로드가 단순해짐(코드에서 쓰지 않는 키).

운영 메모:
- 서버 갱신: `cd ~/ailab && git pull && docker compose up -d --build`.
- 환경변수만 바꿀 때: `.env.docker` 업로드 후 `docker compose up -d --force-recreate --no-deps ailab`(재빌드 없음).
- 일회성 점검 컨테이너는 `docker compose run` 대신 `docker run --rm --env-file .env.docker ailab:latest ...`(고정 IP 충돌, 6-2).
- 컨테이너를 `docker kill`/`stop`으로 멈추면 자동 재시작되지 않음 → 반드시 다시 켤 것(6-4).

### 사용하지 않는 서버 (기록용)

예전 E2 Micro 서버 `161.33.167.69`(x86_64, 메모리 약 0.5GB)는 사양 부족으로 이전 대상에서 제외했고 이전 키와 함께 더 이상 쓰지 않습니다.
