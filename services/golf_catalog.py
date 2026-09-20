import json
import re
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "golf" / "catalog.json"


def _coord_lat_lon(club):
    for a, b in [("lat","lon"), ("latitude","longitude"), ("vworld_y","vworld_x"), ("y","x")]:
        try:
            lat, lon = float(club.get(a)), float(club.get(b))
            if 33 <= lat <= 39.5 and 124 <= lon <= 132.5:
                return lat, lon
        except (TypeError, ValueError):
            pass
    return None


def classify_search_region(lat, lon):
    if 33.0 <= lat <= 34.0 and 126.0 <= lon <= 127.2:
        return "제주권", "제주"
    if 36.85 <= lat <= 38.35 and 126.0 <= lon <= 128.0:
        if lon < 126.85 and 37.2 <= lat <= 37.9:
            return "수도권", "인천"
        if 126.75 <= lon <= 127.25 and 37.40 <= lat <= 37.72:
            return "수도권", "서울"
        return "수도권", "경기북부" if lat >= 37.55 else "경기남부"
    if 37.0 <= lat <= 38.7 and 127.3 <= lon <= 129.6:
        return "강원권", "강원영동" if lon >= 128.45 else "강원영서"
    if 35.8 <= lat < 37.35 and 126.0 <= lon <= 128.7:
        return "충청권", "충북" if lon >= 127.35 else "충남"
    if 34.5 <= lat <= 37.2 and 128.0 <= lon <= 130.0:
        return "영남권", "경북" if lat >= 35.65 else "경남"
    if 34.0 <= lat <= 36.3 and 125.8 <= lon <= 128.0:
        return "호남권", "전북" if lat >= 35.45 else "전남"
    return "", ""


def enrich_search_regions(clubs):
    for club in clubs:
        coord = _coord_lat_lon(club)
        if not coord:
            continue
        area, sub = classify_search_region(*coord)
        if area and not str(club.get("area") or "").strip():
            club["area"] = area
        if sub and not str(club.get("subregion") or "").strip():
            club["subregion"] = sub
        if sub and not str(club.get("city") or "").strip():
            club["city"] = sub
    return clubs



def load_catalog():
    clubs = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return enrich_search_regions(clubs)


def find_clubs(query, clubs=None):
    clubs = clubs or load_catalog()
    q = re.sub(r"\s+", "", str(query or "")).lower()
    if not q:
        return []
    out = []
    for c in clubs:
        values = [
            c.get("name", ""),
            c.get("city", ""),
            c.get("region", ""),
            c.get("area", ""),
            c.get("address", ""),
        ] + c.get("aliases", [])
        if any(q in re.sub(r"\s+", "", str(x)).lower() for x in values):
            out.append(c)
    return out


def _green_fee(fee, weekend=False):
    primary = "weekend_green" if weekend else "weekday_green"
    legacy = "weekend" if weekend else "weekday"
    value = fee.get(primary)
    if value is None:
        value = fee.get(legacy)
    return value


def estimate_per_person(c, weekend=False, players=4):
    f = c.get("fee", {})
    if not f.get("verified"):
        return None
    g = _green_fee(f, weekend)
    if g is None:
        return None
    extra = 0
    if players == 3:
        extra_key = "three_person_weekend_extra" if weekend else "three_person_weekday_extra"
        extra = f.get(extra_key) or 0
    return round(
        g
        + (f.get("cart_team") or 0) / players
        + (f.get("caddie_team") or 0) / players
        + extra
    )


