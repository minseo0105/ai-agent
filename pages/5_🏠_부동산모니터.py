
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st


st.set_page_config(
    page_title="주택청약 · 부동산 모니터",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

from services.realestate_monitor import (
    init_db,
    get_api_status,
    fetch_apt_subscriptions,
    fetch_unsold_subscriptions,
    filter_subscriptions,
    fetch_trades_multi,
    save_alert_rules,
    get_alert_rules,
    toggle_alert_rule,
    delete_alert_rule,
    get_notifications,
    mark_notification_read,
    run_monitoring_once,
    ALL_REGIONS,
    SEOUL_REGIONS,
    GYEONGGI_REGIONS,
    PROPERTY_TYPES,
)

init_db(BASE_DIR)


st.markdown(
    """
<style>
.block-container {
    max-width: 1140px;
    padding-top: 1.3rem;
    padding-bottom: 5rem;
}

.hero {
    padding: 42px 46px;
    border-radius: 28px;
    color: white;
    background: linear-gradient(
        125deg,
        #25070B 0%,
        #64131D 55%,
        #B42332 100%
    );
    box-shadow: 0 18px 40px rgba(72,10,20,0.18);
    margin-bottom: 20px;
}

.hero-kicker {
    font-size: 11px;
    font-weight: 900;
    letter-spacing: .18em;
    color: #F8C9CF;
}

.hero-title {
    font-size: 38px;
    line-height: 1.22;
    font-weight: 900;
    letter-spacing: -.04em;
    margin-top: 10px;
}

.hero-desc {
    font-size: 14px;
    line-height: 1.75;
    color: #FCE8EB;
    max-width: 850px;
    margin-top: 15px;
}

.section-title {
    font-size: 26px;
    font-weight: 900;
    color: #9D1C2A;
    letter-spacing: -.035em;
    margin: 8px 0 5px;
}

.section-desc {
    font-size: 13px;
    color: #64748B;
    margin-bottom: 16px;
}

.card {
    background: white;
    border: 1px solid #EAE3E4;
    border-radius: 17px;
    padding: 17px 19px;
    margin: 9px 0;
    box-shadow: 0 3px 12px rgba(15,23,42,.035);
}

.badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 800;
    background: #FBEAEC;
    color: #9D1C2A;
    margin-right: 5px;
}

.badge-gray {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 800;
    background: #F1F5F9;
    color: #475569;
    margin-right: 5px;
}

.muted {
    color: #64748B;
    font-size: 12px;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #A91F2D !important;
}

div[data-baseweb="tab-highlight"] {
    background-color: #A91F2D !important;
}

div.stButton > button[kind="primary"],
div[data-testid="stFormSubmitButton"] button {
    background: #A91F2D !important;
    border-color: #A91F2D !important;
    color: white !important;
}

div.stButton > button[kind="primary"]:hover,
div[data-testid="stFormSubmitButton"] button:hover {
    background: #8F1825 !important;
    border-color: #8F1825 !important;
}

@media (max-width: 768px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }

    .hero {
        padding: 30px 24px;
    }

    .hero-title {
        font-size: 29px;
    }
}
</style>

<div class="hero">
<div class="hero-kicker">REAL ESTATE MONITORING AGENT</div>
<div class="hero-title">
내가 기다리던 청약과 부동산 변화,<br>
놓치지 않도록.
</div>
<div class="hero-desc">
서울·경기의 청약과 아파트·빌라·단독/다가구·오피스텔 실거래를
조건별로 조회하고, 관심지역의 새로운 변화를 자동으로 탐지합니다.
</div>
</div>
""",
    unsafe_allow_html=True,
)


status = get_api_status()

if status["public_data_key"]:
    st.success("공공데이터포털 API Key가 등록되어 있습니다.")
else:
    st.error(
        "PUBLIC_DATA_API_KEY가 없습니다. "
        ".streamlit/secrets.toml의 [realestate] 설정을 확인해주세요."
    )


tab_subscription, tab_trade, tab_monitor, tab_alert = st.tabs(
    [
        "청약 조회",
        "실거래 조회",
        "모니터링 조건",
        "알림함",
    ]
)


# ============================================================
# TAB 1 : 청약 조회
# ============================================================

with tab_subscription:

    st.markdown(
        '<div class="section-title">청약홈 실데이터</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="section-desc">
서울·경기 관심지역과 공급구분·청약유형·접수상태를 조합해
신규 청약과 무순위 공고를 조회합니다.
</div>
""",
        unsafe_allow_html=True,
    )

    region_scope = st.radio(
        "지역 범위",
        ["서울", "경기", "서울 + 경기"],
        horizontal=True,
        key="subscription_scope",
    )

    if region_scope == "서울":
        subscription_region_options = SEOUL_REGIONS
    elif region_scope == "경기":
        subscription_region_options = GYEONGGI_REGIONS
    else:
        subscription_region_options = ALL_REGIONS

    r1 = st.columns(2)

    with r1[0]:
        subscription_regions = st.multiselect(
            "조회지역",
            subscription_region_options,
            default=[],
            placeholder="여러 지역을 선택할 수 있습니다",
            key="subscription_regions",
        )

    with r1[1]:
        supply_types = st.multiselect(
            "공급구분",
            ["공공", "민간", "미분류"],
            default=[],
            placeholder="선택하지 않으면 전체",
            key="subscription_supply_types",
        )

    r2 = st.columns(2)

    with r2[0]:
        subscription_kinds = st.multiselect(
            "청약유형",
            [
                "일반분양",
                "사전청약",
                "신혼희망타운",
                "무순위/잔여세대",
            ],
            default=[],
            placeholder="선택하지 않으면 전체",
            key="subscription_kinds",
        )

    with r2[1]:
        subscription_statuses = st.multiselect(
            "접수상태",
            [
                "접수예정",
                "접수중",
                "접수마감",
                "일정확인",
            ],
            default=[],
            placeholder="선택하지 않으면 전체",
            key="subscription_statuses",
        )

    b1, b2 = st.columns(2)

    with b1:
        apt_button = st.button(
            "신규 APT 청약 조회",
            use_container_width=True,
        )

    with b2:
        unsold_button = st.button(
            "무순위 / 잔여세대 조회",
            use_container_width=True,
        )

    if apt_button:
        try:
            with st.spinner("신규 APT 청약 정보를 조회하고 있습니다..."):
                rows = fetch_apt_subscriptions(per_page=100)

                filtered = filter_subscriptions(
                    rows,
                    regions=subscription_regions,
                    supply_types=supply_types,
                    subscription_kinds=subscription_kinds,
                    statuses=subscription_statuses,
                )

            st.session_state["apt_subscriptions_filtered"] = filtered

            st.success(
                f"전체 {len(rows)}건 중 조건에 맞는 "
                f"{len(filtered)}건을 찾았습니다."
            )

        except Exception as e:
            st.error(f"신규 APT 청약 조회 실패: {e}")

    if unsold_button:
        try:
            with st.spinner("무순위·잔여세대 정보를 조회하고 있습니다..."):
                rows = fetch_unsold_subscriptions(per_page=100)

                filtered = filter_subscriptions(
                    rows,
                    regions=subscription_regions,
                    supply_types=supply_types,
                    subscription_kinds=subscription_kinds,
                    statuses=subscription_statuses,
                )

            st.session_state["unsold_subscriptions_filtered"] = filtered

            st.success(
                f"전체 {len(rows)}건 중 조건에 맞는 "
                f"{len(filtered)}건을 찾았습니다."
            )

        except Exception as e:
            st.error(f"무순위 / 잔여세대 조회 실패: {e}")

    apt_items = st.session_state.get(
        "apt_subscriptions_filtered",
        [],
    )

    if apt_items:
        st.markdown("#### 신규 APT 청약")

        for item in apt_items[:50]:
            st.markdown(
                f"""
<div class="card">
<b style="font-size:16px;">{item.get('name','')}</b>
<br><br>
<span class="badge">{item.get('supply_type','미분류')}</span>
<span class="badge">{item.get('subscription_kind','')}</span>
<span class="badge">{item.get('status','')}</span>
<br><br>
<span class="muted">{item.get('region','')} · {item.get('address','')}</span><br>
<span class="muted">모집공고일 {item.get('announce_date','-')}</span><br>
<span class="muted">접수 {item.get('apply_date','-')}</span>
</div>
""",
                unsafe_allow_html=True,
            )

    unsold_items = st.session_state.get(
        "unsold_subscriptions_filtered",
        [],
    )

    if unsold_items:
        st.markdown("#### 무순위 / 잔여세대")

        for item in unsold_items[:50]:
            st.markdown(
                f"""
<div class="card">
<b style="font-size:16px;">{item.get('name','')}</b>
<br><br>
<span class="badge">{item.get('supply_type','미분류')}</span>
<span class="badge">{item.get('subscription_kind','')}</span>
<span class="badge">{item.get('status','')}</span>
<br><br>
<span class="muted">{item.get('region','')} · {item.get('address','')}</span><br>
<span class="muted">모집공고일 {item.get('announce_date','-')}</span><br>
<span class="muted">접수 {item.get('apply_date','-')}</span>
</div>
""",
                unsafe_allow_html=True,
            )


# ============================================================
# TAB 2 : 실거래 조회
# ============================================================

with tab_trade:

    st.markdown(
        '<div class="section-title">국토교통부 실거래 조회</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="section-desc">
아파트뿐 아니라 연립·다세대(빌라), 단독·다가구, 오피스텔을
서울·경기 여러 지역에서 동시에 조회할 수 있습니다.
</div>
""",
        unsafe_allow_html=True,
    )

    property_types = st.multiselect(
        "주택유형",
        PROPERTY_TYPES,
        default=[
            "아파트",
            "연립·다세대",
        ],
        help="여러 유형을 동시에 선택할 수 있습니다.",
        key="trade_property_types",
    )

    trade_scope = st.radio(
        "지역 범위",
        ["서울", "경기", "서울 + 경기"],
        index=2,
        horizontal=True,
        key="trade_scope",
    )

    if trade_scope == "서울":
        trade_region_options = SEOUL_REGIONS
    elif trade_scope == "경기":
        trade_region_options = GYEONGGI_REGIONS
    else:
        trade_region_options = ALL_REGIONS

    default_trade_regions = [
        x for x in [
            "서울 > 송파구",
            "서울 > 강동구",
            "경기 > 하남시",
        ]
        if x in trade_region_options
    ]

    trade_regions = st.multiselect(
        "실거래 조회지역",
        trade_region_options,
        default=default_trade_regions,
        placeholder="예: 서울 > 성동구, 경기 > 하남시",
        key="trade_regions",
    )

    trade_month = st.text_input(
        "계약년월",
        value=datetime.now().strftime("%Y%m"),
        help="예: 202609",
        key="trade_month",
    )

    if st.button(
        "선택 조건 실거래 조회",
        type="primary",
        use_container_width=True,
        key="trade_search_btn",
    ):

        if not property_types:
            st.warning("주택유형을 1개 이상 선택해주세요.")

        elif not trade_regions:
            st.warning("실거래 조회지역을 1개 이상 선택해주세요.")

        elif not trade_month.isdigit() or len(trade_month) != 6:
            st.warning("계약년월은 YYYYMM 형식으로 입력해주세요.")

        else:
            try:
                request_count = len(property_types) * len(trade_regions)

                with st.spinner(
                    f"{len(trade_regions)}개 지역 × "
                    f"{len(property_types)}개 주택유형을 조회하고 있습니다..."
                ):
                    rows, errors = fetch_trades_multi(
                        trade_regions,
                        property_types,
                        trade_month,
                    )

                st.session_state["trade_results"] = rows
                st.session_state["trade_errors"] = errors

                st.success(
                    f"{request_count}개 조회 조합에서 "
                    f"실거래 {len(rows)}건을 찾았습니다."
                )

            except Exception as e:
                st.error(f"실거래 조회 실패: {e}")

    errors = st.session_state.get(
        "trade_errors",
        [],
    )

    if errors:
        with st.expander(
            f"일부 조회 실패 {len(errors)}건 보기"
        ):
            for error in errors:
                st.warning(error)

        st.caption(
            "연립·다세대·단독/다가구·오피스텔 API를 처음 사용하는 경우 "
            "공공데이터포털에서 해당 API 활용신청이 별도로 필요할 수 있습니다."
        )

    trade_items = st.session_state.get(
        "trade_results",
        [],
    )

    if trade_items:

        st.markdown("### 조회 요약")

        type_counts = {}

        for item in trade_items:
            key = item.get("property_type", "기타")
            type_counts[key] = type_counts.get(key, 0) + 1

        summary_cols = st.columns(
            min(4, max(1, len(type_counts)))
        )

        for idx, property_type in enumerate(PROPERTY_TYPES):
            if property_type in type_counts:
                summary_cols[
                    idx % len(summary_cols)
                ].metric(
                    property_type,
                    f"{type_counts[property_type]}건",
                )

        st.markdown("### 실거래 결과")

        result_filter = st.multiselect(
            "결과에서 주택유형 다시 필터",
            sorted(
                set(
                    item.get("property_type", "")
                    for item in trade_items
                    if item.get("property_type")
                )
            ),
            default=[],
            placeholder="선택하지 않으면 전체",
            key="trade_result_type_filter",
        )

        display_items = trade_items

        if result_filter:
            display_items = [
                x for x in trade_items
                if x.get("property_type") in result_filter
            ]

        st.caption(
            f"총 {len(display_items)}건 표시 "
            "(화면 성능을 위해 최대 300건까지 표시)"
        )

        for item in display_items[:300]:

            address_bits = [
                item.get("region", ""),
                item.get("road_name", ""),
                item.get("jibun", ""),
            ]

            address_line = " · ".join(
                x for x in address_bits if x
            )

            area_text = (
                f"{item.get('area', 0):.1f}㎡"
                if item.get("area", 0) > 0
                else "면적정보 없음"
            )

            st.markdown(
                f"""
<div class="card">
<div style="display:flex;justify-content:space-between;gap:15px;align-items:flex-start;">
<div>
<span class="badge">{item.get('property_type','')}</span>
<span class="badge-gray">{item.get('region_label','')}</span>
<br><br>
<b style="font-size:16px;">{item.get('name','')}</b><br>
<span class="muted">{address_line}</span><br>
<span class="muted">
{area_text}
· {item.get('floor','-')}층
· 준공 {item.get('build_year','-')}
</span>
</div>

<div style="
font-size:18px;
font-weight:900;
color:#A91F2D;
white-space:nowrap;
">
{item.get('price_text','')}
</div>
</div>

<div class="muted" style="margin-top:8px;">
거래일 {item.get('date','-')}
</div>
</div>
""",
                unsafe_allow_html=True,
            )


# ============================================================
# TAB 3 : 모니터링 조건
# ============================================================

with tab_monitor:

    st.markdown(
        '<div class="section-title">자동 모니터링 조건</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="section-desc">
서울·경기 여러 관심지역과 여러 탐지 이벤트를 저장하고,
실거래는 주택유형까지 구분해 모니터링합니다.
</div>
""",
        unsafe_allow_html=True,
    )

    with st.form("monitor_rule_form"):

        monitor_regions = st.multiselect(
            "관심지역",
            ALL_REGIONS,
            default=[
                "서울 > 송파구",
                "서울 > 강동구",
                "경기 > 하남시",
            ],
            placeholder="여러 지역 선택",
        )

        event_types = st.multiselect(
            "탐지 이벤트",
            [
                "신규청약",
                "무순위청약",
                "신규실거래",
            ],
            default=[
                "신규청약",
                "무순위청약",
            ],
        )

        monitor_property_types = st.multiselect(
            "실거래 주택유형",
            PROPERTY_TYPES,
            default=[
                "아파트",
                "연립·다세대",
            ],
            help="신규실거래 모니터링에만 적용됩니다.",
        )

        monitor_supply_types = st.multiselect(
            "청약 공급구분",
            [
                "공공",
                "민간",
                "미분류",
            ],
            default=[],
            placeholder="선택하지 않으면 전체",
            help="신규청약·무순위청약에만 적용됩니다.",
        )

        c1, c2 = st.columns(2)

        with c1:
            max_price = st.number_input(
                "실거래 최대가격 (억원)",
                min_value=0.0,
                max_value=100.0,
                value=20.0,
                step=0.5,
                help="0으로 설정하면 가격 상한을 적용하지 않습니다.",
            )

        with c2:
            min_area = st.number_input(
                "실거래 최소면적 (㎡)",
                min_value=0.0,
                max_value=500.0,
                value=40.0,
                step=1.0,
                help="0으로 설정하면 최소면적 조건을 적용하지 않습니다.",
            )

        submitted = st.form_submit_button(
            "이 조건으로 모니터링 시작",
            use_container_width=True,
        )

        if submitted:

            if not monitor_regions:
                st.warning("관심지역을 1개 이상 선택해주세요.")

            elif not event_types:
                st.warning("탐지 이벤트를 1개 이상 선택해주세요.")

            elif (
                "신규실거래" in event_types
                and not monitor_property_types
            ):
                st.warning(
                    "신규실거래를 선택했다면 주택유형도 1개 이상 선택해주세요."
                )

            else:
                try:
                    save_alert_rules(
                        BASE_DIR,
                        monitor_regions,
                        event_types,
                        max_price,
                        min_area,
                        monitor_supply_types,
                        monitor_property_types,
                    )

                    st.success(
                        "모니터링 조건을 저장했습니다."
                    )

                    st.rerun()

                except Exception as e:
                    st.error(f"조건 저장 실패: {e}")

    st.divider()

    if st.button(
        "지금 한 번 전체 확인",
        type="primary",
        use_container_width=True,
    ):

        try:
            with st.spinner(
                "저장된 조건을 기준으로 새 이벤트를 확인하고 있습니다..."
            ):
                result = run_monitoring_once(BASE_DIR)

            m1, m2, m3 = st.columns(3)

            m1.metric(
                "탐지 이벤트",
                result.get("events", 0),
            )

            m2.metric(
                "생성 알림",
                result.get("notifications", 0),
            )

            fetched = result.get("fetched", {})

            m3.metric(
                "조회 데이터",
                fetched.get("subscriptions", 0)
                + fetched.get("trades", 0),
            )

            for error in result.get("errors", []):
                st.warning(error)

            if not result.get("errors"):
                st.success(
                    "전체 모니터링 조회가 완료되었습니다."
                )

        except Exception as e:
            st.error(f"모니터링 실행 실패: {e}")

    st.markdown("### 저장된 모니터링 조건")

    rules = get_alert_rules(BASE_DIR)

    if not rules:
        st.info("아직 저장된 모니터링 조건이 없습니다.")

    for rule in rules:

        c1, c2, c3 = st.columns(
            [5, 1.2, 1.2]
        )

        with c1:
            status_text = (
                "모니터링 중"
                if rule["enabled"]
                else "중지됨"
            )

            if rule["event_type"] == "신규실거래":
                detail = (
                    f"{rule.get('property_type','아파트')} · "
                    f"{rule['max_price_100m']}억원 이하 · "
                    f"{rule['min_area']}㎡ 이상"
                )
            else:
                detail = (
                    f"공급구분 "
                    f"{rule.get('supply_type','전체')}"
                )

            st.markdown(
                f"""
<div class="card">
<b>{rule['region']} · {rule['event_type']}</b><br>
<span class="muted">{detail} · {status_text}</span>
</div>
""",
                unsafe_allow_html=True,
            )

        with c2:
            label = (
                "중지"
                if rule["enabled"]
                else "재시작"
            )

            if st.button(
                label,
                key=f"toggle_{rule['id']}",
                use_container_width=True,
            ):
                toggle_alert_rule(
                    BASE_DIR,
                    rule["id"],
                )
                st.rerun()

        with c3:
            if st.button(
                "삭제",
                key=f"delete_{rule['id']}",
                use_container_width=True,
            ):
                delete_alert_rule(
                    BASE_DIR,
                    rule["id"],
                )
                st.rerun()


# ============================================================
# TAB 4 : 알림함
# ============================================================

with tab_alert:

    st.markdown(
        '<div class="section-title">알림함</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="section-desc">
저장된 조건에서 새롭게 탐지된 청약·무순위·실거래 이벤트를 확인합니다.
현재 버전은 웹 알림함만 사용합니다.
</div>
""",
        unsafe_allow_html=True,
    )

    notifications = get_notifications(
        BASE_DIR,
        100,
    )

    if not notifications:
        st.info("아직 생성된 알림이 없습니다.")

    for item in notifications:

        c1, c2 = st.columns(
            [6, 1]
        )

        with c1:
            icon = (
                "🔴"
                if not item["is_read"]
                else "⚪"
            )

            st.markdown(
                f"""
<div class="card">
<b>{icon} {item.get('title','')}</b>
<br><br>
<span style="font-size:13px;color:#334155;">
{item.get('category','')} · {item.get('message','')}
</span>
<br>
<span class="muted">{item.get('created_at','')}</span>
</div>
""",
                unsafe_allow_html=True,
            )

        with c2:
            if not item["is_read"]:
                if st.button(
                    "읽음",
                    key=f"read_{item['id']}",
                    use_container_width=True,
                ):
                    mark_notification_read(
                        BASE_DIR,
                        item["id"],
                    )
                    st.rerun()
