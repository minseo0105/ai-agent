# MONEY Phase 5 — 웹 업로드 우선 배포 절차

현재 요청에 맞춘 안내다. **Hugging Face CLI 로그인은 사용하지 않는다.** 사용자가 웹에서 로그인하고 `moneyon-demo` Docker Space를 직접 생성한다. 이 작업에서는 로그인·Space 생성·업로드·GitHub 설정·workflow 실행을 하지 않았다.

## 1. 준비한 파일

프로젝트 기준 `reports/moneyon-web-upload/`에 아래 산출물을 만들었다.

| 산출물 | 용도 |
| --- | --- |
| `moneyon-huggingface-web.zip` | **우선 사용**. 압축 해제 후 내용물을 HF Space에 업로드. 총 40개 파일 |
| `huggingface-upload/` | 위 ZIP의 압축 해제된 원본. 바로 업로드할 수 있는 폴더 |
| `UPLOAD_FILES.txt` | Space에 올릴 정확한 상대 경로 40개 |
| `moneyon-github-web.zip` | 웹 업로드가 불편할 때 새 MONEY 전용 GitHub 저장소에 올릴 대안. 43개 파일 |
| `github-upload/` | GitHub 대안의 압축 해제된 원본 |

**ZIP 자체를 HF에 올리지 않는다.** ZIP이 자동으로 풀려 앱이 배포되는 방식이 아니다. 압축을 풀고 아래 파일·폴더를 저장소 루트에 올린다. `huggingface-upload`라는 상위 폴더를 통째로 중첩시키지 않는다.

정확한 Space 파일 구조:

```text
Space 저장소 루트/
├─ .dockerignore
├─ Dockerfile
├─ README.md
├─ requirements.txt
├─ space_app.py
├─ manifest.json
├─ api/
│  ├─ __init__.py
│  ├─ access.py
│  ├─ moneyon.py
│  └─ moneyon_trial.py
├─ services/
│  ├─ __init__.py
│  ├─ access.py
│  ├─ config.py
│  ├─ supabase_auth.py
│  ├─ moneyon.py
│  ├─ moneyon_accounts.py
│  ├─ moneyon_banking.py
│  ├─ moneyon_demo.py
│  └─ moneyon_trial.py
└─ web/
   ├─ package.json
   ├─ package-lock.json
   ├─ next-env.d.ts
   ├─ next.config.ts
   ├─ postcss.config.mjs
   ├─ tsconfig.json
   └─ src/
      ├─ app/
      │  ├─ globals.css
      │  ├─ layout.tsx
      │  ├─ page.tsx
      │  └─ moneyon/
      │     ├─ page.tsx
      │     ├─ TrialExperience.tsx
      │     ├─ ChildExperience.tsx
      │     ├─ Banking.tsx
      │     ├─ KidIcon.tsx
      │     ├─ Woorumi.tsx
      │     ├─ types.ts
      │     ├─ child.css
      │     ├─ moneyon.css
      │     └─ banking.css
      └─ lib/
         ├─ access.ts
         └─ moneyonCoach.ts
```

합계: 루트 6개 + api 4개 + services 9개 + web 21개 = **40개**. HF가 자동 생성하는 `.gitattributes`는 그대로 두어도 된다.

`access.py`, `config.py`, `supabase_auth.py`는 기존 금융 API 모듈의 import를 위한 공용 코드다. 설정값이나 자격증명을 포함하지 않는다. `space_app.py`는 체험 라우터만 등록하며, 실제 가족·관리자·Supabase 조회 라우터는 등록하지 않는다. 해당 함수 정의가 들어 있다는 이유로 운영 API가 공개되는 것은 아니다. 운영 API 경로의 404를 별도 검증했다.

## 2. Hugging Face 웹 직접 업로드 — 우선 방법

