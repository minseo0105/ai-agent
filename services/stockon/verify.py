"""뉴스 속 숨은 종목 — 기업 연관성 검증. 뉴스에 나온 단어·업종이 비슷하다는 이유만으로 회사를 잇는 오탐을 막는다.

흐름(이슈 하나, lifemap._finish에서 AI 해석 다음에):
1. 당사자: 기사(제목·요약)에 이름이 실제로 나온 회사만. 상장사 목록·별칭(data/stockon/company_aliases.json)과 대조해
   정식 종목명·종목코드로 바꾸고, 비상장·해외 당사자는 그렇게 표시한다(국내 상장사와의 연결은 2의 검증을 통과할 때만).
   모회사·지주사 연결은 별칭 파일에 근거(source)가 있거나 검증된 근거 자료가 있을 때만.
2. 근거 자료: DART 공시(공급계약 공시 원문·사업보고서에서 당사자 이름이 나온 문장), NAVER 뉴스 검색(제목·요약·링크),
   이슈의 언론사 RSS 요약. 언론사 본문은 가져오지 않는다. 발행 시각이 분석 기준 시각(ref) 뒤인 자료는 쓰지 않는다
   (DART는 접수일만 있어 기준일 전날까지).
3. AI(Sonnet)가 회사마다 관계 종류(계약·공급망·지분·경쟁·사업)와 '근거 문장'(자료 번호 + 자료 그대로의 문장)을 낸다.
   코드가 그 문장(또는 핵심 말 80% 이상)이 그 자료 안에 있는지, 자료에 회사 이름과 이슈(당사자·사건 말)가 함께 나오는지 대조한다.
4. 분류: party(직접 당사자) / indirect(검증된 간접 영향) / industry(단순 업종 참고, 지도에 올리지 않고 등락만) /
   insufficient(근거 부족 — 화면에 보이지 않고 lifemap_verify_log.json에만).
   증거 등급(확률이 아님): 확인됨(공시·공식자료) / 보도 확인(서로 다른 언론사 2곳 이상) / 단일 보도(1곳) / 근거 부족.
   긍정·부정·중립은 근거와 함께 사업 영향 경로가 설명될 때만, 아니면 불확실(unk).

설정: LIFEMAP_VERIFY=1(기본)/0. 끄거나, 검증 중 오류·시간 초과(VERIFY_TIMEOUT)가 나면 지금 방식 결과를 그대로 두고
map.verify.status를 'off'/'unverified'로 남긴다 → 화면 '검증 전'. 저장은 수집기 볼륨(store) JSON·SQLite(공시 원문 캐시)만.
"""

import io
import json
import logging
import os
import re
import sqlite3
import threading
import time
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timedelta
from pathlib import Path

import requests

from services.config import get_secret
from services.stockon import disclosures, lifemap, news, rss, store
from services.stockon.public_data import KST

log = logging.getLogger("stockon.verify")

ALIASES_PATH = Path(__file__).resolve().parents[2] / "data" / "stockon" / "company_aliases.json"
VERIFY_MODEL = "claude-sonnet-5-5"
VERIFY_TIMEOUT = 150         # 이슈 하나 검증 최대 초(넘으면 '검증 전')
REL_KINDS = ("계약", "공급망", "지분", "경쟁", "사업")
INDUSTRY_ONLY = ("같은 업종", "근거 없음")
IMPACTS = ("영향 있음", "영향 없음", "알 수 없음")
DIRECTION = {"긍정": "pos", "부정": "neg", "중립": "neu", "불확실": "unk"}
GRADES = ("확인됨", "보도 확인", "단일 보도", "근거 부족")
KIND_NAME = {"dart": "공시", "news": "뉴스", "rss": "RSS", "official": "공식자료"}
# AI 해석의 관계 → 검증이 실패했을 때 업종 참고로 둘지(경쟁·대체·같은 업종) 근거 부족으로 뺄지(구체적 사업 연결을 주장한 것)
SOFT_CLAIMS = {"경쟁사", "대체재", "같은 업종"}
QUOTE_WORDS = 0.8            # 근거 문장이 자료와 글자 그대로 같지 않을 때: 문장의 말 중 이 비율 이상이 자료에 있어야
NEW_MAX = 2                  # 근거 자료에서 AI가 새로 찾은 회사(예: 발권 시스템 공급사) 최대 수
PER_COMPANY_NEWS = 4
ISSUE_NEWS = 8
DART_DAYS = 365
DART_DOCS = 3                # 이슈 하나에서 여는 공시 원문 수
DART_DOC_MAX = 8_000_000     # 공시 원문(zip) 최대 바이트
LOG_KEEP = 200
IMPACT_BANNED = re.compile(r"수혜|피해|오를|내릴|추천|매수|매도|급등|급락")
WORD = re.compile(r"[0-9A-Za-z가-힣]{2,}")
PARTICLE_NOT = r"(?![은는이가을를의에와과도로만께])[가-힣]"  # 조사가 아닌 한글

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="stockon-verify")
_alias_cache: dict = {"mtime": None, "value": None}
_db_lock = threading.Lock()
_log_lock = threading.Lock()


