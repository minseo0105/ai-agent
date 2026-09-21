from html import escape
from urllib.parse import quote
import datetime
import re

import streamlit as st
import streamlit.components.v1 as components
from urllib.parse import quote_plus
from datetime import date, timedelta

from auth import require_page_auth
from services.navigation import render_sidebar
from services.golf_catalog import (
    load_service_catalog,
    find_clubs,
    estimate_per_person,
    parse_ai_conditions,
    recommendation_pool,
    load_review_seed,
    _subregion_match,
    is_recommendable,
    pool_counts,
)
from services.golf_pool_updater import (
    load_pool_meta,
    quarterly_refresh_due,
    next_refresh_text,
    refresh_pool,
    refresh_pool_dual,
    test_vworld_connection,
)
from services.golf_master import (FEATURES, get_objective_detail, get_objective_status,
    objective_filter_value, matches_objective_conditions, is_round_eligible, normalize_operation_type)
from services.golf_public_data import dual_verification_summary
from services.golf_kga_ui import render_kga_course_intelligence

from services.golf_review_store import (
    load_runtime_summary,
    save_runtime_summary,
)
from services.golf_tavily import search_golf_review_bundle
from services.golf_gpt_analysis import (
    analyze_reviews_with_gpt,
    aggregate,
    DIMS,
)



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



def compact_date_multi_choice(key="golf_round_dates"):
    """
    모바일 압축형 선택 날짜 UI.
    날짜는 필수가 아니며, 달력에서 하루씩 추가하여 복수 날짜를 저장한다.
    선택된 날짜만 작은 버튼으로 노출한다.
    """
    if key not in st.session_state:
        st.session_state[key] = []

    selected = []
    for x in st.session_state[key]:
        try:
            selected.append(date.fromisoformat(x) if isinstance(x, str) else x)
        except Exception:
            pass
    selected = sorted(set(selected))

    c1, c2 = st.columns([3, 1])
    with c1:
        candidate = st.date_input(
            "라운드 날짜",
            value=None,
            min_value=date.today(),
            key=f"{key}_picker",
            help="선택하지 않아도 됩니다. 여러 날짜를 보려면 날짜를 하나씩 추가하세요.",
        )
    with c2:
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        add_clicked = st.button("＋ 추가", key=f"{key}_add", width="stretch")

    if add_clicked and candidate:
        if candidate not in selected:
            selected.append(candidate)
            selected = sorted(set(selected))
        st.session_state[key] = [d.isoformat() for d in selected]
        # date_input 생성 이후에는 동일 widget key의 session_state를 직접 수정할 수 없다.
        # picker 초기화 없이 rerun하고, 선택 목록만 별도 state로 관리한다.
        st.rerun()

    if selected:
        st.caption("선택 날짜 · 다시 누르면 삭제")
        # 최대 3열로 압축
        cols = st.columns(min(3, len(selected)))
        for i, d in enumerate(selected):
            with cols[i % len(cols)]:
                if st.button(
                    "✓ " + _round_date_label(d),
                    key=f"{key}_remove_{d.isoformat()}",
                    width="stretch",
                ):
                    selected = [x for x in selected if x != d]
                    st.session_state[key] = [x.isoformat() for x in selected]
                    st.rerun()
    else:
        st.caption("날짜 미선택 · 날짜 조건 없이 검색")

    return selected


def mobile_multi_choice(label, options, key, disabled=False, help_text=None):
    """드롭다운 없이 버튼을 눌러 바로 복수 선택/해제하는 모바일용 UI."""
    state_key = f"{key}_values"
    if state_key not in st.session_state:
        st.session_state[state_key] = []

    st.session_state[state_key] = [
        x for x in st.session_state[state_key] if x in options
    ]

    st.markdown(f"**{label}**")
    if help_text:
        st.caption(help_text)

    if disabled:
        st.caption("권역을 1개만 선택하면 세부권역을 선택할 수 있습니다.")
        return []

    if not options:
        return []

    selected = list(st.session_state[state_key])
    cols = st.columns(3)

    for i, option in enumerate(options):
        active = option in selected
        with cols[i % 3]:
            if st.button(
                ("✓ " if active else "") + option,
                key=f"{key}_{i}_{option}",
                type="primary" if active else "secondary",
                width="stretch",
            ):
                if active:
                    selected.remove(option)
                else:
                    selected.append(option)
                st.session_state[state_key] = selected
                st.rerun()

    return list(st.session_state[state_key])



# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="골프장 찾기 · AI 실험실",
    page_icon="⛳",
    layout="wide",
)

require_page_auth()
render_sidebar(current_page="6_골프장_추천.py")


# =========================================================
# STYLE
# =========================================================

