# services/golf_repository.py
# ============================================================
# Golf DB Repository
# ------------------------------------------------------------
# 역할
# 1. data/golf 폴더에서 가장 최신의 정밀 DB를 자동 선택
# 2. checkpoint > precision > knowledge_base > catalog 순으로 선택
# 3. JSON 구조(list / {"records": []} / {"clubs": []})를 모두 지원
# 4. 정밀 DB 여부 및 데이터 충실도 통계 제공
# 5. 기존 catalog.json은 최후의 fallback으로만 사용
# ============================================================

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# PATH
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLF_DATA_DIR = PROJECT_ROOT / "data" / "golf"
CATALOG_PATH = GOLF_DATA_DIR / "catalog.json"


# ============================================================
# DB PRIORITY
# ============================================================

# 숫자가 작을수록 우선순위가 높다.
DB_PRIORITY = {
    "checkpoint": 0,
    "precision": 1,
    "knowledge_base": 2,
    "master": 3,
    "catalog": 9,
}


def _priority(path: Path) -> int:
    """
    파일명의 성격에 따라 DB 우선순위를 반환한다.
    """

    name = path.name.lower()

    if "checkpoint" in name:
        return DB_PRIORITY["checkpoint"]

    if "precision" in name:
        return DB_PRIORITY["precision"]

    if "knowledge_base" in name:
        return DB_PRIORITY["knowledge_base"]

    if "master" in name:
        return DB_PRIORITY["master"]

    if name == "catalog.json":
        return DB_PRIORITY["catalog"]

    return 99


def _is_candidate_json(path: Path) -> bool:
    """
    골프 DB 후보 JSON인지 판단한다.

    enrichment 중간산출물, audit, metadata 등의 파일은
    자동 선택 대상에서 제외한다.
    """

    if not path.is_file():
        return False

    if path.suffix.lower() != ".json":
        return False

    name = path.name.lower()

    excluded_keywords = [
        "audit",
        "meta",
        "metadata",
        "source_registry",
        "review",
        "runtime",
        "cache",
        "backup",
        "bak",
        "temp",
        "tmp",
    ]

    if any(keyword in name for keyword in excluded_keywords):
        return False

    # checkpoint
    if "checkpoint" in name:
        return True

    # precision
    if "precision" in name:
        return True

    # ontology / knowledge base
    if "knowledge_base" in name:
        return True

    # master DB
    if "golf_master" in name:
        return True

    # 기존 DB
    if name == "catalog.json":
        return True

    return False


# ============================================================
# JSON LOAD
# ============================================================

def _read_json(path: Path) -> Any:
    """
    UTF-8 / UTF-8-SIG JSON 파일을 안전하게 읽는다.
    """

    last_error = None

    for encoding in ("utf-8", "utf-8-sig"):
        try:
            with path.open("r", encoding=encoding) as f:
                return json.load(f)

        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        except json.JSONDecodeError as exc:
            raise ValueError(
                f"JSON 형식 오류: {path}\n{exc}"
            ) from exc

    if last_error:
        raise last_error

    raise ValueError(f"JSON 파일을 읽을 수 없습니다: {path}")


def _extract_records(data: Any) -> List[Dict[str, Any]]:
    """
    여러 형태의 DB 구조에서 골프장 record list를 추출한다.

    지원:
        [
            {...},
            {...}
        ]

        {
            "records": [...]
        }

        {
            "clubs": [...]
        }

        {
            "golf_courses": [...]
        }

        {
            "data": [...]
        }

        {
            "items": [...]
        }
    """

    if isinstance(data, list):
        return [
            x for x in data
            if isinstance(x, dict)
        ]

    if not isinstance(data, dict):
        return []

    possible_keys = [
        "records",
        "clubs",
        "golf_courses",
        "courses",
        "items",
        "data",
    ]

    for key in possible_keys:
        value = data.get(key)

        if isinstance(value, list):
            return [
                x for x in value
                if isinstance(x, dict)
            ]

    return []


def _validate_db(path: Path) -> Tuple[bool, int]:
    """
    실제 골프장 DB로 사용할 수 있는 파일인지 검증한다.

    return:
        (유효 여부, record 수)
    """

    try:
        data = _read_json(path)
        records = _extract_records(data)

    except Exception:
        return False, 0

    if not records:
        return False, 0

    # 최소한 name 또는 id가 존재하는 레코드가 있어야 한다.
    meaningful = 0

    for record in records[:100]:
        if record.get("name") or record.get("id"):
            meaningful += 1

    if meaningful == 0:
        return False, 0

    return True, len(records)


# ============================================================
# ACTIVE DB DISCOVERY
# ============================================================

def list_db_candidates() -> List[Path]:
    """
    data/golf 안의 사용 가능한 DB 후보를 반환한다.
    """

    if not GOLF_DATA_DIR.exists():
        return []

    candidates = []

    for path in GOLF_DATA_DIR.glob("*.json"):

        if not _is_candidate_json(path):
            continue

        valid, record_count = _validate_db(path)

        if valid and record_count > 0:
            candidates.append(path)

    return candidates


