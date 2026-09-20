# -*- coding: utf-8 -*-

"""
Golf Master A_VERIFIED Apply - DRY RUN v1
============================================================

목적
------------------------------------------------------------
Verifier v2의 최신 A_VERIFIED.json을 읽어서
현재 catalog.json과 비교한다.

A_VERIFIED 항목을 다음으로 분류:
1. SAME     : catalog에 이미 동일 값 존재
2. NEW      : catalog 값이 비어 있음 → 실제 반영 후보
3. CONFLICT : catalog 기존값과 A_VERIFIED 값이 다름
4. MISSING  : catalog에서 해당 골프장을 찾지 못함

중요
------------------------------------------------------------
- catalog.json 수정하지 않음
- Tavily 호출 없음
- LLM 호출 없음
- NEW도 이번 단계에서는 반영하지 않음
- SOURCE_CONFLICT는 애초에 A_VERIFIED에 포함되지 않음
"""

from __future__ import annotations

import hashlib
import json
import re

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# ============================================================
# PATH
# ============================================================

ROOT = Path(__file__).resolve().parent

CATALOG_PATH = (
    ROOT
    / "data"
    / "golf"
    / "catalog.json"
)

VERIFIER_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "verifier_v2"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "apply_dryrun_v1"
)


EXPECTED_CATALOG_COUNT = 553


EMPTY_VALUES = {
    "",
    "없음",
    "미확인",
    "확인 필요",
    "정보 없음",
    "unknown",
    "none",
    "null",
    "-",
}


# ============================================================
# BASIC
# ============================================================

def clean(value: Any) -> str:

    if value is None:
        return ""

    return str(value).strip()


def has_value(value: Any) -> bool:

    if value is None:
        return False

    if isinstance(value, str):

        text = value.strip()

        if not text:
            return False

        if text.lower() in EMPTY_VALUES:
            return False

    if isinstance(
        value,
        (list, tuple, dict),
    ):

        return bool(value)

    return True


