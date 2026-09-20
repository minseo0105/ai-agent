import copy
import html
import json
import re
from datetime import date
from io import StringIO
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd
import requests

BASE_DIR = Path(__file__).resolve().parents[1]
CATALOG_PATH = BASE_DIR / "data" / "golf" / "catalog.json"
REPORT_PATH = BASE_DIR / "data" / "golf" / "kga_match_diagnostic.json"

KGA_RATING_DB = "https://www.kgagolf.or.kr/web/handicap/calculator"
KGA_MEMBER_DB = "https://www.kgagolf.or.kr/web/golfCourse/golfCourse"


def _norm(v):
    s = str(v or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"[^0-9a-z가-힣]", "", s)
    for token in ("컨트리클럽", "골프클럽", "골프장", "countryclub", "golfclub", "cc", "gc"):
        s = s.replace(token, "")
    return s


def _clean(v):
    if pd.isna(v):
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _get(url):
    r = requests.get(
        url,
        timeout=35,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Golf-Finder/1.0)"},
    )
    r.raise_for_status()
    return r.text


def fetch_kga_course_database():
    """KGA 코스레이팅 DB 공개 목록: 골프장/코스/주소."""
    text = _get(KGA_RATING_DB)
    tables = pd.read_html(StringIO(text))
    rows = []
    for df in tables:
        cols = [str(c).strip() for c in df.columns]
        if not any("골프장" in c for c in cols) or not any("코스" in c for c in cols):
            continue
        df.columns = cols
        golf_col = next(c for c in cols if "골프장" in c)
        course_col = next(c for c in cols if "코스" in c)
        address_col = next((c for c in cols if "주소" in c), None)
        region_col = next((c for c in cols if "지역" in c), None)
        for _, r in df.iterrows():
            name = _clean(r.get(golf_col))
            course = _clean(r.get(course_col))
            if not name or name.lower() == "nan":
                continue
            rows.append({
                "name": name,
                "course": course,
                "address": _clean(r.get(address_col)) if address_col else "",
                "region": _clean(r.get(region_col)) if region_col else "",
                "source_url": KGA_RATING_DB,
            })
    # 완전 중복 제거
    out, seen = [], set()
    for x in rows:
        key = (_norm(x["name"]), _norm(x["course"]), x["address"])
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out


def fetch_kga_member_holes():
    """
    KGA 회원사 공개 페이지에서 '골프장명 / N홀 / 지역' 패턴을 보수적으로 추출.
    페이지 구조 변경 시 빈 목록을 반환하며 catalog는 건드리지 않는다.
    """
    text = _get(KGA_MEMBER_DB)
    # 태그 제거 후 텍스트 토큰화
    plain = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.I|re.S)
    plain = re.sub(r"<[^>]+>", "\n", plain)
    plain = html.unescape(plain)
    lines = [re.sub(r"\s+", " ", x).strip() for x in plain.splitlines()]
    lines = [x for x in lines if x]

    results = []
    # "골프장명" 주변 15줄 안의 "18홀 경기" 형태를 찾는다.
    for i, line in enumerate(lines):
        m = re.fullmatch(r"(\d{1,2})홀(?:\s+([가-힣]+))?", line)
        if not m:
            continue
        holes = int(m.group(1))
        region = m.group(2) or ""
        # 앞쪽에서 전화/주소/No./메뉴를 피하고 가장 그럴듯한 짧은 이름 선택
        candidates = []
        for j in range(max(0, i-12), i):
            x = lines[j]
            if len(x) > 40 or re.search(r"(Tel\.|Fax\.|No\.|주소|회원사|검색|지역|홀$)", x, re.I):
                continue
            if re.search(r"\d{2,}", x):
                continue
            if 1 <= len(x) <= 30:
                candidates.append(x)
        if candidates:
            name = candidates[-1]
            results.append({
                "name": name,
                "holes": holes,
                "region": region,
                "source_url": KGA_MEMBER_DB,
            })

    # 이름 정규화 기준 중복 제거
    out = {}
    for x in results:
        key = _norm(x["name"])
        if key:
            out[key] = x
    return list(out.values())


def _best_match(catalog_name, kga_names):
    key = _norm(catalog_name)
    if not key:
        return None, 0.0, "none"
    exact = [n for n in kga_names if _norm(n) == key]
    if len(exact) == 1:
        return exact[0], 1.0, "exact"
    scored = []
    for n in kga_names:
        nk = _norm(n)
        if not nk:
            continue
        score = SequenceMatcher(None, key, nk).ratio()
        # 긴 이름 포함관계는 보너스
        if min(len(key), len(nk)) >= 4 and (key in nk or nk in key):
            score = max(score, 0.94)
        scored.append((score, n))
    scored.sort(reverse=True)
    if not scored:
        return None, 0.0, "none"
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0
    if best_score >= 0.92 and best_score - second >= 0.04:
        return best, best_score, "safe_fuzzy"
    return best, best_score, "review"


