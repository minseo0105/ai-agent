# 성능 기준점 — 개선 전

측정일: 2026-10-23. 코드 수정 없이 측정만 했고, 이후 개선 효과를 비교하기 위한 기준값입니다.

> **정정 (2026-10-23 추가 측정 후):** 아래 1~3절의 '압축 없음 / 캐시 헤더 없음'은 **측정에 쓴 브랜치(`codex/zipon-refresh-review-phase2`, `main`보다 36커밋 뒤처짐)의 결과**입니다. `main`의 `api/main.py`에는 이미 `GZipMiddleware`와 `/_next/static` 1년 `immutable` 캐시가 있고, 실제 HF(커밋 `1c46cef`)도 둘 다 적용된 상태입니다(4절). 즉 이 기준점은 **운영 환경의 개선 전이 아니라 '뒤처진 브랜치'의 값**이며, 전송량 비교는 4절의 HF 값을 쓰세요.

## 측정 조건 (비교할 때 같은 조건으로)

- 이 PC(Windows 10), `.venv` Python 3.12, `uvicorn api.main:app --host 127.0.0.1` (Caddy·Docker 없음, 로컬 루프백)
- 브랜치 `codex/zipon-refresh-review-phase2` (main보다 36커밋 뒤, 11커밋 앞)
- 화면은 기존 `web/out`(정적 빌드, 2026-10-23 11:23 빌드)을 FastAPI가 제공. **소스 최신본으로 다시 빌드한 것이 아님**
- 브라우저: 앱 내장 브라우저, 첫 방문(해당 포트에서 캐시 없음), 한 번 측정. API는 curl 10회
- Supabase 등 외부 키 없음(`/api/ready`는 `not_ready`) — 키가 있으면 시작·응답 시간이 달라질 수 있음
- 로컬 루프백이라 **네트워크 지연이 0에 가깝다.** 실제 서버(오라클/HF)에서는 전송 시간이 훨씬 길어진다.

## 1. 서버 시작 시간 (uvicorn 실행 → `/api/health` 200)

| 회차 | 시간 |
|---|---|
| 1 | 3.49초 |
| 2 | 3.90초 |
| 3 | 2.82초 |

대략 **3~4초**(프로세스 시작 전에 파일 캐시가 데워진 상태). 컨테이너/ARM에서 첫 기동은 더 길 수 있음.

## 2. 첫 페이지(`/`) 로딩

브라우저가 실제로 받은 항목:

| 지표 | 값 |
|---|---|
| 첫 응답 바이트(TTFB) | 59ms |
| DOMContentLoaded | 493ms |
| load | 496ms |
| 요청 파일 | **12개** = HTML 1 + 로컬 JS/CSS 10 + 외부 CDN CSS 1 (이 밖에 API 2건, 3번) |
| 전송량(합계) | 약 **730KB** (로컬 728KB + CDN 13KB) |
| 압축 | **없음 (이 브랜치 한정, main/HF는 있음)** (`Accept-Encoding: gzip`을 보내도 `Content-Encoding` 없음, 전송 크기 = 원본 크기) |
| 캐시 헤더 | **없음 (이 브랜치 한정, main/HF는 있음)** (`/_next/static/*`에도 `Cache-Control` 없음) |

참고: 전체 정적 빌드(`web/out`)는 파일 94개, 1,517,747바이트(약 1.45MB). 첫 화면에 필요한 건 그중 일부.

### 첫 페이지 요청 중 큰 파일 상위 10 (원본 크기 기준)

