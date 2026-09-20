# -*- coding: utf-8 -*-

"""
Golf Master Pipeline v3.1 - Windows Safe Checkpoint Edition

목적
------------------------------------------------------------
1. 현재 catalog.json 553개 기준
2. catalog.json은 절대 수정하지 않음
3. 기존 웹검색 결과 최대한 재사용
4. 공공데이터 / KGA / verified_basic_info 활용
5. 신규 Tavily 검색은 기본적으로 골프장당 1회
6. booking_url 하나만 없다고 추가 검색하지 않음
7. Windows checkpoint 파일 잠금 문제 회피
8. checkpoint_0001.json, checkpoint_0002.json ... 방식
9. 중단 후 재실행하면 가장 최신 checkpoint부터 자동 재개
10. 검색 결과는 검토 후보만 저장하고 catalog에는 자동 반영하지 않음


실행 방법
------------------------------------------------------------

진단만:

.\venv\Scripts\python.exe .\golf_master_pipeline_v3_1.py


실제 검색:

.\venv\Scripts\python.exe .\golf_master_pipeline_v3_1.py --search --max-calls 150


강제로 새 작업 시작:

.\venv\Scripts\python.exe .\golf_master_pipeline_v3_1.py --search --max-calls 150 --new-run
"""


from __future__ import annotations

import argparse
import hashlib
import json
import re
import time

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests


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

ENRICHMENT_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
)

OUTPUT_ROOT = (
    ENRICHMENT_ROOT
    / "pipeline_v3_1"
)

SECRETS_PATH = (
    ROOT
    / ".streamlit"
    / "secrets.toml"
)


# ============================================================
# CONFIG
# ============================================================

EXPECTED_CATALOG_COUNT = 553

PIPELINE_VERSION = "3.1"

DEFAULT_MAX_CALLS = 150

MAX_RESULTS = 8

REQUEST_TIMEOUT = 25

REQUEST_DELAY = 0.55


