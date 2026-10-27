"""뉴스 검색 — NAVER API HUB(네이버 클라우드 플랫폼) 뉴스 검색.

GET https://naverapihub.apigw.ntruss.com/search/v1/news
헤더 X-NCP-APIGW-API-KEY-ID(Client ID) · X-NCP-APIGW-API-KEY(Client Secret), 하루 25,000회.
키: NAVER_SEARCH_CLIENT_ID / NAVER_SEARCH_CLIENT_SECRET (지도 NAVER_MAP_*과 별개, 지도 키로 대신하지 않는다).
제목·링크·검색 요약문만 쓰고 기사 원문은 가져오지 않는다.
"""

from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests

from services.config import get_secret
from services.stockon.safety import clean_text

URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
SOURCE = {"name": "NAVER 뉴스 검색", "url": "https://api.ncloud-docs.com/docs/naver-api-hub-search-news"}

# 카테고리별 검색어. 화면 탭 순서와 같다.
CATEGORIES = [
    ("market", "시장", "코스피 코스닥 증시"),
    ("chip", "반도체", "반도체 업황 주가"),
    ("battery", "2차전지", "2차전지 배터리 주가"),
    ("finance", "금융", "은행 금융지주 주가"),
    ("policy", "정책", "금융위원회 자본시장 정책"),
]


class NewsError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def configured() -> bool:
    return bool(get_secret("NAVER_SEARCH_CLIENT_ID") and get_secret("NAVER_SEARCH_CLIENT_SECRET"))


def date_queries(base: str, day: datetime, kind: str = "stock") -> list[str]:
    """날짜를 넣은 관련도 검색어. 기사가 많은 종목(삼성전자는 35분에 100건)은 최신순 1,000건으로도 전날에
    닿지 못해서, 기사 본문·제목에 흔히 들어가는 날짜 표현으로 찾는다."""
    m, d = day.month, day.day
    if kind == "market":
        return [f"증시 {m}월 {d}일 코스피", f"코스피 {d}일 마감"]
    return [f"{base} {m}월 {d}일", f"{base} {d}일 주가"]


def search_window(query: str, start: datetime, end: datetime, limit: int = 8, max_pages: int = 3,
                  must_contain: str = "", extra_queries: list[str] | None = None, http=requests.get) -> list[dict]:
    """발행 시각이 [start, end)인 기사만. 검색 API에 날짜 조건이 없어
    ① query를 최신순으로 100건씩(최대 max_pages쪽) 넘기며 거르고, 창보다 오래된 기사가 나오면 멈춘다.
    ② extra_queries(날짜 표현을 넣은 검색어)를 관련도순 100건씩 받아 창 안 기사만 더한다.
    must_contain이 있으면 제목에 그 말이 든 기사를 앞에 둔다(같은 날 기사가 많을 때 관련도 우선)."""
    found: list[dict] = []
    seen: set[str] = set()

    def keep(items):
        for n in items:
            pub = datetime.fromisoformat(n["pub"]) if n.get("pub") else None
            if pub and start <= pub < end and n["url"] not in seen:
                seen.add(n["url"])
                found.append(n)

    for page in range(max_pages):
        items, raw = _search(query, display=100, sort="date", start=1 + page * 100, http=http)
        keep(items)
        oldest = min((datetime.fromisoformat(n["pub"]) for n in items if n.get("pub")), default=None)
        if raw < 100 or (oldest and oldest < start):
            break  # 결과 끝이거나 창보다 오래된 기사까지 왔으면 더 넘기지 않는다(중복 제거 전 건수로 판단)
    for q in extra_queries or []:
        if len(found) >= limit * 3:
            break
        keep(_search(q, display=100, sort="sim", http=http)[0])
    if must_contain:
        found.sort(key=lambda n: must_contain not in n["title"])  # 안정 정렬: 같은 그룹 안에서는 찾은 순서 유지
    return found[:limit]


def search(query: str, display: int = 10, sort: str = "date", start: int = 1, http=requests.get) -> list[dict]:
    return _search(query, display, sort, start, http)[0]


def _search(query: str, display: int = 10, sort: str = "date", start: int = 1, http=requests.get) -> tuple[list[dict], int]:
    """(정리한 기사 목록, API가 돌려준 원래 건수). 원래 건수는 쪽 넘김 판단에 쓴다."""
    key_id, key = get_secret("NAVER_SEARCH_CLIENT_ID"), get_secret("NAVER_SEARCH_CLIENT_SECRET")
    if not (key_id and key):
        raise NewsError("not_configured")
    try:
        r = http(URL, params={"query": query, "display": display, "start": start, "sort": sort, "format": "json"},
                 headers={"X-NCP-APIGW-API-KEY-ID": key_id, "X-NCP-APIGW-API-KEY": key}, timeout=15)
    except requests.RequestException as e:
        raise NewsError(f"network:{type(e).__name__}")
    if r.status_code != 200:
        raise NewsError(f"http_{r.status_code}")
    out, seen = [], set()
    raw_items = r.json().get("items") or []
    for item in raw_items:
        url = (item.get("originallink") or item.get("link") or "").strip()
        title = clean_text(item.get("title"), 200)
        if not url.startswith(("https://", "http://")) or not title or title in seen:
            continue
        seen.add(title)
        try:
            pub = parsedate_to_datetime(item.get("pubDate")).isoformat()
        except (TypeError, ValueError):
            pub = None
        out.append({
            "title": title, "url": url, "press": urlparse(url).hostname or "",
            "pub": pub, "snippet": clean_text(item.get("description"), 300),
        })
    return out, len(raw_items)
