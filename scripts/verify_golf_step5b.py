"""Live AppTest session: at most 6 NAVER calls; prints report, writes no review data.

Run with -i to inspect/reanalyze golf_state in the page's in-memory namespace.
Never print app.secrets, headers, response objects, or raw exceptions.
"""
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests
from streamlit.testing.v1 import AppTest
from services.golf_api import SEARCH_BASE, AUTH_HEADERS, REQUIRED_KEYS
from services.golf_expressions import analyze_records


def protected_hashes():
    paths = [ROOT / "data/golf/catalog.json", ROOT / "data/golf/analysis_seed.json",
             ROOT / "services/golf_api.py", ROOT / "app.py", ROOT / "services/navigation.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def report(state):
    result = state["result"]
    if not result:
        print(json.dumps({"calls": state["naver_calls"], "error": state["error"]}, ensure_ascii=False))
        return
    examples = []
    for ev in result["evidence"]:
        observations = [o for o in ev["observations"] if o["classification"] != "uncertain"]
        if observations and ev["classification"] == "relevant":
            examples.append({k: ev[k] for k in ("evidence_id", "title", "description", "link", "postdate", "query", "course_names", "classification")}
                            | {"observations": observations})
    summary = {"initial_query": state["initial_query"], "calls": state["naver_calls"],
               "attempts": state["attempts"], "history": state["history"], "stats": result["stats"],
               "dimensions": result["dimensions"], "courses": result["courses"],
               "examples": examples[:10],
               "exclusions": [{k: e[k] for k in ("evidence_id", "title", "classification", "reason")}
                              for e in result["evidence"] if e["classification"] != "relevant"],
               "storage": result["storage"], "external_llm_calls": result["external_llm_calls"]}
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    before = protected_hashes()
    app = AppTest.from_file(str(ROOT / "pages/6_골프장_추천.py"), default_timeout=240)
    app.session_state["authenticated"] = True
    # Only load NAVER credentials; no external LLM key is read by this test/page.
    import tomllib
    with (ROOT / ".streamlit/secrets.toml").open("rb") as handle:
        credentials = tomllib.load(handle)
    for name in (*AUTH_HEADERS, *REQUIRED_KEYS[:2]):
        app.secrets[name] = credentials.get(name, "")
    del credentials
    original_request = requests.sessions.Session.request
    calls = []

    def guarded_request(session, method, url, **kwargs):
        assert method.upper() == "GET" and url == SEARCH_BASE + "/blog", "Unexpected destination"
        assert set(kwargs.get("headers", {})) == set(AUTH_HEADERS), "Unexpected header names"
        assert kwargs["params"]["display"] == 100 and len(calls) < 6, "Budget/display mismatch"
        calls.append(kwargs["params"]["query"])
        print(f"NAVER request {len(calls)}/6: {calls[-1]}", flush=True)
        response = original_request(session, method, url, **kwargs)
        print(f"HTTP {response.status_code}", flush=True)
        return response

    with patch("requests.sessions.Session.request", side_effect=AssertionError("No network before click")):
        app.run()
    assert not app.exception, "Initial page failed"
    assert not app.button(key="golf_search_reviews").disabled, "NAVER credentials unavailable"
    with patch("requests.sessions.Session.request", guarded_request):
        app.button(key="golf_search_reviews").click().run(timeout=240)
    assert not app.exception, "Page failed after click"
    state = app.session_state["golf_expression_session"]
    report(state)
    print(json.dumps({"protected_files_unchanged": before == protected_hashes(),
                      "actual_http_calls": len(calls), "ui_exceptions": len(app.exception)}, ensure_ascii=False), flush=True)
