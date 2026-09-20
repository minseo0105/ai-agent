from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path


# ============================================================
# Golf Master DB - FIRST 50 DIAGNOSTIC
#
# 목적
# 1. 현재 553개 catalog 중 우선 보강할 50개 선정
# 2. 이미 확보한 공공데이터/KGA/기존 검증정보 최대한 재사용
# 3. 실제 추가 검색이 필요한 필드만 산출
#
# catalog.json 수정 없음
# 외부 API 호출 없음
# LLM 호출 없음
# ============================================================


ROOT = Path(__file__).resolve().parent

CATALOG_PATH = (
    ROOT
    / "data"
    / "golf"
    / "catalog.json"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "master_first50"
)


PLACEHOLDER_INTROS = {
    "",
    "상세 코스정보는 공식 홈페이지에서 확인합니다.",
    "공식 홈페이지에서 상세 코스정보를 확인할 수 있습니다.",
}


TARGET_FIELDS = (
    "operation_type",
    "holes",
    "courses",
    "official_url",
    "booking_url",
    "address",
    "phone",
    "description",
)


# ============================================================
# 기본 함수
# ============================================================


def clean(value):

    if value is None:
        return ""

    return str(value).strip()


def public_data(club):

    return (
        (club.get("verification") or {})
        .get("public_data")
        or {}
    )


def kga_data(club):

    return club.get("kga") or {}


def has_real_intro(club):

    text = clean(
        club.get("course_overview")
    )

    return (
        text
        not in PLACEHOLDER_INTROS
    )


def valid_holes(value):

    return (
        isinstance(value, int)
        and value > 0
    )


def valid_courses(value):

    return (
        isinstance(value, list)
        and len(value) > 0
    )


# ============================================================
# 현재 확보된 사실정보
# ============================================================


def current_facts(club):

    public = public_data(club)

    address = clean(
        club.get("address")
    )

    phone = clean(
        club.get("phone")
    )


    # 기존 catalog 값 우선
    operation_type = clean(
        club.get("operation_type")
    )


    # operation_type이 없고
    # 공공데이터 exact 계열이면 참고 가능
    if not operation_type:

        match_type = clean(
            public.get("match_type")
        ).lower()

        business_type = clean(
            public.get("business_type")
        )

        if (
            public.get("matched") is True
            and match_type in {
                "exact",
                "normalized_1.00",
                "exact_match",
            }
            and business_type
        ):

            operation_type = (
                business_type
            )


    holes = (
        club.get("holes")
        if valid_holes(
            club.get("holes")
        )
        else None
    )


    courses = (
        club.get("courses")
        if valid_courses(
            club.get("courses")
        )
        else None
    )


    official_url = clean(
        club.get("official_url")
    )

    booking_url = clean(
        club.get("booking_url")
    )


    description = (
        clean(
            club.get(
                "course_overview"
            )
        )
        if has_real_intro(club)
        else ""
    )


    return {

        "operation_type":
            operation_type or None,

        "holes":
            holes,

        "courses":
            courses,

        "official_url":
            official_url or None,

        "booking_url":
            booking_url or None,

        "address":
            address or None,

        "phone":
            phone or None,

        "description":
            description or None,
    }


# ============================================================
# 이미 가지고 있는 보조 근거
# ============================================================


def evidence_summary(club):

    public = public_data(club)
    kga = kga_data(club)

    return {

        "public_matched":
            public.get("matched")
            is True,

        "public_match_type":
            public.get(
                "match_type"
            ),

        "public_operating":
            public.get(
                "operating_in_public_data"
            ),

        "public_business_type":
            public.get(
                "business_type"
            ),

        "public_management_no":
            public.get(
                "management_no"
            ),

        "public_updated_at":
            public.get(
                "data_updated_at"
            ),

        "kga_matched":
            kga.get("matched")
            is True,

        "kga_match_type":
            kga.get(
                "match_type"
            ),

        "kga_matched_name":
            kga.get(
                "matched_name"
            ),

        "kga_course_combinations":
            kga.get(
                "course_combinations"
            )
            or [],

        "kga_ratings_count":
            len(
                kga.get(
                    "ratings"
                )
                or []
            ),

        "verified_basic_info":
            club.get(
                "verified_basic_info"
            )
            or {},
    }


# ============================================================
# 검색 필요 필드
# ============================================================


def missing_fields(facts):

    return [
        field
        for field
        in TARGET_FIELDS
        if not facts.get(field)
    ]


# ============================================================
# 검색 묶음 계산
#
# 실제 Tavily 호출은 하지 않습니다.
# 나중에 같은 검색으로 여러 필드를 채울 수 있도록
# 검색 단위를 묶어 계산합니다.
# ============================================================


