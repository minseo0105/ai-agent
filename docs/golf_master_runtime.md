# Golf Master runtime adapter

catalog.json remains the canonical service record. load_service_catalog reads it, attaches Master information to a copied _golf_runtime namespace by unique exact ID, then classifies the service pool. No adapter writes or network requests exist.

## Source priority
Current catalog owns basic information, holes, fees, coordinates, KGA and existing evidence. Master basic/catalog are snapshots; facts/objective_features may be inherited from an earlier builder and are not runtime authorities. play_facility is the final builder output used for the six objective features. Raw catalog play/facilities are not overwritten.

## States
confirmed displays 확인됨 (never 공식 확인), conditional displays 조건부 확인, all other states display 정보 확인 필요. NEGATIVE_CANDIDATE, UNKNOWN, REFERENCE_ONLY and CONTAMINATED_HOLD override positive-looking status strings. No negative contract is enabled: even unavailable/VERIFIED_NEGATIVE cannot exclude a result in this version. Source links, classification, date and conditions remain visible. Explicit conflicts become needs_check. Missing Master fields fall back to positive legacy catalog values; bare negative values do not establish verified unavailability.

## Holes and search
Known positive integer holes >=18 qualify. Nine holes qualify only with confirmed nine_hole_twice; conditional does not qualify. Other known values below18 fail; unknown holes stay candidates. Public non-operating exclusion is unchanged. Condition and sentence searches share matches_objective_conditions. Existing service/public-operating candidate eligibility, prices, KGA ordering and pagination remain in place.

## Persistence boundary
Pool refresh independently reloads raw catalog; never pass load_service_catalog results to save_pool. Manual review refresh retains its existing Tavily/GPT and disk storage behavior. Data JSON and Builder are unchanged.

## Rollback
Use load_service_catalog(use_master=False) to disable the Master overlay. The runtime version resets stored search state when this changes. Missing/corrupt/unsupported Master falls back with a diagnostic. Code rollback restores the original catalog-only behavior; no data migration is needed.

## Validation
Run python -B -m unittest discover -s tests -p test_golf_master_adapter.py and test_golf_service_pool.py. The old test_golf.py imports a missing golf_api module and belongs to the prior NAVER pilot, outside this change.
