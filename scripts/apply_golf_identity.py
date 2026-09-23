"""golf_identity_resolve.py 결과(data/golf/enrichment_review/identity_*.json)를 활성 DB에 반영한다.

- 중복: duplicate_of 설정 + 원본 레코드 aliases 에 이름 추가(이름 검색용)
- 신원 확인(영업·골프장): 비어 있는 정식명칭/공식 홈페이지(검색결과 도메인 검증)/주소(검색결과 원문 검증)/홀 수 채움
- 권역: 검증된 주소로 area/subregion/city 재분류 (좌표 기반 오분류 교정)
- 모든 판정은 record.identity_resolution 에 근거 URL과 함께 보관
- 반영 전 DB 백업

사용: venv\\Scripts\\python.exe scripts\\apply_golf_identity.py <identity.json> [--dry-run]
"""

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.golf_catalog import _region_from_public_address  # noqa: E402
from services.golf_repository import find_active_db  # noqa: E402


SIDO_AREA = [
    (("서울", "인천", "경기"), "수도권"),
    (("충청", "충북", "충남", "대전", "세종"), "충청권"),
    (("강원",), "강원권"),
    (("경상", "경북", "경남", "부산", "대구", "울산"), "영남권"),
    (("전라", "전북", "전남", "광주"), "호남권"),
    (("제주",), "제주권"),
]


def area_from_sido(sido):
    text = str(sido or "")
    return next((area for keys, area in SIDO_AREA if any(k in text for k in keys)), None)


def subregion_city_from_address(address, area, lon=None):
    """'강원 춘천시 …', '충북 음성군 …'처럼 줄여 쓴 주소에서도 세부지역·도시를 정한다."""
    import re as _re
    text = str(address or "")
    m = _re.search(r"([가-힣]+?)(시|군)\s", text + " ")
    city = m.group(1) if m else None
    if area == "충청권":
        sub = "충북" if _re.search(r"충북|충청북", text) else ("충남" if _re.search(r"충남|충청남|대전|세종", text) else None)
    elif area == "강원권":
        east = ("강릉", "속초", "동해", "삼척", "양양", "고성")
        sub = "강원영동" if (city in east or (lon and lon >= 128.45)) else "강원영서"
    else:
        sub = None
    return sub, city


def _host(url):
    from urllib.parse import urlsplit
    return (urlsplit(str(url or "")).hostname or "").removeprefix("www.")


CHAIN_HOSTS = {"golfzoncounty.com", "clubd.co.kr", "clubd.com", "sonohotelsresorts.com", "sono.co.kr",
                "hanwharesort.co.kr", "daemyungresort.com", "lottehotel.com", "kumho-resort.co.kr"}


def _addr_key(ident):
    return "".join(str(ident.get("address") or "").split())[:15]


