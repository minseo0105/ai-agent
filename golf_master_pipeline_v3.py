# -*- coding: utf-8 -*-
"""
Golf Master Pipeline v3
============================================================

목적
------------------------------------------------------------
전국 골프장 Master DB를 빠르고 안전하게 보강하기 위한 수집/판정 파이프라인.

핵심 원칙
------------------------------------------------------------
1. catalog.json 직접 수정 금지
2. 현재 553개 catalog 전체 대상
3. 이미 있는 공공데이터 / KGA / 검증값 우선 사용
4. 부족한 필드만 Tavily 검색
5. 50개 단위 수동 작업 없음
6. 한 골프장 처리할 때마다 checkpoint 저장
7. 중단 후 다시 실행하면 이어서 진행
8. 검색 결과는 필드별 A / B / HOLD 후보로 저장
9. A라고 해도 이 스크립트에서는 catalog에 반영하지 않음
10. 후기 분석은 별도 단계에서 수행

실행
------------------------------------------------------------

진단만:
python golf_master_pipeline_v3.py

실제 검색:
python golf_master_pipeline_v3.py --search

검색 최대 호출 수 제한:
python golf_master_pipeline_v3.py --search --max-calls 100

처음부터 새 검색 세션:
python golf_master_pipeline_v3.py --search --new-run

주의
------------------------------------------------------------
이 스크립트는 catalog.json을 절대 수정하지 않습니다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


# ============================================================
# 기본 경로
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
    / "pipeline_v3"
)

SECRETS_PATH = (
    ROOT
    / ".streamlit"
    / "secrets.toml"
)


# ============================================================
# 기본 설정
# ============================================================

EXPECTED_CATALOG_COUNT = 553

PIPELINE_VERSION = "3.0"

SEARCH_DEPTH = "basic"

MAX_RESULTS = 6

REQUEST_TIMEOUT = 25

REQUEST_DELAY = 0.65

DEFAULT_MAX_CALLS = 120


# ============================================================
# 검색 대상 필드
# ============================================================

TARGET_FIELDS = (
    "operation_type",
    "holes",
    "courses",
    "official_url",
    "booking_url",
    "phone",
)


# ============================================================
# 운영형태에서 '값 없음'으로 처리할 표현
# ============================================================

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
# 제3자 도메인
#
# 중요:
# 이 사이트들이 나쁘다는 의미가 아니다.
# official_url의 근거로 자동 확정하지 않는다는 의미.
# ============================================================

THIRD_PARTY_DOMAINS = {

    # 검색 / 포털
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

    # SNS
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "facebook.com",

    # 골프 플랫폼 / 예약 / 정보
    "golfzon.com",
    "xgolf.com",
    "kimcaddie.com",
    "golfu.net",
    "baigolf.com",
    "w.baigolf.com",

    # FIRST 50에서 실제 오판 사례 계열
    "golf.sbs.co.kr",
    "sbs.co.kr",
    "dbegl.com",
    "grandculture.net",
    "knps.or.kr",

    # 회원권/여행/정보
    "premiumgolf.co.kr",
    "czgolf.kr",
    "hanjingolf.com",
    "yesgolf.co.kr",
    "trip.com",
    "kr.trip.com",

    # 구인/기업정보
    "saramin.co.kr",
    "jobkorea.co.kr",
    "wanted.co.kr",
}


# ============================================================
# 공식 사이트로 보기 위험한 URL path
# ============================================================

BAD_OFFICIAL_PATH_WORDS = (
    "/blog/",
    "/news/",
    "/article/",
    "/post/",
    "/community/",
)


# ============================================================
# 예약 페이지 힌트
# ============================================================

BOOKING_HINTS = (
    "reservation",
    "reserve",
    "booking",
    "bookinglist",
    "golf-reservation",
    "golfreservation",
    "예약",
)


# ============================================================
# JSON helpers
# ============================================================

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

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp.replace(path)


def sha256_bytes(data: bytes) -> str:

    return hashlib.sha256(
        data
    ).hexdigest()


# ============================================================
# 문자열
# ============================================================

def clean(value: Any) -> str:

    if value is None:
        return ""

    return str(
        value
    ).strip()


def has_value(value: Any) -> bool:

    if value is None:
        return False

    if isinstance(
        value,
        str,
    ):

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


def normalize_text(value: Any) -> str:

    text = clean(
        value
    ).lower()

    text = re.sub(
        r"\s+",
        "",
        text,
    )

    return re.sub(
        r"[^0-9a-z가-힣]",
        "",
        text,
    )


def normalize_name(value: Any) -> str:

    text = normalize_text(
        value
    )

    remove_tokens = (

        "골프클럽",
        "컨트리클럽",
        "countryclub",
        "golfclub",

        "country",
        "golf",

        "클럽",

        "cc",
        "gc",
    )

    for token in remove_tokens:

        text = text.replace(
            token,
            "",
        )

    return text


# ============================================================
# URL / Domain
# ============================================================

def domain_of(url: str) -> str:

    try:

        domain = (
            urlparse(url)
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


def is_third_party_domain(
    url: str,
) -> bool:

    domain = domain_of(
        url
    )

    if not domain:
        return True

    for blocked in THIRD_PARTY_DOMAINS:

        blocked = blocked.replace(
            "www.",
            ""
        )

        if (
            domain == blocked
            or domain.endswith(
                "." + blocked
            )
        ):

            return True

    return False


def suspicious_official_path(
    url: str,
) -> bool:

    try:

        path = (
            urlparse(url)
            .path
            .lower()
        )

    except Exception:

        return True

    return any(
        word in path
        for word in BAD_OFFICIAL_PATH_WORDS
    )


def looks_like_booking_url(
    url: str,
    title: str = "",
) -> bool:

    blob = (
        clean(url)
        + " "
        + clean(title)
    ).lower()

    return any(
        hint in blob
        for hint in BOOKING_HINTS
    )


# ============================================================
# secrets.toml
# ============================================================

def load_tavily_key() -> str:

    if not SECRETS_PATH.exists():

        raise RuntimeError(
            f"secrets 파일이 없습니다: "
            f"{SECRETS_PATH}"
        )

    raw = SECRETS_PATH.read_text(
        encoding="utf-8"
    )

    # tomllib가 있으면 정상 파싱
    try:

        import tomllib

        data = tomllib.loads(raw)

        key = clean(
            data.get(
                "TAVILY_API_KEY"
            )
        )

        if key:
            return key

    except Exception:
        pass

    # fallback
    match = re.search(
        r'(?m)^\s*TAVILY_API_KEY\s*=\s*["\']([^"\']+)["\']',
        raw,
    )

    if match:

        return match.group(
            1
        ).strip()

    raise RuntimeError(
        "TAVILY_API_KEY를 "
        ".streamlit/secrets.toml에서 찾지 못했습니다."
    )


# ============================================================
# catalog helper
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


def kga_data(
    club: dict,
) -> dict:

    return (
        club.get(
            "kga"
        )
        or {}
    )


def verified_basic_info(
    club: dict,
) -> dict:

    return (
        club.get(
            "verified_basic_info"
        )
        or {}
    )


# ============================================================
# 기존 검증 여부
# ============================================================

def field_verified(
    club: dict,
    field: str,
) -> bool:

    verified = verified_basic_info(
        club
    )

    item = verified.get(
        field
    )

    if isinstance(
        item,
        dict,
    ):

        if (
            item.get("verified") is True
            or item.get("confidence") == "A"
        ):

            return True

    return False


# ============================================================
# 기존 DB에서 안전하게 확보 가능한 정보
#
# 여기서는 catalog를 수정하지 않고
# 진단할 때만 사용.
# ============================================================

def effective_value(
    club: dict,
    field: str,
) -> Any:

    direct = club.get(
        field
    )

    if has_value(
        direct
    ):

        return direct

    public = public_data(
        club
    )

    kga = kga_data(
        club
    )

    # --------------------------------------------------------
    # 전화
    # --------------------------------------------------------

    if field == "phone":

        value = public.get(
            "phone"
        )

        if has_value(value):

            return value

    # --------------------------------------------------------
    # 코스
    # KGA course_combinations는 실제 물리 코스목록과
    # 동일하다고 보장할 수 없으므로 여기서는
    # '있다'고 간주하지 않는다.
    # --------------------------------------------------------

    if field == "courses":

        return None

    # --------------------------------------------------------
    # 운영형태
    #
    # public business_type은 진단 참고만.
    # direct field를 자동 대체하지 않는다.
    # --------------------------------------------------------

    if field == "operation_type":

        return None

    return None


# ============================================================
# 어떤 필드가 부족한가
# ============================================================

def missing_fields(
    club: dict,
) -> list[str]:

    missing = []

    for field in TARGET_FIELDS:

        value = effective_value(
            club,
            field,
        )

        if not has_value(
            value
        ):

            missing.append(
                field
            )

    return missing


# ============================================================
# 검색 필요도
# ============================================================

def needs_web_search(
    club: dict,
) -> bool:

    missing = missing_fields(
        club
    )

    if not missing:

        return False

    # --------------------------------------------------------
    # public/KGA만으로도 보조 근거가 있지만
    # official/booking/holes/op/courses 부족하면
    # 웹 조사 가치 있음.
    # --------------------------------------------------------

    web_fields = {
        "operation_type",
        "holes",
        "courses",
        "official_url",
        "booking_url",
        "phone",
    }

    return bool(
        web_fields.intersection(
            missing
        )
    )


# ============================================================
# Search Plan
#
# 한 골프장당 무조건 여러 번 검색하지 않는다.
# 1차 profile 검색을 기본으로 하고
# booking이 필요하면서 1차 결과가 약할 때만
# 2차 검색.
# ============================================================

def make_profile_query(
    club: dict,
) -> str:

    name = clean(
        club.get(
            "name"
        )
    )

    address = clean(
        club.get(
            "address"
        )
    )

    locality = ""

    if address:

        parts = address.split()

        locality = " ".join(
            parts[:3]
        )

    return (
        f'"{name}" {locality} '
        f'골프장 공식 홈페이지 '
        f'코스소개 총 홀수 '
        f'회원제 대중제 전화'
    ).strip()


def make_booking_query(
    club: dict,
) -> str:

    name = clean(
        club.get(
            "name"
        )
    )

    address = clean(
        club.get(
            "address"
        )
    )

    locality = ""

    if address:

        locality = " ".join(
            address.split()[:2]
        )

    return (
        f'"{name}" {locality} '
        f'공식 예약 reservation'
    ).strip()


# ============================================================
# Tavily
# ============================================================

def tavily_search(
    api_key: str,
    query: str,
) -> list[dict]:

    response = requests.post(

        "https://api.tavily.com/search",

        json={

            "api_key":
                api_key,

            "query":
                query,

            "search_depth":
                SEARCH_DEPTH,

            "max_results":
                MAX_RESULTS,
        },

        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    results = []

    for item in (
        data.get(
            "results"
        )
        or []
    ):

        results.append({

            "title":
                clean(
                    item.get(
                        "title"
                    )
                ),

            "url":
                clean(
                    item.get(
                        "url"
                    )
                ),

            "content":
                clean(
                    item.get(
                        "content"
                    )
                ),

            "score":
                item.get(
                    "score"
                ),
        })

    return results


# ============================================================
# Identity
#
# 주의:
# 이것은 '공식사이트 점수'가 아니다.
# 검색 결과가 동일 골프장일 가능성 평가.
# ============================================================

def identity_evidence(
    club: dict,
    result: dict,
) -> dict:

    name = clean(
        club.get(
            "name"
        )
    )

    address = clean(
        club.get(
            "address"
        )
    )

    phone = clean(
        club.get(
            "phone"
        )
    )

    title = clean(
        result.get(
            "title"
        )
    )

    content = clean(
        result.get(
            "content"
        )
    )

    url = clean(
        result.get(
            "url"
        )
    )

    blob = (
        title
        + " "
        + content
        + " "
        + url
    ).lower()

    score = 0

    reasons = []

    # --------------------------------------------------------
    # 이름
    # --------------------------------------------------------

    normalized_name = normalize_name(
        name
    )

    normalized_result = normalize_name(
        title + " " + content
    )

    if (
        normalized_name
        and normalized_name
        in normalized_result
    ):

        score += 4

        reasons.append(
            "name_match"
        )

    # --------------------------------------------------------
    # 주소
    # --------------------------------------------------------

    if address:

        address_tokens = [

            token
            for token
            in address.split()

            if len(token) >= 2
        ]

        hits = sum(

            1
            for token
            in address_tokens[:6]

            if token.lower()
            in blob
        )

        if hits >= 3:

            score += 4

            reasons.append(
                "address_strong"
            )

        elif hits >= 2:

            score += 3

            reasons.append(
                "address_match"
            )

        elif hits == 1:

            score += 1

            reasons.append(
                "address_partial"
            )

    # --------------------------------------------------------
    # 전화
    # --------------------------------------------------------

    if phone:

        phone_digits = re.sub(
            r"\D",
            "",
            phone,
        )

        blob_digits = re.sub(
            r"\D",
            "",
            blob,
        )

        if (
            len(phone_digits) >= 8
            and phone_digits
            in blob_digits
        ):

            score += 5

            reasons.append(
                "phone_match"
            )

    return {

        "score":
            score,

        "reasons":
            reasons,
    }


# ============================================================
# Extractors
#
# 절대로 이 값만으로 catalog에 자동 반영하지 않는다.
# ============================================================

def extract_holes(
    text: str,
) -> list[int]:

    values = []

    patterns = (

        r"총\s*(\d{1,3})\s*홀",

        r"전체\s*(\d{1,3})\s*홀",

        r"(\d{1,3})\s*홀\s*규모",

        r"(\d{1,3})\s*holes?",
    )

    for pattern in patterns:

        for match in re.findall(
            pattern,
            text,
            flags=re.I,
        ):

            try:

                value = int(
                    match
                )

                if (
                    9 <= value <= 144
                    and value % 9 == 0
                ):

                    values.append(
                        value
                    )

            except Exception:
                pass

    return sorted(
        set(values)
    )


def extract_phones(
    text: str,
) -> list[str]:

    pattern = (
        r"(?<!\d)"
        r"(0\d{1,2})"
        r"[-\s)]?"
        r"(\d{3,4})"
        r"[-\s]?"
        r"(\d{4})"
        r"(?!\d)"
    )

    values = []

    for match in re.findall(
        pattern,
        text,
    ):

        value = "-".join(
            match
        )

        if value not in values:

            values.append(
                value
            )

    return values[:8]


def extract_operation_phrases(
    text: str,
) -> list[str]:

    values = []

    compact = re.sub(
        r"\s+",
        " ",
        text,
    )

    if re.search(
        r"(대중제|비회원제)\s*골프장",
        compact,
    ):

        values.append(
            "대중제_명시문구"
        )

    if re.search(
        r"회원제\s*골프장",
        compact,
    ):

        values.append(
            "회원제_명시문구"
        )

    # --------------------------------------------------------
    # 혼합은 홀수까지 명시되는 강한 패턴만 후보화
    # --------------------------------------------------------

    if re.search(
        r"회원제\s*\d+\s*홀"
        r".{0,100}"
        r"(대중제|비회원제|퍼블릭)\s*\d+\s*홀",
        compact,
        flags=re.S,
    ):

        values.append(
            "혼합_홀수명시"
        )

    return list(
        dict.fromkeys(
            values
        )
    )


# ============================================================
# 검색 결과 분석
# ============================================================

def analyze_result(
    club: dict,
    result: dict,
) -> dict:

    url = clean(
        result.get(
            "url"
        )
    )

    title = clean(
        result.get(
            "title"
        )
    )

    content = clean(
        result.get(
            "content"
        )
    )

    identity = identity_evidence(
        club,
        result,
    )

    text = (
        title
        + "\n"
        + content
    )

    third_party = (
        is_third_party_domain(
            url
        )
    )

    return {

        **result,

        "domain":
            domain_of(
                url
            ),

        "third_party":
            third_party,

        "identity_score":
            identity["score"],

        "identity_reasons":
            identity["reasons"],

        "holes_found":
            extract_holes(
                text
            ),

        "phones_found":
            extract_phones(
                text
            ),

        "operation_phrases":
            extract_operation_phrases(
                text
            ),

        "booking_path_hint":
            looks_like_booking_url(
                url,
                title,
            ),

        "suspicious_official_path":
            suspicious_official_path(
                url
            ),
    }


# ============================================================
# 필드별 evidence 후보 만들기
#
# A / B / HOLD는 '후보 판정'
# catalog에는 반영하지 않는다.
# ============================================================

def classify_field_candidates(
    club: dict,
    results: list[dict],
) -> dict:

    fields = {

        "official_url": [],
        "booking_url": [],
        "holes": [],
        "phone": [],
        "operation_type": [],
    }

    # --------------------------------------------------------
    # URL 후보
    # --------------------------------------------------------

    for item in results:

        url = clean(
            item.get(
                "url"
            )
        )

        if not url:
            continue

        identity_score = int(
            item.get(
                "identity_score"
            )
            or 0
        )

        third_party = bool(
            item.get(
                "third_party"
            )
        )

        suspicious_path = bool(
            item.get(
                "suspicious_official_path"
            )
        )

        # ----------------------------------------------------
        # 공식 URL 후보
        #
        # A 자동확정은 하지 않는다.
        # 강한 동일성 + 비제3자만 A_CANDIDATE
        # ----------------------------------------------------

        if (
            not third_party
            and not suspicious_path
            and identity_score >= 8
        ):

            confidence = (
                "A_CANDIDATE"
            )

        elif (
            not third_party
            and identity_score >= 5
        ):

            confidence = (
                "B_CANDIDATE"
            )

        else:

            confidence = "HOLD"

        fields[
            "official_url"
        ].append({

            "value":
                url,

            "confidence":
                confidence,

            "source_url":
                url,

            "source_domain":
                item.get(
                    "domain"
                ),

            "identity_score":
                identity_score,

            "identity_reasons":
                item.get(
                    "identity_reasons"
                ),
        })

        # ----------------------------------------------------
        # 예약 URL
        # ----------------------------------------------------

        if item.get(
            "booking_path_hint"
        ):

            if (
                not third_party
                and identity_score >= 8
            ):

                booking_confidence = (
                    "A_CANDIDATE"
                )

            elif (
                not third_party
                and identity_score >= 5
            ):

                booking_confidence = (
                    "B_CANDIDATE"
                )

            else:

                booking_confidence = (
                    "HOLD"
                )

            fields[
                "booking_url"
            ].append({

                "value":
                    url,

                "confidence":
                    booking_confidence,

                "source_url":
                    url,

                "source_domain":
                    item.get(
                        "domain"
                    ),

                "identity_score":
                    identity_score,
            })

        # ----------------------------------------------------
        # 홀 수
        # ----------------------------------------------------

        for holes in (
            item.get(
                "holes_found"
            )
            or []
        ):

            if (
                identity_score >= 8
                and not third_party
            ):

                hole_confidence = (
                    "A_CANDIDATE"
                )

            elif identity_score >= 5:

                hole_confidence = (
                    "B_CANDIDATE"
                )

            else:

                hole_confidence = (
                    "HOLD"
                )

            fields[
                "holes"
            ].append({

                "value":
                    holes,

                "confidence":
                    hole_confidence,

                "source_url":
                    url,

                "source_domain":
                    item.get(
                        "domain"
                    ),

                "identity_score":
                    identity_score,
            })

        # ----------------------------------------------------
        # 전화
        # ----------------------------------------------------

        for phone in (
            item.get(
                "phones_found"
            )
            or []
        ):

            if (
                identity_score >= 8
                and not third_party
            ):

                phone_confidence = (
                    "A_CANDIDATE"
                )

            elif identity_score >= 5:

                phone_confidence = (
                    "B_CANDIDATE"
                )

            else:

                phone_confidence = (
                    "HOLD"
                )

            fields[
                "phone"
            ].append({

                "value":
                    phone,

                "confidence":
                    phone_confidence,

                "source_url":
                    url,

                "source_domain":
                    item.get(
                        "domain"
                    ),

                "identity_score":
                    identity_score,
            })

        # ----------------------------------------------------
        # 운영형태
        # ----------------------------------------------------

        for op in (
            item.get(
                "operation_phrases"
            )
            or []
        ):

            if (
                identity_score >= 8
                and not third_party
            ):

                op_confidence = (
                    "A_CANDIDATE"
                )

            elif identity_score >= 5:

                op_confidence = (
                    "B_CANDIDATE"
                )

            else:

                op_confidence = (
                    "HOLD"
                )

            fields[
                "operation_type"
            ].append({

                "value":
                    op,

                "confidence":
                    op_confidence,

                "source_url":
                    url,

                "source_domain":
                    item.get(
                        "domain"
                    ),

                "identity_score":
                    identity_score,
            })

    # --------------------------------------------------------
    # 중복 제거
    # --------------------------------------------------------

    for field, items in fields.items():

        seen = set()

        deduped = []

        for item in items:

            key = (
                str(
                    item.get(
                        "value"
                    )
                ),
                item.get(
                    "source_url"
                ),
            )

            if key in seen:
                continue

            seen.add(key)

            deduped.append(
                item
            )

        fields[field] = deduped

    return fields


# ============================================================
# 기존 1~100 검색 결과 재사용
# ============================================================

def discover_previous_results() -> list[Path]:

    candidates = []

    enrichment_root = (
        ROOT
        / "data"
        / "golf"
        / "enrichment"
    )

    if not enrichment_root.exists():

        return []

    for path in enrichment_root.rglob(
        "result.json"
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

        clubs = data.get(
            "clubs"
        )

        if not isinstance(
            clubs,
            list,
        ):
            continue

        if data.get(
            "catalog_count"
        ) not in (
            553,
            555,
        ):

            continue

        # ----------------------------------------------------
        # 실제 web 결과가 있는 것만
        # ----------------------------------------------------

        has_results = any(

            isinstance(
                club,
                dict,
            )
            and club.get(
                "results"
            )

            for club in clubs
        )

        if has_results:

            candidates.append(
                path
            )

    return sorted(
        candidates,
        key=lambda p:
            p.stat().st_mtime,
    )


def build_previous_evidence_index(
    catalog: list[dict],
) -> dict[str, dict]:

    index = {}

    current_ids = {

        clean(
            club.get(
                "id"
            )
        )

        for club in catalog

        if clean(
            club.get(
                "id"
            )
        )
    }

    paths = discover_previous_results()

    for path in paths:

        try:

            data = load_json(
                path
            )

        except Exception:
            continue

        for club in (
            data.get(
                "clubs"
            )
            or []
        ):

            club_id = clean(
                club.get(
                    "id"
                )
            )

            if not club_id:
                continue

            # ------------------------------------------------
            # 중복 merge로 사라진 ID는 무시
            # ------------------------------------------------

            if club_id not in current_ids:
                continue

            raw_results = (
                club.get(
                    "results"
                )
                or []
            )

            if not raw_results:
                continue

            # ------------------------------------------------
            # 최신 파일 우선
            # ------------------------------------------------

            index[
                club_id
            ] = {

                "source_file":
                    str(path),

                "raw_results":
                    raw_results,
            }

    return index


# ============================================================
# 기존 결과를 V3 형식으로 재분석
# ============================================================

def reanalyze_previous_results(
    club: dict,
    raw_results: list[dict],
) -> list[dict]:

    analyzed = []

    for raw in raw_results:

        analyzed.append(
            analyze_result(
                club,
                raw,
            )
        )

    return analyzed


# ============================================================
# 세션
# ============================================================

def create_run_dir() -> Path:

    stamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    path = (
        OUTPUT_ROOT
        / stamp
    )

    path.mkdir(
        parents=True,
        exist_ok=False,
    )

    return path


def find_resume_run() -> Path | None:

    if not OUTPUT_ROOT.exists():

        return None

    runs = sorted(

        [
            path
            for path
            in OUTPUT_ROOT.iterdir()

            if path.is_dir()
        ],

        key=lambda p:
            p.stat().st_mtime,

        reverse=True,
    )

    for run in runs:

        checkpoint = (
            run
            / "checkpoint.json"
        )

        if checkpoint.exists():

            try:

                data = load_json(
                    checkpoint
                )

            except Exception:
                continue

            if (
                data.get(
                    "pipeline_version"
                )
                == PIPELINE_VERSION
                and data.get(
                    "complete"
                )
                is not True
            ):

                return run

    return None


# ============================================================
# checkpoint
# ============================================================

def save_checkpoint(
    run_dir: Path,
    *,
    catalog_hash: str,
    catalog_count: int,
    records: list[dict],
    search_calls: int,
    complete: bool,
) -> None:

    data = {

        "pipeline_version":
            PIPELINE_VERSION,

        "updated_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "catalog_count":
            catalog_count,

        "catalog_sha256":
            catalog_hash,

        "catalog_modified":
            False,

        "search_calls":
            search_calls,

        "processed_count":
            len(records),

        "complete":
            complete,

        "clubs":
            records,
    }

    save_json(
        run_dir
        / "checkpoint.json",
        data,
    )


# ============================================================
# DIAGNOSTIC
# ============================================================

def diagnostic(
    catalog: list[dict],
    previous_index: dict[str, dict],
) -> dict:

    missing_counter = Counter()

    search_targets = []

    reused = 0

    complete = 0

    for position, club in enumerate(
        catalog,
        start=1,
    ):

        missing = missing_fields(
            club
        )

        for field in missing:

            missing_counter[
                field
            ] += 1

        if not missing:

            complete += 1
            continue

        club_id = clean(
            club.get(
                "id"
            )
        )

        if club_id in previous_index:

            reused += 1

        if needs_web_search(
            club
        ):

            search_targets.append({

                "position":
                    position,

                "id":
                    club_id,

                "name":
                    clean(
                        club.get(
                            "name"
                        )
                    ),

                "missing_fields":
                    missing,

                "previous_web_result":
                    club_id
                    in previous_index,
            })

    # --------------------------------------------------------
    # 1차 검색 1회 기준 예상
    # booking이 필요한 일부는 2차 가능.
    # --------------------------------------------------------

    without_previous = [

        row
        for row
        in search_targets

        if not row[
            "previous_web_result"
        ]
    ]

    minimum_calls = len(
        without_previous
    )

    booking_extra = sum(

        1
        for row
        in without_previous

        if "booking_url"
        in row[
            "missing_fields"
        ]
    )

    maximum_calls = (
        minimum_calls
        + booking_extra
    )

    return {

        "catalog_count":
            len(catalog),

        "complete_basic_count":
            complete,

        "missing_by_field":
            dict(
                missing_counter
            ),

        "web_target_count":
            len(
                search_targets
            ),

        "previous_result_reuse_count":
            reused,

        "new_web_target_count":
            len(
                without_previous
            ),

        "estimated_min_calls":
            minimum_calls,

        "estimated_max_calls":
            maximum_calls,

        "targets":
            search_targets,
    }


# ============================================================
# REPORT
# ============================================================

def write_diagnostic_report(
    run_dir: Path,
    diag: dict,
) -> None:

    lines = [

        "# Golf Master Pipeline v3 진단",

        "",

        f"- 전체 catalog: {diag['catalog_count']}개",

        (
            "- 현재 주요 필드 완비: "
            f"{diag['complete_basic_count']}개"
        ),

        (
            "- 웹 조사 대상: "
            f"{diag['web_target_count']}개"
        ),

        (
            "- 기존 웹 결과 재사용 가능: "
            f"{diag['previous_result_reuse_count']}개"
        ),

        (
            "- 신규 웹 검색 예상 대상: "
            f"{diag['new_web_target_count']}개"
        ),

        (
            "- 신규 Tavily 최소 예상: "
            f"{diag['estimated_min_calls']}회"
        ),

        (
            "- 신규 Tavily 최대 예상: "
            f"{diag['estimated_max_calls']}회"
        ),

        "",

        "## 필드별 부족",

        "",
    ]

    for field, count in (
        diag[
            "missing_by_field"
        ].items()
    ):

        lines.append(
            f"- {field}: {count}개"
        )

    lines.extend([

        "",

        "## 원칙",

        "",

        "- catalog.json 수정 없음",

        "- 기존 1~100 웹 결과 재사용",

        "- 부족 필드만 검색",

        "- 필드별 A_CANDIDATE / B_CANDIDATE / HOLD",

        "- 후보값은 자동 반영하지 않음",

        "- 중단 후 checkpoint에서 재개",

    ])

    (
        run_dir
        / "diagnostic.md"
    ).write_text(
        "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )

    save_json(
        run_dir
        / "diagnostic.json",
        diag,
    )


# ============================================================
# 골프장 1개 처리
# ============================================================

def process_club(
    *,
    club: dict,
    position: int,
    previous_index: dict[str, dict],
    api_key: str | None,
    allow_search: bool,
    remaining_calls: int,
) -> tuple[dict, int]:

    club_id = clean(
        club.get(
            "id"
        )
    )

    name = clean(
        club.get(
            "name"
        )
    )

    missing = missing_fields(
        club
    )

    record = {

        "catalog_position":
            position,

        "id":
            club_id,

        "name":
            name,

        "missing_fields":
            missing,

        "existing": {

            field:
                club.get(
                    field
                )

            for field in TARGET_FIELDS
        },

        "public_data":
            public_data(
                club
            ),

        "kga": {

            "matched":
                kga_data(
                    club
                ).get(
                    "matched"
                ),

            "matched_name":
                kga_data(
                    club
                ).get(
                    "matched_name"
                ),

            "course_combinations":
                kga_data(
                    club
                ).get(
                    "course_combinations"
                ),
        },

        "search_source":
            None,

        "searches":
            [],

        "results":
            [],

        "field_candidates":
            {},

        "status":
            None,
    }

    # --------------------------------------------------------
    # 이미 충분
    # --------------------------------------------------------

    if not missing:

        record[
            "status"
        ] = "COMPLETE_EXISTING"

        return (
            record,
            0,
        )

    # --------------------------------------------------------
    # 이전 검색결과 재사용
    # --------------------------------------------------------

    previous = previous_index.get(
        club_id
    )

    if previous:

        analyzed = (
            reanalyze_previous_results(
                club,
                previous[
                    "raw_results"
                ],
            )
        )

        record[
            "search_source"
        ] = "PREVIOUS_RESULT"

        record[
            "previous_source_file"
        ] = previous[
            "source_file"
        ]

        record[
            "results"
        ] = analyzed

        record[
            "field_candidates"
        ] = (
            classify_field_candidates(
                club,
                analyzed,
            )
        )

        record[
            "status"
        ] = "REUSED_REVIEW"

        # ----------------------------------------------------
        # 이미 검색한 1~100은 재검색하지 않는다.
        # ----------------------------------------------------

        return (
            record,
            0,
        )

    # --------------------------------------------------------
    # 진단 모드
    # --------------------------------------------------------

    if not allow_search:

        record[
            "status"
        ] = "SEARCH_REQUIRED"

        return (
            record,
            0,
        )

    if remaining_calls <= 0:

        record[
            "status"
        ] = "WAITING_CALL_LIMIT"

        return (
            record,
            0,
        )

    # --------------------------------------------------------
    # 신규 검색
    # --------------------------------------------------------

    used_calls = 0

    all_results = []

    query1 = make_profile_query(
        club
    )

    results1 = tavily_search(
        api_key,
        query1,
    )

    used_calls += 1

    record[
        "searches"
    ].append({

        "type":
            "profile",

        "query":
            query1,

        "result_count":
            len(
                results1
            ),
    })

    all_results.extend(
        results1
    )

    analyzed1 = [

        analyze_result(
            club,
            result,
        )

        for result in results1
    ]

    # --------------------------------------------------------
    # 2차 예약검색 조건
    #
    # booking이 부족하고
    # 첫 검색에서 강한 예약 후보가 없을 때만.
    # --------------------------------------------------------

    needs_booking = (
        "booking_url"
        in missing
    )

    strong_booking_found = any(

        item.get(
            "booking_path_hint"
        )
        and not item.get(
            "third_party"
        )
        and int(
            item.get(
                "identity_score"
            )
            or 0
        ) >= 8

        for item in analyzed1
    )

    if (
        needs_booking
        and not strong_booking_found
        and (
            remaining_calls
            - used_calls
        ) > 0
    ):

        time.sleep(
            REQUEST_DELAY
        )

        query2 = make_booking_query(
            club
        )

        results2 = tavily_search(
            api_key,
            query2,
        )

        used_calls += 1

        record[
            "searches"
        ].append({

            "type":
                "booking",

            "query":
                query2,

            "result_count":
                len(
                    results2
                ),
        })

        all_results.extend(
            results2
        )

    # --------------------------------------------------------
    # 분석
    # --------------------------------------------------------

    analyzed = [

        analyze_result(
            club,
            result,
        )

        for result in all_results
    ]

    record[
        "search_source"
    ] = "NEW_TAVILY"

    record[
        "results"
    ] = analyzed

    record[
        "field_candidates"
    ] = (
        classify_field_candidates(
            club,
            analyzed,
        )
    )

    record[
        "status"
    ] = (
        "SEARCHED_REVIEW_REQUIRED"
        if analyzed
        else "SEARCHED_NO_RESULT"
    )

    return (
        record,
        used_calls,
    )


# ============================================================
# 최종 요약
# ============================================================

def summarize_records(
    records: list[dict],
) -> dict:

    statuses = Counter()

    candidate_counts = Counter()

    for record in records:

        statuses[
            record.get(
                "status"
            )
            or "UNKNOWN"
        ] += 1

        fields = (
            record.get(
                "field_candidates"
            )
            or {}
        )

        for field, candidates in (
            fields.items()
        ):

            for candidate in candidates:

                confidence = candidate.get(
                    "confidence"
                )

                if confidence:

                    candidate_counts[
                        f"{field}:{confidence}"
                    ] += 1

    return {

        "status_counts":
            dict(
                statuses
            ),

        "candidate_counts":
            dict(
                candidate_counts
            ),
    }


# ============================================================
# 최종 report
# ============================================================

def write_final_report(
    run_dir: Path,
    *,
    catalog_count: int,
    search_calls: int,
    records: list[dict],
) -> None:

    summary = summarize_records(
        records
    )

    lines = [

        "# Golf Master Pipeline v3 결과",

        "",

        f"- catalog: {catalog_count}개",

        (
            "- 이번 실행 Tavily 호출: "
            f"{search_calls}회"
        ),

        "- catalog 수정: 없음",

        "",

        "## 상태",

        "",
    ]

    for key, value in (
        summary[
            "status_counts"
        ].items()
    ):

        lines.append(
            f"- {key}: {value}"
        )

    lines.extend([

        "",

        "## 후보",

        "",
    ])

    for key, value in (
        summary[
            "candidate_counts"
        ].items()
    ):

        lines.append(
            f"- {key}: {value}"
        )

    lines.extend([

        "",

        "## 주의",

        "",

        (
            "- A_CANDIDATE는 자동 승인값이 아니라 "
            "강한 검토 후보입니다."
        ),

        (
            "- catalog 반영은 다음 단계의 "
            "verified apply에서만 수행합니다."
        ),

        (
            "- 기존 값과 충돌하는 후보는 "
            "반드시 HOLD해야 합니다."
        ),
    ])

    (
        run_dir
        / "report.md"
    ).write_text(
        "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--search",
        action="store_true",
        help="실제 Tavily 검색 수행",
    )

    parser.add_argument(
        "--max-calls",
        type=int,
        default=DEFAULT_MAX_CALLS,
        help="이번 실행 최대 Tavily 호출 수",
    )

    parser.add_argument(
        "--new-run",
        action="store_true",
        help="기존 checkpoint를 무시하고 새 세션 시작",
    )

    args = parser.parse_args()

    print()
    print("=" * 76)
    print(
        "Golf Master Pipeline v3"
    )
    print("=" * 76)

    # --------------------------------------------------------
    # catalog snapshot
    # --------------------------------------------------------

    if not CATALOG_PATH.exists():

        raise RuntimeError(
            f"catalog가 없습니다: "
            f"{CATALOG_PATH}"
        )

    catalog_bytes = (
        CATALOG_PATH.read_bytes()
    )

    catalog_hash = (
        sha256_bytes(
            catalog_bytes
        )
    )

    catalog = json.loads(
        catalog_bytes.decode(
            "utf-8-sig"
        )
    )

    if not isinstance(
        catalog,
        list,
    ):

        raise RuntimeError(
            "catalog.json 구조가 list가 아닙니다."
        )

    if len(catalog) != EXPECTED_CATALOG_COUNT:

        raise RuntimeError(
            "안전 중단: "
            f"현재 catalog={len(catalog)}개 / "
            f"예상={EXPECTED_CATALOG_COUNT}개"
        )

    print(
        "현재 catalog:",
        len(catalog),
        "개"
    )

    # --------------------------------------------------------
    # 기존 검색결과
    # --------------------------------------------------------

    print(
        "기존 검색결과 탐색 중..."
    )

    previous_index = (
        build_previous_evidence_index(
            catalog
        )
    )

    print(
        "기존 웹검색 재사용 가능:",
        len(previous_index),
        "개"
    )

    # --------------------------------------------------------
    # 진단
    # --------------------------------------------------------

    diag = diagnostic(
        catalog,
        previous_index,
    )

    print()
    print(
        "[진단]"
    )

    print(
        "웹 조사 대상:",
        diag[
            "web_target_count"
        ],
        "개"
    )

    print(
        "기존 결과 재사용:",
        diag[
            "previous_result_reuse_count"
        ],
        "개"
    )

    print(
        "신규 검색 대상:",
        diag[
            "new_web_target_count"
        ],
        "개"
    )

    print(
        "예상 Tavily 최소:",
        diag[
            "estimated_min_calls"
        ],
        "회"
    )

    print(
        "예상 Tavily 최대:",
        diag[
            "estimated_max_calls"
        ],
        "회"
    )

    print()

    for field, count in (
        diag[
            "missing_by_field"
        ].items()
    ):

        print(
            f"  {field}: "
            f"{count}"
        )

    # --------------------------------------------------------
    # 검색 안 하는 진단 모드
    # --------------------------------------------------------

    if not args.search:

        run_dir = create_run_dir()

        write_diagnostic_report(
            run_dir,
            diag,
        )

        # catalog 불변 확인
        if (
            CATALOG_PATH.read_bytes()
            != catalog_bytes
        ):

            raise RuntimeError(
                "catalog 변경 감지"
            )

        print()
        print("=" * 76)
        print(
            "DIAGNOSTIC COMPLETE"
        )
        print("=" * 76)

        print(
            "추가 API 호출: 0"
        )

        print(
            "catalog.json 수정: False"
        )

        print(
            "진단 결과:",
            run_dir
            / "diagnostic.json"
        )

        print()
        print(
            "실제 검색하려면:"
        )

        print(
            r".\venv\Scripts\python.exe "
            r".\golf_master_pipeline_v3.py "
            r"--search --max-calls 120"
        )

        return

    # --------------------------------------------------------
    # Tavily key
    # --------------------------------------------------------

    api_key = load_tavily_key()

    # --------------------------------------------------------
    # resume
    # --------------------------------------------------------

    run_dir = None

    if not args.new_run:

        run_dir = find_resume_run()

    if run_dir:

        print(
            "기존 실행 이어서 진행:",
            run_dir
        )

        checkpoint = load_json(
            run_dir
            / "checkpoint.json"
        )

        existing_records = (
            checkpoint.get(
                "clubs"
            )
            or []
        )

        # ----------------------------------------------------
        # catalog 변경 여부
        # ----------------------------------------------------

        if (
            checkpoint.get(
                "catalog_sha256"
            )
            != catalog_hash
        ):

            raise RuntimeError(
                "catalog가 이전 실행 이후 변경되었습니다. "
                "--new-run으로 새 세션을 시작하세요."
            )

    else:

        run_dir = create_run_dir()

        existing_records = []

        write_diagnostic_report(
            run_dir,
            diag,
        )

    # --------------------------------------------------------
    # 이미 처리된 ID
    # --------------------------------------------------------

    processed_ids = {

        clean(
            record.get(
                "id"
            )
        )

        for record in existing_records

        if clean(
            record.get(
                "id"
            )
        )
    }

    records = list(
        existing_records
    )

    search_calls = 0

    print()
    print(
        "이번 실행 최대 Tavily:",
        args.max_calls,
        "회"
    )

    # --------------------------------------------------------
    # 전체 553개 순회
    # --------------------------------------------------------

    for position, club in enumerate(
        catalog,
        start=1,
    ):

        club_id = clean(
            club.get(
                "id"
            )
        )

        name = clean(
            club.get(
                "name"
            )
        )

        if club_id in processed_ids:

            continue

        remaining = (
            args.max_calls
            - search_calls
        )

        print()
        print(
            f"[{position:03d}/553] "
            f"{name}"
        )

        print(
            "  부족:",
            ", ".join(
                missing_fields(
                    club
                )
            )
            or "없음"
        )

        record, used = process_club(

            club=club,

            position=position,

            previous_index=previous_index,

            api_key=api_key,

            allow_search=True,

            remaining_calls=remaining,
        )

        search_calls += used

        records.append(
            record
        )

        processed_ids.add(
            club_id
        )

        print(
            "  상태:",
            record[
                "status"
            ]
        )

        if used:

            print(
                "  Tavily:",
                used,
                "회"
            )

        print(
            "  이번 실행 누적:",
            search_calls,
            "/",
            args.max_calls,
        )

        # ----------------------------------------------------
        # 매 골프장 checkpoint
        # ----------------------------------------------------

        save_checkpoint(

            run_dir,

            catalog_hash=
                catalog_hash,

            catalog_count=
                len(catalog),

            records=
                records,

            search_calls=
                search_calls,

            complete=False,
        )

        # ----------------------------------------------------
        # 호출 한도
        # ----------------------------------------------------

        if search_calls >= args.max_calls:

            print()
            print(
                "이번 실행 Tavily 한도 도달."
            )

            print(
                "다음 실행 시 checkpoint에서 "
                "자동으로 이어집니다."
            )

            break

        if used:

            time.sleep(
                REQUEST_DELAY
            )

    # --------------------------------------------------------
    # 완료 여부
    # --------------------------------------------------------

    complete = (
        len(processed_ids)
        >= len(catalog)
    )

    save_checkpoint(

        run_dir,

        catalog_hash=
            catalog_hash,

        catalog_count=
            len(catalog),

        records=
            records,

        search_calls=
            search_calls,

        complete=
            complete,
    )

    # --------------------------------------------------------
    # 최종 result
    # --------------------------------------------------------

    summary = summarize_records(
        records
    )

    final = {

        "pipeline_version":
            PIPELINE_VERSION,

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "catalog_count":
            len(catalog),

        "catalog_sha256":
            catalog_hash,

        "catalog_modified":
            False,

        "complete":
            complete,

        "processed_count":
            len(records),

        "this_run_search_calls":
            search_calls,

        "summary":
            summary,

        "clubs":
            records,
    }

    save_json(
        run_dir
        / "result.json",
        final,
    )

    write_final_report(

        run_dir,

        catalog_count=
            len(catalog),

        search_calls=
            search_calls,

        records=
            records,
    )

    # --------------------------------------------------------
    # catalog 불변 검증
    # --------------------------------------------------------

    after_bytes = (
        CATALOG_PATH.read_bytes()
    )

    if after_bytes != catalog_bytes:

        raise RuntimeError(
            "안전 중단: "
            "catalog.json 변경 감지"
        )

    # --------------------------------------------------------
    # END
    # --------------------------------------------------------

    print()
    print("=" * 76)

    if complete:

        print(
            "PIPELINE v3 검색 단계 완료"
        )

    else:

        print(
            "PIPELINE v3 부분 완료"
        )

    print("=" * 76)

    print(
        "처리:",
        len(records),
        "/",
        len(catalog)
    )

    print(
        "이번 실행 Tavily:",
        search_calls,
        "회"
    )

    print(
        "catalog.json 수정:",
        False
    )

    print(
        "완료 여부:",
        complete
    )

    print()
    print(
        "결과:",
        run_dir
        / "result.json"
    )

    print(
        "보고서:",
        run_dir
        / "report.md"
    )

    print(
        "checkpoint:",
        run_dir
        / "checkpoint.json"
    )

    if not complete:

        print()
        print(
            "같은 명령을 다시 실행하면 "
            "이어서 진행합니다:"
        )

        print(
            r".\venv\Scripts\python.exe "
            r".\golf_master_pipeline_v3.py "
            r"--search --max-calls 120"
        )


if __name__ == "__main__":

    main()