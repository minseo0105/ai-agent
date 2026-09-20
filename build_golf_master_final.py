# -*- coding: utf-8 -*-

"""
Golf Master DB Final Builder
-----------------------------------------
- 추가 Tavily 호출 없음
- 추가 LLM 조사 없음
- catalog.json 수정 없음
- 기존 catalog + 기존 Master DB +
  최신 play_facility_verifier_v2 결과 통합
- UNKNOWN은 False로 처리하지 않음

출력:
data/golf/master/golf_master.json
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent

CATALOG = ROOT / "data" / "golf" / "catalog.json"
MASTER = ROOT / "data" / "golf" / "master" / "golf_master.json"

VERIFIER_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "play_facility_verifier_v2"
)

EXPECTED_COUNT = 553


FIELDS = (
    "two_person",
    "three_person",
    "nine_hole_twice",
    "night_round",
    "par3",
    "driving_range",
)


# ---------------------------------------------------------
# 기본 함수
# ---------------------------------------------------------

def load_json(path):

    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def save_json(path, data):

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


def sha256(path):

    h = hashlib.sha256()

    with path.open("rb") as f:

        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def get_clubs(data):

    if isinstance(data, list):
        return data

    return (
        data.get("clubs")
        or data.get("records")
        or data.get("data")
        or []
    )


# ---------------------------------------------------------
# 최신 Verifier 결과 자동 탐색
# ---------------------------------------------------------

def find_latest_verifier():

    if not VERIFIER_ROOT.exists():

        raise FileNotFoundError(
            "play_facility_verifier_v2 "
            "결과 폴더가 없습니다."
        )

    candidates = []

    for folder in VERIFIER_ROOT.iterdir():

        if not folder.is_dir():
            continue

        result = (
            folder
            / "verifier_result.json"
        )

        if result.exists():

            candidates.append(
                result
            )

    if not candidates:

        raise FileNotFoundError(
            "verifier_result.json을 "
            "찾지 못했습니다."
        )

    return max(
        candidates,
        key=lambda p: p.stat().st_mtime,
    )


# ---------------------------------------------------------
# 조건 설명 일부 보존
# ---------------------------------------------------------

def make_condition_notes(evidence):

    notes = []

    for item in evidence[:3]:

        text = " ".join(
            str(
                item.get(k)
                or ""
            )
            for k in (
                "title",
                "snippet",
            )
        )

        text = " ".join(
            text.split()
        )

        if text:

            notes.append(
                text[:500]
            )

    return notes


# ---------------------------------------------------------
# Master DB 생성
# ---------------------------------------------------------

def main():

    print(
        "=" * 72
    )

    print(
        "Golf Master DB Final Builder"
    )

    print(
        "=" * 72
    )

    # -----------------------------------------------------
    # catalog 안전 확인
    # -----------------------------------------------------

    if not CATALOG.exists():

        raise FileNotFoundError(
            CATALOG
        )

    catalog_hash_before = (
        sha256(CATALOG)
    )

    catalog_data = (
        load_json(CATALOG)
    )

    catalog = (
        get_clubs(
            catalog_data
        )
    )

    if len(catalog) != EXPECTED_COUNT:

        raise RuntimeError(
            "안전 중단: "
            f"catalog={len(catalog)}, "
            f"expected={EXPECTED_COUNT}"
        )

    # -----------------------------------------------------
    # 기존 Master DB 읽기
    # -----------------------------------------------------

    if MASTER.exists():

        old_master_data = (
            load_json(MASTER)
        )

        old_master = (
            get_clubs(
                old_master_data
            )
        )

    else:

        old_master = []

    old_by_id = {

        str(
            item.get("id")
            or ""
        ):
        item

        for item
        in old_master
    }

    # -----------------------------------------------------
    # 최신 이용조건 검증자료
    # -----------------------------------------------------

    verifier_path = (
        find_latest_verifier()
    )

    print(
        "Verifier:"
    )

    print(
        verifier_path
    )

    verifier_data = (
        load_json(
            verifier_path
        )
    )

    verifier_by_id = {

        str(
            item.get("id")
            or ""
        ):
        item

        for item
        in verifier_data.get(
            "records",
            []
        )
    }

    # -----------------------------------------------------
    # 기존 Master DB 백업
    # -----------------------------------------------------

    stamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    backup = None

    if MASTER.exists():

        backup = (
            MASTER.parent
            / "backups"
            / (
                "golf_master_before_final_"
                + stamp
                + ".json"
            )
        )

        backup.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            MASTER,
            backup,
        )

    # -----------------------------------------------------
    # 통계
    # -----------------------------------------------------

    stats = {

        field: {
            "confirmed": 0,
            "conditional": 0,
            "unavailable": 0,
            "needs_check": 0,
        }

        for field
        in FIELDS
    }

    master_clubs = []

    # -----------------------------------------------------
    # 553개 통합
    # -----------------------------------------------------

    for club in catalog:

        cid = str(
            club.get("id")
            or ""
        )

        previous = (
            old_by_id.get(
                cid,
                {}
            )
        )

        # 기존 Master 정보 보존
        record = dict(
            previous
        )

        record["id"] = cid

        record["name"] = (
            club.get("name")
            or previous.get("name")
        )

        # -------------------------------------------------
        # 원본 catalog 보존
        # -------------------------------------------------

        record["catalog"] = club

        # -------------------------------------------------
        # 서비스에서 쉽게 쓰는 기본정보
        # -------------------------------------------------

        record["basic"] = {

            "area":
                club.get("area")
                or club.get("region"),

            "city":
                club.get("city"),

            "address":
                club.get("address")
                or club.get("road_address")
                or club.get("lot_address"),

            "phone":
                club.get("phone"),

            "operation_type":
                club.get("operation_type"),

            "holes":
                club.get("holes"),

            "courses":
                club.get("courses"),

            "official_url":
                club.get("official_url"),

            "booking_url":
                club.get("booking_url"),
        }

        # -------------------------------------------------
        # KGA
        # -------------------------------------------------

        record["kga"] = (
            club.get("kga")
            or previous.get("kga")
            or {}
        )

        # -------------------------------------------------
        # 기존 Evidence
        # -------------------------------------------------

        record["evidence"] = (
            club.get("evidence")
            or previous.get("evidence")
            or {}
        )

        # -------------------------------------------------
        # 이용조건
        # -------------------------------------------------

        verifier_record = (
            verifier_by_id.get(
                cid,
                {}
            )
        )

        play_facility = {}

        for field in FIELDS:

            verified = (
                verifier_record
                .get(
                    "fields",
                    {}
                )
                .get(
                    field,
                    {}
                )
            )

            classification = (
                verified.get("class")
                or "UNKNOWN"
            )

            evidence = (
                verified.get("evidence")
                or []
            )

            # ---------------------------------------------
            # 실제 서비스 상태 변환
            # ---------------------------------------------

            if classification in (
                "VERIFIED_CANDIDATE",
                "SUPPORTED_B",
            ):

                status = (
                    "confirmed"
                )

            elif classification == (
                "CONDITIONAL"
            ):

                status = (
                    "conditional"
                )

            elif classification == (
                "NEGATIVE_CANDIDATE"
            ):

                status = (
                    "unavailable"
                )

            else:

                # REFERENCE_ONLY
                # CONTAMINATED_HOLD
                # UNKNOWN
                #
                # 모두 False가 아니라 확인 필요
                status = (
                    "needs_check"
                )

            stats[
                field
            ][
                status
            ] += 1

            sources = []

            for item in evidence[:5]:

                url = (
                    item.get("url")
                )

                if not url:
                    continue

                sources.append(
                    {
                        "title":
                            item.get(
                                "title"
                            ),

                        "url":
                            url,

                        "domain":
                            item.get(
                                "domain"
                            ),
                    }
                )

            play_facility[
                field
            ] = {

                "status":
                    status,

                "verification_class":
                    classification,

                "condition_notes":
                    (
                        make_condition_notes(
                            evidence
                        )
                        if status in (
                            "conditional",
                            "unavailable",
                        )
                        else []
                    ),

                "sources":
                    sources,

                "checked_at":
                    verifier_record.get(
                        "checked_at"
                    ),

                "source":
                    "existing_web_evidence",
            }

        record[
            "play_facility"
        ] = play_facility

        # -------------------------------------------------
        # Master 메타정보
        # -------------------------------------------------

        record[
            "master_meta"
        ] = {

            "built_at":
                datetime.now()
                .astimezone()
                .isoformat(
                    timespec="seconds"
                ),

            "play_verifier_source":
                str(
                    verifier_path
                ),

            "additional_tavily":
                False,

            "additional_llm_research":
                False,

            "unknown_is_false":
                False,
        }

        master_clubs.append(
            record
        )

    # -----------------------------------------------------
    # 최종 Master 구조
    # -----------------------------------------------------

    master_payload = {

        "schema_version":
            "final-1.0",

        "built_at":
            datetime.now()
            .astimezone()
            .isoformat(
                timespec="seconds"
            ),

        "count":
            len(master_clubs),

        "policy": {

            "additional_tavily":
                False,

            "additional_llm_research":
                False,

            "unknown_is_false":
                False,

            "search_groups": [
                "조건 확인됨",
                "정보 확인 필요",
            ],
        },

        "clubs":
            master_clubs,
    }

    # -----------------------------------------------------
    # Master 저장
    # -----------------------------------------------------

    save_json(
        MASTER,
        master_payload,
    )

    # -----------------------------------------------------
    # catalog 안전검사
    # -----------------------------------------------------

    catalog_hash_after = (
        sha256(
            CATALOG
        )
    )

    if (
        catalog_hash_before
        != catalog_hash_after
    ):

        raise RuntimeError(
            "catalog.json 변경 감지!"
        )

    # -----------------------------------------------------
    # 보고서
    # -----------------------------------------------------

    report_path = (

        MASTER.parent
        / (
            "golf_master_final_report_"
            + stamp
            + ".json"
        )
    )

    report = {

        "count":
            len(master_clubs),

        "verifier":
            str(
                verifier_path
            ),

        "backup":
            (
                str(backup)
                if backup
                else None
            ),

        "additional_tavily":
            0,

        "additional_llm":
            0,

        "catalog_unchanged":
            True,

        "stats":
            stats,
    }

    save_json(
        report_path,
        report,
    )

    # -----------------------------------------------------
    # 결과 출력
    # -----------------------------------------------------

    print()

    print(
        "골프장:",
        len(master_clubs),
    )

    print(
        "추가 Tavily:",
        0,
    )

    print(
        "추가 LLM:",
        0,
    )

    print(
        "catalog.json 수정:",
        False,
    )

    print()

    for field, value in stats.items():

        print(
            field,
            value,
        )

    print()

    print(
        "Master DB:"
    )

    print(
        MASTER
    )

    print()

    print(
        "backup:"
    )

    print(
        backup
    )

    print()

    print(
        "report:"
    )

    print(
        report_path
    )

    print()

    print(
        "=" * 72
    )

    print(
        "Master DB 통합 완료"
    )

    print(
        "=" * 72
    )


if __name__ == "__main__":

    main()