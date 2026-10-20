# MONEY Phase 5 — Hugging Face Spaces 배포 준비 보고

> **현재 절차 변경:** 사용자 요청에 따라 HF CLI 로그인·CLI Space 생성은 사용하지 않는다. 사용자가 웹에서 Space를 직접 만든 후 파일을 올리거나, 새 MONEY 전용 GitHub 저장소의 수동 Actions로 동기화한다. 현재 파일 목록·ZIP·토큰 등록·설정 절차는 [웹 업로드 안내](MONEYON_WEB_UPLOAD.md)를 우선한다. 아래 CLI 생성 절차는 이전 설계 기록이며 현재 실행 대상이 아니다.

작성일: 2026-10-16 (한국 시간). **원격 Space 생성·업로드·Git push는 하지 않았다.** 실제 배포는 사용자 승인 후 진행한다.

## 1. 기존 환경 분석과 선택

로컬 배포 정의를 확인했다.

| 항목 | 기존 AI LAB 구성 |
| --- | --- |
| 유형 | `deploy/space_README.md`: `sdk: docker`, `app_port: 7860` |
| 빌드 | 루트 `Dockerfile`: Node 22로 Next.js 정적 export → Python 3.12/FastAPI |
| 실행 | `api.main:app` 한 프로세스가 API와 화면을 같은 주소로 제공 |
| 업로드 | `.github/workflows/deploy-space.yml` → `scripts/deploy_space.py` |
| 기존 키 | 관리자·Supabase·은행 외 에이전트 API 등 여러 서비스용 키가 있는 구성 |
| 이전 Streamlit | `docs/deploy.md`는 Streamlit 주소에서 새 Docker 사이트로 이동하는 과거 연결 방법을 설명 |
| 원격 확인 제한 | 현재 환경에 실제 `HF_SPACE`, `MONEYON_HF_SPACE`, `HF_TOKEN`이 없어 운영 중 Space의 SDK·설정·상태는 조회하지 못함. Docker는 **저장소의 현재 배포 정의** 기준으로 확인 |

| 선택지 | 장점 | 영향과 판단 |
| --- | --- | --- |
| 기존 AI LAB Space에 추가 | 기존 URL·운영 활용 | 기존 관리자·DB 키·다른 에이전트·배포 주기를 공유. 시험 서비스만 공개하기 어려움 |
| MONEY 전용 Docker Space | 기존 정적 Next + FastAPI 구조 재사용, 체험만 공개, 운영 키 불필요 | Space를 하나 더 관리. **선택** |
| Streamlit으로 다시 구현 | 기존 Streamlit 경험 활용 가능 | 현재 Next.js 화면을 재작성해야 하므로 채택하지 않음 |

Vercel은 사용하지 않는다. 기존 루트 Dockerfile, 기존 Space README·업로드 스크립트·배포 workflow는 수정하지 않았다. AI LAB에서 연결할 URL은 실제 MONEY Space 생성 후 결정되므로 기존 포털 링크도 아직 변경하지 않았다.

## 2. 전용 Space 실행 구조

`scripts/prepare_moneyon_space.py`는 화이트리스트의 소스 **39개 파일**을 새 출력 폴더에 복사하고 SHA-256 `manifest.json`을 만든다. 원본 작업공간 전체를 업로드하거나 Docker context로 사용하지 않는다.

```text
방문자 HTTPS
  → Hugging Face 프록시
  → 컨테이너 :7860 / space_app:app
      ├─ /, /moneyon, /_next/* : Next.js 정적 export
      ├─ /api/health
      └─ /api/moneyon/trial/* : Phase 4 체험 API
            └─ 방문자별 가족·자녀·분개 / runtime/trial.sqlite3
```

Docker는 Node 22 빌드 단계와 Python 3.12 실행 단계를 사용한다. 런타임은 UID 1000, 단일 Uvicorn worker다. 체험 DB 디렉터리는 UID 1000이 쓸 수 있게 생성한다. 같은 원본 금융 엔진을 사용하며 실제 가족 라우터는 등록하지 않는다. 전용 화면에는 부모 시작·관리·로그인 메뉴가 없다.

유지 기능: PIN 없는 진입, 통장 28,500원·저금통 15,000원·총 43,500원·기존 엔진 예상 보상 800원, 금액 입력 용돈·소비·저축, 분류 수정, 날짜·승인 시뮬레이션, 목표, 초기화, 홈·통장·저축 모바일 화면.

## 3. 보안과 데이터 경계

