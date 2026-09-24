"""기존 Streamlit 화면 → 새 디지털전략부 AI LAB(Next.js) 연결.

- 새 사이트 주소는 NEW_SITE_URL(환경변수 또는 secrets.toml)로 지정한다.
- 지정하지 않았을 때 로컬(localhost)에서 실행 중이면 http://localhost:3000 을 쓰고,
  배포 환경(예: *.streamlit.app)에서는 None을 돌려준다. 방문자를 로컬 주소로 보내지 않기 위해서다.
"""

import json

import streamlit as st

from services.config import get_secret

LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0")


def _is_local_request():
    try:
        host = (st.context.headers.get("host") or "").split(":")[0].lower()
    except Exception:
        return False
    return host in LOCAL_HOSTS


def new_site_url():
    configured = (get_secret("NEW_SITE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    return "http://localhost:3000" if _is_local_request() else None


def new_site_button():
    url = new_site_url()
    if url:
        st.link_button("✨ 새 디지털전략부 AI LAB으로 이동", url, type="primary", use_container_width=True)


def redirect_script(url, delay_ms=1500):
    """최상위 창을 url로 이동시키는 스크립트(components.html용).

    컴포넌트 iframe은 sandbox라 상위 창을 직접 이동시킬 수 없다(allow-top-navigation 없음).
    같은 출처(allow-same-origin)이므로 최상위 문서에 스크립트를 넣어 그 창이 스스로 이동하게 한다.
    Streamlit Cloud는 앱을 한 겹 더 iframe으로 감싸므로 parent가 아니라 top을 대상으로 한다.
    """
    target = json.dumps(url)
    return (
        "<script>setTimeout(function(){"
        "function go(w){var d=w.document,s=d.createElement('script');"
        f"s.textContent='window.location.replace('+JSON.stringify({target})+')';d.head.appendChild(s);}}"
        "try{go(window.top);}catch(e){try{go(window.parent);}catch(e2){}}"
        f"}},{int(delay_ms)});</script>"
    )
