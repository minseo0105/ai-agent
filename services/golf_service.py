"""골프장 추천 도메인 로직 (Streamlit 무관).

HELPERS: pages/6_골프장_추천.py의 도우미 함수를 그대로 옮긴 것.
SEARCH / DETAIL: FastAPI(api/golf.py)에서 쓰는 검색·상세 함수.
"""

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from functools import wraps
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus
from urllib.request import Request, urlopen

from services.config import get_secret
from services.golf_catalog import estimate_per_person as _catalog_estimate
from services.golf_gpt_analysis import DIMS
from services.golf_pricing import fee_summary, green_fee, team_fee
from services.golf_master import (
    get_objective_detail,
    get_objective_status,
    is_round_eligible,
    normalize_operation_type,
    objective_filter_value,
)


def ttl_cache(ttl):
    """st.cache_data(ttl=...) 대체: 인자별 결과를 ttl초 동안 메모리에 보관."""
    def decorator(fn):
        store = {}

        @wraps(fn)
        def wrapper(*args):
            now = time.monotonic()
            hit = store.get(args)
            if hit and now - hit[0] < ttl:
                return hit[1]
            value = fn(*args)
            store[args] = (now, value)
            if len(store) > 512:
                store.pop(next(iter(store)))
            return value
        return wrapper
    return decorator


def _naver_keys():
    key_id = str(get_secret("NAVER_MAP_NCP_KEY_ID") or get_secret("NAVER_MAP_CLIENT_ID") or "").strip()
    key = str(get_secret("NAVER_MAP_NCP_KEY") or get_secret("NAVER_MAP_CLIENT_SECRET") or "").strip()
    return key_id, key


# =========================================================
# HELPERS (pages/6_골프장_추천.py에서 이동)
# =========================================================

def _booking_url(club):
    """카탈로그에 저장된 공식 예약/홈페이지 URL을 우선 반환."""
    for field in ("booking_url", "reservation_url", "reserve_url"):
        url = str(club.get(field) or "").strip()
        if url.startswith(("http://", "https://")):
            return url

    for field in ("website", "homepage", "url"):
        url = str(club.get(field) or "").strip()
        if url.startswith(("http://", "https://")):
            return url
    return ""


def _naver_booking_search_url(club, round_date=None):
    """공식 예약 URL이 없을 때 사용하는 예약 검색 링크."""
    name = str(club.get("name") or "").strip()
    query = f"{name} 골프 예약"
    if round_date:
        query += f" {round_date.strftime('%Y-%m-%d')}"
    return "https://search.naver.com/search.naver?query=" + quote_plus(query)


def _date_is_weekend(d):
    """선택 날짜가 토/일인지 반환."""
    return d.weekday() >= 5


def _round_date_label(d):
    """모바일 표시용 날짜 라벨."""
    if d is None:
        return "날짜 미선택"
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return f"{d.month}/{d.day}({weekdays[d.weekday()]})"


def _pricing_fee_for_session(club, round_date=None, session_name=None, weekend=None):
    """비회원 18홀 그린피 최저가 (services.golf_pricing 정규화 결과 사용)."""
    if round_date:
        weekend = _date_is_weekend(round_date)
    session = session_name if session_name in ("1부", "2부", "3부") else None
    return green_fee(club, weekend, session)


def estimate_per_person(club, weekend=False, players=4, session=None):
    """1인 예상비용 = 그린피 + (카트비 + 캐디피) ÷ 인원. 정밀 요금표가 없으면 catalog 방식으로 대체."""
    green = green_fee(club, bool(weekend), session)
    if green is None:
        return _catalog_estimate(club, weekend, players)
    team = (team_fee(club, "cart") or 0) + (team_fee(club, "caddie") or 0)
    return int(green + team / max(int(players or 4), 1))


# 정밀 DB operations.caddie.mode → 화면 구분
_CADDIE_MODES = {
    "no_caddie": "노캐디",
    "caddie": "캐디", "caddie_required": "캐디", "caddie_required_indicated": "캐디", "mandatory_caddie": "캐디",
    "caddie_assisted": "캐디", "caddie_required_regular_courses": "캐디", "caddie_assisted_join_supported": "캐디",
    "optional_caddie_or_self": "캐디 선택", "optional_by_session": "캐디 선택", "caddie_or_self_round": "캐디 선택",
    "choice_by_cart_type": "캐디 선택", "selective": "캐디 선택", "session_dependent": "캐디 선택",
    "course_dependent": "캐디 선택", "mixed": "캐디 선택",
}


def _caddie_summary(club):
    op = club.get("operations") or {}
    caddie = op.get("caddie") if isinstance(op, dict) else None
    if isinstance(caddie, dict) and caddie.get("mode") in _CADDIE_MODES:
        return _CADDIE_MODES[caddie["mode"]]
    if isinstance(caddie, dict):
        caddie = caddie.get("mode") if caddie.get("mode") not in (None, "unknown") else None
    text = " ".join(str(x) for x in (caddie, club.get("caddie_type"), club.get("caddie")) if x).strip()
    low = text.lower()
    if any(x in low for x in ("노캐디", "no caddie", "no_caddie", "self")):
        return "노캐디"
    if text and any(x in low for x in ("캐디", "caddie")):
        return "캐디"
    return "확인 필요"


def _matches_caddie(club, choice):
    if choice in (None, "", "전체"):
        return True
    status = _caddie_summary(club)
    # 미확인은 거짓으로 단정하지 않고 결과에 남긴다. '캐디 선택'은 어느 쪽이든 가능.
    return status in ("확인 필요", "캐디 선택") or status == choice


def won(x):
    if x is None:
        return "-"
    return f"{int(x):,}원"


def get_review_year(review):
    """
    후기의 날짜에서 연도만 안전하게 추출.
    날짜를 확인할 수 없으면 None.
    """
    date_text = str(
        review.get("date")
        or review.get("published_date")
        or ""
    )

    match = re.search(r"(20\d{2})", date_text)

    if not match:
        return None

    return int(match.group(1))


def review_preview(review, max_chars=150):
    """Tavily/GPT가 이미 확보한 텍스트에서 원문 미리보기를 만든다. 추가 API 호출 없음."""
    candidates = [
        review.get("summary"),
        review.get("content"),
        review.get("snippet"),
        review.get("text"),
        review.get("raw_content"),
    ]
    text = next((str(x).strip() for x in candidates if x and str(x).strip()), "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"https?://\S+", "", text).strip()
    if not text:
        return "후기 본문 미리보기는 원문에서 확인할 수 있습니다."
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "…"
    return text


def club_lat_lon(club):
    """catalog에 저장된 위경도 후보를 안전하게 읽는다. 정밀 DB가 무효로 표시한 좌표는 쓰지 않는다."""
    validation = club.get("coordinate_validation") or (club.get("verification") or {}).get("coordinate_validation") or {}
    if isinstance(validation, dict) and str(validation.get("status") or "").startswith("invalid"):
        return None
    location = club.get("location") or {}
    candidates = [
        (location.get("latitude"), location.get("longitude")),
        (club.get("lat"), club.get("lon")),
        (club.get("latitude"), club.get("longitude")),
        (club.get("y"), club.get("x")),
        (club.get("vworld_y"), club.get("vworld_x")),
    ]
    for lat, lon in candidates:
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue
        # Streamlit 지도는 WGS84 위경도만 표시
        if 33.0 <= lat <= 39.5 and 124.0 <= lon <= 132.5:
            return lat, lon
    return None


def distance_km(a, b):
    """WGS84 두 지점의 직선거리(km)."""
    import math
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(h))




def _player_status(course, players):
    ops=course.get("operations") or {}; p=ops.get("players") or {}; value=None
    word={1:"one",2:"two",3:"three",4:"four",5:"five"}.get(players)
    if isinstance(p,dict):
        for k in [str(players),f"{players}인",f"{players}_person",f"{players}p",f"{word}_person"]:
            if k in p: value=p.get(k); break
    if value is None and players==3: value=(course.get("play") or {}).get("three_person")
    if isinstance(value,dict):
        value=next((value[k] for k in ("allowed","available","status") if k in value), None)
    if isinstance(value,bool): return value
    s=str(value or "").strip().lower()
    if not s or s in {"unknown","none","null"} or "확인 필요" in s or "조건부" in s: return None
    if any(x in s for x in ["불가","불가능","false","no"]): return False
    if any(x in s for x in ["가능","true","yes"]): return True
    return None

def _night_status(course):
    ops=course.get("operations") or {}
    for value in [ops.get("night"),ops.get("night_round"),(course.get("play") or {}).get("night"),(course.get("play") or {}).get("night_round")]:
        if isinstance(value,dict): value=value.get("available") if "available" in value else value.get("status")
        if isinstance(value,bool): return value
        s=str(value or "").strip().lower()
        if not s or s in {"unknown","none","null"} or "확인 필요" in s: continue
        if any(x in s for x in ["불가","미운영","false","no"]): return False
        if any(x in s for x in ["가능","운영","true","yes"]): return True
    return None

def _cond_session_fee(course, cond, session=None):
    """검색조건의 날짜(있으면) 또는 주중/주말과 시간대로 그린피를 찾는다."""
    cond = cond or {}
    round_d = None
    try:
        round_d = date.fromisoformat(cond["round_date"]) if cond.get("round_date") else None
    except Exception:
        pass
    weekend = cond.get("weekend") if "weekend" in cond else None
    return _pricing_fee_for_session(course, round_d, session or cond.get("session"), weekend=weekend)

