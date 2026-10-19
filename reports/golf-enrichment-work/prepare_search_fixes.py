from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
def save(path,text):
 p=OUT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
s=(ROOT/'services/golf_service.py').read_text(encoding='utf-8')
a=s.index('def estimate_per_person(');b=s.index('# 정밀 DB operations.caddie.mode',a)
s=s[:a]+'''def _known_team_fee(club, kind):
    amount = team_fee(club, kind)
    if amount is not None:
        return amount
    # An expired/conditional operations value must not revive via legacy data.
    if (club.get("operations") or {}).get(kind):
        return None
    fee = club.get("fee") or {}
    value = fee.get(kind + "_team") if fee.get("verified") else None
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def estimate_per_person(club, weekend=False, players=4, session=None):
    """Only show a total when green fee and both team fees are known."""
    green = green_fee(club, bool(weekend), session)
    if green is None and not (club.get("pricing") or {}).get("fee_records") and session is None:
        fee = club.get("fee") or {}
        day = "weekend" if weekend else "weekday"
        value = fee.get(day + "_green") or fee.get(day)
        if fee.get("verified") and isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            green = value
    cart, caddie = _known_team_fee(club, "cart"), _known_team_fee(club, "caddie")
    if green is None or cart is None or caddie is None:
        return None
    return int(green + (cart + caddie) / max(int(players or 4), 1))


'''+s[b:]
s=s.replace('# 화면의 예산은 \'그린피\' 기준. 그린피를 알면 그린피로, 모르면 1인 예상가로 비교한다.','# 화면의 예산은 그린피 기준이며 총액과 혼용하지 않는다.')
s=s.replace('                if est is None:\n                    est = estimate_per_person(club, bool(cond.get("weekend")), int(cond.get("players") or 4))\n','')
s=s.replace('estimated = estimate_per_person(club, bool(cond.get("weekend")), int(cond.get("players") or 4))','estimated = _cond_session_fee(club, cond)')
a=s.index('def _sort_price(');b=s.index('def _distance_from_departure',a)
s=s[:a]+'''def _sort_price(course, cond):
    """Sort by the same green fee used by the budget filter; unknowns last."""
    amount = _cond_session_fee(course, cond)
    return float(amount) if amount is not None else float("inf")


'''+s[b:]
old='    result = _run_search(cond, sort, None, city=str(cond["city"]) if cond.get("city") else None)'
new='''    unsupported = []
    compact = re.sub(r"\\s+", "", text).lower()
    if re.search(r"(?<!\\d)2인|두명|둘이|2명|커플라운", compact):
        unsupported.append("2인 플레이")
    for pattern, label in ((r"연습장|드라이빙레인지", "연습장 시설"), (r"par3|파3|파쓰리", "PAR3 시설")):
        if re.search(pattern, compact):
            unsupported.append(label)
    if cond.get("traits") or re.search(r"페어웨이.*(?:넓|좁)|벙커.*(?:많|적)|시설.*(?:좋|깔끔)|그린.*(?:빠르|빠른|느린)", compact):
        unsupported.append("후기 기반 특징")
    if unsupported:
        trace = dict.fromkeys(("total", "area", "subregion", "final", "conditional", "confirmed", "pending", "excluded", "unknown_excluded", "unknown_included"), 0)
        trace["total"] = len(load_pools()[2])
        trace["unknown_reasons"] = {}
        result = _build_results([], cond, trace, sort, None)
        result["applied"] = []
        result["include_unknown"] = bool(include_unknown)
        result["notice"] = "요청한 " + ", ".join(unsupported) + " 조건은 검증된 자료가 부족해 아직 검색 필터로 지원하지 않습니다. 해당 조건을 제외하고 다시 검색해 주세요. 조건을 무시한 추천 결과는 표시하지 않았습니다."
        result["unsupported_conditions"] = unsupported
    else:
        result = _run_search(cond, sort, None, city=str(cond["city"]) if cond.get("city") else None)'''
assert old in s;s=s.replace(old,new)
s=s.replace('"players": f"{cond.get(\'players\', 4)}인",','"players": "2인 (미지원)" if "2인 플레이" in unsupported else f"{cond.get(\'players\', 4)}인",')
s=s.replace('cart, caddie = team_fee(club, "cart"), team_fee(club, "caddie")','cart, caddie = _known_team_fee(club, "cart"), _known_team_fee(club, "caddie")')
s=s.replace('            return [int(rng[0] + per_person), int(rng[1] + per_person)] if rng else None','            return [int(rng[0] + per_person), int(rng[1] + per_person)] if rng and cart is not None and caddie is not None and summary["is_current"] else None')
s=s.replace('"note": ("비회원 18홀 공식 요금 기준 · 1인 예상은 카트·캐디 팀요금 ÷ 4 포함"','"note": ("비회원 18홀 공식 요금 기준 · " + ("1인 예상은 카트·캐디 팀요금 ÷ 4 포함" if cart is not None and caddie is not None else "카트·캐디 부대비용 미확인 항목이 있어 총액 계산 보류")')
s=s.replace('"cart": fee.get("cart_team", 0),','"cart": _known_team_fee(club, "cart"),').replace('"caddie": fee.get("caddie_team", 0),','"caddie": _known_team_fee(club, "caddie"),')
s=s.replace('    cats = ((club.get("precision_assessment") or {}).get("categories")) or {}','''    cats = dict(((club.get("precision_assessment") or {}).get("categories")) or {})
    # Derived display status, never mutate historical assessments in the DB.
    evidence = club.get("field_evidence") or {}
    for kind in ("cart", "caddie"):
        if _known_team_fee(club, kind) is not None and cats.get(kind) in (None, "missing"):
            cats[kind] = "partial"
    if (club.get("pricing") or {}).get("fee_records") and cats.get("green_fee") in (None, "missing"):
        cats["green_fee"] = "partial"
    if evidence.get("phone") and cats.get("basic_identity") == "missing":
        cats["basic_identity"] = "partial"''')
save('services/golf_service.py',s)
p=(ROOT/'services/golf_pricing.py').read_text(encoding='utf-8')
p=p.replace('        amounts = _amounts(item.get(key))','        value = item.get(key)\n        if isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0:\n            return 0\n        amounts = _amounts(value)')
save('services/golf_pricing.py',p)
t=(ROOT/'web/src/lib/golf.ts').read_text(encoding='utf-8').replace('cart: number; caddie: number; note: string','cart: number | null; caddie: number | null; note: string')
save('web/src/lib/golf.ts',t)