def enabled() -> bool:
    return (os.environ.get("LIFEMAP_VERIFY") or "1").strip() != "0"


def aliases() -> dict:
    """{"aliases": {이름: {listed, relation, source}}, "unlisted": {이름: 설명}, "foreign": {이름: 설명}}."""
    try:
        mtime = ALIASES_PATH.stat().st_mtime
        if _alias_cache["mtime"] != mtime:
            raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
            _alias_cache.update(mtime=mtime, value={k: dict(raw.get(k) or {}) for k in ("aliases", "unlisted", "foreign")})
    except (OSError, ValueError) as e:
        log.warning("aliases read failed: %s", type(e).__name__)
        if _alias_cache["value"] is None:
            _alias_cache["value"] = {"aliases": {}, "unlisted": {}, "foreign": {}}
    return _alias_cache["value"]


# ---------------------------------------------------------
# 이름이 글에 나오나 · 근거 문장 대조
# ---------------------------------------------------------

def _squash(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (text or "").lower())


def mentions(text: str, name: str) -> bool:
    """name이 text에 나오나. 두 글자 이하·영문 이름은 앞뒤가 다른 글자와 붙어 있지 않을 때만('KT'가 'KTX'에 걸리지 않게,
    한글 조사는 허용)."""
    if not name or not text:
        return False
    if len(name) <= 2 or re.fullmatch(r"[A-Za-z0-9&.\s]+", name):
        # 뒤에는 조사만 허용('애플은'은 되고 '애플리케이션'·'KTX'·'GS건설'의 'GS'는 안 된다)
        return bool(re.search(rf"(?<![0-9A-Za-z가-힣]){re.escape(name)}(?![0-9A-Za-z])(?!{PARTICLE_NOT})", text))
    return _squash(name) in _squash(text)


def names_of(code: str, stocks: dict) -> list[str]:
    """종목코드 → 글에서 찾을 이름들(정식 종목명 + 표기만 다른 별칭)."""
    name = (stocks.get(code) or {}).get("name", "")
    same = [k for k, v in aliases()["aliases"].items() if v.get("listed") == name and v.get("relation") == "같은 회사"]
    return [n for n in [name, *same] if n]


def quote_found(quote: str, text: str) -> bool:
    """AI가 낸 근거 문장이 자료 안에 있나: 글자 그대로(띄어쓰기·문장부호 무시, 8자 이상) 있거나,
    문장의 말(두 글자 이상, 3개 이상) 중 QUOTE_WORDS 이상이 자료에 있다(핵심 내용)."""
    q, t = _squash(quote), _squash(text)
    if not q or not t:
        return False
    if len(q) >= 8 and q in t:
        return True
    words = WORD.findall(quote or "")
    return len(words) >= 3 and sum(_squash(w) in t for w in words) / len(words) >= QUOTE_WORDS


# ---------------------------------------------------------
# 근거 자료 모으기: RSS 요약 · NAVER 검색 · DART
# ---------------------------------------------------------

def _pub(value) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _press(a: dict) -> str:
    return a.get("press_name") or rss.press_name(a.get("url") or "") or (a.get("press") or "").removeprefix("www.")