def _eligibility(course,cond):
    issues=[]; unknowns=[]
    if (cond or {}).get("budget"):
        fee=_cond_session_fee(course,cond)
        if fee is None: unknowns.append("그린피")
        elif fee>cond["budget"]: issues.append("예산 초과")
    cad=(cond or {}).get("caddie") or "전체"
    if cad!="전체":
        actual=_caddie_summary(course)
        if actual=="확인 필요": unknowns.append("캐디")
        elif actual not in (cad,"캐디 선택"): issues.append("캐디 불일치")
    if int((cond or {}).get("players") or 4)==3:
        ps=_player_status(course,3)
        if ps is False: issues.append("3인 불가")
        elif ps is None: unknowns.append("3인")
    if (cond or {}).get("night"):
        ns=_night_status(course)
        if ns is False: issues.append("야간 불가")
        elif ns is None: unknowns.append("야간")
    return issues,unknowns

def _useful_detail(course):
    ops=course.get("operations") or {}; cad=ops.get("caddie") or {}; cart=ops.get("cart") or {}; ev=course.get("evaluation") or {}
    def clean(v):
        s=str(v or "").strip()
        if s=="official_ratings_available": return "KGA 공인 난이도 제공"
        # 'partial_official' 같은 내부 상태 코드는 화면에 노출하지 않는다.
        if re.fullmatch(r"[a-z0-9_]+", s): return None
        return None if not s or s.lower() in {"unknown","none","null"} or "확인 필요" in s else s
    p3=_player_status(course,3)
    return {"caddie_mode":_caddie_summary(course),
      "caddie_fee":team_fee(course,"caddie"),
      "cart_fee":team_fee(course,"cart"),
      "three_person":"가능" if p3 is True else ("불가" if p3 is False else "확인 필요"),
      "summary":clean(ev.get("summary")),"difficulty":clean(ev.get("difficulty")),
      "fairway":clean(ev.get("fairway_width")),"green":clean(ev.get("green_difficulty")),
      "condition":clean(ev.get("course_condition")),"scenery":clean(ev.get("scenery"))}

@ttl_cache(60 * 60 * 24)
def vworld_place_search(query, api_key, domain):
    """VWorld 검색 API(type=place)로 역·건물·상호명을 좌표로 변환한다. NAVER 지오코딩은 주소만 인식하므로 보조로 사용."""
    query = str(query or "").strip()
    if not query or not api_key:
        return None
    params = {
        "service": "search", "request": "search", "version": "2.0", "crs": "EPSG:4326",
        "size": 1, "page": 1, "query": query, "type": "place",
        "format": "json", "errorformat": "json", "key": api_key, "domain": domain or "",
    }
    endpoint = "https://api.vworld.kr/req/search?" + "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    try:
        with urlopen(Request(endpoint, headers={"Accept": "application/json"}), timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None

    items = (((payload.get("response") or {}).get("result") or {}).get("items")) or []
    if not items:
        return None
    item = items[0]
    try:
        lon = float((item.get("point") or {}).get("x"))
        lat = float((item.get("point") or {}).get("y"))
    except (TypeError, ValueError):
        return None
    if not (33.0 <= lat <= 39.5 and 124.0 <= lon <= 132.5):
        return None

    address = item.get("address") or {}
    return {
        "lat": lat,
        "lon": lon,
        "place_name": item.get("title") or "",
        "road_address": address.get("road") or "",
        "jibun_address": address.get("parcel") or "",
    }


def geocode_departure(query):
    """주소는 NAVER, 장소명은 VWorld 순으로 좌표를 찾는다. (좌표 dict 또는 None, 사용 가능한 키 여부)"""
    naver_key_id, naver_key = _naver_keys()
    vworld_key = str(get_secret("VWORLD_API_KEY") or "").strip()
    geo = None
    if naver_key_id and naver_key:
        geo = naver_geocode(query, naver_key_id, naver_key)
    if geo is None and vworld_key:
        geo = vworld_place_search(query, vworld_key, str(get_secret("VWORLD_DOMAIN") or "").strip())
    return geo, bool((naver_key_id and naver_key) or vworld_key)


@ttl_cache(60 * 60 * 24)
def naver_geocode(query, api_key_id, api_key):
    """NAVER Cloud Maps Geocoding으로 주소/장소 문자열을 좌표로 변환한다."""
    query = str(query or "").strip()
    if not query or not api_key_id or not api_key:
        return None

    endpoint = "https://maps.apigw.ntruss.com/map-geocode/v2/geocode?query=" + quote(query)
    req = Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "x-ncp-apigw-api-key-id": str(api_key_id),
            "x-ncp-apigw-api-key": str(api_key),
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None

    addresses = payload.get("addresses") or []
    if not addresses:
        return None

    row = addresses[0]
    try:
        lon = float(row.get("x"))
        lat = float(row.get("y"))
    except (TypeError, ValueError):
        return None

    if not (33.0 <= lat <= 39.5 and 124.0 <= lon <= 132.5):
        return None

    return {
        "lat": lat,
        "lon": lon,
        "road_address": row.get("roadAddress") or "",
        "jibun_address": row.get("jibunAddress") or "",
    }


def _sort_price(course, cond):
    """선택한 주중/주말·부 가격을 우선하고, 없으면 기존 1인 예상가를 사용."""
    session_fee = _cond_session_fee(course, cond)
    if session_fee is not None:
        return float(session_fee)

    try:
        est = estimate_per_person(
            course,
            bool((cond or {}).get("weekend")),
            int((cond or {}).get("players") or 4),
        )
    except Exception:
        est = None

    return float(est) if est is not None else float("inf")


def _distance_from_departure(course, departure_coord):
    coord = club_lat_lon(course)
    if not departure_coord or not coord:
        return None
    return distance_km(departure_coord, coord)



@ttl_cache(60 * 10)
def naver_driving_route(start_lat, start_lon, goal_lat, goal_lon, api_key_id, api_key):
    """NAVER Directions 5의 실시간 최적 경로 요약(distance/duration/toll)를 반환."""
    if not api_key_id or not api_key:
        return None
    try:
        start_lat, start_lon = float(start_lat), float(start_lon)
        goal_lat, goal_lon = float(goal_lat), float(goal_lon)
    except (TypeError, ValueError):
        return None

    endpoint = (
        "https://maps.apigw.ntruss.com/map-direction/v1/driving"
        f"?start={start_lon},{start_lat}"
        f"&goal={goal_lon},{goal_lat}"
        "&option=traoptimal"
    )
    req = Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "x-ncp-apigw-api-key-id": str(api_key_id),
            "x-ncp-apigw-api-key": str(api_key),
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=7) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None

    routes = ((payload.get("route") or {}).get("traoptimal") or [])
    if not routes:
        return None
    summary = routes[0].get("summary") or {}
    distance_m = summary.get("distance")
    duration_ms = summary.get("duration")
    toll = summary.get("tollFare")

    try:
        distance_km_value = float(distance_m) / 1000.0
    except (TypeError, ValueError):
        distance_km_value = None
    try:
        duration_min = int(round(float(duration_ms) / 60000.0))
    except (TypeError, ValueError):
        duration_min = None
    try:
        toll_value = int(toll) if toll is not None else None
    except (TypeError, ValueError):
        toll_value = None

    return {
        "distance_km": distance_km_value,
        "duration_min": duration_min,
        "toll_fare": toll_value,
    }


def _route_for_course(course, cond):
    raw = (cond or {}).get("departure_coord")
    goal = club_lat_lon(course)
    if not (isinstance(raw, (list, tuple)) and len(raw) == 2 and goal):
        return None
    try:
        start_lat, start_lon = float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None

    key_id, key = _naver_keys()
    if not (key_id and key):
        return None
    return naver_driving_route(start_lat, start_lon, goal[0], goal[1], key_id, key)


def has_meaningful_summary(summary):
    """
    실제 후기 근거가 있는 저장 요약인지 확인.
    mentions가 하나라도 있으면 유효한 저장 요약으로 간주.
    """
    if not summary:
        return False

    dimensions = summary.get("dimensions", {})

    for dim in DIMS:
        item = dimensions.get(dim, {})
        if int(item.get("mentions", 0) or 0) > 0:
            return True

    return False


def _normalize_result_item(item):
    """검색결과를 화면용 (course, reasons) 2튜플로 통일."""
    if not isinstance(item, (tuple, list)):
        return item, []
    if len(item) == 2:
        course, reasons = item
        return course, reasons if isinstance(reasons, list) else [str(reasons)]
    if len(item) >= 3:
        course, reasons = item[0], item[-1]
        return course, reasons if isinstance(reasons, list) else [str(reasons)]
    return item[0], []


def _condition_evidence(course, cond):
    """3인/예산 조건의 확인 상태를 반환한다."""
    cond = cond or {}
    confirmed, pending = [], []
    if cond.get("areas") or (cond.get("area") not in (None, "", "전체")):
        confirmed.append("지역")

    players = 4  # 요금 추정 기본값. 3인 플레이는 아래 객관조건에서 별도 판정.

    if cond.get("budget"):
        try:
            est = estimate_per_person(course, bool(cond.get("weekend")), players)
        except Exception:
            est = None
        if est is None:
            pending.append("요금")
        else:
            confirmed.append("요금")

    for feature in cond.get("objective_features", []):
        status = _objective_feature_status(course, feature)
        if status is True:
            confirmed.append(feature)
        elif status is None:
            pending.append(feature + (" · 조건부 확인" if get_objective_status(course, feature) == "conditional" else ""))
    return confirmed, pending


def _result_confidence(course, cond):
    confirmed, pending = _condition_evidence(course, cond)

    # Service가 아닌 candidate는 선택조건이 맞더라도
    # 홀 수 등 기본 라운드 정보가 아직 충분히 확인되지 않은 상태다.
    if course.get("service_status") == "candidate":
        if not course.get("holes") and "홀 수" not in pending:
            pending.append("홀 수")
        elif "기본정보" not in pending:
            pending.append("기본정보")

    return ("pending" if pending else "confirmed"), confirmed, pending



