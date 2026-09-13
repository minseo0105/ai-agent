
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
    fetch_apt_trades,
    save_alert_rules,
    get_alert_rules,
    toggle_alert_rule,
    delete_alert_rule,
    get_notifications,
    mark_notification_read,
    run_monitoring_once,
    SEOUL_LAWD,
)

init_db(BASE_DIR)


# ============================================================
# STYLE
# ============================================================

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
    max-width: 800px;
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
<div class="hero-title">내가 기다리던 청약과 부동산 변화,<br>놓치지 않도록.</div>
<div class="hero-desc">관심지역의 신규 청약·무순위 공고와 아파트 실거래 변화를 공공데이터를 통해 확인하고, 저장한 조건에 맞는 새로운 이벤트만 탐지합니다.</div>
</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# API STATUS
# ============================================================

status = get_api_status()

if status["public_data_key"]:
    st.success("공공데이터포털 API Key가 정상적으로 등록되어 있습니다.")
else:
    st.error(
        "PUBLIC_DATA_API_KEY가 없습니다. "
        ".streamlit/secrets.toml의 [realestate] 설정을 확인해주세요."
    )


# ============================================================
# TABS - 설정확인 제거
# ============================================================

tab_data, tab_monitor, tab_alert = st.tabs(
    [
        "실데이터 조회",
        "모니터링 조건",
        "알림함",
    ]
)


# ============================================================
# TAB 1 : 실데이터 조회
# ============================================================

with tab_data:

    st.markdown(
        '<div class="section-title">청약홈 실데이터</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="section-desc">
지역·공급구분·청약유형·접수상태를 기준으로 청약홈 공고를 필터링합니다.
공공/민간 분류는 청약홈 응답의 사업주체·주택구분 텍스트를 조합한 보조 분류입니다.
</div>
""",
        unsafe_allow_html=True,
    )

    filter_row1 = st.columns(2)

    with filter_row1[0]:
        subscription_regions = st.multiselect(
            "조회지역",
            list(SEOUL_LAWD.keys()),
            default=[],
            placeholder="여러 지역을 선택할 수 있습니다",
            key="subscription_regions",
        )

    with filter_row1[1]:
        supply_types = st.multiselect(
            "공급구분",
            ["공공", "민간", "미분류"],
            default=[],
            placeholder="선택하지 않으면 전체",
            key="subscription_supply_types",
        )

    filter_row2 = st.columns(2)

    with filter_row2[0]:
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

    with filter_row2[1]:
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
                f"전체 {len(rows)}건 중 조건에 맞는 {len(filtered)}건을 찾았습니다."
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
                f"전체 {len(rows)}건 중 조건에 맞는 {len(filtered)}건을 찾았습니다."
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

    st.divider()

    st.markdown(
        '<div class="section-title">국토교통부 아파트 실거래</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="section-desc">
관심지역과 계약연월을 선택해 아파트 매매 실거래를 조회합니다.
</div>
""",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)

    with c1:
        regions = list(SEOUL_LAWD.keys())
        default_index = regions.index("서울 송파구")

        trade_region = st.selectbox(
            "실거래 조회지역",
            regions,
            index=default_index,
        )

    with c2:
        trade_month = st.text_input(
            "계약년월",
            value=datetime.now().strftime("%Y%m"),
            help="예: 202609",
        )

    if st.button(
        "아파트 실거래 조회",
        type="primary",
        use_container_width=True,
    ):
        if not trade_month.isdigit() or len(trade_month) != 6:
            st.warning("계약년월은 YYYYMM 형식으로 입력해주세요.")
        else:
            try:
                with st.spinner("실거래 데이터를 조회하고 있습니다..."):
                    rows = fetch_apt_trades(
                        SEOUL_LAWD[trade_region],
                        trade_month,
                    )

                st.session_state["real_trades"] = rows
                st.success(f"실거래 {len(rows)}건을 조회했습니다.")

            except Exception as e:
                st.error(f"실거래 조회 실패: {e}")

    for item in st.session_state.get("real_trades", [])[:50]:
        st.markdown(
            f"""
<div class="card">
<div style="display:flex;justify-content:space-between;gap:15px;">
<div>
<b style="font-size:16px;">{item.get('name','')}</b><br>
<span class="muted">{item.get('region','')} · {item.get('area',0):.1f}㎡ · {item.get('floor','-')}층</span>
</div>
<div style="font-size:18px;font-weight:900;color:#A91F2D;">
{item.get('price_text','')}
</div>
</div>
<div class="muted" style="margin-top:8px;">
거래일 {item.get('date','-')} · 준공 {item.get('build_year','-')}
</div>
</div>
""",
            unsafe_allow_html=True,
        )