class Corpus:
    """번호 붙은 근거 자료 목록. 기준 시각 뒤 자료·주소 중복은 넣지 않는다(뺀 수는 after_ref)."""

    def __init__(self, ref: datetime, checked: str):
        self.ref, self.checked = ref, checked
        self.items: list[dict] = []
        self.urls: set[str] = set()
        self.after_ref = 0

    def add(self, kind: str, title: str, text: str, url: str, press: str, pub: str | None, **extra) -> dict | None:
        when = _pub(pub)
        if not url or url in self.urls or not when:
            return None
        if when > self.ref:
            self.after_ref += 1
            return None
        self.urls.add(url)
        item = {"n": len(self.items) + 1, "kind": kind, "title": (title or "")[:200], "text": (text or "")[:600], "url": url,
                "press": press, "pub": when.isoformat(), "checked": self.checked, **extra}
        self.items.append(item)
        return item

    def add_article(self, a: dict, kind: str) -> dict | None:
        return self.add(kind, a.get("title", ""), f"{a.get('title', '')} {a.get('snippet') or ''}", a.get("url", ""), _press(a), a.get("pub"))


def _search(query: str, display: int, http) -> list[dict]:
    try:
        return news.search(query, display=display, sort="sim", **({"http": http} if http else {}))
    except news.NewsError as e:
        log.warning("verify search %s: %s", query, e.code)
        return []


# --- DART: 공시 목록(1년) → 공급계약 공시·사업보고서 원문에서 당사자 이름이 나온 문장 ---

def _db() -> sqlite3.Connection:
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(store.DATA_DIR / "verify_cache.sqlite", timeout=10)
    con.execute("CREATE TABLE IF NOT EXISTS dart_doc (rcept_no TEXT PRIMARY KEY, text BLOB, ts REAL)")
    return con


def dart_text(rcept_no: str, http=requests.get) -> str:
    """공시 원문 글자(태그 제거). 한 번 연 원문은 볼륨의 SQLite에 압축해 둔다."""
    with _db_lock:
        con = _db()
        try:
            row = con.execute("SELECT text FROM dart_doc WHERE rcept_no=?", (rcept_no,)).fetchone()
        finally:
            con.close()
    if row:
        return zlib.decompress(row[0]).decode("utf-8")
    key = get_secret("DART_API_KEY")
    if not key:
        return ""
    try:
        r = http("https://opendart.fss.or.kr/api/document.xml", params={"crtfc_key": key, "rcept_no": rcept_no}, timeout=25)
        blob = r.content if r.status_code == 200 else b""
    except requests.RequestException as e:
        log.warning("dart doc %s: %s", rcept_no, type(e).__name__)
        return ""
    if not blob.startswith(b"PK") or len(blob) > DART_DOC_MAX:
        return ""
    parts = []
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for n in z.namelist():
                raw = z.read(n)
                for enc in ("utf-8", "euc-kr"):
                    try:
                        parts.append(raw.decode(enc))
                        break
                    except UnicodeDecodeError:
                        continue
    except zipfile.BadZipFile:
        return ""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", " ".join(parts))).strip()
    with _db_lock:
        con = _db()
        try:
            con.execute("INSERT OR REPLACE INTO dart_doc VALUES (?,?,?)", (rcept_no, zlib.compress(text.encode("utf-8")), time.time()))
            con.commit()
        finally:
            con.close()
    return text


def dart_filings(name: str, ref: datetime, http=requests.get) -> list[dict]:
    """회사의 최근 1년 공시(접수일이 기준일 전날까지 — 접수 시각을 알 수 없어 같은 날은 쓰지 않는다)."""
    key = get_secret("DART_API_KEY")
    codes = disclosures.corp_codes_for(name)
    if not key or not codes:
        return []
    params = {"crtfc_key": key, "corp_code": codes[0], "bgn_de": (ref - timedelta(days=DART_DAYS)).strftime("%Y%m%d"),
              "end_de": ref.strftime("%Y%m%d"), "page_count": 100}
    try:
        data = http(disclosures.URL, params=params, timeout=20).json()
    except (requests.RequestException, ValueError) as e:
        log.warning("dart list %s: %s", name, type(e).__name__)
        return []
    if data.get("status") != "000":
        return []
    day = ref.strftime("%Y%m%d")
    return [i for i in data.get("list") or [] if i.get("rcept_no") and (i.get("rcept_dt") or "99999999") < day]


def _excerpts(text: str, names: list[str], width: int = 90, limit: int = 3) -> str:
    out = []
    for n in names:
        for m in re.finditer(re.escape(n), text):
            out.append(text[max(0, m.start() - width): m.end() + width])
            if len(out) >= limit:
                return " … ".join(out)
    return " … ".join(out)


