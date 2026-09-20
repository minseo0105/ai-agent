# -*- coding: utf-8 -*-

"""
Golf Master Verifier v1
============================================================

목적
------------------------------------------------------------
Golf Master Pipeline v3.1에서 수집한 전체 검색결과를
현재 catalog.json + 공공데이터 + KGA + verified_basic_info와
필드 단위로 비교/검증한다.

중요
------------------------------------------------------------
1. catalog.json 수정하지 않음
2. Tavily 추가 호출 없음
3. LLM 호출 없음
4. 553개 전체 자동 검토
5. 공식 URL은 제3자 사이트를 공식 홈페이지로 인정하지 않음
6. booking_url은 공식 도메인 또는 이미 검증된 경우만 강한 후보
7. holes는 총 홀수 표현이 명확한 경우만 후보
8. operation_type은 단순 키워드 동시출현으로 혼합 판정하지 않음
9. 기존 값과 충돌하면 자동 반영하지 않음
10. 결과를 VERIFIED / REVIEW / CONFLICT / HOLD로 분류
11. 이번 버전은 DRY RUN ONLY

실행
------------------------------------------------------------

.\venv\Scripts\python.exe .\golf_master_verifier_v1.py
"""


from __future__ import annotations

import hashlib
import json
import re

from collections import Counter, defaultdict
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

PIPELINE_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "pipeline_v3_1"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "verifier_v1"
)


# ============================================================
# CONFIG
# ============================================================

EXPECTED_CATALOG_COUNT = 553

VERIFIER_VERSION = "1.0"


FIELDS = (
    "official_url",
    "booking_url",
    "holes",
    "operation_type",
    "phone",
)


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


# ============================================================
# THIRD PARTY
# ============================================================

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
    "w.baigolf.com",

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

    "saramin.co.kr",
    "jobkorea.co.kr",
    "wanted.co.kr",
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


def load_json(path: Path) -> Any:

    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def save_json(
    path: Path,
    data: Any,
) -> None:

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


def sha256_bytes(data: bytes) -> str:

    return hashlib.sha256(
        data
    ).hexdigest()


# ============================================================
# URL HELPERS
# ============================================================

def domain_of(url: str) -> str:

    try:

        domain = (
            urlparse(url)
            .netloc
            .lower()
            .split(":")[0]
        )

        if domain.startswith("www."):

            domain = domain[4:]

        return domain

    except Exception:

        return ""


def normalize_domain(url: str) -> str:

    return domain_of(
        clean(url)
    )


def is_third_party(url: str) -> bool:

    domain = normalize_domain(url)

    if not domain:

        return True

    for blocked in THIRD_PARTY_DOMAINS:

        if (
            domain == blocked
            or domain.endswith(
                "." + blocked
            )
        ):

            return True

    return False


def same_domain(
    url1: str,
    url2: str,
) -> bool:

    d1 = normalize_domain(url1)

    d2 = normalize_domain(url2)

    if not d1 or not d2:
        return False

    if d1 == d2:
        return True

    if d1.endswith("." + d2):
        return True

    if d2.endswith("." + d1):
        return True

    return False


# ============================================================
# PHONE
# ============================================================

def normalize_phone(
    value: Any,
) -> str:

    return re.sub(
        r"\D",
        "",
        clean(value),
    )


def same_phone(
    a: Any,
    b: Any,
) -> bool:

    aa = normalize_phone(a)

    bb = normalize_phone(b)

    if (
        len(aa) < 8
        or len(bb) < 8
    ):
        return False

    return aa == bb


# ============================================================
# OPERATION
# ============================================================

def normalize_operation(
    value: Any,
):

    text = clean(value)

    if not text:
        return None

    if text in (
        "대중제",
        "비회원제",
        "퍼블릭",
        "대중제_명시",
    ):

        return "대중제"

    if text in (
        "회원제",
        "회원제_명시",
    ):

        return "회원제"

    if text in (
        "혼합",
        "혼합형",
        "회원제+대중제",
        "혼합_홀수명시",
    ):

        return "혼합"

    return None


