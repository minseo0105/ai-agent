import streamlit as st


def require_page_auth():
    """
    메인 화면에서 한 번 로그인한 세션인지 확인합니다.
    로그인된 같은 Streamlit 세션에서는 다시 비밀번호를 묻지 않습니다.
    """
    if not st.session_state.get("authenticated", False):
        st.switch_page("app.py")


def show_home_button():
    """
    각 서비스 페이지에서 AI Workbench 메인으로 돌아갑니다.
    새 탭을 만들지 않으므로 로그인 세션이 유지됩니다.
    """
    with st.sidebar:
        if st.button(
            "🏠 AI Workbench 홈",
            use_container_width=True,
            key="go_workbench_home"
        ):
            st.switch_page("app.py")