- 운영 DB 파일·`.env`·`.streamlit`·비밀키·실제 사용자 데이터·다른 에이전트 API는 업로드 목록에서 제외한다.
- 런타임에 `api.main`을 가져오지 않는다. 부모·관리자·포털 로그인·다른 서비스 API는 404이며 OpenAPI·Swagger도 제공하지 않는다.
- 기존 부모 API가 사용하는 개발 플래그는 0이고 `APP_ENV=production`이다. 실제 은행 API 구현과 연결 키는 포함하지 않는다.
- 방문자별 난수 토큰과 SHA-256 서버 저장, 소유 자녀 ID, 쓰기 세대 번호 검증을 유지한다. 공유 전역 데모 계좌가 없다.
- 체험 응답 캐시 금지, 다른 Host에서 온 브라우저 쓰기 차단, 교차 출처 CORS 허용 없음, 요청 본문 16KiB 제한을 적용한다.
- HTTPS가 HF 프록시에서 종료돼 내부 요청이 HTTP여도 Host가 일치하는 HTTPS Origin은 허용한다. 위조 `X-Forwarded-Host`는 신뢰하지 않는다.
- peer당 1분에 체험 시작 60회·기타 쓰기 600회로 제한한다. 프록시 peer를 공유하는 방문자는 한도를 공유할 수 있다. 이 제한은 보조 수단이며 방문자 식별·데이터 권한은 비밀 토큰으로 검사한다.
- 기본 access log를 끄고 토큰·본문·비밀값을 출력하지 않는다. 키가 필요한 외부 DB나 AI·은행 호출은 수행하지 않는다.

Space 런타임 Secrets는 **없다**. `HF_TOKEN`은 승인 후 로컬 업로드 명령 또는 별도 배포 시스템에서만 사용하며 Space 환경변수나 소스에 넣지 않는다.

## 4. HF 세션·디스크 정책

| 상황 | 동작 |
| --- | --- |
| 같은 탭 새로고침 | sessionStorage 토큰으로 서버 원장을 다시 읽음 |
| 새 일반 탭·새 브라우저 | 독립 체험 |
| 탭 복제·복원 | 브라우저가 토큰을 복사·복원하면 같은 체험 공유 가능 |
| 토큰 기간 | 생성 후 최대 24시간. 새로고침으로 연장하지 않음 |
| 서버 프로세스만 재시작, DB 파일 유지 | 토큰과 거래 유지 |
| 컨테이너 교체·재빌드·디스크 소실 | 기존 토큰은 거절. 처음 화면에서 새 체험 시작 |
| 초기화 | 해당 방문자만 새 시드로 원자적 교체. 기존 자녀·오래된 세대 요청 거절 |

현재 구성은 체험 기록의 영속 보존을 약속하지 않는다. HF 문서도 기본 Docker 디스크가 재시작 때 사라진다고 설명한다. 로컬 검사에서 **동일 DB 프로세스 재시작**과 **새 DB로의 컨테이너 디스크 소실**을 각각 모사했다. 실제 HF 수면·재시작·재빌드는 아직 수행하지 않았다.

SQLite를 Bucket/FUSE/NFS에 직접 두지 않는다. 현재는 별도 Bucket·운영 Supabase·외부 DB를 사용하지 않는다. 장기 보존·다중 replica·만료 감사 이력 자동 삭제는 이 체험 배포에 포함하지 않는다. 동시 방문은 한 서버의 독립 계좌로 처리한다.

## 5. 검증 결과와 제한

| 검사 | 결과 |
| --- | --- |
| Python 회귀 | 기존 171 + Phase 4 33 + 배포 15 = **219개** |
| 기존 어린이 UI·코치 | **28개 통과** |
| Space 전용 Next 정적 production build / TypeScript | **통과**. `/`, `/moneyon`과 정적 자산만 생성 |
| 동일 주소 실제 Chrome | **14개 시나리오 통과**, API mock 없음, JS 오류 0건 |
| 모바일·태블릿·데스크톱 | **375 / 768 / 1440px**, 가로 넘침 없음 |
| 요청 출처·HF TLS 프록시 | 정상 HTTPS Origin 허용, 다른 Host·위조 forwarded host 거절 |
| 운영 경로·소스·DB 노출 | 가족/관리자/기타 API·설정 파일·DB URL 404 검증 |
| 업로드 dry run | 39개 소스와 manifest 검증. HF 요청 없음 |
| Docker 이미지 빌드·컨테이너 실행 | **미실행**. 이 PC에 Docker/Podman 실행기가 없음 |
| 실제 HF 빌드·수면·접속 | **미실행**. Space ID·토큰 미설정 및 사용자 배포 승인 대기 |

