# 정비사업 공식 조회 cache

## official_detail/

공식 상세·목록 조회 1건당 파일 1개. cache key는 `id-<sha256(source_system|external_id)>`이며
공식 식별자가 없으면 `url-<sha256(normalized_url|candidate_id)>`를 씁니다. 같은 key는 실행 중 1회만
요청하고, 이후 실행은 cache를 먼저 읽습니다. 차단된 호스트는 같은 실행에서 재시도하지 않습니다.

저장 항목: `fetched_at`, `source_system`, `source_url`, `external_id`, `result_status`, `http_status`,
`content_hash`, `parsed_fields`, `evidence`, `parser_version`.
cookie / authorization / api key / token / secret 계열 키는 저장하지 않습니다.

## geocode/

정규화 주소 1건당 파일 1개(`sha256(zipon-geocode-v1|normalized_address)`). Supabase `geocode_cache`에
그대로 적재할 수 있도록 `normalized_address`, `latitude`, `longitude`, `geocode_source`,
`geocode_confidence`, `geocoded_at`, `address_used`, `coordinate_verified`,
`provider_candidate_count`, `cache_version` 컬럼으로 저장합니다.
`geocode_confidence`가 `EXACT`가 아니면 좌표는 비어 있습니다.