def diagnose_kga_matches(catalog=None):
    catalog = catalog or json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    course_rows = fetch_kga_course_database()
    hole_rows = fetch_kga_member_holes()

    by_course_name = {}
    for row in course_rows:
        by_course_name.setdefault(row["name"], []).append(row)
    by_hole_name = {row["name"]: row for row in hole_rows}
    all_names = sorted(set(by_course_name) | set(by_hole_name))

    report = []
    stats = {"catalog": len(catalog), "kga_course_rows": len(course_rows),
             "kga_member_hole_rows": len(hole_rows), "safe": 0, "review": 0, "none": 0}

    for club in catalog:
        match, score, kind = _best_match(club.get("name"), all_names)
        safe = kind in {"exact", "safe_fuzzy"}
        if safe:
            stats["safe"] += 1
        elif kind == "review":
            stats["review"] += 1
        else:
            stats["none"] += 1
        report.append({
            "catalog_id": club.get("id"),
            "catalog_name": club.get("name"),
            "match_name": match,
            "match_type": kind,
            "score": round(score, 4),
            "safe": safe,
            "kga_courses": by_course_name.get(match, []),
            "kga_holes": by_hole_name.get(match),
        })

    payload = {"checked_at": date.today().isoformat(), "stats": stats, "matches": report}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def apply_safe_kga_enrichment(catalog=None, report=None):
    """
    진단에서 safe=True인 항목만 적용.
    KGA 회원사 페이지의 홀 수는 값이 비어 있을 때만 보강하고,
    기존 홀 수와 충돌하면 덮어쓰지 않고 conflict로 기록한다.
    """
    clubs = copy.deepcopy(catalog or json.loads(CATALOG_PATH.read_text(encoding="utf-8")))
    report = report or diagnose_kga_matches(clubs)
    by_id = {x.get("catalog_id"): x for x in report["matches"] if x.get("safe")}
    stats = {"matched": 0, "holes_added": 0, "holes_conflict": 0, "course_profiles_added": 0}

    for club in clubs:
        m = by_id.get(club.get("id"))
        if not m:
            continue
        stats["matched"] += 1
        kga = club.setdefault("kga", {})
        kga["matched"] = True
        kga["matched_name"] = m.get("match_name")
        kga["checked_at"] = report.get("checked_at")
        kga["source"] = "대한골프협회(KGA)"

        course_rows = m.get("kga_courses") or []
        if course_rows:
            combos = []
            for row in course_rows:
                combo = str(row.get("course") or "").strip()
                if combo and combo not in combos:
                    combos.append(combo)
            kga["course_combinations"] = combos
            kga["rating_database_url"] = KGA_RATING_DB
            stats["course_profiles_added"] += 1

        hole_row = m.get("kga_holes")
        if hole_row and hole_row.get("holes"):
            kh = int(hole_row["holes"])
            old = club.get("holes")
            try:
                old_num = int(float(str(old).replace("홀", "").strip())) if old not in (None, "") else None
            except Exception:
                old_num = None
            if old_num is None:
                club["holes"] = kh
                club["holes_source"] = "KGA 회원사골프장 현황"
                stats["holes_added"] += 1
            elif old_num != kh:
                kga["holes_conflict"] = {"catalog": old_num, "kga": kh}
                stats["holes_conflict"] += 1
            kga["member_database_url"] = KGA_MEMBER_DB

    return clubs, stats


def slope_band(value):
    """표시용 상대 난이도. KGA 수치를 임의 평균스코어로 변환하지 않는다."""
    try:
        v = int(value)
    except Exception:
        return "확인 필요"
    if v < 113:
        return "상대적으로 낮음"
    if v == 113:
        return "기준 수준"
    if v <= 125:
        return "다소 높음"
    if v <= 140:
        return "높음"
    return "매우 높음"


def course_handicap(handicap_index, slope_rating, course_rating=None, par=None):
    """
    WHS Course Handicap 기본식.
    Course Rating/Par가 없으면 slope 조정값만 반환하지 않고 None 처리해 과도한 추정을 피한다.
    """
    if handicap_index is None or slope_rating is None or course_rating is None or par is None:
        return None
    return round(float(handicap_index) * (float(slope_rating) / 113.0)
                 + (float(course_rating) - float(par)))