def dart_evidence(corpus: Corpus, company: dict, counterparties: list[str], supply_claim: bool, docs_left: list[int], http=requests.get) -> int:
    """회사의 공급계약 공시(단일판매·공급계약)와, 공급망을 주장했으면 최근 사업보고서 원문에서 당사자 이름이 나온 문장을 근거로 넣는다."""
    if not counterparties:
        return 0
    filings = dart_filings(company["name"], corpus.ref, http)
    contracts = [f for f in filings if re.search(r"공급계약|판매.?공급", f.get("report_nm", ""))][:2]
    reports = [f for f in filings if (f.get("report_nm") or "").strip().startswith("사업보고서")][:1] if supply_claim else []
    added = 0
    for f in contracts + reports:
        if docs_left[0] <= 0:
            break
        docs_left[0] -= 1
        text = dart_text(f["rcept_no"], http)
        found = _excerpts(text, counterparties)
        if found:
            d = f["rcept_dt"]
            item = corpus.add("dart", f"{company['name']} {f.get('report_nm', '').strip()}", found,
                              disclosures.view_url(f["rcept_no"]), "DART 전자공시", f"{d[:4]}-{d[4:6]}-{d[6:]}T00:00:00+09:00",
                              filer=company["code"])
            added += bool(item)
    return added


# ---------------------------------------------------------
# AI: 회사마다 관계 종류 + 근거 문장
# ---------------------------------------------------------

VERIFY_SYSTEM = """너는 뉴스와 상장사의 연결을 검증하는 사실 확인 담당자다. 주어진 '근거 자료' 안에 실제로 적힌 내용만으로 판단한다.
규칙:
- parties: 기사에 이름이 나온 사건의 주체(회사·기관) 이름을 기사에 적힌 그대로. kind는 '국내 상장'/'국내 비상장'/'해외'/'모름'.
- companies: '후보 회사' 각각과, 근거 자료에서 이 사건과 직접 이어진다고 적혀 있는 다른 한국 상장사(예: 사고가 난 시스템의 공급사)를 판단한다.
  · relation: 근거 자료에 적힌 관계 — '계약'(사건 당사자와 계약), '공급망'(당사자·제품의 공급사·고객사), '지분'(당사자 지분 보유),
    '경쟁'(같은 제품·서비스로 당사자와 경쟁한다고 자료에 적힘), '사업'(사건이 그 회사의 같은 제품·서비스에 직접 닿는다고 자료에 적힘).
    자료에 그런 내용이 없고 업종만 같으면 '같은 업종', 아무 근거도 없으면 '근거 없음'.
  · evidence: 그 관계를 보여 주는 자료 번호(n)와 quote = 그 자료에 있는 문장을 글자 그대로 옮긴 것(60자 이내). 자료에 없는 문장을 만들지 않는다.
    회사 이름과 이 사건(당사자나 사건 내용)이 함께 나오는 자료만 쓴다. 근거가 없으면 빈 목록.
  · impact: 자료에 그 회사가 이 사건으로 실제 영향을 받았다(받을 수 있다)고 적혀 있으면 '영향 있음', 영향이 없었거나 미미했다고
    적혀 있으면(예: '정상적으로 운영했다', '큰 문제는 없었다') '영향 없음', 알 수 없으면 '알 수 없음'.
  · path: 근거 자료로 설명되는 사업 영향 경로 한 줄(40자 이내, 예: '발권 시스템을 공급해 복구·보상 책임이 생길 수 있다'). 설명할 수 없으면 빈 문자열.
  · direction: path가 있을 때만 '긍정'/'부정'/'중립', 없거나 판단이 어려우면 '불확실'.
- 회사 이름은 상장 종목명 그대로. 업종이 같다·비슷한 단어가 나온다는 이유만으로 관계를 만들지 않는다.
- 금지: 주가 방향 예측, '수혜', '피해', '오를 것', '추천', 매수·매도. 주가 변동과 뉴스의 인과를 단정하지 않는다. 한국어."""

VERIFY_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["parties", "companies"],
    "properties": {
        "parties": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "kind"],
            "properties": {"name": {"type": "string"}, "kind": {"type": "string", "enum": ["국내 상장", "국내 비상장", "해외", "모름"]}}}},
        "companies": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "relation", "evidence", "impact", "path", "direction"],
            "properties": {
                "name": {"type": "string"},
                "relation": {"type": "string", "enum": [*REL_KINDS, *INDUSTRY_ONLY]},
                "evidence": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["n", "quote"],
                    "properties": {"n": {"type": "integer"}, "quote": {"type": "string"}}}},
                "impact": {"type": "string", "enum": list(IMPACTS)},
                "path": {"type": "string"},
                "direction": {"type": "string", "enum": list(DIRECTION)}}}},
    },
}


