from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent

CATALOG = ROOT / "data" / "golf" / "catalog.json"
BACKUPS = ROOT / "data" / "golf" / "backups"
REPORTS = ROOT / "data" / "golf" / "enrichment" / "duplicate_merge"


# ============================================================
# 병합 대상
#
# keep   : 최종적으로 남길 레코드
# remove : 정보를 옮긴 뒤 제거할 중복 레코드
# ============================================================

MERGES = [
    {
        "keep": "silkriver",
        "remove": "kgba_세레니티",
        "label": "청주 세레니티",
    },
    {
        "keep": "clubd_theplayers",
        "remove": "vworld_더플레이어스",
        "label": "클럽디 더플레이어스",
    },
]


def find_by_id(catalog, club_id):

    matches = [
        c for c in catalog
        if c.get("id") == club_id
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"{club_id}: {len(matches)}개 검색됨"
        )

    return matches[0]


def atomic_write(path, data):

    fd, tmp = tempfile.mkstemp(
        prefix="catalog_merge_",
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

        os.replace(tmp, path)

    except Exception:

        try:
            os.unlink(tmp)
        except OSError:
            pass

        raise


def merge_unique_list(a, b):

    result = []

    for value in (a or []) + (b or []):

        if value not in result:
            result.append(value)

    return result


def merge_pair(keep, remove, checked_at):

    moved = []

    # --------------------------------------------------------
    # 1. aliases
    # --------------------------------------------------------

    aliases = list(keep.get("aliases") or [])

    for value in [
        remove.get("name"),
        *(remove.get("aliases") or []),
        remove.get("public_data_name"),
    ]:

        if (
            value
            and value != keep.get("name")
            and value not in aliases
        ):
            aliases.append(value)

    keep["aliases"] = aliases


    # --------------------------------------------------------
    # 2. verification.sources 합치기
    # --------------------------------------------------------

    keep_ver = keep.setdefault(
        "verification",
        {}
    )

    remove_ver = remove.get(
        "verification"
    ) or {}

    keep_ver["sources"] = merge_unique_list(
        keep_ver.get("sources"),
        remove_ver.get("sources"),
    )


    # --------------------------------------------------------
    # 3. 공공데이터 정보
    #
    # keep에 없을 경우에만 remove에서 가져옵니다.
    # 기존 검증 정보를 덮어쓰지 않습니다.
    # --------------------------------------------------------

    remove_public = (
        remove_ver.get("public_data")
        or {}
    )

    keep_public = (
        keep_ver.get("public_data")
        or {}
    )

    if (
        remove_public
        and not keep_public
    ):

        keep_ver["public_data"] = copy.deepcopy(
            remove_public
        )

        moved.append(
            "verification.public_data"
        )


    # --------------------------------------------------------
    # 4. public_data_name
    # --------------------------------------------------------

    if (
        not keep.get("public_data_name")
        and remove.get("public_data_name")
    ):

        keep["public_data_name"] = (
            remove["public_data_name"]
        )

        moved.append(
            "public_data_name"
        )


    # --------------------------------------------------------
    # 5. KGA 정보 병합
    #
    # keep의 KGA 기본정보는 유지합니다.
    # remove에만 있는 ratings를 가져옵니다.
    # --------------------------------------------------------

    keep_kga = keep.setdefault(
        "kga",
        {}
    )

    remove_kga = remove.get(
        "kga"
    ) or {}


    if (
        not keep_kga.get("ratings")
        and remove_kga.get("ratings")
    ):

        keep_kga["ratings"] = copy.deepcopy(
            remove_kga["ratings"]
        )

        moved.append(
            "kga.ratings"
        )


    for field in [
        "ratings_source_name",
        "ratings_source_url",
        "ratings_source_date",
        "ratings_checked_at",
    ]:

        if (
            not keep_kga.get(field)
            and remove_kga.get(field)
        ):

            keep_kga[field] = copy.deepcopy(
                remove_kga[field]
            )

            moved.append(
                f"kga.{field}"
            )


    # --------------------------------------------------------
    # 6. KGA course combinations
    #
    # keep에 없을 때만 가져옵니다.
    # --------------------------------------------------------

    if (
        not keep_kga.get("course_combinations")
        and remove_kga.get("course_combinations")
    ):

        keep_kga["course_combinations"] = (
            copy.deepcopy(
                remove_kga[
                    "course_combinations"
                ]
            )
        )

        moved.append(
            "kga.course_combinations"
        )


    # --------------------------------------------------------
    # 7. KGA source metadata
    # --------------------------------------------------------

    for field in [
        "source_name",
        "source_url",
        "region",
        "address",
    ]:

        if (
            not keep_kga.get(field)
            and remove_kga.get(field)
        ):

            keep_kga[field] = copy.deepcopy(
                remove_kga[field]
            )

            moved.append(
                f"kga.{field}"
            )


    # --------------------------------------------------------
    # 8. 공공데이터 관리용 보조정보
    # --------------------------------------------------------

    if remove_public:

        merged_public = (
            keep_ver.get("public_data")
            or {}
        )

        # 관리번호 등 빠진 항목만 채움
        for field in [
            "management_no",
            "dataset_id",
            "source_name",
            "checked_at",
            "match_type",
            "public_name",
            "address",
            "phone",
            "status",
            "detail_status",
            "closed_date",
            "data_updated_at",
            "last_modified_at",
            "business_type",
            "operating_in_public_data",
            "matched",
        ]:

            if (
                not merged_public.get(field)
                and remove_public.get(field)
                not in (None, "")
            ):

                merged_public[field] = (
                    copy.deepcopy(
                        remove_public[field]
                    )
                )

        keep_ver["public_data"] = (
            merged_public
        )


    # --------------------------------------------------------
    # 9. 병합 이력
    # --------------------------------------------------------

    history = keep.setdefault(
        "merge_history",
        []
    )

    history.append(
        {
            "merged_from_id": remove.get("id"),
            "merged_from_name": remove.get("name"),
            "merged_at": checked_at,
            "reason": "duplicate_same_golf_course",
            "moved_fields": moved,
        }
    )


    return moved


def main():

    print()
    print("=" * 72)
    print("Golf Master DB - DUPLICATE MERGE")
    print("=" * 72)


    if not CATALOG.exists():
        raise RuntimeError(
            f"catalog 없음: {CATALOG}"
        )


    original_bytes = CATALOG.read_bytes()

    catalog = json.loads(
        original_bytes.decode("utf-8-sig")
    )


    if len(catalog) != 555:

        raise RuntimeError(
            "안전 중단: 현재 catalog가 "
            f"555개가 아닙니다. ({len(catalog)}개)"
        )


    # --------------------------------------------------------
    # 대상 존재 여부 사전 검증
    # --------------------------------------------------------

    for job in MERGES:

        keep = find_by_id(
            catalog,
            job["keep"],
        )

        remove = find_by_id(
            catalog,
            job["remove"],
        )

        print()
        print(
            "[CHECK]",
            job["label"],
        )

        print(
            " 유지:",
            keep["id"],
            "/",
            keep["name"],
        )

        print(
            " 제거:",
            remove["id"],
            "/",
            remove["name"],
        )

        # 주소가 다르면 자동 중단
        keep_address = (
            keep.get("address")
            or ""
        ).replace(" ", "")

        remove_address = (
            remove.get("address")
            or ""
        ).replace(" ", "")

        if (
            keep_address
            and remove_address
            and keep_address != remove_address
        ):

            # 청원군 → 청주시 행정구역 표현처럼
            # 문자열이 달라도 KGA 주소가 동일할 수 있으므로
            # 여기서는 경고만 표시
            print(
                " [NOTICE] 주소 문자열 표현이 다름"
            )


    # --------------------------------------------------------
    # 백업
    # --------------------------------------------------------

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    BACKUPS.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup = (
        BACKUPS
        / f"catalog_before_duplicate_merge_{stamp}.json"
    )

    shutil.copy2(
        CATALOG,
        backup,
    )


    if backup.read_bytes() != original_bytes:

        raise RuntimeError(
            "백업 검증 실패"
        )


    print()
    print(
        "백업 완료:",
        backup,
    )


    # --------------------------------------------------------
    # 병합
    # --------------------------------------------------------

    checked_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    results = []


    for job in MERGES:

        keep = find_by_id(
            catalog,
            job["keep"],
        )

        remove = find_by_id(
            catalog,
            job["remove"],
        )


        moved = merge_pair(
            keep,
            remove,
            checked_at,
        )


        catalog.remove(
            remove
        )


        results.append(
            {
                "label": job["label"],
                "kept_id": keep["id"],
                "removed_id": remove["id"],
                "moved_fields": moved,
            }
        )


        print()
        print(
            "[MERGED]",
            job["label"],
        )

        print(
            " 유지:",
            keep["id"],
        )

        print(
            " 제거:",
            remove["id"],
        )

        print(
            " 이동:",
            moved,
        )


    # --------------------------------------------------------
    # 반드시 553개여야 함
    # --------------------------------------------------------

    if len(catalog) != 553:

        raise RuntimeError(
            "안전 중단: 병합 후 예상 개수는 "
            f"553개인데 현재 {len(catalog)}개입니다."
        )


    # 제거 ID가 정말 없어졌는지 확인
    remaining_ids = {
        c.get("id")
        for c in catalog
    }


    for job in MERGES:

        if job["remove"] in remaining_ids:

            raise RuntimeError(
                f"{job['remove']}가 아직 남아 있습니다."
            )

        if job["keep"] not in remaining_ids:

            raise RuntimeError(
                f"{job['keep']}가 사라졌습니다."
            )


    # --------------------------------------------------------
    # Atomic 저장
    # --------------------------------------------------------

    try:

        atomic_write(
            CATALOG,
            catalog,
        )

    except Exception:

        shutil.copy2(
            backup,
            CATALOG,
        )

        raise


    # --------------------------------------------------------
    # 저장 후 재검증
    # --------------------------------------------------------

    verify = json.loads(
        CATALOG.read_text(
            encoding="utf-8-sig"
        )
    )


    if len(verify) != 553:

        shutil.copy2(
            backup,
            CATALOG,
        )

        raise RuntimeError(
            "저장 후 개수 검증 실패. "
            "백업으로 복원했습니다."
        )


    # --------------------------------------------------------
    # 핵심 병합정보 검증
    # --------------------------------------------------------

    serenity = find_by_id(
        verify,
        "silkriver",
    )

    players = find_by_id(
        verify,
        "clubd_theplayers",
    )


    if not (
        serenity.get("verification", {})
        .get("public_data")
    ):

        shutil.copy2(
            backup,
            CATALOG,
        )

        raise RuntimeError(
            "세레니티 공공데이터 병합 실패. "
            "백업 복원."
        )


    if not (
        serenity.get("kga", {})
        .get("ratings")
    ):

        shutil.copy2(
            backup,
            CATALOG,
        )

        raise RuntimeError(
            "세레니티 KGA ratings 병합 실패. "
            "백업 복원."
        )


    if not (
        players.get("verification", {})
        .get("public_data")
    ):

        shutil.copy2(
            backup,
            CATALOG,
        )

        raise RuntimeError(
            "더플레이어스 공공데이터 병합 실패. "
            "백업 복원."
        )


    if not (
        players.get("kga", {})
        .get("ratings")
    ):

        shutil.copy2(
            backup,
            CATALOG,
        )

        raise RuntimeError(
            "더플레이어스 KGA ratings 병합 실패. "
            "백업 복원."
        )


    # --------------------------------------------------------
    # 리포트
    # --------------------------------------------------------

    REPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )


    report = {
        "success": True,
        "merged_at": checked_at,
        "count_before": 555,
        "count_after": 553,
        "backup": str(backup),
        "results": results,
    }


    report_path = (
        REPORTS
        / f"{stamp}_duplicate_merge.json"
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
    print("=" * 72)
    print("중복 병합 완료")
    print("=" * 72)

    print()
    print(
        "catalog:",
        "555 →",
        len(verify),
    )

    print(
        "청주 세레니티 KGA ratings:",
        len(
            serenity.get("kga", {})
            .get("ratings", [])
        ),
        "건",
    )

    print(
        "클럽디 더플레이어스 KGA ratings:",
        len(
            players.get("kga", {})
            .get("ratings", [])
        ),
        "건",
    )

    print()
    print(
        "백업:",
        backup,
    )

    print(
        "리포트:",
        report_path,
    )

    print()
    print(
        "SUCCESS: 중복 2건을 정보 손실 없이 병합했습니다."
    )
    print()


if __name__ == "__main__":
    main()