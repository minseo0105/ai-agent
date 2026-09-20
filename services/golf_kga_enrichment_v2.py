import json
import re
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parents[1]
CATALOG_PATH = BASE_DIR / "data" / "golf" / "catalog.json"
REPORT_PATH = BASE_DIR / "data" / "golf" / "kga_match_diagnostic_v2.json"

KGA_CALCULATOR_URL = "https://www.kgagolf.or.kr/web/handicap/calculator"

REGIONS = {
    "서울","경기","인천","강원","충북","충남","대전","세종",
    "경북","경남","대구","부산","울산","전북","전남","광주","제주"
}
SKIP = {
    "NO","지역","골프장","코스","주소","검색","선택","핸디캡",
    "코스레이팅™ & 슬로프레이팅™ 데이터베이스"
}

def _clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()

def _norm(v):
    s = _clean(v).lower()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"[^0-9a-z가-힣]", "", s)
    for t in ("컨트리클럽","골프클럽","골프장","countryclub","golfclub","cc","gc"):
        s = s.replace(t, "")
    return s

def _looks_address(s):
    s = _clean(s)
    return bool(
        re.search(r"(특별자치도|특별자치시|광역시|경기도|강원도|충청|전라|경상|제주|"
                  r"서울|경기|인천|강원|충북|충남|대전|세종|경북|경남|대구|부산|울산|전북|전남|광주)"
                  r".*(시|군|구|읍|면|동|로|길|산)\b?", s)
        and re.search(r"\d", s)
    )

def fetch_kga_rows():
    """KGA 공개 코스레이팅 DB의 화면 텍스트를 파싱한다. pandas/read_html을 쓰지 않는다."""
    r = requests.get(
        KGA_CALCULATOR_URL,
        timeout=40,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # script/style/nav 등 잡음 제거
    for tag in soup(["script","style","noscript","svg"]):
        tag.decompose()

    raw = [_clean(x) for x in soup.stripped_strings]
    tokens = [x for x in raw if x and x not in SKIP]

    # DB 시작점 이후만 사용
    start = 0
    for i, x in enumerate(raw):
        if "코스레이팅" in x and "슬로프레이팅" in x and "데이터베이스" in x:
            start = i + 1
            break
    tokens = [_clean(x) for x in raw[start:] if _clean(x) and _clean(x) not in SKIP]

    rows = []
    i = 0
    while i < len(tokens) - 2:
        if tokens[i] not in REGIONS:
            i += 1
            continue
        region = tokens[i]

        # 다음 지역 토큰까지 한 레코드 후보로 본다.
        j = i + 1
        chunk = []
        while j < len(tokens) and tokens[j] not in REGIONS:
            chunk.append(tokens[j])
            j += 1

        # 숫자 NO, 버튼성 문자열 제거
        chunk = [x for x in chunk if not re.fullmatch(r"\d+", x) and x not in {"상세","보기"}]
        if len(chunk) >= 2:
            name = chunk[0]
            course = chunk[1]
            address = next((x for x in chunk[2:] if _looks_address(x)), "")
            # 메뉴/푸터 진입 방지
            if (
                1 <= len(name) <= 40 and 1 <= len(course) <= 60
                and not any(k in name for k in ("공지사항","회원사","ABOUT","온라인 문의"))
            ):
                rows.append({
                    "region": region,
                    "name": name,
                    "course": course,
                    "address": address,
                    "source_url": KGA_CALCULATOR_URL,
                })
        i = max(j, i + 1)

    # 동일 행 중복 제거
    out, seen = [], set()
    for x in rows:
        key = (_norm(x["name"]), _norm(x["course"]), _clean(x["address"]))
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out

def _address_city(address):
    s = _clean(address)
    m = re.search(r"([가-힣]+(?:시|군|구))", s)
    return m.group(1) if m else ""

def _match_one(club, names, rows_by_name):
    key = _norm(club.get("name"))
    if not key:
        return None, 0.0, "none"

    exact = [n for n in names if _norm(n) == key]
    if len(exact) == 1:
        return exact[0], 1.0, "exact"

    scored = []
    club_city = _clean(club.get("city"))
    club_addr = _clean(club.get("address"))
    for n in names:
        nk = _norm(n)
        if not nk:
            continue
        score = SequenceMatcher(None, key, nk).ratio()
        if min(len(key), len(nk)) >= 4 and (key in nk or nk in key):
            score = max(score, 0.94)

        # 주소/도시가 일치하면 이름 표기차이에 보너스
        candidates = rows_by_name.get(n, [])
        addr_bonus = 0.0
        for row in candidates:
            kga_addr = row.get("address") or ""
            if club_city and club_city in kga_addr:
                addr_bonus = max(addr_bonus, 0.03)
            if club_addr and _address_city(club_addr) and _address_city(club_addr) == _address_city(kga_addr):
                addr_bonus = max(addr_bonus, 0.03)
        scored.append((min(score + addr_bonus, 1.0), n))

    scored.sort(reverse=True)
    if not scored:
        return None, 0.0, "none"
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0

    # 자동 적용은 매우 보수적으로
    if best_score >= 0.95 and best_score - second >= 0.05:
        return best, best_score, "safe_fuzzy"
    if best_score >= 0.75:
        return best, best_score, "review"
    return None, best_score, "none"

def diagnose_kga_matches(catalog=None):
    if catalog is None:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    rows = fetch_kga_rows()
    rows_by_name = {}
    for row in rows:
        rows_by_name.setdefault(row["name"], []).append(row)
    names = sorted(rows_by_name)

    matches = []
    stats = {
        "catalog": len(catalog),
        "kga_course_rows": len(rows),
        "kga_golf_courses": len(names),
        "safe": 0,
        "review": 0,
        "none": 0,
    }

    for club in catalog:
        name, score, kind = _match_one(club, names, rows_by_name)
        safe = kind in {"exact", "safe_fuzzy"}
        stats["safe" if safe else ("review" if kind == "review" else "none")] += 1
        matches.append({
            "catalog_id": club.get("id"),
            "catalog_name": club.get("name"),
            "catalog_city": club.get("city"),
            "match_name": name,
            "match_type": kind,
            "score": round(score, 4),
            "safe": safe,
            "kga_rows": rows_by_name.get(name, []) if name else [],
        })

    payload = {
        "checked_at": date.today().isoformat(),
        "source": KGA_CALCULATOR_URL,
        "stats": stats,
        "matches": matches,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