# ---------------------------------------------------------
# 당사자
# ---------------------------------------------------------

def find_parties(names: list[tuple[str, str]], text: str, stocks: dict, index: dict) -> tuple[list[dict], list[dict]]:
    """(이름, AI가 본 종류) 목록 → (상장 당사자 [{code, name, via?, source?}], 비상장·해외 당사자 [{name, kind}]).
    기사 글(text)에 이름이 실제로 나온 것만. 상장 여부는 AI가 아니라 종목 목록·별칭 파일로 정한다."""
    al = aliases()
    listed: dict[str, dict] = {}
    others: dict[str, dict] = {}
    for name, ai_kind in names:
        name = lifemap.normalize_word(name)[:30]
        if not name or not mentions(text, name):
            continue
        code = lifemap.match_company(name, index)
        alias = al["aliases"].get(name)
        if code:
            listed.setdefault(code, {"code": code, "name": stocks[code]["name"]})
        elif alias and alias.get("listed") and lifemap.match_company(alias["listed"], index):
            code = lifemap.match_company(alias["listed"], index)
            if alias.get("relation") == "같은 회사":
                listed.setdefault(code, {"code": code, "name": stocks[code]["name"]})
            elif alias.get("source"):  # 모회사·지주사: 근거가 적힌 것만
                listed.setdefault(code, {"code": code, "name": stocks[code]["name"], "via": name, "source": alias["source"]})
            others.setdefault(name, {"name": name, "kind": "국내 비상장", "note": f"{stocks[code]['name']} 자회사"})
        elif name in al["unlisted"] or (alias and alias.get("relation") == "비상장"):
            others.setdefault(name, {"name": name, "kind": "국내 비상장", "note": al["unlisted"].get(name) or alias.get("source", "")})
        elif name in al["foreign"]:
            others.setdefault(name, {"name": name, "kind": "해외", "note": al["foreign"][name]})
        elif ai_kind in ("국내 비상장", "해외"):
            others.setdefault(name, {"name": name, "kind": ai_kind, "note": "종목 목록에 없음"})
    # 같은 기관의 짧은 이름과 긴 이름이 둘 다 있으면 긴 것만('인천공항' 설명에 '인천국제공항공사'가 있다)
    rest = list(others.values())
    rest = [o for o in rest if not any(o is not p and o["kind"] == p["kind"] and (o["name"] in p["name"] or p["name"] in o.get("note", ""))
                                       for p in rest)]
    return list(listed.values()), rest


def known_parties(text: str) -> list[tuple[str, str]]:
    """별칭·비상장·해외 목록에 있는 이름 중 기사에 나온 것(AI가 빠뜨려도 당사자로 본다)."""
    al = aliases()
    return [(n, "") for group in ("aliases", "unlisted", "foreign") for n in al[group] if mentions(text, n)]


# ---------------------------------------------------------
# 이슈 하나 검증
# ---------------------------------------------------------

def _grade(items: list[dict]) -> str:
    if any(i["kind"] in ("dart", "official") for i in items):
        return "확인됨"
    presses = {i["press"] for i in items if i["kind"] in ("news", "rss")}
    return "보도 확인" if len(presses) >= 2 else "단일 보도" if presses else "근거 부족"


def _source(i: dict, quote: str = "") -> dict:
    return {"kind": KIND_NAME[i["kind"]], "title": i["title"], "url": i["url"], "press": i["press"], "pub": i["pub"],
            "checked": i["checked"], **({"quote": quote[:80]} if quote and not lifemap._unsafe(quote) else {})}


def tied(text: str, party_names: list[str], event_words: list[str]) -> bool:
    """자료가 이 사건 이야기인지: 당사자 이름이 나오거나, 사건 말(이슈 이름·검색어)이 둘 이상(말이 하나뿐이면 그 하나) 나온다.
    '게임'처럼 업종 말 하나만 겹치는 기사로 회사를 잇지 않게."""
    if any(mentions(text, n) for n in party_names):
        return True
    return bool(event_words) and sum(mentions(text, w) for w in event_words) >= min(2, len(event_words))


