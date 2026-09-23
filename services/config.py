"""Streamlit에 의존하지 않는 설정 로더.

우선순위: 환경변수 → .streamlit/secrets.toml
FastAPI 서버, 스케줄러, Streamlit 앱이 모두 같은 키를 쓰도록 한 곳에서 읽는다.
"""

import os
import tomllib
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = PROJECT_ROOT / ".streamlit" / "secrets.toml"


@lru_cache(maxsize=1)
def _load_secrets_file():
    if not SECRETS_PATH.exists():
        return {}
    try:
        with SECRETS_PATH.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def get_secret(name, default="", section=None):
    """환경변수 → secrets.toml [section] → secrets.toml 최상위 순으로 찾는다."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    secrets = _load_secrets_file()
    if section and isinstance(secrets.get(section), dict):
        value = secrets[section].get(name)
        if value not in (None, ""):
            return str(value).strip()
    value = secrets.get(name)
    return str(value).strip() if value not in (None, "") else default
