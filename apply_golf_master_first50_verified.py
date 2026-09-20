# -*- coding: utf-8 -*-
"""
Golf Master DB - FIRST 50 검증값 안전 반영

원칙
1. 추가 Tavily/API 호출 없음
2. 현재 catalog 553개 전제
3. 기존에 이미 있는 값은 원칙적으로 보존
4. 공식 URL / 예약 URL / 총 홀수 / 전화 / 운영형태 중
   보수적으로 확인 가능한 값만 반영
5. 충돌하거나 애매한 값은 HOLD
6. 적용 전 catalog 자동 백업
7. 적용 후 553개 유지 및 ID 중복 여부 검증
"""

from __future__ import annotations

import json
import re
import shutil
import hashlib

from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse


# ============================================================
# 기본 경로
# ============================================================

ROOT = Path(__file__).resolve().parent

CATALOG = (
    ROOT
    / "data"
    / "golf"
    / "catalog.json"
)

ENRICH_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
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
# 시간
# ============================================================

KST = timezone(
    timedelta(hours=9)
)

NOW = datetime.now(KST)

STAMP = NOW.strftime(
    "%Y%m%d_%H%M%S"
)

CHECKED_AT = (
    NOW.isoformat()
)


# ============================================================
# 공식 홈페이지로 자동 인정하지 않을 사이트
# ============================================================

BAD_DOMAINS = {
    "naver.com",
    "blog.naver.com",
    "m.blog.naver.com",
    "cafe.naver.com",

    "daum.net",
    "v.daum.net",

    "tistory.com",

    "youtube.com",
    "youtu.be",

    "instagram.com",
    "facebook.com",

    "x.com",
    "twitter.com",

    "teescanner.com",
    "m.teescanner.com",

    "kimcaddie.com",

    "premiumgolf.co.kr",
    "czgolf.kr",

    "golfzon.com",
}


# 이미 발견된 비정상 주소 패턴
BAD_ADDRESS_TOKENS = (
    "전남광주통합특별시",
)


# ============================================================
# JSON
# ============================================================

