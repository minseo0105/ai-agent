"""뉴스 속 숨은 종목 — '오늘 무슨 일이 있었나'(이슈 발견)용 종합 언론사·방송사 RSS.

출처 목록은 data/stockon/news_sources.json(rss = 피드, general_press = 대표 기사가 될 수 있는 종합지·방송사 도메인).
피드는 제목·링크·발행 시각·요약만 쓰고 기사 원문은 가져오지 않는다. 발행 시각이 없는 기사는 버린다(24시간 규칙을 쓸 수 없다).
기사 수·언론사 수와 관련 기사는 NAVER 뉴스 검색(news.py)으로 따로 센다.
"""

import json
import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from services.stockon.public_data import KST
from services.stockon.safety import clean_text

log = logging.getLogger("stockon.rss")

SOURCES_PATH = Path(__file__).resolve().parents[2] / "data" / "stockon" / "news_sources.json"
UA = "Mozilla/5.0 (compatible; AILAB-StockOn/1.0; +https://ailab)"
TIMEOUT = 12
WORKERS = 6
DC_DATE = "{http://purl.org/dc/elements/1.1/}date"

_cache: dict = {"mtime": None, "value": None}


def sources() -> dict:
    """{"rss": [{press, section, url}], "general_press": {도메인: 언론사 이름}}. 파일이 바뀔 때만 다시 읽는다."""
    try:
        mtime = SOURCES_PATH.stat().st_mtime
        if _cache["mtime"] != mtime:
            raw = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
            _cache.update(mtime=mtime, value={"rss": [f for f in raw.get("rss") or [] if f.get("url")],
                                              "general_press": dict(raw.get("general_press") or {})})
    except (OSError, ValueError) as e:
        log.warning("news sources read failed: %s", type(e).__name__)
        if _cache["value"] is None:
            _cache["value"] = {"rss": [], "general_press": {}}
    return _cache["value"]


def _host(url: str) -> str:
    return (urlparse(url or "").hostname or "").lower()


def press_name(url: str) -> str:
    """종합지·방송사 도메인이면 언론사 이름, 아니면 빈 문자열(경제지·전문지·모르는 곳)."""
    host = _host(url)
    for domain, name in sources()["general_press"].items():
        if host == domain or host.endswith("." + domain):
            return name
    return ""


def general(url: str) -> bool:
    """대표 기사가 될 수 있는 종합지·방송사 기사인지(도메인으로)."""
    return bool(press_name(url))


def _pub(item: ET.Element) -> str | None:
    raw = (item.findtext("pubDate") or item.findtext(DC_DATE) or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw) if not raw[:4].isdigit() else datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST).isoformat()


def parse(text: str | bytes, feed: dict) -> list[dict]:
    """RSS 2.0 → [{title, url, press, press_name, section, pub, snippet, source: 'rss'}]. 발행 시각·링크·제목이 없는 항목은 뺀다."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        log.warning("rss parse %s: %s", feed.get("url"), e)
        return []
    out = []
    for item in root.iter("item"):
        title = clean_text(item.findtext("title"), 200)
        url = (item.findtext("link") or "").strip()
        pub = _pub(item)
        if not title or not pub or not url.startswith(("https://", "http://")):
            continue
        out.append({"title": title, "url": url, "press": _host(url), "press_name": feed.get("press") or press_name(url),
                    "section": feed.get("section") or "", "pub": pub, "snippet": clean_text(item.findtext("description"), 300),
                    "source": "rss"})
    return out


def fetch(feed: dict, http=requests.get) -> list[dict]:
    try:
        r = http(feed["url"], headers={"User-Agent": UA}, timeout=TIMEOUT)
    except requests.RequestException as e:
        log.warning("rss %s: %s", feed["url"], type(e).__name__)
        return []
    if r.status_code != 200:
        log.warning("rss %s: http_%s", feed["url"], r.status_code)
        return []
    return parse(r.content, feed)


def collect(start: datetime, end: datetime, per_feed: int = 30, http=requests.get) -> tuple[list[dict], list[dict]]:
    """[start, end) 안 기사(피드마다 최신 per_feed개, 제목 중복 제거) + 피드별 결과 [{press, section, url, ok, items}](상태 확인용)."""
    feeds = sources()["rss"]
    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="stockon-rss") as pool:
        results = list(pool.map(lambda f: fetch(f, http), feeds))
    out, seen, report = [], set(), []
    for feed, items in zip(feeds, results):
        inside = sorted((a for a in items if start <= datetime.fromisoformat(a["pub"]) < end), key=lambda a: a["pub"], reverse=True)
        report.append({**{k: feed.get(k) for k in ("press", "section", "url")}, "ok": bool(items), "items": len(inside)})
        for a in inside[:per_feed]:
            if a["title"] not in seen:
                seen.add(a["title"])
                out.append(a)
    return out, report