def find_active_db() -> Path:
    """
    실제 서비스에서 사용할 DB를 자동 선택한다.

    선택 기준
    ----------------------------------------------------------
    1. checkpoint
    2. precision
    3. knowledge_base
    4. golf_master
    5. catalog.json

    같은 등급이면 수정 시간이 가장 최근인 파일을 사용한다.
    """

    candidates = list_db_candidates()

    if candidates:

        candidates.sort(
            key=lambda p: (
                _priority(p),
                -p.stat().st_mtime,
            )
        )

        return candidates[0]

    # 마지막 fallback
    if CATALOG_PATH.exists():
        return CATALOG_PATH

    raise FileNotFoundError(
        "\n골프장 DB를 찾을 수 없습니다.\n"
        f"검색 위치: {GOLF_DATA_DIR}\n"
        "checkpoint / precision / knowledge_base / "
        "golf_master / catalog.json 중 하나가 필요합니다."
    )


# ============================================================
# PRECISION DB DETECTION
# ============================================================

def is_precision_db(path: Path) -> bool:
    """
    현재 DB가 정밀화 DB인지 파일명 기준으로 판단한다.
    """

    name = path.name.lower()

    precision_keywords = [
        "checkpoint",
        "precision",
        "knowledge_base",
        "golf_master",
    ]

    return any(
        keyword in name
        for keyword in precision_keywords
    )


# ============================================================
# RECORD HELPERS
# ============================================================

def _has_location(record: Dict[str, Any]) -> bool:
    """
    주소 또는 정상적인 위경도가 있으면 위치정보 보유로 판단.
    """

    if str(record.get("address") or "").strip():
        return True

    location = record.get("location")

    if isinstance(location, dict):

        if str(location.get("address") or "").strip():
            return True

        lat = (
            location.get("lat")
            or location.get("latitude")
        )

        lon = (
            location.get("lon")
            or location.get("lng")
            or location.get("longitude")
        )

        if lat is not None and lon is not None:
            return True

    lat_candidates = [
        record.get("lat"),
        record.get("latitude"),
        record.get("y"),
        record.get("vworld_y"),
    ]

    lon_candidates = [
        record.get("lon"),
        record.get("lng"),
        record.get("longitude"),
        record.get("x"),
        record.get("vworld_x"),
    ]

    if (
        any(v is not None for v in lat_candidates)
        and
        any(v is not None for v in lon_candidates)
    ):
        return True

    return False


def _has_pricing(record: Dict[str, Any]) -> bool:
    """
    실제 가격 정보가 존재하는지 판단한다.
    단순히 pricing key가 존재하는 것만으로는 True 처리하지 않는다.
    """

    pricing = record.get("pricing")

    if isinstance(pricing, dict):

        fee_records = pricing.get("fee_records")

        if isinstance(fee_records, list) and fee_records:
            return True

        for key in (
            "greenfee",
            "green_fee",
            "weekday",
            "weekend",
            "sessions",
            "fees",
            "records",
        ):
            value = pricing.get(key)

            if value not in (
                None,
                "",
                [],
                {},
            ):
                return True

    fee = record.get("fee")

    if isinstance(fee, dict):

        for key, value in fee.items():

            if key in (
                "verified",
                "basis",
                "status",
            ):
                continue

            if value not in (
                None,
                "",
                [],
                {},
            ):
                return True

    return False


def _has_course_details(record: Dict[str, Any]) -> bool:
    """
    코스/홀 상세정보가 존재하는지 판단.
    """

    details = record.get("course_details")

    if isinstance(details, list) and details:
        return True

    if isinstance(details, dict) and details:
        return True

    courses = record.get("courses")

    if isinstance(courses, list) and courses:
        return True

    return False


def _has_operations(record: Dict[str, Any]) -> bool:
    """
    1/2/3부, 캐디, 카트 등의 운영정보가 있는지 판단.
    """

    operations = record.get("operations")

    if not isinstance(operations, dict):
        return False

    for key in (
        "sessions",
        "caddie",
        "cart",
        "players",
    ):
        value = operations.get(key)

        if value not in (
            None,
            "",
            [],
            {},
        ):
            return True

    return False


def _has_official_url(record: Dict[str, Any]) -> bool:

    for key in (
        "official_url",
        "website",
        "homepage",
        "url",
    ):

        value = str(
            record.get(key) or ""
        ).strip()

        if value.startswith(
            ("http://", "https://")
        ):
            return True

    return False


# ============================================================
# LOAD ACTIVE DB
# ============================================================

