import streamlit as st

def require_page_auth():
    """
    멀티페이지 직접 접근 차단용.
    각 pages/*.py 파일에서 set_page_config 다음에:
        from auth import require_page_auth
        require_page_auth()
    를 호출하세요.
    """
    if not st.session_state.get("authenticated", False):
        st.warning("🔒 먼저 메인 화면에서 인증해 주세요.")
        st.markdown(
            '<a href="/" target="_self" '
            'style="display:inline-block;padding:10px 16px;border-radius:12px;'
            'background:#2563EB;color:white;text-decoration:none;font-weight:700;">'
            '메인 로그인으로 이동 →</a>',
            unsafe_allow_html=True
        )
        st.stop()
