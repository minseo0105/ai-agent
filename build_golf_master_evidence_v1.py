# -*- coding: utf-8 -*-

"""
Golf Master Evidence Builder v1
============================================================

목적
------------------------------------------------------------
B_SUPPORTED DRY RUN에서 생성된 KEEP_AS_EVIDENCE.json을
catalog.json 각 골프장에 'evidence' 영역으로 저장한다.

중요 원칙
------------------------------------------------------------
1. 확정 필드(holes, phone 등)는 변경하지 않는다.
2. evidence는 참고정보일 뿐 VERIFIED가 아니다.
3. 기존 verified_basic_info는 변경하지 않는다.
4. SOURCE_CONFLICT / REVIEW 데이터는 넣지 않는다.
5. 기존 evidence가 있으면 덮어쓰지 않고 history에 보존한다.
6. 저장 전 자동 백업.
7. catalog 553개 유지 확인.
8. Tavily 호출 없음.
9. LLM 호출 없음.
"""

from __future__ import annotations

import json
import os
import shutil

from datetime import datetime
from pathlib import Path
from typing import Any


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

EVIDENCE_RUN_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "b_supported_dryrun_v1"
)

BACKUP_DIR = (
    ROOT
    / "data"
    / "golf"
    / "backups"
)

REPORT_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "master_evidence"
)

EXPECTED_COUNT = 553


# ============================================================
# BASIC
# ============================================================

def clean(value: Any) -> str:

    if value is None:
        return ""

    return str(value).strip()


