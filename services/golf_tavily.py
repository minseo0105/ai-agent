"""Tavily multi-query golf review search. No NAVER dependency."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
import re
import requests

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

class TavilyGolfError(RuntimeError):
    pass

BLOCKED_HOSTS = (
    "instagram.com","facebook.com","youtube.com","youtu.be","tiktok.com",
    "shopping.","smartstore.","booking.","agoda.","expedia."
)
BAD = re.compile(
    r"(광고|협찬|체험단|제공받|이벤트|경품|회원권\s*(매매|분양|시세)|"
    r"해외\s*골프|골프\s*여행|여행\s*전문|예약\s*대행|견적문의|"
    r"log\s*in|sign\s*up|never miss a post|전체메뉴|카테고리\s*이동)", re.I
)
ROUND = re.compile(
    r"(라운딩|라운드|후기|리뷰|플레이|티샷|페어웨이|그린|잔디|"
    r"홀별|코스\s*(공략|관리|상태)|클럽하우스|전반|후반)", re.I
)
TARGET = re.compile(r"레이크\s*사이드\s*(CC|컨트리\s*클럽)?", re.I)

def _five_year_start():
    today = datetime.now(timezone(timedelta(hours=9))).date()
    try: return today.replace(year=today.year-5).isoformat()
    except ValueError: return today.replace(year=today.year-5, day=28).isoformat()

def _date(value, text=""):
    digits = "".join(c for c in str(value or "") if c.isdigit())
    if len(digits) >= 8: return digits[:8]
    m = re.search(r"\b(20(?:2[1-9]|3[0-9]))[.\-/년 ]\s*(0?[1-9]|1[0-2])[.\-/월 ]\s*(0?[1-9]|[12][0-9]|3[01])", text[:5000])
    return f"{int(m.group(1)):04d}{int(m.group(2)):02d}{int(m.group(3)):02d}" if m else ""

def _usable(url, title, content, club_name):
    host = (urlsplit(url).hostname or "").lower()
    if any(x in host for x in BLOCKED_HOSTS): return False
    sample = f"{title} {content[:5000]}"
    if re.sub(r"\\s+","",club_name).lower() not in re.sub(r"\\s+","",sample).lower() or not ROUND.search(sample): return False
    if BAD.search(sample) and not re.search(r"(라운딩|라운드).{0,16}(후기|리뷰)|(?:후기|리뷰).{0,16}(라운딩|라운드)", title, re.I):
        return False
    return True

def _one(api_key, query, max_results=20):
    payload = {
        "query": query, "topic":"general", "search_depth":"advanced",
        "max_results": min(max(int(max_results),5),20),
        "include_answer": False, "include_raw_content":"markdown",
        "start_date": _five_year_start(),
    }
    try:
        r = requests.post(TAVILY_SEARCH_URL,
            headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
            json=payload, timeout=40)
    except requests.RequestException as e:
        raise TavilyGolfError(f"Tavily 연결 실패: {e}") from e
    if r.status_code != 200:
        raise TavilyGolfError(f"Tavily 검색 실패 (HTTP {r.status_code}): {r.text[:250]}")
    return r.json().get("results", [])

def search_golf_reviews(api_key, *, query=None, max_results=20):
    """Compatibility single search."""
    if not api_key: raise TavilyGolfError("TAVILY_API_KEY가 설정되어 있지 않습니다.")
    items = _one(api_key, query or "레이크사이드CC 라운딩 후기", max_results)
    return _normalize(items, query or "레이크사이드CC 라운딩 후기", "레이크사이드CC")

def _normalize(items, query, club_name):
    out = []
    for item in items:
        url, title = item.get("url") or "", item.get("title") or ""
        content = item.get("raw_content") or item.get("content") or ""
        if not _usable(url,title,content,club_name): continue
        postdate = _date(item.get("published_date") or item.get("published_at"), title+"\n"+content)
        out.append({
            "title":title, "description":content[:14000], "url":url,
            "published_at":postdate, "query":query, "score":item.get("score"), "source":"Tavily"
        })
    return out

def search_golf_review_bundle(api_key, club_name="레이크사이드CC"):
    """One user action -> four focused Tavily searches, deduped."""
    if not api_key: raise TavilyGolfError("TAVILY_API_KEY가 설정되어 있지 않습니다.")
    queries = [
        f"{club_name} 라운딩 후기",
        f"{club_name} 코스 라운딩 후기",
        f"{club_name} 페어웨이 그린 난이도 티샷 후기",
        f"{club_name} 잔디 코스관리 시설 클럽하우스 후기",
    ]
    by_url, raw_count = {}, 0
    for q in queries:
        items = _one(api_key, q, 20); raw_count += len(items)
        for rec in _normalize(items, q, club_name):
            # Prefer richer copy for same URL.
            if rec["url"] not in by_url or len(rec["description"]) > len(by_url[rec["url"]]["description"]):
                by_url[rec["url"]] = rec
    records = list(by_url.values())
    records.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    return records, {"queries":len(queries), "raw":raw_count, "unique_valid":len(records)}