TARGET_FIELDS = (
    "operation_type",
    "holes",
    "courses",
    "official_url",
    "booking_url",
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
# THIRD PARTY DOMAIN
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


BOOKING_HINTS = (
    "reservation",
    "reserve",
    "booking",
    "예약",
)


# ============================================================
# BASIC HELPERS
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


# ============================================================
# WINDOWS SAFE JSON SAVE
#
# 기존 checkpoint 파일을 덮어쓰지 않는다.
# checkpoint는 항상 새로운 파일명을 사용한다.
# ============================================================

def save_json(
    path: Path,
    data: Any,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )

    last_error = None

    # Windows에서 백신/동기화 프로그램 등이
    # 새 파일 생성 순간에도 잠깐 간섭할 수 있으므로 재시도
    for attempt in range(5):

        try:

            path.write_text(
                text,
                encoding="utf-8",
            )

            return

        except (PermissionError, OSError) as exc:

            last_error = exc

            time.sleep(
                0.4 * (attempt + 1)
            )

    raise RuntimeError(
        f"파일 저장 실패: {path}\n"
        f"오류: {last_error}"
    )


def sha256_bytes(data: bytes) -> str:

    return hashlib.sha256(
        data
    ).hexdigest()


# ============================================================
# URL
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


def is_third_party(url: str) -> bool:

    domain = domain_of(url)

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


# ============================================================
# CATALOG DATA
# ============================================================

def public_data(club: dict) -> dict:

    return (
        (
            club.get("verification")
            or {}
        )
        .get("public_data")
        or {}
    )


def kga_data(club: dict) -> dict:

    return (
        club.get("kga")
        or {}
    )


def verified_data(club: dict) -> dict:

    return (
        club.get("verified_basic_info")
        or {}
    )


# ============================================================
# VERIFIED VALUE
# ============================================================

def verified_value(
    club: dict,
    field: str,
):

    item = (
        verified_data(club)
        .get(field)
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
        item.get("confidence") == "A"
        and has_value(
            club.get(field)
        )
    ):

        return club.get(field)

    return None


# ============================================================
# PUBLIC DATA
# ============================================================

def public_phone(pub: dict):

    for key in (
        "phone",
        "TELNO",
        "telno",
    ):

        value = pub.get(key)

        if has_value(value):

            return value

    return None


def public_operation(pub: dict):

    if pub.get("matched") is not True:

        return None

    value = (
        pub.get("business_type")
        or pub.get("DTL_SALS_STTS_NM")
    )

    if not has_value(value):

        return None

    text = clean(value)

    if text == "회원제":

        return "회원제"

    if text in (
        "비회원제",
        "대중제",
        "퍼블릭",
    ):

        return "대중제"

    return None


# ============================================================
# KGA
# ============================================================

def kga_course_info(kga: dict):

    combinations = (
        kga.get("course_combinations")
    )

    if (
        kga.get("matched") is True
        and isinstance(
            combinations,
            list,
        )
        and combinations
    ):

        return combinations

    return None


# ============================================================
# EFFECTIVE INFORMATION
# ============================================================

def effective_info(
    club: dict,
) -> dict:

    pub = public_data(club)

    kga = kga_data(club)

    values = {}

    sources = {}

    for field in TARGET_FIELDS:

        # 1. 검증된 정보
        value = verified_value(
            club,
            field,
        )

        if has_value(value):

            values[field] = value

            sources[field] = (
                "verified_basic_info"
            )

            continue

        # 2. catalog 직접 정보
        value = club.get(field)

        if has_value(value):

            values[field] = value

            sources[field] = "catalog"

            continue

        # 3. 공공데이터 전화번호
        if field == "phone":

            value = public_phone(pub)

            if has_value(value):

                values[field] = value

                sources[field] = (
                    "public_data"
                )

                continue

        # 4. 공공데이터 운영형태
        if field == "operation_type":

            value = public_operation(pub)

            if has_value(value):

                values[field] = value

                sources[field] = (
                    "public_data_exact"
                )

                continue

        # 5. KGA 코스 정보
        if field == "courses":

            value = kga_course_info(kga)

            if has_value(value):

                values[field] = value

                sources[field] = (
                    "kga_course_combinations"
                )

                continue

        values[field] = None

        sources[field] = None

    return {

        "values": values,

        "sources": sources,
    }


# ============================================================
# MISSING
# ============================================================

def missing_fields(
    club: dict,
) -> list[str]:

    info = (
        effective_info(club)
        ["values"]
    )

    return [

        field

        for field in TARGET_FIELDS

        if not has_value(
            info.get(field)
        )
    ]


# ============================================================
# HIGH PRIORITY
#
# booking_url 하나만 부족하면 신규검색하지 않는다.
# ============================================================

def high_priority_missing(
    club: dict,
) -> list[str]:

    missing = set(
        missing_fields(club)
    )

    priority = (
        "official_url",
        "holes",
        "operation_type",
        "phone",
    )

    return [

        field

        for field in priority

        if field in missing
    ]


# ============================================================
# TAVILY KEY
# ============================================================

def load_tavily_key() -> str:

    if not SECRETS_PATH.exists():

        raise RuntimeError(
            f"secrets.toml 없음: "
            f"{SECRETS_PATH}"
        )

    raw = SECRETS_PATH.read_text(
        encoding="utf-8"
    )

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

    match = re.search(
        r'(?m)^\s*TAVILY_API_KEY\s*=\s*["\']([^"\']+)["\']',
        raw,
    )

    if match:

        return (
            match.group(1)
            .strip()
        )

    raise RuntimeError(
        "TAVILY_API_KEY를 찾지 못했습니다."
    )


# ============================================================
# NAME NORMALIZATION
# ============================================================

def normalize_name(value: Any) -> str:

    text = clean(value).lower()

    text = re.sub(
        r"[^0-9a-z가-힣]",
        "",
        text,
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
# IDENTITY CHECK
# ============================================================

def identity_evidence(
    club: dict,
    result: dict,
) -> dict:

    name = clean(
        club.get("name")
    )

    address = clean(
        club.get("address")
    )

    phone = (
        clean(
            club.get("phone")
        )
        or clean(
            public_phone(
                public_data(club)
            )
        )
    )

    blob = " ".join([

        clean(
            result.get("title")
        ),

        clean(
            result.get("content")
        ),

        clean(
            result.get("url")
        ),

    ]).lower()

    score = 0

    reasons = []

    # --------------------------------------------------------
    # 이름
    # --------------------------------------------------------

    normalized_name = (
        normalize_name(name)
    )

    normalized_result = (
        normalize_name(blob)
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

        tokens = [

            token

            for token in address.split()

            if len(token) >= 2

        ][:7]

        hits = sum(

            1

            for token in tokens

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
    # 전화번호
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

        "score": score,

        "reasons": reasons,
    }


# ============================================================
# HOLES
# ============================================================

def extract_holes(
    text: str,
) -> list[int]:

    values = set()

    patterns = (
        r"총\s*(\d{1,3})\s*홀",
        r"전체\s*(\d{1,3})\s*홀",
        r"(\d{1,3})\s*홀\s*규모",
        r"(\d{1,3})\s*holes?",
    )

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.I,
        )

        for match in matches:

            try:

                number = int(match)

                if (
                    9 <= number <= 144
                    and number % 9 == 0
                ):

                    values.add(
                        number
                    )

            except Exception:

                pass

    return sorted(
        values
    )


# ============================================================
# PHONE
# ============================================================

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


# ============================================================
# OPERATION TYPE
# ============================================================

def extract_operations(
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
            "대중제_명시"
        )

    if re.search(
        r"회원제\s*골프장",
        compact,
    ):

        values.append(
            "회원제_명시"
        )

    # 회원제 + 대중제가 각각 홀수와 함께 명시된 경우만
    if re.search(

        r"회원제\s*\d+\s*홀"
        r".{0,120}"
        r"(대중제|비회원제|퍼블릭)"
        r"\s*\d+\s*홀",

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
# ANALYZE RESULT
# ============================================================

def analyze_result(
    club: dict,
    raw: dict,
) -> dict:

    url = clean(
        raw.get("url")
    )

    title = clean(
        raw.get("title")
    )

    content = clean(
        raw.get("content")
    )

    identity = (
        identity_evidence(
            club,
            raw,
        )
    )

    text = (
        title
        + "\n"
        + content
    )

    booking_hint = any(

        hint in (
            url
            + " "
            + title
        ).lower()

        for hint
        in BOOKING_HINTS
    )

    return {

        "title":
            title,

        "url":
            url,

        "content":
            content,

        "score":
            raw.get("score"),

        "domain":
            domain_of(url),

        "third_party":
            is_third_party(url),

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
            extract_operations(
                text
            ),

        "booking_hint":
            booking_hint,
    }


# ============================================================
# QUERY
# ============================================================

def make_query(
    club: dict,
) -> str:

    name = clean(
        club.get("name")
    )

    address = clean(
        club.get("address")
    )

    locality = ""

    if address:

        locality = " ".join(
            address.split()[:3]
        )

    return (

        f'"{name}" '
        f'{locality} '
        f'공식 홈페이지 '
        f'골프장 예약 '
        f'코스 총 홀수 '
        f'회원제 대중제 '
        f'전화'

    ).strip()


# ============================================================
# TAVILY
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
                "basic",

            "max_results":
                MAX_RESULTS,
        },

        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    results = []

    for item in (
        data.get("results")
        or []
    ):

        results.append({

            "title":
                clean(
                    item.get("title")
                ),

            "url":
                clean(
                    item.get("url")
                ),

            "content":
                clean(
                    item.get("content")
                ),

            "score":
                item.get("score"),
        })

    return results


# ============================================================
# FIELD CANDIDATES
#
# 주의:
# A_CANDIDATE라고 catalog에 바로 넣지 않는다.
# ============================================================

def classify_candidates(
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

    for result in results:

        score = int(
            result.get(
                "identity_score"
            )
            or 0
        )

        third_party = bool(
            result.get(
                "third_party"
            )
        )

        if (
            score >= 8
            and not third_party
        ):

            confidence = (
                "A_CANDIDATE"
            )

        elif score >= 5:

            confidence = (
                "B_CANDIDATE"
            )

        else:

            confidence = "HOLD"

        url = clean(
            result.get("url")
        )

        # ----------------------------------------------------
        # 홈페이지 후보
        # ----------------------------------------------------

        if url:

            fields[
                "official_url"
            ].append({

                "value":
                    url,

                "confidence":
                    confidence,

                "source_url":
                    url,

                "domain":
                    result.get(
                        "domain"
                    ),

                "identity_score":
                    score,
            })

        # ----------------------------------------------------
        # 예약 후보
        # ----------------------------------------------------

        if (
            url
            and result.get(
                "booking_hint"
            )
        ):

            fields[
                "booking_url"
            ].append({

                "value":
                    url,

                "confidence":
                    confidence,

                "source_url":
                    url,

                "domain":
                    result.get(
                        "domain"
                    ),

                "identity_score":
                    score,
            })

        # ----------------------------------------------------
        # 홀수 후보
        # ----------------------------------------------------

        for holes in (
            result.get(
                "holes_found"
            )
            or []
        ):

            fields[
                "holes"
            ].append({

                "value":
                    holes,

                "confidence":
                    confidence,

                "source_url":
                    url,

                "domain":
                    result.get(
                        "domain"
                    ),

                "identity_score":
                    score,
            })

        # ----------------------------------------------------
        # 전화번호 후보
        # ----------------------------------------------------

        for phone in (
            result.get(
                "phones_found"
            )
            or []
        ):

            fields[
                "phone"
            ].append({

                "value":
                    phone,

                "confidence":
                    confidence,

                "source_url":
                    url,

                "domain":
                    result.get(
                        "domain"
                    ),

                "identity_score":
                    score,
            })

        # ----------------------------------------------------
        # 운영형태 후보
        # ----------------------------------------------------

        for operation in (
            result.get(
                "operation_phrases"
            )
            or []
        ):

            fields[
                "operation_type"
            ].append({

                "value":
                    operation,

                "confidence":
                    confidence,

                "source_url":
                    url,

                "domain":
                    result.get(
                        "domain"
                    ),

                "identity_score":
                    score,
            })

    # --------------------------------------------------------
    # 중복 제거
    # --------------------------------------------------------

    for field in fields:

        seen = set()

        deduped = []

        for item in fields[field]:

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

            seen.add(
                key
            )

            deduped.append(
                item
            )

        fields[field] = (
            deduped
        )

    return fields


# ============================================================
# PREVIOUS WEB RESULTS
#
# enrichment 아래 기존 결과를 재사용
# ============================================================

def discover_previous_evidence(
    catalog: list[dict],
) -> dict[str, dict]:

    current = {

        clean(
            club.get("id")
        ):
        club

        for club in catalog

        if clean(
            club.get("id")
        )
    }

    index = {}

    if not ENRICHMENT_ROOT.exists():

        return index

    paths = sorted(

        ENRICHMENT_ROOT.rglob(
            "*.json"
        ),

        key=lambda path:
            path.stat().st_mtime,
    )

    for path in paths:

        path_text = (
            str(path)
            .lower()
        )

        # 자기 자신 pipeline 결과 제외
        if (
            "pipeline_v3"
            in path_text
        ):

            continue

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

        for row in clubs:

            if not isinstance(
                row,
                dict,
            ):

                continue

            raw_results = (
                row.get("results")
            )

            if (
                not isinstance(
                    raw_results,
                    list,
                )
                or not raw_results
            ):

                continue

            row_id = clean(
                row.get("id")
            )

            row_name = clean(
                row.get("name")
            )

            matched_id = None

            # ------------------------------------------------
            # ID match
            # ------------------------------------------------

            if row_id in current:

                matched_id = row_id

            # ------------------------------------------------
            # unique name match
            # ------------------------------------------------

            elif row_name:

                normalized = (
                    normalize_name(
                        row_name
                    )
                )

                matches = [

                    club_id

                    for club_id, club
                    in current.items()

                    if (
                        normalized
                        and normalize_name(
                            club.get("name")
                        )
                        == normalized
                    )
                ]

                if len(matches) == 1:

                    matched_id = (
                        matches[0]
                    )

            if not matched_id:

                continue

            index[
                matched_id
            ] = {

                "source_file":
                    str(path),

                "raw_results":
                    raw_results,

                "matched_by":
                    (
                        "id"
                        if row_id
                        == matched_id
                        else "name"
                    ),
            }

    return index


# ============================================================
# DIAGNOSTIC
# ============================================================

def diagnostic(
    catalog: list[dict],
    previous: dict[str, dict],
) -> dict:

    missing_counter = (
        Counter()
    )

    targets = []

    reused = 0

    for position, club in enumerate(
        catalog,
        start=1,
    ):

        missing = (
            missing_fields(
                club
            )
        )

        for field in missing:

            missing_counter[
                field
            ] += 1

        high_priority = (
            high_priority_missing(
                club
            )
        )

        if not high_priority:

            continue

        club_id = clean(
            club.get("id")
        )

        has_previous = (
            club_id
            in previous
        )

        if has_previous:

            reused += 1

        targets.append({

            "position":
                position,

            "id":
                club_id,

            "name":
                clean(
                    club.get("name")
                ),

            "missing_fields":
                missing,

            "high_priority_missing":
                high_priority,

            "previous_web_result":
                has_previous,
        })

    new_targets = [

        row

        for row in targets

        if not row[
            "previous_web_result"
        ]
    ]

    return {

        "catalog_count":
            len(catalog),

        "missing_by_field":
            dict(
                missing_counter
            ),

        "web_target_count":
            len(targets),

        "previous_result_reuse_count":
            reused,

        "new_web_target_count":
            len(new_targets),

        "estimated_calls":
            len(new_targets),

        "targets":
            targets,
    }


# ============================================================
# RUN DIRECTORY
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


# ============================================================
# CHECKPOINT FILES
# ============================================================

def checkpoint_files_for_run(
    run: Path,
) -> list[Path]:

    files = list(
        run.glob(
            "checkpoint_*.json"
        )
    )

    # 번호가 큰 것이 최신
    files = sorted(
        files,
        key=lambda path:
            path.name,
        reverse=True,
    )

    # 과거 방식 checkpoint도 읽는다
    legacy = (
        run
        / "checkpoint.json"
    )

    if legacy.exists():

        files.append(
            legacy
        )

    return files


# ============================================================
# LATEST INCOMPLETE RUN
# ============================================================

def latest_incomplete_run(
    catalog_hash: str,
):

    if not OUTPUT_ROOT.exists():

        return None

    runs = sorted(

        [

            path

            for path
            in OUTPUT_ROOT.iterdir()

            if path.is_dir()
        ],

        key=lambda path:
            path.stat().st_mtime,

        reverse=True,
    )

    for run in runs:

        checkpoint_files = (
            checkpoint_files_for_run(
                run
            )
        )

        for checkpoint_path in (
            checkpoint_files
        ):

            try:

                data = load_json(
                    checkpoint_path
                )

            except Exception:

                continue

            if (
                data.get(
                    "pipeline_version"
                )
                == PIPELINE_VERSION

                and data.get(
                    "catalog_sha256"
                )
                == catalog_hash

                and data.get(
                    "complete"
                )
                is not True
            ):

                return (
                    run,
                    data,
                    checkpoint_path,
                )

    return None


# ============================================================
# CHECKPOINT SAVE
#
# 같은 checkpoint를 덮어쓰지 않는다.
# ============================================================

def save_checkpoint(
    run: Path,
    checkpoint: dict,
) -> Path:

    processed_count = int(
        checkpoint.get(
            "processed_count"
        )
        or 0
    )

    base_path = (
        run
        / (
            f"checkpoint_"
            f"{processed_count:04d}.json"
        )
    )

    # 같은 번호 파일이 이미 있다면 절대 덮어쓰지 않고
    # timestamp suffix를 붙인다.
    if base_path.exists():

        suffix = (
            datetime.now()
            .strftime(
                "%H%M%S_%f"
            )
        )

        base_path = (
            run
            / (
                f"checkpoint_"
                f"{processed_count:04d}_"
                f"{suffix}.json"
            )
        )

    save_json(
        base_path,
        checkpoint,
    )

    return base_path


# ============================================================
# MAIN
# ============================================================

def main():

    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--search",
        action="store_true",
    )

    parser.add_argument(
        "--max-calls",
        type=int,
        default=DEFAULT_MAX_CALLS,
    )

    parser.add_argument(
        "--new-run",
        action="store_true",
    )

    args = parser.parse_args()

    print()

    print(
        "=" * 76
    )

    print(
        "Golf Master Pipeline v3.1"
    )

    print(
        "=" * 76
    )

    # ========================================================
    # CATALOG LOAD
    # ========================================================

    if not CATALOG_PATH.exists():

        raise RuntimeError(
            f"catalog 없음: "
            f"{CATALOG_PATH}"
        )

    original_bytes = (
        CATALOG_PATH.read_bytes()
    )

    catalog_hash = (
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

            f"현재 catalog="
            f"{len(catalog)}개 / "

            f"예상="
            f"{EXPECTED_CATALOG_COUNT}개"
        )

    print(
        "현재 catalog:",
        len(catalog),
        "개"
    )

    # ========================================================
    # PREVIOUS RESULTS
    # ========================================================

    print(
        "기존 검색결과 전체 탐색 중..."
    )

    previous = (
        discover_previous_evidence(
            catalog
        )
    )

    print(
        "기존 웹검색 재사용 가능:",
        len(previous),
        "개"
    )

    # ========================================================
    # DIAGNOSTIC
    # ========================================================

    diag = (
        diagnostic(
            catalog,
            previous,
        )
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
        "예상 Tavily:",
        diag[
            "estimated_calls"
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
            f"  {field}: {count}"
        )

    # ========================================================
    # DIAGNOSTIC ONLY
    # ========================================================

    if not args.search:

        run = (
            create_run_dir()
        )

        save_json(
            run
            / "diagnostic.json",
            diag,
        )

        if (
            CATALOG_PATH.read_bytes()
            != original_bytes
        ):

            raise RuntimeError(
                "catalog 변경 감지"
            )

        print()

        print(
            "=" * 76
        )

        print(
            "DIAGNOSTIC COMPLETE"
        )

        print(
            "=" * 76
        )

        print(
            "추가 API 호출: 0"
        )

        print(
            "catalog.json 수정: False"
        )

        print(
            "진단 결과:",
            run
            / "diagnostic.json"
        )

        return

    # ========================================================
    # SEARCH MODE
    # ========================================================

    api_key = (
        load_tavily_key()
    )

    resumed = None

    if not args.new_run:

        resumed = (
            latest_incomplete_run(
                catalog_hash
            )
        )

    # ========================================================
    # RESUME
    # ========================================================

    if resumed:

        (
            run,
            checkpoint,
            checkpoint_path,
        ) = resumed

        records = (
            checkpoint.get("clubs")
            or []
        )

        print()

        print(
            "이전 checkpoint에서 "
            "이어서 진행:"
        )

        print(
            run
        )

        print(
            "불러온 checkpoint:"
        )

        print(
            checkpoint_path
        )

        print(
            "기존 처리:",
            len(records),
            "개"
        )

    else:

        run = (
            create_run_dir()
        )

        records = []

        print()

        print(
            "새 검색 세션 시작:"
        )

        print(
            run
        )

    processed = {

        clean(
            record.get("id")
        )

        for record in records

        if clean(
            record.get("id")
        )
    }

    # 이번 실행에서 실제로 새 Tavily를 호출한 횟수
    calls = 0

    print()

    print(
        "이번 실행 Tavily 최대:",
        args.max_calls,
        "회"
    )

    print(
        "현재까지 처리된 골프장:",
        len(processed),
        "개"
    )

    # ========================================================
    # 553개 전체 순회
    # ========================================================

    for position, club in enumerate(
        catalog,
        start=1,
    ):

        club_id = clean(
            club.get("id")
        )

        if club_id in processed:

            continue

        name = clean(
            club.get("name")
        )

        missing = (
            missing_fields(
                club
            )
        )

        high_priority = (
            high_priority_missing(
                club
            )
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

            "high_priority_missing":
                high_priority,

            "effective_info":
                effective_info(
                    club
                ),

            "search_source":
                None,

            "results":
                [],

            "field_candidates":
                {},

            "status":
                None,
        }

        # ====================================================
        # NO SEARCH
        # ====================================================

        if not high_priority:

            record[
                "status"
            ] = (
                "NO_NEW_SEARCH_NEEDED"
            )

        # ====================================================
        # REUSE OLD SEARCH
        # ====================================================

        elif club_id in previous:

            previous_item = (
                previous[
                    club_id
                ]
            )

            raw_results = (
                previous_item[
                    "raw_results"
                ]
            )

            analyzed = [

                analyze_result(
                    club,
                    raw,
                )

                for raw
                in raw_results
            ]

            record[
                "search_source"
            ] = (
                "PREVIOUS_RESULT"
            )

            record[
                "previous_source_file"
            ] = (
                previous_item[
                    "source_file"
                ]
            )

            record[
                "previous_matched_by"
            ] = (
                previous_item[
                    "matched_by"
                ]
            )

            record[
                "results"
            ] = analyzed

            record[
                "field_candidates"
            ] = (
                classify_candidates(
                    club,
                    analyzed,
                )
            )

            record[
                "status"
            ] = (
                "REUSED_REVIEW_REQUIRED"
            )

        # ====================================================
        # MAX CALLS
        # ====================================================

        elif calls >= args.max_calls:

            break

        # ====================================================
        # NEW TAVILY
        # ====================================================

        else:

            query = (
                make_query(
                    club
                )
            )

            print(
                f"[{position:03d}/553] "
                f"{name} "
                f"→ Tavily 1회"
            )

            raw_results = (
                tavily_search(
                    api_key,
                    query,
                )
            )

            calls += 1

            analyzed = [

                analyze_result(
                    club,
                    raw,
                )

                for raw
                in raw_results
            ]

            record[
                "search_source"
            ] = (
                "NEW_TAVILY"
            )

            record[
                "query"
            ] = query

            record[
                "results"
            ] = analyzed

            record[
                "field_candidates"
            ] = (
                classify_candidates(
                    club,
                    analyzed,
                )
            )

            record[
                "status"
            ] = (
                "SEARCHED_REVIEW_REQUIRED"
            )

            time.sleep(
                REQUEST_DELAY
            )

        # ====================================================
        # ADD RECORD
        # ====================================================

        records.append(
            record
        )

        processed.add(
            club_id
        )

        # ====================================================
        # CHECKPOINT
        # ====================================================

        checkpoint = {

            "pipeline_version":
                PIPELINE_VERSION,

            "catalog_count":
                len(catalog),

            "catalog_sha256":
                catalog_hash,

            "catalog_modified":
                False,

            "updated_at":
                datetime.now()
                .astimezone()
                .isoformat(),

            "this_run_search_calls":
                calls,

            "processed_count":
                len(records),

            "complete":
                (
                    len(processed)
                    == len(catalog)
                ),

            "clubs":
                records,
        }

        save_checkpoint(
            run,
            checkpoint,
        )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    complete = (
        len(processed)
        == len(catalog)
    )

    status_counter = (
        Counter(

            record.get(
                "status"
            )

            for record
            in records
        )
    )

    result = {

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
            calls,

        "status_counts":
            dict(
                status_counter
            ),

        "clubs":
            records,
    }

    # result.json도 과거 잠금 가능성을 피하기 위해
    # 완료 시각을 포함한 별도 파일로 저장
    result_name = (
        "result_"
        + datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        + ".json"
    )

    result_path = (
        run
        / result_name
    )

    save_json(
        result_path,
        result,
    )

    # ========================================================
    # CATALOG SAFETY CHECK
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
    # OUTPUT
    # ========================================================

    print()

    print(
        "=" * 76
    )

    if complete:

        print(
            "PIPELINE v3.1 완료"
        )

    else:

        print(
            "PIPELINE v3.1 부분 완료"
        )

    print(
        "=" * 76
    )

    print(
        "처리:",
        len(records),
        "/",
        len(catalog)
    )

    print(
        "이번 실행 Tavily:",
        calls,
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

    print(
        "결과:",
        result_path
    )

    if not complete:

        print()

        print(
            "같은 명령을 다시 실행하면 "
            "최신 checkpoint에서 이어집니다."
        )

        print()

        print(
            r".\venv\Scripts\python.exe "
            r".\golf_master_pipeline_v3_1.py "
            r"--search --max-calls 150"
        )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()