def load_review_seed(path=None):
    if path is None:
        path = Path(__file__).resolve().parents[1] / "data" / "golf" / "review_seed.json"
    else:
        path = Path(path)
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_ai_conditions(text, current_area="전체", current_weekend=False, current_players=4, current_budget=None):
    t = str(text or "").strip()
    area = current_area
    weekend = current_weekend
    players = current_players
    budget = current_budget
    city = None
    traits = []

    city_map = {
        "서울": ["서울"],
        "인천": ["인천"],
        "용인": ["용인", "기흥", "처인", "수지"],
        "성남": ["성남", "분당"],
        "광주": ["경기광주", "광주"],
        "이천": ["이천"], "여주": ["여주"], "안성": ["안성"],
        "화성": ["화성"], "가평": ["가평"], "양평": ["양평"], "포천": ["포천"],
        "춘천": ["춘천"], "원주": ["원주"], "홍천": ["홍천"], "횡성": ["횡성"],
        "강릉": ["강릉"], "속초": ["속초"], "고성": ["고성"],
        "청주": ["청주"], "충주": ["충주"], "음성": ["음성"], "보은": ["보은"],
        "천안": ["천안"], "아산": ["아산"], "대전": ["대전"], "세종": ["세종"],
        "부산": ["부산"], "대구": ["대구"], "울산": ["울산"],
        "창원": ["창원"], "김해": ["김해"], "양산": ["양산"], "경주": ["경주"],
        "포항": ["포항"], "거제": ["거제"],
        "광주광역시": ["광주광역시"], "전주": ["전주"], "익산": ["익산"],
        "군산": ["군산"], "순천": ["순천"], "여수": ["여수"], "목포": ["목포"],
        "제주": ["제주", "서귀포"], "서귀포": ["서귀포"],
    }
    for c, words in city_map.items():
        if any(w in t for w in words):
            city = c
            break

    if any(x in t for x in ["제주", "서귀포"]):
        area = "제주권"
    elif any(x in t for x in ["호남", "전북", "전남", "광주광역시", "전주", "익산", "군산", "순천", "여수", "목포"]):
        area = "호남권"
    elif any(x in t for x in ["영남", "경북", "경남", "부산", "대구", "울산", "창원", "김해", "양산", "경주", "포항", "거제"]):
        area = "영남권"
    elif any(x in t for x in ["강원", "춘천", "원주", "홍천", "횡성", "강릉", "속초", "고성"]):
        area = "강원권"
    elif any(x in t for x in ["충청", "충북", "충남", "청주", "충주", "음성", "보은", "대전", "세종", "천안", "아산"]):
        area = "충청권"
    elif any(x in t for x in ["수도권", "서울", "경기", "인천", "용인", "성남", "분당", "이천", "여주", "안성", "화성", "가평", "양평", "포천"]):
        area = "수도권"

    if any(x in t for x in ["주말", "토요일", "일요일", "공휴일", "이번주말", "이번 주말"]):
        weekend = True
    elif any(x in t for x in ["주중", "평일", "월요일", "화요일", "수요일", "목요일", "금요일"]):
        weekend = False

    if any(x in t for x in ["3인", "3명", "세 명"]):
        players = 3
    elif any(x in t for x in ["4인", "4명", "네 명"]):
        players = 4

    m = re.search(r"(?:(\d{1,3})\s*만\s*원|\b(\d{5,6})\s*원)", t)
    if m:
        budget = int(m.group(1)) * 10000 if m.group(1) else int(m.group(2))

    trait_map = {
        "fairway_wide": ["페어웨이 넓", "넓은 페어웨이", "티샷 부담 적", "넓은 곳"],
        "maintenance_good": ["관리 좋", "관리 잘", "잔디 좋", "컨디션 좋"],
        "easy": ["쉬운", "편한 코스", "초보", "난이도 낮"],
        "green_fast": ["그린 빠", "빠른 그린"],
        "facilities_good": ["시설 좋", "클럽하우스 좋", "시설 좋은"],
    }
    for key, words in trait_map.items():
        if any(w in t for w in words):
            traits.append(key)

    return {
        "area": area,
        "city": city,
        "weekend": weekend,
        "players": players,
        "budget": budget,
        "traits": traits,
    }


def _trait_match(c, trait):
    rt = c.get("review_traits", {})
    if isinstance(rt, dict) and rt.get(trait) is True:
        return True

    blob = (
        str(c.get("course_overview", ""))
        + " "
        + str(c.get("review_traits", ""))
    ).lower()

    phrases = {
        "fairway_wide": ["페어웨이 넓", "페어웨이 폭은 넓", "넓은 페어웨이"],
        "maintenance_good": ["관리 좋", "관리 잘", "잔디 관리", "잔디 좋"],
        "easy": ["쉬운 코스", "편한 코스", "초보"],
        "green_fast": ["그린 빠", "빠른 그린"],
        "facilities_good": ["시설 좋", "클럽하우스 좋"],
    }
    return any(p in blob for p in phrases.get(trait, []))


def _recommendation_score(c, city=None, traits=None, budget=None, weekend=False, players=4):
    traits = traits or []
    score = 0
    reasons = []

    city_text = f'{c.get("city","")} {c.get("address","")}'
    if city and city in city_text:
        score += 30
        reasons.append(f"{city} 지역 일치")

    matched_traits = [t for t in traits if _trait_match(c, t)]
    score += len(matched_traits) * 28

    trait_labels = {
        "fairway_wide": "넓은 페어웨이",
        "maintenance_good": "코스관리",
        "easy": "편한 코스",
        "green_fast": "빠른 그린",
        "facilities_good": "시설",
    }
    for t in matched_traits:
        reasons.append(f"{trait_labels.get(t,t)} 조건 일치")

    cost = estimate_per_person(c, weekend, players)
    if cost is not None:
        score += 6
        if budget:
            gap = max(budget - cost, 0)
            score += min(gap / 10000, 8)
            reasons.append(f"예산 내 · 1인 약 {cost:,}원")
        else:
            reasons.append(f"1인 예상 약 {cost:,}원")
    else:
        reasons.append("요금은 방문 전 확인")

    if c.get("fee", {}).get("verified"):
        score += 2
    if c.get("data_checked"):
        score += 1

    return score, reasons



