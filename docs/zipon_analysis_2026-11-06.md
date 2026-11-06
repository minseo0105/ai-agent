# ZIP:ON 분석과 수정 내역 — 2026-11-06

운영 DB·GitHub 설정에는 접근하지 않았다(이 세션에 권한 없음). 아래는 저장소 코드·문서 기준 분석이다.

## 1. 분석 요약

| 항목 | 상태 |
|---|---|
| 집온 Python 테스트 | 715개 통과, 스킵 8 (이번 변경 후) |
| 프론트 typecheck / build | 통과 |
| 지도 화면 갱신 로직 | 정상 — 탭 복귀·5분마다 재조회 |
| 데이터 수집 자동화 | **미활성** — 구현은 있으나 `CONFIG_REQUIRED + DB_MIGRATION_REQUIRED`, LIVE_VERIFIED 아님 |
| 마지막 문서화된 실제 수집 | 2026-10 초 (25개 구 1,203건 후보) |
| 검증된 폴리곤 | 0건 → "구역 안(INSIDE)" 판정 꺼짐 (의도된 안전 설정) |

**핵심 결론:** 지도에 최신 개발 내용이 안 보이는 이유는 화면 코드가 아니라 수집이 켜진 적이 없기 때문이다.
이를 켜는 단계(Supabase 마이그레이션, GitHub Secrets/변수, canary)는 운영 권한이 필요해 사용자가 직접 해야 한다.

## 2. 이번에 수정한 것

1. **데이터 신선도 표시** — `services/development_investor.py: freshness()`
   - 가장 최근 공식 확인일이 14일을 넘으면 `stale`. 날짜가 없으면 `unknown`(최신으로 보지 않음).
   - `/development/map` 응답에 `freshness`, 각 프로젝트에 `freshness` 추가.
   - 지도 탭 상단 배너와 카드의 "N일 전 확인" 배지로 표시.
2. **단계별 투자 접근 안내** — `investor_guide()`, 카드의 접이식 "이 단계에서 알아둘 점"
   - 기존 `stage_guide`는 변경하지 않았다. 확인된 사실과 섞이지 않는 별도 블록.
   - 자세한 내용은 `docs/zipon_investor_guide_2026-11-06.md`.
3. **활성화 사전점검** — `scripts/zipon_activation_preflight.py` (읽기 전용, Secret 값 미출력)

스키마·DB·검토 큐·프로젝트 ID는 바꾸지 않았다. 응답에 필드만 추가했고, 구버전 서버 응답에서도 프론트가 깨지지 않게 optional로 받는다.

## 3. 활성화 절차 (사용자 직접)

`python scripts/zipon_activation_preflight.py`로 저장소 쪽 준비를 먼저 확인한 뒤 `docs/zipon_live_refresh.md`의 3단계를 따른다.

1. **Supabase** — 읽기 전용 SQL 실행·개수 기록 → 스테이징 검증 → 마이그레이션 설치 → 비공개 버킷 `zipon-official-raw`
2. **GitHub Secrets** — `ZIPON_IMPORT_SUPABASE_URL`, `ZIPON_IMPORT_SUPABASE_KEY` (REFRESH_ENABLED·CANARY_VERIFIED는 아직 끄기)
3. **Actions** — canary dry-run(limit 1) → WRITE_ENABLED 후 apply canary → 전후 개수·이력 일치 시 CANARY_VERIFIED, REFRESH_ENABLED 켜기

활성화 후 14일 안에 새 확인일이 들어오면 지도의 주의 배너가 자동으로 사라진다.

## 4. 범위 밖으로 남긴 것

- `tests/test_frontend_ux.py`의 `ServiceGridResponsiveTests` 2건 실패: 홈 `ServiceGrid` 레이아웃 클래스를 기대하는 오래된 테스트로, 집온과 무관하며 이번 변경 전에도 실패했다.
- 5건 모호 지오코딩, 1건 실패 주소(길동진흥), 목록만 있는 11건의 상세 조사, 공식 폴리곤 확보: 기존 문서의 남은 데이터 작업 그대로.
- 의심 중복 식별자(마천2 등)는 검토 대상이며 자동 병합하지 않는다.
- 이 세션 환경에서는 `lunar_python`(사주) 빌드가 실패해 `pip install -r requirements-api.txt` 전체는 못 돌렸다. 집온 테스트에 필요한 `fastapi`, `httpx`만 설치해 검증했다.
