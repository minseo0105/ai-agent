"""공식 홈페이지에서 그린피·캐디/카트비·인원 조건을 추출해 '검토 대기' 후보로 저장한다.

- DB는 수정하지 않는다. 결과는 data/golf/enrichment_review/ 에 저장.
- 공식 홈페이지(record.official_url)와 같은 도메인의 요금/이용안내 페이지만 읽는다.
- Claude가 값마다 원문 인용(quote)을 남기고, 코드가 인용이 실제 페이지에 있는지 재검증한다.

사용:
  venv\\Scripts\\python.exe scripts\\golf_official_enrich.py --pilot 10
  venv\\Scripts\\python.exe scripts\\golf_official_enrich.py --ids id1,id2
"""

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import List, Literal, Optional
from urllib.parse import urljoin, urlsplit

import anthropic
import requests
import urllib3
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.config import get_secret  # noqa: E402
from services import golf_service as gs  # noqa: E402
from services.golf_pricing import fee_summary  # noqa: E402

MODEL = "claude-opus-5"
OUT_DIR = Path("data/golf/enrichment_review")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}
STRONG_WORDS = ("요금", "그린피", "이용요금", "요금안내", "greenfee", "green_fee", "fee", "price", "charge", "rate")
LINK_WORDS = STRONG_WORDS + ("이용안내", "예약안내", "이용료", "예약", "안내", "guide", "reserv", "info", "use", "캐디", "카트")
SKIP_WORDS = ("login", "join", "logout", "member/update", "board", "notice", "event", "popup", "hotel", "spa", "condo",
              "room", "ski", "resort/", "waterpark", "restaurant", "menu", "map", "greeting", "history", "recruit",
              "terms", "privacy", "my-page", "mypage", ".css", ".js", ".png", ".jpg", ".pdf")
MAX_PAGES = 8
MAX_DEPTH = 2
MAX_CHARS_PER_PAGE = 12000
JS_LINK = re.compile(r"""(?:location\.href|location\.replace|window\.open|goUrl|goPage|goMenu|movePage)\s*\(?\s*=?\s*["']([^"']+)["']""")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------- fetch