def _eligible_round_course(club):
    return is_round_eligible(club)


def _over_18_holes_only(clubs):
    return [club for club in clubs if _eligible_round_course(club)]




def _truthy(value):
    return value in (True, "가능", "있음", "yes", "Y", "true", "True")


def _objective_feature_status(club, key):
    return objective_filter_value(club, key)

def _objective_display(club, feature):
    detail = get_objective_detail(club, feature)
    status = detail.get("status")
    if status == "confirmed": return "확인됨"
    if status == "conditional": return "조건부 확인"
    return "확인 필요"


def _kga_num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _kga_rating_summary(club):
    """KGA 저장 rating에서 대표 난이도 값을 만든다. 임의 rating 생성 없음."""
    ratings = ((club.get("kga") or {}).get("ratings") or [])
    if not ratings:
        return None

    # 사용자가 성별/티를 선택하지 않았으므로 특정 성별을 임의 우선하지 않는다.
    # 현재 개인화 검색은 KGA 등록 Slope의 전체 범위를 참고용으로만 사용한다.
    rows = ratings

    slopes = [_kga_num(r.get("slope_rating")) for r in rows]
    lengths = [_kga_num(r.get("length_yds")) for r in rows]
    slopes = [x for x in slopes if x is not None]
    lengths = [x for x in lengths if x is not None]

    if not slopes:
        return None

    return {
        "slope": sum(slopes) / len(slopes),
        "length_yds": (sum(lengths) / len(lengths)) if lengths else None,
    }


def _skill_target_slope(avg_score, challenge):
    """
    평균타수는 Handicap Index가 아니므로 공식 핸디캡 계산에 쓰지 않는다.
    아래 값은 검색 정렬용 '참고 목표 난이도'일 뿐이다.
    """
    score = int(avg_score or 100)
    if score >= 110:
        base = 118
    elif score >= 100:
        base = 123
    elif score >= 90:
        base = 128
    else:
        base = 133
    return base + {"편하게": -7, "적당히": 0, "도전": 8}.get(challenge, 0)


def _skill_fit(club, avg_score, challenge, avg_score_label=None):
    """
    KGA 공식 Slope/전장 수치는 근거로 유지하되,
    화면의 첫 문장은 사용자가 이해하기 쉬운 개인화 해석으로 표시한다.
    평균타수는 Handicap Index로 환산하지 않는다.
    """
    summary = _kga_rating_summary(club)
    if not summary:
        return {
            "known": False,
            "distance": 999.0,
            "label": "내게 맞는 난이도 판단에 정보가 더 필요해요",
            "detail": "KGA 공인 난이도 상세값 확인 필요",
        }

    slope = summary["slope"]
    target = _skill_target_slope(avg_score, challenge)
    distance = abs(slope - target)

    # 아래 문구는 KGA의 공식 난이도 등급이 아니라
    # 사용자가 선택한 평균타수/라운드 목적과 KGA 수치를 비교한 서비스 해석이다.
    if distance <= 5:
        label = "내가 원하는 난이도와 비슷해요"
    elif slope < target:
        label = "내 설정에서는 비교적 편하게 즐길 후보예요"
    else:
        label = "내 설정에서는 도전적인 코스예요"

    bits = []
    if summary.get("length_yds"):
        yards = summary["length_yds"]
        meters = yards * 0.9144
        bits.append(f"전장 {yards:,.0f}yd ({meters:,.0f}m)")

    # 숫자는 해석의 근거로 뒤에 작게 남긴다.
    bits.append(f"KGA 등록 Slope 참고값 {slope:.0f}")
    display_score = avg_score_label or (
        "110타 이상" if int(avg_score) >= 110 else
        "100타대" if int(avg_score) >= 100 else
        "90타대" if int(avg_score) >= 90 else
        "80타대"
    )
    bits.append(f"{display_score} · {challenge} 선택 기준 참고")

    return {
        "known": True,
        "distance": distance,
        "label": label,
        "detail": " · ".join(bits),
    }



def _master_evidence(club, field):
    """B_SUPPORTED 참고정보. 확정값을 덮어쓰지 않는다."""
    item = ((club.get("evidence") or {}).get(field) or {})
    if not isinstance(item, dict) or item.get("status") != "SUPPORTED":
        return None
    value = item.get("candidate")
    return None if value in (None, "", "없음", "미확인", "확인 필요") else value


def _master_value(club, field):
    """확정 catalog 값 우선, 없을 때만 B_SUPPORTED evidence를 표시용으로 사용."""
    value = club.get(field)
    if value not in (None, "", "없음", "미확인", "확인 필요"):
        return value, "confirmed"
    value = _master_evidence(club, field)
    if value is not None:
        return value, "evidence"
    return None, "missing"


def _holes_display(club):
    value, level = _master_value(club, "holes")
    if value is None:
        return "홀 수 확인 필요", level
    try:
        label = f"{int(float(str(value).replace('홀','').strip()))}홀"
    except (TypeError, ValueError):
        label = str(value)
    if level == "evidence":
        label += " · 참고정보"
    return label, level


def _phone_display(club):
    return _master_value(club, "phone")


def _avg_score_display(cond):
    label = str((cond or {}).get("avg_score_label") or "").strip()
    if label and label != "미선택":
        return label
    score = (cond or {}).get("avg_score")
    if not score:
        return ""
    score = int(score)
    if score >= 110: return "110타 이상"
    if score >= 100: return "100타대"
    if score >= 90: return "90타대"
    return "80타대"


def _operation_type_text(club):
    """저장된 명시적 운영형태만 표시. 없으면 추정하지 않는다."""
    public = ((club.get("verification") or {}).get("public_data") or {})
    candidates = [
        club.get("operation_type"),
        club.get("membership_type"),
        club.get("business_type"),
        club.get("club_type"),
        club.get("golf_type"),
        _master_evidence(club, "operation_type"),
        public.get("business_type"),
    ]
    raw = next((str(x).strip() for x in candidates if x and str(x).strip()), "")
    if not raw:
        return "운영형태 확인 필요"
    return normalize_operation_type(raw)


def _course_labels(club):
    """기존 catalog 코스와 KGA 코스조합에서 표시 가능한 코스명을 모은다."""
    labels = []

    for item in (club.get("courses") or []):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            holes = item.get("holes")
            if name:
                label = f"{name} {holes}H" if holes else name
                labels.append(label)
        elif item:
            labels.append(str(item).strip())

    # catalog 코스가 부족하면 KGA 안전 매칭 결과를 보조로 사용
    if not labels:
        for item in ((club.get("kga") or {}).get("course_combinations") or []):
            if isinstance(item, dict):
                names = [
                    str(item.get(k) or "").strip()
                    for k in ("course", "course_name", "combination", "name")
                    if item.get(k)
                ]
                if names:
                    labels.append(names[0])
            elif item:
                labels.append(str(item).strip())

    out = []
    seen = set()
    for x in labels:
        x = re.sub(r"\s+", " ", str(x)).strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out[:8]


def _fact_based_intro(club):
    """확보된 사실만 조합해 2문장 이내 소개를 만든다."""
    location = " ".join(
        str(x).strip() for x in (club.get("region"), club.get("city"))
        if x and str(x).strip()
    )
    holes, holes_level = _master_value(club, "holes")
    op = _operation_type_text(club)
    courses = _course_labels(club)

    first = []
    if location:
        first.append(f"{location}에 위치")
    if holes:
        try:
            holes_text = f"{int(float(str(holes).replace('홀','').strip()))}홀 규모"
        except (TypeError, ValueError):
            holes_text = f"{holes} 규모"
        if holes_level == "evidence":
            holes_text += "(참고정보)"
        first.append(holes_text)
    if op != "운영형태 확인 필요":
        first.append(op)

    sentences = []
    if first:
        sentences.append(" · ".join(first) + " 골프장입니다.")
    else:
        sentences.append("현재 확보된 공식·공공 데이터를 기준으로 기본정보를 제공하고 있습니다.")

    if courses:
        shown = ", ".join(courses[:4])
        sentences.append(f"확인된 코스 구성은 {shown}입니다.")
    elif (club.get("kga") or {}).get("matched"):
        sentences.append("KGA 코스정보가 연결된 골프장입니다.")

    return " ".join(sentences[:2])


def _overview_trait_badges(club):
    """저장된 후기/특징 값만 사용. 없는 특징은 만들지 않는다."""
    return _descriptive_badges(club)


def _descriptive_badges(club):
    """카드에 표시할 주관적 특징은 필터가 아니라 참고 배지로만 사용."""
    badges = []
    traits = club.get("traits") or []
    rt = club.get("review_traits") or {}
    keys = set(traits if isinstance(traits, list) else [])
    if isinstance(rt, dict):
        keys.update(k for k,v in rt.items() if v is True)
    elif isinstance(rt, list):
        keys.update(rt)
    labels = {
        "fairway_wide": "⛳ 페어웨이 넓음",
        "maintenance_good": "🌿 관리 좋음",
        "facilities_good": "✨ 시설 좋음",
        "green_fast": "🔥 빠른 그린",
    }
    for k,label in labels.items():
        if k in keys: badges.append(label)
    return badges[:3]


# =========================================================
# SEARCH (페이지의 조건 검색 / AI 문장검색 / 직접 찾기 로직)
# =========================================================