def _subregion_match(club, subregion):
    if not subregion:
        return True
    text = " ".join(str(club.get(k) or "") for k in ("subregion", "city", "region", "area", "name"))
    aliases = {
        "경기남부": ["경기남부", "용인", "성남", "광주", "이천", "여주", "안성", "화성", "수원", "평택"],
        "경기북부": ["경기북부", "가평", "포천", "양주", "파주", "고양", "남양주", "의정부"],
        "충북": ["충북", "청주", "충주", "음성", "보은", "제천", "진천"],
        "충남": ["충남", "천안", "아산", "공주", "당진", "태안", "대전", "세종"],
        "강원영서": ["강원영서", "춘천", "원주", "홍천", "횡성"],
        "강원영동": ["강원영동", "강릉", "속초", "고성", "동해", "삼척"],
        "경북": ["경북", "대구", "경주", "포항", "구미"],
        "경남": ["경남", "부산", "울산", "창원", "김해", "양산", "거제"],
        "전북": ["전북", "전주", "익산", "군산"],
        "전남": ["전남", "광주", "순천", "여수", "목포"],
        "제주": ["제주", "서귀포"],
        "서울": ["서울"],
        "인천": ["인천"],
    }
    return any(x in text for x in aliases.get(subregion, [subregion]))



def is_recommendable(club):
    """추천에는 서비스 정보가 검증/보강된 레코드만 사용한다.
    VWorld-only 레코드는 존재 후보/지도 Pool에는 남기되 자동 추천에서 제외한다.
    """
    fee_verified = bool((club.get("fee") or {}).get("verified"))
    checked = bool(club.get("data_checked"))
    has_service_source = any(
        str(club.get(k) or "").strip()
        for k in ("official_url", "website", "homepage", "phone")
    )
    has_enriched_detail = bool(
        club.get("holes")
        or club.get("traits")
        or club.get("review_traits")
        or (club.get("play") or {}).get("three_person")
    )
    return checked or fee_verified or (has_service_source and has_enriched_detail)

def recommendation_pool(clubs, area="전체", text="", budget=None, players=4, weekend=False,
                        limit=6, offset=0, city=None, traits=None):
    """
    순위가 아니라 '조건 적합 후보군'을 반환한다.
    offset은 이미 본 후보 수를 뜻하며, 끝에 도달하면 처음으로 순환한다.
    """
    traits = traits or []

    pool = [
        c for c in clubs
        if (area == "전체" or c.get("area") == area)
        and is_recommendable(c)
    ]

    if budget:
        pool = [
            c for c in pool
            if estimate_per_person(c, weekend, players) is None
            or estimate_per_person(c, weekend, players) <= budget
        ]

    if players == 3:
        pool = [
            c for c in pool
            if "불가" not in str(c.get("play", {}).get("three_person", ""))
        ]

    scored = []
    for c in pool:
        score, reasons = _recommendation_score(
            c,
            city=city,
            traits=traits,
            budget=budget,
            weekend=weekend,
            players=players,
        )
        scored.append((score, c, reasons))

    # 조건 일치도 우선. 동점일 때 검증요금/지역/이름으로 안정 정렬.
    scored.sort(
        key=lambda x: (
            -x[0],
            not x[1].get("fee", {}).get("verified"),
            x[1].get("city", ""),
            x[1].get("name", ""),
        )
    )

    if not scored:
        return []

    # offset 이후 묶음. 마지막 묶음은 남은 후보만 표시하고 자동 순환하지 않는다.
    start = max(int(offset or 0), 0)
    if start >= len(scored):
        start = 0

    selected = scored[start:start + limit]
    day = "주말" if weekend else "주중"

    result = []
    for score, c, reasons in selected:
        base = f'{c.get("region","")} {c.get("city","")} · {day} {players}인'
        display_reasons = [base] + reasons[:3]
        result.append((c, display_reasons))

    return result


def recommend_clubs(clubs, area="전체", text="", budget=None, players=4, limit=6, weekend=False):
    cond = parse_ai_conditions(text, area, weekend, players, budget)
    return recommendation_pool(
        clubs,
        cond["area"],
        text,
        cond["budget"],
        cond["players"],
        cond["weekend"],
        limit=limit,
        offset=0,
        city=cond.get("city"),
        traits=cond.get("traits"),
    )


def catalog_count(clubs=None):
    clubs = clubs or load_catalog()
    return len(clubs)


def catalog_area_counts(clubs=None):
    clubs = clubs or load_catalog()
    out = {}
    for c in clubs:
        area = c.get("area") or "기타"
        out[area] = out.get(area, 0) + 1
    return out
