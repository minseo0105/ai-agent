-- NEW zipon-realestate only. Run ENTIRE file as Dashboard postgres.
-- This is a rollback-only functional test, NOT a read-only query.
-- All fixture writes use random TEST_ZIPON UUID identifiers inside a subtransaction.
-- Success AND failure roll back every fixture before returning results. No DELETE/TRUNCATE.
--
-- 확인하는 것: 경계 RPC가 검토를 통과한 값만 받고, 이미 확인된 경계는 덮어쓰지 않고,
-- 자치구가 다르거나 대표좌표가 polygon 밖이거나 서울을 벗어나면 거절하는지.
-- 그리고 반영 뒤에 좌표·단계·identity가 그대로이며 INSIDE가 그때서야 켜지는지.
BEGIN;
SET LOCAL statement_timeout='60s';
SET LOCAL lock_timeout='5s';
DO $test$
DECLARE pid uuid:=gen_random_uuid(); sid uuid:=gen_random_uuid();
 tag text; answer jsonb; results jsonb:='[]'; ok boolean; rev bigint;
 square jsonb; far jsonb; huge jsonb; evidence jsonb; relation text;
BEGIN
 tag:='TEST_ZIPON_'||pid::text;
 square:=jsonb_build_object('type','Polygon','coordinates',
   jsonb_build_array(jsonb_build_array(
     jsonb_build_array(127.126,37.540),jsonb_build_array(127.126,37.543),
     jsonb_build_array(127.129,37.543),jsonb_build_array(127.129,37.540),
     jsonb_build_array(127.126,37.540))));
 far:=jsonb_build_object('type','Polygon','coordinates',
   jsonb_build_array(jsonb_build_array(
     jsonb_build_array(129.000,35.100),jsonb_build_array(129.000,35.200),
     jsonb_build_array(129.100,35.200),jsonb_build_array(129.100,35.100),
     jsonb_build_array(129.000,35.100))));
 huge:=jsonb_build_object('type','Polygon','coordinates',
   jsonb_build_array(jsonb_build_array(
     jsonb_build_array(126.740,37.420),jsonb_build_array(126.740,37.710),
     jsonb_build_array(127.260,37.710),jsonb_build_array(127.260,37.420),
     jsonb_build_array(126.740,37.420))));
 evidence:=jsonb_build_object(
   'match_status','EXACT','auto_apply_candidate',true,
   'representative_point_inside_polygon',true,
   'source_dataset','도시계획사업 현황(서울플랜+) 공간정보','source_version','202609',
   'source_sha256',repeat('a',64),'official_name','천호1',
   'checks',jsonb_build_object('geometry_valid',true,'ring_closed',true,'crs_converted',true,
     'normalized_name_match',true,'district_match',true,'single_candidate',true,
     'not_identity_protected',true,'point_in_polygon',true));
 BEGIN
 SELECT COALESCE((to_regprocedure('public.zipon_set_project_boundary(uuid,jsonb,text,text,text,bigint,jsonb)') IS NOT NULL
   AND to_regprocedure('public.zipon_development_map(text,integer)') IS NOT NULL),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','function signatures','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT COALESCE((SELECT count(*)=2 AND bool_and(NOT p.prosecdef
   AND has_function_privilege('service_role',p.oid,'EXECUTE')
   AND NOT has_function_privilege('anon',p.oid,'EXECUTE')
   AND NOT has_function_privilege('authenticated',p.oid,'EXECUTE'))
   FROM pg_proc p WHERE p.oid IN (
     to_regprocedure('public.zipon_set_project_boundary(uuid,jsonb,text,text,text,bigint,jsonb)'),
     to_regprocedure('public.zipon_development_map(text,integer)'))),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','invoker and grants','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 INSERT INTO public.development_projects(project_id,project_name,project_type,sido,sigungu,dong,
   address,status,validation_status,official_authority,external_id,location,location_source,
   location_verified_at,last_verified_at,stage,stage_raw,stage_mapping_version)
 VALUES(pid,tag,'REDEVELOPMENT','서울특별시','강동구','천호동','서울특별시 강동구 천호동 423-200',
   'UNKNOWN','UNVERIFIED',tag,tag,
   extensions.ST_SetSRID(extensions.ST_MakePoint(127.1275,37.5415),4326)::extensions.geography,
   'NAVER_MAP_GEOCODE',now(),NULL,NULL,NULL,NULL);

 -- canonical_source_id가 없으면 verified 경계를 만들 수 없다. 거절해야 한다.
 SELECT public.zipon_set_project_boundary(pid,square,'서울특별시','https://data.seoul.go.kr/',
   '강동구',1,evidence) INTO answer;
 ok:=answer->>'reason'='NO_CANONICAL_SOURCE';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','refuses without canonical source','passed',ok,'answer',answer));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 INSERT INTO public.development_project_sources(source_id,project_id,source_name,source_type,
   source_url,is_official,validation_status,collected_at,content_hash)
 VALUES(sid,pid,tag,'OFFICIAL_WEBSITE','https://cleanup.seoul.go.kr/'||tag,true,'VERIFIED',now(),
   repeat('b',64));
 UPDATE public.development_projects SET canonical_source_id=sid,last_verified_at=now()
 WHERE project_id=pid;
 SELECT revision INTO rev FROM public.development_projects WHERE project_id=pid;

 -- 좌표가 polygon 밖이면 거절한다.
 SELECT public.zipon_set_project_boundary(pid,far,'서울특별시','https://data.seoul.go.kr/',
   '강동구',rev,evidence) INTO answer;
 ok:=answer->>'reason'='BOUNDARY_OUTSIDE_SEOUL';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','refuses a polygon outside Seoul','passed',ok,'answer',answer));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 자치구 단위 크기의 도형은 정비사업 구역이 아니다.
 SELECT public.zipon_set_project_boundary(pid,huge,'서울특별시','https://data.seoul.go.kr/',
   '강동구',rev,evidence) INTO answer;
 ok:=answer->>'reason'='BOUNDARY_AREA_IMPLAUSIBLE';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','refuses an implausible area','passed',ok,'answer',answer));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 검토 근거가 빠지면 거절한다.
 SELECT public.zipon_set_project_boundary(pid,square,'서울특별시','https://data.seoul.go.kr/',
   '강동구',rev,evidence-'checks') INTO answer;
 ok:=answer->>'reason'='BOUNDARY_CHECKS_NOT_PASSED';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','refuses without checks','passed',ok,'answer',answer));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 자치구가 다르면 거절한다.
 SELECT public.zipon_set_project_boundary(pid,square,'서울특별시','https://data.seoul.go.kr/',
   '송파구',rev,evidence) INTO answer;
 ok:=answer->>'reason'='DISTRICT_MISMATCH';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','refuses a district mismatch','passed',ok,'answer',answer));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- revision이 어긋나면 거절한다.
 SELECT public.zipon_set_project_boundary(pid,square,'서울특별시','https://data.seoul.go.kr/',
   '강동구',rev+99,evidence) INTO answer;
 ok:=answer->>'reason'='REVISION_CONFLICT';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','refuses a stale revision','passed',ok,'answer',answer));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 정상 반영. 좌표·단계·identity는 그대로여야 한다.
 SELECT public.zipon_set_project_boundary(pid,square,'서울특별시 도시계획사업 현황(서울플랜+) 공간정보',
   'https://data.seoul.go.kr/dataList/OA-22712/S/1/datasetView.do','강동구',rev,evidence) INTO answer;
 ok:=answer->>'result'='boundary_set'
   AND (answer->'geometry_verified')::boolean
   AND (answer->'location_untouched')::boolean
   AND (answer->'stage_untouched')::boolean
   AND (answer->'identity_untouched')::boolean
   AND answer->>'geometry_type'='POLYGON';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','writes a reviewed boundary','passed',ok,'answer',answer));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 같은 호출을 다시 하면 건너뛴다. 덮어쓰지 않는다.
 SELECT revision INTO rev FROM public.development_projects WHERE project_id=pid;
 SELECT public.zipon_set_project_boundary(pid,square,'서울특별시','https://data.seoul.go.kr/',
   '강동구',rev,evidence) INTO answer;
 ok:=answer->>'result'='skipped' AND answer->>'reason'='BOUNDARY_ALREADY_VERIFIED';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','never overwrites a verified boundary','passed',ok,'answer',answer));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 이제서야 INSIDE가 켜진다. 경계 안의 점만 INSIDE다.
 SELECT relation INTO relation FROM public.zipon_development_search(127.1275,37.5415,'강동구',1000,30)
 WHERE project_id=pid;
 ok:=relation='INSIDE';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','inside turns on for a point in the boundary','passed',ok,'relation',relation));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 SELECT relation INTO relation FROM public.zipon_development_search(127.1400,37.5500,'강동구',3000,30)
 WHERE project_id=pid;
 ok:=relation='NEARBY';
 results:=results||jsonb_build_array(jsonb_build_object('check_item','a point outside the boundary stays nearby','passed',ok,'relation',relation));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 -- 지도 RPC는 확인된 경계를 GeoJSON으로 내보낸다.
 SELECT COALESCE((SELECT boundary->>'type'='Polygon' AND geometry_verified
   AND boundary_area_m2 BETWEEN 100 AND 5000000
   FROM public.zipon_development_map('강동구',500) WHERE project_id=pid),false) INTO ok;
 results:=results||jsonb_build_array(jsonb_build_object('check_item','map rpc emits the verified boundary','passed',ok));
 IF NOT ok THEN RAISE EXCEPTION 'Postcheck assertion failed' USING ERRCODE='ZP002'; END IF;

 RAISE EXCEPTION 'ZIPON_POSTCHECK_ROLLBACK %',results::text USING ERRCODE='ZP001';
 EXCEPTION
 WHEN sqlstate 'ZP001' THEN RAISE NOTICE '%',SQLERRM;
 WHEN sqlstate 'ZP002' THEN RAISE NOTICE 'FAILED %',results::text; RAISE;
 END;
END
$test$;
ROLLBACK;
