-- ZIP:ON 1차 대시보드 정합성 점검 — 읽기 전용(SELECT만).
-- READ ONLY 트랜잭션이라 실수로 INSERT/UPDATE/DDL이 섞여도 DB가 거부한다. 쓰기 RPC는 호출하지 않는다.
-- Supabase SQL Editor에서 한 블록씩 실행해도 된다. 기대값은 2026-11-06 canary dry-run 기준이며,
-- 일일 갱신이 쓰면 달라질 수 있다. "기대값과 다르면 오류"가 아니라 "왜 다른지 설명이 필요한 지점"이다.
BEGIN TRANSACTION READ ONLY;

-- [1] 개발사업 전체 / 좌표 / 경계 / 검증.  기대: projects=1190, locations=849, verified_boundaries=0, verified_projects=0
SELECT count(*)                                         AS projects,
       count(DISTINCT project_id)                       AS distinct_ids,
       count(*) FILTER (WHERE location IS NOT NULL)     AS locations,
       count(*) FILTER (WHERE location IS NULL)         AS no_location,
       count(*) FILTER (WHERE geometry IS NOT NULL)     AS has_geometry,
       count(*) FILTER (WHERE geometry_verified)        AS verified_boundaries,
       count(*) FILTER (WHERE validation_status='VERIFIED') AS verified_projects
FROM public.development_projects;

-- [2] 정합성 위반 후보.  기대: 전부 0 (CHECK 제약이 막는 항목이지만 실제 데이터로 한 번 더 본다)
SELECT
  count(*) FILTER (WHERE geometry_verified AND (geometry IS NULL OR geometry_verified_at IS NULL OR canonical_source_id IS NULL)) AS verified_without_evidence,
  count(*) FILTER (WHERE geometry IS NOT NULL AND NOT geometry_verified)      AS unverified_geometry_rows,
  count(*) FILTER (WHERE location IS NOT NULL AND (location_source IS NULL OR btrim(location_source)='')) AS location_without_source,
  count(*) FILTER (WHERE sigungu IS NULL OR btrim(sigungu)='')                AS no_sigungu,
  count(*) FILTER (WHERE stage IS NOT NULL AND canonical_source_id IS NULL)   AS stage_without_source
FROM public.development_projects;

-- [3] 중복.  기대: 두 쿼리 모두 0행
SELECT project_id, count(*) FROM public.development_projects GROUP BY project_id HAVING count(*)>1;
SELECT official_authority, external_id, count(*) FROM public.development_projects
WHERE external_id IS NOT NULL GROUP BY official_authority, external_id HAVING count(*)>1;

-- [4] 상세 이력(타임라인) 보유.  화면의 타임라인은 field_evidence.official_stage.milestones 또는
--     저장소의 development_stage_catalog.json(패키지, 130건 중 119건 유효)에서 온다. DB 쪽만 센다.
--     패키지 쪽 기대값은 `python scripts/checks/zipon_catalog_counts.py` 로 확인한다(DB 불필요).
SELECT
  count(*) FILTER (WHERE jsonb_typeof(field_evidence->'official_stage'->'milestones')='array'
                   AND jsonb_array_length(field_evidence->'official_stage'->'milestones')>0) AS db_with_milestones,
  count(*) FILTER (WHERE field_evidence ? 'official_stage')                                   AS db_with_official_stage_block,
  count(*) FILTER (WHERE stage_mapping_version='zipon-refresh-policy-v1')                     AS refreshed_by_live_policy
FROM public.development_projects;

-- [5] 변경 이력과 출처.
SELECT (SELECT count(*) FROM public.development_updates)                         AS updates,
       (SELECT count(DISTINCT project_id) FROM public.development_updates)       AS projects_with_updates,
       (SELECT count(*) FROM public.development_project_sources)                 AS sources,
       (SELECT count(DISTINCT project_id) FROM public.development_project_sources WHERE is_official) AS projects_with_official_source;

-- [6] 수집 실행 기록(최근 10건). 대시보드의 "마지막 확인일" 근거.
SELECT run_id, started_at, finished_at, status, dry_run, source_complete,
       new_count, changed_count, unchanged_count, validation_failed_count
FROM public.development_collection_runs ORDER BY started_at DESC LIMIT 10;

-- [7] 검토 대기.  주의: "994"는 canary dry-run이 보고한 review_required 건수다. dry-run은 큐에 쓰지 않는다.
--     아래 큐 행 수가 0이어도 이상이 아니다(apply 실행 전까지 큐는 비어 있다).
SELECT to_regclass('public.development_review_queue') AS review_queue_table;
SELECT state, count(*) FROM public.development_review_queue GROUP BY state ORDER BY state;
SELECT reason, state, count(*) FROM public.development_review_queue GROUP BY reason, state ORDER BY count(*) DESC;
-- dry-run 기준 사유별 기대값(합 994): AMBIGUOUS_DATE 376, NO_OFFICIAL_IDENTIFIER 306, DUPLICATE_SUSPECTED 159,
--   STATUS_REVIEW_REQUIRED 60, IDENTITY_OR_FRAME_UNRESOLVED 50, SOURCE_MISSING 16, MOA_CANCELLATION_REVIEW 11,
--   OFFICIAL_NOTICE_REVIEW 6, PROTECTED_IDENTITY 5, PROJECT_NAME_CHANGED 5.

-- [8] 사업 유형·자치구별 좌표 보유율(2차 경계 활성화 우선순위용).
SELECT project_type, count(*) AS projects,
       count(*) FILTER (WHERE location IS NOT NULL) AS with_location,
       round(100.0*count(*) FILTER (WHERE location IS NOT NULL)/count(*),1) AS pct_location,
       count(*) FILTER (WHERE external_id IS NOT NULL) AS with_official_id
FROM public.development_projects GROUP BY project_type ORDER BY projects DESC;
SELECT sigungu, count(*) AS projects, count(*) FILTER (WHERE location IS NOT NULL) AS with_location
FROM public.development_projects GROUP BY sigungu ORDER BY projects DESC;

-- [9] 권한. 기대: 검토 큐·리스 테이블은 RLS on, anon/authenticated/PUBLIC 권한 0행
SELECT schemaname, tablename, rowsecurity FROM pg_tables
WHERE schemaname='public' AND tablename IN ('development_review_queue','development_refresh_lease','development_projects');
SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants
WHERE table_schema='public' AND table_name IN ('development_review_queue','development_refresh_lease')
  AND grantee IN ('anon','authenticated','PUBLIC');

ROLLBACK;