# ============================================================
# TAB 2 : 모니터링 조건
# ============================================================

with tab_monitor:

    st.markdown(
        '<div class="section-title">자동 모니터링 조건</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="section-desc">
관심지역과 탐지 이벤트를 여러 개 선택할 수 있습니다.
저장 시 지역 × 이벤트 조합으로 자동 등록됩니다.
</div>
""",
        unsafe_allow_html=True,
    )

    with st.form("monitor_rule_form"):

        monitor_regions = st.multiselect(
            "관심지역",
            list(SEOUL_LAWD.keys()),
            default=["서울 송파구", "서울 강동구"],
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
            )

        with c2:
            min_area = st.number_input(
                "실거래 최소면적 (㎡)",
                min_value=0.0,
                max_value=300.0,
                value=59.0,
                step=1.0,
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

            else:
                try:
                    save_alert_rules(
                        BASE_DIR,
                        monitor_regions,
                        event_types,
                        max_price,
                        min_area,
                        monitor_supply_types,
                    )

                    st.success(
                        f"{len(monitor_regions)}개 지역 × "
                        f"{len(event_types)}개 이벤트 조건을 저장했습니다."
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
            with st.spinner("저장된 조건을 기준으로 새 이벤트를 확인하고 있습니다..."):
                result = run_monitoring_once(BASE_DIR)

            m1, m2, m3 = st.columns(3)

            m1.metric("탐지 이벤트", result.get("events", 0))
            m2.metric("생성 알림", result.get("notifications", 0))

            fetched = result.get("fetched", {})
            m3.metric(
                "조회 데이터",
                fetched.get("subscriptions", 0)
                + fetched.get("trades", 0),
            )

            for error in result.get("errors", []):
                st.warning(error)

            if not result.get("errors"):
                st.success("전체 모니터링 조회가 완료되었습니다.")

        except Exception as e:
            st.error(f"모니터링 실행 실패: {e}")

    st.markdown("### 저장된 모니터링 조건")

    rules = get_alert_rules(BASE_DIR)

    if not rules:
        st.info("아직 저장된 모니터링 조건이 없습니다.")

    for rule in rules:

        c1, c2, c3 = st.columns([5, 1.2, 1.2])

        with c1:
            status_text = "모니터링 중" if rule["enabled"] else "중지됨"

            detail = ""

            if rule["event_type"] == "신규실거래":
                detail = (
                    f"{rule['max_price_100m']}억원 이하 · "
                    f"{rule['min_area']}㎡ 이상"
                )
            else:
                detail = f"공급구분 {rule.get('supply_type','전체')}"

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
            label = "중지" if rule["enabled"] else "재시작"

            if st.button(
                label,
                key=f"toggle_{rule['id']}",
                use_container_width=True,
            ):
                toggle_alert_rule(BASE_DIR, rule["id"])
                st.rerun()

        with c3:
            if st.button(
                "삭제",
                key=f"delete_{rule['id']}",
                use_container_width=True,
            ):
                delete_alert_rule(BASE_DIR, rule["id"])
                st.rerun()


# ============================================================
# TAB 3 : 알림함
# ============================================================

with tab_alert:

    st.markdown(
        '<div class="section-title">알림함</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="section-desc">
현재 버전은 웹 알림함에만 기록합니다.
휴대폰 Push·텔레그램·문자 알림 로직은 포함하지 않았습니다.
</div>
""",
        unsafe_allow_html=True,
    )

    notifications = get_notifications(BASE_DIR, 100)

    if not notifications:
        st.info("아직 생성된 알림이 없습니다.")

    for item in notifications:

        c1, c2 = st.columns([6, 1])

        with c1:
            icon = "🔴" if not item["is_read"] else "⚪"

            st.markdown(
                f"""
<div class="card">
<b>{icon} {item.get('title','')}</b><br><br>
<span style="font-size:13px;color:#334155;">
{item.get('category','')} · {item.get('message','')}
</span><br>
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
