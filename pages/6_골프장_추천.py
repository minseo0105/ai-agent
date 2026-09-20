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
    load_catalog,
    find_clubs,
    estimate_per_person,
    parse_ai_conditions,
    recommendation_pool,
    load_review_seed,
    _subregion_match,
    is_recommendable,
)
from services.golf_pool_updater import (
    load_pool_meta,
    quarterly_refresh_due,
    next_refresh_text,
    refresh_pool,
    refresh_pool_dual,
    test_vworld_connection,
)
from services.golf_public_data import dual_verification_summary

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
            pending.append(feature)
    return confirmed, pending


def _result_confidence(course, cond):
    confirmed, pending = _condition_evidence(course, cond)
    return ("pending" if pending else "confirmed"), confirmed, pending



def _eligible_round_course(club):
    """알려진 18홀 미만은 제외하되, 홀 수 미확인은 검색 Pool에 남긴다."""
    raw = club.get("holes")
    try:
        holes = int(float(str(raw).replace("홀", "").strip()))
    except (TypeError, ValueError):
        holes = None
    play = club.get("play") or {}
    nine_twice = play.get("nine_hole_twice") in (True, "가능", "yes", "Y")

    # 18홀 이상: 포함
    if holes is not None and holes >= 18:
        return True
    # 9홀이라도 9홀×2가 명확히 확인된 경우: 포함
    if holes == 9 and nine_twice:
        return True
    # 1~17홀이 확인됐고 위 예외가 아니면: 제외
    if holes is not None and holes < 18:
        return False
    # 홀 수 데이터가 없는 기존 골프장은 검색결과 부족을 막기 위해 유지.
    # 카드에서 '홀 수 확인 필요'로 명확히 표시한다.
    return True


def _over_18_holes_only(clubs):
    return [club for club in clubs if _eligible_round_course(club)]




def _truthy(value):
    return value in (True, "가능", "있음", "yes", "Y", "true", "True")


def _objective_feature_status(club, key):
    """객관적 운영/시설 정보: True/False/None(미확인)."""
    play = club.get("play") or {}
    facilities = club.get("facilities") or {}
    sources = {
        "2인 플레이": play.get("two_person"),
        "3인 플레이": play.get("three_person"),
        "9홀×2 라운드": play.get("nine_hole_twice"),
        "PAR3 연습장": facilities.get("par3"),
        "야외 연습장": facilities.get("driving_range"),
        "야간 라운드": play.get("night_round"),
    }
    value = sources.get(key)
    if value in (True, "가능", "있음", "yes", "Y"): return True
    if value in (False, "불가", "없음", "no", "N"): return False
    return None


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

