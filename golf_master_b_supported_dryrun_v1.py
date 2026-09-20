# -*- coding: utf-8 -*-

"""
Golf Master B_SUPPORTED DRY RUN v1
============================================================

목적
------------------------------------------------------------
최신 Verifier v2의 B_SUPPORTED.json을 읽어
현재 catalog.json과 비교한다.

1단계
- SAME      : catalog에 이미 같은 값 존재
- NEW       : catalog 해당 필드가 비어 있음
- CONFLICT  : catalog 기존값과 후보값이 다름
- MISSING   : catalog에서 골프장을 찾지 못함

2단계 - NEW만 재분류
- PROMOTE
    비교적 안전하게 실제 DB 반영을 검토할 수 있는 값
- KEEP_AS_EVIDENCE
    근거자료로 보관하되 확정 필드에는 아직 넣지 않을 값
- REVIEW
    사람이 한 번 더 확인해야 하는 값

중요
------------------------------------------------------------
- catalog.json 수정 없음
- Tavily 호출 없음
- LLM 호출 없음
- B_SUPPORTED를 자동 반영하지 않음
- operation_type SOURCE_CONFLICT는 이 파일의 입력 대상이 아님
- official_url은 검색후보만으로 PROMOTE하지 않음
- holes는 검색 snippet 근거만으로 PROMOTE하지 않음
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
    / "b_supported_dryrun_v1"
)


EXPECTED_CATALOG_COUNT = 553


# ============================================================
# CONFIG
# ============================================================

SUPPORTED_FIELDS = {
    "official_url",
    "booking_url",
    "holes",
    "operation_type",
    "phone",
}


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


THIRD_PARTY_DOMAINS = {
    "naver.com",
    "blog.naver.com",
    "m.blog.naver.com",
    "cafe.naver.com",
    "map.naver.com",
    "place.naver.com",
    "daum.net",
    "tistory.com",
    "kakao.com",
    "map.kakao.com",
    "kakao.golf",
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "facebook.com",
    "golfzon.com",
    "xgolf.com",
    "kimcaddie.com",
    "golfu.net",
    "baigolf.com",
    "golf.sbs.co.kr",
    "sbs.co.kr",
    "dbegl.com",
    "grandculture.net",
    "knps.or.kr",
    "premiumgolf.co.kr",
    "czgolf.kr",
    "hanjingolf.com",
    "yesgolf.co.kr",
    "trip.com",
    "kr.trip.com",
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


def sha256_bytes(
    data: bytes,
) -> str:

    return hashlib.sha256(
        data
    ).hexdigest()


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_phone(
    value: Any,
) -> str:

    return re.sub(
        r"\D",
        "",
        clean(value),
    )


def normalize_operation(
    value: Any,
):

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


def domain_of(
    url: Any,
) -> str:

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


def is_third_party(
    url: Any,
) -> bool:

    domain = domain_of(
        url
    )

    if not domain:
        return True

    return any(

        domain == blocked
        or domain.endswith(
            "." + blocked
        )

        for blocked
        in THIRD_PARTY_DOMAINS
    )


# ============================================================
# SAME VALUE
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

        a = (
            clean(current)
            .rstrip("/")
            .lower()
        )

        b = (
            clean(candidate)
            .rstrip("/")
            .lower()
        )

        return a == b

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
# PUBLIC DATA
# ============================================================

def public_data(
    club: dict,
) -> dict:

    return (
        (
            club.get(
                "verification"
            )
            or {}
        )
        .get(
            "public_data"
        )
        or {}
    )


def public_phone(
    club: dict,
):

    pub = public_data(
        club
    )

    for key in (
        "phone",
        "TELNO",
        "telno",
    ):

        value = pub.get(
            key
        )

        if has_value(value):

            return value

    return None


# ============================================================
# FIND LATEST B_SUPPORTED
# ============================================================

def find_latest_b_supported() -> Path:

    if not VERIFIER_ROOT.exists():

        raise RuntimeError(
            f"Verifier v2 폴더 없음: "
            f"{VERIFIER_ROOT}"
        )

    candidates = []

    for path in (
        VERIFIER_ROOT.rglob(
            "B_SUPPORTED.json"
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
            "B_SUPPORTED.json을 "
            "찾지 못했습니다."
        )

    return max(
        candidates,
        key=lambda path:
            path.stat().st_mtime,
    )


# ============================================================
# PROMOTION POLICY
# ============================================================

def classify_new_candidate(
    club: dict,
    row: dict,
) -> dict:

    """
    B_SUPPORTED 중 catalog 빈 필드인 NEW만 판정한다.

    PROMOTE:
      현재 확보한 증거만으로 실제 DB 입력을 검토할 만한 값.

    KEEP_AS_EVIDENCE:
      유용하지만 확정값으로 쓰기엔 부족한 값.

    REVIEW:
      운영주체/URL 의미 등 사람이 한 번 더 봐야 하는 값.
    """

    field = clean(
        row.get("field")
    )

    candidate = (
        row.get("value")
    )

    reason = clean(
        row.get("reason")
    )

    detail = (
        row.get("detail")
        or {}
    )

    # ========================================================
    # PHONE
    # ========================================================

    if field == "phone":

        pub = public_data(
            club
        )

        pub_phone = (
            public_phone(
                club
            )
        )

        # 정확 매칭된 공공데이터 전화번호이고
        # B_SUPPORTED 값과 동일
        if (
            pub.get("matched") is True
            and has_value(
                pub_phone
            )
            and same_value(
                "phone",
                pub_phone,
                candidate,
            )
        ):

            return {
                "promotion":
                    "PROMOTE",

                "promotion_reason":
                    "exact_public_data_phone",

                "source_type":
                    "public_data",
            }

        # 웹 여러 결과가 동일 전화번호를 지지
        if reason == (
            "multiple_web_results_agree"
        ):

            return {
                "promotion":
                    "KEEP_AS_EVIDENCE",

                "promotion_reason":
                    "multiple_web_phone_support_but_not_authoritative",

                "source_type":
                    "web",
            }

        return {
            "promotion":
                "KEEP_AS_EVIDENCE",

            "promotion_reason":
                "phone_supported_but_not_A_verified",

            "source_type":
                "mixed",
        }

    # ========================================================
    # OPERATION TYPE
    # ========================================================

    if field == "operation_type":

        # exact public data 기반 B_SUPPORTED
        if reason == (
            "exact_public_data_operation"
        ):

            pub = public_data(
                club
            )

            if (
                pub.get("matched") is True
                and has_value(
                    candidate
                )
            ):

                return {
                    "promotion":
                        "PROMOTE",

                    "promotion_reason":
                        "exact_public_data_operation_type",

                    "source_type":
                        "public_data",
                }

        # 기존 catalog operation이면
        # NEW일 수 없겠지만 방어적으로 처리
        if reason == (
            "existing_catalog_operation"
        ):

            return {
                "promotion":
                    "KEEP_AS_EVIDENCE",

                "promotion_reason":
                    "existing_operation_reference",

                "source_type":
                    "catalog",
            }

        return {
            "promotion":
                "REVIEW",

            "promotion_reason":
                "operation_type_requires_source_review",

            "source_type":
                "mixed",
        }

    # ========================================================
    # BOOKING URL
    # ========================================================

    if field == "booking_url":

        url = clean(
            candidate
        )

        if not url:

            return {
                "promotion":
                    "REVIEW",

                "promotion_reason":
                    "empty_booking_url",
            }

        if is_third_party(
            url
        ):

            return {
                "promotion":
                    "REVIEW",

                "promotion_reason":
                    "third_party_booking_candidate",
            }

        official_url = clean(
            club.get(
                "official_url"
            )
        )

        # 공식 홈페이지가 이미 catalog에 있고
        # booking candidate가 동일 도메인
        if (
            has_value(
                official_url
            )
            and domain_of(
                official_url
            )
            and domain_of(
                official_url
            )
            == domain_of(
                url
            )
        ):

            # B_SUPPORTED이므로 실제 예약 동작을
            # 완전히 확정하지 않고 PROMOTE 가능 후보로 둔다.
            return {
                "promotion":
                    "PROMOTE",

                "promotion_reason":
                    "booking_url_on_existing_official_domain",

                "source_type":
                    "official_domain",
            }

        return {
            "promotion":
                "REVIEW",

            "promotion_reason":
                "official_domain_not_confirmed_for_booking",

            "source_type":
                "web",
        }

    # ========================================================
    # OFFICIAL URL
    # ========================================================

    if field == "official_url":

        url = clean(
            candidate
        )

        if not url:

            return {
                "promotion":
                    "REVIEW",

                "promotion_reason":
                    "empty_official_url",
            }

        if is_third_party(
            url
        ):

            return {
                "promotion":
                    "REVIEW",

                "promotion_reason":
                    "third_party_domain",
            }

        # B_SUPPORTED의 official_url은
        # 운영주체 도메인인지 아직 완전히 확인되지 않았으므로
        # 자동 PROMOTE하지 않는다.
        return {
            "promotion":
                "REVIEW",

            "promotion_reason":
                "official_operator_identity_not_A_verified",

            "source_type":
                "web",
        }

    # ========================================================
    # HOLES
    # ========================================================

    if field == "holes":

        # B_SUPPORTED holes는 구조적
        # '총 N홀' 검색근거가 있더라도 snippet 기반.
        # 실제 DB 확정값으로 자동승격하지 않는다.
        return {
            "promotion":
                "KEEP_AS_EVIDENCE",

            "promotion_reason":
                "structural_total_holes_web_evidence_only",

            "source_type":
                "web",
        }

    # ========================================================
    # DEFAULT
    # ========================================================

    return {
        "promotion":
            "REVIEW",

        "promotion_reason":
            "unsupported_field_policy",
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print(
        "=" * 78
    )

    print(
        "Golf Master B_SUPPORTED DRY RUN v1"
    )

    print(
        "=" * 78
    )

    # ========================================================
    # LOAD CATALOG
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
    # B_SUPPORTED
    # ========================================================

    source_path = (
        find_latest_b_supported()
    )

    print()

    print(
        "사용 B_SUPPORTED:"
    )

    print(
        source_path
    )

    supported_rows = (
        load_json(
            source_path
        )
    )

    print(
        "B_SUPPORTED 입력:",
        len(supported_rows),
        "개"
    )

    # ========================================================
    # CATALOG INDEX
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

    promote_rows = []

    evidence_rows = []

    review_rows = []

    field_counter = {
        field: Counter()
        for field in SUPPORTED_FIELDS
    }

    promotion_counter = {
        field: Counter()
        for field in SUPPORTED_FIELDS
    }

    for row in supported_rows:

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

        if field not in (
            SUPPORTED_FIELDS
        ):

            continue

        club = (
            catalog_index.get(
                club_id
            )
        )

        # ----------------------------------------------------
        # MISSING CLUB
        # ----------------------------------------------------

        if club is None:

            result = {
                "id": club_id,
                "name": name,
                "field": field,
                "candidate": candidate,
                "status": "MISSING",
                "reason":
                    "catalog_id_not_found",
            }

            missing_rows.append(
                result
            )

            field_counter[
                field
            ]["MISSING"] += 1

            continue

        # ----------------------------------------------------
        # EMPTY CANDIDATE
        # ----------------------------------------------------

        if not has_value(
            candidate
        ):

            result = {
                "id": club_id,
                "name": name,
                "field": field,
                "candidate": candidate,
                "status": "MISSING",
                "reason":
                    "B_SUPPORTED_candidate_empty",
            }

            missing_rows.append(
                result
            )

            field_counter[
                field
            ]["MISSING"] += 1

            continue

        current = (
            club.get(
                field
            )
        )

        # ----------------------------------------------------
        # SAME
        # ----------------------------------------------------

        if (
            has_value(current)
            and same_value(
                field,
                current,
                candidate,
            )
        ):

            result = {
                "id": club_id,
                "name": name,
                "field": field,
                "current": current,
                "candidate": candidate,
                "status": "SAME",
                "reason":
                    "catalog_and_B_supported_agree",
                "verification_reason":
                    row.get("reason"),
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

        if has_value(
            current
        ):

            result = {
                "id": club_id,
                "name": name,
                "field": field,
                "current": current,
                "candidate": candidate,
                "status": "CONFLICT",
                "reason":
                    "existing_catalog_value_differs_from_B_supported",
                "verification_reason":
                    row.get("reason"),
                "detail":
                    row.get("detail"),
            }

            conflict_rows.append(
                result
            )

            field_counter[
                field
            ]["CONFLICT"] += 1

            continue

        # ----------------------------------------------------
        # NEW
        # ----------------------------------------------------

        result = {
            "id": club_id,
            "name": name,
            "field": field,
            "current": current,
            "candidate": candidate,
            "status": "NEW",
            "verification_reason":
                row.get("reason"),
            "detail":
                row.get("detail"),
        }

        promotion = (
            classify_new_candidate(
                club,
                row,
            )
        )

        result.update(
            promotion
        )

        new_rows.append(
            result
        )

        field_counter[
            field
        ]["NEW"] += 1

        promotion_name = (
            result.get(
                "promotion"
            )
            or "REVIEW"
        )

        promotion_counter[
            field
        ][
            promotion_name
        ] += 1

        if (
            promotion_name
            == "PROMOTE"
        ):

            promote_rows.append(
                result
            )

        elif (
            promotion_name
            == "KEEP_AS_EVIDENCE"
        ):

            evidence_rows.append(
                result
            )

        else:

            review_rows.append(
                result
            )

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

        "source_B_SUPPORTED":
            str(
                source_path
            ),

        "B_SUPPORTED_input":
            len(
                supported_rows
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

        "PROMOTE":
            len(
                promote_rows
            ),

        "KEEP_AS_EVIDENCE":
            len(
                evidence_rows
            ),

        "REVIEW":
            len(
                review_rows
            ),

        "field_counts": {

            field:
                dict(
                    counts
                )

            for field, counts
            in field_counter.items()
        },

        "promotion_counts": {

            field:
                dict(
                    counts
                )

            for field, counts
            in promotion_counter.items()
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

    save_json(
        run
        / "PROMOTE.json",
        promote_rows,
    )

    save_json(
        run
        / "KEEP_AS_EVIDENCE.json",
        evidence_rows,
    )

    save_json(
        run
        / "REVIEW.json",
        review_rows,
    )

    # ========================================================
    # REPORT
    # ========================================================

    report = []

    report.append(
        "# Golf Master B_SUPPORTED DRY RUN"
    )

    report.append("")

    report.append(
        f"- B_SUPPORTED 입력: "
        f"{len(supported_rows)}"
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
        "## NEW 재분류"
    )

    report.append("")

    report.append(
        f"- PROMOTE: "
        f"{len(promote_rows)}"
    )

    report.append(
        f"- KEEP_AS_EVIDENCE: "
        f"{len(evidence_rows)}"
    )

    report.append(
        f"- REVIEW: "
        f"{len(review_rows)}"
    )

    report.append("")

    report.append(
        "## 필드별"
    )

    report.append("")

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

        promotions = (
            promotion_counter.get(
                field,
                Counter(),
            )
        )

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

        report.append(
            f"- PROMOTE: "
            f"{promotions.get('PROMOTE', 0)}"
        )

        report.append(
            f"- KEEP_AS_EVIDENCE: "
            f"{promotions.get('KEEP_AS_EVIDENCE', 0)}"
        )

        report.append(
            f"- REVIEW: "
            f"{promotions.get('REVIEW', 0)}"
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
        "B_SUPPORTED DRY RUN COMPLETE"
    )

    print(
        "=" * 78
    )

    print()

    print(
        "B_SUPPORTED 입력:",
        len(supported_rows)
    )

    print()

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
        "[NEW 재분류]"
    )

    print(
        "PROMOTE:",
        len(promote_rows)
    )

    print(
        "KEEP_AS_EVIDENCE:",
        len(evidence_rows)
    )

    print(
        "REVIEW:",
        len(review_rows)
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

        promotions = (
            promotion_counter.get(
                field,
                Counter(),
            )
        )

        print()

        print(
            field
        )

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

        print(
            "  → PROMOTE:",
            promotions.get(
                "PROMOTE",
                0,
            )
        )

        print(
            "  → KEEP_AS_EVIDENCE:",
            promotions.get(
                "KEEP_AS_EVIDENCE",
                0,
            )
        )

        print(
            "  → REVIEW:",
            promotions.get(
                "REVIEW",
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
        "실제 반영 검토 대상:"
    )

    print(
        run
        / "PROMOTE.json"
    )

    print()

    print(
        "근거 보관 대상:"
    )

    print(
        run
        / "KEEP_AS_EVIDENCE.json"
    )

    print()

    print(
        "추가 검토 대상:"
    )

    print(
        run
        / "REVIEW.json"
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