| 순위 | 파일 | 크기 |
|---|---|---|
| 1 | `/_next/static/chunks/1xmwz_0_wbv6z.js` | 229,156 B |
| 2 | `/_next/static/chunks/1eh83f1trsv72.js` | 165,160 B |
| 3 | `/_next/static/chunks/0j2n4cw82bs09.js` | 141,388 B |
| 4 | `/_next/static/chunks/2haugyfbwi_ot.css` | 64,208 B |
| 5 | CDN `pretendardvariable-dynamic-subset.min.css` (jsdelivr) | 53,513 B (전송 12,493 B, CDN이 압축) |
| 6 | `/_next/static/chunks/248zyuox27atv.js` | 34,073 B |
| 7 | `/_next/static/chunks/2ul8ophnk13y-.js` | 28,907 B |
| 8 | `/_next/static/chunks/3gqe_k251jcnm.js` | 25,688 B |
| 9 | `/` (index.html) | 12,430 B |
| 10 | `/_next/static/chunks/2pnts6qxyvohm.css` | 12,282 B |

상위 3개 JS만 535KB로 첫 화면 전송량의 약 73%.

## 3. 첫 화면에서 호출하는 API

| 호출 | 시작 시점 | 브라우저 측정 | 서버 로그 | curl 10회 (최소/중앙/최대) |
|---|---|---|---|---|
| `GET /api/access/status` | 페이지 로드 직후(~517ms) | 6ms (응답 547B) | 2.7ms | 2.7 / 4.2 / 5.3ms |
| `POST /api/analytics/events` | 약 2.1초 뒤 | 14ms (204, 본문 없음) | 9.6ms | (POST라 curl 미측정) |

- 첫 화면 렌더에 필요한 API는 `access/status` 한 건이고, `analytics/events`는 화면과 무관한 사용 기록 전송.
- `/` 자체 응답은 curl 4.8 / 5.7 / 8.4ms.
- 로컬에서는 모두 한 자릿수~십수 ms라 병목이 아님. 비교 지점은 **전송량(730KB, 무압축, 캐시 없음)** 과 **원격 서버에서의 왕복**.

## (구) 개선 후보 — 4·5절로 대체됨

- 정적 파일 압축 없음 → gzip/br 적용 시 JS·CSS 대폭 감소 예상. Caddy를 쓰면 `encode`가 이미 켜져 있음(Caddyfile). 앱을 직접 노출하는 HF에서는 없음.
- `/_next/static/*`에 `Cache-Control: immutable` 없음 → 재방문 시 재다운로드.
- 큰 JS 3개(535KB)의 분할/지연 로딩 여부는 번들 구성 확인 필요.
- 서버 시작 3~4초는 import 비용으로 추정(프로파일 미실시).

## 측정 방법 재현

```bash
# 시작 시간: uvicorn 실행 직후부터 /api/health 200까지 (50ms 간격으로 확인)
# 첫 페이지: 서버를 띄우고 브라우저에서 / 열기 -> performance.getEntriesByType('resource')
# API: curl -s -o /dev/null -w "%{time_total}\n" http://127.0.0.1:<port>/api/access/status
```

## 4. 허깅페이스 실제 주소 (https://minseo2-digital-ai-lab.hf.space/)

2026-10-23 오후, 이 PC에서 `curl` GET만 사용. `/api/health` 기준 HF 실행 커밋 `1c46cef`, 가동 약 48시간(잠들어 있지 않음).

### 4-1. 첫 페이지 HTML 5회 (`Accept-Encoding: gzip`)

| 회차 | DNS | TCP | TLS 완료 | **TTFB** | 전체 | 크기 |
|---|---|---|---|---|---|---|
| 1 | 0.12s | 0.36s | 1.03s | **1.29s** | 1.29s | 3,253B |
| 2 | 0.01s | 0.25s | 0.76s | **1.04s** | 1.04s | 3,253B |
| 3 | 0.02s | 0.27s | 0.76s | **1.04s** | 1.04s | 3,253B |
| 4 | 0.02s | 0.26s | 0.73s | **0.98s** | 0.98s | 3,253B |
| 5 | 0.02s | 0.25s | 0.72s | **0.96s** | 0.96s | 3,253B |

