"""공공데이터(행정안전부 생활 골프장)로 운영형태(회원제/대중제)를 채운다.

공공데이터에는 그린피가 없지만 업종 구분(DTIL_TPBIZ_NM)이 있어
회원제 / 정규대중 / 일반대중 / 비회원제를 구분할 수 있다.
요금이 '회원가인지 일반가인지' 판단할 때 근거가 된다.

이름이 정확히 1건만 매칭될 때에만 반영한다(match_public_records와 같은 기준).

사용:
  venv\\Scripts\\python.exe scripts\\golf_fill_operation_type.py [--dry-run]
"""

import argparse
import collections
import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.config import get_secret  # noqa: E402
from services.golf_public_data import _norm, _record_name, fetch_public_golf_records  # noqa: E402
from services.golf_repository import find_active_db  # noqa: E402

BACKUP_DIR = Path("data/golf/backups")
# 공공데이터 업종명 -> 화면에서 쓰는 운영형태
TYPE_MAP = {
    "회원제": "회원제",
    "비회원제": "대중제",
    "정규대중": "대중제",
    "일반대중": "대중제",
    "간이": "간이골프장",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = get_secret("DATA_GO_KR_SERVICE_KEY")
    if not key:
        print("DATA_GO_KR_SERVICE_KEY가 없습니다.")
        return
    public = fetch_public_golf_records(key, page_size=100)
    print(f"공공데이터 {len(public)}건")

    index = collections.defaultdict(list)
    for rec in public:
        name_key = _norm(_record_name(rec))
        if name_key:
            index[name_key].append(rec)

    path = find_active_db()
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data["records"] if isinstance(data, dict) and "records" in data else data

    today = date.today().isoformat()
    filled = collections.Counter()
    changes = []
    for club in records:
        ops = club.setdefault("operations", {})
        current = ops.get("operation_type")
        if isinstance(current, dict) and current.get("value"):
            continue  # 이미 있는 값은 건드리지 않는다

        candidates = index.get(_norm(club.get("name")), [])
        if len(candidates) != 1:
            continue
        raw = str(candidates[0].get("DTIL_TPBIZ_NM") or "").strip()
        value = TYPE_MAP.get(raw)
        if not value:
            continue

        ops["operation_type"] = {
            "value": value,
            "raw": raw,
            "source": "공공데이터 행정안전부_생활_골프장",
            "checked_at": today,
            "confidence": "public_data",
        }
        filled[value] += 1
        changes.append(f"- {club.get('name')}: {value} ({raw})")

    for line in changes[:15]:
        print(line)
    if len(changes) > 15:
        print(f"  … 외 {len(changes) - 15}곳")
    print(f"\n{'[dry-run] ' if args.dry_run else ''}{sum(filled.values())}곳 반영 · {dict(filled)}")

    if changes and not args.dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / f"{path.stem}_before_optype_{datetime.now():%Y%m%d_%H%M%S}.json"
        shutil.copy2(path, backup)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"백업: {backup.name}")


if __name__ == "__main__":
    main()