def check_claims(claim: dict, names: list[str], party_names: list[str], event_words: list[str], corpus: Corpus,
                 code: str) -> list[tuple[dict, str]]:
    """AI가 낸 근거(자료 번호 + 문장) 중 코드 대조를 통과한 것 [(자료, 문장)]: 번호가 있고, 문장이 그 자료에 있고,
    자료에 회사 이름(공시는 그 회사가 낸 것)과 이 사건(tied)이 함께 나온다."""
    ok = []
    for ev in claim.get("evidence") or []:
        n, quote = ev.get("n"), str(ev.get("quote") or "")
        if not isinstance(n, int) or not 1 <= n <= len(corpus.items):
            continue
        item = corpus.items[n - 1]
        text = f"{item['title']} {item['text']}"
        named = item.get("filer") == code or any(mentions(text, x) for x in names)
        if named and tied(text, party_names, event_words) and quote_found(quote, text):
            ok.append((item, quote))
    return ok


def _direction(claim: dict, verified: bool) -> tuple[str, str]:
    path = lifemap.normalize_word(str(claim.get("path") or ""))[:50]
    if not verified or not path or lifemap._unsafe(path) or IMPACT_BANNED.search(path):
        return "unk", ""
    return DIRECTION.get(claim.get("direction"), "unk"), path


def _rows(m: dict) -> list[dict]:
    return [c for st in m.get("stages") or [] for c in st.get("companies") or []]


def collect(t: dict, m: dict, context: list[dict], ref: datetime, http=None) -> tuple[Corpus, list[tuple[str, str]], str]:
    """근거 자료 모으기 → (자료, 먼저 아는 당사자 [(이름, 종류)], 기사 글). 이슈 검색(당사자·사건과 함께 나온 회사 찾기) →
    회사별 검색(회사 이름이 나온 기사만) → 공시."""
    stocks, index, _ = lifemap.directory()
    corpus = Corpus(ref, datetime.now(KST).isoformat(timespec="seconds"))
    for a in context:
        corpus.add_article(a, "rss" if a.get("source") == "rss" else "news")
    article_text = " ".join(f"{a.get('title', '')} {a.get('snippet') or ''}" for a in context)
    rows = _rows(m)
    pre_parties = [(c["name"], "국내 상장") for c in rows if c.get("party")] + known_parties(article_text)
    anchor = next((n for n, _ in pre_parties if not lifemap.match_company(n, index)), "") or t.get("query") or t["name"]
    for a in _search(t.get("query") or t["name"], 30, http)[:ISSUE_NEWS]:
        corpus.add_article(a, "news")
    named_in_article = {c["code"] for c in rows if any(mentions(article_text, n) for n in names_of(c["code"], stocks))}
    for c in rows:
        if c["code"] in named_in_article:
            continue
        found = [a for a in _search(f"{c['name']} {anchor}", 20, http) if any(mentions(f"{a['title']} {a.get('snippet') or ''}", n)
                                                                             for n in names_of(c["code"], stocks))]
        for a in found[:PER_COMPANY_NEWS]:
            corpus.add_article(a, "news")
    docs_left = [DART_DOCS]
    for c in rows:
        if c["code"] not in named_in_article:
            own = set(names_of(c["code"], stocks))
            dart_evidence(corpus, c, [n for n, _ in pre_parties if n not in own], c.get("relation") in ("공급사", "고객사"),
                          docs_left, http or requests.get)
    return corpus, pre_parties, article_text


def ask(t: dict, m: dict, corpus: Corpus) -> dict:
    payload = {"이슈": t["name"], "제목": t.get("title", ""), "후보 회사": [
        {"이름": c["name"], "AI 해석의 관계": c.get("relation", ""), "AI 해석의 이유": c.get("reason", "")} for c in _rows(m)],
               "근거 자료": [{"n": i["n"], "종류": KIND_NAME[i["kind"]], "출처": i["press"], "제목": i["title"], "내용": i["text"]}
                         for i in corpus.items]}
    return lifemap._ask(VERIFY_MODEL, VERIFY_SYSTEM, f"'{t['name']}' 뉴스의 당사자와 후보 회사의 관계를 근거 자료로 검증하라.",
                        payload, VERIFY_SCHEMA, 4000) or {}


def _verify(t: dict, m: dict, context: list[dict], ref: datetime, http=None) -> dict:
    corpus, pre_parties, article_text = collect(t, m, context, ref, http)
    return classify(t, m, corpus, ask(t, m, corpus), pre_parties, article_text)


