"""공식 홈페이지 추출 결과(data/golf/enrichment_review/*.json)를 활성 DB에 반영한다.

반영 규칙:
  - verified_quote=True 인 값만 (인용이 실제 페이지에 있고 금액이 인용에 포함됨)
  - 그린피는 비회원 18홀 행만.
  - 빈 필드 → 채운다.
  - 이 자동 수집(CONFIDENCE)으로 채웠던 값 → --refresh 일 때 새 값으로 갱신한다.
  - 다른 경로(정밀 작업)로 확정된 값과 다르면 → 덮어쓰지 않고 conflicts 로 보고한다.
  - 반영 전 활성 DB를 data/golf/backups/ 에 백업한다.

사용:
  venv\\Scripts\\python.exe scripts\\apply_golf_review.py <review.json> [--ids a,b] [--refresh] [--dry-run]
"""

import argparse
import json
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.golf_repository import find_active_db  # noqa: E402

CONFIDENCE = "official_homepage_extracted_quote_verified"
MODE_MAP = {"caddie": "caddie", "no_caddie": "no_caddie", "optional": "optional_caddie_or_self"}


def _ours(item):
    return isinstance(item, dict) and item.get("confidence") == CONFIDENCE


def _fee_rows(ex, today):
    """비회원(일반) 18홀 그린피만 fee_records 행으로 만든다.

    customer 구분
      - nonmember : 그대로 사용한다.
      - member    : 사용하지 않는다. 회원가를 일반 요금으로 쓰면 실제보다 싸게 보인다.
      - unknown   : 그 골프장 추출본에 member/nonmember 행이 하나도 없을 때만 사용한다.
                    대중제(퍼블릭)는 회원·비회원 구분 없이 요금표가 하나뿐이라
                    Claude가 customer를 'unknown'으로 남기는데, 이 값이 곧 일반 요금이다.
                    회원가가 함께 있는 곳의 unknown은 어느 쪽인지 알 수 없으므로 버린다.
    """
    all_rows = [r for r in (ex.get("green_fees") or [])
                if r.get("verified_quote") and r.get("holes") == 18]
    labeled = {r.get("customer") for r in all_rows} & {"member", "nonmember"}
    # 회원/비회원 구분이 전혀 없는 단일 요금표일 때만 unknown을 일반 요금으로 인정
    usable = {"nonmember"} if labeled else {"unknown"}

    rows = []
    for row in all_rows:
        if row.get("customer") not in usable:
            continue
        rows.append({
            "record_type": "official_homepage_extract",
            "day_type": {"weekday": "weekday", "weekend": "weekend"}.get(row["day"], ""),
            "session": row["session"],
            "member_type": "nonmember",
            "greenfee": row["price_krw"],
            "evidence_quote": row["quote"],
            "source_url": row["source_url"],
            "checked_at": today,
            "confidence": CONFIDENCE,
        })
    return rows


def _price_set(rows):
    return sorted((r.get("day_type"), r.get("session"), r.get("greenfee")) for r in rows)


