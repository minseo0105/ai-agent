from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


# ============================================================
# 기본 설정
# ============================================================

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "data" / "golf" / "catalog.json"

REPORT_DIR = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "verified_apply"
)

# 이번 단계는 무조건 DRY RUN입니다.
# catalog.json을 수정하는 코드는 넣지 않았습니다.
MODE = "DRY_RUN"


# ============================================================
# 이번 1차 검증에서 반영 후보로 인정한 값
#
# 중요:
# - 라비에벨
# - 레이크사이드
# - 블랙스톤 이천
# - 사우스스프링스
#
# 위 4곳은 이번 반영 대상에서 제외했습니다.
# ============================================================

PATCHES = [

    # --------------------------------------------------------
    # 88CC
    # --------------------------------------------------------
    {
        "label": "88CC",
        "names": [
            "88CC",
            "88컨트리클럽",
            "88 C.C",
            "88 C.C.",
            "88CountryClub",
        ],
        "fields": {
            "official_url": {
                "value": "https://www.88countryclub.co.kr/",
                "source_type": "official_operator",
                "confidence": "A",
            },
            "booking_url": {
                "value": "https://88countryclub.co.kr/Reservation/Reservation.aspx",
                "source_type": "official_operator",
                "confidence": "A",
            },
        },
    },

    # --------------------------------------------------------
    # 레인보우힐스
    # --------------------------------------------------------
    {
        "label": "레인보우힐스CC",
        "names": [
            "레인보우힐스CC",
            "레인보우힐스",
            "레인보우힐스컨트리클럽",
            "Rainbow Hills",
            "RainbowHills",
        ],
        "fields": {
            "holes": {
                "value": 27,
                "source_type": "official_operator",
                "confidence": "A",
            },
        },
    },

    # --------------------------------------------------------
    # 블루헤런
    # --------------------------------------------------------
    {
        "label": "블루헤런GC",
        "names": [
            "블루헤런GC",
            "블루헤런",
            "블루헤런골프클럽",
            "Blue Heron",
            "BlueHeron",
        ],
        "fields": {
            "holes": {
                "value": 18,
                "source_type": "official_operator",
                "confidence": "A",
            },
            "courses": {
                "value": [
                    "West",
                    "East",
                ],
                "source_type": "official_operator",
                "confidence": "A",
            },
            "official_url": {
                "value": "https://blueheron.co.kr/",
                "source_type": "official_operator",
                "confidence": "A",
            },
            "booking_url": {
                "value": "https://blueheron.co.kr/reservation/golf",
                "source_type": "official_operator",
                "confidence": "A",
            },
        },
    },

    # --------------------------------------------------------
    # 청주 세레니티
    # --------------------------------------------------------
    {
        "label": "청주 세레니티",
        "names": [
            "청주 세레니티",
            "세레니티CC",
            "세레니티",
            "세레니티 골프앤리조트 청주",
            "세레니티골프앤리조트",
            "Serenity",
        ],
        "fields": {
            "holes": {
                "value": 27,
                "source_type": "official_operator",
                "confidence": "A",
            },
            "courses": {
                "value": [
                    "Silk",
                    "River",
                    "Blue",
                ],
                "source_type": "official_operator",
                "confidence": "A",
            },
            "official_url": {
                "value": "https://www.serenitygolfresort.com/cheongju/",
                "source_type": "official_operator",
                "confidence": "A",
            },
        },
    },

    # --------------------------------------------------------
    # 클럽72
    # --------------------------------------------------------
    {
        "label": "클럽72",
        "names": [
            "클럽72",
            "클럽72CC",
            "클럽72 골프클럽",
            "CLUB72",
            "Club72",
        ],
        "fields": {
            "operation_type": {
                "value": "대중제",
                "source_type": "official_operator",
                "confidence": "A",
            },
            "holes": {
                "value": 72,
                "source_type": "official_operator",
                "confidence": "A",
            },
            "courses": {
                "value": [
                    "하늘",
                    "오션",
                    "레이크",
                    "클래식",
                ],
                "source_type": "official_operator",
                "confidence": "A",
            },
        },
    },

    # --------------------------------------------------------
    # 클럽디 더플레이어스
    # --------------------------------------------------------
    {
        "label": "클럽디 더플레이어스",
        "names": [
            "클럽디 더플레이어스",
            "클럽디 더 플레이어스",
            "더플레이어스GC",
            "더플레이어스 골프클럽",
            "ClubD The Players",
            "The Players",
        ],
        "fields": {
            "operation_type": {
                "value": "대중제",
                "source_type": "official_operator",
                "confidence": "A",
            },
            "holes": {
                "value": 27,
                "source_type": "official_operator",
                "confidence": "A",
            },
            "courses": {
                "value": [
                    "Valley",
                    "Lake",
                    "Mountain",
                ],
                "source_type": "official_operator",
                "confidence": "A",
            },
            "official_url": {
                "value": "https://www.clubd.com/theplayers/",
                "source_type": "official_operator",
                "confidence": "A",
            },
        },
    },
]


