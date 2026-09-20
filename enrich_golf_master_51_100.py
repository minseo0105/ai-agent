from __future__ import annotations

import json
import re
import time
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    import tomllib
except ImportError:
    import tomli as tomllib


# ============================================================
# Golf Master DB - 51~100 WEB RESEARCH
#
# 중요
# - 현재 catalog 553개 기준
# - 51~100번째 50개만 조사
# - catalog.json 절대 수정하지 않음
# - 검색 결과는 "후보 자료"일 뿐 자동 승인하지 않음
# - 공식 홈페이지 / 예약 페이지도 자동 확정하지 않음
# - 다음 단계에서 사람이 검토 후 화이트리스트 반영
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
    / "master_51_100_web"
)

SECRETS_PATH = (
    ROOT
    / ".streamlit"
    / "secrets.toml"
)


# ============================================================
# 범위
# Python index 기준 50~99 = 사람 기준 51~100
# ============================================================

START_INDEX = 50
END_INDEX = 100


# ============================================================
# 검색 설정
# ============================================================

SEARCH_DEPTH = "basic"
MAX_RESULTS = 6
TIMEOUT = 20

REQUEST_DELAY = 0.7

MAX_SEARCHES_PER_CLUB = 2


# ============================================================
# 제3자/비공식 사이트
#
# 검색결과에는 저장하지만
# official 후보로 절대 분류하지 않는다.
# ============================================================

NON_OFFICIAL_DOMAINS = {

    "naver.com",
    "blog.naver.com",
    "m.blog.naver.com",
    "cafe.naver.com",
    "map.naver.com",
    "search.naver.com",
    "place.naver.com",

    "kakao.com",
    "map.kakao.com",

    "daum.net",
    "tistory.com",

    "youtube.com",
    "youtu.be",

    "instagram.com",
    "facebook.com",

    "golfzon.com",
    "kimcaddie.com",
    "xgolf.com",

    # FIRST50에서 실제 오판된 유형
    "golf.sbs.co.kr",
    "sbs.co.kr",

    "dbegl.com",

    "tripinfo.co.kr",

    "premiumgolf.co.kr",
    "czgolf.kr",

    "msg1.co.kr",

    "grandculture.net",

    "knps.or.kr",
}


# ============================================================
# 파일
# ============================================================

def load_json(path):

    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def sha256_bytes(data):

    return hashlib.sha256(
        data
    ).hexdigest()


# ============================================================
# Tavily Key
# ============================================================

def load_tavily_key():

    if not SECRETS_PATH.exists():

        raise RuntimeError(
            f"secrets 파일 없음: {SECRETS_PATH}"
        )

    data = tomllib.loads(
        SECRETS_PATH.read_text(
            encoding="utf-8"
        )
    )

    key = str(
        data.get(
            "TAVILY_API_KEY"
        )
        or ""
    ).strip()

    if not key:

        raise RuntimeError(
            "TAVILY_API_KEY가 없습니다."
        )

    return key


# ============================================================
# 문자열
# ============================================================

def clean(value):

    if value is None:
        return ""

    return str(
        value
    ).strip()


def normalize_name(value):

    text = clean(
        value
    ).lower()

    text = re.sub(
        r"\s+",
        "",
        text,
    )

    for token in (

        "골프클럽",
        "컨트리클럽",

        "countryclub",
        "golfclub",

        "country",
        "golf",

        "cc",
        "gc",

        "클럽",
    ):

        text = text.replace(
            token,
            "",
        )

    return re.sub(
        r"[^0-9a-z가-힣]",
        "",
        text,
    )


def domain_of(url):

    try:

        domain = (
            urlparse(url)
            .netloc
            .lower()
        )

        if domain.startswith(
            "www."
        ):

            domain = domain[4:]

        return domain

    except Exception:

        return ""


def is_blocked_official_domain(url):

    domain = domain_of(
        url
    )

    if not domain:
        return True

    for blocked in NON_OFFICIAL_DOMAINS:

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