def apply_item(record, item, today, refresh=False, apply_players=False):
    """apply_players=False(기본): 2·3인 허용 여부는 해석 오류 위험이 있어 반영하지 않고 제안(conflicts)으로만 남긴다."""
    ex = item.get("extraction") or {}
    changes, conflicts = [], []

    # 그린피
    pricing = record.setdefault("pricing", {"currency": "KRW", "fee_records": []})
    existing = pricing.get("fee_records") or []
    new_rows = _fee_rows(ex, today)
    if new_rows:
        if not existing or (refresh and all(_ours(r) for r in existing)):
            if _price_set(existing) != _price_set(new_rows):
                pricing["fee_records"] = new_rows
                pricing["last_checked"] = today
                pricing["source_url"] = new_rows[0]["source_url"]
                changes.append(f"green_fee x{len(new_rows)}" + (" (갱신)" if existing else ""))
            else:
                for r in existing:
                    r["checked_at"] = today
                pricing["last_checked"] = today
        elif not all(_ours(r) for r in existing):
            conflicts.append({"field": "green_fee", "existing": "정밀 DB 요금표 유지",
                              "new": [f"{r['day_type'] or '-'} {r['session']} {r['greenfee']:,}" for r in new_rows],
                              "source_url": new_rows[0]["source_url"]})

    # 캐디피 / 카트비
    ops = record.setdefault("operations", {})
    for key, field in (("caddie_fee", "caddie"), ("cart_fee", "cart")):
        fee = ex.get(key)
        target = ops.setdefault(field, {})
        if not (fee and fee.get("verified_quote")):
            continue
        current = target.get("fee_team")
        if not current or (refresh and _ours(target) and current != fee["fee_team_krw"]):
            target.update(fee_team=fee["fee_team_krw"], source_url=fee["source_url"], evidence_quote=fee["quote"],
                          checked_at=today, confidence=CONFIDENCE)
            changes.append(f"{field}_fee" + (" (갱신)" if current else ""))
        elif current != fee["fee_team_krw"] and not _ours(target):
            conflicts.append({"field": f"{field}_fee", "existing": current, "new": fee["fee_team_krw"],
                              "source_url": fee["source_url"]})

    # 캐디 방식
    caddie = ops.setdefault("caddie", {})
    mode = MODE_MAP.get(ex.get("caddie_mode"))
    if mode and caddie.get("mode") in (None, "", "unknown") and ex.get("caddie_mode_quote"):
        caddie["mode"] = mode
        caddie.setdefault("evidence_quote", ex["caddie_mode_quote"])
        changes.append("caddie_mode")

    # 야간 라운드: 인용에 '야간/나이트/조명'이 실제로 있을 때만(verified_quote) 반영
    night = ex.get("night_round")
    current_night = ops.get("night") if isinstance(ops.get("night"), dict) else {}
    if night and night.get("verified_quote"):
        if current_night.get("available") in (None, "unknown") or (refresh and _ours(current_night)
                                                                     and current_night.get("available") != night["available"]):
            ops["night"] = {"available": night["available"], "condition": night.get("condition") or "",
                            "source_url": night["source_url"], "evidence_quote": night["quote"],
                            "checked_at": today, "confidence": CONFIDENCE}
            changes.append("night_round")

    # 2인 / 3인
    players = ops.setdefault("players", {})
    for key in ("two_person", "three_person"):
        rule = ex.get(key)
        current = players.get(key) if isinstance(players.get(key), dict) else {}
        if not (rule and rule.get("verified_quote")):
            continue
        if not apply_players:
            if current.get("allowed") != rule["allowed"]:
                conflicts.append({"field": key, "existing": current.get("allowed", "미확인"), "new": rule["allowed"],
                                  "source_url": rule["source_url"], "quote": rule["quote"][:120], "kind": "suggestion"})
            continue
        if current.get("allowed") in (None, "unknown") or (refresh and _ours(current) and current.get("allowed") != rule["allowed"]):
            players[key] = {"allowed": rule["allowed"], "condition": rule.get("condition") or "",
                            "source_url": rule["source_url"], "evidence_quote": rule["quote"],
                            "checked_at": today, "confidence": CONFIDENCE}
            changes.append(key)
        elif current.get("allowed") != rule["allowed"] and not _ours(current):
            conflicts.append({"field": key, "existing": current.get("allowed"), "new": rule["allowed"],
                              "source_url": rule["source_url"]})

    if changes:
        record.setdefault("_derived_fields", []).append({
            "fields": changes, "source": "official_homepage", "method": "golf_official_enrich_v2",
            "derived_at": today, "review_item": item["id"],
        })
    return changes, conflicts


def apply_review(review_path, ids=None, refresh=False, dry_run=False, apply_players=False):
    review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    db_path = find_active_db()
    records = json.loads(db_path.read_text(encoding="utf-8-sig"))
    index = {r["id"]: r for r in records}
    today = date.today().isoformat()

    summary = []
    for item in review["results"]:
        if ids and item["id"] not in ids:
            continue
        if item["id"] not in index or not item.get("extraction"):
            continue
        changes, conflicts = apply_item(index[item["id"]], item, today, refresh=refresh, apply_players=apply_players)
        summary.append({"id": item["id"], "name": item["name"], "changes": changes, "conflicts": conflicts})

    changed = sum(1 for s in summary if s["changes"])
    backup = None
    if not dry_run and changed:
        backup = db_path.parent / "backups" / f"{db_path.stem}_before_review_{datetime.now():%Y%m%d_%H%M%S}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, backup)
        db_path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"db": db_path.name, "backup": backup.name if backup else None, "changed": changed,
            "dry_run": dry_run, "items": summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("review")
    ap.add_argument("--ids", default="")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply-players", action="store_true", help="2·3인 허용 여부까지 반영 (검토 후에만)")
    args = ap.parse_args()
    result = apply_review(args.review, set(filter(None, args.ids.split(","))) or None, args.refresh, args.dry_run,
                          args.apply_players)
    for s in result["items"]:
        print(f"- {s['name']}: {', '.join(s['changes']) or '변경 없음'}")
        for c in s["conflicts"]:
            print(f"    · 확인 필요 {c['field']}: DB={c['existing']} / 홈페이지={c['new']}"
                  + (f" · \"{c['quote']}\"" if c.get("quote") else ""))
    print(("[dry-run] " if result["dry_run"] else "") + f"{result['changed']}곳 반영 · {result['db']}"
          + (f" (백업: {result['backup']})" if result["backup"] else ""))


if __name__ == "__main__":
    main()