from services.golf_catalog import (  # noqa: E402
    _subregion_match,
    find_clubs,
    load_review_seed,
    load_service_catalog,
    parse_ai_conditions,
)
from services.golf_master import FEATURES, matches_objective_conditions  # noqa: E402
from services.golf_review_store import load_runtime_summary, save_runtime_summary  # noqa: E402

SUPPORTED_GOLF_AREAS = {"수도권", "충청권", "강원권"}
AREA_OPTIONS = ["수도권", "충청권", "강원권"]
SUBREGION_MAP = {
    "수도권": ["서울", "인천", "경기남부", "경기북부"],
    "충청권": ["충북", "충남"],
    "강원권": ["강원영서", "강원영동"],
}
BUDGETS = {
    "전체": None, "10만 이하": 100000, "15만 이하": 150000,
    "20만 이하": 200000, "25만 이하": 250000, "30만 이하": 300000,
}
AVG_SCORES = {"80타대": 85, "90타대": 95, "100타대": 105, "110타 이상": 115}
SESSIONS = ["1부", "2부", "3부"]
CHALLENGES = ["편하게", "적당히", "도전"]
SORTS = ["추천순", "가까운순", "가격순"]


def _public_operating_candidate(club):
    """공공데이터상 영업이 확인된 candidate를 조건/AI 검색 Pool에 포함."""
    if club.get("service_status") != "candidate":
        return False
    public = ((club.get("verification") or {}).get("public_data") or {})
    return public.get("matched") is True and public.get("operating_in_public_data") is True


def _apply_official_players(club):
    """operations.players에 공식 출처로 '가능'이 확인된 2인/3인 플레이를 이용조건(features)에 반영한다.
    불가 값은 기존 정책대로 필터 제외 근거로 쓰지 않는다(needs_check 유지)."""
    players = (club.get("operations") or {}).get("players") or {}
    if not isinstance(players, dict):
        return
    runtime = dict(club.get("_golf_runtime") or {})
    features = dict(runtime.get("features") or {})
    changed = False
    for key in ("two_person", "three_person"):
        item = players.get(key)
        if not isinstance(item, dict) or item.get("allowed") is not True:
            continue
        if (features.get(key) or {}).get("status") == "confirmed":
            continue
        source = item.get("source_url") or players.get("source_url")
        if not source:
            continue
        notes = [str(item[k]) for k in ("condition", "policy_text") if item.get(k)]
        if item.get("surcharge_team"):
            notes.append(f"팀 추가요금 {int(item['surcharge_team']):,}원")
        features[key] = dict(
            status="confirmed", label="확인됨", verification_class="OFFICIAL_SOURCE",
            checked_at=item.get("checked_at") or players.get("checked_at"),
            sources=[source], condition_notes=notes, conflict=False,
        )
        changed = True
    if changed:
        runtime["features"] = features
        club["_golf_runtime"] = runtime


_db_mtime = {}


def _refresh_if_db_changed():
    """분기 갱신 등으로 활성 DB 파일이 수정되면 캐시를 비워 서버 재시작 없이 반영한다."""
    from services import golf_repository
    path = golf_repository.load_active_db()["path"]
    try:
        mtime = path.stat().st_mtime
    except OSError:
        golf_repository.clear_cache()
        return
    if _db_mtime.get("path") == path and _db_mtime.get("mtime") != mtime:
        golf_repository.clear_cache()
    _db_mtime.update(path=path, mtime=mtime)


def load_pools():
    """(전체 원장, 직접검색 Pool, 조건/AI 검색 Pool)"""
    _refresh_if_db_changed()
    all_clubs = load_service_catalog()
    for club in all_clubs:
        _apply_official_players(club)
    clubs = [c for c in all_clubs if c["service_status"] != "excluded" and _eligible_round_course(c)]
    condition_search_clubs = [
        c for c in all_clubs
        if c.get("area") in SUPPORTED_GOLF_AREAS
        and (c.get("service_status") == "service" or _public_operating_candidate(c))
        and _eligible_round_course(c)
    ]
    return all_clubs, clubs, condition_search_clubs


def search_options():
    all_clubs, clubs, pool = load_pools()
    runtime = (all_clubs[0].get("_golf_runtime") or {}) if all_clubs else {}
    return {
        "areas": AREA_OPTIONS,
        "subregions": SUBREGION_MAP,
        "budgets": list(BUDGETS),
        "sessions": SESSIONS,
        "caddie": ["전체", "캐디", "노캐디"],
        "players": ["전체", "3인", "4인"],
        "avg_scores": ["미선택", *AVG_SCORES],
        "challenges": CHALLENGES,
        "sorts": SORTS,
        "counts": {"all": len(all_clubs), "searchable": len(clubs), "pool": len(pool)},
        "runtime_ok": runtime.get("diagnostic") in ("ok", "disabled"),
        "naver_enabled": all(_naver_keys()),
    }


def find_by_name(query, limit=20):
    _, clubs, _ = load_pools()
    return [
        {"id": x["id"], "name": x["name"], "region": x.get("region", ""), "city": x.get("city", "")}
        for x in (find_clubs(query, clubs) or [])[:limit]
    ]


def build_condition(params):
    """화면 입력값 → 페이지와 동일한 cond dict. (cond, 출발지 안내문)"""
    params = params or {}
    areas = [a for a in (params.get("areas") or []) if a in SUPPORTED_GOLF_AREAS]
    single_area = areas[0] if len(areas) == 1 else None
    subregions = [s for s in (params.get("subregions") or []) if s in SUBREGION_MAP.get(single_area, [])]

    # 요금표가 주중/주말 단위라 날짜 대신 요일 구분만 받는다. (round_date가 오면 그 날짜의 요일을 따른다)
    round_date = None
    try:
        round_date = date.fromisoformat(params["round_date"]) if params.get("round_date") else None
    except (TypeError, ValueError):
        round_date = None
    weekend = _date_is_weekend(round_date) if round_date else params.get("day") == "주말"

    players_choice = params.get("players") or "전체"
    objective_choice = []
    if players_choice == "3인":
        objective_choice.append("3인 플레이")
    if params.get("night"):
        objective_choice.append("야간 라운드")

    avg_score_label = params.get("avg_score_label") or "미선택"
    departure = str(params.get("departure") or "").strip()

    # 출발지 좌표화: 주소는 NAVER, 역·건물명은 VWorld 장소검색으로 보완.
    departure_geo, geocoder_available = geocode_departure(departure) if departure else (None, True)

    cond = {
        "area": single_area or "전체",
        "areas": areas,
        "city": None,
        "subregions": subregions,
        "weekend": weekend,
        "round_date": round_date.isoformat() if round_date else None,
        "session": params.get("session") if params.get("session") in SESSIONS else None,
        "departure": departure,
        "departure_coord": [departure_geo["lat"], departure_geo["lon"]] if departure_geo else None,
        "departure_address": (
            departure_geo.get("road_address") or departure_geo.get("jibun_address")
            if departure_geo else ""
        ),
        "caddie": params.get("caddie") or "전체",
        "budget": params.get("budget") if isinstance(params.get("budget"), int) else BUDGETS.get(params.get("budget")),
        "objective_features": objective_choice,
        "players": 3 if players_choice == "3인" else 4,
        "avg_score": AVG_SCORES.get(avg_score_label),
        "avg_score_label": avg_score_label,
        "challenge": params.get("challenge") or "적당히",
    }

    status = None
    if departure:
        if departure_geo:
            address = departure_geo.get("road_address") or departure_geo.get("jibun_address") or departure
            place = departure_geo.get("place_name")
            status = "출발지 확인 · " + (f"{place} ({address})" if place else address)
        elif not geocoder_available:
            status = "출발지 거리계산 미사용 · NAVER Cloud Maps 또는 VWorld 키 필요"
        else:
            status = "출발지 좌표 확인 실패 · 주소나 장소명을 조금 더 구체적으로 입력해 주세요"
    return cond, status


def _has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_value(item) for item in value)
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    return False


def _has_amount(value):
    if isinstance(value, bool) or not _has_value(value):
        return False
    try:
        amount = float(str(value).replace(",", "").replace("원", "").strip())
    except (TypeError, ValueError):
        return False
    return math.isfinite(amount) and amount >= 0


def _condition_sort_key(club, cond):
    """확인된 선택조건 수 → 미확인 수 → 요금 확인 → 정보 충실도 → 이름순."""
    confirmed_features = sum(
        _objective_feature_status(club, feature) is True
        for feature in set(cond.get("objective_features") or [])
    )
    _status, _confirmed, pending = _result_confidence(club, cond)
    price_missing = 0
    if cond.get("budget"):
        try:
            estimated = estimate_per_person(club, bool(cond.get("weekend")), int(cond.get("players") or 4))
        except Exception:
            estimated = None
        price_missing = 0 if _has_amount(estimated) else 1

    fee = club.get("fee") or {}
    fee_known = isinstance(fee, dict) and (
        fee.get("verified") is True
        or any(_has_amount(fee.get(key)) for key in (
            "weekday_green", "weekend_green", "weekday", "weekend",
            "cart_team", "caddie_team", "three_person_weekday_extra",
            "three_person_weekend_extra",
        ))
    )
    information_count = sum((
        _has_value(club.get("holes")),
        any(_has_value(club.get(key)) for key in ("official_url", "website", "homepage")),
        any(_has_value(club.get(key)) for key in ("booking_url", "reservation_url", "reserve_url")),
        _has_value(club.get("phone")),
        _has_value(club.get("address")),
        club_lat_lon(club) is not None,
        fee_known,
        _has_value(club.get("courses")),
        _has_value(club.get("play")),
        _has_value(club.get("facilities")),
        _has_value(club.get("data_checked")),
    ))
    return (-confirmed_features, len(pending), price_missing, -information_count, str(club.get("name") or ""))


