from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


# ============================================================
# Golf Master DB
# 검증 완료 3개 필드만 실제 반영
#
# 1. 88컨트리클럽 booking_url
# 2. 블루헤런GC booking_url
# 3. 클럽72 operation_type
#
# 그 외 필드는 절대 수정하지 않음
# ============================================================


ROOT = Path(__file__).resolve().parent

CATALOG_PATH = (
    ROOT
    / "data"
    / "golf"
    / "catalog.json"
)

BACKUP_DIR = (
    ROOT
    / "data"
    / "golf"
    / "backups"
)

REPORT_DIR = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "verified_apply"
)


# ============================================================
# 이번에 실제 반영할 값
#
# ID까지 고정합니다.
# 이름 검색이나 fuzzy match를 하지 않습니다.
# ============================================================

PATCHES = [

    {
        "id": "88cc",
        "expected_name": "88컨트리클럽",
        "field": "booking_url",
        "value": (
            "https://88countryclub.co.kr/"
            "Reservation/Reservation.aspx"
        ),
        "source_type": "official_operator",
        "confidence": "A",
    },

    {
        "id": "blueheron",
        "expected_name": "블루헤런GC",
        "field": "booking_url",
        "value": (
            "https://blueheron.co.kr/"
            "reservation/golf"
        ),
        "source_type": "official_operator",
        "confidence": "A",
    },

    {
        "id": "club72",
        "expected_name": "클럽72",
        "field": "operation_type",
        "value": "대중제",
        "source_type": "official_operator",
        "confidence": "A",
    },
]


# ============================================================
# 수정 가능한 필드 자체를 제한
# ============================================================

ALLOWED_FIELDS = {
    "booking_url",
    "operation_type",
}


# ============================================================
# JSON 안전 저장
#
# 기존 catalog에 바로 덮어쓰지 않고
# 임시파일 저장 성공 후 교체합니다.
# ============================================================

def atomic_write_json(path: Path, data):

    fd, temp_path = tempfile.mkstemp(
        prefix="catalog_",
        suffix=".tmp",
        dir=str(path.parent),
    )

    try:

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
            )

            f.write("\n")

        os.replace(
            temp_path,
            path,
        )

    except Exception:

        try:
            os.unlink(temp_path)
        except OSError:
            pass

        raise


# ============================================================
# ID로 골프장 찾기
# ============================================================

def find_by_id(catalog, club_id):

    matches = [
        club
        for club in catalog
        if club.get("id") == club_id
    ]

    return matches


# ============================================================
# 메인
# ============================================================

