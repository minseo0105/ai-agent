import streamlit as st


def require_page_auth():
    """
    메인(app.py)에서 한 번 로그인한 같은 Streamlit 세션이면
    상세 페이지에서 비밀번호를 다시 묻지 않습니다.
    """
    if not st.session_state.get("authenticated", False):
        st.switch_page("app.py")


def show_home_button():
    """
    각 상세 페이지 사이드바에 메인 복귀 버튼을 표시합니다.
    """
    with st.sidebar:
        if st.button(
            "🏠 메인으로",
            key="go_main_home",
            use_container_width=True,
        ):
            st.switch_page("app.py")