def _recommendation_score(club, cond):
    """조건 확인도 + 가격 근거 + 데이터 완성도 + KGA 난이도 적합도."""
    score = 0.0
    reasons = []

    selected_features = set(cond.get("objective_features") or [])
    confirmed_features = sum(_objective_feature_status(club, f) is True for f in selected_features)
    conditional_features = sum(get_objective_status(club, f) == "conditional" for f in selected_features)
    score += confirmed_features * 14
    score += conditional_features * 4
    if confirmed_features:
        reasons.append(f"선택조건 {confirmed_features}개 확인")

    _status, confirmed_fields, pending_fields = _result_confidence(club, cond)
    score += min(len(confirmed_fields), 5) * 5
    score -= min(len(pending_fields), 5) * 3

    if cond.get("budget"):
        try:
            estimated = estimate_per_person(club, bool(cond.get("weekend")), int(cond.get("players") or 4))
        except Exception:
            estimated = None
        if estimated is not None:
            score += 12
            if estimated <= cond["budget"]:
                margin = max(cond["budget"] - estimated, 0)
                score += min(margin / max(cond["budget"], 1) * 8, 8)
                reasons.append("예산 범위 확인")
        else:
            score -= 4

    info_fields = [
        club.get("holes"), club.get("phone"), club.get("address"),
        club.get("official_url") or club.get("website") or club.get("homepage"),
        club.get("booking_url") or club.get("reservation_url") or club.get("reserve_url"),
        club.get("courses"), club.get("facilities"), club.get("data_checked"),
    ]
    info_count = sum(bool(v) for v in info_fields)
    score += info_count * 1.5
    if info_count >= 6:
        reasons.append("기본정보 충실")

    if cond.get("avg_score"):
        skill = _skill_fit(club, cond["avg_score"], cond.get("challenge") or "적당히", cond.get("avg_score_label"))
        if skill.get("known"):
            distance = float(skill.get("distance") or 0)
            score += max(18 - min(distance, 18), 0)
            reasons.append("난이도 적합도 확인")
        else:
            score -= 2

    public = club.get("public_data") or {}
    if public.get("matched") is True and public.get("operating_in_public_data") is True:
        score += 5
        reasons.append("공공데이터 영업 확인")

    return round(score, 1), reasons


def condition_search(params, sort="추천순"):
    cond, departure_status = build_condition(params)
    _, _, pool = load_pools()

    total_count = len(pool)
    search_clubs = list(pool)
    if cond["areas"]:
        search_clubs = [c for c in search_clubs if c.get("area") in cond["areas"]]
    area_count = len(search_clubs)

    if cond["subregions"]:
        search_clubs = [c for c in search_clubs if any(_subregion_match(c, sub) for sub in cond["subregions"])]
    subregion_count = len(search_clubs)

    # 추가조건은 정보가 확인된 레코드에 대해서만 판정한다. 정보가 없으면 '충족'으로 추정하지 않는다.
    filtered = []
    for club in search_clubs:
        ok = _matches_caddie(club, cond.get("caddie"))
        if ok and cond.get("budget"):
            # 화면의 예산은 '그린피' 기준. 그린피를 알면 그린피로, 모르면 1인 예상가로 비교한다.
            try:
                est = _cond_session_fee(club, cond)
                if est is None:
                    est = estimate_per_person(club, bool(cond.get("weekend")), int(cond.get("players") or 4))
            except Exception:
                est = None
            if est is not None and est > cond["budget"]:
                ok = False
        if not matches_objective_conditions(club, cond.get("objective_features", [])):
            ok = False
        if ok:
            filtered.append(club)

    # 선택한 예산/캐디/3인/야간은 확인된 골프장만 결과에 포함한다.
    strict_filtered = []
    for club in filtered:
        issues, unknowns = _eligibility(club, cond)
        if not issues and not unknowns:
            strict_filtered.append(club)
    has_strict_condition = bool(
        cond.get("budget")
        or cond.get("caddie") not in (None, "", "전체")
        or int(cond.get("players") or 4) == 3
        or cond.get("night")
    )
    if has_strict_condition:
        filtered = strict_filtered
    final_count = len(filtered)

    scored = {c["id"]: _recommendation_score(c, cond) for c in filtered}
    filtered = sorted(
        filtered,
        key=lambda c: (-scored[c["id"]][0], _condition_sort_key(c, cond), str(c.get("name") or "")),
    )

    confirmed_count = pending_count = conditional_count = 0
    for club in filtered:
        if any(get_objective_status(club, f) == "conditional" for f in cond.get("objective_features", [])):
            conditional_count += 1
        status, _, _ = _result_confidence(club, cond)
        if status == "confirmed":
            confirmed_count += 1
        else:
            pending_count += 1

    all_recs = [
        (club, [f"추천점수 {scored[club['id']][0]:.1f}"] + scored[club["id"]][1])
        for club in filtered
    ]
    trace = {
        "total": total_count,
        "area": area_count,
        "subregion": subregion_count,
        "final": final_count,
        "conditional": conditional_count,
        "confirmed": confirmed_count,
        "pending": pending_count,
        "excluded": max(subregion_count - final_count, 0),
    }
    return _build_results(all_recs, cond, trace, sort, departure_status)


def ai_condition(text):
    cond = parse_ai_conditions(text, "전체", False, 4, None)
    cond["players_specified"] = cond.get("players") is not None
    cond["players"] = int(cond.get("players") or 4)
    cond["areas"] = [] if cond.get("area") == "전체" else [cond.get("area")]
    cond["subregions"] = []
    cond["objective_features"] = ["3인 플레이"] if cond["players"] == 3 else []
    return cond


def condition_from_request(search):
    """상세화면용: 직전 검색요청({"text"} 또는 {"params"})으로 cond를 다시 만든다."""
    if not search:
        return {}
    if search.get("text"):
        return ai_condition(search["text"])
    return build_condition(search.get("params") or {})[0]


def ai_search(text, sort="추천순"):
    cond = ai_condition(text)

    _, _, pool = load_pools()
    total_count = len(pool)
    search_clubs = list(pool)

    if cond.get("area") and cond["area"] != "전체":
        search_clubs = [c for c in search_clubs if c.get("area") == cond["area"]]
    area_count = len(search_clubs)

    # 도시명: city/address/name에 실제 문자열이 있는 레코드만
    if cond.get("city"):
        city = str(cond["city"])
        search_clubs = [
            c for c in search_clubs
            if city in " ".join(str(c.get(k) or "") for k in ("city", "address", "name", "subregion"))
        ]
    city_count = len(search_clubs)

    filtered = []
    for club in search_clubs:
        ok = matches_objective_conditions(club, cond.get("objective_features", []))
        if ok and cond.get("budget"):
            est = estimate_per_person(club, bool(cond.get("weekend")), int(cond.get("players") or 4))
            if est is not None and est > cond["budget"]:
                ok = False
        if ok:
            filtered.append(club)

    filtered = sorted(filtered, key=lambda x: str(x.get("name") or ""))
    trace = {"total": total_count, "area": area_count, "subregion": city_count, "final": len(filtered)}
    parsed = {
        "area": cond.get("area") or "전체",
        "city": cond.get("city") or "전체",
        "day": "주말/공휴일" if cond.get("weekend") else "주중",
        "players": f"{cond.get('players', 4)}인",
        "budget": f"{cond['budget'] // 10000}만원 이하" if cond.get("budget") else "제한 없음",
        "traits": ", ".join(cond.get("traits") or []) or "없음",
    }
    result = _build_results([(c, ["문장 검색조건 충족"]) for c in filtered], cond, trace, sort, None)
    result["parsed"] = parsed
    return result


def _applied_chips(cond):
    chips = [" · ".join(cond.get("areas") or ["전국"])]
    if cond.get("subregions"):
        chips.append(" / ".join(cond["subregions"]))
    elif cond.get("city"):
        chips.append(str(cond["city"]))
    if cond.get("round_date"):
        try:
            chips.append(_round_date_label(date.fromisoformat(cond["round_date"])))
        except Exception:
            pass
    if cond.get("session"):
        chips.append(cond["session"])
    if cond.get("caddie") and cond.get("caddie") != "전체":
        chips.append(cond["caddie"])
    chips.append("주말/공휴일" if cond.get("weekend") else "주중")
    if cond.get("budget"):
        chips.append(f'{cond["budget"] // 10000}만원 이하')
    chips.extend(cond.get("objective_features") or [])
    if cond.get("avg_score"):
        chips.append(f"{_avg_score_display(cond)} 참고")
        chips.append(cond.get("challenge") or "적당히")
    return chips


def _departure_coord(cond):
    raw = (cond or {}).get("departure_coord")
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        try:
            return float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            return None
    return None