def main():

    print()
    print("=" * 72)
    print("Golf Master DB - VERIFIED 3 FIELD APPLY")
    print("=" * 72)
    print()


    # --------------------------------------------------------
    # 1. catalog 존재 확인
    # --------------------------------------------------------

    if not CATALOG_PATH.exists():

        raise RuntimeError(
            f"catalog.json을 찾을 수 없습니다.\n"
            f"{CATALOG_PATH}"
        )


    # --------------------------------------------------------
    # 2. 원본 읽기
    # --------------------------------------------------------

    original_bytes = (
        CATALOG_PATH.read_bytes()
    )

    try:

        catalog = json.loads(
            original_bytes.decode("utf-8-sig")
        )

    except Exception as exc:

        raise RuntimeError(
            f"catalog.json 읽기 실패: {exc}"
        )


    if not isinstance(catalog, list):

        raise RuntimeError(
            "catalog.json 최상위 구조가 list가 아닙니다."
        )


    original_count = len(catalog)

    print(
        "현재 catalog:",
        original_count,
        "개",
    )


    # --------------------------------------------------------
    # 3. 반드시 555개인지 확인
    #
    # 현재 우리가 검증한 catalog가 555개였기 때문에
    # 다른 파일에서 실행하는 실수를 방지합니다.
    # --------------------------------------------------------

    if original_count != 555:

        raise RuntimeError(
            "안전 중단: catalog 개수가 "
            f"555개가 아닙니다. 현재 {original_count}개"
        )


    # --------------------------------------------------------
    # 4. 수정 대상 사전 검증
    #
    # 아직 아무것도 수정하지 않습니다.
    # --------------------------------------------------------

    targets = []

    for patch in PATCHES:

        field = patch["field"]

        if field not in ALLOWED_FIELDS:

            raise RuntimeError(
                f"허용되지 않은 필드: {field}"
            )


        matches = find_by_id(
            catalog,
            patch["id"],
        )


        if len(matches) != 1:

            raise RuntimeError(
                "안전 중단: "
                f"{patch['id']} ID가 "
                f"{len(matches)}개 검색되었습니다."
            )


        club = matches[0]


        # 이름까지 확인
        if (
            club.get("name")
            != patch["expected_name"]
        ):

            raise RuntimeError(
                "안전 중단: ID와 골프장 이름이 "
                "예상과 다릅니다.\n"
                f"ID: {patch['id']}\n"
                f"예상: {patch['expected_name']}\n"
                f"실제: {club.get('name')}"
            )


        current = club.get(field)


        # ----------------------------------------------------
        # 기존 값이 있는데 새 값과 다르면 중단
        #
        # 자동 덮어쓰기 금지
        # ----------------------------------------------------

        if (
            current not in (
                None,
                "",
                [],
                {},
            )
            and current != patch["value"]
        ):

            raise RuntimeError(
                "안전 중단: 기존 값과 충돌합니다.\n"
                f"골프장: {club.get('name')}\n"
                f"필드: {field}\n"
                f"기존값: {current}\n"
                f"새 값: {patch['value']}"
            )


        targets.append(
            (
                club,
                patch,
                current,
            )
        )


    print()
    print("사전 검증 완료")
    print("수정 대상 필드:", len(targets), "개")
    print()


    for club, patch, current in targets:

        print(
            f"[READY] "
            f"{club['name']} | "
            f"{patch['field']} | "
            f"{current} → {patch['value']}"
        )


    # --------------------------------------------------------
    # 5. 백업
    # --------------------------------------------------------

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_path = (
        BACKUP_DIR
        / (
            "catalog_before_verified_3fields_"
            f"{stamp}.json"
        )
    )


    shutil.copy2(
        CATALOG_PATH,
        backup_path,
    )


    if not backup_path.exists():

        raise RuntimeError(
            "백업 파일 생성 실패"
        )


    # 백업 내용까지 원본과 같은지 확인
    if (
        backup_path.read_bytes()
        != original_bytes
    ):

        raise RuntimeError(
            "백업 파일 검증 실패"
        )


    print()
    print(
        "백업 완료:",
        backup_path,
    )


    # --------------------------------------------------------
    # 6. 실제 값 반영
    # --------------------------------------------------------

    checked_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )


    applied = []


    for club, patch, current in targets:

        field = patch["field"]

        new_value = patch["value"]


        # 이미 동일하면 데이터 값은 건드리지 않음
        if current != new_value:

            club[field] = new_value


        # ----------------------------------------------------
        # 검증 메타데이터
        #
        # 기존 verification / public / KGA 등은
        # 전혀 건드리지 않고 별도 영역에 저장
        # ----------------------------------------------------

        verified = club.setdefault(
            "verified_basic_info",
            {}
        )

        verified_fields = (
            verified.setdefault(
                "fields",
                {}
            )
        )


        verified_fields[field] = {

            "value": new_value,

            "source_type": (
                patch["source_type"]
            ),

            "confidence": (
                patch["confidence"]
            ),

            "checked_at": checked_at,
        }


        verified["checked_at"] = (
            checked_at
        )


        applied.append({

            "id": club["id"],

            "name": club["name"],

            "field": field,

            "old": current,

            "new": new_value,

            "source_type": (
                patch["source_type"]
            ),

            "confidence": (
                patch["confidence"]
            ),
        })


    # --------------------------------------------------------
    # 7. 저장 직전 개수 검증
    # --------------------------------------------------------

    if len(catalog) != original_count:

        raise RuntimeError(
            "안전 중단: 저장 전 catalog 개수가 "
            "변경되었습니다."
        )


    # --------------------------------------------------------
    # 8. Atomic Write
    # --------------------------------------------------------

    try:

        atomic_write_json(
            CATALOG_PATH,
            catalog,
        )

    except Exception as exc:

        print()
        print("저장 실패")
        print("원본 백업은 유지되어 있습니다.")
        print(exc)

        raise


    # --------------------------------------------------------
    # 9. 저장 후 다시 읽어서 검증
    # --------------------------------------------------------

    verify_catalog = json.loads(
        CATALOG_PATH.read_text(
            encoding="utf-8-sig"
        )
    )


    if len(verify_catalog) != 555:

        # 문제가 생기면 즉시 백업 복원
        shutil.copy2(
            backup_path,
            CATALOG_PATH,
        )

        raise RuntimeError(
            "저장 후 catalog 개수 이상. "
            "백업으로 자동 복원했습니다."
        )


    # --------------------------------------------------------
    # 10. 세 값이 정확히 저장됐는지 검증
    # --------------------------------------------------------

    verification_results = []


    for patch in PATCHES:

        matches = find_by_id(
            verify_catalog,
            patch["id"],
        )


        if len(matches) != 1:

            shutil.copy2(
                backup_path,
                CATALOG_PATH,
            )

            raise RuntimeError(
                "저장 후 대상 골프장 검증 실패. "
                "백업으로 자동 복원했습니다."
            )


        club = matches[0]

        actual = club.get(
            patch["field"]
        )


        ok = (
            actual
            == patch["value"]
        )


        verification_results.append({

            "id": patch["id"],

            "name": club.get("name"),

            "field": patch["field"],

            "expected": patch["value"],

            "actual": actual,

            "ok": ok,
        })


        if not ok:

            shutil.copy2(
                backup_path,
                CATALOG_PATH,
            )

            raise RuntimeError(
                "저장값 검증 실패. "
                "백업으로 자동 복원했습니다."
            )


    # --------------------------------------------------------
    # 11. 결과 리포트 저장
    # --------------------------------------------------------

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    report = {

        "mode": "APPLY",

        "applied_at": checked_at,

        "catalog_count_before": (
            original_count
        ),

        "catalog_count_after": (
            len(verify_catalog)
        ),

        "backup": str(
            backup_path
        ),

        "applied": applied,

        "verification": (
            verification_results
        ),

        "success": True,
    }


    report_path = (
        REPORT_DIR
        / (
            f"{stamp}_3fields_apply.json"
        )
    )


    report_path.write_text(

        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),

        encoding="utf-8",
    )


    # --------------------------------------------------------
    # 12. 최종 출력
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("실제 반영 완료")
    print("=" * 72)
    print()


    for item in verification_results:

        print(
            "[OK]",
            item["name"],
            "|",
            item["field"],
            "=",
            item["actual"],
        )


    print()

    print(
        "catalog:",
        len(verify_catalog),
        "개 유지",
    )

    print(
        "백업:",
        backup_path,
    )

    print(
        "리포트:",
        report_path,
    )

    print()

    print(
        "SUCCESS: 검증된 3개 필드만 "
        "정상 반영되었습니다."
    )

    print()


if __name__ == "__main__":
    main()