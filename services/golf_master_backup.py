"""Read-only runtime overlay. Never persist these records or infer negative facts."""
from copy import deepcopy
from collections import Counter
import json
import math
from pathlib import Path

MASTER_PATH = Path(__file__).resolve().parents[1] / "data/golf/master/golf_master.json"
FEATURES = {"2인 플레이": "two_person", "3인 플레이": "three_person",
            "9홀×2 라운드": "nine_hole_twice", "야간 라운드": "night_round",
            "PAR3 연습장": "par3", "야외 연습장": "driving_range"}
LABELS = {"confirmed": "확인됨", "conditional": "조건부 확인", "needs_check": "정보 확인 필요"}
UNTRUSTED = {"NEGATIVE_CANDIDATE", "REFERENCE_ONLY", "CONTAMINATED_HOLD", "UNKNOWN"}


def _legacy(club, key):
    group = "facilities" if key in ("par3", "driving_range") else "play"
    values = club.get(group) or {}
    value = values.get(key) if isinstance(values, dict) else None
    if value in (True, "가능", "있음", "yes", "Y", "y"):
        return "confirmed", value
    return "needs_check", value


def get_objective_detail(club, feature):
    key = FEATURES.get(feature, feature)
    runtime = club.get("_golf_runtime") or {}
    item = (runtime.get("features") or {}).get(key)
    if item is not None:
        return deepcopy(item)
    status, _ = _legacy(club, key)
    return dict(status=status, label=LABELS[status], verification_class="CATALOG_LEGACY",
                sources=[], condition_notes=[], checked_at=None, conflict=False)


def get_objective_status(club, feature):
    return get_objective_detail(club, feature)["status"]


def objective_filter_value(club, feature):
    # No verified-negative contract exists in this version. Never return False.
    return True if get_objective_status(club, feature) == "confirmed" else None


def matches_objective_conditions(club, features):
    return all(objective_filter_value(club, key) is not False for key in features)


def known_holes(club):
    try:
        raw = club.get("holes")
        if isinstance(raw, bool):
            return None
        value = float(str(raw).replace("홀", "").strip())
        return int(value) if math.isfinite(value) and value > 0 and value.is_integer() else None
    except (ValueError, TypeError):
        return None


def is_round_eligible(club):
    holes = known_holes(club)
    return holes is None or holes >= 18 or (
        holes == 9 and get_objective_status(club, "nine_hole_twice") == "confirmed")


def normalize_operation_type(value):
    text = str(value or "").strip()
    compact = text.replace(" ", "").lower()
    if compact in {"혼합", "회원제/대중제", "회원제·대중제혼합", "회원제+대중제"}:
        return "회원제 · 대중제 혼합"
    if compact in {"비회원제", "대중제", "대중형", "대중제(퍼블릭)", "퍼블릭", "public"}:
        return "대중제(퍼블릭)"
    if compact == "회원제":
        return "회원제"
    return text or "운영형태 확인 필요"


def attach_master(clubs, path=MASTER_PATH, enabled=True):
    rows = deepcopy(clubs)
    diagnostic = "disabled" if not enabled else "ok"
    index = {}
    if enabled:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or data.get("schema_version") != "final-1.0":
                raise ValueError("unsupported schema")
            records = data["clubs"]
            if not isinstance(records, list) or any(not isinstance(x, dict) for x in records):
                raise ValueError("invalid records")
            counts = Counter(x.get("id") for x in records)
            index = {x["id"]: x for x in records if x.get("id") and counts[x["id"]] == 1}
            if any(v > 1 for v in counts.values()):
                diagnostic = "duplicate_master_id"
        except (OSError, ValueError, KeyError, TypeError):
            diagnostic = "master_unavailable"
    counts = Counter(x.get("id") for x in rows)
    for club in rows:
        master = index.get(club.get("id")) if counts[club.get("id")] == 1 else None
        features = {}
        fields = (master or {}).get("play_facility") or {}
        if not isinstance(fields, dict):
            fields = {}
        for key in FEATURES.values():
            item = fields.get(key)
            if not isinstance(item, dict):
                continue
            classification = str(item.get("verification_class") or "UNKNOWN").upper()
            status = item.get("status")
            if classification in UNTRUSTED or status not in ("confirmed", "conditional"):
                status = "needs_check"
            if status == "confirmed" and classification not in {"SUPPORTED_B", "VERIFIED_CANDIDATE"}:
                status = "needs_check"
            if status == "conditional" and classification != "CONDITIONAL":
                status = "needs_check"
            _, legacy_value = _legacy(club, key)
            conflict = status in ("confirmed", "conditional") and legacy_value in (False, "불가", "없음", "no", "N")
            if conflict:
                status = "needs_check"
            features[key] = dict(status=status, label=LABELS[status],
                verification_class=classification, checked_at=item.get("checked_at"),
                sources=deepcopy(item.get("sources")) if isinstance(item.get("sources"), list) else [],
                condition_notes=deepcopy(item.get("condition_notes")) if isinstance(item.get("condition_notes"), list) else [],
                conflict=conflict)
        club["_golf_runtime"] = dict(features=features, matched=master is not None,
                                    diagnostic=diagnostic, version="master-runtime-1" if enabled else "catalog-only-1")
    return rows
