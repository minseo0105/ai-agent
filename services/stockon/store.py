"""스냅샷 파일과 STOCK:ON 설정(팀 관심 종목) 저장소.

- 스냅샷: data/admin/stockon/*.json. 오라클에서는 ailab-admin 볼륨이라 재시작해도 남는다.
  사용자 요청은 이 파일만 읽는다. 외부 API는 service.py의 갱신 작업만 부른다.
- 설정: Supabase app_settings의 stockon_settings 키(접근 설정과 같은 저장소). 없으면 로컬 파일.
"""

import json
import os
import time
from pathlib import Path
from threading import Lock

from services import access as ac

DATA_DIR = ac.ADMIN_DIR / "stockon"
SETTINGS_KEY = "stockon_settings"
SETTINGS_PATH = ac.ADMIN_DIR / "stockon_settings.json"
WATCHLIST_MAX = 30

_lock = Lock()
_settings_cache: dict = {"at": 0.0, "value": None}
SETTINGS_CACHE_SEC = 30


def _path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


def read(name: str, default=None):
    try:
        return json.loads(_path(name).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def write(name: str, value) -> None:
    """임시 파일에 쓴 뒤 교체한다. 읽는 쪽이 반쯤 쓴 파일을 보지 않게."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(name).with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for attempt in range(5):
        try:
            os.replace(tmp, _path(name))
            return
        except PermissionError:  # Windows: 백신·색인이 방금 쓴 파일을 잠깐 잡는 경우
            if attempt == 4:
                raise
            time.sleep(0.1)


# ---------------------------------------------------------
# 설정 (팀 관심 종목)
# ---------------------------------------------------------

def _normalize(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    watch = []
    for item in raw.get("watchlist") or []:
        if isinstance(item, dict) and str(item.get("code", "")).isalnum() and item.get("name"):
            code = str(item["code"])[:12]
            if code not in [w["code"] for w in watch]:
                watch.append({"code": code, "name": str(item["name"])[:40]})
    return {"watchlist": watch[:WATCHLIST_MAX], "updated_at": int(raw.get("updated_at") or 0)}


def load_settings(fresh: bool = False) -> dict:
    if not fresh and _settings_cache["value"] is not None and time.time() - _settings_cache["at"] < SETTINGS_CACHE_SEC:
        return _settings_cache["value"]
    try:
        if ac._supabase():
            value = ac._remote_get(SETTINGS_KEY)
            raw = json.loads(value) if value else {}
        else:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")) if SETTINGS_PATH.exists() else {}
    except Exception:
        # 읽기 실패 시 마지막 값을 쓴다. 관심 종목이 잠깐 비어 보이는 것보다 낫다.
        if _settings_cache["value"] is not None:
            return _settings_cache["value"]
        raw = {}
    settings = _normalize(raw)
    _settings_cache.update(at=time.time(), value=settings)
    return settings


def save_watchlist(items: list[dict]) -> dict:
    settings = _normalize({"watchlist": items, "updated_at": int(time.time())})
    text = json.dumps(settings, ensure_ascii=False)
    with _lock:
        if ac._supabase():
            ac._remote_put(SETTINGS_KEY, text)
        else:
            ac.ADMIN_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_PATH.write_text(text, encoding="utf-8")
        _settings_cache.update(at=time.time(), value=settings)
    return settings
