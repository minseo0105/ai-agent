# ZIP:ON 운영 반영 절차(작업 A)와 자동 갱신 정상화 설계(작업 B) — 2026-11-07

## A-1. 배포 전 확인할 수 없는 것 (명시)
- 운영 서버 `.env.docker`의 `PUBLIC_DATA_API_KEY`·`NAVER_MAP_CLIENT_ID` 존재 여부, 네이버 콘솔 Web 서비스 URL에 `wai-labs.com` 등록 여부, 실제 NAVER 지도 SDK 동작, 실제 Supabase 응답시간. 이 세션은 서버·키·운영 도메인에 접근할 수 없다.

## A-2. 배포 직후 검증 절차 (10분, 읽기만)
1. `https://wai-labs.com/api/health` 200, `/api/map/config`가 지도 ID **존재 여부**만 응답하는지(값은 공유하지 않음).
2. `/realestate` 개발지도: 실제 네이버 지도 타일·마커가 보이는지, 헤더가 "954건 중 638건 지도 표시"인지.
3. '완료사업 보기' → "1,190건 중 849건", 끄면 다시 954건.
4. 상태 미확인 사업 하나 선택 → "표시 단계 … 공식 원문 …" 노출, 사업정보 탭에 "단계 정보 수집일 / DB 반영일(대부분 '미기록')".
5. 실거래 탭: 상단 네이버 버튼 1개(새 탭), 거래 표 또는 상태 문구(미연동/403/거래 없음/조회 실패) 중 하나.
6. 서버 로그에서 `{"event":"zipon_map", "cache": "MISS"…}` 다음 요청 `"HIT"` 확인, `ms`·`db_calls` 기록.
7. 브라우저 콘솔 오류 없음. 실패 시 아래 복구 절차.

## A-3. 이전 배포 버전으로 복구
- 배포 방식이 서버에서 `git pull --ff-only` 후 `docker compose build ailab && up -d --no-deps ailab`이므로:
  1. 배포 전 서버에서 현재 커밋을 기록: `git rev-parse HEAD` (예상: 9ba5447 또는 그 이후 main).
  2. 이상 시 main에서 PR #2 병합 커밋을 `git revert -m 1 <병합커밋>`으로 되돌리는 PR을 만들어 병합 → "Deploy to Oracle" 버튼 재실행(이력 보존, 강제 푸시 없음).
  3. 긴급 시 서버에서 `git checkout <기록한 커밋>` 후 같은 compose 명령으로 재빌드(임시 조치, 이후 main을 revert로 맞춘다).
- DB 스키마·데이터 변경이 없으므로 DB 복구는 필요 없다.

## B. 자동 갱신 정상화 설계 (구현 전, 별도 승인)
1. **판정 체계**: `services/development_refresh.py`의 상태 계산(현재 `failed=any(...) or bool(errors)`)을 다음으로 교체.
   - 필수 소스 = 정보몽땅 자치구 목록 25 + 신속통합 재개발·재건축 2. 선택 = seoul_moa, 공지, official_detail, SHP.
   - FAILURE: 필수 소스 실패 / RPC·DB 오류 / 공식 ID 중복 등 무결성 오류 / 대량 변경(변경 > max(60, 전체 5%) 또는 종료·해제 판정 > 10).
   - WARNING: 선택 소스 실패, NO_CURRENT_STAGE. SUCCESS: 그 외. 종료코드 FAILURE만 1.
   - `report['errors']`는 그대로 보존하고 `report['warnings']`, `report['status_reason']`을 추가.
2. **이월**: `WRITE_BUDGET_DEFERRED`를 errors에 넣지 않고 `report['counts']['deferred']`로 집계. 다음 실행이 같은 후보를 다시 처리하므로 데이터 손실 없음.
3. **검토 큐**:
   - 기록 상한: 실행당 `review_limit`(기본 200)으로 제한하고 초과분은 `counts.review_deferred`.
   - 중복·누적: 같은 `candidate_key`의 PENDING 행이 있으면 새 해시 행 추가 대신 `superseded_by`로 이전 행을 표시(마이그레이션 필요: `superseded_at`, `decided_by`, `decided_at`, `decision_note`).
   - 승인·거절: 관리자 전용 API(`/api/admin/zipon/review/{id}` PATCH, `state` APPROVED/REJECTED만 허용)와 감사 기록. APPROVED는 해당 후보를 다음 실행에서 반영 대상으로만 표시(자동 즉시 쓰기 아님).
4. **변경 없는 사업의 확인 이력**: `development_projects`를 건드리지 않고 별도 테이블 `development_source_checks(project_id, source_url, content_hash, checked_at, run_id)`에 "확인했고 변화 없음"을 기록(하루 1행/사업, upsert). 화면의 신선도는 이 테이블의 최신 `checked_at`을 "공식 목록 확인일"로 쓰고, DB 반영일·단계 정보 수집일과 구분 표시.
5. 재개 순서: 위 1~2 구현·테스트 → dry-run → apply limit=10 → 결과 검증 2일 → `ZIPON_CANARY_VERIFIED`, `ZIPON_REFRESH_ENABLED` 순서로 활성화. 중단 기준: FAILURE 1회 또는 대량 변경 감지 시 변수 끄기.
