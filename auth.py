import streamlit as st


def require_page_auth():
    """
    메인 화면에서 한 번 로그인한 세션인지 확인합니다.
    같은 Streamlit 세션에서는 다시 비밀번호를 묻지 않습니다.
    """
    if not st.session_state.get("authenticated", False):
        st.switch_page("app.py")


def show_home_button():
    """
    상세 페이지의 왼쪽 메뉴를 한글로 표시합니다.
    Streamlit 기본 페이지 목록은 config.toml에서 숨깁니다.
    """
    with st.sidebar:
        st.markdown("### ✦ AI WORKBENCH")
        st.caption("민서의 AI Lab")

        if st.button(
            "🏠 메인으로",
            key="nav_home",
            use_container_width=True,
        ):
            st.switch_page("app.py")

        st.divider()
        st.markdown("**빠른 이동**")

        if st.button(
            "🚙 내차에서 드림카까지",
            key="nav_dreamcar",
            use_container_width=True,
        ):
            st.switch_page("pages/dreamcar.py")

        if st.button(
            "🏠 부동산 모니터",
            key="nav_realestate",
            use_container_width=True,
        ):
            st.switch_page("pages/realestate.py")

        if st.button(
            "📄 보고서 작성기",
            key="nav_report",
            use_container_width=True,
        ):
            st.switch_page("pages/report.py")

        if st.button(
            "🚗 차량 선택기",
            key="nav_car_selector",
            use_container_width=True,
        ):
            st.switch_page("pages/car_selector.py")

        if st.button(
            "🎞️ GIF 변환기",
            key="nav_gif",
            use_container_width=True,
        ):
            st.switch_page("pages/gif_converter.py")
