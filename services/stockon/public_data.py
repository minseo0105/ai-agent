"""금융위원회 공공데이터(주식시세·지수시세) — 전일 기준(T+1, 기준일 다음 영업일 13시 이후 갱신).

이용허락: 공공누리 제4유형(출처표시·상업적 이용금지·변경금지). 화면에 출처와 기준일을 항상 표시한다.
키: PUBLIC_DATA_API_KEY(ZIP:ON 실거래와 같은 키, 공공데이터포털에서 두 API 활용신청 필요).
"""

from datetime import datetime, timedelta, timezone

import requests

from services.config import get_secret

KST = timezone(timedelta(hours=9))
# 포털 상세기능 이름(_V2)과 같은 주소. 예전 주소(/service/…Service/getStockPriceInfo)는 신규 활용신청 키를 받지 않는다.
BASE = "https://apis.data.go.kr/1160100"
STOCK_URL = f"{BASE}/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2"
INDEX_URL = f"{BASE}/GetMarketIndexInfoService_V2/getStockMarketIndex_V2"
SOURCE_NAME = "금융위원회 공공데이터"
SOURCE_URL = "https://www.data.go.kr/data/15094808/openapi.do"
INDEX_SOURCE_URL = "https://www.data.go.kr/data/15094807/openapi.do"
MARKETS = ("KOSPI", "KOSDAQ")
INDICES = ("코스피", "코스닥")
PAGE = 1000
HEATMAP_N = 40
MOVERS_N = 10
MOVER_MIN_VALUE = 1_000_000_000  # 거래대금 10억 원 미만 종목은 등락 순위에서 뺀다(극소 거래 종목 소음)
TIMEOUT = 25