로컬 정적 빌드와 동일 서버 검증은 Docker/HF 실행 완료를 의미하지 않는다. Docker 실제 실행은 아래 명령 또는 추가한 수동 CI로 확인해야 한다. CI도 아직 실행하지 않았다.

결과: [회귀 JSON](../reports/moneyon-phase5/regression-result.json), [Chrome JSON](../reports/moneyon-phase5/browser-result.json).

캡처: [375px](../reports/moneyon-phase5/space-home-375.png), [768px](../reports/moneyon-phase5/space-home-768.png), [1440px](../reports/moneyon-phase5/space-home-1440.png).

## 6. Docker 검증 명령

프로젝트 루트에서 새 소스 번들을 생성한다. 기존 출력 폴더는 덮어쓰지 않는다.

```powershell
.venv/Scripts/python.exe scripts/prepare_moneyon_space.py --output reports/moneyon-space-candidate-docker
docker build -t moneyon-trial:phase5 reports/moneyon-space-candidate-docker
docker run --rm --name moneyon-check -p 127.0.0.1:7860:7860 moneyon-trial:phase5
```

별도 터미널:

```powershell
.venv/Scripts/python.exe scripts/check_moneyon_space.py --url http://127.0.0.1:7860
```

컨테이너 종료 후 해당 컨테이너 DB는 보존하지 않는다. 업로드는 빌드에 사용한 변경된 폴더가 아니라 **새로 생성한 소스 전용 번들**로 한다. `deploy_moneyon_space.py`는 추가 파일·변경된 파일·비밀 경로를 거절한다.

Docker가 있는 Linux CI에서는 `.github/workflows/moneyon-space-check.yml`을 수동 실행할 수 있다. checkout → 소스 번들 → Docker build → run → 정적 페이지/샘플/격리/용돈/초기화 smoke test를 수행한다. **HF 생성·업로드는 전혀 하지 않는다.**

## 7. 실제 Space 생성·업로드 방법 — 승인 후에만

권장 새 ID는 `실제소유자/moneyon-demo`다. 실제 소유자는 아직 정해지지 않았다. 기존 AI LAB Space ID를 사용하지 않는다.

### 검토용 번들

현재 검토 폴더는 `reports/moneyon-space-candidate-reviewed`다. source 파일 39개와 manifest만 들어간다. 비밀값이 없고 기존 실제 거래 데이터도 없다.

```powershell
.venv/Scripts/python.exe scripts/deploy_moneyon_space.py --bundle reports/moneyon-space-candidate-reviewed --space 실제소유자/moneyon-demo
```

이 기본 명령은 **로컬 검사만** 하고 HF API를 호출하지 않는다.

### 승인 후 새 공개 Docker Space 자동 생성

로컬 환경에 쓰기 권한 HF 토큰을 안전하게 설정한다. 토큰은 채팅·Git·명령줄 인자에 붙이지 않는다. 아래 `$env:HF_TOKEN`은 이미 설정된 환경변수를 사용한다.

```powershell
# 필요한 경우 배포 도구 전용 가상환경에 설치
python -m venv .venv-moneyon-deploy
.venv-moneyon-deploy/Scripts/python.exe -m pip install "huggingface_hub>=0.25,<2"

# 실제 사용자 승인 후에만 실행: 새 public Docker Space 생성 + 소스 업로드
.venv-moneyon-deploy/Scripts/python.exe scripts/deploy_moneyon_space.py --bundle reports/moneyon-space-candidate-reviewed --space 실제소유자/moneyon-demo --publish
```

`--publish`가 없으면 네트워크 요청이 없다. 업로드 명령은 기존 AI LAB의 `HF_SPACE`와 같은 대상을 거절하고, 어떤 기존 Space라도 `exist_ok=False`로 생성에 실패하도록 하여 덮어쓰지 않는다. 기존 MONEY Space의 추후 업데이트는 현재 최초 생성 명령의 범위에 포함하지 않는다.

### 웹 UI로 만드는 대안