def classify(t: dict, m: dict, corpus: Corpus, raw: dict, pre_parties: list[tuple[str, str]], article_text: str) -> dict:
    """AI 답(raw)을 코드로 대조해 회사마다 tier·grade·근거를 붙인 새 지도. 근거 부족은 지도에서 빼고 verify.dropped에."""
    stocks, index, _ = lifemap.directory()
    checked = corpus.checked
    listed, others = find_parties(pre_parties + [(p.get("name", ""), p.get("kind", "")) for p in raw.get("parties") or []],
                                  article_text, stocks, index)
    party_codes = {p["code"]: p for p in listed}
    party_names = [n for n, _ in pre_parties] + [o["name"] for o in others] + [p["name"] for p in listed]
    event_words = sorted(lifemap._event_words(t), key=len, reverse=True)
    claims = {}
    for cl in raw.get("companies") or []:
        code = lifemap.match_company(str(cl.get("name") or ""), index)
        if code and code not in claims:
            claims[code] = cl

    dropped, counts = [], {"party": 0, "indirect": 0, "industry": 0, "insufficient": 0}

    def judge(c: dict) -> dict | None:
        code = c["code"]
        names = names_of(code, stocks)
        cl = claims.get(code, {})
        if code in party_codes:
            p = party_codes[code]
            mention = [i for i in corpus.items if i["kind"] in ("rss", "news") and any(mentions(f"{i['title']} {i['text']}", n) for n in names)]
            if p.get("via"):
                srcs = [{"kind": "공식자료", "title": p["source"], "url": "", "press": "", "pub": "", "checked": checked}]
                tier, grade, rel = "party", "확인됨", "지분"
            else:
                srcs = [_source(i) for i in mention[:3]]
                tier, grade, rel = "party", _grade(mention) if mention else "단일 보도", "당사자"
            direction, path = _direction(cl, True)
            return {**c, "party": True, "hop": 0, "tier": tier, "grade": grade, "rel_kind": rel, "sources": srcs,
                    "direction": direction, **({"path": path} if path else {})}
        # AI 해석이 당사자·모회사라 했어도 기사에 이름이 없으면 근거 자료(지분 등)로 검증될 때만 남긴다
        rel = cl.get("relation") or "근거 없음"
        ok = check_claims(cl, names, party_names, event_words, corpus, code) if rel in REL_KINDS else []
        if ok and cl.get("impact") == "영향 없음":  # 자료가 '영향 없었다'고 하면 연결이 아니라 같은 업종 참고
            ok, rel = [], "같은 업종"
        if ok:
            direction, path = _direction(cl, True)
            return {**c, "party": False, "hop": max(1, c.get("hop") or 1), "tier": "indirect", "grade": _grade([i for i, _ in ok]),
                    "rel_kind": rel, "sources": [_source(i, q) for i, q in ok[:3]], "direction": direction, **({"path": path} if path else {})}
        why = ("기사에 이름 없음" if c.get("party") else "보도상 영향 없음" if cl.get("impact") == "영향 없음" else
               "업종만 같음" if rel == "같은 업종" else "근거 없음" if rel == "근거 없음" else "근거 문장이 자료에 없음")
        # 업종 참고: AI 검증이 '같은 업종'이라 했거나, AI 해석이 원래 경쟁·대체·같은 업종(약한 연결)이라 한 회사.
        # 공급·고객·사고 대응·규제·지분처럼 구체적 연결을 주장했는데 근거가 없으면 근거 부족(화면에서 뺀다)
        if not c.get("party") and (rel == "같은 업종" or c.get("relation") in SOFT_CLAIMS):
            return {**c, "party": False, "tier": "industry", "grade": "근거 부족", "rel_kind": "같은 업종", "sources": [],
                    "direction": "unk", "relevance": "약", "note": why}
        dropped.append({"code": code, "name": c["name"], "claimed": c.get("relation", ""), "ai_relation": rel, "why": why})
        return None

    stages = []
    seen: set[str] = set()
    for st in m.get("stages") or []:
        out = []
        for c in st.get("companies") or []:
            row = judge(c)
            if row:
                seen.add(row["code"])
                counts[row["tier"]] += 1
                out.append(row)
        if out:
            stages.append({**st, "key": f"p{len(stages)}", "companies": out})
    counts["insufficient"] = len(dropped)

    # AI 해석에 없던 상장 당사자(별칭으로 찾은 모회사 등)와 근거 자료에서 새로 찾은 회사(검증 통과만)
    extra = []
    for code, p in party_codes.items():
        if code not in seen and len(seen) < lifemap.COMPANIES_MAX:
            row = judge({"code": code, "name": p["name"], "relevance": "강", "reason": f"{p.get('via') or p['name']} 뉴스의 당사자",
                         "direction": "unk", "link": "직접 당사자"})
            if row:
                seen.add(code)
                counts["party"] += 1
                extra.append(row)
    if extra:
        stages.insert(0, {"key": "p_party", "label": "뉴스 당사자", "detail": "", "companies": extra})
    new = []
    for code, cl in claims.items():
        if code in seen or len(new) >= NEW_MAX or len(seen) >= lifemap.COMPANIES_MAX or cl.get("relation") not in REL_KINDS \
                or cl.get("impact") == "영향 없음":
            continue
        ok = check_claims(cl, names_of(code, stocks), party_names, event_words, corpus, code)
        if ok:
            direction, path = _direction(cl, True)
            new.append({"code": code, "name": stocks[code]["name"], "relevance": "중", "reason": path or f"{cl['relation']} 관계로 알려진 회사",
                        "direction": direction, "relation": cl["relation"], "hop": 1, "party": False,
                        "tier": "indirect", "grade": _grade([i for i, _ in ok]), "rel_kind": cl["relation"],
                        "sources": [_source(i, q) for i, q in ok[:3]], "found": True, **({"path": path} if path else {})})
            seen.add(code)
            counts["indirect"] += 1
    if new:
        stages.append({"key": f"p{len(stages)}", "label": "근거로 확인된 연결", "detail": "", "companies": new})
    for i, st in enumerate(stages):
        st["key"] = f"p{i}"
    listed_n = counts["party"] + counts["indirect"]
    verify = {"status": "ok", "checked": checked, "ref": corpus.ref.isoformat(), "model": VERIFY_MODEL, "listed": listed_n,
              "counts": counts, "evidence": len(corpus.items), "after_ref": corpus.after_ref, "dropped": dropped}
    return {**m, "stages": stages, "parties": others + [{"name": p["name"], "kind": "국내 상장", "code": p["code"],
                                                         **({"via": p["via"]} if p.get("via") else {})} for p in listed],
            "verify": verify}


