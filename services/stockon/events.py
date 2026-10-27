"""이번 주 일정: 연간 일정 파일(data/stockon/events_YYYY.json) + 옵션 만기일 규칙.

옵션 만기일(코스피200 옵션 최종거래일)은 매월 둘째 목요일로 계산한다. 그날이 휴장이면 거래소가
앞당기므로 화면에 '규칙 계산'이라고 함께 적는다.
"""

import json
from datetime import date, timedelta

from services.config import PROJECT_ROOT

EVENTS_DIR = PROJECT_ROOT / "data" / "stockon"
EXPIRY_SOURCE = {"name": "한국거래소 파생상품 최종거래일 규칙(매월 둘째 목요일)", "url": "https://www.krx.co.kr"}


def _second_thursday(year: int, month: int) -> date:
    d = date(year, month, 1)
    first_thu = d + timedelta(days=(3 - d.weekday()) % 7)
    return first_thu + timedelta(days=7)


def _file_events(year: int) -> list[dict]:
    try:
        data = json.loads((EVENTS_DIR / f"events_{year}.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []
    return [e for e in data.get("events", []) if e.get("date") and e.get("title")]


def week_events(today: date) -> dict:
    """오늘이 속한 주(월~일)와 다음 주 월~금 일정. 주말에 보면 다음 주 일정이 보이도록."""
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=11)
    events = []
    for year in {start.year, end.year}:
        events += _file_events(year)
        for month in range(1, 13):
            d = _second_thursday(year, month)
            events.append({"date": d.isoformat(), "title": "코스피200 옵션 만기일", "kind": "expiry",
                           "note": "규칙 계산", "source": EXPIRY_SOURCE})
    events = [e for e in events if start.isoformat() <= e["date"] <= end.isoformat()]
    return {"from": start.isoformat(), "to": end.isoformat(),
            "events": sorted(events, key=lambda e: (e["date"], e["title"]))}