# ============================================================
# PUBLIC DATA
# ============================================================

def public_data(
    club: dict,
) -> dict:

    return (
        (
            club.get("verification")
            or {}
        )
        .get("public_data")
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

        value = pub.get(key)

        if has_value(value):

            return value

    return None


def public_operation(
    club: dict,
):

    pub = public_data(
        club
    )

    if pub.get("matched") is not True:

        return None

    value = (
        pub.get("business_type")
        or pub.get(
            "DTL_SALS_STTS_NM"
        )
    )

    return normalize_operation(
        value
    )


# ============================================================
# VERIFIED BASIC INFO
# ============================================================

def verified_basic(
    club: dict,
    field: str,
):

    data = (
        club.get(
            "verified_basic_info"
        )
        or {}
    )

    item = data.get(
        field
    )

    if not isinstance(
        item,
        dict,
    ):

        return None

    for key in (
        "value",
        "verified_value",
    ):

        value = item.get(key)

        if has_value(value):

            return value

    if (
        item.get("verified") is True
        and has_value(
            club.get(field)
        )
    ):

        return club.get(field)

    if (
        item.get("confidence")
        in ("A", "VERIFIED")
        and has_value(
            club.get(field)
        )
    ):

        return club.get(field)

    return None


# ============================================================
# FIND LATEST PIPELINE RESULT
# ============================================================

def find_latest_pipeline_result() -> Path:

    if not PIPELINE_ROOT.exists():

        raise RuntimeError(
            f"pipeline 폴더 없음: "
            f"{PIPELINE_ROOT}"
        )

    candidates = []

    for path in (
        PIPELINE_ROOT.rglob(
            "result_*.json"
        )
    ):

        try:

            data = load_json(
                path
            )

        except Exception:

            continue

        if not isinstance(
            data,
            dict,
        ):

            continue

        if (
            data.get(
                "complete"
            )
            is True
            and data.get(
                "catalog_count"
            )
            == EXPECTED_CATALOG_COUNT
        ):

            candidates.append(
                path
            )

    if not candidates:

        raise RuntimeError(
            "완료된 pipeline_v3_1 "
            "result 파일을 찾지 못했습니다."
        )

    return max(
        candidates,
        key=lambda path:
            path.stat().st_mtime,
    )


# ============================================================
# CURRENT VALUE
# ============================================================

def current_value(
    club: dict,
    field: str,
):

    verified = verified_basic(
        club,
        field,
    )

    if has_value(verified):

        return verified

    direct = club.get(
        field
    )

    if has_value(direct):

        return direct

    if field == "phone":

        value = public_phone(
            club
        )

        if has_value(value):

            return value

    if field == "operation_type":

        value = public_operation(
            club
        )

        if has_value(value):

            return value

    return None


# ============================================================
# CURRENT SOURCE
# ============================================================

def current_source(
    club: dict,
    field: str,
):

    if has_value(
        verified_basic(
            club,
            field,
        )
    ):

        return "verified_basic_info"

    if has_value(
        club.get(field)
    ):

        return "catalog"

    if (
        field == "phone"
        and has_value(
            public_phone(
                club
            )
        )
    ):

        return "public_data"

    if (
        field == "operation_type"
        and has_value(
            public_operation(
                club
            )
        )
    ):

        return "public_data"

    return None


# ============================================================
# PIPELINE CLUB INDEX
# ============================================================

def pipeline_index(
    pipeline: dict,
) -> dict[str, dict]:

    index = {}

    for row in (
        pipeline.get("clubs")
        or []
    ):

        if not isinstance(
            row,
            dict,
        ):
            continue

        club_id = clean(
            row.get("id")
        )

        if club_id:

            index[
                club_id
            ] = row

    return index


# ============================================================
# CANDIDATE LIST
# ============================================================

def get_candidates(
    pipeline_row: dict,
    field: str,
) -> list[dict]:

    fields = (
        pipeline_row.get(
            "field_candidates"
        )
        or {}
    )

    values = fields.get(
        field
    )

    if not isinstance(
        values,
        list,
    ):

        return []

    return [
        x
        for x in values
        if isinstance(x, dict)
    ]


# ============================================================
# AGREEMENT
# ============================================================

def values_agree(
    field: str,
    a: Any,
    b: Any,
) -> bool:

    if not has_value(a):
        return False

    if not has_value(b):
        return False

    if field in (
        "official_url",
        "booking_url",
    ):

        return same_domain(
            clean(a),
            clean(b),
        )

    if field == "phone":

        return same_phone(
            a,
            b,
        )

    if field == "holes":

        try:

            return (
                int(a)
                == int(b)
            )

        except Exception:

            return False

    if field == "operation_type":

        return (
            normalize_operation(a)
            == normalize_operation(b)
        )

    return (
        clean(a).lower()
        == clean(b).lower()
    )


# ============================================================
# UNIQUE CANDIDATES
# ============================================================

def unique_candidates(
    field: str,
    candidates: list[dict],
) -> list[dict]:

    output = []

    seen = set()

    for item in candidates:

        value = item.get(
            "value"
        )

        if not has_value(value):

            continue

        if field in (
            "official_url",
            "booking_url",
        ):

            key = normalize_domain(
                clean(value)
            )

            if not key:
                continue

        elif field == "phone":

            key = normalize_phone(
                value
            )

            if not key:
                continue

        elif field == "operation_type":

            key = normalize_operation(
                value
            )

            if not key:
                continue

        else:

            key = str(
                value
            )

        if key in seen:

            continue

        seen.add(
            key
        )

        output.append(
            item
        )

    return output


# ============================================================
# OFFICIAL URL VERIFY
# ============================================================

def verify_official_url(
    club: dict,
    pipeline_row: dict,
) -> dict:

    current = current_value(
        club,
        "official_url",
    )

    source = current_source(
        club,
        "official_url",
    )

    candidates = unique_candidates(
        "official_url",
        get_candidates(
            pipeline_row,
            "official_url",
        ),
    )

    # 제3자 사이트 제거
    safe = [

        item

        for item in candidates

        if (
            has_value(
                item.get("value")
            )
            and not is_third_party(
                clean(
                    item.get("value")
                )
            )
        )
    ]

    # 기존 검증값 우선
    if (
        source
        == "verified_basic_info"
        and has_value(current)
    ):

        return {
            "status": "VERIFIED",
            "value": current,
            "reason": "existing_verified_basic_info",
            "source": source,
        }

    # 현재 공식 URL과 검색 후보 동일 도메인
    if has_value(current):

        agreeing = [

            item

            for item in safe

            if same_domain(
                clean(current),
                clean(
                    item.get("value")
                ),
            )
        ]

        if agreeing:

            return {
                "status": "VERIFIED",
                "value": current,
                "reason": "current_url_supported_by_web",
                "source": source,
                "evidence": agreeing[:3],
            }

        # 현재값이 제3자면 충돌
        if is_third_party(
            clean(current)
        ):

            return {
                "status": "CONFLICT",
                "value": current,
                "reason": "current_url_is_third_party",
                "source": source,
                "candidates": safe[:5],
            }

        return {
            "status": "REVIEW",
            "value": current,
            "reason": "current_url_not_independently_confirmed",
            "source": source,
            "candidates": safe[:5],
        }

    # 값이 없고 검색 결과가 하나의 도메인으로 수렴
    strong = [

        item

        for item in safe

        if item.get(
            "confidence"
        )
        == "A_CANDIDATE"
    ]

    domains = {
        normalize_domain(
            clean(
                item.get("value")
            )
        )
        for item in strong
        if normalize_domain(
            clean(
                item.get("value")
            )
        )
    }

    if (
        len(domains) == 1
        and strong
    ):

        best = strong[0]

        return {
            "status": "REVIEW",
            "value": best.get("value"),
            "reason": "single_strong_official_domain_candidate",
            "source": "web_candidate",
            "evidence": strong[:5],
        }

    if len(domains) > 1:

        return {
            "status": "CONFLICT",
            "value": None,
            "reason": "multiple_official_domain_candidates",
            "candidates": strong[:8],
        }

    return {
        "status": "HOLD",
        "value": None,
        "reason": "no_safe_official_candidate",
        "candidates": safe[:5],
    }


# ============================================================
# BOOKING URL VERIFY
# ============================================================

def verify_booking_url(
    club: dict,
    pipeline_row: dict,
    official_result: dict,
) -> dict:

    current = current_value(
        club,
        "booking_url",
    )

    source = current_source(
        club,
        "booking_url",
    )

    if (
        source
        == "verified_basic_info"
        and has_value(current)
    ):

        return {
            "status": "VERIFIED",
            "value": current,
            "reason": "existing_verified_booking",
            "source": source,
        }

    official_url = (
        official_result.get("value")
        or current_value(
            club,
            "official_url",
        )
    )

    candidates = unique_candidates(
        "booking_url",
        get_candidates(
            pipeline_row,
            "booking_url",
        ),
    )

    safe = []

    for item in candidates:

        url = clean(
            item.get("value")
        )

        if not url:
            continue

        if is_third_party(url):
            continue

        # 공식 홈페이지와 같은 도메인일 때만
        # 강한 예약페이지 후보
        if (
            has_value(official_url)
            and same_domain(
                url,
                clean(official_url),
            )
        ):

            safe.append(
                item
            )

    if has_value(current):

        if (
            has_value(official_url)
            and same_domain(
                clean(current),
                clean(official_url),
            )
        ):

            return {
                "status": "VERIFIED",
                "value": current,
                "reason": "booking_on_official_domain",
                "source": source,
            }

        return {
            "status": "REVIEW",
            "value": current,
            "reason": "existing_booking_not_on_confirmed_official_domain",
            "source": source,
            "candidates": safe[:5],
        }

    if safe:

        strong = [

            item

            for item in safe

            if item.get(
                "confidence"
            )
            == "A_CANDIDATE"
        ]

        if strong:

            return {
                "status": "REVIEW",
                "value": strong[0].get(
                    "value"
                ),
                "reason": "booking_candidate_on_official_domain",
                "source": "web_candidate",
                "evidence": strong[:5],
            }

    return {
        "status": "HOLD",
        "value": None,
        "reason": "no_verified_booking_page",
        "candidates": safe[:5],
    }


# ============================================================
# HOLES VERIFY
# ============================================================

def verify_holes(
    club: dict,
    pipeline_row: dict,
) -> dict:

    current = current_value(
        club,
        "holes",
    )

    source = current_source(
        club,
        "holes",
    )

    candidates = unique_candidates(
        "holes",
        get_candidates(
            pipeline_row,
            "holes",
        ),
    )

    if (
        source
        == "verified_basic_info"
        and has_value(current)
    ):

        return {
            "status": "VERIFIED",
            "value": current,
            "reason": "existing_verified_holes",
            "source": source,
        }

    candidate_values = []

    for item in candidates:

        try:

            number = int(
                item.get("value")
            )

        except Exception:

            continue

        if (
            number >= 9
            and number <= 144
            and number % 9 == 0
        ):

            candidate_values.append(
                number
            )

    counts = Counter(
        candidate_values
    )

    if has_value(current):

        try:
            current_int = int(
                current
            )
        except Exception:
            current_int = None

        if (
            current_int is not None
            and counts.get(
                current_int,
                0,
            ) >= 1
        ):

            return {
                "status": "VERIFIED",
                "value": current_int,
                "reason": "current_holes_supported_by_web",
                "source": source,
                "support_count": counts[
                    current_int
                ],
            }

        if (
            counts
            and current_int is not None
            and current_int
            not in counts
        ):

            return {
                "status": "CONFLICT",
                "value": current_int,
                "reason": "current_holes_conflicts_with_web",
                "source": source,
                "candidate_counts": dict(
                    counts
                ),
            }

        return {
            "status": "REVIEW",
            "value": current,
            "reason": "existing_holes_not_confirmed",
            "source": source,
            "candidate_counts": dict(
                counts
            ),
        }

    # 값 없음
    if not counts:

        return {
            "status": "HOLD",
            "value": None,
            "reason": "no_total_holes_evidence",
        }

    ranked = (
        counts.most_common()
    )

    best_value, best_count = (
        ranked[0]
    )

    # 서로 다른 값이 비슷하게 존재
    if (
        len(ranked) >= 2
        and ranked[1][1]
        == best_count
    ):

        return {
            "status": "CONFLICT",
            "value": None,
            "reason": "multiple_holes_values",
            "candidate_counts": dict(
                counts
            ),
        }

    # 검색 결과 한 건의 18홀 언급만으로
    # 총 홀수 확정하지 않음
    if best_count < 2:

        return {
            "status": "REVIEW",
            "value": best_value,
            "reason": "single_total_holes_evidence",
            "support_count": best_count,
            "candidate_counts": dict(
                counts
            ),
        }

    return {
        "status": "REVIEW",
        "value": best_value,
        "reason": "multiple_web_results_agree_on_holes",
        "support_count": best_count,
        "candidate_counts": dict(
            counts
        ),
    }


# ============================================================
# OPERATION TYPE VERIFY
# ============================================================

def verify_operation(
    club: dict,
    pipeline_row: dict,
) -> dict:

    direct = club.get(
        "operation_type"
    )

    current = (
        normalize_operation(
            current_value(
                club,
                "operation_type",
            )
        )
    )

    source = current_source(
        club,
        "operation_type",
    )

    public = public_operation(
        club
    )

    candidates = unique_candidates(
        "operation_type",
        get_candidates(
            pipeline_row,
            "operation_type",
        ),
    )

    web_values = []

    for item in candidates:

        normalized = (
            normalize_operation(
                item.get("value")
            )
        )

        if normalized:

            web_values.append(
                normalized
            )

    counts = Counter(
        web_values
    )

    # 이미 검증된 값
    if (
        source
        == "verified_basic_info"
        and current
    ):

        return {
            "status": "VERIFIED",
            "value": current,
            "reason": "existing_verified_operation_type",
            "source": source,
        }

    # catalog direct와 public 충돌
    direct_normalized = (
        normalize_operation(
            direct
        )
    )

    if (
        direct_normalized
        and public
        and direct_normalized
        != public
    ):

        return {
            "status": "CONFLICT",
            "value": direct_normalized,
            "reason": "catalog_conflicts_with_public_data",
            "catalog_value": direct_normalized,
            "public_value": public,
            "web_counts": dict(
                counts
            ),
        }

    # public + web 일치
    if public:

        if counts.get(
            public,
            0,
        ) >= 1:

            return {
                "status": "VERIFIED",
                "value": public,
                "reason": "public_data_supported_by_web",
                "source": "public_data+web",
                "web_support_count": counts[
                    public
                ],
            }

        # 웹이 다른 값만 강하게 말하는 경우
        other = {
            key: value
            for key, value
            in counts.items()
            if key != public
        }

        if other:

            return {
                "status": "CONFLICT",
                "value": public,
                "reason": "public_data_conflicts_with_web",
                "public_value": public,
                "web_counts": dict(
                    counts
                ),
            }

        return {
            "status": "VERIFIED",
            "value": public,
            "reason": "exact_public_data_operation_type",
            "source": "public_data",
        }

    # catalog 값 + web
    if current:

        if counts.get(
            current,
            0,
        ) >= 1:

            return {
                "status": "VERIFIED",
                "value": current,
                "reason": "current_operation_supported_by_web",
                "source": source,
            }

        if counts:

            return {
                "status": "CONFLICT",
                "value": current,
                "reason": "current_operation_conflicts_with_web",
                "source": source,
                "web_counts": dict(
                    counts
                ),
            }

        return {
            "status": "REVIEW",
            "value": current,
            "reason": "existing_operation_not_independently_confirmed",
            "source": source,
        }

    # 아무 값도 없음
    if not counts:

        return {
            "status": "HOLD",
            "value": None,
            "reason": "no_operation_type_evidence",
        }

    ranked = counts.most_common()

    if (
        len(ranked) >= 2
        and ranked[0][1]
        == ranked[1][1]
    ):

        return {
            "status": "CONFLICT",
            "value": None,
            "reason": "multiple_operation_types",
            "web_counts": dict(
                counts
            ),
        }

    best, count = ranked[0]

    return {
        "status": "REVIEW",
        "value": best,
        "reason": "web_operation_candidate",
        "support_count": count,
        "web_counts": dict(
            counts
        ),
    }


# ============================================================
# PHONE VERIFY
# ============================================================

def verify_phone(
    club: dict,
    pipeline_row: dict,
) -> dict:

    current = current_value(
        club,
        "phone",
    )

    source = current_source(
        club,
        "phone",
    )

    pub = public_phone(
        club
    )

    candidates = unique_candidates(
        "phone",
        get_candidates(
            pipeline_row,
            "phone",
        ),
    )

    candidate_values = [

        item.get("value")

        for item in candidates

        if has_value(
            item.get("value")
        )
    ]

    # 기존 verified
    if (
        source
        == "verified_basic_info"
        and has_value(current)
    ):

        return {
            "status": "VERIFIED",
            "value": current,
            "reason": "existing_verified_phone",
            "source": source,
        }

    # catalog/public 전화번호와 검색결과 일치
    if has_value(current):

        supporting = [

            value

            for value
            in candidate_values

            if same_phone(
                current,
                value,
            )
        ]

        if supporting:

            return {
                "status": "VERIFIED",
                "value": current,
                "reason": "current_phone_supported_by_web",
                "source": source,
            }

        # 공공데이터 자체가 현재값인 경우
        if (
            has_value(pub)
            and same_phone(
                current,
                pub,
            )
        ):

            return {
                "status": "VERIFIED",
                "value": current,
                "reason": "public_data_phone",
                "source": source,
            }

        return {
            "status": "REVIEW",
            "value": current,
            "reason": "existing_phone_not_confirmed",
            "source": source,
            "candidates": candidate_values[:8],
        }

    # 값 없음
    normalized = defaultdict(
        list
    )

    for value in candidate_values:

        key = normalize_phone(
            value
        )

        if len(key) >= 8:

            normalized[
                key
            ].append(
                value
            )

    if not normalized:

        return {
            "status": "HOLD",
            "value": None,
            "reason": "no_phone_evidence",
        }

    ranked = sorted(
        normalized.items(),
        key=lambda item:
            len(item[1]),
        reverse=True,
    )

    best_key, values = ranked[0]

    if len(values) >= 2:

        return {
            "status": "REVIEW",
            "value": values[0],
            "reason": "multiple_web_results_agree_on_phone",
            "support_count": len(
                values
            ),
        }

    return {
        "status": "REVIEW",
        "value": values[0],
        "reason": "single_phone_candidate",
    }


# ============================================================
# VERIFY ONE CLUB
# ============================================================

def verify_club(
    club: dict,
    pipeline_row: dict,
) -> dict:

    official = (
        verify_official_url(
            club,
            pipeline_row,
        )
    )

    booking = (
        verify_booking_url(
            club,
            pipeline_row,
            official,
        )
    )

    holes = (
        verify_holes(
            club,
            pipeline_row,
        )
    )

    operation = (
        verify_operation(
            club,
            pipeline_row,
        )
    )

    phone = (
        verify_phone(
            club,
            pipeline_row,
        )
    )

    fields = {
        "official_url": official,
        "booking_url": booking,
        "holes": holes,
        "operation_type": operation,
        "phone": phone,
    }

    statuses = [
        item.get("status")
        for item
        in fields.values()
    ]

    if "CONFLICT" in statuses:

        overall = "CONFLICT"

    elif "REVIEW" in statuses:

        overall = "REVIEW"

    elif "HOLD" in statuses:

        overall = "PARTIAL"

    else:

        overall = "VERIFIED"

    return {
        "id": clean(
            club.get("id")
        ),
        "name": clean(
            club.get("name")
        ),
        "address": clean(
            club.get("address")
        ),
        "overall_status": overall,
        "fields": fields,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 78)
    print("Golf Master Verifier v1")
    print("=" * 78)

    # --------------------------------------------------------
    # catalog
    # --------------------------------------------------------

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
            f"안전 중단: "
            f"catalog={len(catalog)} / "
            f"예상={EXPECTED_CATALOG_COUNT}"
        )

    print(
        "현재 catalog:",
        len(catalog),
        "개"
    )

    # --------------------------------------------------------
    # pipeline result
    # --------------------------------------------------------

    pipeline_path = (
        find_latest_pipeline_result()
    )

    print(
        "사용 Pipeline 결과:"
    )

    print(
        pipeline_path
    )

    pipeline = load_json(
        pipeline_path
    )

    if (
        pipeline.get(
            "complete"
        )
        is not True
    ):

        raise RuntimeError(
            "Pipeline 결과가 완료 상태가 아닙니다."
        )

    if (
        pipeline.get(
            "catalog_count"
        )
        != EXPECTED_CATALOG_COUNT
    ):

        raise RuntimeError(
            "Pipeline catalog_count 불일치"
        )

    pindex = (
        pipeline_index(
            pipeline
        )
    )

    print(
        "Pipeline 골프장:",
        len(pindex),
        "개"
    )

    # --------------------------------------------------------
    # verify
    # --------------------------------------------------------

    results = []

    overall_counter = Counter()

    field_counter = {
        field: Counter()
        for field in FIELDS
    }

    print()
    print("553개 전체 검증 중...")

    for position, club in enumerate(
        catalog,
        start=1,
    ):

        club_id = clean(
            club.get("id")
        )

        pipeline_row = (
            pindex.get(
                club_id
            )
            or {}
        )

        result = (
            verify_club(
                club,
                pipeline_row,
            )
        )

        result[
            "catalog_position"
        ] = position

        results.append(
            result
        )

        overall_counter[
            result[
                "overall_status"
            ]
        ] += 1

        for field in FIELDS:

            status = (
                result[
                    "fields"
                ][field]
                .get("status")
            )

            field_counter[
                field
            ][status] += 1

    # --------------------------------------------------------
    # output
    # --------------------------------------------------------

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

    output = {
        "verifier_version": VERIFIER_VERSION,
        "created_at": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),
        "mode": "DRY_RUN_ONLY",
        "catalog_count": len(
            catalog
        ),
        "catalog_sha256": (
            original_hash
        ),
        "catalog_modified": False,
        "pipeline_result": str(
            pipeline_path
        ),
        "overall_counts": dict(
            overall_counter
        ),
        "field_counts": {
            field: dict(
                counts
            )
            for field, counts
            in field_counter.items()
        },
        "clubs": results,
    }

    result_path = (
        run
        / "verification_result.json"
    )

    save_json(
        result_path,
        output,
    )

    # --------------------------------------------------------
    # conflict list
    # --------------------------------------------------------

    conflicts = []

    reviews = []

    verified = []

    for club in results:

        for field, info in (
            club["fields"].items()
        ):

            row = {
                "id": club["id"],
                "name": club["name"],
                "field": field,
                "status": info.get(
                    "status"
                ),
                "value": info.get(
                    "value"
                ),
                "reason": info.get(
                    "reason"
                ),
                "detail": info,
            }

            if (
                info.get("status")
                == "CONFLICT"
            ):

                conflicts.append(
                    row
                )

            elif (
                info.get("status")
                == "REVIEW"
            ):

                reviews.append(
                    row
                )

            elif (
                info.get("status")
                == "VERIFIED"
            ):

                verified.append(
                    row
                )

    save_json(
        run
        / "conflicts.json",
        conflicts,
    )

    save_json(
        run
        / "review_candidates.json",
        reviews,
    )

    save_json(
        run
        / "verified_fields.json",
        verified,
    )

    # --------------------------------------------------------
    # report
    # --------------------------------------------------------

    lines = []

    lines.append(
        "# Golf Master Verifier v1"
    )

    lines.append("")

    lines.append(
        "## 전체"
    )

    lines.append("")

    for key, value in (
        overall_counter.items()
    ):

        lines.append(
            f"- {key}: {value}"
        )

    lines.append("")

    lines.append(
        "## 필드별"
    )

    lines.append("")

    for field in FIELDS:

        lines.append(
            f"### {field}"
        )

        for status, count in (
            field_counter[
                field
            ].items()
        ):

            lines.append(
                f"- {status}: {count}"
            )

        lines.append("")

    lines.append(
        "## 주의"
    )

    lines.append("")

    lines.append(
        "- 이번 실행은 catalog.json을 수정하지 않습니다."
    )

    lines.append(
        "- REVIEW는 자동 반영 대상이 아닙니다."
    )

    lines.append(
        "- CONFLICT는 반드시 기존값과 출처를 다시 확인해야 합니다."
    )

    lines.append(
        "- official_url은 제3자 페이지를 공식 홈페이지로 인정하지 않습니다."
    )

    lines.append(
        "- booking_url은 공식 도메인 확인을 우선합니다."
    )

    lines.append(
        "- 홀수는 검색결과의 단순 18홀 언급만으로 총 홀수를 확정하지 않습니다."
    )

    lines.append(
        "- 운영형태는 단순 키워드 혼재로 혼합형을 만들지 않습니다."
    )

    (
        run
        / "report.md"
    ).write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # catalog unchanged
    # --------------------------------------------------------

    if (
        CATALOG_PATH.read_bytes()
        != original_bytes
    ):

        raise RuntimeError(
            "안전 중단: "
            "catalog.json 변경 감지"
        )

    # --------------------------------------------------------
    # console
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("VERIFIER DRY RUN COMPLETE")
    print("=" * 78)

    print()
    print("[전체 판정]")

    for status in (
        "VERIFIED",
        "REVIEW",
        "PARTIAL",
        "CONFLICT",
    ):

        print(
            f"{status}: "
            f"{overall_counter.get(status, 0)}"
        )

    print()
    print("[필드별]")

    for field in FIELDS:

        counts = (
            field_counter[
                field
            ]
        )

        print()
        print(field)

        for status in (
            "VERIFIED",
            "REVIEW",
            "CONFLICT",
            "HOLD",
        ):

            print(
                f"  {status}: "
                f"{counts.get(status, 0)}"
            )

    print()
    print(
        "VERIFIED 필드:",
        len(verified)
    )

    print(
        "REVIEW 필드:",
        len(reviews)
    )

    print(
        "CONFLICT 필드:",
        len(conflicts)
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
        "결과:",
        result_path
    )

    print(
        "검증완료:",
        run
        / "verified_fields.json"
    )

    print(
        "추가검토:",
        run
        / "review_candidates.json"
    )

    print(
        "충돌:",
        run
        / "conflicts.json"
    )

    print(
        "보고서:",
        run
        / "report.md"
    )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()