def dedupe_batch(review, index):
    """이번 신원확인 대상끼리의 중복: 같은 주소(앞 15자), 또는 체인이 아닌 같은 공식 도메인이면서 주소가 충돌하지 않을 때.
    정보가 많은 쪽을 남긴다."""
    groups = {}
    for item in review["results"]:
        ident = item.get("identity") or {}
        if item.get("status") != "resolved" or ident.get("duplicate_of_id") or ident.get("public_access") in ("military", "member_only"):
            continue
        checks = item.get("checks") or {}
        keys = []
        host = _host(ident.get("official_url"))
        if host and checks.get("url_in_results") and host not in CHAIN_HOSTS:
            keys.append("url:" + host)
        if ident.get("address") and checks.get("address_in_results"):
            keys.append("addr:" + "".join(str(ident["address"]).split())[:15])
        for k in keys:
            groups.setdefault(k, []).append(item)
    marked = {}
    for items in groups.values():
        if len(items) < 2:
            continue
        score = lambda it: sum(bool((it.get("identity") or {}).get(f)) for f in ("official_url", "address", "holes"))
        keep = max(items, key=score)
        keep_addr = _addr_key(keep.get("identity") or {})
        for it in items:
            other_addr = _addr_key(it.get("identity") or {})
            if keep_addr and other_addr and keep_addr != other_addr:
                continue  # 같은 도메인이라도 주소가 다르면 다른 골프장
            if it is not keep and it["id"] not in marked:
                marked[it["id"]] = keep["id"]
    for item in review["results"]:
        if item["id"] in marked:
            item.setdefault("identity", {})["duplicate_of_id"] = marked[item["id"]]
    return marked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("review")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    review = json.loads(Path(args.review).read_text(encoding="utf-8"))
    db_path = find_active_db()
    records = json.loads(db_path.read_text(encoding="utf-8-sig"))
    index = {r["id"]: r for r in records}
    today = date.today().isoformat()
    stats = Counter()
    batch_dups = dedupe_batch(review, index)
    print(f"대상 내부 중복 {len(batch_dups)}곳:", [index[k]["name"] + "→" + index[v]["name"] for k, v in batch_dups.items()])

    for item in review["results"]:
        rec = index.get(item["id"])
        ident = item.get("identity") or {}
        if not rec or item.get("status") not in ("resolved", "rule"):
            stats["skipped"] += 1
            continue
        checks = item.get("checks") or {}
        rec["identity_resolution"] = {**ident, "checks": checks, "resolved_at": today,
                                      "method": "web_search+llm_identity_v1"}

        dup = ident.get("duplicate_of_id")
        if dup and dup in index and dup != rec["id"]:
            rec["duplicate_of"] = dup
            aliases = index[dup].setdefault("aliases", [])
            if rec["name"] not in aliases:
                aliases.append(rec["name"])
            stats["duplicate"] += 1
            continue

        if ident.get("public_access") in ("military", "member_only"):
            stats["restricted"] += 1
        if ident.get("operating") == "closed" or ident.get("is_golf_course") is False:
            stats["closed_or_not_golf"] += 1
            continue

        filled = []
        if not rec.get("official_name") and ident.get("official_name"):
            rec["official_name"] = ident["official_name"]
            filled.append("official_name")
        if not rec.get("official_url") and ident.get("official_url") and checks.get("url_in_results"):
            rec["official_url"] = ident["official_url"]
            filled.append("official_url")
        if not rec.get("address") and ident.get("address") and checks.get("address_in_results"):
            rec["address"] = ident["address"]
            loc = rec.setdefault("location", {})
            loc["address"] = ident["address"]
            filled.append("address")
        if not rec.get("holes") and isinstance(ident.get("holes"), int) and ident["holes"] > 0:
            rec["holes"] = ident["holes"]
            rec["holes_source"] = "web_identity"
            filled.append("holes")

        # 검증된 주소로 권역 재분류
        address = rec.get("address") if checks.get("address_in_results") or rec.get("address") else None
        region = _region_from_public_address(address) if address else None
        if region and region[0]:
            area, sub, city = region
            if (area, sub, city) != (rec.get("area"), rec.get("subregion"), rec.get("city")):
                old = (rec.get("area"), rec.get("subregion"), rec.get("city"))
                rec["area"], rec["subregion"], rec["city"] = area, sub or rec.get("subregion"), city or rec.get("city")
                loc = rec.setdefault("location", {})
                loc.update(area=rec["area"], subregion=rec["subregion"], city=rec["city"])
                rec["region_source"] = "identity_address"
                if old[0] != area:
                    filled.append(f"region {old[0]}→{area}")
                    stats["region_fixed"] += 1
        else:
            # 주소로 분류하지 못하면 신원확인의 시/도로 권역만 교정 (좌표 기반 오분류 방지)
            area = area_from_sido(ident.get("sido"))
            if area and area != rec.get("area"):
                old_area = rec.get("area")
                rec["area"] = area
                if area not in ("수도권", "충청권", "강원권"):
                    rec["subregion"] = None
                else:
                    lon = (rec.get("location") or {}).get("longitude")
                    sub, city = subregion_city_from_address(rec.get("address"), area, lon)
                    rec["subregion"] = sub or rec.get("subregion")
                    rec["city"] = city or rec.get("city")
                rec["region"] = ident.get("sido") or rec.get("region")
                loc = rec.setdefault("location", {})
                loc.update(area=area, subregion=rec.get("subregion"))
                rec["region_source"] = "identity_sido"
                filled.append(f"region {old_area}→{area}")
                stats["region_fixed"] += 1

        if filled:
            rec.setdefault("_derived_fields", []).append({"fields": filled, "source": "web_search_identity",
                                                          "method": "web_search+llm_identity_v1", "derived_at": today})
        stats["resolved"] += 1
        print(f"- {rec['name']}: {', '.join(filled) or '판정만 기록'}")

    print(dict(stats))
    if args.dry_run:
        print("[dry-run] 저장하지 않음")
        return
    backup = db_path.parent / "backups" / f"{db_path.stem}_before_identity_{datetime.now():%Y%m%d_%H%M%S}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, backup)
    db_path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {db_path.name} (backup {backup.name})")


if __name__ == "__main__":
    main()
