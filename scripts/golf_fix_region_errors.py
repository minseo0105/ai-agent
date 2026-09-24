"""좌표 추정 때문에 지역이 잘못 들어간 레코드를 근거와 함께 바로잡는다.

좌표 사각형만으로는 시·도 경계를 정확히 가를 수 없어(고양시가 서울 안으로 들어오는 등)
일부 레코드의 지역이 틀렸다. 여기 적힌 건은 이름·공식 홈페이지·좌표로 직접 확인한 것만 넣는다.
전체를 좌표로 다시 계산하면 오히려 맞는 값까지 망가지므로 하지 않는다.

사용:
  venv\\Scripts\\python.exe scripts\\golf_fix_region_errors.py [--dry-run]
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.golf_repository import find_active_db  # noqa: E402

BACKUP_DIR = Path("data/golf/backups")

# name -> (area, subregion, city, 근거)
FIXES = {
    "고양컨트리": ("수도권", "경기북부", "고양", "공식명 고양컨트리클럽 · goyangcc.com · 좌표 37.636/126.860 = 고양시 덕양구"),
    "홍천 C.C": ("강원권", "강원영서", "홍천", "공식명 비콘힐스CC(구 홍천CC) · 좌표 37.626/127.867 = 홍천군"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = find_active_db()
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data["records"] if isinstance(data, dict) and "records" in data else data

    changed = []
    for rec in records:
        fix = FIXES.get(rec.get("name"))
        if not fix:
            continue
        area, subregion, city, reason = fix
        if (rec.get("area"), rec.get("subregion"), rec.get("city")) == (area, subregion, city):
            continue
        changed.append(f"- {rec['name']}: {rec.get('subregion')}/{rec.get('city')} -> {subregion}/{city}  ({reason})")
        loc = rec.get("location") or {}
        for target in (rec, loc):
            target["area"], target["subregion"], target["city"] = area, subregion, city
        rec["location"] = loc
        rec["region_source"] = "manual_verified"
        rec["region_field_sources"] = dict(rec.get("region_field_sources") or {},
                                           area="manual_verified", subregion="manual_verified", city="manual_verified")

    print("\n".join(changed) or "수정할 항목 없음")
    print(f"{'[dry-run] ' if args.dry_run else ''}{len(changed)}곳 수정")

    if changed and not args.dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / f"{path.stem}_before_region_errors_{datetime.now():%Y%m%d_%H%M%S}.json"
        shutil.copy2(path, backup)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"백업: {backup.name}")


if __name__ == "__main__":
    main()
