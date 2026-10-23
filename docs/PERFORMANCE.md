# 성능 기준점 — 개선 전

측정일: 2026-10-23. 코드 수정 없이 측정만 했고, 이후 개선 효과를 비교하기 위한 기준값입니다.

## 측정 조건 (비교할 때 같은 조건으로)

- 이 PC(Windows 10), `.venv` Python 3.12, `uvicorn api.main:app --host 127.0.0.1` (Caddy·Docker 없음, 로컬 루프백)
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
| 압축 | **없음** (`Accept-Encoding: gzip`을 보내도 `Content-Encoding` 없음, 전송 크기 = 원본 크기) |
| 캐시 헤더 | **없음** (`/_next/static/*`에도 `Cache-Control` 없음) |

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

## 개선 후보 (아직 하지 않음, 측정 근거만)

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
