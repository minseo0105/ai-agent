"""pricing.fee_records 정규화.

정밀 DB의 요금 행은 골프장마다 형식이 제각각이다(43가지 이상). 예:
  {"day_type": "월요일", "session": "1부", "price": 140000}
  {"nonmember": {"weekday_1st": 140000, "weekend_2nd": 310000}}
  {"member_type": "비회원", "weekday": 230000, "weekend_holiday": 300000}
  {"fees": {"weekday": {"full_member": 130000, "nonmember": 245000}, ...}}

여기서는 모든 숫자 값을 경로와 함께 펼친 뒤,
  - 비회원(일반) 18홀 그린피만 남기고 (회원가·9홀·카트/캐디비 제외)
  - 경로/행 정보에서 주중·주말, 1·2·3부를 읽어
  - 현재 유효한 요금(tier 0)과 지난/예정 요금(tier 1)을 구분한다.
값을 추정해서 만들지 않는다. 판단할 수 없는 행은 요일/시간대 구분 없음(None)으로 둔다.
"""

import re
from datetime import date

_NON_FEE = ("cart", "caddie", "카트", "캐디", "surcharge", "extra", "players", "holes", "basis",
            "capacity", "team", "discount", "deposit", "penalty", "tax")
_NONMEMBER = ("nonmember", "non_member", "non-member", "비회원", "general", "일반", "internet", "public",
              "visitor", "guest", "normal", "standard_rate")
_MEMBER = ("member", "회원", "designated")
_SHORT = ("9h", "9홀", "6홀", "12홀", "nine")
_WEEKEND_EN = {"weekend", "saturday", "sunday", "holiday", "sat", "sun"}
_WEEKDAY_EN = {"weekday", "mon", "tue", "wed", "thu", "fri", "monday", "tuesday", "wednesday", "thursday", "friday"}
_SESSION_TOKENS = {"1st": "1부", "2nd": "2부", "3rd": "3부", "1": "1부", "2": "2부", "3": "3부"}


def _amounts(value):
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [int(value)] if 10000 <= value <= 2000000 else []
    if isinstance(value, str):
        nums = [int(n) for n in re.findall(r"\d{5,7}", value.replace(",", ""))]
        return [n for n in nums if 10000 <= n <= 2000000]
    return []


def _leaves(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, path + (str(k),))
    elif isinstance(obj, list):
        for v in obj:
            yield from _leaves(v, path)
    else:
        yield path, obj


def _tokens(key):
    return [t for t in re.split(r"[^0-9a-zA-Z가-힣]+", key.lower()) if t]


def _parse_period(row):
    """(시작, 끝) date. 모르면 None."""
    def d(s):
        try:
            return date.fromisoformat(str(s)[:10])
        except (TypeError, ValueError):
            return None

    start = d(row.get("valid_from") or row.get("effective_from"))
    end = d(row.get("valid_to") or row.get("effective_to"))
    for key in ("valid_period", "period", "effective_period"):
        text = str(row.get(key) or "")
        found = re.findall(r"\d{4}-\d{2}-\d{2}", text)
        if len(found) >= 2:
            start, end = start or d(found[0]), end or d(found[1])
    return start, end


def _row_tier(row, today):
    status = " ".join(str(row.get(k) or "") for k in ("status", "source_status", "period_status", "effective_period")).lower()
    if row.get("superseded") is True or "historical" in status or "legacy" in status or "not_current" in status:
        return 1
    start, end = _parse_period(row)
    if (end and end < today) or (start and start > today):
        return 1
    return 0


def _day_of(path_tokens, day_text):
    if any(t in _WEEKEND_EN for t in path_tokens):
        return True
    if any(t in _WEEKDAY_EN for t in path_tokens):
        return False
    text = day_text.lower()
    en = set(_tokens(text))
    if en & _WEEKEND_EN or any(t in text for t in ("주말", "토", "일요일", "공휴일", "휴일")):
        return True
    if en & _WEEKDAY_EN or any(t in text for t in ("평일", "주중", "월", "화", "수", "목", "금")):
        return False
    return None


def _session_of(path_tokens, session_text):
    m = re.search(r"([123])\s*부", session_text or "")
    if m:
        return f"{m.group(1)}부"
    has_day = any(t in _WEEKEND_EN | _WEEKDAY_EN for t in path_tokens)
    if has_day:
        for t in path_tokens:
            if t in _SESSION_TOKENS:
                return _SESSION_TOKENS[t]
    return None