# ============================================================
# 현재 DB 상태
# ============================================================

def public_data(club):

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


def has_real_value(value):

    if value is None:
        return False

    if isinstance(
        value,
        str,
    ):

        value = value.strip()

        if value in (
            "",
            "없음",
            "미확인",
            "unknown",
            "Unknown",
        ):

            return False

    return True


def determine_missing_fields(club):

    missing = []

    # 운영형태
    if not has_real_value(
        club.get(
            "operation_type"
        )
    ):

        missing.append(
            "operation_type"
        )

    # 홀수
    if not has_real_value(
        club.get(
            "holes"
        )
    ):

        missing.append(
            "holes"
        )

    # 공식 홈페이지
    if not has_real_value(
        club.get(
            "official_url"
        )
    ):

        missing.append(
            "official_url"
        )

    # 예약 페이지
    if not has_real_value(
        club.get(
            "booking_url"
        )
    ):

        missing.append(
            "booking_url"
        )

    # 전화
    if not has_real_value(
        club.get(
            "phone"
        )
    ):

        missing.append(
            "phone"
        )

    return missing


# ============================================================
# Tavily
# ============================================================

def tavily_search(
    api_key,
    query,
):

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

        timeout=TIMEOUT,
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
# 검색 Query
#
# FIRST50보다 공식출처를 더 강하게 요구
# ============================================================

def make_primary_query(
    club,
):

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

        parts = (
            address.split()
        )

        locality = " ".join(
            parts[:3]
        )

    return (
        f'"{name}" {locality} '
        f'공식 골프장 홈페이지 '
        f'코스소개 예약 '
        f'총 홀수 전화번호'
    ).strip()


def make_secondary_query(
    club,
):

    name = clean(
        club.get(
            "name"
        )
    )

    return (
        f'"{name}" '
        f'골프장 공식 사이트 '
        f'코스 안내 이용 안내 예약'
    )


# ============================================================
# Identity 평가
#
# 주의:
# 이것은 승인 점수가 아니다.
# 동일 골프장일 가능성을 검토하기 위한 참고값이다.
# ============================================================

