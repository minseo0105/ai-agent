"""주소 기반 좌표 보정.

- 주소가 있는데 좌표가 없거나, 무효로 표시됐거나, 저장 좌표가 주소 좌표와 3km 이상 어긋나면
  NAVER 지오코딩(실패 시 VWorld 주소검색) 좌표로 location.latitude/longitude 를 교체한다.
- 기존 좌표는 location.previous_coordinate 에 보관, 출처는 location.source 에 기록.
- 반영 전 DB 백업.

사용: venv\\Scripts\\python.exe scripts\\golf_geocode_fill.py [--dry-run]
"""

import argparse
import json
import shutil
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import golf_service as gs  # noqa: E402
from services.config import get_secret  # noqa: E402
from services.golf_repository import find_active_db  # noqa: E402

MAX_OFFSET_KM = 3.0


def geocode(address):
    key_id, key = gs._naver_keys()
    geo = gs.naver_geocode(address, key_id, key) if key_id and key else None
    source = "naver_geocode_address"
    if geo is None:
        geo = gs.vworld_place_search(address, get_secret("VWORLD_API_KEY"), get_secret("VWORLD_DOMAIN"))
        source = "vworld_search"
    return (geo, source) if geo else (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db_path = find_active_db()
    records = json.loads(db_path.read_text(encoding="utf-8-sig"))
    today = date.today().isoformat()
    stats = Counter()

    for rec in records:
        if rec.get("service_status") == "excluded" and not gs._public_operating(rec):
            continue
        if rec.get("duplicate_of"):
            continue
        address = str(rec.get("address") or (rec.get("location") or {}).get("address") or "").strip()
        if not address:
            stats["no_address"] += 1
            continue
        current = gs.club_lat_lon(rec)
        geo, source = geocode(address)
        time.sleep(0.05)
        if not geo:
            stats["geocode_failed"] += 1
            continue
        new = (geo["lat"], geo["lon"])
        offset = gs.distance_km(current, new) if current else None
        if current and offset < MAX_OFFSET_KM:
            stats["ok"] += 1
            continue
        loc = rec.setdefault("location", {})
        if current:
            loc["previous_coordinate"] = {"latitude": current[0], "longitude": current[1], "offset_km": round(offset, 2)}
        loc.update(latitude=new[0], longitude=new[1], source=source, geocoded_at=today, geocoded_address=address)
        validation = rec.get("coordinate_validation")
        if isinstance(validation, dict) and str(validation.get("status", "")).startswith("invalid"):
            validation["status"] = "regeocoded_from_address"
            validation["regeocoded_at"] = today
        stats["filled" if not current else "corrected"] += 1
        print(f"- {rec['name']}: {'새 좌표' if not current else f'{offset:.1f}km 보정'} ({source})")

    print(dict(stats))
    if args.dry_run:
        print("[dry-run] 저장하지 않음")
        return
    backup = db_path.parent / "backups" / f"{db_path.stem}_before_geocode_{datetime.now():%Y%m%d_%H%M%S}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, backup)
    db_path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {db_path.name} (backup {backup.name})")


if __name__ == "__main__":
    main()