def _card(course, reasons, cond, route_cache):
    status, confirmed_fields, pending_fields = _result_confidence(course, cond)
    est = estimate_per_person(course, bool(cond.get("weekend")), int(cond.get("players", 4)))

    facts = []
    km = _distance_from_departure(course, _departure_coord(cond))
    route = route_cache.get(course.get("id"))
    if route and route.get("distance_km") is not None:
        route_text = f"차량 {route['distance_km']:.1f}km"
        if route.get("duration_min") is not None:
            route_text += f" · 약 {route['duration_min']}분"
        facts.append(route_text)
    elif km is not None:
        facts.append(f"직선거리 {km:.1f}km")

    facts.append(_holes_display(course)[0])
    session_fee = _cond_session_fee(course, cond)
    if session_fee is not None:
        facts.append(f"{cond.get('session') or ''} 그린피 {won(session_fee)}".strip())
    elif est is not None:
        facts.append(f"예상 1인 {won(est)}")
    else:
        facts.append("요금 확인 필요")
    facts.append(f"캐디 {_caddie_summary(course)}")
    if "3인 플레이" in (cond.get("objective_features") or []):
        facts.append(f"3인 {_objective_display(course, '3인 플레이')}")

    if status == "confirmed":
        badge = "✓ 선택조건 확인"
        evidence = ("확인: " + " · ".join(confirmed_fields)) if confirmed_fields else "선택조건 확인"
    else:
        badge = "△ 일부정보 확인 필요"
        evidence = ("확인 필요: " + " · ".join(pending_fields[:3])) if pending_fields else "일부 정보 확인 필요"

    loc = " ".join(str(x).strip() for x in (course.get("region"), course.get("city")) if x and str(x).strip())
    return {
        "id": course["id"],
        "name": course["name"],
        "location": loc or course.get("area", ""),
        "status": status,
        "badge": badge,
        "facts": facts,
        "badges": _descriptive_badges(course)[:4],
        "reasons": reasons[:2],
        "evidence": evidence,
    }


def _build_results(all_recs, cond, trace, sort, departure_status):
    normalized_all = [_normalize_result_item(x) for x in all_recs]
    departure_coord = _departure_coord(cond)
    route_cache = {}
    notice = None

    if sort == "가까운순":
        if departure_coord:
            def straight(item):
                d = _distance_from_departure(item[0], departure_coord)
                return (d is None, d if d is not None else float("inf"))

            # API 호출량을 줄이기 위해 직선거리 상위 20개만 실주행 거리를 조회한다.
            pre_sorted = sorted(normalized_all, key=straight)
            nearest = [course for course, _ in pre_sorted[:20]]
            with ThreadPoolExecutor(max_workers=8) as pool:
                routes = pool.map(lambda c: _route_for_course(c, cond), nearest)
            route_cache = {c.get("id"): r for c, r in zip(nearest, routes)}
            normalized_all = sorted(
                pre_sorted,
                key=lambda x: (
                    route_cache.get(x[0].get("id")) is None,
                    (route_cache.get(x[0].get("id")) or {}).get("distance_km", float("inf")),
                    straight(x)[1],
                    str(x[0].get("name") or ""),
                ),
            )
        else:
            notice = "가까운순은 출발지 좌표가 확인될 때 적용됩니다. 현재는 추천순을 유지합니다."
    elif sort == "가격순":
        normalized_all = sorted(
            normalized_all,
            key=lambda x: (_sort_price(x[0], cond) == float("inf"), _sort_price(x[0], cond), str(x[0].get("name") or "")),
        )

    items = [_card(course, reasons, cond, route_cache) for course, reasons in normalized_all]

    # 확인된 결과가 부족하면 점수순 상위 결과로 TOP 4를 채운다.
    top = [x for x in items if x["status"] == "confirmed"][:4]
    used = {x["id"] for x in top}
    for x in items:
        if len(top) >= 4:
            break
        if x["id"] not in used:
            top.append(x)
            used.add(x["id"])

    return {
        "applied": _applied_chips(cond),
        "departure_status": departure_status,
        "trace": trace,
        "sort": sort,
        "notice": notice,
        "top_ids": [x["id"] for x in top],
        "items": items,
        "has_departure": bool(departure_coord),
    }


# =========================================================
# DETAIL
# =========================================================

def _kga_block(club):
    kga = club.get("kga") or {}
    if not kga.get("matched"):
        return {"matched": False}
    combos = [" ".join(str(x or "").split()) for x in (kga.get("course_combinations") or [])]
    ratings = []
    for r in (kga.get("ratings") or [])[:8]:
        length = r.get("length_yds")
        cr = r.get("course_rating")
        slope = r.get("slope_rating")
        parts = [x for x in [
            f"{r.get('course')} ·" if r.get("course") and len(combos) > 1 else None,
            f"{r.get('tee') or '티'} {r.get('gender') or ''}".strip(),
            f"{length:,}yd" if isinstance(length, (int, float)) else None,
            f"Course Rating {cr}" if cr not in (None, "") else None,
            f"Slope {slope}" if slope not in (None, "") else None,
        ] if x]
        ratings.append(" ".join(parts).replace("· ·", "·"))
    return {
        "matched": True,
        "status": kga.get("status", "KGA 코스정보 확인"),
        "checked_at": kga.get("checked_at", "-"),
        "combos": [c for c in combos if c],
        "ratings": ratings,
        "source_url": kga.get("source_url") or "",
    }


def _hole_rows(course_details):
    rows = []
    for course in course_details:
        if not isinstance(course, dict):
            continue
        cname = str(course.get("name") or course.get("course_name") or course.get("course") or "").strip()
        holes_data = course.get("holes") or course.get("hole_details") or course.get("hole_info") or []
        if isinstance(holes_data, dict):
            holes_data = holes_data.get("items") or holes_data.get("holes") or []
        if not isinstance(holes_data, list):
            continue

        for idx, hole in enumerate(holes_data, start=1):
            if not isinstance(hole, dict):
                continue
            hole_no = hole.get("hole") or hole.get("hole_no") or hole.get("number") or idx
            par = hole.get("par")
            hdcp = hole.get("hdcp") or hole.get("handicap") or hole.get("hcp")
            if hdcp in (None, "") and (hole.get("hdcp_men") or hole.get("hdcp_women")):
                hdcp = f"남 {hole.get('hdcp_men', '-')} / 여 {hole.get('hdcp_women', '-')}"
            distances = (hole.get("distances_m") or hole.get("distance_m") or hole.get("distance")
                         or hole.get("length_m") or hole.get("published_distance_m") or hole.get("champion_m"))
            unit = "m"
            if isinstance(distances, dict):
                unit = {"meter": "m", "yard": "yd", "yards": "yd"}.get(str(distances.get("unit") or "meter"), "m")
                distances = {k: v for k, v in distances.items() if k != "unit"}
            elif distances in (None, "") and hole.get("distance_yard"):
                distances, unit = hole.get("distance_yard"), "yd"
            if isinstance(distances, dict):
                dist_text = " / ".join(f"{k} {v}{unit}" for k, v in distances.items() if v not in (None, ""))
            elif isinstance(distances, list):
                dist_text = " / ".join(str(v) for v in distances if v not in (None, ""))
            elif distances not in (None, ""):
                dist_text = str(distances)
                if re.fullmatch(r"\d+(?:\.\d+)?", dist_text):
                    dist_text += unit
            else:
                dist_text = ""

            hazards = hole.get("hazards") or hole.get("hazard") or ""
            bunkers = hole.get("bunkers") or hole.get("bunker") or ""
            strategy = (hole.get("official_strategy") or hole.get("official_strategy_summary")
                        or hole.get("strategy") or hole.get("summary") or "")
            facts = []
            if par not in (None, ""):
                facts.append(f"Par {par}")
            if dist_text:
                facts.append(dist_text)
            if hdcp not in (None, ""):
                facts.append(f"HDCP {hdcp}")
            if hole.get("operator_average_score") not in (None, ""):
                facts.append(f"평균 {hole['operator_average_score']}타")
            if hazards:
                facts.append("해저드 " + str(hazards))
            if bunkers:
                facts.append("벙커 " + str(bunkers))
            rows.append({
                "course": cname,
                "hole": str(hole_no),
                "facts": " · ".join(facts),
                "strategy": str(strategy).strip(),
            })
    return rows


def _course_cards(club, course_details):
    """코스별 카드: 정밀 DB의 course_groups → course_details → courses 순으로 사용."""
    groups = club.get("course_groups") if isinstance(club.get("course_groups"), list) else []
    display_courses = groups or course_details or (club.get("courses") or [])
    cards = []
    for course in display_courses:
        if isinstance(course, dict):
            name = str(course.get("name") or course.get("course_name") or course.get("course") or "").strip()
            holes = course.get("holes")
            count = (course.get("holes_count") or course.get("hole_count")
                     or (len(holes) if isinstance(holes, list) and holes else None)
                     or (holes if isinstance(holes, (int, float)) else None))
            title = (name or "코스") + (f" · {count}H" if count else "")
            specs = []
            par = course.get("par") or course.get("par_total")
            if par:
                specs.append(f"Par {par}")
            length = course.get("length_meters") or course.get("length_m") or course.get("total_distance_m")
            if length:
                specs.append(f"{int(length):,}m")
            if course.get("designer"):
                specs.append(f"설계 {course['designer']}")
            desc = str(course.get("characteristics") or course.get("characteristic") or course.get("official_description")
                       or course.get("summary") or course.get("type") or course.get("course_type")
                       or course.get("description") or "").strip()
            source = course.get("source_url") or course.get("description_source_url") or (
                course.get("source") if str(course.get("source") or "").startswith("http") else "")
            cards.append({"title": title, "specs": " · ".join(specs), "type": desc, "source_url": source or ""})
        elif str(course).strip():
            cards.append({"title": str(course).strip(), "specs": "", "type": "", "source_url": ""})
    return cards


def _kga_ratings_table(club):
    """정밀 DB course_rating(공식 KGA) 우선, 없으면 kga.ratings."""
    rows = []
    for r in (club.get("course_rating") or []):
        if isinstance(r, dict):
            rows.append({"course": r.get("course") or "", "tee": r.get("tee") or "", "gender": r.get("gender") or "",
                         "rating": r.get("rating"), "slope": r.get("slope"), "length_yards": r.get("length_yards")})
    if not rows:
        for r in ((club.get("kga") or {}).get("ratings") or []):
            rows.append({"course": r.get("course") or "", "tee": r.get("tee") or "", "gender": r.get("gender") or "",
                         "rating": r.get("course_rating"), "slope": r.get("slope_rating"), "length_yards": r.get("length_yds")})
    return rows