def load_json(path: Path):

    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def atomic_write_json(
    path: Path,
    obj,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = path.with_suffix(
        path.suffix + ".tmp"
    )

    temp.write_text(
        json.dumps(
            obj,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 저장된 JSON 자체 검증
    json.loads(
        temp.read_text(
            encoding="utf-8"
        )
    )

    temp.replace(path)


def sha256(path: Path):

    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


# ============================================================
# 문자열
# ============================================================

def clean(value):

    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):

        value = value.strip()

        if (
            not value
            or value.lower()
            in {
                "없음",
                "미확인",
                "unknown",
                "n/a",
                "-",
                "none",
            }
        ):
            return None

    return value


def normalize_name(value):

    return re.sub(
        r"[^0-9a-z가-힣]+",
        "",
        str(
            value or ""
        ).lower(),
    )


# ============================================================
# 운영형태 정규화
# ============================================================

def normalize_operation(
    value,
):

    text = str(
        value or ""
    ).strip()

    if (
        not text
        or text == "없음"
    ):
        return None

    # 혼합형
    if (
        "혼합" in text
        or (
            "회원" in text
            and (
                "대중" in text
                or "비회원" in text
                or "퍼블릭" in text
            )
        )
    ):
        return "혼합"

    # 대중제
    if (
        "비회원" in text
        or "대중" in text
        or "퍼블릭" in text
    ):
        return "대중제"

    # 회원제
    if "회원" in text:
        return "회원제"

    return None


# ============================================================
# URL
# ============================================================

def get_host(url):

    try:

        host = (
            urlparse(
                str(url)
            )
            .netloc
            .lower()
            .split(":")[0]
        )

        if host.startswith(
            "www."
        ):
            host = host[4:]

        return host

    except Exception:

        return ""


def is_bad_domain(url):

    host = get_host(url)

    if not host:
        return True

    for bad in BAD_DOMAINS:

        if (
            host == bad
            or host.endswith(
                "." + bad
            )
        ):
            return True

    return False


def same_domain(
    url1,
    url2,
):

    h1 = get_host(url1)
    h2 = get_host(url2)

    if not h1 or not h2:
        return False

    return (
        h1 == h2
        or h1.endswith(
            "." + h2
        )
        or h2.endswith(
            "." + h1
        )
    )


# ============================================================
# FIRST 50 웹검색 결과 자동 탐색
# ============================================================

def find_latest_web_result():

    candidates = []

    for path in (
        ENRICH_ROOT.rglob(
            "result.json"
        )
    ):

        try:

            data = load_json(
                path
            )

            if (
                data.get("mode")
                == "WEB_ENRICHMENT_REVIEW_ONLY"
                and data.get(
                    "catalog_count"
                )
                == 553
            ):

                candidates.append(
                    (
                        path.stat().st_mtime,
                        path,
                        data,
                    )
                )

        except Exception:

            continue

    if not candidates:

        raise FileNotFoundError(
            "\n553개 기준 FIRST 50 웹검색 "
            "result.json을 찾지 못했습니다.\n\n"
            "예상 위치:\n"
            "data/golf/enrichment/"
            "master_first50_web/"
            "20260920_211029/result.json\n"
        )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return (
        candidates[0][1],
        candidates[0][2],
    )


# ============================================================
# catalog 구조
# ============================================================

def get_clubs(data):

    if isinstance(
        data,
        list,
    ):
        return data

    if isinstance(
        data,
        dict,
    ):

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

    raise ValueError(
        "catalog.json 구조를 "
        "인식하지 못했습니다."
    )


# ============================================================
# 검색 결과 꺼내기
# ============================================================

def flatten_results(
    record,
):

    analysis = (
        record.get(
            "analysis"
        )
        or {}
    )

    if isinstance(
        analysis.get(
            "results"
        ),
        list,
    ):

        return analysis[
            "results"
        ]

    results = []

    for search in (
        record.get(
            "searches"
        )
        or []
    ):

        results.extend(
            search.get(
                "results"
            )
            or []
        )

    return results


# ============================================================
# 골프장 identity 확인
# ============================================================

def identity_strong(
    result,
):

    reasons = set(
        result.get(
            "identity_reasons"
        )
        or []
    )

    score = int(
        result.get(
            "identity_score"
        )
        or 0
    )

    # 전화번호나 주소가 일치
    if (
        "phone_match" in reasons
        or "address_match" in reasons
    ):
        return True

    # 이름 + 지역 일부 일치
    if (
        "name_match" in reasons
        and "address_partial"
        in reasons
        and score >= 5
    ):
        return True

    return False


# ============================================================
# 공식 홈페이지 후보
# ============================================================

def official_candidate(
    record,
):

    candidates = []

    for result in flatten_results(
        record
    ):

        url = clean(
            result.get(
                "url"
            )
        )

        if not url:
            continue

        if is_bad_domain(
            url
        ):
            continue

        if not result.get(
            "official_candidate"
        ):
            continue

        if not identity_strong(
            result
        ):
            continue

        score = int(
            result.get(
                "identity_score"
            )
            or 0
        )

        candidates.append(
            (
                score,
                url,
                result,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    top = candidates[0]

    # 충분히 강한 후보만
    if top[0] < 7:
        return None

    # 동일 점수인데 서로 다른 사이트면 HOLD
    if len(candidates) > 1:

        second = candidates[1]

        if (
            second[0] == top[0]
            and get_host(
                second[1]
            )
            != get_host(
                top[1]
            )
        ):
            return None

    return {
        "value":
            top[1],

        "evidence":
            top[2],
    }


# ============================================================
# 공식 예약 URL
# ============================================================

def booking_candidate(
    record,
    official_url,
):

    if not official_url:
        return None

    for result in flatten_results(
        record
    ):

        url = clean(
            result.get(
                "url"
            )
        )

        if not url:
            continue

        # 공식 홈페이지와 같은 도메인만
        if not same_domain(
            url,
            official_url,
        ):
            continue

        text = (
            f"{result.get('title', '')} "
            f"{result.get('content', '')} "
            f"{url}"
        ).lower()

        if any(
            keyword in text
            for keyword in (
                "예약",
                "reservation",
                "booking",
                "reserve",
                "resv",
            )
        ):

            return {
                "value":
                    url,

                "evidence":
                    result,
            }

    return None


# ============================================================
# 총 홀수
# ============================================================

def holes_candidate(
    record,
):

    values = []

    for result in flatten_results(
        record
    ):

        if not identity_strong(
            result
        ):
            continue

        text = str(
            result.get(
                "content"
            )
            or ""
        )

        # 중요:
        # 단순히 '18홀'이라는 말만 나왔다고
        # 전체 골프장을 18홀로 만들지 않는다.
        #
        # 총 27홀
        # 전체 36홀
        # 54홀 규모
        # 같은 표현만 사용.

        patterns = (
            r"(?:총|전체|규모)"
            r"\s*[:：]?\s*"
            r"(9|18|27|36|45|54|63|72)"
            r"\s*홀",

            r"(9|18|27|36|45|54|63|72)"
            r"\s*홀\s*"
            r"(?:규모|골프장)",
        )

        for pattern in patterns:

            found = re.findall(
                pattern,
                text,
            )

            for value in found:

                values.append(
                    int(value)
                )

    values = sorted(
        set(values)
    )

    # 여러 값이 나오면 자동반영 금지
    if len(values) != 1:
        return None

    return values[0]


# ============================================================
# 전화번호
# ============================================================

def phone_candidate(
    record,
):

    phones = []

    for result in flatten_results(
        record
    ):

        if not identity_strong(
            result
        ):
            continue

        text = str(
            result.get(
                "content"
            )
            or ""
        )

        matches = re.findall(
            r"(?<!\d)"
            r"(0\d{1,2})"
            r"[-.) ]?"
            r"(\d{3,4})"
            r"[- ]?"
            r"(\d{4})"
            r"(?!\d)",
            text,
        )

        for area, mid, end in matches:

            phone = (
                f"{area}-"
                f"{mid}-"
                f"{end}"
            )

            if phone not in phones:
                phones.append(
                    phone
                )

    # 번호가 하나일 때만
    if len(phones) != 1:
        return None

    return phones[0]


# ============================================================
# 회원제 + 대중제 혼합 근거
# ============================================================

def mixed_operation_candidate(
    record,
):

    for result in flatten_results(
        record
    ):

        if not identity_strong(
            result
        ):
            continue

        text = str(
            result.get(
                "content"
            )
            or ""
        )

        member = bool(
            re.search(
                r"회원제\s*"
                r"(?:\d+\s*홀)?",
                text,
            )
        )

        public = bool(
            re.search(
                r"(?:대중제|비회원제|퍼블릭)"
                r"\s*(?:\d+\s*홀)?",
                text,
            )
        )

        if (
            member
            and public
        ):
            return "혼합"

    return None


# ============================================================
# provenance metadata
# ============================================================

def make_meta(
    source_file,
    field,
    value,
    evidence=None,
    source_type=
        "web_enrichment_reviewed",
):

    evidence = (
        evidence
        or {}
    )

    try:

        source_name = str(
            source_file.relative_to(
                ROOT
            )
        )

    except Exception:

        source_name = str(
            source_file
        )

    return {
        "value":
            value,

        "confidence":
            "A",

        "checked_at":
            CHECKED_AT,

        "source_type":
            source_type,

        "source_file":
            source_name,

        "field":
            field,

        "evidence_url":
            evidence.get(
                "url"
            ),

        "evidence_title":
            evidence.get(
                "title"
            ),
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 72)
    print(
        "Golf Master DB - "
        "FIRST 50 검증값 안전 반영"
    )
    print("=" * 72)

    # --------------------------------------------------------
    # FIRST50 검색결과
    # --------------------------------------------------------

    source_file, web_data = (
        find_latest_web_result()
    )

    print()
    print(
        "검색결과:",
        source_file,
    )

    print(
        "기존 Tavily 호출:",
        web_data.get(
            "search_calls"
        ),
    )

    print(
        "추가 API 호출: 0"
    )

    # --------------------------------------------------------
    # catalog
    # --------------------------------------------------------

    catalog_data = load_json(
        CATALOG
    )

    clubs = get_clubs(
        catalog_data
    )

    if len(clubs) != 553:

        raise RuntimeError(
            "\n안전 중단\n"
            "현재 catalog가 "
            "553개가 아닙니다.\n"
            f"현재: {len(clubs)}개\n"
        )

    before_hash = sha256(
        CATALOG
    )

    # --------------------------------------------------------
    # ID / 이름 index
    # --------------------------------------------------------

    by_id = {
        str(
            club.get("id")
        ):
        club

        for club in clubs

        if club.get("id")
        is not None
    }

    by_name = {}

    for club in clubs:

        key = normalize_name(
            club.get(
                "name"
            )
        )

        by_name.setdefault(
            key,
            [],
        ).append(
            club
        )

    changes = []
    holds = []

    records = (
        web_data.get(
            "clubs"
        )
        or []
    )

    # --------------------------------------------------------
    # 50개 검토
    # --------------------------------------------------------

    for record in records:

        club_id = str(
            record.get(
                "id"
            )
            or ""
        )

        name = (
            record.get(
                "name"
            )
            or club_id
        )

        club = by_id.get(
            club_id
        )

        # ID가 없으면 이름 exact로 한 번 더
        if club is None:

            matches = (
                by_name.get(
                    normalize_name(
                        name
                    ),
                    [],
                )
            )

            if len(matches) == 1:

                club = matches[0]

            else:

                holds.append({
                    "id":
                        club_id,

                    "name":
                        name,

                    "field":
                        "identity",

                    "reason":
                        "catalog match ambiguous",
                })

                continue

        existing_evidence = (
            record.get(
                "existing_evidence"
            )
            or {}
        )

        verified = (
            club.setdefault(
                "verified_basic_info",
                {},
            )
        )

        # ----------------------------------------------------
        # 주소 품질 문제
        # ----------------------------------------------------

        address = str(
            club.get(
                "address"
            )
            or ""
        )

        if any(
            token in address
            for token
            in BAD_ADDRESS_TOKENS
        ):

            holds.append({
                "id":
                    club_id,

                "name":
                    name,

                "field":
                    "address",

                "reason":
                    "행정주소 문자열 이상 "
                    "- 자동 수정 금지",
            })

        # ----------------------------------------------------
        # 1. 공식 홈페이지
        #
        # 기존 공식 URL이 있으면 절대 덮어쓰지 않는다.
        # ----------------------------------------------------

        if not clean(
            club.get(
                "official_url"
            )
        ):

            candidate = (
                official_candidate(
                    record
                )
            )

            if candidate:

                new_value = (
                    candidate[
                        "value"
                    ]
                )

                club[
                    "official_url"
                ] = new_value

                verified[
                    "official_url"
                ] = make_meta(
                    source_file,
                    "official_url",
                    new_value,
                    candidate[
                        "evidence"
                    ],
                )

                changes.append({
                    "id":
                        club_id,

                    "name":
                        name,

                    "field":
                        "official_url",

                    "new":
                        new_value,
                })

        # ----------------------------------------------------
        # 2. 예약 페이지
        #
        # 공식 홈페이지와 같은 도메인일 때만.
        # 예약 가능 여부가 아니라
        # "예약 페이지 URL"만 저장.
        # ----------------------------------------------------

        if not clean(
            club.get(
                "booking_url"
            )
        ):

            candidate = (
                booking_candidate(
                    record,
                    club.get(
                        "official_url"
                    ),
                )
            )

            if candidate:

                new_value = (
                    candidate[
                        "value"
                    ]
                )

                club[
                    "booking_url"
                ] = new_value

                verified[
                    "booking_url"
                ] = make_meta(
                    source_file,
                    "booking_url",
                    new_value,
                    candidate[
                        "evidence"
                    ],
                )

                changes.append({
                    "id":
                        club_id,

                    "name":
                        name,

                    "field":
                        "booking_url",

                    "new":
                        new_value,
                })

        # ----------------------------------------------------
        # 3. 총 홀수
        #
        # 기존 홀수가 있으면 유지.
        # 없는 경우만 강한 표현 사용.
        # ----------------------------------------------------

        if not clean(
            club.get(
                "holes"
            )
        ):

            holes = (
                holes_candidate(
                    record
                )
            )

            if holes:

                club[
                    "holes"
                ] = holes

                verified[
                    "holes"
                ] = make_meta(
                    source_file,
                    "holes",
                    holes,
                )

                changes.append({
                    "id":
                        club_id,

                    "name":
                        name,

                    "field":
                        "holes",

                    "new":
                        holes,
                })

        # ----------------------------------------------------
        # 4. 전화번호
        # ----------------------------------------------------

        if not clean(
            club.get(
                "phone"
            )
        ):

            phone = (
                phone_candidate(
                    record
                )
            )

            if phone:

                club[
                    "phone"
                ] = phone

                verified[
                    "phone"
                ] = make_meta(
                    source_file,
                    "phone",
                    phone,
                )

                changes.append({
                    "id":
                        club_id,

                    "name":
                        name,

                    "field":
                        "phone",

                    "new":
                        phone,
                })

        # ----------------------------------------------------
        # 5. 운영형태
        # ----------------------------------------------------

        direct = normalize_operation(
            club.get(
                "operation_type"
            )
        )

        public_raw = (
            existing_evidence.get(
                "public_business_type"
            )
        )

        public_operation = (
            normalize_operation(
                public_raw
            )
        )

        mixed = (
            mixed_operation_candidate(
                record
            )
        )

        # ----------------------------------------------------
        # 기존값과 공공데이터 충돌
        # ----------------------------------------------------

        if (
            direct
            and public_operation
            and direct
            != public_operation
        ):

            # 웹 근거에서 회원제+대중제가
            # 명시적으로 병존하면 혼합으로 정교화
            if mixed == "혼합":

                old_value = (
                    club.get(
                        "operation_type"
                    )
                )

                club[
                    "operation_type"
                ] = "혼합"

                verified[
                    "operation_type"
                ] = make_meta(
                    source_file,
                    "operation_type",
                    "혼합",
                )

                verified[
                    "operation_type"
                ][
                    "note"
                ] = (
                    f"기존={old_value}, "
                    f"공공데이터={public_raw}; "
                    "웹 근거에 회원제+대중제 병존"
                )

                changes.append({
                    "id":
                        club_id,

                    "name":
                        name,

                    "field":
                        "operation_type",

                    "old":
                        old_value,

                    "new":
                        "혼합",
                })

            else:

                holds.append({
                    "id":
                        club_id,

                    "name":
                        name,

                    "field":
                        "operation_type",

                    "reason":
                        (
                            "충돌: "
                            f"catalog="
                            f"{club.get('operation_type')} "
                            f"/ public="
                            f"{public_raw}"
                        ),
                })

        # ----------------------------------------------------
        # 현재 operation_type 없음
        # ----------------------------------------------------

        elif not direct:

            # 웹에서 회원제+대중제 명시
            if mixed == "혼합":

                if (
                    public_operation
                    and public_operation
                    != "혼합"
                ):

                    holds.append({
                        "id":
                            club_id,

                        "name":
                            name,

                        "field":
                            "operation_type",

                        "reason":
                            (
                                "웹=혼합 / "
                                f"공공데이터="
                                f"{public_raw} 충돌"
                            ),
                    })

                else:

                    club[
                        "operation_type"
                    ] = "혼합"

                    verified[
                        "operation_type"
                    ] = make_meta(
                        source_file,
                        "operation_type",
                        "혼합",
                    )

                    changes.append({
                        "id":
                            club_id,

                        "name":
                            name,

                        "field":
                            "operation_type",

                        "new":
                            "혼합",
                    })

            # ------------------------------------------------
            # 공공데이터 안전매칭
            # ------------------------------------------------

            elif (
                public_operation
                and existing_evidence.get(
                    "public_matched"
                )
                is True
                and existing_evidence.get(
                    "public_operating"
                )
                is True
            ):

                match_type = str(
                    existing_evidence.get(
                        "public_match_type"
                    )
                    or ""
                )

                safe_match = (
                    match_type
                    in {
                        "exact",
                        "normalized_1.00",
                        "safe_fuzzy",
                    }
                    or "1.00"
                    in match_type
                )

                if safe_match:

                    club[
                        "operation_type"
                    ] = public_operation

                    verified[
                        "operation_type"
                    ] = {
                        "value":
                            public_operation,

                        "confidence":
                            "A",

                        "checked_at":
                            CHECKED_AT,

                        "source_type":
                            "public_data",

                        "source_name":
                            (
                                "행정안전부 "
                                "생활 골프장 조회서비스"
                            ),

                        "public_management_no":
                            existing_evidence.get(
                                "public_management_no"
                            ),

                        "public_updated_at":
                            existing_evidence.get(
                                "public_updated_at"
                            ),

                        "raw_business_type":
                            public_raw,
                    }

                    changes.append({
                        "id":
                            club_id,

                        "name":
                            name,

                        "field":
                            "operation_type",

                        "new":
                            public_operation,
                    })

        # ----------------------------------------------------
        # 과거 2A에서 KGA tee 기반으로 홀수 생성된 값
        # 이번에는 건드리지 않고 재검증 대상으로 기록
        # ----------------------------------------------------

        if (
            club.get(
                "holes_source"
            )
            == "kga_tee_explicit"
        ):

            holds.append({
                "id":
                    club_id,

                "name":
                    name,

                "field":
                    "holes",

                "reason":
                    (
                        "holes_source="
                        "kga_tee_explicit "
                        "- 총 홀수 재검증 필요"
                    ),
            })

    # ========================================================
    # BACKUP
    # ========================================================

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup_path = (
        BACKUP_DIR
        / (
            "catalog_before_"
            "first50_verified_apply_"
            f"{STAMP}.json"
        )
    )

    shutil.copy2(
        CATALOG,
        backup_path,
    )

    print()
    print(
        "백업 완료:",
        backup_path,
    )

    # ========================================================
    # catalog 저장
    # ========================================================

    atomic_write_json(
        CATALOG,
        catalog_data,
    )

    # ========================================================
    # 저장 후 안전검증
    # ========================================================

    after_data = load_json(
        CATALOG
    )

    after_clubs = get_clubs(
        after_data
    )

    # 553 유지
    if len(after_clubs) != 553:

        shutil.copy2(
            backup_path,
            CATALOG,
        )

        raise RuntimeError(
            "\n저장 후 catalog 개수가 "
            "553개가 아니어서 "
            "자동으로 백업 복원했습니다.\n"
        )

    # ID 중복 검사
    ids = [
        str(
            club.get(
                "id"
            )
        )

        for club in after_clubs

        if club.get(
            "id"
        )
        is not None
    ]

    if (
        len(ids)
        != len(
            set(ids)
        )
    ):

        shutil.copy2(
            backup_path,
            CATALOG,
        )

        raise RuntimeError(
            "\nID 중복이 발생해 "
            "자동으로 백업 복원했습니다.\n"
        )

    # ========================================================
    # REPORT
    # ========================================================

    report = {
        "mode":
            "FIRST50_VERIFIED_SAFE_APPLY",

        "created_at":
            CHECKED_AT,

        "source_result":
            str(
                source_file
            ),

        "catalog_count_before":
            553,

        "catalog_count_after":
            len(
                after_clubs
            ),

        "source_search_calls":
            web_data.get(
                "search_calls"
            ),

        "additional_search_calls":
            0,

        "changes_count":
            len(
                changes
            ),

        "hold_count":
            len(
                holds
            ),

        "changes":
            changes,

        "holds":
            holds,

        "backup":
            str(
                backup_path
            ),

        "catalog_hash_before":
            before_hash,

        "catalog_hash_after":
            sha256(
                CATALOG
            ),
    }

    report_path = (
        REPORT_DIR
        / (
            f"{STAMP}_"
            "first50_verified_apply.json"
        )
    )

    atomic_write_json(
        report_path,
        report,
    )

    # ========================================================
    # 결과 출력
    # ========================================================

    print()
    print("=" * 72)
    print(
        "FIRST 50 검증값 안전 반영 완료"
    )
    print("=" * 72)

    print(
        f"catalog: "
        f"553 -> "
        f"{len(after_clubs)}"
    )

    print(
        "추가 Tavily/API 호출: 0"
    )

    print(
        f"반영 필드: "
        f"{len(changes)}"
    )

    print(
        f"HOLD: "
        f"{len(holds)}"
    )

    print()

    print(
        "백업:",
        backup_path,
    )

    print(
        "리포트:",
        report_path,
    )

    print()
    print("-" * 72)

    # 실제 반영 내용
    if changes:

        print(
            "실제 반영된 값"
        )

        print("-" * 72)

        for item in changes:

            old_value = (
                item.get(
                    "old"
                )
            )

            if old_value is not None:

                print(
                    f"[APPLY] "
                    f"{item['name']} "
                    f"/ {item['field']} "
                    f"/ {old_value} "
                    f"→ {item.get('new')}"
                )

            else:

                print(
                    f"[APPLY] "
                    f"{item['name']} "
                    f"/ {item['field']} "
                    f"→ {item.get('new')}"
                )

    else:

        print(
            "안전 기준을 통과한 "
            "신규 반영값이 없습니다."
        )

    # HOLD
    if holds:

        print()
        print("-" * 72)

        print(
            "HOLD "
            "(catalog를 덮어쓰지 않음)"
        )

        print("-" * 72)

        for item in holds[:50]:

            print(
                f"[HOLD] "
                f"{item['name']} "
                f"/ {item['field']} "
                f"/ {item['reason']}"
            )

        if len(holds) > 50:

            print(
                f"... 외 "
                f"{len(holds) - 50}건"
            )

    print()
    print("=" * 72)

    print(
        "SUCCESS: "
        "553개 catalog 유지 / "
        "검증값만 반영 / "
        "추가 검색 없음"
    )

    print("=" * 72)
    print()


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    main()