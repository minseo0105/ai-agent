# -*- coding: utf-8 -*-

import json
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "data" / "golf" / "catalog.json"
BACKUPS = ROOT / "data" / "golf" / "backups"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")


# ==========================================================
# 사람이 검토해서 확정한 값만 적는다.
# 검색 결과의 official_candidate / REVIEW_A 등은 사용하지 않는다.
# ==========================================================

APPROVED = {

    # 이전 단계에서 이미 별도 검증·적용했던 값
    "88cc": {
        "booking_url":
            "https://88countryclub.co.kr/Reservation/Reservation.aspx",
    },

    "blueheron": {
        "booking_url":
            "https://blueheron.co.kr/reservation/golf",
    },

    "club72": {
        "operation_type": "대중제",
    },

    # FIRST 50 재검토
    #
    # 설해원은 검색 결과에서 실제 설해원 공식 도메인
    # seolhaeone.com의 예약 경로가 확인됨.
    "kgba_설해원": {
        "official_url":
            "https://www.seolhaeone.com/home.do",

        "booking_url":
            "https://www.seolhaeone.com/mobile/reservation/golf-wait-day_new.do",
    },

    # 블랙밸리 역시 blackcc.co.kr 운영 도메인 확인.
    # 운영형태는 공공데이터와 기존값 충돌이 있으므로 넣지 않는다.
    "kgba_블랙밸리": {
        "official_url":
            "https://www.blackcc.co.kr/club/intro",
    },

    # 아크로는 검색 결과에서 골프장 자체 도메인이 확인된 값.
    # 단, 예약 페이지는 홈페이지 URL과 동일하게 넣지 않는다.
    "kgba_아크로": {
        "official_url":
            "http://www.acrogolf.co.kr",
    },
}


# ID가 과거 수집 과정에서 다를 가능성이 있는 항목은
# 이름으로도 찾을 수 있게 한다.
NAME_FALLBACK = {

    "88cc": ["88CC", "88cc"],

    "blueheron": [
        "블루헤런GC",
        "블루헤런",
        "BlueHeron",
    ],

    "club72": [
        "클럽72",
        "Club72",
    ],

    "kgba_설해원": [
        "설해원",
    ],

    "kgba_블랙밸리": [
        "블랙밸리",
    ],

    "kgba_아크로": [
        "아크로",
    ],
}


def load_json(path):

    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def save_json(path, data):

    temp = path.with_suffix(
        ".json.tmp"
    )

    temp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 저장 검증
    json.loads(
        temp.read_text(
            encoding="utf-8"
        )
    )

    temp.replace(path)


def get_clubs(data):

    if isinstance(data, list):
        return data

    if isinstance(data, dict):

        for key in (
            "clubs",
            "items",
            "data",
            "golf_courses",
        ):

            if isinstance(
                data.get(key),
                list,
            ):
                return data[key]

    raise RuntimeError(
        "catalog 구조를 인식하지 못했습니다."
    )


def normalize(value):

    return (
        str(value or "")
        .replace(" ", "")
        .lower()
    )


def find_club(clubs, target_id):

    # 1. ID exact
    for club in clubs:

        if str(
            club.get("id")
        ) == target_id:

            return club

    # 2. 이름 fallback
    names = NAME_FALLBACK.get(
        target_id,
        [],
    )

    normalized_names = {
        normalize(x)
        for x in names
    }

    matches = []

    for club in clubs:

        if normalize(
            club.get("name")
        ) in normalized_names:

            matches.append(
                club
            )

    if len(matches) == 1:
        return matches[0]

    return None