# ============================================================
# 문자열 정규화
# ============================================================

def normalize_name(value):
    value = str(value or "").casefold()

    return re.sub(
        r"[^0-9a-z가-힣]+",
        "",
        value,
    )


# ============================================================
# 골프장의 이름 + alias 가져오기
# ============================================================

def get_all_names(club):

    names = []

    if club.get("name"):
        names.append(club["name"])

    aliases = club.get("aliases") or []

    if isinstance(aliases, list):
        names.extend(aliases)

    return names


# ============================================================
# PATCH 대상 골프장 찾기
#
# 정확한 이름/alias 정규화 일치만 허용합니다.
# fuzzy match는 사용하지 않습니다.
# ============================================================

def find_matches(catalog, target_names):

    targets = {
        normalize_name(name)
        for name in target_names
        if name
    }

    matches = []

    for club in catalog:

        existing_names = {
            normalize_name(name)
            for name in get_all_names(club)
            if name
        }

        if targets.intersection(existing_names):
            matches.append(club)

    return matches


# ============================================================
# 값 비교
# ============================================================

def values_equal(old, new):

    if isinstance(old, list) and isinstance(new, list):

        old_norm = [
            normalize_name(x)
            for x in old
        ]

        new_norm = [
            normalize_name(x)
            for x in new
        ]

        return old_norm == new_norm

    return old == new


# ============================================================
# 빈 값 판단
# ============================================================

def is_empty(value):

    return value in (
        None,
        "",
        [],
        {},
    )


# ============================================================
# 메인
# ============================================================