def load_json(path: Path):

    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def save_json_atomic(
    path: Path,
    data: Any,
):

    temp = path.with_name(
        path.name
        + ".evidence_tmp"
    )

    temp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.replace(
        temp,
        path,
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


# ============================================================
# FIND LATEST KEEP_AS_EVIDENCE
# ============================================================

def find_latest_evidence_file():

    if not EVIDENCE_RUN_ROOT.exists():

        raise RuntimeError(
            "b_supported_dryrun_v1 폴더가 없습니다."
        )

    candidates = []

    for path in (
        EVIDENCE_RUN_ROOT.rglob(
            "KEEP_AS_EVIDENCE.json"
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
            "KEEP_AS_EVIDENCE.json을 "
            "찾지 못했습니다."
        )

    return max(
        candidates,
        key=lambda p:
            p.stat().st_mtime,
    )


# ============================================================
# NORMALIZE EVIDENCE
# ============================================================

def make_evidence_record(
    row: dict,
    checked_at: str,
):

    field = clean(
        row.get("field")
    )

    candidate = (
        row.get("candidate")
    )

    detail = (
        row.get("detail")
        or {}
    )

    source_type = (
        row.get("source_type")
        or "unknown"
    )

    verification_reason = (
        row.get(
            "verification_reason"
        )
    )

    promotion_reason = (
        row.get(
            "promotion_reason"
        )
    )

    record = {

        "candidate":
            candidate,

        "status":
            "SUPPORTED",

        "confidence":
            "B",

        "display_status":
            "참고정보",

        "source_type":
            source_type,

        "verification_reason":
            verification_reason,

        "evidence_reason":
            promotion_reason,

        "checked_at":
            checked_at,

        "can_auto_apply":
            False,
    }

    # Verifier가 남긴 보조정보도 보존
    if detail:

        record[
            "verification_detail"
        ] = detail

    return field, record


# ============================================================
# SAME EVIDENCE
# ============================================================

def same_evidence(
    old: dict,
    new: dict,
):

    if not isinstance(
        old,
        dict,
    ):

        return False

    return (
        old.get("candidate")
        == new.get("candidate")
        and
        old.get("status")
        == new.get("status")
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
        "Golf Master Evidence Builder v1"
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

    catalog = load_json(
        CATALOG_PATH
    )

    if (
        len(catalog)
        != EXPECTED_COUNT
    ):

        raise RuntimeError(

            "안전 중단: "

            f"catalog="
            f"{len(catalog)} / "

            f"expected="
            f"{EXPECTED_COUNT}"
        )

    print(
        "현재 catalog:",
        len(catalog)
    )

    # ========================================================
    # EVIDENCE SOURCE
    # ========================================================

    evidence_path = (
        find_latest_evidence_file()
    )

    print()

    print(
        "사용 Evidence:"
    )

    print(
        evidence_path
    )

    evidence_rows = (
        load_json(
            evidence_path
        )
    )

    print(
        "Evidence 입력:",
        len(evidence_rows)
    )

    # ========================================================
    # INDEX
    # ========================================================

    index = {}

    for club in catalog:

        club_id = clean(
            club.get("id")
        )

        if club_id:

            index[
                club_id
            ] = club

    # ========================================================
    # PRE-CHECK
    # ========================================================

    missing_ids = []

    for row in evidence_rows:

        club_id = clean(
            row.get("id")
        )

        if (
            club_id
            and club_id not in index
        ):

            missing_ids.append(
                {
                    "id":
                        club_id,

                    "name":
                        row.get("name"),

                    "field":
                        row.get("field"),
                }
            )

    if missing_ids:

        print()

        print(
            "catalog에 없는 ID 발견:"
        )

        for item in missing_ids:

            print(
                "-",
                item
            )

        raise RuntimeError(
            "ID 불일치로 안전 중단"
        )

    # ========================================================
    # BACKUP
    # ========================================================

    stamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    checked_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup_path = (
        BACKUP_DIR
        / (
            "catalog_before_master_evidence_"
            + stamp
            + ".json"
        )
    )

    shutil.copy2(
        CATALOG_PATH,
        backup_path,
    )

    print()

    print(
        "백업:"
    )

    print(
        backup_path
    )

    # ========================================================
    # APPLY EVIDENCE
    # ========================================================

    added = []

    replaced = []

    unchanged = []

    field_counts = {}

    clubs_with_evidence = set()

    for row in evidence_rows:

        club_id = clean(
            row.get("id")
        )

        if not club_id:

            continue

        club = index[
            club_id
        ]

        field, record = (
            make_evidence_record(
                row,
                checked_at,
            )
        )

        if not field:

            continue

        field_counts[
            field
        ] = (
            field_counts.get(
                field,
                0,
            )
            + 1
        )

        evidence = (
            club.setdefault(
                "evidence",
                {}
            )
        )

        existing = (
            evidence.get(
                field
            )
        )

        # ----------------------------------------------------
        # NEW EVIDENCE
        # ----------------------------------------------------

        if existing is None:

            evidence[
                field
            ] = record

            added.append(
                {
                    "id":
                        club_id,

                    "name":
                        club.get(
                            "name"
                        ),

                    "field":
                        field,

                    "candidate":
                        record.get(
                            "candidate"
                        ),
                }
            )

            clubs_with_evidence.add(
                club_id
            )

            continue

        # ----------------------------------------------------
        # SAME EVIDENCE
        # ----------------------------------------------------

        if same_evidence(
            existing,
            record,
        ):

            unchanged.append(
                {
                    "id":
                        club_id,

                    "name":
                        club.get(
                            "name"
                        ),

                    "field":
                        field,
                }
            )

            clubs_with_evidence.add(
                club_id
            )

            continue

        # ----------------------------------------------------
        # REPLACE WITH HISTORY
        # ----------------------------------------------------

        history = (
            evidence.setdefault(
                "_history",
                []
            )
        )

        history.append(
            {
                "field":
                    field,

                "previous":
                    existing,

                "replaced_at":
                    checked_at,
            }
        )

        evidence[
            field
        ] = record

        replaced.append(
            {
                "id":
                    club_id,

                "name":
                    club.get(
                        "name"
                    ),

                "field":
                    field,

                "previous_candidate":
                    (
                        existing.get(
                            "candidate"
                        )
                        if isinstance(
                            existing,
                            dict,
                        )
                        else existing
                    ),

                "new_candidate":
                    record.get(
                        "candidate"
                    ),
            }
        )

        clubs_with_evidence.add(
            club_id
        )

    # ========================================================
    # SAVE
    # ========================================================

    save_json_atomic(
        CATALOG_PATH,
        catalog,
    )

    # ========================================================
    # RELOAD CHECK
    # ========================================================

    reloaded = load_json(
        CATALOG_PATH
    )

    if (
        len(reloaded)
        != EXPECTED_COUNT
    ):

        shutil.copy2(
            backup_path,
            CATALOG_PATH,
        )

        raise RuntimeError(
            "catalog 개수가 변경되어 "
            "백업으로 자동 복원했습니다."
        )

    # ========================================================
    # VERIFY EVIDENCE COUNT
    # ========================================================

    stored_count = 0

    stored_clubs = 0

    for club in reloaded:

        evidence = (
            club.get(
                "evidence"
            )
            or {}
        )

        normal_fields = [
            key
            for key in evidence.keys()
            if not key.startswith(
                "_"
            )
        ]

        if normal_fields:

            stored_clubs += 1

            stored_count += len(
                normal_fields
            )

    # ========================================================
    # REPORT
    # ========================================================

    report_dir = (
        REPORT_ROOT
        / stamp
    )

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {

        "created_at":
            checked_at,

        "catalog_count":
            len(reloaded),

        "source":
            str(
                evidence_path
            ),

        "input_evidence_count":
            len(
                evidence_rows
            ),

        "added":
            len(
                added
            ),

        "replaced":
            len(
                replaced
            ),

        "unchanged":
            len(
                unchanged
            ),

        "clubs_touched":
            len(
                clubs_with_evidence
            ),

        "catalog_total_evidence_fields":
            stored_count,

        "catalog_clubs_with_evidence":
            stored_clubs,

        "field_counts":
            field_counts,

        "backup":
            str(
                backup_path
            ),
    }

    save_json(
        report_dir
        / "evidence_apply_report.json",
        report,
    )

    save_json(
        report_dir
        / "added.json",
        added,
    )

    save_json(
        report_dir
        / "replaced.json",
        replaced,
    )

    # ========================================================
    # MASTER DB SCHEMA DESCRIPTION
    # ========================================================

    schema = {

        "version":
            "1.0",

        "description":
            (
                "Golf Master DB field confidence model"
            ),

        "layers": {

            "confirmed_fields": {

                "description":
                    (
                        "catalog 최상위 필드. "
                        "서비스에서 사실정보로 사용."
                    ),

                "examples": [
                    "address",
                    "phone",
                    "holes",
                    "operation_type",
                    "official_url",
                    "booking_url",
                    "courses",
                ],
            },

            "verified_basic_info": {

                "description":
                    (
                        "A급 검증정보와 "
                        "출처/검증시점 기록."
                    ),

                "display_rule":
                    "확정정보",
            },

            "evidence": {

                "description":
                    (
                        "B급 참고정보. "
                        "확정값이 아니며 자동 적용 금지."
                    ),

                "display_rule":
                    (
                        "참고정보 또는 "
                        "추가 확인 필요"
                    ),
            },

            "public_data": {

                "location":
                    "verification.public_data",

                "description":
                    (
                        "행정안전부 생활 골프장 "
                        "공공데이터 매칭 결과"
                    ),
            },

            "kga": {

                "description":
                    (
                        "대한골프협회 "
                        "Course Rating / "
                        "Slope Rating 및 "
                        "코스 관련 정보"
                    ),
            },
        },

        "service_priority": [

            "verified_basic_info",

            "confirmed catalog field",

            "evidence",

            "public_data",

            "KGA",

        ],

        "important_rule":
            (
                "evidence 값은 confirmed field를 "
                "자동 덮어쓰지 않는다."
            ),
    }

    save_json(
        report_dir
        / "master_db_schema.json",
        schema,
    )

    # ========================================================
    # CONSOLE
    # ========================================================

    print()

    print(
        "=" * 78
    )

    print(
        "MASTER EVIDENCE BUILD COMPLETE"
    )

    print(
        "=" * 78
    )

    print()

    print(
        "입력 Evidence:",
        len(evidence_rows)
    )

    print(
        "신규 저장:",
        len(added)
    )

    print(
        "기존 Evidence 교체:",
        len(replaced)
    )

    print(
        "이미 동일:",
        len(unchanged)
    )

    print()

    print(
        "Evidence가 들어간 골프장:",
        len(
            clubs_with_evidence
        )
    )

    print()

    print(
        "[필드별 입력]"
    )

    for field in sorted(
        field_counts
    ):

        print(
            f"  {field}: "
            f"{field_counts[field]}"
        )

    print()

    print(
        "최종 catalog:",
        len(reloaded)
    )

    print(
        "catalog 내 전체 Evidence 필드:",
        stored_count
    )

    print(
        "Evidence 보유 골프장:",
        stored_clubs
    )

    print()

    print(
        "Tavily 호출: 0"
    )

    print(
        "LLM 호출: 0"
    )

    print()

    print(
        "백업:"
    )

    print(
        backup_path
    )

    print()

    print(
        "보고서:"
    )

    print(
        report_dir
        / "evidence_apply_report.json"
    )

    print()

    print(
        "Master DB 스키마:"
    )

    print(
        report_dir
        / "master_db_schema.json"
    )


if __name__ == "__main__":

    main()