def build_search_plan(
    club,
    missing,
):

    name = club.get(
        "name",
        ""
    )

    plans = []


    # --------------------------------------------------------
    # 공식 기본정보 검색
    # --------------------------------------------------------

    profile_fields = [
        field
        for field in (
            "operation_type",
            "holes",
            "courses",
            "official_url",
            "description",
        )
        if field in missing
    ]


    if profile_fields:

        plans.append({

            "type":
                "official_profile",

            "fields":
                profile_fields,

            "query":
                (
                    f"{name} 공식 홈페이지 "
                    "골프장 코스 홀수 "
                    "회원제 대중제"
                ),

            "priority":
                1,
        })


    # --------------------------------------------------------
    # 예약페이지
    # --------------------------------------------------------

    if (
        "booking_url"
        in missing
    ):

        plans.append({

            "type":
                "official_booking",

            "fields": [
                "booking_url"
            ],

            "query":
                f"{name} 공식 예약",

            "priority":
                2,
        })


    # --------------------------------------------------------
    # 주소/전화
    # --------------------------------------------------------

    contact_fields = [
        field
        for field in (
            "address",
            "phone",
        )
        if field in missing
    ]


    if contact_fields:

        plans.append({

            "type":
                "official_contact",

            "fields":
                contact_fields,

            "query":
                (
                    f"{name} "
                    "공식 주소 전화번호"
                ),

            "priority":
                3,
        })


    return plans


# ============================================================
# 우선 보강 점수
#
# "좋은 골프장 순위"가 아닙니다.
# DB 보강 우선순위입니다.
#
# 서비스에 노출되는 골프장과
# 공공/KGA 근거가 이미 있는 골프장을 먼저 처리합니다.
# ============================================================


def enrichment_priority(club):

    score = 0

    status = club.get(
        "service_status"
    )


    if status == "service":
        score += 100

    elif status == "candidate":
        score += 50


    public = public_data(club)

    if (
        public.get(
            "operating_in_public_data"
        )
        is True
    ):
        score += 25


    kga = kga_data(club)

    if (
        kga.get("matched")
        is True
    ):
        score += 20


    if (
        kga.get("ratings")
    ):
        score += 10


    facts = current_facts(
        club
    )


    # 어느 정도 정보가 이미 있어
    # 검색 효율이 좋은 곳을 먼저 처리
    score += (
        sum(
            bool(v)
            for v
            in facts.values()
        )
        * 2
    )


    return score


# ============================================================
# 첫 50개 선정
# ============================================================


def choose_first_50(
    catalog,
):

    eligible = [

        club

        for club
        in catalog

        if club.get(
            "service_status"
        )
        != "excluded"
    ]


    eligible.sort(

        key=lambda club: (

            -enrichment_priority(
                club
            ),

            clean(
                club.get("name")
            ),
        )
    )


    return eligible[:50]


# ============================================================
# 메인
# ============================================================