class Fetcher:
    """일반 HTTP로 먼저 읽고, 막히거나(403/406) 스크립트 렌더링 페이지면 PC의 Edge(Playwright)로 읽는다."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._pw = None
        self._browser = None
        self.browser_used = 0

    def _browser_page(self):
        if self._browser is None:
            try:
                from playwright.sync_api import sync_playwright
                self._pw = sync_playwright().start()
            except Exception:
                self._browser = False
                return None
            # Windows PC에서는 설치된 Edge를, GitHub Actions(Linux)에서는 playwright chromium을 쓴다.
            for options in ({"channel": "msedge"}, {}):
                try:
                    self._browser = self._pw.chromium.launch(headless=True, **options)
                    break
                except Exception:
                    self._browser = False
        return self._browser.new_page() if self._browser else None

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def static(self, url):
        for verify in (True, False):
            try:
                r = self.session.get(url, timeout=12, verify=verify, allow_redirects=True)
            except requests.exceptions.SSLError:
                continue
            except requests.RequestException:
                return None, None
            if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
                r.encoding = r.apparent_encoding
            return r.status_code, (r.url, r.text)
        return None, None

    def rendered(self, url):
        page = self._browser_page()
        if not page:
            return None
        try:
            page.goto(url, wait_until="networkidle", timeout=25000)
            page.wait_for_timeout(800)
            self.browser_used += 1
            return page.url, page.content()
        except Exception:
            return None
        finally:
            page.close()

    def get(self, url):
        status, got = self.static(url)
        if status == 200 and got and len(page_text(got[1])) >= 300:
            return got
        if status in (404, 410):
            return None
        return self.rendered(url) or (got if status == 200 else None)


def page_text(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    # 표는 셀 구분을 살려서 텍스트화
    for cell in soup.find_all(["td", "th"]):
        cell.append(" | ")
    for row in soup.find_all(["tr", "li", "p", "div", "br", "h1", "h2", "h3", "h4"]):
        row.append("\n")
    text = soup.get_text(" ")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def candidate_links(base_url, html):
    """같은 사이트 링크를 요금 관련도로 점수화. [(url, score, is_frame)]"""
    soup = BeautifulSoup(html, "lxml")
    host = urlsplit(base_url).hostname or ""
    root = ".".join(host.split(".")[-2:])
    found = {}

    def add(href, label, is_frame=False):
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            return
        url = urljoin(base_url, href).split("#")[0]
        if not (urlsplit(url).hostname or "").endswith(root):
            return
        text = f"{label} {href}".lower()
        if not is_frame and any(w in text for w in SKIP_WORDS):
            return
        score = sum(3 if w in STRONG_WORDS else 1 for w in LINK_WORDS if w in text) + (10 if is_frame else 0)
        if score:
            prev = found.get(url)
            found[url] = (max(score, prev[0] if prev else 0), is_frame or (prev[1] if prev else False))

    for tag in soup.find_all(["a", "area"]):
        add(tag.get("href"), tag.get_text(" ", strip=True))
        for attr in ("onclick", "data-href", "data-url"):
            if tag.get(attr):
                for m in JS_LINK.findall(tag[attr]) or [tag[attr]]:
                    add(m, tag.get_text(" ", strip=True))
    for tag in soup.find_all(["frame", "iframe"]):
        add(tag.get("src"), "frame", is_frame=True)
    for m in JS_LINK.findall(html):
        add(m, "")
    return [(u, s, f) for u, (s, f) in sorted(found.items(), key=lambda x: -x[1][0])]


def crawl(start_url, fetcher):
    """요금 관련 링크 우선 탐색. 프레임은 깊이에 포함하지 않는다."""
    pages, seen = [], set()
    frontier = [(100, start_url, 0)]  # (우선순위, url, depth)
    while frontier and len(pages) < MAX_PAGES:
        frontier.sort(key=lambda x: -x[0])
        _, url, depth = frontier.pop(0)
        if url in seen:
            continue
        seen.add(url)
        got = fetcher.get(url)
        if not got:
            continue
        final, html = got
        # 리다이렉트로 이미 본 페이지/로그인 페이지에 도착한 경우 건너뛴다.
        if (final != url and final in seen) or (depth > 0 and any(w in final.lower() for w in ("login", "member/"))):
            continue
        seen.add(final)
        text = page_text(html)
        if text:
            pages.append({"url": final, "text": text[:MAX_CHARS_PER_PAGE]})
        for link, score, is_frame in candidate_links(final, html)[:12]:
            next_depth = depth if is_frame else depth + 1
            if link not in seen and next_depth <= MAX_DEPTH:
                frontier.append((score - next_depth, link, next_depth))
        time.sleep(0.2)
    return pages


# ---------------------------------------------------------------- extract

class FeeRow(BaseModel):
    day: Literal["weekday", "weekend", "unspecified"]
    session: Literal["1부", "2부", "3부", "all"]
    customer: Literal["nonmember", "member", "unknown"] = Field(description="비회원/일반=nonmember, 회원가=member")
    holes: int = Field(description="18홀 요금이면 18, 9홀이면 9")
    price_krw: int
    source_url: str
    quote: str = Field(description="금액이 들어 있는 원문 문장/표 행을 페이지에서 그대로 복사")


class TeamFee(BaseModel):
    fee_team_krw: int
    source_url: str
    quote: str


class PlayerRule(BaseModel):
    allowed: bool
    condition: str = Field(description="추가요금·조건. 없으면 빈 문자열")
    source_url: str
    quote: str


class Extraction(BaseModel):
    green_fees: List[FeeRow]
    caddie_fee: Optional[TeamFee]
    cart_fee: Optional[TeamFee]
    caddie_mode: Literal["caddie", "no_caddie", "optional", "unknown"]
    caddie_mode_quote: str
    three_person: Optional[PlayerRule]
    two_person: Optional[PlayerRule]
    notes: str = Field(description="요금 기준일, 시즌 구분 등 참고사항. 없으면 빈 문자열")


PROMPT = """아래는 골프장 '{name}'의 공식 홈페이지에서 가져온 페이지 텍스트입니다.
여기에 **명시적으로 적힌 값만** 추출하세요. 추정하거나 일반 상식으로 채우지 마세요.

- 대상은 정규 골프 코스(18홀 라운드)입니다. 파3 코스·연습장·스크린골프 등 부대시설의 요금과 규정은 모두 제외하세요.
- green_fees: 그린피(1인 기준) 행. 회원가/비회원가를 구분하고, 9홀 요금은 holes=9로 표시.
  customer는 '비회원'·'일반'·'정상요금(일반 고객)'만 nonmember로, 회원·가족회원·지정회원은 member로,
  지역주민·경로·단체·이벤트 할인처럼 조건부 요금은 unknown으로 표시하세요.
  요일은 주중(weekday)/주말·공휴일(weekend)/구분 없음(unspecified), 시간대는 1부/2부/3부/all.
- caddie_fee / cart_fee: 팀당 요금. 없으면 null.
- caddie_mode: 캐디 필수(caddie), 노캐디(no_caddie), 선택 가능(optional), 알 수 없음(unknown).
- three_person / two_person: 정규 코스의 3인·2인 플레이(팀 인원) 허용 여부가 명시된 경우에만. 없으면 null.
  '투 볼 플레이'(한 사람이 공 2개로 치는 것) 자제 같은 경기 에티켓은 팀 인원 규정이 아니므로 제외하세요.
- quote에는 해당 값이 들어 있는 원문을 **글자 그대로** 복사하세요(40~200자). source_url은 그 텍스트가 나온 페이지 URL.
- 값을 찾지 못하면 빈 배열/null/unknown으로 두세요.

