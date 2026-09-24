"""같은 골프장이 두 번 등록된 레코드를 하나로 합친다.

합치는 기준(모두 만족할 때만):
  - 이름을 정규화(컨트리클럽/CC 등 제거)했을 때 같다
  - 코스 구분 꼬리표(Ⅱ, 올드, 뉴, 웨스트 …)가 서로 같다  → 센추리21 / 센추리21-Ⅱ 같은 별개 코스 보호
  - 주소·전화·홈페이지가 서로 어긋나지 않는다 (있는 것끼리 같아야 한다)
  - 셋 중 최소 하나는 실제로 있다 (근거 없이 이름만 같은 경우는 제외)

남길 레코드는 정보가 더 많은 쪽을 고르고, 비어 있는 값만 다른 쪽에서 채운다.
값이 서로 다르면 남긴 쪽을 유지한다(덮어쓰지 않는다).

사용:
  venv\\Scripts\\python.exe scripts\\golf_merge_duplicates.py --dry-run
  venv\\Scripts\\python.exe scripts\\golf_merge_duplicates.py
"""

import argparse
import collections
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.golf_repository import find_active_db  # noqa: E402

BACKUP_DIR = Path("data/golf/backups")
COURSE_MARKS = ("ii", "ⅱ", "2", "3", "올드", "뉴", "웨스트", "이스트", "사우스", "노스",
                "남", "북", "동", "서", "듄스", "레이크", "밸리코스", "힐", "파인", "구")
# 합칠 때 우선순위를 매기는 기준 필드
RICH_FIELDS = ("pricing", "operations", "course_details", "kga", "official_url", "phone", "address", "holes")


def norm(name):
    n = re.sub(r"(컨트리클럽|골프클럽|골프장|골프&리조트|CC|C\.C|GC|㈜|\(주\)|주식회사)", "", str(name or ""))
    return re.sub(r"[^가-힣a-z0-9]", "", n.lower())


def tail(name):
    low = str(name or "").lower()
    return frozenset(m for m in COURSE_MARKS if m in low)


def digits(s):
    return re.sub(r"\D", "", str(s or ""))


def host(u):
    m = re.search(r"https?://(?:www\.)?([^/]+)", str(u or ""))
    return m.group(1).lower() if m else ""


def has_fee(rec):
    return bool((rec.get("pricing") or {}).get("fee_records"))


def richness(rec):
    score = sum(1 for f in RICH_FIELDS if rec.get(f))
    if has_fee(rec):
        score += 5
    return (score, len(json.dumps(rec, ensure_ascii=False)))


def mergeable(group):
    if len({tail(r.get("name")) for r in group}) != 1:
        return False
    addrs = {str(r.get("address") or "").strip() for r in group if r.get("address")}
    phones = {digits(r.get("phone")) for r in group if digits(r.get("phone"))}
    hosts = {host(r.get("official_url")) for r in group if host(r.get("official_url"))}
    if len(addrs) > 1 or len(phones) > 1 or len(hosts) > 1:
        return False
    return bool(addrs or phones or hosts)


def fill_empty(keep, drop):
    """남긴 레코드의 빈 값만 채운다. 이미 값이 있으면 그대로 둔다."""
    filled = []
    for key, value in drop.items():
        if value in (None, "", [], {}):
            continue
        current = keep.get(key)
        if current in (None, "", [], {}):
            keep[key] = value
            filled.append(key)
    # 이름이 다르면 다른 이름을 별칭으로 남겨 검색에서 찾을 수 있게 한다
    aliases = list(keep.get("aliases") or [])
    for name in (drop.get("name"), drop.get("official_name")):
        if name and name != keep.get("name") and name not in aliases:
            aliases.append(name)
    if aliases:
        keep["aliases"] = aliases
    keep["merged_from"] = sorted(set(keep.get("merged_from") or []) | {drop.get("id")} - {None})
    return filled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = find_active_db()
    data = json.loads(path.read_text(encoding="utf-8"))
    wrapped = isinstance(data, dict) and "records" in data
    records = data["records"] if wrapped else data

    groups = collections.defaultdict(list)
    for rec in records:
        groups[norm(rec.get("name"))].append(rec)

    drop_ids, lines = set(), []
    for key, group in groups.items():
        if not key or len(group) < 2 or not mergeable(group):
            continue
        group = sorted(group, key=richness, reverse=True)
        keep, drops = group[0], group[1:]
        for drop in drops:
            filled = fill_empty(keep, drop)
            drop_ids.add(id(drop))
            lines.append(f"- {keep.get('name')} <- {drop.get('name')}"
                         + (f"  (가져온 값: {', '.join(filled)})" if filled else "  (가져올 값 없음)"))

    print("\n".join(lines) or "합칠 항목 없음")
    print(f"\n{'[dry-run] ' if args.dry_run else ''}{len(drop_ids)}개 레코드 정리 "
          f"({len(records)} -> {len(records) - len(drop_ids)})")

    if not drop_ids or args.dry_run:
        return

    kept = [r for r in records if id(r) not in drop_ids]
    if wrapped:
        data["records"] = kept
    else:
        data = kept

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"{path.stem}_before_merge_{datetime.now():%Y%m%d_%H%M%S}.json"
    shutil.copy2(path, backup)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"백업: {backup.name}")


if __name__ == "__main__":
    main()