def main():

    print()

    print(
        "=" * 72
    )

    print(
        "Golf Master DB - FIRST 50 DIAGNOSTIC"
    )

    print(
        "=" * 72
    )


    if not CATALOG_PATH.exists():

        raise RuntimeError(
            "catalog.json을 찾을 수 없습니다."
        )


    original_bytes = (
        CATALOG_PATH.read_bytes()
    )


    catalog = json.loads(

        original_bytes.decode(
            "utf-8-sig"
        )
    )


    print()

    print(
        "현재 catalog:",
        len(catalog),
        "개",
    )


    if len(catalog) != 553:

        raise RuntimeError(

            "안전 중단: "
            "현재 예상 catalog는 "
            "553개입니다. "

            f"실제 {len(catalog)}개"
        )


    selected = (
        choose_first_50(
            catalog
        )
    )


    rows = []

    field_missing_counter = (
        Counter()
    )

    search_type_counter = (
        Counter()
    )

    total_search_units = 0


    # --------------------------------------------------------
    # 50개 분석
    # --------------------------------------------------------

    for index, club in enumerate(
        selected,
        start=1,
    ):

        facts = current_facts(
            club
        )

        missing = missing_fields(
            facts
        )

        plans = build_search_plan(
            club,
            missing,
        )


        for field in missing:

            field_missing_counter[
                field
            ] += 1


        for plan in plans:

            search_type_counter[
                plan["type"]
            ] += 1


        total_search_units += (
            len(plans)
        )


        rows.append({

            "order":
                index,

            "id":
                club.get("id"),

            "name":
                club.get("name"),

            "service_status":
                club.get(
                    "service_status"
                ),

            "area":
                club.get("area"),

            "subregion":
                club.get(
                    "subregion"
                ),

            "city":
                club.get("city"),

            "current_facts":
                facts,

            "missing_fields":
                missing,

            "missing_count":
                len(missing),

            "existing_evidence":
                evidence_summary(
                    club
                ),

            "search_plan":
                plans,

            "planned_search_units":
                len(plans),
        })


    # --------------------------------------------------------
    # catalog 불변 확인
    # --------------------------------------------------------

    if (
        CATALOG_PATH.read_bytes()
        != original_bytes
    ):

        raise RuntimeError(
            "catalog.json 변경 감지"
        )


    # --------------------------------------------------------
    # 출력 폴더
    # --------------------------------------------------------

    stamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )


    output_dir = (
        OUTPUT_ROOT
        / stamp
    )


    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )


    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    result = {

        "mode":
            "DIAGNOSTIC_ONLY",

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "catalog_count":
            len(catalog),

        "selected_count":
            len(rows),

        "catalog_modified":
            False,

        "external_search_calls":
            0,

        "llm_calls":
            0,

        "planned_search_units":
            total_search_units,

        "missing_by_field":
            dict(
                field_missing_counter
            ),

        "search_plan_by_type":
            dict(
                search_type_counter
            ),

        "clubs":
            rows,
    }


    result_path = (
        output_dir
        / "result.json"
    )


    result_path.write_text(

        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),

        encoding="utf-8",
    )


    # --------------------------------------------------------
    # 사람이 보기 쉬운 report.md
    # --------------------------------------------------------

    lines = [

        "# Golf Master DB - First 50 Diagnostic",

        "",

        f"- 전체 catalog: {len(catalog)}개",

        f"- 이번 대상: {len(rows)}개",

        "- 실제 외부검색: 0회",

        "- LLM 호출: 0회",

        f"- 향후 최대 검색 묶음: {total_search_units}회",

        "- catalog 수정: 없음",

        "",

        "## 필드별 추가 확인 필요",

        "",
    ]


    for field in TARGET_FIELDS:

        lines.append(

            f"- {field}: "
            f"{field_missing_counter.get(field, 0)}개"
        )


    lines.extend([

        "",

        "## 검색 종류별 예상",

        "",
    ])


    for key in (
        "official_profile",
        "official_booking",
        "official_contact",
    ):

        lines.append(

            f"- {key}: "
            f"{search_type_counter.get(key, 0)}회"
        )


    lines.extend([

        "",

        "## 첫 50개",

        "",

        "| # | 골프장 | 상태 | 확보 | 누락 | 검색묶음 |",

        "|---:|---|---|---:|---:|---:|",
    ])


    for row in rows:

        have = (
            len(TARGET_FIELDS)
            - row[
                "missing_count"
            ]
        )

        lines.append(

            f"| {row['order']} "
            f"| {row['name']} "
            f"| {row['service_status']} "
            f"| {have}/8 "
            f"| {row['missing_count']} "
            f"| {row['planned_search_units']} |"
        )


    report_path = (
        output_dir
        / "report.md"
    )


    report_path.write_text(

        "\n".join(lines)
        + "\n",

        encoding="utf-8",
    )


    # --------------------------------------------------------
    # 콘솔 결과
    # --------------------------------------------------------

    print()

    print(
        "첫 50개 선정 완료"
    )

    print()

    print(
        "필드별 추가 확인 필요:"
    )


    for field in TARGET_FIELDS:

        print(
            " -",
            field,
            ":",
            field_missing_counter.get(
                field,
                0,
            ),
            "개",
        )


    print()

    print(
        "예상 검색 묶음:"
    )

    print(
        " - 공식 기본정보:",
        search_type_counter.get(
            "official_profile",
            0,
        ),
        "회",
    )

    print(
        " - 공식 예약:",
        search_type_counter.get(
            "official_booking",
            0,
        ),
        "회",
    )

    print(
        " - 주소/전화:",
        search_type_counter.get(
            "official_contact",
            0,
        ),
        "회",
    )


    print()

    print(
        "최대 검색 묶음:",
        total_search_units,
        "회",
    )

    print()

    print(
        "외부 API 호출: 0회"
    )

    print(
        "LLM 호출: 0회"
    )

    print(
        "catalog.json 수정: 없음"
    )

    print()

    print(
        "결과:",
        result_path,
    )

    print(
        "요약:",
        report_path,
    )

    print()

    print(
        "=" * 72
    )

    print(
        "진단 완료"
    )

    print(
        "=" * 72
    )

    print()

    print(
        "다음 단계에서는 이 결과를 기준으로"
    )

    print(
        "이미 확보된 정보는 다시 검색하지 않고,"
    )

    print(
        "실제 누락된 필드만 조사합니다."
    )

    print()


if __name__ == "__main__":
    main()