def _fee_block(club):
    """정밀 요금표(pricing) 요약 + 카트/캐디 팀 요금. 요금표가 없으면 기존 fee 방식."""
    summary = fee_summary(club)
    if summary and (summary["weekday"] or summary["weekend"] or summary["unspecified"]):
        cart, caddie = team_fee(club, "cart"), team_fee(club, "caddie")
        per_person = ((cart or 0) + (caddie or 0)) / 4
        def total(rng):
            return [int(rng[0] + per_person), int(rng[1] + per_person)] if rng else None
        return {
            "verified": True,
            "kind": "table",
            "weekday": summary["weekday"], "weekend": summary["weekend"], "unspecified": summary["unspecified"],
            "weekday_sessions": summary["weekday_sessions"], "weekend_sessions": summary["weekend_sessions"],
            "weekday_total": total(summary["weekday"]), "weekend_total": total(summary["weekend"]),
            "cart": cart, "caddie": caddie,
            "is_current": summary["is_current"],
            "checked_at": summary["checked_at"],
            "latest_notice_month": summary["latest_notice_month"],
            "source_url": summary["source_url"],
            "note": ("비회원 18홀 공식 요금 기준 · 1인 예상은 카트·캐디 팀요금 ÷ 4 포함"
                     + ("" if summary["is_current"] else " · 현재 기간 요금표가 없어 가장 최근 공식 요금으로 표시")),
        }
    fee = club.get("fee", {}) or {}
    if fee.get("verified"):
        three_person = (club.get("play", {}) or {}).get("three_person", "확인 필요")
        return {
            "verified": True,
            "kind": "legacy",
            "weekday_total": estimate_per_person(club, False, 4),
            "weekend_total": estimate_per_person(club, True, 4),
            "weekday_green": fee.get("weekday_green") or fee.get("weekday") or 0,
            "weekend_green": fee.get("weekend_green") or fee.get("weekend") or 0,
            "cart": fee.get("cart_team", 0),
            "caddie": fee.get("caddie_team", 0),
            "note": f'{fee.get("basis", "공식 안내")} · 4인 기준 · 3인 {three_person} · 실제 예약가 변동 가능',
        }
    extras = []
    cart, caddie = fee.get("cart_team") or team_fee(club, "cart"), fee.get("caddie_team") or team_fee(club, "caddie")
    if cart:
        extras.append(f'카트 {won(cart)} / 팀')
    if caddie:
        extras.append(f'캐디 {won(caddie)} / 팀')
    detail = " · ".join(extras) if extras else "상세요금 공식 확인 필요"
    return {"verified": False, "text": f'{fee.get("basis", "그린피 공식 확인 필요")} · {detail}'}


def _review_cards_from_saved(summary, label="저장 분석"):
    dims = summary.get("dimensions", {})
    cards = []
    for dim, name in DIMS.items():
        item = dims.get(dim, {"verdict": "후기 정보 부족", "mentions": 0})
        mentions = int(item.get("mentions", 0) or 0)
        cards.append({
            "name": name,
            "verdict": str(item.get("verdict") or "후기 정보 부족"),
            "sub": f"언급 {mentions}건" if mentions > 0 else label,
        })
    return cards


def _recent_links(source_reviews):
    """원문 링크 = 현재년도 ~ 2년 전, 날짜 확인된 후기만, URL 중복 제거, 최대 8개."""
    current_year = date.today().year
    cutoff_year = current_year - 2
    links = []
    for review in source_reviews or []:
        year = get_review_year(review)
        url = (review.get("url") or "").strip()
        if year is None or not (cutoff_year <= year <= current_year) or not url:
            continue
        links.append({
            "date": str(review.get("date") or review.get("published_date") or ""),
            "title": review.get("title") or review.get("source") or "라운딩 후기",
            "url": url,
            "year": year,
            "preview": review_preview(review),
        })
    unique, seen = [], set()
    for item in sorted(links, key=lambda x: (x["year"], x["date"]), reverse=True):
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        unique.append(item)
    return unique[:8], cutoff_year, current_year


def _saved_summary(club_id):
    """화면에 표시할 저장본: 의미 있는 runtime 분석 우선, 없으면 seed."""
    runtime_saved = load_runtime_summary(club_id)
    return runtime_saved if has_meaningful_summary(runtime_saved) else load_review_seed().get(club_id)


def _saved_mentions(club_id):
    dims = (_saved_summary(club_id) or {}).get("dimensions", {})
    return sum(int((dims.get(d) or {}).get("mentions", 0) or 0) for d in DIMS)


def _reviews_block(club):
    saved = _saved_summary(club["id"])

    analysis = None
    if has_meaningful_summary(saved):
        meta = saved.get("note") or "저장된 후기 분석"
        if saved.get("updated"):
            meta += f" · 분석일 {saved['updated']}"
        analysis = {"cards": _review_cards_from_saved(saved), "meta": meta}

    source = (saved or {}).get("reviews", []) if isinstance(saved, dict) else []
    links, cutoff_year, current_year = _recent_links(source)
    return {
        "naver_search_url": "https://search.naver.com/search.naver?query=" + quote_plus(f"{club['name']} 라운딩 후기"),
        "analysis": analysis,
        "links": links,
        "cutoff_year": cutoff_year,
        "current_year": current_year,
        "can_analyze": bool(get_secret("TAVILY_API_KEY") and get_secret("OPENAI_API_KEY")),
    }


_CATEGORY_LABELS = {
    "basic_identity": "기본정보", "course_structure": "코스 구성", "green_fee": "그린피", "caddie": "캐디",
    "cart": "카트", "player_conditions": "인원 조건", "hole_details": "홀별 정보",
    "official_strategy": "공식 공략", "recent_evaluation": "최근 평가",
}
_SOURCE_LABELS = {"official_homepage": "공식 홈페이지", "public_data": "공공데이터", "KGA": "대한골프협회(KGA)",
                  "kga": "대한골프협회(KGA)", "licensed_booking_platform": "제휴 예약처"}
_CART_TYPES = {"electric_5seat": "전동 5인승", "electric_5seat_4bag": "전동 5인승(4백)"}


def _profile_block(club):
    """공식 출처가 확인된 개요/연혁/정식명칭."""
    ov = club.get("club_overview") or {}
    hist = club.get("club_history") or {}
    ident = club.get("identity_verification") or {}
    bits = []
    if ov.get("opened_at"):
        bits.append(f"개장 {str(ov['opened_at'])[:10]}")
    if ov.get("par_total"):
        bits.append(f"Par {ov['par_total']}")
    if hist.get("current_name_since"):
        bits.append(f"현재 명칭 {hist['current_name_since']}년부터")
    for key, value in hist.items():
        m = re.fullmatch(r"full_(\d+)_holes_since", key)
        if m and value:
            bits.append(f"{m.group(1)}홀 운영 {value}년부터")
    official_name = ident.get("official_name") or club.get("official_name") or ""
    source = ov.get("source_url") or hist.get("source_url") or ident.get("source_url") or ""
    if not (bits or official_name):
        return None
    return {"official_name": official_name if official_name != club.get("name") else "",
            "facts": bits, "source_url": source}


def _operations_block(club):
    ops = club.get("operations") or {}
    sessions = []
    for name, item in (ops.get("sessions") or {}).items():
        if isinstance(item, dict) and item.get("time_range"):
            sessions.append({"name": name, "time": item["time_range"]})

    caddie = ops.get("caddie") if isinstance(ops.get("caddie"), dict) else {}
    caddie_bits = []
    if team_fee(club, "caddie"):
        caddie_bits.append(f"캐디피 {won(team_fee(club, 'caddie'))}/팀")
    if caddie.get("third_session_fee_team"):
        caddie_bits.append(f"3부 {won(caddie['third_session_fee_team'])}/팀")
    if caddie.get("foreign_language_fee_team"):
        caddie_bits.append(f"외국어 캐디 {won(caddie['foreign_language_fee_team'])}/팀")

    cart = ops.get("cart") if isinstance(ops.get("cart"), dict) else {}
    cart_bits = []
    if team_fee(club, "cart"):
        cart_bits.append(f"카트비 {won(team_fee(club, 'cart'))}/팀")
    if cart.get("type") in _CART_TYPES:
        cart_bits.append(_CART_TYPES[cart["type"]])
    for key in ("limousine_fee_team", "limousine_cart_fee_team", "fee_team_limousine"):
        if cart.get(key):
            cart_bits.append(f"리무진 {won(cart[key])}/팀")
            break

    players = []
    raw_players = ops.get("players") if isinstance(ops.get("players"), dict) else {}
    for key, label in (("two_person", "2인"), ("three_person", "3인"), ("five_person", "5인")):
        item = raw_players.get(key)
        if not isinstance(item, dict):
            continue
        allowed = item.get("allowed")
        status = "가능" if allowed is True else ("불가" if allowed is False else None)
        if not status:
            continue
        notes = [str(item[k]) for k in ("condition", "policy_text") if item.get(k)]
        if item.get("surcharge_team"):
            notes.append(f"팀 추가 {won(item['surcharge_team'])}")
        players.append({"label": label, "status": status, "note": " · ".join(notes)})

    return {
        "sessions": sessions,
        "caddie": {"mode": _caddie_summary(club), "bits": caddie_bits,
                   "source_url": caddie.get("source_url") or "", "checked_at": caddie.get("checked_at") or ""},
        "cart": {"bits": cart_bits, "source_url": cart.get("source_url") or "", "checked_at": cart.get("checked_at") or ""},
        "players": players,
        "players_source_url": raw_players.get("source_url") or next(
            (v.get("source_url") for v in raw_players.values() if isinstance(v, dict) and v.get("source_url")), ""),
    }