def verify_map(t: dict, m: dict, context: list[dict], ref: datetime, http=None) -> dict:
    """이슈 하나의 회사 지도를 검증해 새 지도를 돌려준다. 꺼져 있거나 오류·시간 초과면 지금 결과 + verify.status
    ('off'/'unverified') → 화면 '검증 전'. 결과는 lifemap_verify_log.json에도 남긴다(근거 부족으로 뺀 회사 포함)."""
    if not enabled():
        return {**m, "verify": {"status": "off"}}
    started = time.time()
    future = _pool.submit(_verify, t, json.loads(json.dumps(m)), context, ref, http)
    try:
        out = future.result(timeout=VERIFY_TIMEOUT)
    except FutureTimeout:
        out = {**m, "verify": {"status": "unverified", "error": "timeout"}}
    except Exception as e:  # 검증이 안 되면 지금 방식 결과를 그대로(화면이 비지 않게)
        log.warning("verify %s failed: %s", t.get("name"), type(e).__name__)
        out = {**m, "verify": {"status": "unverified", "error": f"{type(e).__name__}: {str(e)[:100]}"}}
    out["verify"]["sec"] = round(time.time() - started, 1)
    write_log(t, out)
    return out


def write_log(t: dict, m: dict) -> None:
    v = m.get("verify") or {}
    row = {"ts": time.time(), "issue": t.get("name"), "title": t.get("title"), **{k: v.get(k) for k in ("status", "error", "ref", "sec", "counts", "after_ref")},
           "companies": [{k: c.get(k) for k in ("code", "name", "tier", "grade", "rel_kind", "relation", "direction")}
                         for st in m.get("stages") or [] for c in st.get("companies") or []],
           "parties": m.get("parties") or [], "dropped": v.get("dropped") or []}
    try:
        with _log_lock:
            rows = (store.read("lifemap_verify_log", []) or [])[-(LOG_KEEP - 1):]
            store.write("lifemap_verify_log", rows + [row])
    except Exception as e:
        log.warning("verify log write failed: %s", type(e).__name__)