def main():

    print()
    print("=" * 70)
    print("Golf Master STRICT VERIFIED APPLY")
    print("=" * 70)

    data = load_json(
        CATALOG
    )

    clubs = get_clubs(
        data
    )

    if len(clubs) != 553:

        raise RuntimeError(
            f"안전 중단: catalog={len(clubs)} "
            "553개가 아닙니다."
        )

    # ------------------------------------------------------
    # 백업
    # ------------------------------------------------------

    BACKUPS.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup = (
        BACKUPS
        / f"catalog_before_strict_verified_{STAMP}.json"
    )

    shutil.copy2(
        CATALOG,
        backup,
    )

    print()
    print(
        "백업:",
        backup,
    )

    applied = []
    same = []
    hold = []

    # ------------------------------------------------------
    # 확정 화이트리스트만 적용
    # ------------------------------------------------------

    for target_id, fields in APPROVED.items():

        club = find_club(
            clubs,
            target_id,
        )

        if club is None:

            hold.append({
                "target":
                    target_id,

                "reason":
                    "catalog에서 골프장을 하나로 특정하지 못함",
            })

            continue

        club_name = (
            club.get("name")
            or target_id
        )

        verified = club.setdefault(
            "verified_basic_info",
            {},
        )

        for field, new_value in fields.items():

            old_value = club.get(
                field
            )

            # 이미 동일
            if old_value == new_value:

                same.append({
                    "name":
                        club_name,

                    "field":
                        field,

                    "value":
                        new_value,
                })

                continue

            # 기존 값이 다른 경우 자동 덮어쓰기 금지
            if old_value not in (
                None,
                "",
                "없음",
            ):

                hold.append({
                    "name":
                        club_name,

                    "field":
                        field,

                    "existing":
                        old_value,

                    "candidate":
                        new_value,

                    "reason":
                        "기존값 존재 - 자동 덮어쓰기 금지",
                })

                continue

            # 실제 반영
            club[field] = new_value

            verified[field] = {
                "value":
                    new_value,

                "confidence":
                    "A",

                "checked_at":
                    datetime.now().isoformat(),

                "verification_method":
                    "manual_strict_whitelist",

                "note":
                    (
                        "FIRST 50 웹검색 결과를 "
                        "필드별 재검토 후 확정"
                    ),
            }

            applied.append({
                "name":
                    club_name,

                "field":
                    field,

                "old":
                    old_value,

                "new":
                    new_value,
            })

    # ------------------------------------------------------
    # 저장
    # ------------------------------------------------------

    save_json(
        CATALOG,
        data,
    )

    # ------------------------------------------------------
    # 다시 읽어서 검증
    # ------------------------------------------------------

    verify_data = load_json(
        CATALOG
    )

    verify_clubs = get_clubs(
        verify_data
    )

    if len(verify_clubs) != 553:

        shutil.copy2(
            backup,
            CATALOG,
        )

        raise RuntimeError(
            "검증 실패: 553개가 아니어서 "
            "자동 복원했습니다."
        )

    ids = [
        str(
            club.get("id")
        )
        for club in verify_clubs
        if club.get("id") is not None
    ]

    if len(ids) != len(set(ids)):

        shutil.copy2(
            backup,
            CATALOG,
        )

        raise RuntimeError(
            "검증 실패: ID 중복 발생. "
            "자동 복원했습니다."
        )

    # ------------------------------------------------------
    # 결과
    # ------------------------------------------------------

    print()
    print("=" * 70)
    print("STRICT 반영 완료")
    print("=" * 70)

    print(
        "골프장 수:",
        len(verify_clubs),
    )

    print(
        "신규 반영:",
        len(applied),
    )

    print(
        "이미 동일:",
        len(same),
    )

    print(
        "HOLD:",
        len(hold),
    )

    print()

    for item in applied:

        print(
            "[APPLY]",
            item["name"],
            "/",
            item["field"],
            "→",
            item["new"],
        )

    for item in same:

        print(
            "[SAME]",
            item["name"],
            "/",
            item["field"],
            "=",
            item["value"],
        )

    for item in hold:

        print(
            "[HOLD]",
            item,
        )

    print()
    print("=" * 70)

    print(
        "SUCCESS: "
        "검색결과 자동판정 없이 "
        "화이트리스트 확정값만 반영"
    )

    print("=" * 70)


if __name__ == "__main__":

    main()