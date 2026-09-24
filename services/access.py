"""공개 범위 · 접근 권한 관리 (관리자 설정).

- 사이트 공개 범위: public(모두) · members(등록된 사람만) · closed(점검 중, 관리자만)
- 서비스별 공개 범위: inherit(사이트 설정 따름) · public · members · hidden(숨김)
- 구성원: 관리자가 이름을 등록하면 개인 접속 코드가 발급된다. 코드는 해시만 저장하므로
  발급 직후 한 번만 보여 주고, 잃어버리면 재발급한다(재발급 시 기존 로그인도 끊긴다).
- 토큰: HMAC 서명된 짧은 문자열. 관리자 토큰은 12시간, 구성원 토큰은 설정한 일수만큼 유효.

설정 파일(data/admin/)은 Git에 올리지 않는다.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from copy import deepcopy
from pathlib import Path
from threading import Lock

from services.config import get_secret

ADMIN_DIR = Path(__file__).resolve().parent.parent / "data" / "admin"
SETTINGS_PATH = ADMIN_DIR / "access_settings.json"
SECRET_PATH = ADMIN_DIR / "secret.key"

SITE_MODES = ["public", "members", "closed"]
SERVICE_MODES = ["inherit", "public", "members", "hidden"]
ADMIN_TOKEN_HOURS = 12
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 헷갈리는 0/O, 1/I 제외

# 서비스 id → 화면 경로 · API 경로 (접근 제어 기준)
SERVICE_CATALOG = [
    {"id": "agent", "icon": "🤖", "title": "AI 에이전트", "page": "/#agent", "api": ["/api/chat", "/api/agent"]},
    {"id": "golf", "icon": "⛳", "title": "골프장 찾기", "page": "/golf", "api": ["/api/golf"]},
    {"id": "dreamcar", "icon": "🚙", "title": "내차에서 드림카까지", "page": "/dreamcar", "api": ["/api/dreamcar"]},
    {"id": "realestate", "icon": "🏠", "title": "부동산 모니터", "page": "/realestate", "api": ["/api/realestate"]},
    {"id": "report", "icon": "📄", "title": "보고서 작성기", "page": "/report", "api": ["/api/report"]},
    {"id": "saju", "icon": "🔮", "title": "AI 사주 · 대운 분석", "page": "/saju", "api": ["/api/saju"]},
    {"id": "car-selector", "icon": "🚗", "title": "차량 선택기", "page": "/car-selector", "api": ["/api/car-selector"]},
    {"id": "gif", "icon": "🎞️", "title": "GIF 변환기", "page": "/gif", "api": ["/api/gif"]},
]
SERVICE_IDS = [s["id"] for s in SERVICE_CATALOG]

DEFAULT_SETTINGS = {
    "site_mode": "public",
    "notice": {"enabled": False, "text": ""},
    "services": {sid: "inherit" for sid in SERVICE_IDS},
    "member_token_days": 30,
    "members": [],
    "updated_at": 0,
}

_lock = Lock()


class AccessError(Exception):
    """status: HTTP 상태, code: 프런트에서 분기할 이유"""

    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# =========================================================
# 저장소
# =========================================================

def _secret_key() -> bytes:
    env = os.environ.get("ACCESS_SECRET")
    if env:
        return env.encode()
    with _lock:
        if not SECRET_PATH.exists():
            ADMIN_DIR.mkdir(parents=True, exist_ok=True)
            SECRET_PATH.write_text(secrets.token_hex(32), encoding="utf-8")
        return SECRET_PATH.read_text(encoding="utf-8").strip().encode()


def _normalize(raw: dict) -> dict:
    s = deepcopy(DEFAULT_SETTINGS)
    if raw.get("site_mode") in SITE_MODES:
        s["site_mode"] = raw["site_mode"]
    notice = raw.get("notice") or {}
    s["notice"] = {"enabled": bool(notice.get("enabled")), "text": str(notice.get("text") or "")[:300]}
    for sid in SERVICE_IDS:
        mode = (raw.get("services") or {}).get(sid)
        if mode in SERVICE_MODES:
            s["services"][sid] = mode
    days = raw.get("member_token_days")
    if isinstance(days, int) and 1 <= days <= 365:
        s["member_token_days"] = days
    s["members"] = [m for m in raw.get("members") or [] if isinstance(m, dict) and m.get("id") and m.get("code_hash")]
    s["updated_at"] = raw.get("updated_at") or 0
    return s


def load_settings() -> dict:
    with _lock:
        if not SETTINGS_PATH.exists():
            return deepcopy(DEFAULT_SETTINGS)
        try:
            return _normalize(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except Exception:
            return deepcopy(DEFAULT_SETTINGS)


def _save(settings: dict):
    settings["updated_at"] = int(time.time())
    ADMIN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)


def _mutate(fn):
    """설정을 읽고 fn(settings)로 고친 뒤 저장. fn의 반환값을 돌려준다."""
    with _lock:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")) if SETTINGS_PATH.exists() else {}
        settings = _normalize(raw)
        result = fn(settings)
        _save(settings)
        return result


# =========================================================
# 토큰 · 코드
# =========================================================

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret_key(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _verify(token: str):
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(_secret_key(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _code_hash(code: str) -> str:
    normalized = code.replace("-", "").replace(" ", "").upper()
    return hmac.new(_secret_key(), f"code:{normalized}".encode(), hashlib.sha256).hexdigest()


def _new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def identify(token: str | None, settings: dict | None = None):
    """토큰 → {"role": "admin"} | {"role": "member", "id", "name"} | None"""
    if not token:
        return None
    payload = _verify(token)
    if not payload:
        return None
    if payload.get("r") == "admin":
        return {"role": "admin", "name": "관리자"}
    if payload.get("r") == "member":
        settings = settings or load_settings()
        m = next((m for m in settings["members"] if m["id"] == payload.get("m")), None)
        if m and m.get("active", True) and m.get("ver", 1) == payload.get("v"):
            return {"role": "member", "id": m["id"], "name": m["name"]}
    return None


# =========================================================
# 로그인 (실패 횟수 제한)
# =========================================================

_failures: dict[str, list[float]] = {}
MAX_FAILURES, WINDOW_SEC = 5, 600


def _check_rate(key: str):
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < WINDOW_SEC]
    _failures[key] = recent
    if len(recent) >= MAX_FAILURES:
        raise AccessError(429, "too_many_attempts", "시도가 너무 많아요. 10분 뒤에 다시 시도해 주세요.")


def _fail(key: str):
    _failures.setdefault(key, []).append(time.time())


def admin_configured() -> bool:
    return bool(get_secret("ADMIN_PASSWORD"))


def admin_login(password: str, client: str) -> dict:
    expected = get_secret("ADMIN_PASSWORD")
    if not expected:
        raise AccessError(503, "admin_not_configured",
                          "관리자 비밀번호가 설정되지 않았어요. .streamlit/secrets.toml에 ADMIN_PASSWORD를 추가해 주세요.")
    key = f"admin:{client}"
    _check_rate(key)
    if not hmac.compare_digest(password.encode(), str(expected).encode()):
        _fail(key)
        raise AccessError(401, "wrong_password", "비밀번호가 올바르지 않아요.")
    exp = int(time.time()) + ADMIN_TOKEN_HOURS * 3600
    return {"token": _sign({"r": "admin", "exp": exp}), "expires_at": exp, "name": "관리자", "role": "admin"}


def member_login(code: str, client: str) -> dict:
    key = f"member:{client}"
    _check_rate(key)
    h = _code_hash(code or "")

    def apply(settings):
        m = next((m for m in settings["members"] if hmac.compare_digest(m["code_hash"], h)), None)
        if not m or not m.get("active", True):
            return None
        m["last_login_at"] = int(time.time())
        exp = int(time.time()) + settings["member_token_days"] * 86400
        return {"token": _sign({"r": "member", "m": m["id"], "v": m.get("ver", 1), "exp": exp}),
                "expires_at": exp, "name": m["name"], "role": "member"}

    result = _mutate(apply)
    if not result:
        _fail(key)
        raise AccessError(401, "wrong_code", "접속 코드가 올바르지 않거나 사용이 중지됐어요.")
    return result


# =========================================================
# 권한 판단
# =========================================================

def service_level(settings: dict, sid: str) -> str:
    """public · members · admin(점검 중) · hidden"""
    if settings["site_mode"] == "closed":
        return "admin"
    mode = settings["services"].get(sid, "inherit")
    if mode == "hidden":
        return "hidden"
    if mode == "inherit":
        return settings["site_mode"]
    return mode


def allowed(level: str, who) -> bool:
    if who and who["role"] == "admin":
        return True
    if level == "public":
        return True
    if level == "members":
        return bool(who)
    return False


def service_for_path(path: str):
    for s in SERVICE_CATALOG:
        if any(path == p or path.startswith(p + "/") for p in s["api"]):
            return s["id"]
    return None


def check_api(path: str, token: str | None):
    """API 요청 허용 여부. 막을 때 AccessError."""
    sid = service_for_path(path)
    if not sid:
        return
    settings = load_settings()
    who = identify(token, settings)
    level = service_level(settings, sid)
    if allowed(level, who):
        return
    if level == "admin":
        raise AccessError(403, "closed", "지금은 점검 중이에요. 잠시 후 다시 방문해 주세요.")
    if level == "hidden":
        raise AccessError(403, "hidden", "현재 공개되지 않은 서비스예요.")
    raise AccessError(401, "login_required", "등록된 사람만 이용할 수 있어요. 접속 코드를 입력해 주세요.")


def status(token: str | None) -> dict:
    """프런트 게이트 · 홈 화면용 공개 정보 (구성원 목록 등 민감정보 제외)"""
    settings = load_settings()
    who = identify(token, settings)
    services = {}
    for s in SERVICE_CATALOG:
        level = service_level(settings, s["id"])
        services[s["id"]] = {
            "level": level,
            "visible": level != "hidden" or (who is not None and who["role"] == "admin"),
            "allowed": allowed(level, who),
        }
    return {
        "site_mode": settings["site_mode"],
        "site_allowed": allowed(settings["site_mode"] if settings["site_mode"] != "closed" else "admin", who),
        "notice": settings["notice"] if settings["notice"]["enabled"] and settings["notice"]["text"].strip() else None,
        "services": services,
        "me": who,
    }


# =========================================================
# 관리자 설정
# =========================================================

def _public_member(m: dict) -> dict:
    return {k: m.get(k) for k in ("id", "name", "note", "code_hint", "active", "created_at", "last_login_at")}


def admin_view() -> dict:
    s = load_settings()
    return {
        "site_mode": s["site_mode"],
        "notice": s["notice"],
        "services": s["services"],
        "member_token_days": s["member_token_days"],
        "members": [_public_member(m) for m in s["members"]],
        "catalog": [{k: c[k] for k in ("id", "icon", "title", "page")} for c in SERVICE_CATALOG],
        "updated_at": s["updated_at"],
    }


def update_settings(site_mode: str, notice: dict, services: dict, member_token_days: int) -> dict:
    if site_mode not in SITE_MODES:
        raise AccessError(400, "invalid", "사이트 공개 범위 값이 올바르지 않아요.")
    if not 1 <= member_token_days <= 365:
        raise AccessError(400, "invalid", "로그인 유지 기간은 1~365일이어야 해요.")
    bad = [k for k, v in services.items() if k not in SERVICE_IDS or v not in SERVICE_MODES]
    if bad:
        raise AccessError(400, "invalid", "서비스 설정 값이 올바르지 않아요.")

    def apply(s):
        s["site_mode"] = site_mode
        s["notice"] = {"enabled": bool(notice.get("enabled")), "text": str(notice.get("text") or "").strip()[:300]}
        s["services"].update(services)
        s["member_token_days"] = member_token_days

    _mutate(apply)
    return admin_view()


def add_member(name: str, note: str = "") -> dict:
    name = name.strip()
    if not name:
        raise AccessError(400, "invalid", "이름을 입력해 주세요.")
    code = _new_code()
    member = {
        "id": uuid.uuid4().hex[:12], "name": name[:40], "note": note.strip()[:100],
        "code_hash": _code_hash(code), "code_hint": code[-4:], "ver": 1, "active": True,
        "created_at": int(time.time()), "last_login_at": None,
    }
    _mutate(lambda s: s["members"].append(member))
    return {"member": _public_member(member), "code": code}


def _find(s: dict, member_id: str) -> dict:
    m = next((m for m in s["members"] if m["id"] == member_id), None)
    if not m:
        raise AccessError(404, "not_found", "해당 구성원을 찾을 수 없어요.")
    return m


def update_member(member_id: str, name=None, note=None, active=None) -> dict:
    def apply(s):
        m = _find(s, member_id)
        if name is not None and name.strip():
            m["name"] = name.strip()[:40]
        if note is not None:
            m["note"] = note.strip()[:100]
        if active is not None:
            m["active"] = bool(active)
        return _public_member(m)

    return _mutate(apply)


def reissue_code(member_id: str) -> dict:
    code = _new_code()

    def apply(s):
        m = _find(s, member_id)
        m["code_hash"], m["code_hint"] = _code_hash(code), code[-4:]
        m["ver"] = m.get("ver", 1) + 1  # 기존 로그인 무효화
        return _public_member(m)

    return {"member": _mutate(apply), "code": code}


def delete_member(member_id: str):
    def apply(s):
        _find(s, member_id)
        s["members"] = [m for m in s["members"] if m["id"] != member_id]

    _mutate(apply)