clubs = load_catalog()
clubs = _over_18_holes_only(clubs)

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
            <div>전국 골프장 · 조건검색 · AI 검색</div>
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
            ["골프장 직접 찾기", "조건 검색", "✨ AI 문장검색 · 선택사항"],
            default="골프장 직접 찾기",
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
            area_options = ["수도권", "충청권", "강원권", "영남권", "호남권", "제주권"]
            selected_areas = mobile_multi_choice(
                "권역",
                area_options,
                key="golf_area_multi",
                help_text="여러 권역 선택 가능 · 선택하지 않으면 전국",
            )
            # 기존 추천함수 호환용. 복수 권역은 후단에서 필터링한다.
            area = selected_areas[0] if len(selected_areas) == 1 else "전체"

            # 세부권역은 단일 권역을 선택했을 때만 다중선택 가능
            subregion_map = {
                "수도권": ["서울", "인천", "경기남부", "경기북부"],
                "충청권": ["충북", "충남"],
                "강원권": ["강원영서", "강원영동"],
                "영남권": ["경북", "경남"],
                "호남권": ["전북", "전남"],
                "제주권": ["제주"],
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

            st.markdown("##### 추가 조건 <span style='font-size:.72rem;font-weight:500;opacity:.55'>선택사항</span>", unsafe_allow_html=True)
            objective_choice = mobile_multi_choice(
                "시설 · 운영 조건",
                ["2인 플레이", "3인 플레이", "9홀×2 라운드", "PAR3 연습장", "야외 연습장", "야간 라운드"],
                key="golf_objective_multi",
                help_text="선택사항입니다. 확인된 곳을 우선 구분해 보여줍니다.",
            )

            cfind, cmore = st.columns([2.2, 1])
            with cfind:
                find_clicked = st.button("조건으로 검색", type="primary", width="stretch")
            with cmore:
                more_clicked = st.button("다음 결과", width="stretch")

            if find_clicked or more_clicked:
                st.session_state.pop("golf_selected_id", None)
                st.session_state.golf_v14 = {}

                if find_clicked:
                    st.session_state.golf_rec_offset = 0
                else:
                    st.session_state.golf_rec_offset = st.session_state.get("golf_rec_offset", 0) + 12

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
                }
                st.session_state.golf_rec_conditions = cond

                # 검증 가능한 필터 검색:
                # 1) 전체 Pool -> 2) 권역 -> 3) 세부권역 -> 4) 확인 가능한 추가조건
                total_count = len(clubs)
                search_clubs = list(clubs)

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
                    for feature in cond.get("objective_features", []):
                        if _objective_feature_status(club, feature) is False:
                            ok = False
                            break

                    if ok:
                        filtered.append(club)

                final_count = len(filtered)

                # 선택한 추가조건이 실제 화면에 즉시 체감되도록
                # '모든 선택조건이 확인된 곳'을 먼저, '정보 미확인'을 뒤에 표시한다.
                # 추천점수/랭킹은 사용하지 않고 각 그룹 안에서는 이름순이다.
                def _condition_sort_key(club):
                    _status, _confirmed, _pending = _result_confidence(club, cond)
                    return (0 if _status == "confirmed" else 1, str(club.get("name") or ""))

                filtered = sorted(filtered, key=_condition_sort_key)
                confirmed_count = 0
                pending_count = 0
                for result_club in filtered:
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
                page_clubs = filtered[start_idx:start_idx + 12]

                # 기존 카드 렌더러 호환용 tuple
                st.session_state.golf_recs = [
                    (club, ["검색조건 충족"]) for club in page_clubs
                ]
                st.session_state.golf_filter_trace = {
                    "total": total_count,
                    "area": area_count,
                    "subregion": subregion_count,
                    "final": final_count,
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
                cond["objective_features"] = []

                total_count = len(clubs)
                search_clubs = list(clubs)

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

                    if int(cond.get("players") or 4) == 3:
                        three = (club.get("play") or {}).get("three_person")
                        if three in (False, "불가", "no", "N"):
                            ok = False

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
                    (club, ["문장 검색조건 충족"]) for club in filtered[:12]
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
                st.success("검색 적용: " + " · ".join(chips))

            st.markdown("### 검색 결과")
            region_count = st.session_state.get("golf_region_pool_count")
            if region_count is not None:
                trace = st.session_state.get("golf_filter_trace") or {}
                if trace:
                    st.info(
                        f"검색 과정  |  전체 {trace.get('total', 0)}개 → "
                        f"권역 {trace.get('area', 0)}개 → "
                        f"세부지역 {trace.get('subregion', 0)}개 → "
                        f"검색결과 {trace.get('final', 0)}개"
                    )
                    if "confirmed" in trace:
                        st.caption(
                            f"조건 확인 {trace.get('confirmed', 0)}개 · "
                            f"정보 확인 필요 {trace.get('pending', 0)}개 · "
                            f"명확한 불일치 제외 {trace.get('excluded', 0)}개"
                        )
                    st.caption(
                        "선택조건은 명확한 불가만 제외하고, 정보가 없으면 결과에 남겨 "
                        "‘확인 필요’로 구분합니다."
                    )

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
                for row_start in range(0, len(items), 3):
                    row = items[row_start:row_start + 3]
                    cols = st.columns(len(row))
                    for col, item in zip(cols, row):
                        course, reasons, confirmed_fields, pending_fields = item
                        with col:
                            weekend = bool(cond.get("weekend")) if cond else False
                            nplayers = int(cond.get("players", 4)) if cond else 4
                            est = estimate_per_person(course, weekend, nplayers)
                            three_raw = (course.get("play") or {}).get("three_person")
                            if three_raw in (True, "가능", "yes", "Y"):
                                three_text = "가능"
                            elif three_raw in (False, "불가", "no", "N"):
                                three_text = "불가"
                            else:
                                three_text = "확인 필요"

                            loc = " ".join(str(x).strip() for x in
                                [course.get("region"), course.get("city")]
                                if x and str(x).strip())
                            verify_text = dual_verification_summary(course)

                            facts = []
                            if course.get("holes"):
                                facts.append(f"{course.get('holes')}홀")
                            else:
                                facts.append("홀 수 확인 필요")
                            if est is not None:
                                facts.append(f"예상 1인 {won(est)}")
                            elif cond and cond.get("budget"):
                                facts.append("요금 확인 필요")
                            selected_features = (cond or {}).get("objective_features", [])
                            if "2인 플레이" in selected_features:
                                two_raw = (course.get("play") or {}).get("two_person")
                                two_text = "가능" if two_raw in (True, "가능", "yes", "Y") else "확인 필요"
                                facts.append(f"2인 {two_text}")
                            if "3인 플레이" in selected_features:
                                facts.append(f"3인 {three_text}")

                            if pending_group:
                                badge = "△ 정보 확인 필요"
                                evidence = "미확인: " + " · ".join(pending_fields)
                            else:
                                badge = "✓ 선택조건 확인됨"
                                evidence = ("확인: " + " · ".join(confirmed_fields)) if confirmed_fields else "선택조건 확인"

                            fact_text = " · ".join(facts) if facts else "세부 이용정보는 상세에서 확인"
                            descriptive = _descriptive_badges(course)
                            badge_text = " · ".join(descriptive)
                            st.html(f"""
                            <div class="decision-card">
                                <div class="sm">{escape(badge)}</div>
                                <div class="name">{escape(course["name"])}</div>
                                <div class="sm">{escape(loc or course.get("area",""))}</div>
                                <div class="sm">🛡 {escape(verify_text)}</div>
                                <div class="why"><b>{escape(evidence)}</b></div>
                                <div class="sm">{escape(fact_text)}</div>
                                {f'<div class="sm">{escape(badge_text)}</div>' if badge_text else ''}
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
                    f'VWorld 원본 {updated.get("vworld_count",0)}개'
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

    st.divider()

    holes = (
        f'{club["holes"]}홀'
        if club.get("holes")
        else "세부정보 확인 중"
    )

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
    # CONTACT / NAVIGATION
    # =====================================================

    phone = (
        club.get("phone")
        or ""
    ).strip()

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
        club.get("play", {}).get("three_person", "확인 필요")
    )

    snapshot_bits = []
    if selected_est is not None:
        snapshot_bits.append(f"예상 1인 {won(selected_est)}")
    if three_text and "확인 필요" not in three_text:
        snapshot_bits.append(f"3인 {three_text}")
    if club.get("holes"):
        snapshot_bits.append(f"{club.get('holes')}홀")
    if snapshot_bits:
        st.caption(" · ".join(snapshot_bits))

    # =====================================================
    # NAVER MAP
    # 모바일 스크롤을 줄이기 위해 선택 골프장 지도 1개만 표시.
    # NAVER Maps JavaScript API의 ncpKeyId가 있으면 앱 안에 표시하고,
    # 없으면 네이버지도 외부 열기 버튼만 제공한다.
    # =====================================================

    st.markdown("### 위치")
    selected_coord = club_lat_lon(club)
    naver_map_key = str(st.secrets.get("NAVER_MAP_NCP_KEY_ID", "") or "").strip()

    if selected_coord:
        selected_lat, selected_lon = selected_coord

        if naver_map_key:
            safe_name = str(club.get("name") or "골프장").replace("\\", "\\\\").replace("'", "\\'")
            map_html = f"""
            <!doctype html>
            <html>
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
              <script src="https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId={naver_map_key}"></script>
              <style>
                html,body,#map{{margin:0;width:100%;height:100%;overflow:hidden}}
                #map{{border-radius:14px}}
              </style>
            </head>
            <body>
              <div id="map"></div>
              <script>
                const pos = new naver.maps.LatLng({float(selected_lat)}, {float(selected_lon)});
                const map = new naver.maps.Map('map', {{
                  center: pos, zoom: 14, zoomControl: false, mapTypeControl: false
                }});
                const marker = new naver.maps.Marker({{position: pos, map: map}});
                const info = new naver.maps.InfoWindow({{
                  content: "<div style='padding:7px 9px;font-size:12px;font-weight:700;white-space:nowrap'>{safe_name}</div>"
                }});
                naver.maps.Event.addListener(marker, 'click', function() {{
                  if (info.getMap()) info.close(); else info.open(map, marker);
                }});
              </script>
            </body>
            </html>
            """
            components.html(map_html, height=180, scrolling=False)
        else:
            st.caption("네이버 지도 앱/웹에서 위치를 바로 확인할 수 있습니다.")

        st.link_button("네이버지도에서 크게 보기 ↗", naver_nav, width="stretch")
    else:
        st.caption("📍 위치정보 확인 필요")
        st.link_button("네이버지도에서 검색 ↗", naver_nav, width="stretch")

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

    st.markdown("### 코스 정보")

    if club.get("courses"):

        course_cards = []

        for course in club["courses"]:

            course_cards.append(
                f"""
                <div class="course">
                    <b>
                        {escape(str(course.get("name","")))}
                        ·
                        {escape(str(course.get("holes","")))}H
                    </b>

                    <div class="sm">
                        {escape(str(course.get("type","")))}
                    </div>
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
