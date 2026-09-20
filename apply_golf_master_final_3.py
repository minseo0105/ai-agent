# -*- coding: utf-8 -*-

"""
Golf Master - Final Verified Apply 3
=====================================

실제 반영:
1. 레이크사이드CC booking_url
2. 클럽디 더플레이어스 operation_type
3. 청주 세레니티 operation_type

안전장치:
- catalog 553개 확인
- 변경 전 자동 백업
- 대상 필드가 비어 있을 때만 신규 입력
- 기존 값이 다르면 자동 변경 금지
- verified_basic_info provenance 기록
- 원자적 저장
- 저장 후 553개 재확인
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent

CATALOG_PATH = (
    ROOT / "data" / "golf" / "catalog.json"
)

BACKUP_DIR = (
    ROOT / "data" / "golf" / "backups"
)

REPORT_DIR = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "final_verified_apply"
)

EXPECTED_COUNT = 553


APPLY_ITEMS = [
    {
        "id": "lakeside",
        "name": "레이크사이드CC",
        "field": "booking_url",
        "value": (
            "https://www.lakeside.kr/"
            "reservation/real_reservation.do"
        ),
        "source_name": "레이크사이드 컨트리클럽 공식 홈페이지",
        "source_url": (
            "https://www.lakeside.kr/"
            "reservation/real_reservation.do"
        ),
        "verification_method": "official_booking_link_verified",
        "confidence": "A",
        "note": (
            "공식 사이트의 예약하기 메뉴에서 확인. "
            "비로그인 접근 시 로그인 화면으로 연결됨."
        ),
    },
    {
        "id": "clubd_theplayers",
        "name": "클럽디 더플레이어스",
        "field": "operation_type",
        "value": "대중제",
        "source_name": "행정안전부 생활 골프장 공공데이터",
        "source_url": (
            "https://www.data.go.kr/data/15154978/openapi.do"
        ),
        "verification_method": "matched_public_data",
        "confidence": "A",
        "note": "공공데이터 비회원제 정보를 서비스 표준값 대중제로 정규화.",
    },
    {
        "id": "silkriver",
        "name": "청주 세레니티",
        "field": "operation_type",
        "value": "회원제",
        "source_name": "행정안전부 생활 골프장 공공데이터",
        "source_url": (
            "https://www.data.go.kr/data/15154978/openapi.do"
        ),
        "verification_method": "matched_public_data",
        "confidence": "A",
        "note": "공공데이터 회원제 정보와 동일.",
    },
]


def load_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def atomic_save(path: Path, data):
    temp_path = path.with_name(
        path.name + ".final_apply_tmp"
    )

    temp_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.replace(
        temp_path,
        path,
    )


def is_empty(value):
    if value is None:
        return True

    if isinstance(value, str):
        return value.strip().lower() in {
            "",
            "없음",
            "미확인",
            "확인 필요",
            "정보 없음",
            "none",
            "null",
            "unknown",
            "-",
        }

    return False


def main():

    print()
    print("=" * 78)
    print("Golf Master FINAL VERIFIED APPLY")
    print("=" * 78)

    if not CATALOG_PATH.exists():
        raise RuntimeError(
            f"catalog.json 없음: {CATALOG_PATH}"
        )

    catalog = load_json(
        CATALOG_PATH
    )

    if len(catalog) != EXPECTED_COUNT:
        raise RuntimeError(
            f"안전 중단: catalog={len(catalog)} / "
            f"expected={EXPECTED_COUNT}"
        )

    print(
        "현재 catalog:",
        len(catalog),
    )

    index = {
        str(c.get("id", "")).strip(): c
        for c in catalog
        if str(c.get("id", "")).strip()
    }

    # --------------------------------------------------------
    # 먼저 전부 검사
    # --------------------------------------------------------

    planned = []
    same = []
    conflicts = []
    missing = []

    for item in APPLY_ITEMS:

        club = index.get(
            item["id"]
        )

        if club is None:
            missing.append(item)
            continue

        current = club.get(
            item["field"]
        )

        if is_empty(current):
            planned.append(item)
            continue

        if str(current).strip() == str(
            item["value"]
        ).strip():
            same.append(item)
            continue

        conflicts.append(
            {
                **item,
                "current": current,
            }
        )

    print()
    print("[사전 검사]")
    print("신규 반영:", len(planned))
    print("이미 동일:", len(same))
    print("충돌:", len(conflicts))
    print("ID 없음:", len(missing))

    if conflicts:
        print()
        print("기존값 충돌이 있어 안전 중단합니다.")

        for x in conflicts:
            print(
                "-",
                x["name"],
                x["field"],
                "현재=",
                x["current"],
                "후보=",
                x["value"],
            )

        return

    if missing:
        print()
        print("골프장 ID를 찾지 못해 안전 중단합니다.")

        for x in missing:
            print(
                "-",
                x["id"],
                x["name"],
            )

        return

    # --------------------------------------------------------
    # BACKUP
    # --------------------------------------------------------

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup_path = (
        BACKUP_DIR
        / f"catalog_before_final_verified_apply_{stamp}.json"
    )

    shutil.copy2(
        CATALOG_PATH,
        backup_path,
    )

    print()
    print(
        "백업:",
        backup_path,
    )

    # --------------------------------------------------------
    # APPLY
    # --------------------------------------------------------

    checked_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    applied = []

    for item in planned:

        club = index[
            item["id"]
        ]

        field = item["field"]
        value = item["value"]

        club[field] = value

        verified = club.setdefault(
            "verified_basic_info",
            {},
        )

        verified[field] = {
            "value": value,
            "verified": True,
            "confidence": item["confidence"],
            "checked_at": checked_at,
            "source_name": item["source_name"],
            "source_url": item["source_url"],
            "verification_method": (
                item["verification_method"]
            ),
            "note": item["note"],
        }

        applied.append(
            {
                "id": item["id"],
                "name": item["name"],
                "field": field,
                "value": value,
                "checked_at": checked_at,
                "source_name": item["source_name"],
                "source_url": item["source_url"],
            }
        )

    # 동일값도 provenance가 없으면 보강
    metadata_added = []

    for item in same:

        club = index[
            item["id"]
        ]

        verified = club.setdefault(
            "verified_basic_info",
            {},
        )

        if item["field"] not in verified:

            verified[item["field"]] = {
                "value": item["value"],
                "verified": True,
                "confidence": item["confidence"],
                "checked_at": checked_at,
                "source_name": item["source_name"],
                "source_url": item["source_url"],
                "verification_method": (
                    item["verification_method"]
                ),
                "note": item["note"],
            }

            metadata_added.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "field": item["field"],
                }
            )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    atomic_save(
        CATALOG_PATH,
        catalog,
    )

    # --------------------------------------------------------
    # RELOAD VALIDATION
    # --------------------------------------------------------

    reloaded = load_json(
        CATALOG_PATH
    )

    if len(reloaded) != EXPECTED_COUNT:

        shutil.copy2(
            backup_path,
            CATALOG_PATH,
        )

        raise RuntimeError(
            "저장 후 catalog 개수 이상. "
            "백업으로 자동 복원했습니다."
        )

    reindex = {
        str(c.get("id", "")).strip(): c
        for c in reloaded
    }

    verification_failures = []

    for item in APPLY_ITEMS:

        club = reindex.get(
            item["id"]
        )

        if not club:
            verification_failures.append(
                {
                    "id": item["id"],
                    "reason": "club_missing",
                }
            )
            continue

        actual = club.get(
            item["field"]
        )

        if str(actual).strip() != str(
            item["value"]
        ).strip():

            verification_failures.append(
                {
                    "id": item["id"],
                    "field": item["field"],
                    "expected": item["value"],
                    "actual": actual,
                }
            )

    if verification_failures:

        shutil.copy2(
            backup_path,
            CATALOG_PATH,
        )

        raise RuntimeError(
            "저장 후 값 검증 실패. "
            "백업으로 자동 복원했습니다.\n"
            + json.dumps(
                verification_failures,
                ensure_ascii=False,
                indent=2,
            )
        )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    run_dir = (
        REPORT_DIR
        / stamp
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "created_at": checked_at,
        "catalog_count_before": EXPECTED_COUNT,
        "catalog_count_after": len(reloaded),
        "applied_count": len(applied),
        "already_same_count": len(same),
        "metadata_added_count": len(metadata_added),
        "conflict_count": 0,
        "missing_count": 0,
        "backup": str(backup_path),
        "applied": applied,
        "already_same": same,
        "metadata_added": metadata_added,
        "held_back": [
            {
                "id": "lavie",
                "name": "라비에벨CC",
                "field": "booking_url",
                "candidate": (
                    "https://www.lavieestbellegolfnresort.com/"
                    "dunescourse/pagesite/reservation/live.asp"
                ),
                "reason": (
                    "공식 도메인이지만 현재 페이지 내용을 "
                    "독립 검증하지 못해 보류"
                ),
            }
        ],
    }

    report_path = (
        run_dir
        / "final_apply_report.json"
    )

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 78)
    print("FINAL APPLY COMPLETE")
    print("=" * 78)

    print()
    print(
        "실제 신규 반영:",
        len(applied),
    )

    for x in applied:
        print(
            " +",
            x["name"],
            "/",
            x["field"],
            "=",
            x["value"],
        )

    print()
    print(
        "이미 동일:",
        len(same),
    )

    print(
        "검증 메타데이터 추가:",
        len(metadata_added),
    )

    print(
        "보류:",
        1,
        "(라비에벨 예약 URL)",
    )

    print()
    print(
        "최종 catalog:",
        len(reloaded),
    )

    print(
        "백업:",
        backup_path,
    )

    print(
        "보고서:",
        report_path,
    )


if __name__ == "__main__":
    main()