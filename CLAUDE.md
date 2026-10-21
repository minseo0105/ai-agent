# Golf enrichment handoff

작업 폴더는 `C:\Users\user\Desktop\ai-agent`이다. 이전 복사본은 `ai-agent_old`로 보관 중이며 쓰지 않는다.
docs/에 나오는 옛 폴더("ai-agent - 복사본") 설명은 과거 기록이다.

Before changing golf data, read `docs/golf_handoff_2026-09-24.md` and `docs/golf_enrichment_policy.md`.
Preserve working features and unrelated local changes. Check consumers before schema changes.
Never infer missing values as false or overwrite uncertain/conflicting values automatically.
Preserve source/evidence/confidence, field_evidence, enrichment history and candidates.
Refresh schedule: full information January/July; prices April/October (quarterly prices overall).
Do not revert to monthly fee collection. Remote automation has not been activated/verified.

Golf changes were committed and deployed on 2026-09-24. Read docs/golf_production_deployment_2026-09-24.md for the latest status. Preserve any subsequent local changes; do not reset/clean/restore the working tree.
Use `venv\Scripts\python.exe -B scripts\golf_db_status.py` for current coverage and smoke checks.
Use `venv\Scripts\python.exe -B -m unittest discover -s tests -p test_golf_import_policy.py -v` for the 13 policy tests.
These checks do not call paid APIs. Do not treat the old dated research JSON as fresh research.

Also read `docs/golf_refinement_243_2026-09-24.md`: 243-record review evidence audit, paid search cost, candidate vs reviewed opinions, and scoped UI integration. Do not promote unreviewed review candidates to filters.

Latest changes: read docs/golf_applied_2026-09-25.md for search integrity, 25 added fields, 13 reviewed observations, 4 rejected candidates, price quarantine, regression baseline, and deployment verification. Keep the 243 recommendation record IDs; suspected duplicate identities need separate review.