class PublicDataError(Exception):
    """화면·로그에는 code만 남긴다. 키나 요청 URL은 담지 않는다."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _key() -> str:
    key = get_secret("PUBLIC_DATA_API_KEY")
    if not key:
        raise PublicDataError("not_configured")
    from urllib.parse import unquote
    return unquote(key)  # 인코딩 키를 넣었어도 requests가 다시 인코딩하도록 디코딩 키로 통일


def _get(url: str, params: dict, http=requests.get) -> dict:
    try:
        r = http(url, params={"serviceKey": _key(), "resultType": "json", **params}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise PublicDataError(f"network:{type(e).__name__}")
    text = r.text or ""
    if "SERVICE_KEY_IS_NOT_REGISTERED" in text:
        raise PublicDataError("not_registered")  # 활용신청 전이거나 승인 반영 전
    if "NO_OPENAPI_SERVICE" in text:
        raise PublicDataError("no_such_service")  # 주소·기능 이름이 포털과 다름
    if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in text:
        raise PublicDataError("quota_exceeded")
    try:
        body = r.json()["response"]
    except Exception:
        raise PublicDataError(f"http_{r.status_code}")
    code = str(body.get("header", {}).get("resultCode", ""))
    if code not in ("00", "0"):
        raise PublicDataError(f"result_{code}")
    return body.get("body") or {}


def _items(body: dict) -> list[dict]:
    items = body.get("items") or {}
    item = items.get("item") if isinstance(items, dict) else None
    if isinstance(item, dict):
        return [item]
    return item or []


def _num(v, cast=float):
    try:
        return cast(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _paged(url: str, params: dict, http) -> list[dict]:
    out, page = [], 1
    while True:
        body = _get(url, {**params, "numOfRows": PAGE, "pageNo": page}, http)
        rows = _items(body)
        out.extend(rows)
        total = _num(body.get("totalCount"), int) or 0
        if not rows or len(out) >= total or page >= 10:
            return out
        page += 1


def latest_trading_day(now: datetime | None = None, http=requests.get) -> str:
    """가장 최근 기준일(YYYYMMDD). 삼성전자(005930)의 최근 2주 시세에서 가장 늦은 날짜."""
    now = now or datetime.now(KST)
    begin = (now - timedelta(days=14)).strftime("%Y%m%d")
    body = _get(STOCK_URL, {"likeSrtnCd": "005930", "beginBasDt": begin, "numOfRows": 20, "pageNo": 1}, http)
    days = [str(i.get("basDt")) for i in _items(body) if i.get("basDt")]
    if not days:
        raise PublicDataError("no_recent_data")
    return max(days)


def _stock_row(i: dict) -> dict | None:
    code, name = str(i.get("srtnCd") or "").strip(), str(i.get("itmsNm") or "").strip()
    close, cap = _num(i.get("clpr"), int), _num(i.get("mrktTotAmt"), int)
    if not code or not name or close is None:
        return None
    return {
        "code": code, "name": name, "market": str(i.get("mrktCtg") or ""),
        "close": close, "change": _num(i.get("vs"), int), "rate": _num(i.get("fltRt")),
        "volume": _num(i.get("trqu"), int), "value": _num(i.get("trPrc"), int), "cap": cap,
    }


def fetch_market(http=requests.get, now: datetime | None = None) -> tuple[dict, dict]:
    """(화면용 시장 스냅샷, 전 종목 목록)을 돌려준다. 전 종목 목록은 관리자 검색·관심 종목에만 쓴다."""
    as_of = latest_trading_day(now, http)
    stocks: list[dict] = []
    for market in MARKETS:
        for i in _paged(STOCK_URL, {"basDt": as_of, "mrktCls": market}, http):
            row = _stock_row(i)
            if row:
                row["market"] = row["market"] or market
                stocks.append(row)
    if not stocks:
        raise PublicDataError("empty_market")

    heatmap = {}
    for market in MARKETS:
        rows = sorted((s for s in stocks if s["market"] == market and s["cap"]), key=lambda s: -s["cap"])
        heatmap[market] = rows[:HEATMAP_N]
    liquid = [s for s in stocks if (s["value"] or 0) >= MOVER_MIN_VALUE and s["rate"] is not None]
    movers = {
        "up": sorted(liquid, key=lambda s: -s["rate"])[:MOVERS_N],
        "down": sorted(liquid, key=lambda s: s["rate"])[:MOVERS_N],
        "value": sorted(stocks, key=lambda s: -(s["value"] or 0))[:MOVERS_N],
    }
    up = sum(1 for s in stocks if (s["rate"] or 0) > 0)
    down = sum(1 for s in stocks if (s["rate"] or 0) < 0)
    market = {
        "as_of": as_of,
        "source": {"name": SOURCE_NAME, "url": SOURCE_URL},
        "indices": fetch_indices(as_of, http),
        "heatmap": heatmap,
        "movers": movers,
        "breadth": {"up": up, "down": down, "flat": len(stocks) - up - down, "total": len(stocks)},
        "mover_min_value": MOVER_MIN_VALUE,
    }
    directory = {s["code"]: {k: s[k] for k in ("name", "market", "close", "change", "rate", "cap", "value")} for s in stocks}
    return market, {"as_of": as_of, "stocks": directory}


def fetch_indices(as_of: str, http=requests.get) -> list[dict]:
    """코스피·코스닥 최근 약 30거래일 종가(작은 추이선용)와 기준일 등락."""
    end = datetime.strptime(as_of, "%Y%m%d")
    begin = (end - timedelta(days=50)).strftime("%Y%m%d")
    # endBasDt는 '그 날 미만'(미포함)이다. 기준일을 넣으면 하루 전까지만 와서 전일 지수를 기준일 값으로 보이게 된다.
    end_exclusive = (end + timedelta(days=1)).strftime("%Y%m%d")
    out = []
    for name in INDICES:
        rows = _paged(INDEX_URL, {"idxNm": name, "beginBasDt": begin, "endBasDt": end_exclusive}, http)
        rows = sorted((r for r in rows if str(r.get("idxNm")) == name), key=lambda r: str(r.get("basDt")))
        if not rows:
            out.append({"name": name, "status": "missing"})
            continue
        last = rows[-1]
        out.append({
            "name": name, "as_of": str(last.get("basDt")),
            # 지수 자료가 종목 시세보다 늦게 올라오면 False. 화면·브리핑은 이때 지수를 기준일 값으로 쓰지 않는다.
            "same_day": str(last.get("basDt")) == as_of,
            "close": _num(last.get("clpr")), "change": _num(last.get("vs")), "rate": _num(last.get("fltRt")),
            "series": [{"d": str(r.get("basDt")), "c": _num(r.get("clpr"))} for r in rows[-30:]],
            "source": {"name": SOURCE_NAME, "url": INDEX_SOURCE_URL},
        })
    return out