@lru_cache(maxsize=1)
def load_active_db() -> Dict[str, Any]:
    """
    현재 활성 DB와 records를 함께 반환한다.
    """

    path = find_active_db()

    raw = _read_json(path)
    records = _extract_records(raw)

    return {
        "path": path,
        "file_name": path.name,
        "precision_db": is_precision_db(path),
        "records": records,
        "raw": raw,
    }


def load_records() -> List[Dict[str, Any]]:
    """
    현재 활성 DB의 골프장 목록만 반환.
    """

    return load_active_db()["records"]


def clear_cache() -> None:
    """
    DB 파일 교체 후 cache 초기화가 필요한 경우 사용.
    """

    load_active_db.cache_clear()


# ============================================================
# LOOKUP
# ============================================================

def get_by_id(
    golf_id: str,
) -> Optional[Dict[str, Any]]:

    target = str(
        golf_id or ""
    ).strip()

    if not target:
        return None

    for record in load_records():

        if str(
            record.get("id") or ""
        ).strip() == target:
            return record

    return None


def get_by_name(
    name: str,
) -> Optional[Dict[str, Any]]:

    target = str(
        name or ""
    ).strip().lower()

    if not target:
        return None

    # exact name
    for record in load_records():

        record_name = str(
            record.get("name") or ""
        ).strip().lower()

        if record_name == target:
            return record

    # aliases
    for record in load_records():

        aliases = record.get(
            "aliases"
        ) or []

        if not isinstance(
            aliases,
            list,
        ):
            continue

        normalized = [
            str(x).strip().lower()
            for x in aliases
        ]

        if target in normalized:
            return record

    return None


# ============================================================
# REGION FILTER
# ============================================================

def filter_by_area(
    area: str,
) -> List[Dict[str, Any]]:

    target = str(
        area or ""
    ).strip()

    if not target:
        return load_records()

    return [
        record
        for record in load_records()
        if str(
            record.get("area") or ""
        ).strip() == target
    ]


def precision_target_records() -> List[Dict[str, Any]]:
    """
    현재 우선 정밀화 대상:
    수도권 / 충청권 / 강원권
    """

    target_areas = {
        "수도권",
        "충청권",
        "강원권",
    }

    return [
        record
        for record in load_records()
        if record.get("area")
        in target_areas
    ]


# ============================================================
# DB STATUS
# ============================================================

def repository_status() -> Dict[str, Any]:
    """
    현재 활성 DB 상태를 진단한다.
    """

    db = load_active_db()

    path = db["path"]
    records = db["records"]

    with_location = sum(
        1
        for r in records
        if _has_location(r)
    )

    with_pricing = sum(
        1
        for r in records
        if _has_pricing(r)
    )

    with_course_details = sum(
        1
        for r in records
        if _has_course_details(r)
    )

    with_operations = sum(
        1
        for r in records
        if _has_operations(r)
    )

    with_official_url = sum(
        1
        for r in records
        if _has_official_url(r)
    )

    target_areas = {
        "수도권",
        "충청권",
        "강원권",
    }

    priority_records = [
        r
        for r in records
        if r.get("area")
        in target_areas
    ]

    return {
        "active_db": str(path),
        "file_name": path.name,
        "precision_db": db["precision_db"],

        "records": len(records),

        "priority_region_records":
            len(priority_records),

        "with_location":
            with_location,

        "with_pricing":
            with_pricing,

        "with_operations":
            with_operations,

        "with_course_details":
            with_course_details,

        "with_official_url":
            with_official_url,
    }


# ============================================================
# DIAGNOSTIC
# ============================================================

def candidate_status() -> List[Dict[str, Any]]:
    """
    자동탐색 대상 DB 후보 목록과 선택 우선순위를 보여준다.
    """

    rows = []

    active = find_active_db()

    for path in list_db_candidates():

        valid, count = _validate_db(
            path
        )

        rows.append(
            {
                "file_name":
                    path.name,

                "priority":
                    _priority(path),

                "records":
                    count,

                "valid":
                    valid,

                "precision_db":
                    is_precision_db(path),

                "selected":
                    path == active,

                "modified":
                    path.stat().st_mtime,
            }
        )

    rows.sort(
        key=lambda x: (
            x["priority"],
            -x["modified"],
        )
    )

    return rows


# ============================================================
# COMMAND LINE TEST
# ============================================================

if __name__ == "__main__":

    print(
        "\n"
        "========================================"
    )

    print(
        " GOLF REPOSITORY STATUS"
    )

    print(
        "========================================"
    )

    try:

        status = repository_status()

        print(
            json.dumps(
                status,
                ensure_ascii=False,
                indent=2,
            )
        )

        print(
            "\n"
            "----------------------------------------"
        )

        print(
            " DB CANDIDATES"
        )

        print(
            "----------------------------------------"
        )

        print(
            json.dumps(
                candidate_status(),
                ensure_ascii=False,
                indent=2,
            )
        )

    except Exception as exc:

        print(
            "\n[ERROR]"
        )

        print(
            str(exc)
        )

        raise