- TTFB 약 **1.0초**(0.96~1.29). 그중 TCP+TLS 연결이 약 0.75초, 서버 응답 대기는 약 0.25초. 즉 HTML은 서버 처리보다 **지리적 거리/연결 수립** 비중이 큼(이 PC↔HF 서버 왕복이 길다).
- 로컬(루프백) TTFB 59ms, `/` 5.7ms와 비교하면 약 15~20배. 개선해도 연결 비용은 남는다.
- 이 값은 한 PC·한 시각의 값이라 시간대·회선에 따라 달라짐.

### 4-2. 첫 페이지가 참조하는 JS/CSS 10개 (각각 별도 요청, curl)

| 지표 | 값 |
|---|---|
| 원본 합계 | 811,744B |
| 전송 합계(gzip) | **241,258B** (원본의 약 30%) |
| 응답 헤더 | 전부 `content-encoding: gzip`, `cache-control: public, max-age=31536000, immutable` |
| 파일별 TTFB | 0.95~1.04s (새 연결 기준, 파일마다 curl을 따로 호출했기 때문) |
| 가장 큰 파일 | `1xmwz_0_wbv6z.js` 229,156B -> 71,526B 전송 |

브라우저는 연결을 재사용(HTTP/2)하므로 파일별 TTFB를 합산하면 안 됨. **브라우저 기준 전체 로딩 시간은 아직 못 쟀습니다.** 아래 방법으로 재 주세요.

### 4-3. 직접 재는 방법 (브라우저)

1. Chrome에서 시크릿 창으로 HF 주소를 연다(캐시 없는 첫 방문).
2. F12 -> Network 탭 -> "Disable cache" 체크 해제 상태에서 새로고침(Ctrl+Shift+R은 캐시 무시이므로 첫 방문 값).
3. 아래 Network 요약줄의 `Finish`(전체 완료), `DOMContentLoaded`, `Load`와 전송량(`transferred`)을 기록. 두 번째 방문은 일반 새로고침(F5)으로 재서 캐시 효과를 본다(JS/CSS가 `(disk cache)`로 나와야 함).
4. 더 정확히는 Lighthouse 탭 -> Mobile, Performance 한 번 실행.

### 4-4. HF에서 압축·캐시가 효과가 있는가

- **이미 적용되어 동작 중**입니다. HF 응답 헤더로 확인: HTML/JS/CSS 모두 gzip, `/_next/static/*` 1년 `immutable`.
- 코드 출처: `main:api/main.py` — `GZipMiddleware(minimum_size=500)`(SSE와 이미지는 Starlette가 기본 제외), `NextAssets(StaticFiles)`가 `static/` 아래만 `immutable` 부여(해시 파일명이라 안전).
- HF 앞단(프록시)이 압축하는지 앱이 하는지는 이 측정만으로 구분 못 함. 어느 쪽이든 `main`의 앱 레벨 설정이 있으므로 **HF가 아닌 환경(오라클 VM + Caddy)에서도 동일하게 동작**. Caddy는 `encode zstd gzip`까지 있어 이중 압축이 되지는 않는다(Caddy는 이미 `Content-Encoding`이 있는 응답은 다시 압축하지 않음).
- 따라서 '압축/캐시를 HF에서도 효과 있게 적용'하는 추가 작업은 없고, **이 브랜치에 main을 반영하는 것**이 전부입니다(5절 1번).
- 주의: HF 실행 커밋 `1c46cef`은 이 PC의 저장소에서 찾을 수 없었음(원격 fetch 안 함). main에 이미 포함된 커밋인지는 미확인.

## 5. 배경 제거(rembg) 첫 호출 vs 이후 (로컬, 2026-10-23)

방법: 새로 띄운 서버(7872)에 `POST /api/gif/preview`, `remove_bg=true`, 이미지 `car_images_real/carnival_black.jpg`(34,603B). 같은 이미지 3회. HF 운영 서버에는 이미지를 보내지 않았음.

| 호출 | 응답 시간 | 출력 |
|---|---|---|
| 1번째 | **20.40초** | 52,994B |
| 2번째 | 0.26초 | 52,994B |
| 3번째 | 0.24초 | 52,994B |
| 참고: `remove_bg=false` | 0.18초 | |