def normalize_fee_records(club, today=None):
    """[{weekend, session, price, tier, source_url, label}]"""
    today = today or date.today()
    pricing = club.get("pricing") or {}
    rows = pricing.get("fee_records") or []
    if not isinstance(rows, list):
        return []

    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        descriptors = " ".join(
            str(row.get(k) or "") for k in ("member_type", "customer_type", "category", "member_class", "product",
                                             "rate_type", "record_type")
        ).lower()
        session_text = str(row.get("session") or "")
        holes_text = " ".join(str(row.get(k) or "") for k in ("holes", "round_holes", "course_scope")) + " " + session_text
        if re.search(r"\b(6|9|12)\b", holes_text) or any(t in holes_text.lower() for t in _SHORT):
            continue
        day_text = " ".join(str(row.get(k) or "") for k in ("day_type", "day", "days"))
        tier = _row_tier(row, today)

        for path, value in _leaves(row):
            if not path:
                continue
            key = "_".join(path).lower()
            if path[0] in ("valid_from", "valid_to", "effective_from", "effective_to", "checked_at", "observed_at",
                           "source_url", "note", "valid_period", "period", "effective_period", "holes", "round_holes",
                           "players", "operating_months", "evidence_quote", "confidence", "record_type"):
                continue
            if any(t in key for t in _NON_FEE) or any(t in key for t in _SHORT):
                continue
            amounts = _amounts(value)
            if not amounts:
                continue

            member_text = f"{descriptors} {key}"
            is_nonmember = any(t in member_text for t in _NONMEMBER)
            is_member = any(t in member_text for t in _MEMBER)
            if is_member and not is_nonmember:
                continue

            ptoks = _tokens(key)
            for amount in amounts:
                out.append({
                    "weekend": _day_of(ptoks, day_text),
                    "session": _session_of(ptoks, session_text),
                    "price": amount,
                    "tier": tier,
                    "source_url": row.get("source_url") or pricing.get("source_url") or "",
                    "label": key,
                })
    return out


def _current(rows):
    best = min((r["tier"] for r in rows), default=None)
    return [r for r in rows if r["tier"] == best], best


def green_fee(club, weekend=None, session=None):
    """조건에 맞는 비회원 18홀 그린피 최저가. 없으면 None."""
    rows, _ = _current(normalize_fee_records(club))
    prices = [
        r["price"] for r in rows
        if r['tier'] == 0 and (weekend is None or r["weekend"] is None or r["weekend"] == weekend)
        and (session is None or r["session"] is None or r["session"] == session)
    ]
    return min(prices) if prices else None


def fee_summary(club):
    """상세화면용 요약: 주중/주말 범위, 시간대별 최저가, 출처, 기준."""
    rows, tier = _current(normalize_fee_records(club))
    if not rows:
        return None

    def rng(values):
        return [min(values), max(values)] if values else None

    by_day = {}
    for label, flag in (("weekday", False), ("weekend", True)):
        vals = [r["price"] for r in rows if r["weekend"] == flag]
        by_day[label] = rng(vals)
        sessions = {}
        for s in ("1부", "2부", "3부"):
            sv = [r["price"] for r in rows if r["weekend"] == flag and r["session"] == s]
            if sv:
                sessions[s] = min(sv)
        by_day[label + "_sessions"] = sessions
    unspecified = rng([r["price"] for r in rows if r["weekend"] is None])

    pricing = club.get("pricing") or {}
    sources = list(dict.fromkeys(r["source_url"] for r in rows if r["source_url"]))
    notices = pricing.get("monthly_notices") or []
    return {
        "weekday": by_day["weekday"],
        "weekend": by_day["weekend"],
        "weekday_sessions": by_day["weekday_sessions"],
        "weekend_sessions": by_day["weekend_sessions"],
        "unspecified": unspecified,
        "is_current": tier == 0,
        "checked_at": pricing.get("last_checked") or pricing.get("checked_at") or "",
        "source_url": sources[0] if sources else (pricing.get("source_url") or ""),
        "rule": pricing.get("pricing_rule") or "",
        "latest_notice_month": ((pricing.get("freshness") or {}).get("latest_notice_month")
                                or (notices[-1].get("month") if notices and isinstance(notices[-1], dict) else "")),
    }


def team_fee(club, kind):
    """operations.cart / operations.caddie의 팀당 요금(18홀 기준 우선)."""
    item = (club.get("operations") or {}).get(kind) or {}
    if not isinstance(item, dict):
        return None
    if item.get('fresh_until') and str(item['fresh_until']) < date.today().isoformat():
        return None
    for key in ("fee_team", "fee_team_18h", "18h_team", "fee_team_standard", "fee_team_standard_18h", "standard_team"):
        amounts = _amounts(item.get(key))
        if amounts:
            return amounts[0]
    return None