st.html(
    """
<style>
.st-key-golf {
    max-width: 980px;
    margin: auto;
}

.hero {
    padding: 13px 15px;
    border-radius: 15px;
    background: linear-gradient(120deg,#0f172a,#0f766e);
    color: white;
    margin: 4px 0 8px;
}

.hero h1 {
    color: white;
    font-size: 1.35rem;
    margin: 1px 0;
}

.rec,
.costs,
.courses,
.traits {
    display: grid;
    gap: 6px;
}

.rec {
    grid-template-columns: repeat(3,1fr);
}

.decision-card {
    border: 1px solid rgba(128,128,128,.20);
    border-radius: 14px;
    padding: 12px;
    margin-bottom: 8px;
    min-height: 132px;
    background: rgba(255,255,255,.015);
}
.decision-card .name {
    font-size: 1.02rem;
    font-weight: 900;
    margin-bottom: 4px;
}
.decision-card .price {
    font-size: .94rem;
    font-weight: 850;
    margin: 5px 0;
}
.decision-card .why {
    font-size: .72rem;
    line-height: 1.45;
    opacity: .78;
}
.map-note {
    padding: 9px 11px;
    border-radius: 11px;
    background: rgba(15,118,110,.06);
    font-size: .76rem;
    margin: 5px 0 8px;
}

.costs {
    grid-template-columns: repeat(2,1fr);
}

.courses {
    grid-template-columns: repeat(3,1fr);
}

.traits {
    grid-template-columns: repeat(5,1fr);
}

.box,
.cost,
.course,
.trait {
    border: 1px solid rgba(128,128,128,.20);
    border-radius: 12px;
    padding: 9px;
}

.quick-actions {
    display: grid;
    grid-template-columns: repeat(4,1fr);
    gap: 5px;
    margin: 6px 0 8px;
}

.quick-actions a {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 34px;
    border: 1px solid rgba(128,128,128,.22);
    border-radius: 10px;
    text-decoration: none !important;
    font-size: .72rem;
    font-weight: 750;
    padding: 4px 5px;
}

.quick-actions a:hover {
    background: rgba(128,128,128,.06);
}

.quick-actions .disabled {
    opacity: .38;
    pointer-events: none;
}

.cost {
    background: rgba(15,118,110,.06);
}

.big {
    font-size: 1.02rem;
    font-weight: 900;
}

.sm {
    font-size: .67rem;
    opacity: .68;
    line-height: 1.4;
}

.trait b {
    font-size: .77rem;
}

.ev {
    border-left: 3px solid #789;
    padding: 6px 8px;
    margin: 5px 0;
}

.ev a {
    font-size: .65rem;
}

.quote {
    font-size: .76rem;
}

.review-empty {
    padding: 13px 14px;
    border: 1px solid rgba(128,128,128,.18);
    border-radius: 12px;
    background: rgba(128,128,128,.035);
    margin: 5px 0;
}

.review-meta {
    font-size: .72rem;
    opacity: .72;
    margin-top: 5px;
}

@media(max-width:700px) {

    .quick-actions {
        grid-template-columns: repeat(4,1fr);
    }

    .quick-actions a {
        font-size: .65rem;
        min-height: 31px;
    }

    .rec {
        grid-template-columns: 1fr;
    }

    .traits {
        grid-template-columns: repeat(2,1fr);
    }

    .block-container {
        padding: .65rem;
    }

    .cost {
        padding: 7px;
    }

    .big {
        font-size: .9rem;
    }

    .course {
        padding: 6px;
    }

    .course b {
        font-size: .7rem;
    }

    .hero {
        padding: 11px 12px;
        border-radius: 13px;
    }

    .hero h1 {
        font-size: 1.16rem;
    }

    .quick-actions {
        grid-template-columns: repeat(2,1fr);
    }

    .decision-card {
        min-height: auto;
        padding: 10px;
    }

    div[data-testid="stHorizontalBlock"] {
        gap: .45rem;
    }

    div[data-testid="stButton"] button {
        min-height: 40px;
    }
}

/* v12 mobile compact */
@media (max-width: 640px) {
    .hero { padding: 10px 12px !important; margin-bottom: 6px !important; border-radius: 14px !important; }
    .hero h1 { font-size: 1.28rem !important; margin: 1px 0 2px !important; line-height: 1.18 !important; }
    .hero .sm { font-size: .58rem !important; }
    .hero div:last-child { font-size: .68rem !important; }

    div[data-testid="stVerticalBlock"] { gap: .42rem; }
    div[data-testid="stHorizontalBlock"] { gap: .42rem; }
    div[data-testid="stCaptionContainer"] { margin-top: -8px !important; margin-bottom: -3px !important; }
    div[data-testid="stMarkdownContainer"] h5 { margin: 3px 0 !important; font-size: .88rem !important; }

    div[data-testid="stSegmentedControl"] { margin-bottom: 0 !important; }
    div[data-testid="stSegmentedControl"] button { min-height: 34px !important; padding: 4px 7px !important; font-size: .72rem !important; }

    div[data-testid="stSelectbox"] { margin-bottom: 0 !important; }
    div[data-baseweb="select"] > div { min-height: 36px !important; font-size: .78rem !important; }

    div[data-testid="stButton"] button { min-height: 38px !important; padding: 5px 8px !important; }
    .decision-card { padding: 10px !important; margin: 6px 0 !important; }
    .quick-actions { grid-template-columns: repeat(2,1fr) !important; }
}
</style>

<style>
@media (max-width: 768px) {
  div[data-testid="stDeckGlJsonChart"] { margin-top: .1rem !important; margin-bottom: .1rem !important; }
  div[data-testid="stExpander"] details summary { min-height: 2.35rem !important; padding: .3rem .5rem !important; }
}
</style>


<style>
@media (max-width: 768px) {
  div[data-testid="stButton"] button {
    min-height: 2.65rem !important;
    padding: .35rem .45rem !important;
    font-size: .90rem !important;
    border-radius: .7rem !important;
  }
  div[data-testid="stHorizontalBlock"] {
    gap: .35rem !important;
  }
}

</style>

<style>
/* v3 mobile-first compact */
@media (max-width: 640px) {
  .st-key-golf { max-width: 100% !important; }
  .block-container { padding-left: .55rem !important; padding-right: .55rem !important; }
  .hero { padding: 8px 10px !important; margin: 0 0 5px !important; }
  .hero h1 { font-size: 1.12rem !important; }
  .decision-card { padding: 8px 9px !important; margin-bottom: 3px !important; }
  .decision-card .name { font-size: .98rem !important; margin-bottom: 2px !important; }
  .decision-card .sm, .decision-card .why { font-size: .76rem !important; line-height: 1.22 !important; }
  div[data-testid="stAlert"] { padding: .5rem .65rem !important; }
  div[data-testid="stExpander"] { margin-top: .05rem !important; margin-bottom: .18rem !important; }
}
</style>

<!-- 모바일 압축 레이아웃 -->

<style>
@media (max-width: 768px) {
  .block-container {padding-top: .7rem !important; padding-bottom: 1.5rem !important;}
  div[data-testid="stVerticalBlock"] {gap: .45rem !important;}
  div[data-testid="stHorizontalBlock"] {gap: .35rem !important;}
  .decision-card {padding: .72rem !important; min-height: 0 !important; margin-bottom: .35rem !important;}
  .decision-card .name {font-size: 1.02rem !important;}
  .decision-card .price {font-size: .95rem !important; margin-top: .25rem !important;}
  .decision-card .sm, .decision-card .why {font-size: .82rem !important; line-height: 1.3 !important;}
  div[data-testid="stExpander"] details summary {padding-top:.45rem !important; padding-bottom:.45rem !important;}
  div[data-baseweb="select"] > div {min-height: 2.35rem !important;}
  .stButton button {min-height: 2.45rem !important;}
}
</style>

<style>
@media (max-width: 640px) {
  /* 검색방식 3개를 한 줄에서 명확하게 구분 */
  div[data-testid="stSegmentedControl"] button {
    min-height: 38px !important;
    padding: 4px 5px !important;
    font-size: .70rem !important;
    line-height: 1.08 !important;
  }
  /* 권역/세부권역/추가조건 버튼의 세로 길이 축소 */
  div[data-testid="stButton"] button {
    min-height: 35px !important;
    padding: 4px 6px !important;
  }
  /* 접힌 추가조건은 검색 버튼과 시각적으로 분리 */
  div[data-testid="stExpander"] {
    margin-top: .15rem !important;
    margin-bottom: .35rem !important;
  }
  div[data-testid="stExpander"] details summary {
    min-height: 36px !important;
    font-weight: 700 !important;
  }
}
</style>

"""
)