승인 후 [새 Space](https://huggingface.co/new-space)에서 소유자·`moneyon-demo`·공개 여부·Docker SDK를 선택하고, 번들 루트의 `Dockerfile`, `README.md`, 소스 폴더를 업로드한다. 이 방법은 위 자동 생성 명령과 **둘 중 하나만** 사용한다. 수동 생성 후 `--publish`를 실행하면 기존 Space 보호 규칙으로 거절한다.

### 설정

| 변수 | 값/설정 위치 |
| --- | --- |
| `APP_ENV` | Docker 기본 `production` |
| `MONEYON_TRIAL_ENABLED` | Docker 기본 `1` |
| `MONEYON_LOCAL_DEV`, `MONEYON_DEMO` | Docker 기본 `0` |
| `MONEYON_TRIAL_DB` | Docker 기본 `/home/user/app/runtime/trial.sqlite3`; 변경하지 않음 |
| `STATIC_EXPORT` | 빌드 단계 `1` |
| `NEXT_PUBLIC_API_URL` | 빌드 단계 **빈 문자열**. 브라우저가 같은 Space의 `/api/...` 사용 |
| `NEXT_PUBLIC_MONEYON_EPHEMERAL` | 빌드 단계 `1`; 서버 디스크 소실 안내 |
| `HF_TOKEN` | 로컬 업로드 환경만. Space Secrets에 넣지 않음 |
| 운영 DB·실제 사용자·은행·AI 키 | **설정하지 않음** |

일반 CPU Docker 하드웨어로 시작하는 구성이며 계정의 제공 옵션·비용은 생성 시 확인한다. GPU나 유료 영속 저장소는 요청하지 않았다.

### 예상 주소와 승인 후 확인

- 저장소: `https://huggingface.co/spaces/실제소유자/moneyon-demo`
- 일반적인 앱 주소: `https://실제소유자-moneyon-demo.hf.space/`
- 체험 진입: 앱 주소의 `/` 또는 `/moneyon`
- 상태: 앱 주소의 `/api/health`

정확한 앱 호스트는 생성된 Space의 Embed/실행 주소에서 확인한다. URL은 아직 발급되지 않았다. Space Logs에서 빌드와 실행을 확인한 후 `check_moneyon_space.py --url https://실제앱주소`를 실행하고 실제 모바일·별도 브라우저·서버 재시작을 다시 확인한다. 이 공개 smoke test도 체험 데이터만 생성한다. 완료 후 AI LAB의 MONEY 링크 연결을 별도 검토한다.

## 8. Git 변경 정리와 승인 범위

신규:

- `deploy/moneyon/`: Dockerfile, requirements, Space README, 전용 layout/page, 체험 서버
- `scripts/prepare_moneyon_space.py`, `deploy_moneyon_space.py`, `check_moneyon_space.py`
- `tests/test_moneyon_space.py`, `tests/test_moneyon_space_browser.cjs`
- `.github/workflows/moneyon-space-check.yml`
- `docs/MONEYON_SPACES.md`, `reports/moneyon-phase5/` 검증 결과·캡처

수정: `TrialExperience.tsx`의 Space 저장 정책 안내, `.gitignore`의 생성 번들 제외, `docs/MONEYON.md`의 Phase 5 링크.

기존 작업공간에는 이 작업 이전의 대규모 변경 및 Git 미추적 Phase 1~4 코드가 있다. `git add .`나 전체 작업공간 커밋을 하지 않았다. 새 CI를 사용하려면 배포 번들의 원본인 MONEY Phase 1~4 파일도 Git에 포함해야 한다. `manifest.json`이 필요한 원본 파일 검토 기준이다. node_modules·빌드 결과·체험 DB·비밀값은 커밋하지 않는다.

기존 AI LAB workflow는 `main`의 `api/**`, `services/**`, `web/**`, `deploy/**` 변경에 자동 배포하도록 되어 있으므로, 검토 전 main push를 하면 기존 AI LAB 배포가 촉발될 수 있다. 이 작업에서는 commit·push·workflow 실행을 하지 않았다. 우선 별도 소스 번들을 검토하고 MONEY 전용 Space만 생성하는 방식이다.

승인이 필요한 실제 외부 변경은 **지정한 새 공개 Docker Space 생성 및 검토 번들 업로드**다. 기존 AI LAB Space·운영 DB·운영 비밀키·Git 원격은 변경하지 않는다. 소유자/Space ID와 배포 승인을 받은 뒤 수행한다. Docker 실검증과 HF 실환경 검증이 남았다는 제한을 함께 검토해야 한다.

공식 근거: [Docker Spaces·7860·UID 1000·환경변수](https://huggingface.co/docs/hub/spaces-sdks-docker), [디스크·저장소](https://huggingface.co/docs/hub/spaces-storage), [Space 생성·관리](https://huggingface.co/docs/huggingface_hub/guides/manage-spaces), [폴더 업로드](https://huggingface.co/docs/huggingface_hub/guides/upload).