- **첫 호출만 느립니다(약 80배).** 서버 시작 시에는 rembg를 불러오지 않고(`/api/health` 200까지 3~4초), 첫 배경 제거 요청에서 처음 불러오는 **지연 로딩 구조**입니다. `services/gif_maker.py`의 `_rembg_session()`이 전역 `_session`이 `None`일 때만 `from rembg import new_session` -> `new_session('u2net')`을 실행하고 이후 재사용합니다.
- 별도 프로세스로 쪼개 보면: `import rembg` 7.7초 + `new_session('u2net')` 1.4초 = 약 9초(파일 캐시가 데워진 뒤). 서버 첫 호출의 20.4초는 디스크 캐시가 차가웠고 첫 추론 워밍업이 포함된 값으로 보이며, 정확한 분해는 안 했음. **import 비용이 가장 크다.**
- 모델 파일은 로컬 `.rembg/models/u2net`에 이미 있어 다운로드는 아님. Dockerfile의 `RUN python -c "from rembg import new_session; new_session('u2net')"`는 **다운로드만 미리 해 두는 것**이라 첫 호출의 import/세션 생성 시간은 그대로 남습니다. HF에서도 같은 지연이 있을 가능성이 높지만 **HF에서는 측정하지 않음**.
- 같은 서버에서 메모리 증가는 이 측정 방식(런처 프로세스만 잡힘)으로는 못 쟀음. 코드 주석상 u2net은 약 650MB를 추가 사용.
- 사용자 영향: 서버가 재시작된 뒤 첫 사용자가 20초 가까이 기다림. 프록시/화면 타임아웃이 이보다 짧으면 첫 요청이 실패할 수 있음(타임아웃 값은 미확인).

## 6. 개선 후보 (위험 낮은 순, 아직 하나도 하지 않음)

| 순서 | 후보 | 기대 효과 | 위험 / 비용 |
|---|---|---|---|
| 1 | 이 브랜치에 `main` 반영(머지/리베이스)해서 GZip·immutable 캐시 상태로 기준점 다시 측정 | 이 브랜치의 전송량이 HF 수준(약 30%)으로 | 코드 수정 아님. 36커밋 차이라 충돌 가능, 이 작업 폴더에 다른 변경이 있어 별도 브랜치/worktree에서 확인 권장 |
| 2 | 배경 제거 첫 호출 안내 문구 + 타임아웃 확인 (프론트/프록시 20초 이상 허용인지) | 첫 사용자 실패·이탈 방지 | 매우 낮음. 문구/설정만 |
| 3 | 오라클 배포에서 Caddy 응답 헤더 확인(압축 이중 적용·캐시 헤더 통과) | 배포 후 회귀 방지 | 낮음. 점검만, 실제 서버가 생긴 뒤 |
| 4 | rembg 선로딩: 서버 시작 직후 백그라운드 스레드에서 import + `new_session` 실행 | 첫 호출 20초 -> 약 0.3초(시작은 막지 않음) | 낮음~중간. 시작 직후 메모리 +650MB를 상시 점유해 1GB급 VM엔 부적합(그땐 `REMBG_MODEL=silueta`/`u2netp`로 낮춰야 하며 품질 차이 미측정). HF 16GB는 여유 |
| 5 | 서버 시작 3~4초 단축: import 프로파일 후 무거운 모듈 지연 로딩 | 시작·재시작 시간 | 중간. 프로파일 선행 필요, 지연 로딩이 첫 요청으로 비용을 옮길 수 있음 |
| 6 | 큰 JS 3개(합 535KB) 분할/지연 로딩 | 첫 화면 전송량 | 중간~높음. 프론트 구조 변경, 시각 회귀 검증 필요 |

HTML 응답 TTFB(약 1초)의 대부분은 연결 수립이라 위 후보로 줄지 않습니다. 줄이려면 사용자와 가까운 서버(오라클 서울/춘천 리전 등)로 옮기는 것이 유일한 방법이며, 이전 후 같은 방법으로 다시 재서 비교하면 됩니다.