def main():

    print()
    print("=" * 70)
    print("Golf Master DB - VERIFIED PILOT")
    print("MODE:", MODE)
    print("=" * 70)
    print()

    # --------------------------------------------------------
    # catalog 존재 확인
    # --------------------------------------------------------

    if not CATALOG_PATH.exists():

        print("ERROR")
        print("catalog.json을 찾을 수 없습니다.")
        print()
        print("예상 위치:")
        print(CATALOG_PATH)

        return


    # --------------------------------------------------------
    # catalog 읽기
    # --------------------------------------------------------

    raw_before = CATALOG_PATH.read_bytes()

    try:

        catalog = json.loads(
            raw_before.decode("utf-8-sig")
        )

    except Exception as exc:

        print("catalog.json 읽기 실패")
        print(exc)

        return


    if not isinstance(catalog, list):

        print("ERROR")
        print("catalog.json 최상위 구조가 list가 아닙니다.")

        return


    print("전체 catalog:", len(catalog), "개")
    print()


    # --------------------------------------------------------
    # 결과
    # --------------------------------------------------------

    changes = []
    already_same = []
    conflicts = []
    not_found = []
    multiple_matches = []


    # --------------------------------------------------------
    # PATCH별 검사
    # --------------------------------------------------------

    for patch in PATCHES:

        label = patch["label"]

        matches = find_matches(
            catalog,
            patch["names"],
        )

        print("-" * 70)
        print("검사:", label)


        # ----------------------------------------------------
        # 못 찾음
        # ----------------------------------------------------

        if len(matches) == 0:

            print("  [NOT FOUND] catalog에서 정확히 일치하는 이름을 찾지 못했습니다.")

            not_found.append({
                "label": label,
                "target_names": patch["names"],
            })

            continue


        # ----------------------------------------------------
        # 여러 개 찾음
        # ----------------------------------------------------

        if len(matches) > 1:

            names = [
                x.get("name")
                for x in matches
            ]

            print(
                "  [HOLD] 여러 골프장이 동시에 일치:",
                names,
            )

            multiple_matches.append({
                "label": label,
                "matches": names,
            })

            continue


        # ----------------------------------------------------
        # 정확히 한 개
        # ----------------------------------------------------

        club = matches[0]

        print(
            "  catalog:",
            club.get("name"),
        )

        print(
            "  id:",
            club.get("id"),
        )


        # ----------------------------------------------------
        # 필드 비교
        # ----------------------------------------------------

        for field, info in patch["fields"].items():

            proposed = info["value"]

            current = club.get(field)


            # ------------------------------------------------
            # 이미 동일
            # ------------------------------------------------

            if values_equal(
                current,
                proposed,
            ):

                print(
                    f"  [SAME] {field}:",
                    current,
                )

                already_same.append({
                    "club": club.get("name"),
                    "id": club.get("id"),
                    "field": field,
                    "value": current,
                })

                continue


            # ------------------------------------------------
            # 현재 값이 비어 있음
            # → 안전 반영 후보
            # ------------------------------------------------

            if is_empty(current):

                print(
                    f"  [CHANGE] {field}:",
                    current,
                    "→",
                    proposed,
                )

                changes.append({
                    "club": club.get("name"),
                    "id": club.get("id"),
                    "field": field,
                    "old": current,
                    "new": proposed,
                    "source_type": info["source_type"],
                    "confidence": info["confidence"],
                })

                continue


            # ------------------------------------------------
            # 현재 값이 이미 있는데 다름
            # → 자동 덮어쓰기 금지
            # ------------------------------------------------

            print(
                f"  [HOLD] {field}:",
                current,
                "≠",
                proposed,
            )

            conflicts.append({
                "club": club.get("name"),
                "id": club.get("id"),
                "field": field,
                "existing": current,
                "proposed": proposed,
                "source_type": info["source_type"],
                "confidence": info["confidence"],
                "reason": "existing_nonempty_conflict",
            })


    # ========================================================
    # catalog 불변 검증
    # ========================================================

    raw_after = CATALOG_PATH.read_bytes()

    catalog_unchanged = (
        raw_before == raw_after
    )


    # ========================================================
    # 리포트 저장
    # ========================================================

    checked_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    report = {

        "mode": MODE,

        "checked_at": checked_at,

        "catalog_count": len(catalog),

        "catalog_unchanged": catalog_unchanged,

        "summary": {
            "change_candidates": len(changes),
            "already_same": len(already_same),
            "conflicts": len(conflicts),
            "not_found": len(not_found),
            "multiple_matches": len(multiple_matches),
        },

        "change_candidates": changes,

        "already_same": already_same,

        "conflicts": conflicts,

        "not_found": not_found,

        "multiple_matches": multiple_matches,
    }


    report_path = (
        REPORT_DIR
        / f"{stamp}_dryrun.json"
    )

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


    # ========================================================
    # 최종 출력
    # ========================================================

    print()
    print("=" * 70)
    print("DRY RUN 결과")
    print("=" * 70)

    print(
        "변경 후보:",
        len(changes),
        "건",
    )

    print(
        "이미 동일:",
        len(already_same),
        "건",
    )

    print(
        "충돌/보류:",
        len(conflicts),
        "건",
    )

    print(
        "골프장 못 찾음:",
        len(not_found),
        "곳",
    )

    print(
        "다중 일치:",
        len(multiple_matches),
        "곳",
    )

    print()

    print(
        "catalog.json 변경 여부:",
        not catalog_unchanged,
    )

    print()

    print(
        "리포트:",
        report_path,
    )

    print()

    if catalog_unchanged:

        print(
            "정상: catalog.json은 수정되지 않았습니다."
        )

    else:

        print(
            "WARNING: catalog.json 변경이 감지되었습니다."
        )

    print()
    print("=" * 70)
    print("IMPORTANT")
    print("=" * 70)

    print(
        "아직 실제 반영하지 마세요."
    )

    print(
        "위 결과 전체를 ChatGPT에 그대로 보내주세요."
    )

    print()


if __name__ == "__main__":
    main()