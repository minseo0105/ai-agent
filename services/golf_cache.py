"""Session-only experiment state. No disk, seed, database or shared cache access."""


def new_experiment():
    return {"club_id": "lakeside", "naver_calls": 0, "openai_calls": 0,
            "collection": None, "analysis": None, "attempts": [],
            "extractions": {}, "analysis_current": False, "busy": False}


def get_experiment(session_state):
    if "golf_hub_experiment" not in session_state:
        session_state["golf_hub_experiment"] = new_experiment()
    return session_state["golf_hub_experiment"]


def clear_experiment(state):
    """Drop snippets/analysis; retain call budget to prevent reset bypass."""
    calls = state["naver_calls"], state["openai_calls"]
    state.clear()
    state.update(new_experiment())
    state["naver_calls"], state["openai_calls"] = calls
