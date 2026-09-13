import streamlit as st

def require_page_auth():
    """
    각 pages/*.py 파일에서 호출합니다.
    로그인 세션이 없으면 메인 로그인 화면으로 유도합니다.
    """
    if not st.session_state.get("authenticated", False):
        st.warning("🔒 먼저 메인 화면에서 인증해 주세요.")
        st.link_button("메인 로그인으로 이동 →", "/", use_container_width=True)
        st.stop()


def show_home_button():
    """
    각 에이전트/페이지에서 메인 홈으로 돌아가는 버튼을 표시합니다.
    인증 세션은 유지되므로 다시 비밀번호를 묻지 않습니다.
    """
    with st.sidebar:
        st.link_button("🏠 AI Workbench 홈", "/", use_container_width=True)