def load_json(path: Path):

    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def save_json(
    path: Path,
    data: Any,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def sha256_bytes(data: bytes) -> str:

    return hashlib.sha256(
        data
    ).hexdigest()


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_phone(value: Any) -> str:

    return re.sub(
        r"\D",
        "",
        clean(value),
    )


def normalize_operation(value: Any):

    text = clean(value)

    if text in {
        "대중제",
        "비회원제",
        "퍼블릭",
        "대중제_명시",
    }:
        return "대중제"

    if text in {
        "회원제",
        "회원제_명시",
    }:
        return "회원제"

    if text in {
        "혼합",
        "혼합형",
        "회원제+대중제",
        "혼합_홀수명시",
    }:
        return "혼합"

    return text


def domain_of(url: Any) -> str:

    try:

        domain = (
            urlparse(
                clean(url)
            )
            .netloc
            .lower()
            .split(":")[0]
        )

        if domain.startswith(
            "www."
        ):
            domain = domain[4:]

        return domain

    except Exception:

        return ""


# ============================================================
# FIELD EQUALITY
# ============================================================

def same_value(
    field: str,
    current: Any,
    candidate: Any,
) -> bool:

    if (
        not has_value(current)
        or not has_value(candidate)
    ):
        return False

    # --------------------------------------------------------
    # URL
    # --------------------------------------------------------

    if field in {
        "official_url",
        "booking_url",
    }:

        # APPLY 단계에서는 단순 같은 도메인보다
        # URL 자체 비교를 우선한다.
        a = clean(current).rstrip("/")
        b = clean(candidate).rstrip("/")

        if a.lower() == b.lower():
            return True

        return False

    # --------------------------------------------------------
    # PHONE
    # --------------------------------------------------------

    if field == "phone":

        a = normalize_phone(
            current
        )

        b = normalize_phone(
            candidate
        )

        return (
            len(a) >= 8
            and a == b
        )

    # --------------------------------------------------------
    # HOLES
    # --------------------------------------------------------

    if field == "holes":

        try:

            return (
                int(current)
                == int(candidate)
            )

        except Exception:

            return False

    # --------------------------------------------------------
    # OPERATION
    # --------------------------------------------------------

    if field == "operation_type":

        return (
            normalize_operation(
                current
            )
            == normalize_operation(
                candidate
            )
        )

    return (
        clean(current).lower()
        == clean(candidate).lower()
    )


# ============================================================
# FIND LATEST VERIFIER v2
# ============================================================

def find_latest_verified_file() -> Path:

    if not VERIFIER_ROOT.exists():

        raise RuntimeError(
            f"Verifier v2 폴더 없음: "
            f"{VERIFIER_ROOT}"
        )

    candidates = []

    for path in (
        VERIFIER_ROOT.rglob(
            "A_VERIFIED.json"
        )
    ):

        try:

            data = load_json(
                path
            )

        except Exception:

            continue

        if isinstance(
            data,
            list,
        ):

            candidates.append(
                path
            )

    if not candidates:

        raise RuntimeError(
            "A_VERIFIED.json을 "
            "찾지 못했습니다."
        )

    return max(
        candidates,
        key=lambda path:
            path.stat().st_mtime,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print(
        "=" * 78
    )

    print(
        "Golf Master A_VERIFIED Apply DRY RUN v1"
    )

    print(
        "=" * 78
    )

    # ========================================================
    # CATALOG
    # ========================================================

    if not CATALOG_PATH.exists():

        raise RuntimeError(
            f"catalog 없음: "
            f"{CATALOG_PATH}"
        )

    original_bytes = (
        CATALOG_PATH.read_bytes()
    )

    original_hash = (
        sha256_bytes(
            original_bytes
        )
    )

    catalog = json.loads(
        original_bytes.decode(
            "utf-8-sig"
        )
    )

    if (
        len(catalog)
        != EXPECTED_CATALOG_COUNT
    ):

        raise RuntimeError(

            "안전 중단: "

            f"catalog="
            f"{len(catalog)} / "

            f"expected="
            f"{EXPECTED_CATALOG_COUNT}"
        )

    print(
        "현재 catalog:",
        len(catalog),
        "개"
    )

    # ========================================================
    # A_VERIFIED
    # ========================================================

    verified_path = (
        find_latest_verified_file()
    )

    print()

    print(
        "사용 A_VERIFIED:"
    )

    print(
        verified_path
    )

    verified_rows = (
        load_json(
            verified_path
        )
    )

    print(
        "A_VERIFIED 필드:",
        len(verified_rows),
        "개"
    )

    # ========================================================
    # INDEX
    # ========================================================

    catalog_index = {}

    for club in catalog:

        club_id = clean(
            club.get("id")
        )

        if club_id:

            catalog_index[
                club_id
            ] = club

    # ========================================================
    # CLASSIFY
    # ========================================================

    same_rows = []

    new_rows = []

    conflict_rows = []

    missing_rows = []

    field_counter = {}

    for row in verified_rows:

        if not isinstance(
            row,
            dict,
        ):
            continue

        club_id = clean(
            row.get("id")
        )

        name = clean(
            row.get("name")
        )

        field = clean(
            row.get("field")
        )

        candidate = (
            row.get("value")
        )

        if field not in {
            "official_url",
            "booking_url",
            "holes",
            "operation_type",
            "phone",
        }:

            continue

        if field not in field_counter:

            field_counter[
                field
            ] = Counter()

        club = (
            catalog_index.get(
                club_id
            )
        )

        # ----------------------------------------------------
        # CLUB MISSING
        # ----------------------------------------------------

        if club is None:

            result = {
                "id": club_id,
                "name": name,
                "field": field,
                "candidate": candidate,
                "status": "MISSING",
                "reason": (
                    "catalog_id_not_found"
                ),
            }

            missing_rows.append(
                result
            )

            field_counter[
                field
            ]["MISSING"] += 1

            continue

        current = (
            club.get(field)
        )

        # ----------------------------------------------------
        # CANDIDATE EMPTY
        # ----------------------------------------------------

        if not has_value(
            candidate
        ):

            result = {
                "id": club_id,
                "name": name,
                "field": field,
                "current": current,
                "candidate": candidate,
                "status": "MISSING",
                "reason": (
                    "verified_candidate_empty"
                ),
            }

            missing_rows.append(
                result
            )

            field_counter[
                field
            ]["MISSING"] += 1

            continue

        # ----------------------------------------------------
        # NEW
        # ----------------------------------------------------

        if not has_value(
            current
        ):

            result = {
                "id": club_id,
                "name": name,
                "field": field,
                "current": current,
                "candidate": candidate,
                "status": "NEW",
                "reason": (
                    "catalog_field_empty"
                ),
                "verification_reason": (
                    row.get("reason")
                ),
            }

            new_rows.append(
                result
            )

            field_counter[
                field
            ]["NEW"] += 1

            continue

        # ----------------------------------------------------
        # SAME
        # ----------------------------------------------------

        if same_value(
            field,
            current,
            candidate,
        ):

            result = {
                "id": club_id,
                "name": name,
                "field": field,
                "current": current,
                "candidate": candidate,
                "status": "SAME",
                "reason": (
                    "catalog_and_A_verified_agree"
                ),
                "verification_reason": (
                    row.get("reason")
                ),
            }

            same_rows.append(
                result
            )

            field_counter[
                field
            ]["SAME"] += 1

            continue

        # ----------------------------------------------------
        # CONFLICT
        # ----------------------------------------------------

        result = {
            "id": club_id,
            "name": name,
            "field": field,
            "current": current,
            "candidate": candidate,
            "status": "CONFLICT",
            "reason": (
                "existing_catalog_value_differs"
            ),
            "verification_reason": (
                row.get("reason")
            ),
        }

        conflict_rows.append(
            result
        )

        field_counter[
            field
        ]["CONFLICT"] += 1

    # ========================================================
    # OUTPUT
    # ========================================================

    stamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    run = (
        OUTPUT_ROOT
        / stamp
    )

    run.mkdir(
        parents=True,
        exist_ok=False,
    )

    summary = {

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "mode":
            "DRY_RUN_ONLY",

        "catalog_count":
            len(catalog),

        "catalog_sha256":
            original_hash,

        "catalog_modified":
            False,

        "source_A_VERIFIED":
            str(
                verified_path
            ),

        "A_VERIFIED_input":
            len(
                verified_rows
            ),

        "SAME":
            len(
                same_rows
            ),

        "NEW":
            len(
                new_rows
            ),

        "CONFLICT":
            len(
                conflict_rows
            ),

        "MISSING":
            len(
                missing_rows
            ),

        "field_counts": {

            field:
                dict(counts)

            for field, counts
            in field_counter.items()
        },
    }

    save_json(
        run
        / "summary.json",
        summary,
    )

    save_json(
        run
        / "SAME.json",
        same_rows,
    )

    save_json(
        run
        / "NEW.json",
        new_rows,
    )

    save_json(
        run
        / "CONFLICT.json",
        conflict_rows,
    )

    save_json(
        run
        / "MISSING.json",
        missing_rows,
    )

    # ========================================================
    # HUMAN REPORT
    # ========================================================

    report = []

    report.append(
        "# Golf Master Apply DRY RUN"
    )

    report.append("")

    report.append(
        f"- A_VERIFIED 입력: "
        f"{len(verified_rows)}"
    )

    report.append(
        f"- SAME: "
        f"{len(same_rows)}"
    )

    report.append(
        f"- NEW: "
        f"{len(new_rows)}"
    )

    report.append(
        f"- CONFLICT: "
        f"{len(conflict_rows)}"
    )

    report.append(
        f"- MISSING: "
        f"{len(missing_rows)}"
    )

    report.append("")

    report.append(
        "## 필드별"
    )

    report.append("")

    for field, counts in (
        field_counter.items()
    ):

        report.append(
            f"### {field}"
        )

        report.append(
            f"- SAME: "
            f"{counts.get('SAME', 0)}"
        )

        report.append(
            f"- NEW: "
            f"{counts.get('NEW', 0)}"
        )

        report.append(
            f"- CONFLICT: "
            f"{counts.get('CONFLICT', 0)}"
        )

        report.append(
            f"- MISSING: "
            f"{counts.get('MISSING', 0)}"
        )

        report.append("")

    (
        run
        / "report.md"
    ).write_text(
        "\n".join(
            report
        ),
        encoding="utf-8",
    )

    # ========================================================
    # SAFETY CHECK
    # ========================================================

    if (
        CATALOG_PATH.read_bytes()
        != original_bytes
    ):

        raise RuntimeError(
            "안전 중단: "
            "catalog.json 변경 감지"
        )

    # ========================================================
    # CONSOLE
    # ========================================================

    print()

    print(
        "=" * 78
    )

    print(
        "APPLY DRY RUN COMPLETE"
    )

    print(
        "=" * 78
    )

    print()

    print(
        "A_VERIFIED 입력:",
        len(verified_rows)
    )

    print(
        "SAME:",
        len(same_rows)
    )

    print(
        "NEW:",
        len(new_rows)
    )

    print(
        "CONFLICT:",
        len(conflict_rows)
    )

    print(
        "MISSING:",
        len(missing_rows)
    )

    print()

    print(
        "[필드별]"
    )

    for field in (
        "official_url",
        "booking_url",
        "holes",
        "operation_type",
        "phone",
    ):

        counts = (
            field_counter.get(
                field,
                Counter(),
            )
        )

        print()

        print(field)

        print(
            "  SAME:",
            counts.get(
                "SAME",
                0,
            )
        )

        print(
            "  NEW:",
            counts.get(
                "NEW",
                0,
            )
        )

        print(
            "  CONFLICT:",
            counts.get(
                "CONFLICT",
                0,
            )
        )

        print(
            "  MISSING:",
            counts.get(
                "MISSING",
                0,
            )
        )

    print()

    print(
        "추가 Tavily 호출: 0"
    )

    print(
        "LLM 호출: 0"
    )

    print(
        "catalog.json 수정: False"
    )

    print()

    print(
        "결과 폴더:"
    )

    print(
        run
    )

    print()

    print(
        "실제 신규 반영 후보:"
    )

    print(
        run
        / "NEW.json"
    )

    print()

    print(
        "기존값 충돌:"
    )

    print(
        run
        / "CONFLICT.json"
    )


if __name__ == "__main__":

    main()