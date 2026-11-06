# ZIP:ON 경계·실거래 읽기 전용 분석 — 실행 절차서 (예약: 2026-11-06 23:51 KST)

승인 범위: 운영 `development_projects` **SELECT만**, SHP 202609 **읽기 전용 분석**, 실거래 API **로컬 샘플링 방식**.
금지: INSERT/UPDATE/DELETE, 테이블·RLS 변경, 쓰기 RPC, 운영 마이그레이션, 배포, 서비스 적용·가공 데이터 배포·운영 DB 저장.

## 사전 점검 결과 (23:26 KST, 분석은 시작하지 않음)
| 항목 | 상태 |
| --- | --- |
| 예약 | 세션 내 예약 `trig_01SP5qXKBCf9AGzMuAakP7CZ`, 23:51 KST(14:51Z) 1회 |
| SHP 202609 | 확보(2.5MB, sha256 `7788af6b…1703`), 작업 폴더에만 있음(저장소 미포함). 열림·레코드 2,776·EPSG:5174·코드표 174행 확인 |
| 네트워크 | `data.seoul.go.kr` 200, `apis.data.go.kr` 응답(키 없이 400) |
| 분석 스크립트 | `scripts/zipon_boundary_analysis_readonly.py`(저장소 밖 출력만 허용, GeoJSON 생성 안 함), 테스트 4개 통과 |
| 실거래 키 | **이 환경에 `PUBLIC_DATA_API_KEY` 없음**(`--check-config` → false). 결과를 만들지 않고 로컬 실행 방법만 보고 |
| 운영 읽기 | 서비스 역할 키 **불필요**: Supabase MCP로 SELECT만 실행(읽기 전용 트랜잭션). 서비스 키는 사용·요청하지 않음 |

## 실행 순서
1. **운영 SELECT**(project `nnxtkvjpzqqhjlgnprzo`). 최소 컬럼, 읽기 전용 트랜잭션:
   ```sql
   BEGIN READ ONLY;
   SELECT project_id, project_name, sigungu, dong, project_type, external_id, official_authority, address,
          extensions.ST_X(location::extensions.geometry) AS lon,
          extensions.ST_Y(location::extensions.geometry) AS lat
   FROM public.development_projects ORDER BY project_id;
   COMMIT;
   ```
   결과가 크면 파일로 저장된 원문을 `--projects`에 그대로 넘긴다(스크립트가 MCP 결과 원문을 읽는다).
2. **레이어 분석**: `python scripts/zipon_boundary_analysis_readonly.py --archive <202609.zip> --out-dir <저장소 밖> --layer-only`
3. **매칭**: 같은 명령에 `--projects <1단계 결과>` 추가. 산출: `match_summary.json`, `match_rows.json`, `risk_cases.json`, `layer_profile.json`(모두 저장소 밖).
4. **실거래**: 키가 없으면 `docs/zipon_phase2_3_plan` §3.2 항목을 "미확인"으로 두고 로컬 실행 방법(`scripts/sample_molit_trade_apis.py`)만 안내.
5. **보고**: 승인된 표 9개 항목 + 추가 승인 필요 항목. 저장소에는 **집계 수치와 문서만** 커밋(SHP 파생 경계·폴리곤·행 단위 매칭 결과 제외).

## 이 분석이 하지 않는 것
- DB에 아무것도 쓰지 않는다. 경계(geometry)를 만들거나 GeoJSON으로 내보내지 않는다.
- 자동 병합·자동 승격을 하지 않는다. 오매칭 위험 사례는 보고만 한다.
