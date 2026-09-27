# ZIP:ON 공식 진행단계 수집·표시

## 실제 확인 결과

대상 130개 ID는 기존 DB 적재 기록과 운영 검색 API의 세 자치구 응답에서 서로 일치한다.
변경 전 운영 검색 API는 130건 모두 `project_stage=null`을 반환했고 카드에는 모두
“공식 단계 확인 중”이 표시됐다. 원본 canonical 130건에는 목록의 진행단계가 남아 있었다.

원인:

1. 기존 ingest는 `stage_raw`를 저장하지만 공간검색 RPC는 `stage`만 반환한다.
2. UI는 RPC에 없는 `stage_raw`/진행단계 근거를 조회하지 않았다.
3. 기존 상세 파서는 표/dl만 처리했고 실제 홈페이지의 iframe 안 `.progress-cont`를 읽지 않았다.
4. 공식 용어 `철거신고`, `착공신고`, `일반분양승인`, `조합설립추진위원회승인` 매핑이 빠져 있었다.

운영 DB의 전체 행을 직접 dump한 것은 아니다. 운영 API 응답·기존 적재 기록·canonical
스냅샷·실제 SQL/코드를 교차 확인했다. 변경 전 API와 provenance는
`data/development/official_stage_audit_20260927.json`에 130건별로 보존했다.

| 항목 | 건수 |
|---|---:|
| 대상 canonical | 130 |
| 공식 홈페이지 URL 확보 | 128 |
| 사업명 및 cafeId/frame 일치 | 114 |
| 상세 현재단계 직접 추출 | 112 |
| 날짜가 있는 단계 이력 | 107 |
| 상세 확인 | 112 |
| 기존 목록 근거만 표시 | 18 |
| 목록까지 포함해 단계 없음 | 0 |

상세 미확정 18건: 홈페이지/프레임 식별 미해결 14, 상세 식별자 없음 2,
현재단계 없음 2. 비슷한 사업명으로 매칭하거나 첫 검색 결과로 연결하지 않았다.
공식 단계별 분포: 정비구역 1, 추진위 6, 조합설립 27, 사업시행 6, 관리처분 13,
철거 2, 착공 4, 일반분양 3, 준공 10, 부분준공 1, 이전고시 5, 해산 18, 청산 16.

## 수집 근거와 날짜

목록의 실제 `cafeOpenPopup`은 `/cafe/mainIndx.do?cafeUrl=<alias>`로 연결된다.
그 페이지에서 사업명과 iframe의 cafeId를 확인하고, 공식 iframe URL을 읽는다.
추정 URL의 응답이나 검색 snippet만으로 상세 확인 상태를 부여하지 않는다.
현재단계는 명시된 텍스트를 사용하고 active 마커 충돌 시 확정하지 않는다.
순서와 날짜는 해당 사업의 실제 목록에서 추출한다. 날짜 없는 과거 단계를 완료로 추정하지 않는다.
`23.02.09`는 공식 두 자리 연도 표기 그대로 보존한다. 임의로 2023/1923을 선택하지 않는다.
정규 4자리 날짜는 ISO 날짜로 저장한다. 단계 자료로 사업 상태(status)를 자동 변경하지 않는다.

원문 공개 영역, URL, HTTP status, 수집 시각, content hash를 캐시했다.
HTTP 실패/접근 차단 후 같은 호스트를 반복 호출하지 않는다. Secret/쿠키/인증 헤더는
캐시에 넣지 않는다. 캐시만으로 재파싱 가능하며, 미래 재수집은 새 날짜의 `--cache-dir`를
사용해 이전 원문을 보존한다. 이번에는 NAVER 재호출이 없었다.

## 표시 경로

공간 RPC는 그대로 두고 검색 후 읽기 전용 GET 1회로 stage_raw/field_evidence/식별자를 보강한다.
지도 기본 목록은 기존 경량 컬럼을 유지한다. 수집 결과 중 공개 표시용 최소 필드는
`services/development_stage_catalog.json`으로 배포한다. ID 기반으로만 연결하며 DB 값은 변경하지 않는다.
DB field_evidence의 더 최근 상세 근거가 있으면 그것을 우선한다.
상세 근거와 목록 근거를 구분하고 원래 프로젝트 전체의 검증 등급은 승격하지 않는다.

카드: 현재단계, 한 문장 설명, 공식 확인일/출처.
데스크톱: 가로 진행 표시. 모바일: 현재 및 인접 단계의 압축 타임라인.
상세 펼침: 날짜가 제공된 공식 진행이력과 현재단계. 내부 enum을 화면 문구로 노출하지 않는다.

## DB와 좌표 반영 경계

DB write 0, migration 0. 기존 `stage`, `stage_raw`, `field_evidence` JSON 및
`development_project_sources`, `development_updates`로 보존할 수 있으므로 새 테이블은 불필요하다.
`official_stage_apply_review_20260927.json`은 실행 불가능한 검토안이다.
실제 단계 저장 전 fresh DB snapshot/revision, canonical/source FK, 기존 JSON 병합,
이전/신규 snapshot와 revision history의 단일 트랜잭션 보장이 필요하다.
현재 ingest RPC가 verified 값을 보수적으로 보호하므로 그대로 강제 덮어쓰면 안 된다.
단계 DB 적용은 별도 승인·검토 대상이며 좌표 적용과 섞지 않는다.

좌표 122건 apply-ready 파일은 변경 없이 유지했다. 재-geocoding 및 DB 적용은 하지 않았다.
단계 표시가 개선되어도 대표좌표만으로 INSIDE를 판정하지 않는다.

## 검증

ZIP:ON 408 tests: 실패/오류 0, 2 skipped. 공식 단계 신규 테스트 14건 포함.
Next.js STATIC_EXPORT 빌드 PASS. 실제 Chrome에서 mock API로 모바일 390px 및
데스크톱 1200px의 단계·이력 표시, 모바일/데스크톱 분기, 가로 넘침 없음 확인.
공식 상세 페이지 전체 확보가 끝난 것은 아니므로 전체 데이터 확보 상태는 PARTIAL이다.