{pages}"""


def extract(client, name, pages):
    blob = "\n\n".join(f"=== PAGE: {p['url']} ===\n{p['text']}" for p in pages)
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": PROMPT.format(name=name, pages=blob)}],
        output_format=Extraction,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model refusal")
    return response.parsed_output, response.usage


# ---------------------------------------------------------------- verify

def _norm(s):
    return re.sub(r"[\s|,]+", "", str(s or ""))


def verify_quote(pages, url, quote, amount=None):
    """인용이 해당 페이지(없으면 전체)에 실제로 있는지, 금액 숫자가 인용에 들어 있는지."""
    q = _norm(quote)
    if len(q) < 6:
        return False
    texts = [p["text"] for p in pages if p["url"] == url] or [p["text"] for p in pages]
    found = any(q in _norm(t) for t in texts)
    if not found:
        return False
    if amount is None:
        return True
    digits = str(amount)
    q_digits = re.sub(r"\D", "", quote)
    man = str(amount // 10000) if amount % 10000 == 0 else None
    return digits in q_digits or (man is not None and re.search(rf"{man}\s*만", quote) is not None) \
        or f"{amount:,}" in quote


# ---------------------------------------------------------------- main

def pick_pilot(n):
    _, _, pool = gs.load_pools()
    cands = sorted(
        (c for c in pool if not fee_summary(c) and str(c.get("official_url") or "").startswith("http")
         and c.get("service_status") == "service"),
        key=lambda c: c["id"],
    )
    quota = {"수도권": 4, "충청권": 3, "강원권": 3} if n == 10 else None
    picked = []
    for area in ("수도권", "충청권", "강원권"):
        group = [c for c in cands if c.get("area") == area]
        k = quota[area] if quota else max(1, n // 3)
        step = max(1, len(group) // k)
        picked += group[::step][:k]
    return picked[:n]


def run(clubs, label="manual"):
    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))
    fetcher = Fetcher()
    results, usage_in, usage_out = [], 0, 0
    for club in clubs:
        t0 = time.time()
        item = {"id": club["id"], "name": club["name"], "area": club.get("area"),
                "official_url": club.get("official_url"), "status": "pending_review"}
        try:
            before = fetcher.browser_used
            pages = crawl(club["official_url"], fetcher)
            item["browser_pages"] = fetcher.browser_used - before
            item["pages"] = [{"url": p["url"], "chars": len(p["text"])} for p in pages]
            if not pages or sum(len(p["text"]) for p in pages) < 200:
                item["status"] = "no_content"
                item["error"] = "홈페이지 본문을 가져오지 못함 (접속 실패 또는 이미지/스크립트 렌더링 페이지)"
            else:
                data, usage = extract(client, club["name"], pages)
                usage_in += usage.input_tokens
                usage_out += usage.output_tokens
                ex = data.model_dump()
                for row in ex["green_fees"]:
                    row["verified_quote"] = verify_quote(pages, row["source_url"], row["quote"], row["price_krw"])
                for key in ("caddie_fee", "cart_fee"):
                    if ex[key]:
                        ex[key]["verified_quote"] = verify_quote(pages, ex[key]["source_url"], ex[key]["quote"], ex[key]["fee_team_krw"])
                for key in ("three_person", "two_person"):
                    if ex[key]:
                        ex[key]["verified_quote"] = verify_quote(pages, ex[key]["source_url"], ex[key]["quote"])
                item["extraction"] = ex
                item["usage"] = {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
        except Exception as e:  # 한 곳 실패가 전체를 멈추지 않도록
            item["status"] = "error"
            item["error"] = f"{type(e).__name__}: {e}"[:300]
        item["seconds"] = round(time.time() - t0, 1)
        results.append(item)
        fees = len((item.get("extraction") or {}).get("green_fees") or [])
        print(f"- {club['name']}: {item['status']} pages={len(item.get('pages') or [])} "
              f"browser={item.get('browser_pages', 0)} fees={fees} {item['seconds']}s", flush=True)

    fetcher.close()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"official_enrich_{date.today().isoformat()}_{label}_{int(time.time())}.json"
    payload = {"created_at": date.today().isoformat(), "model": MODEL, "label": label,
               "method": "official_homepage_crawl(v2: static+edge)+llm_extract+quote_verify",
               "usage": {"input_tokens": usage_in, "output_tokens": usage_out}, "results": results}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {out} | tokens in={usage_in:,} out={usage_out:,}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", type=int, default=0)
    ap.add_argument("--ids", default="")
    args = ap.parse_args()
    if args.ids:
        wanted = set(args.ids.split(","))
        _, clubs_all, _ = gs.load_pools()
        targets = [c for c in clubs_all if c["id"] in wanted]
    else:
        targets = pick_pilot(args.pilot or 10)
    print("targets:", [c["name"] for c in targets], flush=True)
    run(targets, label="ids" if args.ids else "pilot")