1. 네트워크 로그인 차단이 해제된 후 기존 계정으로 HF 웹에 직접 로그인한다.
2. [Create new Space](https://huggingface.co/new-space)에서 **소유자: 본인 계정**, **이름: `moneyon-demo`**, **SDK: Docker**, **공개 여부: Public**을 선택한다. 기존 AI LAB Space는 열어 수정하지 않는다. Docker 템플릿 선택이 있으면 빈 Docker 구성을 사용한다. 하드웨어 요금은 생성 화면에서 확인한다.
3. 새 `소유자/moneyon-demo`의 **Files / Files and versions → Add file → Upload files**를 연다. HF 공식 문서는 이 웹 파일 추가 경로를 안내한다.
4. `moneyon-huggingface-web.zip`을 PC에서 압축 해제한다. 그 안의 루트 파일 6개와 `api`, `services`, `web` 폴더의 내용물을 올린다.
5. 폴더 드래그를 지원하는 화면에서는 파일과 폴더를 함께 드래그하되, **커밋 전 업로드 목록의 상대 경로**를 확인한다. 예: `web/package.json`, `api/moneyon_trial.py`. `huggingface-upload/web/...`나 모든 파일이 루트로 펼쳐진 구조면 커밋하지 않는다.
6. 브라우저가 폴더 업로드·경로 보존을 지원하지 않으면 저장소의 대상 디렉터리에서 파일을 추가하는 웹 UI를 사용하거나, 아래의 GitHub 대안으로 전환한다. 모든 디렉터리에 파일을 하나씩 재작성할 필요는 없다.
7. 루트 `Dockerfile`과 `README.md`는 반드시 이 패키지의 것으로 저장한다. HF가 생성한 기본 README를 그대로 두지 않는다. 패키지 README에는 `sdk: docker`, `app_port: 7860`이 있다.
8. 파일 목록을 `UPLOAD_FILES.txt`와 비교한 후 사용자가 직접 Commit changes를 누른다. 첫 Docker 빌드는 필수 파일이 모두 올라온 뒤 확인한다. 분할 업로드 중의 일시적 빌드 실패는 최종 전체 업로드 후 다시 확인한다.
9. Space의 **Logs → Build / Container**에서 성공과 실행 상태를 확인한다. `/api/health`가 `service: moneyon-trial`, `family_api: false`를 반환하는지 확인한다.

웹 로그인과 직접 파일 업로드에는 API 토큰을 발급할 필요가 없다. 기존 네트워크 차단은 이 방식에서도 먼저 해제되어야 하며, 이 안내는 차단을 우회하는 방법이 아니다.

## 3. 설정 확인

패키지 Dockerfile을 확인했다. Space Settings에서 별도로 바꾸지 않으면 다음 기본값이 적용된다.

| 설정 | 확인한 값 |
| --- | --- |
| README SDK / 외부 포트 | `docker` / `7860` |
| 화면 빌드 | Node 22, `npm ci`, `npm run build`, Next 정적 export |
| `STATIC_EXPORT` | 빌드 단계 `1` |
| `NEXT_PUBLIC_API_URL` | 빌드 단계 **빈 문자열**. 같은 Space의 상대 경로 `/api/...` 사용 |
| `NEXT_PUBLIC_MONEYON_EPHEMERAL` | 빌드 단계 `1` |
| `MONEYON_TRIAL_ENABLED` | 런타임 **`1`** |
| `APP_ENV` | `production` |
| `MONEYON_LOCAL_DEV`, `MONEYON_DEMO` | `0`, `0` |
| `MONEYON_TRIAL_DB` | `/home/user/app/runtime/trial.sqlite3` |
| 실행 | Python 3.12, UID 1000, Uvicorn 1 worker, `0.0.0.0:7860` |
| DB 디렉터리 | UID 1000 쓰기 권한 생성 |
| Space Secrets | **추가할 항목 없음** |

필요하면 Space Settings → Variables에 `MONEYON_TRIAL_ENABLED` = `1`을 명시해도 된다. `0`으로 덮어쓰면 체험 API가 비활성화된다. 운영 DB 키·실제 은행 키·부모 계정·개인정보·AI 키를 넣지 않는다. `HF_TOKEN`도 Space 런타임에 넣지 않는다.

Space 기본 디스크가 사라지면 체험 데이터도 없어질 수 있다. 같은 탭 새로고침은 원장을 이어 읽지만, 재배포·컨테이너 재생성 후에는 새 체험으로 시작할 수 있다. 24시간은 토큰의 최대 유효기간이며 영속 보존 약속이 아니다.

## 4. GitHub Actions 대안 — 새 MONEY 전용 저장소만 사용

수동 업로드에서 경로 보존이 어렵거나 이후 동기화를 원할 때 사용한다. **기존 AI LAB GitHub 저장소에 이 패키지를 덮어쓰거나 기존 배포 workflow를 수정하지 않는다.** 새 전용 저장소 예: `moneyon-space-deploy`를 만든다.

### GitHub 웹에서 파일 등록

1. GitHub 웹에서 새 저장소를 만든다. 기존 AI LAB 저장소와 구분되는 이름을 사용한다.
2. `moneyon-github-web.zip`을 로컬에서 압축 해제한다.
3. 새 저장소 **Add file → Upload files**에서 압축 내부의 파일·폴더를 루트에 업로드한다. 기본 앱 파일 40개에 아래 3개가 추가된 **43개**다.

```text
.github/workflows/deploy-moneyon.yml
tools/sync_moneyon.py
tools/check_moneyon_space.py
```

4. `.github`를 빠뜨리지 않는다. 루트 `Dockerfile`과 `.github/workflows/deploy-moneyon.yml`이 보이는지 확인한다. 기본 브랜치에 workflow가 등록되어야 Actions 목록에서 수동 실행할 수 있다.

이 GitHub 패키지의 `.dockerignore`에는 제어용 `.github/`, `tools/` 제외 규칙이 추가되어 있다. manifest도 그 파일의 해시를 기록한다. 앱 소스는 HF 웹 패키지와 같다. GitHub 제어용 세 파일은 HF로 동기화하지 않는다.

### 토큰 발급과 직접 등록

1. 사용자가 HF 웹 **Settings → Access Tokens**에서 전용 토큰을 만든다. 가능한 경우 fine-grained 토큰으로 **본인이 만든 `moneyon-demo` 저장소의 읽기·쓰기만** 허용한다. 기존 AI LAB이나 다른 Space 접근 권한은 추가하지 않는다. 토큰 이름은 예를 들어 `moneyon-github-deploy`로 지정한다.
2. 토큰은 HF 화면에서 복사하여 **새 MONEY GitHub 저장소**의 **Settings → Secrets and variables → Actions → New repository secret**에 직접 붙여 넣는다.
3. Secret 이름은 **`MONEYON_HF_TOKEN`**이다. 기존 AI LAB이 사용하는 `HF_TOKEN` Secret을 바꾸지 않는다.
4. 같은 화면의 **Variables → New repository variable**에 **`MONEYON_HF_SPACE`** = **`실제소유자/moneyon-demo`**를 등록한다. 이 값에는 URL이 아니라 저장소 ID를 넣는다.
5. Settings → Environments에서 **`moneyon-production`**을 만든다. 원하면 required reviewers를 설정해 업로드 직전 사람이 검토하게 할 수 있다. 저장소 Secret/Variable은 이 job에서도 사용한다.

**토큰을 Codex 대화창·소스코드·README·Space 환경변수·명령어 인자에 입력하지 않는다.** 사용자가 직접 HF 웹에서 발급하고 GitHub Secrets에 넣는다. 로컬 CLI 로그인과 로컬 `HF_TOKEN` 설정은 필요 없다.

### 실행·보호 장치

1. GitHub **Actions → Deploy MONEY only to existing Docker Space → Run workflow**를 사용자가 직접 누른다.
2. push나 일정에 의한 자동 실행은 없다. `workflow_dispatch`만 있다.
3. 첫 job은 manifest 확인 → Docker build → 임시 컨테이너 → 샘플·격리·초기화 smoke test를 수행한다. 성공해야 업로드 job이 실행된다.
4. 업로드는 새 Secret `MONEYON_HF_TOKEN`을 환경변수로만 읽는다. CLI 로그인은 하지 않는다.
5. 대상 ID가 로그인 토큰의 본인 계정 **`소유자/moneyon-demo`**인지, **이미 생성된 Docker Space**인지 검사한다. 조직 소유 Space는 현재 이 보호 규칙에서 허용하지 않는다.
6. 기존 Space에 예상하지 못한 다른 앱 파일이 있으면 중단한다. HF 자동 `.gitattributes`는 허용한다. 새 Docker 템플릿에 `app.py` 등 불필요한 파일이 있으면 임의 삭제하지 않고 원인을 먼저 확인한다.
7. manifest에 적힌 **40개 파일만** 업로드한다. 다른 파일 삭제, Space 생성, 설정·Secrets 변경, 하드웨어 변경은 하지 않는다. 기존 AI LAB은 이 경로에 포함되지 않는다.

소스 파일을 나중에 바꾸면 새 패키지를 생성해 manifest도 함께 갱신해야 한다. 파일 해시가 다르면 업로드를 거절한다.

## 5. 검증과 아직 수행하지 않은 작업

- 웹 ZIP의 파일 40개·루트 구조·정확한 목록 일치 검사 통과.
- GitHub ZIP 43개·제어 파일 분리·동기화 대상 40개 검사 통과.
- 다른 Space·다른 소유자·Docker 아닌 Space·예상 외 원격 파일·변경된 원본 거절 검사 통과.
- 위 신규 오프라인 검사 **7개 통과**. 실제 HF·GitHub API 호출 없이 실행했다.
- 기존 Phase 5 검증: Python 219개, UI 28개, 동일 주소 Chrome 14개 시나리오, Next 정적 프로덕션 빌드가 이전 작업에서 통과했다. 이번에는 금융·화면 코드를 변경하지 않았다.
- `MONEYON_TRIAL_ENABLED=1`, `sdk: docker`, `app_port: 7860`, UID 1000 DB 쓰기 경로를 패키지에서 확인했다.
- 로컬 Docker 실행기는 없어 Docker 이미지 실실행은 여전히 미검증이다. 준비한 Actions의 첫 job이 그 검사를 수행하지만 아직 실행하지 않았다.
- 원격 Space 생성·업로드·GitHub 등록·토큰 발급·workflow 실행·기존 AI LAB 변경은 **하지 않았다**.

## 6. 업로드 후 확인할 항목

예상 일반 앱 URL은 `https://실제소유자-moneyon-demo.hf.space/`이며 정확한 주소는 생성된 Space에서 확인한다. 아직 실제 URL은 발급·확인하지 않았다.

1. Space build 성공, Running 상태와 `/api/health` 확인.
2. 공개 URL에서 PIN 없이 ‘바로 체험하기’, 통장 28,500원·저금통 15,000원·예상 보상 800원 확인.
3. 용돈 받기·소비·저축·가상 날짜와 보상 승인·초기화 확인.
4. 서로 다른 브라우저의 거래와 초기화가 섞이지 않는지 확인.
5. 375px·768px·1440px 화면, 새로고침 유지와 서버 재생성 후 재시작 안내 확인.

## 7. 패키지 재생성

소스가 바뀌었을 때만 새 출력 경로로 재생성한다. 로컬 HF CLI와 인증 없이 파일만 만드는 명령이다.

```powershell
.venv/Scripts/python.exe -m scripts.prepare_moneyon_web_upload --output reports/moneyon-web-upload-v2
```

공식 안내: [HF 웹 파일 추가](https://huggingface.co/docs/hub/repositories-getting-started#adding-files-to-a-repository-web-ui), [GitHub Actions로 Space 동기화](https://huggingface.co/docs/hub/spaces-github-actions), [Docker Space 설정·환경변수](https://huggingface.co/docs/hub/spaces-sdks-docker).
