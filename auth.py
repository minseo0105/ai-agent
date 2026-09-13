import streamlit as st


def require_page_auth():
    """
    메인에서 한 번 로그인한 같은 Streamlit 세션이면
    상세 페이지에서 비밀번호를 다시 묻지 않습니다.
    """
    if not st.session_state.get("authenticated", False):
        st.switch_page("app.py")


def _hide_streamlit_default_nav():
    """
    pages 폴더의 영문 파일명이 자동으로 노출되는
    Streamlit 기본 사이드바 메뉴를 강제로 숨깁니다.
    config.toml 설정이 반영되지 않는 환경에서도 동작하도록
    CSS를 페이지마다 직접 주입합니다.
    """
    st.markdown(
        """
<style>
[data-testid="stSidebarNav"] {
    display: none !important;
}
[data-testid="stSidebarNavItems"] {
    display: none !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def show_home_button():
    """
    모든 상세 페이지에서 동일한 한글 사이드바를 표시합니다.
    내부 파일명은 영문으로 유지하고 화면 표시만 한글로 합니다.
    """
    _hide_streamlit_default_nav()

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
