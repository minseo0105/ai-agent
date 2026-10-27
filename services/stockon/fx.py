"""원/달러 매매기준율 — 한국수출입은행 현재환율 API (영업일 11시 전후 하루 1회 고시).

키: KOREAEXIM_API_KEY(선택). 없으면 환율 카드는 '키 미설정'으로 보인다.
도메인은 2025-06 oapi.koreaexim.go.kr로 바뀌었다(이전 www 도메인은 2026-04-30 종료).
"""

from datetime import datetime, timedelta

import requests

from services.config import get_secret
from services.stockon.public_data import KST

URL = "https://oapi.koreaexim.go.kr/site/program/financial/exchangeJSON"
SOURCE = {"name": "한국수출입은행", "url": "https://www.koreaexim.go.kr"}


def _rate_on(day: datetime, key: str, http) -> float | None:
    r = http(URL, params={"authkey": key, "searchdate": day.strftime("%Y%m%d"), "data": "AP01"}, timeout=20)
    rows = r.json() if r.status_code == 200 else []
    for row in rows if isinstance(rows, list) else []:
        if row.get("cur_unit") == "USD" and str(row.get("result")) == "1":
            try:
                return float(str(row.get("deal_bas_r")).replace(",", ""))
            except ValueError:
                return None
    return None


def fetch_usdkrw(http=requests.get, now: datetime | None = None) -> dict:
    key = get_secret("KOREAEXIM_API_KEY")
    if not key:
        return {"status": "not_configured", "source": SOURCE}
    now = now or datetime.now(KST)
    found = []
    day = now
    for _ in range(10):  # 주말·휴일은 빈 응답 → 하루씩 거슬러 올라가 최근 2개 고시일을 찾는다
        try:
            rate = _rate_on(day, key, http)
        except (requests.RequestException, ValueError):
            return {"status": "error", "error": "network", "source": SOURCE}
        if rate:
            found.append((day.strftime("%Y%m%d"), rate))
            if len(found) == 2:
                break
        day -= timedelta(days=1)
    if not found:
        return {"status": "error", "error": "empty", "source": SOURCE}
    (as_of, rate), prev = found[0], (found[1][1] if len(found) > 1 else None)
    change = round(rate - prev, 2) if prev else None
    return {
        "status": "ok", "name": "원/달러", "as_of": as_of, "close": rate, "change": change,
        "rate": round(change / prev * 100, 2) if prev and change is not None else None, "source": SOURCE,
    }
