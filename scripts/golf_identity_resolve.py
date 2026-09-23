"""정보가 부족한 골프장 레코드(VWorld 지도 데이터만 있는 곳)의 신원을 웹 검색 + Claude로 확인한다.

판정: 실제 골프장/영업 여부/기존 레코드 중복/정식명칭/공식 홈페이지/주소/시도/홀 수/일반인 이용 가능 여부
검증: 주소가 검색 결과 원문에 있는지, 홈페이지 도메인이 검색 결과 URL에 있는지 코드로 확인한다.
DB는 수정하지 않는다. 결과는 data/golf/enrichment_review/identity_*.json

사용:
  venv\\Scripts\\python.exe scripts\\golf_identity_resolve.py --ids a,b
  venv\\Scripts\\python.exe scripts\\golf_identity_resolve.py --sparse   # 3권역 정보부족 레코드 전체
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Literal, Optional
from urllib.parse import urlsplit

import anthropic
import requests
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.config import get_secret  # noqa: E402
from services import golf_service as gs  # noqa: E402

MODEL = "claude-opus-5"
OUT_DIR = Path("data/golf/enrichment_review")
MILITARY = re.compile(r"체력단련장|군\s*골프|공군|육군|해군|비행단|사령부")
SUFFIX = re.compile(r"(컨트리클럽|골프클럽|골프리조트|골프앤리조트|골프&리조트|골프코스|골프장|퍼블릭|대중제?|회원제|cc|gc|c\.c|g\.c|\(주\)|주식회사)", re.I)


class Identity(BaseModel):
    is_golf_course: bool = Field(description="실제 골프 코스(연습장·스크린골프 제외)면 true")
    operating: Literal["operating", "closed", "unknown"]
    duplicate_of_id: Optional[str] = Field(description="후보 목록 중 같은 골프장이면 그 id, 아니면 null")
    official_name: str
    official_url: Optional[str] = Field(description="골프장 공식 홈페이지 URL (검색 결과에 나온 것만)")
    address: Optional[str] = Field(description="도로명 또는 지번 주소 (검색 결과에 적힌 그대로)")
    sido: Optional[str] = Field(description="시/도. 예: 경기도, 충청북도, 강원특별자치도, 경상북도")
    holes: Optional[int]
    public_access: Literal["public", "member_only", "military", "unknown"]
    evidence_urls: List[str]
    note: str


PROMPT = """VWorld 지도 데이터에 '{name}'(표시 위치: {area} {city})라는 골프장 레코드가 있습니다. 좌표와 지역 표기는 부정확할 수 있습니다.
아래 웹 검색 결과만 근거로 이 레코드의 실체를 판정하세요. 검색 결과에 없는 사실은 null/unknown으로 두세요.

- duplicate_of_id: 아래 '기존 레코드 후보' 중 같은 골프장(같은 장소의 회원제/대중제 구분, 옛 이름·새 이름 포함)이 있으면 그 id.
  같은 리조트 안의 다른 코스라도 운영 주체와 예약이 같으면 같은 골프장으로 봅니다.
- 군 체력단련장처럼 일반인 이용이 제한되면 public_access=military 또는 member_only.
- official_url은 골프장 자체의 공식 사이트만(예약대행·블로그·뉴스 제외).
- address는 검색 결과 원문에 적힌 주소를 그대로.

기존 레코드 후보:
{candidates}