# =========================================================
# HELPERS
# =========================================================

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
    """catalog에 저장된 위경도 후보를 안전하게 읽는다."""
    candidates = [
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


def render_review_cards(summary, label="저장 요약"):
    cards = []

    dimensions = summary.get("dimensions", {})

    for dim, name in DIMS.items():

        item = dimensions.get(
            dim,
            {
                "verdict": "후기 정보 부족",
                "mentions": 0,
            },
        )

        verdict = item.get("verdict") or "후기 정보 부족"
        mentions = int(item.get("mentions", 0) or 0)

        sub = (
            f"언급 {mentions}건"
            if mentions > 0
            else label
        )

        cards.append(
            f"""
            <div class="trait">
                <b>{escape(name)}<br>{escape(str(verdict))}</b>
                <div class="sm">{escape(sub)}</div>
            </div>
            """
        )

    st.html(
        '<div class="traits">'
        + "".join(cards)
        + "</div>"
    )



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

    players = 4  # 요금 추정 기본값. 2인/3인 플레이는 아래 객관조건에서 별도 판정.

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
# LOAD DATA
# =========================================================

all_clubs = load_service_catalog()
golf_runtime_version = all_clubs[0].get("_golf_runtime", {}).get("version") if all_clubs else None
if st.session_state.get("golf_runtime_version") != golf_runtime_version:
    for key in ("golf_recs", "golf_rec_conditions", "golf_filter_trace", "golf_ai_parsed",
                "golf_region_pool_count", "golf_verified_pool_count"):
        st.session_state.pop(key, None)
    st.session_state.golf_rec_offset = 0
st.session_state["golf_runtime_version"] = golf_runtime_version
if all_clubs and all_clubs[0].get("_golf_runtime", {}).get("diagnostic") not in ("ok", "disabled"):
    st.warning("Master 검증정보 일부를 읽지 못해 catalog 기준으로 표시합니다.")
clubs = [c for c in all_clubs if c["service_status"] != "excluded" and _eligible_round_course(c)]
service_clubs = [c for c in all_clubs if c["service_status"] == "service" and _eligible_round_course(c)]

def _public_operating_candidate(club):
    """공공데이터상 영업이 확인된 candidate를 조건/AI 검색 Pool에 포함."""
    if club.get("service_status") != "candidate":
        return False
    public = ((club.get("verification") or {}).get("public_data") or {})
    return public.get("matched") is True and public.get("operating_in_public_data") is True

SUPPORTED_GOLF_AREAS = {"수도권", "충청권", "강원권"}

# 기존 catalog를 그대로 사용하고, 추천/조건검색 Pool만 서비스 대상 3개 권역으로 제한.
# service + 공공데이터상 영업 확인 candidate를 함께 사용한다.
condition_search_clubs = [
    c for c in all_clubs
    if c.get("area") in SUPPORTED_GOLF_AREAS
    and (c.get("service_status") == "service" or _public_operating_candidate(c))
    and _eligible_round_course(c)
]

# 실제 연결 상태: catalog 원장 / 3권역 / 현재 추천가능 Pool
_target_area_count = sum(1 for c in all_clubs if c.get("area") in SUPPORTED_GOLF_AREAS)
_service_count = sum(
    1 for c in all_clubs
    if c.get("area") in SUPPORTED_GOLF_AREAS and c.get("service_status") == "service"
)
_public_candidate_count = sum(
    1 for c in all_clubs
    if c.get("area") in SUPPORTED_GOLF_AREAS
    and c.get("service_status") == "candidate"
    and _public_operating_candidate(c)
)


# 직접검색은 excluded만 제외한 전체 검색 가능 Pool을 사용.
# 기존 검색결과 state도 service 13개로 강제 축소하지 않는다.
if st.session_state.get("golf_recs"):
    searchable_ids = {c["id"] for c in clubs}
    st.session_state.golf_recs = [
        item for item in st.session_state.golf_recs
        if _normalize_result_item(item)[0].get("id") in searchable_ids
    ]

if "golf_filters_open" not in st.session_state:
    st.session_state.golf_filters_open = True

if "golf_rec_offset" not in st.session_state:
    st.session_state.golf_rec_offset = 0


# =========================================================
# MAIN
# =========================================================

with st.container(key="golf"):

    st.html(
        """
        <div class="hero">
            <div class="sm">AI GOLF FINDER</div>
            <h1>골프장 찾기</h1>
            <div>수도권 · 충청권 · 강원권 · AI 맞춤추천</div>
        </div>
        """
    )

    # -----------------------------------------------------
    # SEARCH OPEN BUTTON
    # 기존 상세정보는 지우지 않음
    # -----------------------------------------------------

    if not st.session_state.golf_filters_open:

        if st.button(
            "⌄ 검색 조건 다시 열기",
            width="stretch",
        ):
            st.session_state.golf_filters_open = True
            st.rerun()

    # -----------------------------------------------------
    # SEARCH / RECOMMENDATION
    # 골프장명 검색 / 조건 검색 / AI 문장 검색을 명확히 분리
    # -----------------------------------------------------

    if st.session_state.golf_filters_open:

        search_mode = st.segmented_control(
            "찾는 방법",
            ["조건 검색", "✨ AI 문장검색", "골프장 직접 찾기"],
            default="조건 검색",
            label_visibility="collapsed",
        )

        previous_mode = st.session_state.get("golf_last_search_mode")
        if previous_mode is not None and previous_mode != search_mode:
            for key in (
                "golf_recs",
                "golf_rec_conditions",
                "golf_filter_trace",
                "golf_region_pool_count",
                "golf_verified_pool_count",
                "golf_ai_parsed",
            ):
                st.session_state.pop(key, None)
            st.session_state.golf_rec_offset = 0
        st.session_state["golf_last_search_mode"] = search_mode

        # 1) 골프장명/지역 직접 검색
        if search_mode == "골프장 직접 찾기":
            q = st.text_input(
                "전국 골프장 빠른검색",
                placeholder="예: 레이크사이드, 용인, 제주",
            )
            if q:
                matches = find_clubs(q, clubs)
                if matches:
                    options = {
                        f'{x["name"]} · {x.get("region","")} {x.get("city","")}': x["id"]
                        for x in matches[:20]
                    }
                    option_labels = ["골프장을 선택하세요"] + list(options)
                    pick = st.selectbox("검색결과", option_labels)
                    if pick != "골프장을 선택하세요":
                        picked_id = options[pick]
                        if st.session_state.get("golf_selected_id") != picked_id:
                            st.session_state.golf_selected_id = picked_id
                            st.session_state.golf_v14 = {}
                            st.session_state.golf_filters_open = False
                            st.rerun()
                else:
                    st.info("현재 Pool에서 일치하는 골프장을 찾지 못했습니다.")

        # 2) 카테고리/상세조건 검색
        elif search_mode == "조건 검색":
            area_options = ["수도권", "충청권", "강원권"]
            selected_areas = mobile_multi_choice(
                "권역",
                area_options,
                key="golf_area_multi",
                help_text="복수 선택 가능 · 미선택 시 전국",
            )
            # 기존 추천함수 호환용. 복수 권역은 후단에서 필터링한다.
            area = selected_areas[0] if len(selected_areas) == 1 else "전체"

            # 세부권역은 단일 권역을 선택했을 때만 다중선택 가능
            subregion_map = {
                "수도권": ["서울", "인천", "경기남부", "경기북부"],
                "충청권": ["충북", "충남"],
                "강원권": ["강원영서", "강원영동"],
            }

            single_area = selected_areas[0] if len(selected_areas) == 1 else None
            # 권역이 바뀌면 이전 세부권역 선택이 남지 않도록 정리
            previous_single_area = st.session_state.get("golf_previous_single_area")
            if previous_single_area != single_area:
                st.session_state["golf_subregion_multi_values"] = []
                st.session_state["golf_previous_single_area"] = single_area

            detail_places = mobile_multi_choice(
                "세부권역",
                subregion_map.get(single_area, []),
                key="golf_subregion_multi",
                disabled=not bool(single_area),
                help_text=(
                    "여러 세부권역 선택 가능"
                    if single_area
                    else "권역을 여러 개 선택하면 세부권역은 전체로 적용됩니다."
                ),
            )

            budgets = {
                "제한 없음": None,
                "15만원 이하": 150000,
                "20만원 이하": 200000,
                "25만원 이하": 250000,
                "30만원 이하": 300000,
                "40만원 이하": 400000,
            }
            # 모바일에서는 예산과 요일을 한 줄에 배치해 세로 스크롤을 줄인다.
            c_budget, c_day = st.columns([1.05, 1])
            with c_budget:
                budget_label = st.selectbox(
                    "1인 예상예산",
                    list(budgets.keys()),
                    label_visibility="collapsed",
                )
                st.caption("예산")
            with c_day:
                day_type = st.selectbox(
                    "요일",
                    ["주중", "주말/공휴일"],
                    label_visibility="collapsed",
                )
                st.caption("요일")
            is_weekend = day_type == "주말/공휴일"

            st.markdown("##### 내 실력 · 원하는 난이도 <span style='font-size:.72rem;font-weight:500;opacity:.55'>선택사항</span>", unsafe_allow_html=True)
            c_skill, c_challenge = st.columns(2)
            with c_skill:
                avg_score_label = st.selectbox(
                    "내 평균타수",
                    ["미선택", "80타대", "90타대", "100타대", "110타 이상"],
                    index=0,
                    key="golf_avg_score",
                )
            with c_challenge:
                challenge = st.segmented_control(
                    "원하는 난이도",
                    ["편하게", "적당히", "도전"],
                    default="적당히",
                    key="golf_challenge",
                )
            avg_score = {
                "80타대": 85,
                "90타대": 95,
                "100타대": 105,
                "110타 이상": 115,
            }.get(avg_score_label)

            with st.expander("＋ 추가 조건 · 인원 / 연습장 / 야간", expanded=False):
                objective_choice = mobile_multi_choice(
                    "시설 · 운영 조건",
                    ["2인 플레이", "3인 플레이", "9홀×2 라운드", "PAR3 연습장", "야외 연습장", "야간 라운드"],
                    key="golf_objective_multi",
                    help_text="필요한 조건만 선택하세요.",
                )

            cfind, cmore = st.columns([3.2, 1])
            with cfind:
                find_clicked = st.button("🔎 이 조건으로 찾기", type="primary", width="stretch")
            with cmore:
                more_clicked = st.button("다음 4개 →", width="stretch")

            if find_clicked or more_clicked:
                st.session_state.pop("golf_selected_id", None)
                st.session_state.golf_v14 = {}

                if find_clicked:
                    st.session_state.golf_rec_offset = 0
                else:
                    st.session_state.golf_rec_offset = st.session_state.get("golf_rec_offset", 0) + 4

                cond = {
                    "area": area,
                    "areas": selected_areas,
                    "city": None,
                    "subregions": detail_places,
                    "weekend": is_weekend,
                    "budget": budgets[budget_label],
                    "objective_features": list(objective_choice),
                    # 인원은 별도 상단 조건이 없다. 2인/3인은 objective_features에서 독립 판정한다.
                    "players": 4,
                    "avg_score": avg_score,
                    "avg_score_label": avg_score_label,
                    "challenge": challenge or "적당히",
                }
                st.session_state.golf_rec_conditions = cond

                # 검증 가능한 필터 검색:
                # 1) 전체 Pool -> 2) 권역 -> 3) 세부권역 -> 4) 확인 가능한 추가조건
                total_count = len(condition_search_clubs)
                search_clubs = list(condition_search_clubs)

                if selected_areas:
                    search_clubs = [
                        club for club in search_clubs
                        if club.get("area") in selected_areas
                    ]
                area_count = len(search_clubs)

                if detail_places:
                    search_clubs = [
                        club for club in search_clubs
                        if any(_subregion_match(club, sub) for sub in detail_places)
                    ]
                subregion_count = len(search_clubs)

                # 추가조건은 정보가 확인된 레코드에 대해서만 판정한다.
                # 정보가 없으면 '충족'으로 추정하지 않는다.
                filtered = []
                for club in search_clubs:
                    ok = True

                    # 예산:
                    # 금액이 확인된 곳만 상한을 적용하고, 금액 미확인 골프장은 남겨둔다.
                    if ok and cond.get("budget"):
                        try:
                            est = estimate_per_person(club, bool(cond.get("weekend")), int(cond.get("players") or 4))
                        except Exception:
                            est = None
                        if est is not None and est > cond["budget"]:
                            ok = False

                    # 객관 필터: 명확한 불가/없음만 제외. 미확인은 결과에 남겨 별도 표시.
                    if not matches_objective_conditions(club, cond.get("objective_features", [])):
                        ok = False

                    if ok:
                        filtered.append(club)

                final_count = len(filtered)

                # 확인된 선택조건 수 → 미확인 수 → 요금 확인 → 정보 충실도 → 이름순.
                # 내부 정렬에만 사용하며 기존 조건 확인 구분과 필터는 변경하지 않는다.
                def _condition_sort_key(club):
                    import math

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

                    confirmed_features = sum(
                        _objective_feature_status(club, feature) is True
                        for feature in set(cond.get("objective_features") or [])
                    )
                    _status, _confirmed, pending = _result_confidence(club, cond)
                    price_missing = 0
                    if cond.get("budget"):
                        try:
                            estimated = estimate_per_person(
                                club, bool(cond.get("weekend")), int(cond.get("players") or 4)
                            )
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
                    return (
                        -confirmed_features,
                        len(pending),
                        price_missing,
                        -information_count,
                        str(club.get("name") or ""),
                    )

                # 추천 정밀도 점수: 조건 확인도 + 가격 근거 + 데이터 완성도 + KGA 난이도 적합도를
                # 하나의 점수로 결합한다. 미확인 정보는 감점하되 검색 결과에서 임의로 제외하지 않는다.
                def _recommendation_score(club):
                    score = 0.0
                    reasons = []

                    selected_features = set(cond.get("objective_features") or [])
                    confirmed_features = sum(
                        _objective_feature_status(club, feature) is True
                        for feature in selected_features
                    )
                    conditional_features = sum(
                        get_objective_status(club, feature) == "conditional"
                        for feature in selected_features
                    )
                    score += confirmed_features * 14
                    score += conditional_features * 4
                    if confirmed_features:
                        reasons.append(f"선택조건 {confirmed_features}개 확인")

                    _status, confirmed_fields, pending_fields = _result_confidence(club, cond)
                    score += min(len(confirmed_fields), 5) * 5
                    score -= min(len(pending_fields), 5) * 3

                    if cond.get("budget"):
                        try:
                            estimated = estimate_per_person(
                                club, bool(cond.get("weekend")), int(cond.get("players") or 4)
                            )
                        except Exception:
                            estimated = None
                        if estimated is not None:
                            score += 12
                            if estimated <= cond["budget"]:
                                # 예산 여유가 클수록 소폭 가점. 가격만으로 순위를 지배하지 않도록 상한을 둔다.
                                margin = max(cond["budget"] - estimated, 0)
                                score += min(margin / max(cond["budget"], 1) * 8, 8)
                                reasons.append("예산 범위 확인")
                        else:
                            score -= 4

                    # 실제 서비스에서 유용한 핵심 데이터의 완성도를 가점한다.
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

                    # KGA Slope가 확인된 경우 사용자의 평균타수/선호 난이도와 가까울수록 가점.
                    if cond.get("avg_score"):
                        skill = _skill_fit(
                            club, cond["avg_score"], cond.get("challenge") or "적당히", cond.get("avg_score_label")
                        )
                        if skill.get("known"):
                            distance = float(skill.get("distance") or 0)
                            score += max(18 - min(distance, 18), 0)
                            reasons.append("난이도 적합도 확인")
                        else:
                            score -= 2

                    # 공공데이터 영업 확인 레코드는 identity/운영 근거에 소폭 가점.
                    public = club.get("public_data") or {}
                    if public.get("matched") is True and public.get("operating_in_public_data") is True:
                        score += 5
                        reasons.append("공공데이터 영업 확인")

                    return round(score, 1), reasons

                filtered = sorted(
                    filtered,
                    key=lambda c: (
                        -_recommendation_score(c)[0],
                        _condition_sort_key(c),
                        str(c.get("name") or ""),
                    ),
                )

                confirmed_count = 0
                pending_count = 0
                conditional_count = 0
                for result_club in filtered:
                    if any(get_objective_status(result_club, f) == "conditional" for f in cond.get("objective_features", [])):
                        conditional_count += 1
                    status, confirmed_fields, pending_fields = _result_confidence(
                        result_club,
                        cond,
                    )
                    if status == "confirmed":
                        confirmed_count += 1
                    else:
                        pending_count += 1
                excluded_count = max(subregion_count - final_count, 0)

                start_idx = st.session_state.golf_rec_offset
                if final_count and start_idx >= final_count:
                    start_idx = 0
                    st.session_state.golf_rec_offset = 0
                page_clubs = filtered[start_idx:start_idx + 4]

                # 기존 카드 렌더러 호환용 tuple
                st.session_state.golf_recs = [
                    (club, [f"추천점수 {_recommendation_score(club)[0]:.1f}"] + _recommendation_score(club)[1])
                    for club in page_clubs
                ]
                st.session_state.golf_filter_trace = {
                    "total": total_count,
                    "area": area_count,
                    "subregion": subregion_count,
                    "final": final_count,
                    "conditional": conditional_count,
                    "confirmed": confirmed_count,
                    "pending": pending_count,
                    "excluded": excluded_count,
                }
                st.session_state.golf_region_pool_count = subregion_count
                st.session_state.golf_verified_pool_count = final_count

        # 3) AI 문장검색 - 외부 API 없이 문장에서 조건을 읽고 동일 필터엔진 적용
        else:
            natural = st.text_area(
                "원하는 라운드를 문장으로 입력하세요",
                placeholder="예: 여주에서 주말 4인, 1인 30만원 이하 골프장 찾아줘",
                height=82,
            )
            st.caption(
                "문장에서 지역 · 주중/주말 · 인원 · 예산을 읽습니다. "
                "미확인 3인·요금 정보는 검색에서 제외하지 않고 결과에서 확인 필요로 구분합니다."
            )

            ai_find = st.button(
                "문장으로 검색",
                type="primary",
                width="stretch",
                disabled=not bool(natural.strip()),
            )

            if ai_find:
                st.session_state.pop("golf_selected_id", None)
                st.session_state.golf_v14 = {}
                st.session_state.golf_rec_offset = 0

                cond = parse_ai_conditions(natural, "전체", False, 4, None)
                cond["players_specified"] = cond.get("players") is not None
                cond["players"] = int(cond.get("players") or 4)
                cond["areas"] = [] if cond.get("area") == "전체" else [cond.get("area")]
                cond["subregions"] = []
                cond["objective_features"] = ["3인 플레이"] if cond["players"] == 3 else []

                total_count = len(condition_search_clubs)
                search_clubs = list(condition_search_clubs)

                # 권역
                if cond.get("area") and cond["area"] != "전체":
                    search_clubs = [c for c in search_clubs if c.get("area") == cond["area"]]
                area_count = len(search_clubs)

                # 도시명: city/address/name에 실제 문자열이 있는 레코드만
                if cond.get("city"):
                    city = str(cond["city"])
                    search_clubs = [
                        c for c in search_clubs
                        if city in " ".join(str(c.get(k) or "") for k in ("city","address","name","subregion"))
                    ]
                city_count = len(search_clubs)

                filtered = []
                for club in search_clubs:
                    ok = True

                    ok = matches_objective_conditions(club, cond.get("objective_features", []))

                    if ok and cond.get("budget"):
                        est = estimate_per_person(club, bool(cond.get("weekend")), int(cond.get("players") or 4))
                        if est is not None and est > cond["budget"]:
                            ok = False

                    # 코스 특징은 데이터가 충분하지 않아 검색 제외조건으로 사용하지 않는다.

                    if ok:
                        filtered.append(club)

                filtered = sorted(filtered, key=lambda x: str(x.get("name") or ""))
                final_count = len(filtered)
                st.session_state.golf_recs = [
                    (club, ["문장 검색조건 충족"]) for club in filtered[:4]
                ]
                st.session_state.golf_rec_conditions = cond
                st.session_state.golf_filter_trace = {
                    "total": total_count,
                    "area": area_count,
                    "subregion": city_count,
                    "final": final_count,
                }
                st.session_state.golf_region_pool_count = city_count
                st.session_state.golf_verified_pool_count = final_count
                st.session_state.golf_ai_parsed = {
                    "입력": natural,
                    "권역": cond.get("area") or "전체",
                    "지역": cond.get("city") or "전체",
                    "요일": "주말/공휴일" if cond.get("weekend") else "주중",
                    "인원": f"{cond.get('players', 4)}인",
                    "예산": f"{cond['budget']//10000}만원 이하" if cond.get("budget") else "제한 없음",
                    "코스특징": ", ".join(cond.get("traits") or []) or "없음",
                }

            parsed = st.session_state.get("golf_ai_parsed")
            if parsed:
                st.info(
                    "AI 해석 조건  |  "
                    f"{parsed['권역']} · {parsed['지역']} · {parsed['요일']} · "
                    f"{parsed['인원']} · {parsed['예산']}"
                )

        # 공통 추천결과
        recs = st.session_state.get("golf_recs")
        cond = st.session_state.get("golf_rec_conditions")

        if recs:
            if cond:
                daytxt = "주말/공휴일" if cond["weekend"] else "주중"
                chips = [" · ".join(cond.get("areas") or ["전국"])]
                if cond.get("subregions"):
                    chips.append(" / ".join(cond["subregions"]))
                elif cond.get("city"):
                    chips.append(str(cond["city"]))
                chips.append(daytxt)
                if cond.get("budget"):
                    chips.append(f'{cond["budget"] // 10000}만원 이하')
                if cond.get("objective_features"):
                    chips.extend(cond["objective_features"])
                if cond.get("avg_score"):
                    chips.append(f'{_avg_score_display(cond)} 참고')
                    chips.append(cond.get("challenge") or "적당히")
                st.success("검색 적용: " + " · ".join(chips))

            st.markdown("### 검색 결과")
            region_count = st.session_state.get("golf_region_pool_count")
            if region_count is not None:
                trace = st.session_state.get("golf_filter_trace") or {}
                if trace:
                    st.caption(
                        f"검색결과 {trace.get('final', 0)}개 · "
                        f"조건확인 {trace.get('confirmed', 0)}개 · "
                        f"확인필요 {trace.get('pending', 0)}개"
                    )
                    with st.expander("검색 기준 · 데이터 상태", expanded=False):
                        st.write(
                            f"전체 Pool {trace.get('total', 0)}개 → "
                            f"권역 {trace.get('area', 0)}개 → "
                            f"세부지역 {trace.get('subregion', 0)}개 → "
                            f"검색결과 {trace.get('final', 0)}개"
                        )
                        if "confirmed" in trace:
                            st.caption(
                                f"조건 확인 {trace.get('confirmed', 0)}개 · "
                                f"정보 확인 필요 {trace.get('pending', 0)}개 "
                                f"(조건부 {trace.get('conditional', 0)}개) · "
                                f"불일치 제외 {trace.get('excluded', 0)}개"
                            )
                        st.caption("명확한 불가만 제외하고 미확인 정보는 ‘확인 필요’로 남깁니다.")

            normalized_recs = [_normalize_result_item(x) for x in recs]
            confirmed_recs, pending_recs = [], []
            for course, reasons in normalized_recs:
                status, confirmed_fields, pending_fields = _result_confidence(course, cond)
                item = (course, reasons, confirmed_fields, pending_fields)
                (pending_recs if status == "pending" else confirmed_recs).append(item)

            def _render_result_group(items, title, description, pending_group=False):
                if not items:
                    return
                st.markdown(f"#### {title}")
                st.caption(description)
                # 모바일 우선: 1열 컴팩트 카드. 좁은 화면에서 2열 카드가 길어지는 문제 방지.
                for item in items:
                    course, reasons, confirmed_fields, pending_fields = item
                    with st.container():
                            weekend = bool(cond.get("weekend")) if cond else False
                            nplayers = int(cond.get("players", 4)) if cond else 4
                            est = estimate_per_person(course, weekend, nplayers)
                            three_text = get_objective_detail(course, "three_person")["label"]

                            loc = " ".join(str(x).strip() for x in
                                [course.get("region"), course.get("city")]
                                if x and str(x).strip())
                            verify_text = dual_verification_summary(course)

                            facts = []
                            result_holes_text, result_holes_level = _holes_display(course)
                            facts.append(result_holes_text)
                            if est is not None:
                                facts.append(f"예상 1인 {won(est)}")
                            elif cond and cond.get("budget"):
                                facts.append("요금 확인 필요")
                            selected_features = (cond or {}).get("objective_features", [])
                            if "2인 플레이" in selected_features:
                                facts.append(f"2인 {_objective_display(course, '2인 플레이')}")
                            if "3인 플레이" in selected_features:
                                facts.append(f"3인 {_objective_display(course, '3인 플레이')}")

                            if pending_group:
                                badge = "△ 정보 확인 필요"
                                evidence = "미확인: " + " · ".join(pending_fields)
                            else:
                                badge = "✓ 선택조건 확인됨"
                                evidence = ("확인: " + " · ".join(confirmed_fields)) if confirmed_fields else "선택조건 확인"

                            fact_text = " · ".join(facts) if facts else "세부 이용정보는 상세에서 확인"
                            descriptive = _descriptive_badges(course)
                            badge_text = " · ".join(descriptive)

                            recommendation_html = ""
                            if reasons:
                                recommendation_html = (
                                    '<div class="why" style="margin-top:6px"><b>추천 근거</b><br>'
                                    + escape(" · ".join(reasons[:2])) + '</div>'
                                )

                            skill_html = ""
                            if cond and cond.get("avg_score"):
                                skill = _skill_fit(
                                    course,
                                    cond["avg_score"],
                                    cond.get("challenge") or "적당히",
                                    cond.get("avg_score_label"),
                                )
                                skill_html = (
                                    f'<div class="why" style="margin-top:6px">'
                                    f'<b>🎯 {escape(skill["label"])}</b><br>'
                                    f'{escape(skill["detail"])}</div>'
                                )

                            st.html(f"""
                            <div class="decision-card">
                                <div class="sm">{escape(badge)}</div>
                                <div class="name">{escape(course["name"])}</div>
                                <div class="sm">{escape(loc or course.get("area",""))}</div>
                                <div class="sm">{escape(fact_text)}</div>
                                {f'<div class="sm">{escape(badge_text)}</div>' if badge_text else ''}
                                {recommendation_html}
                                {skill_html}
                            </div>
                            """)
                            if st.button("상세보기",
                                key=("pending_" if pending_group else "confirmed_") + course["id"],
                                width="stretch"):
                                st.session_state.golf_selected_id = course["id"]
                                st.session_state.golf_v14 = {}
                                st.session_state.golf_filters_open = False
                                st.rerun()

            _render_result_group(
                confirmed_recs,
                f"조건 확인됨 · {len(confirmed_recs)}개",
                "선택한 조건을 현재 보유 데이터로 확인할 수 있는 골프장입니다.",
                False,
            )
            _render_result_group(
                pending_recs,
                f"정보 확인 필요 · {len(pending_recs)}개",
                "지역에는 맞지만 선택조건 일부 정보가 없어 방문 전 확인이 필요한 골프장입니다.",
                True,
            )

        elif st.session_state.get("golf_rec_conditions"):
            st.warning(
                "선택한 조건을 모두 확인할 수 있는 골프장이 없습니다. "
                "지역이나 예산 조건을 넓혀 다시 검색해 보세요."
            )

    # =====================================================
    # VWORLD POOL / CONNECTION TEST
    # =====================================================

    with st.expander("⚙ 골프장 Pool 관리 · VWorld 점검", expanded=False):
        pool_meta = load_pool_meta()
        golf_pool_stats = pool_counts(all_clubs)
        for column, (label, field) in zip(st.columns(5), (
            ("전체 원장", "count"), ("Service Pool", "service"), ("Candidate", "candidate"),
            ("Excluded", "excluded"), ("권역 미분류", "unclassified"),
        )):
            column.metric(label, f"{golf_pool_stats[field]}개")
        if st.session_state.get("golf_pool_refresh_result"):
            last = st.session_state["golf_pool_refresh_result"]
            st.caption(f"갱신 완료 · 전체 {last['count']} · VWorld {last['vworld_count']} · Service {last['service']} · Candidate {last['candidate']} · Excluded {last['excluded']} · 권역 미분류 {last['unclassified']}")
            if (last.get("public_data") or {}).get("status") != "ok":
                st.warning((last.get("public_data") or {}).get("message", "공공데이터 교차확인 미완료"))
        vworld_key = st.secrets.get("VWORLD_API_KEY", "")
        vworld_domain = st.secrets.get("VWORLD_DOMAIN", "")
        public_service_key = st.secrets.get("DATA_GO_KR_SERVICE_KEY", "")

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("현재 저장 Pool", f'{pool_meta.get("count", len(clubs))}개')
            st.caption("전국 Pool · 좌표 기반 중권역 분류")
        with m2:
            st.metric("마지막 갱신", pool_meta.get("last_updated") or "미실행")
        with m3:
            st.metric(
                "다음 정기 갱신",
                "지금 가능" if quarterly_refresh_due() else next_refresh_text(),
            )

        if not vworld_key or not vworld_domain:
            st.warning(
                ".streamlit/secrets.toml에 VWORLD_API_KEY와 "
                "VWORLD_DOMAIN을 먼저 설정해주세요."
            )

        t1, t2 = st.columns(2)

        with t1:
            test_clicked = st.button(
                "VWorld 연결 테스트",
                width="stretch",
                disabled=not bool(vworld_key and vworld_domain),
                help="catalog.json은 변경하지 않습니다.",
            )

        test_state = st.session_state.get("vworld_test_result") or {}
        test_passed = bool(test_state.get("ok"))

        with t2:
            refresh_clicked = st.button(
                "전국 Pool 지금 갱신",
                type="primary",
                width="stretch",
                disabled=not bool(vworld_key and vworld_domain and test_passed),
                help=(
                    "VWorld 연결 테스트가 성공한 뒤 활성화됩니다. "
                    "기존 catalog.json을 백업한 뒤 전국 Pool과 병합합니다."
                ),
            )

        if test_clicked:
            try:
                with st.spinner("VWorld 전국 골프장과 좌표를 확인하고 있습니다…"):
                    result = test_vworld_connection(
                        vworld_key,
                        vworld_domain,
                        sample_size=5,
                    )
                st.session_state["vworld_test_result"] = result
            except Exception as ex:
                st.session_state.pop("vworld_test_result", None)
                st.error(f"VWorld 연결 테스트 실패: {ex}")

        result = st.session_state.get("vworld_test_result")
        if result:
            if result.get("ok"):
                st.success("VWorld API 연결 정상 · 실제 골프장 데이터 응답 확인")
            else:
                st.error("VWorld 연결은 시도했지만 정상 데이터 응답을 받지 못했습니다.")

            d1, d2, d3 = st.columns(3)
            with d1:
                st.metric("HTTP", str(result.get("http_status") or "-"))
            with d2:
                st.metric("응답형식", result.get("response_format") or "-")
            with d3:
                ctype = result.get("content_type") or "-"
                st.metric("Content-Type", ctype.split(";")[0][:24])

            if not result.get("ok") and result.get("message"):
                st.warning("VWorld 응답 메시지: " + str(result.get("message")))

            r1, r2, r3 = st.columns(3)
            with r1:
                st.metric("VWorld 조회", f'{result.get("count", 0)}개')
            with r2:
                st.metric("지도 좌표 정상", f'{result.get("coordinate_ok", 0)}개')
            with r3:
                st.metric("좌표 확인 필요", f'{result.get("coordinate_bad", 0)}개')

            st.caption(
                f'요청 좌표계: {result.get("crs_requested","EPSG:4326")} · '
                "연결 테스트는 catalog.json을 변경하지 않습니다."
            )

            samples = result.get("samples") or []
            if samples:
                st.markdown("**실제 응답 샘플**")
                for item in samples:
                    lat = item.get("lat")
                    lon = item.get("lon")
                    try:
                        coord_text = f'{float(lat):.6f}, {float(lon):.6f}'
                    except (TypeError, ValueError):
                        coord_text = "좌표 없음/변환 필요"
                    st.caption(f'• {item.get("name","")} · {coord_text}')

        if refresh_clicked:
            try:
                # 저장 직전에도 한 번 더 확인해 비정상 응답으로 catalog를 건드리지 않음
                gate = test_vworld_connection(vworld_key, vworld_domain, sample_size=2)
                if not gate.get("ok"):
                    st.error(
                        "갱신을 중단했습니다. VWorld 테스트가 정상 통과하지 않았습니다. "
                        + str(gate.get("message") or "")
                    )
                    st.stop()

                with st.spinner(
                    "기존 catalog 백업 → VWorld 전국 Pool 수집 → "
                    "기존 상세정보 병합 → 좌표 저장 중…"
                ):
                    updated = refresh_pool_dual(
                        api_key=vworld_key,
                        domain=vworld_domain,
                        public_service_key=public_service_key,
                        force=True,
                    )
                st.success(
                    f'Pool 갱신 완료 · 전체 {updated.get("count",0)}개 · '
                    f'VWorld 원본 {updated.get("vworld_count",0)}개 · '
                    f'Service {updated.get("service",0)}개 · Candidate {updated.get("candidate",0)}개 · '
                    f'Excluded {updated.get("excluded",0)}개 · 권역 미분류 {updated.get("unclassified",0)}개'
                )
                st.caption(
                    "기존 catalog.json은 자동 백업했습니다. "
                    "새 좌표를 화면에 반영하기 위해 페이지를 다시 불러옵니다."
                )
                st.session_state.pop("vworld_test_result", None)
                st.rerun()
            except Exception as ex:
                st.error(f"전국 Pool 갱신 실패: {ex}")

    # =====================================================
    # SELECTED COURSE
    # =====================================================

    club = next(
        (
            x
            for x in clubs
            if x["id"]
            == st.session_state.get(
                "golf_selected_id"
            )
        ),
        None,
    )

    if not club:
        st.stop()
    if club.get("service_status") == "candidate":
        st.info("기본정보 확인 중")

    st.divider()

    holes, holes_level = _holes_display(club)
    if holes_level == "missing":
        holes = "세부정보 확인 중"

    st.html(
        f"""
        <div class="hero">
            <div class="sm">GOLF COURSE</div>
            <h1>{escape(club["name"])}</h1>
            <div>
                {escape(str(club["region"]))}
                {escape(str(club["city"]))}
                · {holes}
            </div>
        </div>
        """
    )

    # =====================================================
    # GOLF COURSE AT A GLANCE
    # =====================================================

    operation_type = _operation_type_text(club)
    course_labels = _course_labels(club)
    intro_text = _fact_based_intro(club)

    overview_bits = []
    loc_text = " ".join(
        str(x).strip() for x in (club.get("region"), club.get("city"))
        if x and str(x).strip()
    )
    if loc_text:
        overview_bits.append("📍 " + loc_text)
    overview_bits.append("🏷 " + operation_type)
    overview_holes, overview_holes_level = _holes_display(club)
    overview_bits.append("⛳ " + overview_holes)

    st.markdown("### 한눈에 보기")
    st.caption(" · ".join(overview_bits))
    if overview_holes_level == "evidence":
        st.caption("※ 참고정보는 복수 출처에서 지지되지만 아직 확정 필드로 승격하지 않은 정보입니다.")

    # 모바일에서는 핵심정보만 먼저 보여주고 긴 설명/검증근거는 접는다.
    trait_badges = _overview_trait_badges(club)
    if trait_badges:
        st.caption(" · ".join(trait_badges[:4]))

    with st.expander("골프장 · 코스 정보 더보기", expanded=False):
        st.write(intro_text)
        if course_labels:
            st.markdown("**코스 구성** · " + " · ".join(course_labels))
        else:
            st.caption("코스 구성 · 확인 가능한 상세정보가 아직 없습니다.")

        verified_info = club.get("verified_basic_info") or {}
        evidence_info = club.get("evidence") or {}
        verified_fields = [k for k, v in verified_info.items() if isinstance(v, dict) and v.get("verified") is True]
        evidence_fields = [k for k, v in evidence_info.items() if not str(k).startswith("_") and isinstance(v, dict) and v.get("status") == "SUPPORTED"]
        if verified_fields:
            st.caption("확정 검증 · " + ", ".join(verified_fields))
        if evidence_fields:
            st.caption("참고정보 · " + ", ".join(evidence_fields))

    st.markdown("### 이용조건")
    # 모든 항목을 세로로 펼치지 않고 상태를 한 줄 요약.
    objective_summary = []
    for feature in FEATURES:
        label = _objective_display(club, feature)
        if label and "확인 필요" not in str(label):
            objective_summary.append(f"{feature} {label}")
    if objective_summary:
        st.caption(" · ".join(objective_summary[:6]))
    else:
        st.caption("확인된 이용조건이 아직 없습니다.")

    with st.expander("이용조건 근거 · KGA 코스정보", expanded=False):
        for feature in FEATURES:
            detail = get_objective_detail(club, feature)
            st.write(f"**{feature}** · {_objective_display(club, feature)}")
            st.caption(f"{detail['verification_class']} · {detail.get('checked_at') or '미확인'}")
            for note in detail.get("condition_notes", [])[:2]:
                st.caption(str(note))
        render_kga_course_intelligence(club)

    # =====================================================
    # CONTACT / NAVIGATION
    # =====================================================

    phone_value, phone_level = _phone_display(club)
    phone = str(phone_value or "").strip()

    official = (
        club.get("official_url")
        or ""
    ).strip()

    nav_query = (
        club.get("address")
        or club["name"]
    ).strip()

    kakao_nav = (
        "https://map.kakao.com/link/search/"
        + quote(nav_query)
    )

    naver_nav = (
        "https://map.naver.com/p/search/"
        + quote(nav_query)
    )

    phone_html = (
        f'<a href="tel:{escape(phone, quote=True)}">'
        f'☎ 전화</a>'
        if phone
        else '<a class="disabled">☎ 전화</a>'
    )

    home_html = (
        f'<a href="{escape(official, quote=True)}" '
        f'target="_blank" '
        f'rel="noopener noreferrer">'
        f'⌂ 홈페이지</a>'
        if official
        else '<a class="disabled">⌂ 홈페이지</a>'
    )

    st.html(
        f"""
        <div class="quick-actions">
            {phone_html}
            {home_html}
            <a href="{kakao_nav}"
               target="_blank"
               rel="noopener noreferrer">
               ↗ 카카오맵
            </a>
            <a href="{naver_nav}"
               target="_blank"
               rel="noopener noreferrer">
               ↗ 네이버지도
            </a>
        </div>
        """
    )
    if phone and phone_level == "evidence":
        st.caption("☎ 전화번호는 참고정보(B_SUPPORTED)입니다. 이용 전 공식 홈페이지에서 재확인해 주세요.")

    # =====================================================
    # ROUND DECISION SNAPSHOT
    # =====================================================

    selected_weekend = bool(
        st.session_state.get("golf_rec_conditions", {}).get("weekend", False)
    )
    selected_players = int(
        st.session_state.get("golf_rec_conditions", {}).get("players", 4)
    )
    selected_est = estimate_per_person(
        club, selected_weekend, selected_players
    )
    three_text = str(
        get_objective_detail(club, "three_person")["label"]
    )

    snapshot_bits = []
    if selected_est is not None:
        snapshot_bits.append(f"예상 1인 {won(selected_est)}")
    if three_text and "확인 필요" not in three_text:
        snapshot_bits.append(f"3인 {three_text}")
    snapshot_holes, snapshot_holes_level = _holes_display(club)
    if snapshot_holes_level != "missing":
        snapshot_bits.append(snapshot_holes)
    if snapshot_bits:
        st.caption(" · ".join(snapshot_bits))

    # =====================================================
    # NAVER MAP
    # 모바일 스크롤을 줄이기 위해 선택 골프장 지도 1개만 표시.
    # NAVER Maps JavaScript API의 ncpKeyId가 있으면 앱 안에 표시하고,
    # 없으면 네이버지도 외부 열기 버튼만 제공한다.
    # =====================================================

    selected_coord = club_lat_lon(club)
    naver_map_key = str(st.secrets.get("NAVER_MAP_NCP_KEY_ID", "") or "").strip()

    if selected_coord:
        selected_lat, selected_lon = selected_coord

        st.link_button("📍 네이버지도에서 위치 보기 ↗", naver_nav, width="stretch")
    else:
        st.caption("📍 위치정보 확인 필요")
        st.link_button("📍 네이버지도에서 위치 보기 ↗", naver_nav, width="stretch")

    # =====================================================
    # PRICE
    # =====================================================

    fee = club.get("fee", {})

    if fee.get("verified"):

        weekday_total = estimate_per_person(
            club,
            False,
            4,
        )

        weekend_total = estimate_per_person(
            club,
            True,
            4,
        )

        cart = fee.get(
            "cart_team",
            0,
        )

        caddie = fee.get(
            "caddie_team",
            0,
        )

        weekday_green = (
            fee.get("weekday_green")
            or fee.get("weekday")
            or 0
        )

        weekend_green = (
            fee.get("weekend_green")
            or fee.get("weekend")
            or 0
        )

        st.html(
            f"""
            <div class="costs">

                <div class="cost">
                    <div class="sm">
                        주중 · 1인 예상
                    </div>

                    <div class="big">
                        {won(weekday_total)}
                    </div>

                    <div class="sm">
                        그린피 {won(weekday_green)}
                        + 카트 {won(cart)}÷4
                        + 캐디 {won(caddie)}÷4
                    </div>
                </div>

                <div class="cost">
                    <div class="sm">
                        주말 · 1인 예상
                    </div>

                    <div class="big">
                        {won(weekend_total)}
                    </div>

                    <div class="sm">
                        그린피 {won(weekend_green)}
                        + 카트 {won(cart)}÷4
                        + 캐디 {won(caddie)}÷4
                    </div>
                </div>

            </div>
            """
        )

        three_person = (
            club.get(
                "play",
                {},
            ).get(
                "three_person",
                "확인 필요",
            )
        )

        st.caption(
            f'{fee.get("basis","공식 안내")} · '
            f'4인 기준 · '
            f'3인 {three_person} · '
            f'실제 예약가 변동 가능'
        )

    else:

        basis = fee.get(
            "basis",
            "그린피 공식 확인 필요",
        )

        extras = []

        if fee.get("cart_team"):
            extras.append(
                f'카트 '
                f'{won(fee["cart_team"])} / 팀'
            )

        if fee.get("caddie_team"):
            extras.append(
                f'캐디 '
                f'{won(fee["caddie_team"])} / 팀'
            )

        detail = (
            " · ".join(extras)
            if extras
            else "상세요금 공식 확인 필요"
        )

        st.info(
            f"{basis} · {detail}"
        )

    # =====================================================
    # COURSE INFORMATION
    # =====================================================

    st.markdown("### 코스 상세")

    if club.get("courses"):

        course_cards = []

        for course in club["courses"]:
            if isinstance(course, dict):
                course_name = str(course.get("name") or "").strip()
                course_holes = str(course.get("holes") or "").strip()
                course_type = str(course.get("type") or "").strip()
                title = course_name + (f" · {course_holes}H" if course_holes else "")
            else:
                title = str(course).strip()
                course_type = ""

            if not title:
                continue

            course_cards.append(
                f"""
                <div class="course">
                    <b>{escape(title)}</b>
                    <div class="sm">{escape(course_type)}</div>
                </div>
                """
            )

        st.html(
            '<div class="courses">'
            + "".join(course_cards)
            + "</div>"
        )

    overview = (
        club.get("course_overview")
        or
        "상세 코스정보는 공식 홈페이지에서 "
        "확인할 수 있습니다."
    )

    st.caption(overview)

    checked = club.get(
        "data_checked"
    )

    if checked:
        st.caption(
            f"공식정보 확인 · {checked}"
        )
    else:
        st.caption(
            "공식정보 최신 확인 필요"
        )

    # =====================================================
    # REVIEW
    # =====================================================

    tavily_key = st.secrets.get(
        "TAVILY_API_KEY",
        "",
    )

    openai_key = st.secrets.get(
        "OPENAI_API_KEY",
        "",
    )

    state = st.session_state.setdefault(
        "golf_v14",
        {},
    )

    if (
        state.get("club_id")
        != club["id"]
    ):
        state.clear()


    # =====================================================
    # BEFORE YOU BOOK
    # =====================================================

    st.markdown(
        "### 최근 후기"
    )

    # 원문 연결은 AI 분석 여부와 무관하게 항상 제공한다.
    review_query = quote_plus(f"{club['name']} 라운딩 후기")
    naver_review_search = f"https://search.naver.com/search.naver?query={review_query}"
    c_review1, c_review2 = st.columns(2)
    with c_review1:
        st.link_button("네이버 후기 찾기 ↗", naver_review_search, width="stretch")
    with c_review2:
        st.caption("AI 요약은 저장본 우선 · 필요할 때만 최신화")

    # -----------------------------------------------------
    # IMPORTANT
    # 상세페이지 진입 시 Tavily / GPT 자동 실행하지 않음
    # -----------------------------------------------------

    seeds = load_review_seed()

    runtime_saved = load_runtime_summary(
        club["id"]
    )

    seed_saved = seeds.get(
        club["id"]
    )

    # 실제 분석 데이터 우선
    saved_summary = (
        runtime_saved
        if has_meaningful_summary(
            runtime_saved
        )
        else seed_saved
    )

    live_reviews = state.get(
        "reviews"
    )

    live_agg = state.get(
        "agg"
    )

    # =====================================================
    # LIVE ANALYSIS EXISTS
    # =====================================================

    if live_reviews and live_agg:

        dated_count = sum(
            bool(
                r.get("date")
                or r.get("published_date")
            )
            for r in live_reviews
        )

        st.caption(
            f'최근 5년 분석 · '
            f'유효 후기 {len(live_reviews)}건 · '
            f'작성일 확인 {dated_count}건'
        )

        cards = []

        for dim, name in DIMS.items():

            item = live_agg.get(
                dim,
                {},
            )

            counts = item.get(
                "counts",
                {},
            )

            mentions = sum(
                counts.values()
            )

            verdict = item.get(
                "verdict",
                "후기 정보 부족",
            )

            cards.append(
                f"""
                <div class="trait">
                    <b>
                        {escape(name)}
                        <br>
                        {escape(str(verdict))}
                    </b>

                    <div class="sm">
                        언급 {mentions}건
                    </div>
                </div>
                """
            )

        st.html(
            '<div class="traits">'
            + "".join(cards)
            + "</div>"
        )

    # =====================================================
    # SAVED ANALYSIS EXISTS
    # =====================================================

    elif has_meaningful_summary(
        saved_summary
    ):

        render_review_cards(
            saved_summary,
            "저장 분석",
        )

        updated = (
            saved_summary.get("updated")
            or ""
        )

        note = (
            saved_summary.get("note")
            or "저장된 후기 분석"
        )

        meta = note

        if updated:
            meta += f" · 분석일 {updated}"

        st.caption(meta)

    # =====================================================
    # NO REVIEW ANALYSIS
    # =====================================================

    else:

        st.html(
            """
            <div class="review-empty">
                <b>아직 저장된 후기 분석이 없습니다.</b>
                <div class="review-meta">
                    골프장 정보는 바로 확인할 수 있고,
                    후기 분석은 필요할 때만 실행합니다.
                </div>
            </div>
            """
        )

    # =====================================================
    # RECENT ORIGINAL REVIEW LINKS
    #
    # 전체 AI 요약 = 최근 5년
    # 원문 링크 = 현재년도 ~ 2년 전
    # =====================================================

    source_reviews = (
        live_reviews
        if live_reviews
        else (
            (saved_summary or {}).get("reviews", [])
            if isinstance(saved_summary, dict)
            else []
        )
    )

    current_year = (
        datetime.date.today().year
    )

    cutoff_year = (
        current_year - 2
    )

    recent_links = []

    for review in (
        source_reviews or []
    ):

        year = get_review_year(
            review
        )

        if year is None:
            continue

        if not (
            cutoff_year
            <= year
            <= current_year
        ):
            continue

        url = (
            review.get("url")
            or ""
        ).strip()

        if not url:
            continue

        date_text = str(
            review.get("date")
            or review.get("published_date")
            or ""
        )

        title = (
            review.get("title")
            or review.get("source")
            or "라운딩 후기"
        )

        recent_links.append(
            {
                "date": date_text,
                "title": title,
                "url": url,
                "year": year,
                "preview": review_preview(review),
            }
        )

    # URL 중복 제거
    unique_links = []
    seen_urls = set()

    for item in sorted(
        recent_links,
        key=lambda x: (
            x["year"],
            x["date"],
        ),
        reverse=True,
    ):

        if item["url"] in seen_urls:
            continue

        seen_urls.add(
            item["url"]
        )

        unique_links.append(
            item
        )

    unique_links = unique_links[:8]

    if unique_links:

        st.markdown(
            "#### 최근 후기 직접 보기"
        )

        st.caption(
            f"{cutoff_year}~{current_year}년 · "
            f"날짜가 확인된 후기만"
        )

        # 최근 3개는 내용 미리보기까지 바로 표시하고, 나머지는 접어서 표시
        def render_review_link(item, idx):
            label_date = item["date"][:10] if item["date"] else str(item["year"])
            st.markdown(f"**{label_date} · {item['title']}**")
            st.caption(item.get("preview") or "후기 본문 미리보기는 원문에서 확인할 수 있습니다.")
            st.link_button(
                "원문 보기 ↗",
                item["url"],
                key=f"review_link_{idx}",
                width="stretch",
            )

        for idx, item in enumerate(unique_links[:3]):
            render_review_link(item, idx)

        if len(unique_links) > 3:
            with st.expander(f"후기 {len(unique_links)-3}개 더 보기", expanded=False):
                for idx, item in enumerate(unique_links[3:], start=3):
                    render_review_link(item, idx)

    # =====================================================
    # MANUAL REVIEW UPDATE
    # =====================================================

    with st.expander(
        "↻ 후기 최신화",
        expanded=False,
    ):

        st.caption(
            "전체 후기 요약은 최근 5년 웹 후기 기준입니다. "
            "이 버튼을 눌렀을 때만 "
            "Tavily + GPT를 실행합니다."
        )

        st.caption(
            f"후기 원문 링크는 "
            f"{cutoff_year}~{current_year}년 자료만 "
            f"표시합니다."
        )

        can_analyze = bool(
            tavily_key
            and openai_key
        )

        if not can_analyze:

            st.warning(
                "TAVILY_API_KEY와 "
                "OPENAI_API_KEY를 확인해주세요."
            )

        analyze_clicked = st.button(
            "후기 빠른 최신화",
            type="primary",
            width="stretch",
            disabled=not can_analyze,
        )

        if analyze_clicked:

            try:

                with st.spinner(
                    "최근 후기 수집 → "
                    "유효 후기 선별 → "
                    "AI 요약 중…"
                ):

                    records, stats = (
                        search_golf_review_bundle(
                            tavily_key,
                            club["name"],
                        )
                    )

                    reviews = (
                        analyze_reviews_with_gpt(
                            openai_key,
                            records,
                            club["name"],
                        )
                    )

                    agg_new = aggregate(
                        reviews
                    )

                    state.update(
                        {
                            "club_id": club["id"],
                            "reviews": reviews,
                            "stats": stats,
                            "agg": agg_new,
                        }
                    )

                    # 유효 분석이 있을 때만 저장
                    total_mentions = 0

                    for dim in DIMS:

                        item = agg_new.get(
                            dim,
                            {},
                        )

                        total_mentions += sum(
                            item.get(
                                "counts",
                                {},
                            ).values()
                        )

                    if total_mentions > 0:

                        save_runtime_summary(
                            club["id"],
                            agg_new,
                            reviews=reviews,
                        )

                st.rerun()

            except Exception as ex:

                st.error(
                    f"후기 분석 중 오류: {ex}"
                )

    # =====================================================
    # REVIEW EVIDENCE
    # =====================================================

    if live_agg is not None:

        with st.expander(
            "후기 근거 상세",
            expanded=False,
        ):

            for dim, name in DIMS.items():

                item = live_agg.get(
                    dim,
                    {},
                )

                counts = item.get(
                    "counts",
                    {},
                )

                if not counts:
                    continue

                st.markdown(
                    f"**{name} · "
                    f"{item.get('verdict','')}**"
                )

                evidence = item.get(
                    "evidence",
                    {},
                )

                for label in counts:

                    rows = evidence.get(
                        label,
                        [],
                    )

                    for review in rows[:2]:

                        dimension_data = (
                            review.get(
                                "dimensions",
                                {},
                            ).get(
                                dim,
                                {},
                            )
                        )

                        quote_text = (
                            dimension_data.get(
                                "evidence",
                                "",
                            )
                        )

                        date_text = (
                            review.get("date")
                            or
                            review.get(
                                "published_date"
                            )
                            or
                            "날짜 미확인"
                        )

                        url = (
                            review.get("url")
                            or ""
                        )

                        if not quote_text:
                            continue

                        link_html = ""

                        if url:
                            link_html = (
                                f' · '
                                f'<a href="'
                                f'{escape(url, quote=True)}" '
                                f'target="_blank" '
                                f'rel="noopener noreferrer">'
                                f'↗ 원문'
                                f'</a>'
                            )

                        st.html(
                            f"""
                            <div class="ev">
                                <div class="quote">
                                    “{escape(str(quote_text))}”
                                </div>

                                <span class="sm">
                                    {escape(str(date_text))}
                                </span>

                                {link_html}
                            </div>
                            """
                        )