def identity_score(
    club,
    result,
):

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

    normalized_name = (
        normalize_name(
            name
        )
    )

    normalized_result = (
        normalize_name(
            title
            + " "
            + content
        )
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

    # 주소
    if address:

        tokens = [

            x
            for x
            in address.split()

            if len(x) >= 2
        ]

        hits = sum(

            1
            for token
            in tokens[:5]

            if token.lower()
            in blob
        )

        if hits >= 2:

            score += 3

            reasons.append(
                "address_match"
            )

        elif hits == 1:

            score += 1

            reasons.append(
                "address_partial"
            )

    # 전화
    if phone:

        digits = re.sub(
            r"\D",
            "",
            phone,
        )

        result_digits = re.sub(
            r"\D",
            "",
            blob,
        )

        if (
            len(digits) >= 8
            and digits
            in result_digits
        ):

            score += 4

            reasons.append(
                "phone_match"
            )

    if is_blocked_official_domain(
        url
    ):

        reasons.append(
            "third_party_domain"
        )

    return (
        score,
        reasons,
    )


# ============================================================
# 근거 추출
#
# 자동 반영하지 않는다.
# ============================================================

def extract_holes(text):

    values = []

    patterns = (

        # 총 27홀
        r"총\s*(\d{1,3})\s*홀",

        # 전체 36홀
        r"전체\s*(\d{1,3})\s*홀",

        # 54홀 규모
        r"(\d{1,3})\s*홀\s*규모",
    )

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.I,
        )

        for value in matches:

            try:

                value = int(
                    value
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


def extract_operation(text):

    values = []

    # 단순 회원제/대중제 동시출현로
    # 혼합 판정하지 않는다.

    if re.search(
        r"(?:회원제\s*\d+\s*홀)"
        r".{0,80}"
        r"(?:대중제|비회원제|퍼블릭)"
        r"\s*\d+\s*홀",
        text,
        flags=re.S,
    ):

        values.append(
            "혼합_명시"
        )

    if re.search(
        r"(?:대중제|비회원제)\s*골프장",
        text,
    ):

        values.append(
            "대중제_문구"
        )

    if re.search(
        r"회원제\s*골프장",
        text,
    ):

        values.append(
            "회원제_문구"
        )

    return list(
        dict.fromkeys(
            values
        )
    )


def extract_phone(text):

    matches = re.findall(
        r"(?:0\d{1,2})"
        r"[-\s)]?"
        r"\d{3,4}"
        r"[-\s]?"
        r"\d{4}",
        text,
    )

    values = []

    for value in matches:

        value = re.sub(
            r"\s+",
            "-",
            value.strip(),
        )

        if value not in values:

            values.append(
                value
            )

    return values[:5]


# ============================================================
# 검색결과 분석
# ============================================================

def analyze_results(
    club,
    results,
):

    analyzed = []

    for result in results:

        score, reasons = (
            identity_score(
                club,
                result,
            )
        )

        text = (
            result.get(
                "title",
                ""
            )
            + "\n"
            + result.get(
                "content",
                ""
            )
        )

        url = result.get(
            "url",
            ""
        )

        analyzed.append({

            **result,

            "identity_reference_score":
                score,

            "identity_reasons":
                reasons,

            "domain":
                domain_of(
                    url
                ),

            "third_party_domain":
                is_blocked_official_domain(
                    url
                ),

            "holes_found":
                extract_holes(
                    text
                ),

            "operation_phrases":
                extract_operation(
                    text
                ),

            "phones_found":
                extract_phone(
                    text
                ),

            # 매우 중요:
            # 자동 공식사이트 판정 없음.
            "official_status":
                "REVIEW_REQUIRED",
        })

    return analyzed


# ============================================================
# 현재 사실 snapshot
# ============================================================

def build_current_facts(
    club,
):

    public = public_data(
        club
    )

    return {

        "operation_type":
            club.get(
                "operation_type"
            ),

        "holes":
            club.get(
                "holes"
            ),

        "courses":
            club.get(
                "courses"
            ),

        "official_url":
            club.get(
                "official_url"
            ),

        "booking_url":
            club.get(
                "booking_url"
            ),

        "address":
            club.get(
                "address"
            ),

        "phone":
            club.get(
                "phone"
            ),

        "public_data": {

            "matched":
                public.get(
                    "matched"
                ),

            "business_type":
                public.get(
                    "business_type"
                ),

            "operating":
                public.get(
                    "operating_in_public_data"
                ),

            "management_no":
                public.get(
                    "management_no"
                ),

            "road_address":
                public.get(
                    "road_address"
                ),

            "phone":
                public.get(
                    "phone"
                ),
        },
    }


# ============================================================
# checkpoint
# ============================================================

def save_checkpoint(
    path,
    catalog_hash,
    completed,
    search_calls,
):

    data = {

        "mode":
            "WEB_RESEARCH_REVIEW_ONLY",

        "range":
            "51-100",

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "catalog_count":
            553,

        "catalog_sha256":
            catalog_hash,

        "catalog_modified":
            False,

        "search_calls":
            search_calls,

        "completed_count":
            len(
                completed
            ),

        "clubs":
            completed,
    }

    path.write_text(

        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),

        encoding="utf-8",
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 72)
    print(
        "Golf Master DB - "
        "51~100 WEB RESEARCH"
    )
    print("=" * 72)

    api_key = (
        load_tavily_key()
    )

    # --------------------------------------------------------
    # catalog snapshot
    # --------------------------------------------------------

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
            "현재 catalog.json이 "
            "list 구조가 아닙니다."
        )

    if len(catalog) != 553:

        raise RuntimeError(
            f"안전 중단: "
            f"catalog={len(catalog)}개"
        )

    # --------------------------------------------------------
    # 51~100
    # --------------------------------------------------------

    target_clubs = (
        catalog[
            START_INDEX:
            END_INDEX
        ]
    )

    if len(target_clubs) != 50:

        raise RuntimeError(
            f"대상이 50개가 아닙니다. "
            f"{len(target_clubs)}개"
        )

    print()
    print(
        "현재 catalog:",
        len(catalog),
    )

    print(
        "이번 대상:",
        len(target_clubs),
        "개 (51~100)"
    )

    print()
    print(
        "※ catalog.json은 "
        "절대 수정하지 않습니다."
    )

    # --------------------------------------------------------
    # output
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

    checkpoint_path = (
        output_dir
        / "checkpoint.json"
    )

    result_path = (
        output_dir
        / "result.json"
    )

    report_path = (
        output_dir
        / "report.md"
    )

    completed = []
    search_calls = 0

    # --------------------------------------------------------
    # 각 골프장
    # --------------------------------------------------------

    for number, club in enumerate(
        target_clubs,
        start=51,
    ):

        name = clean(
            club.get(
                "name"
            )
        )

        club_id = (
            club.get(
                "id"
            )
        )

        missing = (
            determine_missing_fields(
                club
            )
        )

        print()
        print(
            f"[{number:03d}/100] "
            f"{name}"
        )

        print(
            "  부족:",
            (
                ", ".join(
                    missing
                )
                if missing
                else "없음"
            ),
        )

        # ----------------------------------------------------
        # 검색할 게 없으면 skip
        # ----------------------------------------------------

        if not missing:

            completed.append({

                "catalog_position":
                    number,

                "id":
                    club_id,

                "name":
                    name,

                "status":
                    "NO_SEARCH_NEEDED",

                "missing_fields":
                    [],

                "current_facts":
                    build_current_facts(
                        club
                    ),

                "searches":
                    [],

                "results":
                    [],
            })

            save_checkpoint(
                checkpoint_path,
                catalog_hash,
                completed,
                search_calls,
            )

            print(
                "  → 검색 생략"
            )

            continue

        # ----------------------------------------------------
        # 1차 검색
        # ----------------------------------------------------

        searches = []
        combined_results = []

        try:

            query1 = (
                make_primary_query(
                    club
                )
            )

            print(
                "  검색 1:",
                query1,
            )

            results1 = (
                tavily_search(
                    api_key,
                    query1,
                )
            )

            search_calls += 1

            searches.append({

                "query":
                    query1,

                "result_count":
                    len(
                        results1
                    ),
            })

            combined_results.extend(
                results1
            )

            analyzed1 = (
                analyze_results(
                    club,
                    results1,
                )
            )

            strongest = max(

                [
                    row.get(
                        "identity_reference_score",
                        0,
                    )
                    for row
                    in analyzed1
                ]

                or [0]
            )

            # ------------------------------------------------
            # 2차 검색
            #
            # 동일 골프장 근거가 너무 약할 때만.
            # ------------------------------------------------

            if (
                strongest < 4
                and MAX_SEARCHES_PER_CLUB
                >= 2
            ):

                time.sleep(
                    REQUEST_DELAY
                )

                query2 = (
                    make_secondary_query(
                        club
                    )
                )

                print(
                    "  검색 2:",
                    query2,
                )

                results2 = (
                    tavily_search(
                        api_key,
                        query2,
                    )
                )

                search_calls += 1

                searches.append({

                    "query":
                        query2,

                    "result_count":
                        len(
                            results2
                        ),
                })

                combined_results.extend(
                    results2
                )

            # ------------------------------------------------
            # 최종 분석
            # ------------------------------------------------

            analyzed = (
                analyze_results(
                    club,
                    combined_results,
                )
            )

            # 검색결과가 있어도
            # 자동 PARTIAL/APPROVE 같은 승인 의미를 주지 않는다.
            status = (
                "REVIEW_REQUIRED"
                if analyzed
                else "NO_RESULT"
            )

            completed.append({

                "catalog_position":
                    number,

                "id":
                    club_id,

                "name":
                    name,

                "status":
                    status,

                "missing_fields":
                    missing,

                "current_facts":
                    build_current_facts(
                        club
                    ),

                "searches":
                    searches,

                "results":
                    analyzed,
            })

            print(
                "  →",
                status,
                "| 결과",
                len(analyzed),
                "건"
            )

        except Exception as exc:

            completed.append({

                "catalog_position":
                    number,

                "id":
                    club_id,

                "name":
                    name,

                "status":
                    "ERROR",

                "missing_fields":
                    missing,

                "current_facts":
                    build_current_facts(
                        club
                    ),

                "searches":
                    searches,

                "results":
                    [],

                "error":
                    (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
            })

            print(
                "  → ERROR:",
                type(exc).__name__,
                exc,
            )

        # ----------------------------------------------------
        # 매 골프장마다 저장
        # ----------------------------------------------------

        save_checkpoint(
            checkpoint_path,
            catalog_hash,
            completed,
            search_calls,
        )

        time.sleep(
            REQUEST_DELAY
        )

    # ========================================================
    # catalog 불변 검증
    # ========================================================

    after_bytes = (
        CATALOG_PATH.read_bytes()
    )

    if after_bytes != catalog_bytes:

        raise RuntimeError(
            "안전 중단: "
            "catalog.json 변경 감지"
        )

    # ========================================================
    # 결과 집계
    # ========================================================

    counts = {}

    for row in completed:

        status = (
            row.get(
                "status"
            )
            or "UNKNOWN"
        )

        counts[
            status
        ] = (
            counts.get(
                status,
                0,
            )
            + 1
        )

    final = {

        "mode":
            "WEB_RESEARCH_REVIEW_ONLY",

        "range":
            "51-100",

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "catalog_count":
            len(
                catalog
            ),

        "catalog_sha256":
            catalog_hash,

        "catalog_modified":
            False,

        "search_calls":
            search_calls,

        "status_counts":
            counts,

        "clubs":
            completed,
    }

    result_path.write_text(

        json.dumps(
            final,
            ensure_ascii=False,
            indent=2,
        ),

        encoding="utf-8",
    )

    # ========================================================
    # 보고서
    # ========================================================

    lines = [

        "# Golf Master DB - 51~100 Web Research",

        "",

        f"- catalog: {len(catalog)}개",

        "- 범위: 51~100",

        f"- 대상: {len(completed)}개",

        f"- Tavily 호출: {search_calls}회",

        "- catalog 수정: 없음",

        "- 검색 결과 자동승인: 없음",

        "",

        "## 결과",

        "",
    ]

    for key, value in counts.items():

        lines.append(
            f"- {key}: {value}개"
        )

    lines.extend([

        "",

        "## 골프장별 결과",

        "",

        "| 위치 | 골프장 | 상태 | 부족정보 | 결과수 |",

        "|---:|---|---|---|---:|",
    ])

    for row in completed:

        lines.append(

            f"| {row.get('catalog_position')} "

            f"| {row.get('name')} "

            f"| {row.get('status')} "

            f"| {', '.join(row.get('missing_fields') or []) or '-'} "

            f"| {len(row.get('results') or [])} |"
        )

    report_path.write_text(

        "\n".join(
            lines
        )
        + "\n",

        encoding="utf-8",
    )

    # ========================================================
    # 종료
    # ========================================================

    print()
    print("=" * 72)
    print(
        "51~100 검색 완료"
    )
    print("=" * 72)

    print(
        "Tavily 실제 호출:",
        search_calls,
        "회"
    )

    print(
        "결과:",
        counts
    )

    print(
        "catalog.json 수정:",
        False
    )

    print(
        "자동 승인:",
        False
    )

    print()

    print(
        "결과 JSON:",
        result_path
    )

    print(
        "검토 보고서:",
        report_path
    )

    print()

    print(
        "SUCCESS: "
        "검색자료만 저장했습니다. "
        "catalog.json은 변경하지 않았습니다."
    )


if __name__ == "__main__":

    main()