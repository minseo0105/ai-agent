import json
import shutil
from datetime import datetime
from pathlib import Path

from services.golf_kga_enrichment import (
    CATALOG_PATH, diagnose_kga_matches, apply_safe_kga_enrichment
)
from services.golf_catalog import prepare_service_pool, pool_counts

if __name__ == "__main__":
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    report = diagnose_kga_matches(catalog)
    enriched, stats = apply_safe_kga_enrichment(catalog, report)
    enriched = prepare_service_pool(enriched)

    backup_dir = CATALOG_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"catalog_before_kga_{datetime.now():%Y%m%d_%H%M%S}.json"
    shutil.copy2(CATALOG_PATH, backup)

    CATALOG_PATH.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = pool_counts(enriched)

    print("=" * 64)
    print("KGA 코스정보 안전 보강 완료")
    print("=" * 64)
    print(f"안전 매칭              : {stats['matched']}건")
    print(f"홀 수 신규 보강         : {stats['holes_added']}건")
    print(f"홀 수 충돌(미덮어쓰기)   : {stats['holes_conflict']}건")
    print(f"코스 조합 보강          : {stats['course_profiles_added']}건")
    print(f"Service/Candidate/제외  : {counts['service']}/{counts['candidate']}/{counts['excluded']}")
    print(f"백업: {backup}")