def _sources_block(club):
    rows, seen = [], set()
    for s in club.get("sources") or []:
        if not isinstance(s, dict) or not s.get("source_url") or s["source_url"] in seen:
            continue
        seen.add(s["source_url"])
        rows.append({"label": _SOURCE_LABELS.get(s.get("source_type"), s.get("source_type") or "출처"),
                     "url": s["source_url"], "checked_at": s.get("checked_at") or "",
                     "fields": [str(f) for f in (s.get("fields") or [])][:6]})
    public = (club.get("verification") or {}).get("public_data") or {}
    status = " · ".join(x for x in (public.get("status"), public.get("detail_status")) if x)
    return {"items": rows, "public_status": status,
            "public_checked_at": public.get("data_updated_at") or public.get("checked_at") or ""}


def _completeness_block(club):
    cats = ((club.get("precision_assessment") or {}).get("categories")) or {}
    items = [{"label": _CATEGORY_LABELS.get(k, k), "status": v} for k, v in cats.items() if k in _CATEGORY_LABELS]
    if not items:
        return None
    done = sum(1 for i in items if i["status"] == "complete")
    return {"items": items, "complete": done, "total": len(items),
            "assessed_at": (club.get("precision_assessment") or {}).get("assessed_at") or ""}


def get_club(club_id):
    _, clubs, _ = load_pools()
    return next((x for x in clubs if x["id"] == club_id), None)


def club_detail(club_id, search=None):
    club = get_club(club_id)
    if not club:
        return None
    cond = condition_from_request(search)

    holes, holes_level = _holes_display(club)
    loc_text = " ".join(str(x).strip() for x in (club.get("region"), club.get("city")) if x and str(x).strip())
    overview_bits = ([f"📍 {loc_text}"] if loc_text else []) + [f"🏷 {_operation_type_text(club)}", f"⛳ {holes}"]

    verified_info = club.get("verified_basic_info") or {}
    evidence_info = club.get("evidence") or {}

    useful = _useful_detail(club)
    selected_session = cond.get("session") or "선택 시간대"
    selected_fee = _cond_session_fee(club, cond, selected_session)
    if cond and "weekend" in cond:
        selected_session = ("주말 " if cond["weekend"] else "주중 ") + selected_session

    fee_bits = []
    for label, value in (("캐디피", useful["caddie_fee"]), ("카트", useful["cart_fee"])):
        if value not in (None, ""):
            try:
                fee_bits.append(f"{label} {int(value):,}원/팀")
            except Exception:
                fee_bits.append(f"{label} {value}")

    eval_bits = [f"{label} {value}" for label, value in [
        ("난이도", useful["difficulty"]), ("페어웨이", useful["fairway"]), ("그린", useful["green"]),
        ("관리", useful["condition"]), ("경관", useful["scenery"])] if value]

    objective_summary = []
    objective_details = []
    for feature in FEATURES:
        label = _objective_display(club, feature)
        if label and "확인 필요" not in str(label):
            objective_summary.append(f"{feature} {label}")
        detail = get_objective_detail(club, feature)
        objective_details.append({
            "feature": feature,
            "label": label,
            "verification": f"{detail['verification_class']} · {detail.get('checked_at') or '미확인'}",
            "notes": [str(n) for n in detail.get("condition_notes", [])[:2]],
        })

    phone_value, phone_level = _phone_display(club)
    phone = str(phone_value or "").strip()
    nav_query = (club.get("address") or club["name"]).strip()

    est = estimate_per_person(club, bool(cond.get("weekend", False)), int(cond.get("players", 4)))
    three_text = str(get_objective_detail(club, "three_person")["label"])
    snapshot_bits = []
    if est is not None:
        snapshot_bits.append(f"예상 1인 {won(est)}")
    if three_text and "확인 필요" not in three_text:
        snapshot_bits.append(f"3인 {three_text}")
    if holes_level != "missing":
        snapshot_bits.append(holes)

    route = None
    detail_route = _route_for_course(club, cond) if cond else None
    if cond.get("departure") and detail_route:
        bits = []
        if detail_route.get("distance_km") is not None:
            bits.append(f"차량거리 {detail_route['distance_km']:.1f}km")
        if detail_route.get("duration_min") is not None:
            bits.append(f"예상 {detail_route['duration_min']}분")
        if detail_route.get("toll_fare") not in (None, 0):
            bits.append(f"통행료 약 {detail_route['toll_fare']:,}원")
        if bits:
            route = f"{cond['departure']} 출발 · " + " · ".join(bits)

    course_details = club.get("course_details") or []
    if isinstance(course_details, dict):
        course_details = course_details.get("courses") or course_details.get("course_list") or course_details.get("items") or []
    if not isinstance(course_details, list):
        course_details = []

    return {
        "id": club["id"],
        "name": club["name"],
        "region": str(club.get("region") or ""),
        "city": str(club.get("city") or ""),
        "candidate": club.get("service_status") == "candidate",
        "holes": holes if holes_level != "missing" else "세부정보 확인 중",
        "overview_bits": overview_bits,
        "holes_is_evidence": holes_level == "evidence",
        "trait_badges": _overview_trait_badges(club)[:4],
        "intro": _fact_based_intro(club),
        "course_labels": _course_labels(club),
        "verified_fields": [k for k, v in verified_info.items() if isinstance(v, dict) and v.get("verified") is True],
        "evidence_fields": [
            k for k, v in evidence_info.items()
            if not str(k).startswith("_") and isinstance(v, dict) and v.get("status") == "SUPPORTED"
        ],
        "round": {
            "session": selected_session,
            "fee": selected_fee,
            "three_person": useful["three_person"],
            "caddie_mode": useful["caddie_mode"],
            "fee_bits": fee_bits,
            "summary": useful["summary"],
            "eval_bits": eval_bits,
        },
        "objective_summary": objective_summary[:6],
        "objective_details": objective_details,
        "kga": _kga_block(club),
        "contact": {
            "phone": phone,
            "phone_is_evidence": bool(phone) and phone_level == "evidence",
            "official_url": (club.get("official_url") or "").strip(),
            "kakao_map": "https://map.kakao.com/link/search/" + quote(nav_query),
            "naver_map": "https://map.naver.com/p/search/" + quote(nav_query),
        },
        "snapshot": snapshot_bits,
        "route": route,
        "has_coord": club_lat_lon(club) is not None,
        "fee_block": _fee_block(club),
        "course_cards": _course_cards(club, course_details),
        "hole_rows": _hole_rows(course_details),
        "course_overview": club.get("course_overview") or "상세 코스정보는 공식 홈페이지에서 확인할 수 있습니다.",
        "data_checked": club.get("data_checked") or (club.get("pricing") or {}).get("last_checked") or "",
        "profile": _profile_block(club),
        "operations": _operations_block(club),
        "ratings": _kga_ratings_table(club),
        "sources": _sources_block(club),
        "completeness": _completeness_block(club),
        "reviews": _reviews_block(club),
    }


def refresh_reviews(club_id):
    """Tavily 수집 + GPT 분석을 실행하고, 유효 분석이면 저장한다. (사용자가 버튼을 눌렀을 때만)"""
    from services.golf_gpt_analysis import aggregate, analyze_reviews_with_gpt
    from services.golf_tavily import search_golf_review_bundle

    club = get_club(club_id)
    if not club:
        return None
    tavily_key, openai_key = get_secret("TAVILY_API_KEY"), get_secret("OPENAI_API_KEY")
    if not (tavily_key and openai_key):
        raise RuntimeError("TAVILY_API_KEY와 OPENAI_API_KEY를 확인해주세요.")

    records, _stats = search_golf_review_bundle(tavily_key, club["name"])
    reviews = analyze_reviews_with_gpt(openai_key, records, club["name"])
    agg = aggregate(reviews)

    # 새 분석의 언급 수가 현재 표시 중인 저장본보다 많을 때만 덮어쓴다.
    total_mentions = sum(sum((agg.get(d, {}).get("counts") or {}).values()) for d in DIMS)
    saved_mentions = _saved_mentions(club["id"])
    if total_mentions <= saved_mentions:
        block = _reviews_block(club)
        block["notice"] = (
            f"새 분석의 후기 언급({total_mentions}건)이 저장된 분석({saved_mentions}건)보다 많지 않아 기존 분석을 유지했어요."
        )
        return block
    save_runtime_summary(club["id"], agg, reviews=reviews)

    cards, evidence = [], []
    for dim, name in DIMS.items():
        item = agg.get(dim, {})
        counts = item.get("counts", {})
        cards.append({"name": name, "verdict": str(item.get("verdict", "후기 정보 부족")), "sub": f"언급 {sum(counts.values())}건"})
        if not counts:
            continue
        quotes = []
        for label in counts:
            for review in (item.get("evidence", {}).get(label, []) or [])[:2]:
                text = (review.get("dimensions", {}).get(dim, {}) or {}).get("evidence", "")
                if text:
                    quotes.append({
                        "text": str(text),
                        "date": str(review.get("date") or review.get("published_date") or "날짜 미확인"),
                        "url": review.get("url") or "",
                    })
        evidence.append({"name": name, "verdict": str(item.get("verdict", "")), "quotes": quotes})

    dated = sum(bool(r.get("date") or r.get("published_date")) for r in reviews)
    links, cutoff_year, current_year = _recent_links(reviews)
    block = _reviews_block(club)
    block.update({
        "analysis": {"cards": cards, "meta": f"최근 5년 분석 · 유효 후기 {len(reviews)}건 · 작성일 확인 {dated}건"},
        "evidence": evidence,
        "links": links,
    })
    return block
