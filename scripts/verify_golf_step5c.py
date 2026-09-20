"""Explicit live verification. No response/analysis files are written.

--preview opens a loopback-only QA server with the same in-memory results.
The test runner authenticates its isolated QA session, not the production app.
The preview exposes no keys, cannot make HTTP requests, and stops with this process.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import hashlib
    import tomllib
    from unittest.mock import patch
    import requests
    from streamlit.testing.v1 import AppTest
    from services.golf_api import SEARCH_BASE, AUTH_HEADERS, REQUIRED_KEYS
    from services.golf_expressions import analyze_records

    sys.stdout.reconfigure(encoding="utf-8")
    protected = [ROOT / "app.py", ROOT / "auth.py", ROOT / "services/navigation.py",
                 ROOT / "services/golf_api.py", ROOT / "data/golf/catalog.json",
                 ROOT / "data/golf/analysis_seed.json", ROOT / "requirements.txt"]
    protected += [p for p in (ROOT / "pages").glob("*.py") if not p.name.startswith("6_")]
    hashes = lambda: {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    baseline = hashes()
    app = AppTest.from_file(str(ROOT / "pages/6_골프장_추천.py"), default_timeout=240)
    app.session_state["authenticated"] = True
    with (ROOT / ".streamlit/secrets.toml").open("rb") as handle:
        credentials = tomllib.load(handle)
    for key in (*AUTH_HEADERS, *REQUIRED_KEYS[:2]):
        app.secrets[key] = credentials.get(key, "")
    del credentials
    request = requests.sessions.Session.request
    calls = []

    def guarded(session, method, url, **kwargs):
        assert method.upper() == "GET" and url == SEARCH_BASE + "/blog"
        assert set(kwargs["headers"]) == set(AUTH_HEADERS)
        assert kwargs["params"]["display"] == 100 and len(calls) < 6
        calls.append(kwargs["params"]["query"])
        response = request(session, method, url, **kwargs)
        print(f"NAVER {len(calls)}/6: {calls[-1]} · HTTP {response.status_code}", flush=True)
        return response

    with patch("requests.sessions.Session.request", side_effect=AssertionError("No call before click")):
        app.run()
    assert not app.exception
    with patch("requests.sessions.Session.request", guarded):
        app.button(key="golf_search_reviews").click().run(timeout=240)
    assert not app.exception
    state = app.session_state["golf_expression_session"]
    assert state["completed"] and state["result"], "Actual analysis failed"
    result = state["result"]
    before = analyze_records(state["records"], apply_freshness=False)
    fields = ("label", "counts", "independent_counts", "recent_valid_evidence_count",
              "latest_evidence_date", "historical_counts", "insufficiency_reason")
    legacy = next((e for e in result["evidence"] if e["link"] == "https://blog.naver.com/rachopin/222838459815"), None)
    assert legacy is not None, "The earlier E134 URL was not returned; do not invent it"
    for dimension in ("green", "maintenance"):
        m = result["dimensions"][dimension]
        assert all(legacy["evidence_id"] not in ids for ids in m["evidence_ids"].values())
        assert any(legacy["evidence_id"] in ids for ids in m["historical_evidence_ids"].values())
    with patch("requests.sessions.Session.request", side_effect=AssertionError("No call on rerun")):
        app.run()
    assert not app.exception
    assert app.button(key="golf_search_reviews").label == "최신 후기 다시 분석"
    print(json.dumps({"calls": len(calls), "attempts": state["attempts"], "cutoff": result["recent_cutoff"],
        "stats": result["stats"], "before": {d: {k: m[k] for k in ("label", "counts")} for d, m in before["dimensions"].items()},
        "after": {d: {k: m[k] for k in fields} for d, m in result["dimensions"].items()},
        "former_E134": {k: legacy[k] for k in ("evidence_id", "link", "postdate", "freshness", "detected_expression")},
        "protected_files_unchanged": hashes() == baseline, "rerun_no_requests": True,
        "ui_exceptions": len(app.exception), "storage": "session_only", "external_llm_calls": 0}, ensure_ascii=False, indent=2), flush=True)
    if "--preview" in sys.argv:
        preview(state)


def preview(state):
    """Test-only memory bridge to an actual responsive Streamlit renderer."""
    import threading
    import types
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from unittest.mock import patch
    from streamlit.web import bootstrap

    memory = types.ModuleType("golf_qa_memory")
    memory.state = state
    sys.modules["golf_qa_memory"] = memory

    class MobileFrame(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'<!doctype html><title>Golf mobile QA 390px</title><body style="margin:0;background:#e8edf0"><iframe title="390px mobile preview" src="http://127.0.0.1:8508" style="width:390px;height:844px;border:0;display:block;margin:auto"></iframe></body>')

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 8509), MobileFrame)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("MOBILE_QA http://127.0.0.1:8509 · viewport 390x844 · zero additional API calls", flush=True)
    try:
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Preview never calls APIs")):
            options = {
                "server.address": "127.0.0.1", "server.port": 8508, "server.headless": True,
                "server.fileWatcherType": "none", "browser.gatherUsageStats": False}
            bootstrap.load_config_options(flag_options=options)
            from streamlit import config
            assert config.get_option("server.address") == "127.0.0.1"
            assert config.get_option("server.port") == 8508
            bootstrap.run(str(Path(__file__).resolve()), False, ["--render"], options)
    finally:
        server.shutdown()
        del sys.modules["golf_qa_memory"]


if __name__ == "__main__":
    if "--preview-fixture" in sys.argv:
        from services.golf_expressions import analyze_records, new_expression_session
        sample = [dict(title="레이크사이드CC 화면 검증용 합성 후기", description=text,
                       url=f"https://example.com/{i}", published_at=published, query="합성 화면 QA")
                  for i, (text, published) in enumerate([
                      ("코스가 어렵다. 페어웨이가 넓다. 그린이 빠르다. 코스 관리가 좋다.", "20260801"),
                      ("그린이 빠르다. 잔디 관리가 좋다. 시설이 좋다.", "20220803")])]
        fixture = new_expression_session()
        fixture.update(records=sample, result=analyze_records(sample), completed=True)
        preview(fixture)
    elif "--render" in sys.argv:
        import runpy
        import streamlit as st
        import golf_qa_memory
        st.session_state["authenticated"] = True
        st.session_state.setdefault("golf_expression_session", golf_qa_memory.state)
        runpy.run_path(str(ROOT / "pages/6_골프장_추천.py"), run_name="__main__")
    else:
        main()