웹 검색 결과:
{results}"""


def core(name):
    return SUFFIX.sub("", re.sub(r"[\s·.\-_&()]+", "", str(name or "").lower()))


def candidates_for(club, known, k=20):
    kc = core(club["name"])
    scored = sorted(known, key=lambda o: -SequenceMatcher(None, kc, core(o["name"])).ratio())[:k]
    return "\n".join(f"- {o['id']} | {o['name']} | {o.get('region') or ''} {o.get('city') or ''} | {o.get('address') or ''}"
                     for o in scored)


def tavily(query, api_key):
    r = requests.post("https://api.tavily.com/search", timeout=25, headers={"Authorization": f"Bearer {api_key}"},
                      json={"query": query, "search_depth": "basic", "max_results": 6, "include_answer": False})
    r.raise_for_status()
    return r.json().get("results", [])


def verify(identity, results):
    blob = " ".join(f"{x.get('title', '')} {x.get('content', '')}" for x in results)
    norm = lambda s: re.sub(r"[\s,()]", "", str(s or ""))
    address_ok = bool(identity.get("address")) and norm(identity["address"])[:12] in norm(blob)
    domains = {(urlsplit(x.get("url", "")).hostname or "").removeprefix("www.") for x in results}
    url = identity.get("official_url") or ""
    url_ok = bool(url) and (urlsplit(url).hostname or "").removeprefix("www.") in domains
    return {"address_in_results": address_ok, "url_in_results": url_ok}


def resolve(club, known, client, tavily_key):
    item = {"id": club["id"], "name": club["name"], "area": club.get("area"), "city": club.get("city")}
    if MILITARY.search(club["name"]):
        item.update(status="rule", identity={"public_access": "military", "operating": "unknown"})
        return item
    try:
        results = tavily(f"{club['name']} 골프장 {club.get('city') or ''}".strip(), tavily_key)
        if len(results) < 3:
            results += tavily(f"{core(club['name'])} 컨트리클럽 골프", tavily_key)
        text = "\n\n".join(f"[{i}] {x.get('title', '')}\nURL: {x.get('url', '')}\n{(x.get('content') or '')[:900]}"
                           for i, x in enumerate(results))
        resp = client.messages.parse(
            model=MODEL, max_tokens=4000, output_format=Identity,
            messages=[{"role": "user", "content": PROMPT.format(
                name=club["name"], area=club.get("area") or "", city=club.get("city") or "",
                candidates=candidates_for(club, known), results=text)}],
        )
        identity = resp.parsed_output.model_dump()
        item.update(status="resolved", identity=identity, checks=verify(identity, results),
                    usage={"in": resp.usage.input_tokens, "out": resp.usage.output_tokens})
    except Exception as e:
        item.update(status="error", error=f"{type(e).__name__}: {e}"[:300])
    return item


def sparse_targets():
    all_clubs, _, pool = gs.load_pools()
    pool_ids = {c["id"] for c in pool}
    return [c for c in all_clubs if c.get("area") in gs.SUPPORTED_GOLF_AREAS and c["id"] not in pool_ids
            and c["service_status"] == "candidate"], all_clubs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--sparse", action="store_true")
    args = ap.parse_args()

    targets, all_clubs = sparse_targets()
    if args.ids:
        wanted = set(args.ids.split(","))
        targets = [c for c in all_clubs if c["id"] in wanted]
    target_ids = {c["id"] for c in targets}
    known = [c for c in all_clubs if c["id"] not in target_ids and c["service_status"] != "excluded"]

    client = anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY"))
    tavily_key = get_secret("TAVILY_API_KEY")
    print(f"targets {len(targets)}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lambda c: resolve(c, known, client, tavily_key), targets))
    for r in results:
        idn = r.get("identity") or {}
        print(f"- {r['name']}: {r['status']} dup={idn.get('duplicate_of_id')} op={idn.get('operating')} "
              f"access={idn.get('public_access')} sido={idn.get('sido')} holes={idn.get('holes')} "
              f"url={'✓' if (r.get('checks') or {}).get('url_in_results') else '-'} "
              f"addr={'✓' if (r.get('checks') or {}).get('address_in_results') else '-'}", flush=True)

    usage_in = sum((r.get("usage") or {}).get("in", 0) for r in results)
    usage_out = sum((r.get("usage") or {}).get("out", 0) for r in results)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"identity_{date.today().isoformat()}_{int(time.time())}.json"
    out.write_text(json.dumps({"created_at": date.today().isoformat(), "model": MODEL,
                               "usage": {"input_tokens": usage_in, "output_tokens": usage_out},
                               "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {out} | tokens in={usage_in:,} out={usage_out:,} | ~${usage_in / 1e6 * 5 + usage_out / 1e6 * 25:.2f}")


if __name__ == "__main__":
    main()
