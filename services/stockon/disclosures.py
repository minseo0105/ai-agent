"""DART 공시 목록 — 팀 관심 종목의 최근 공시. 키: DART_API_KEY(AI 에이전트와 같은 키)."""

from datetime import datetime, timedelta

import requests

from services.agent import load_corp_codes
from services.config import get_secret
from services.stockon.public_data import KST

URL = "https://opendart.fss.or.kr/api/list.json"
SOURCE = {"name": "DART 전자공시", "url": "https://dart.fss.or.kr"}


def view_url(rcept_no: str) -> str:
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


def corp_codes_for(name: str) -> list[str]:
    """종목명 → DART 고유번호. 정확히 같은 이름만 쓴다(비슷한 이름의 다른 회사 공시를 붙이지 않게)."""
    try:
        corp_map = load_corp_codes()
    except Exception:
        return []
    norm = name.replace(" ", "").lower()
    for n, codes in corp_map.items():
        if n.replace(" ", "").lower() == norm:
            return list(codes)
    return []


def recent(name: str, days: int = 14, http=requests.get, now: datetime | None = None) -> list[dict]:
    key = get_secret("DART_API_KEY")
    codes = corp_codes_for(name)
    if not key or not codes:
        return []
    now = now or datetime.now(KST)
    params = {"crtfc_key": key, "bgn_de": (now - timedelta(days=days)).strftime("%Y%m%d"),
              "end_de": now.strftime("%Y%m%d"), "page_count": 10}
    for code in codes:
        try:
            data = http(URL, params={**params, "corp_code": code}, timeout=20).json()
        except (requests.RequestException, ValueError):
            continue
        if data.get("status") == "000" and data.get("list"):
            # 회사가 직접 낸 공시만. 임원·주요주주 소유상황보고서(개인 제출), 대량보유보고서(다른 회사 제출)는
            # 같은 제목으로 여러 종목에 겹쳐 보여서 뺀다.
            own = [i for i in data["list"] if i.get("rcept_no") and (i.get("flr_nm") or "").strip() == (i.get("corp_name") or "").strip()]
            return [{"title": i.get("report_nm", "").strip(), "date": i.get("rcept_dt"),
                     "url": view_url(i.get("rcept_no", ""))} for i in own[:5]]
    return []
