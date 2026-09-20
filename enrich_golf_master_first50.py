from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    import tomllib
except ImportError:
    import tomli as tomllib


# ============================================================
# Golf Master DB - FIRST 50 WEB ENRICHMENT
#
# 목적
# - 진단된 첫 50개만 처리
# - 누락/의심 필드만 Tavily로 조사
# - catalog.json 절대 수정하지 않음
# - 검색 원문 + 후보값 + 출처를 checkpoint에 저장
#
# 중요:
# 이 스크립트는 "자동 DB 반영기"가 아닙니다.
# 검토용 후보를 만드는 단계입니다.
# ============================================================


ROOT = Path(__file__).resolve().parent

CATALOG_PATH = ROOT / "data" / "golf" / "catalog.json"

DIAG_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "master_first50"
)

OUTPUT_ROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "master_first50_web"
)

SECRETS_PATH = (
    ROOT
    / ".streamlit"
    / "secrets.toml"
)


# ------------------------------------------------------------
# 검색 설정
# ------------------------------------------------------------

SEARCH_DEPTH = "basic"
MAX_RESULTS = 6
TIMEOUT = 20

# Tavily 호출 사이 간격
REQUEST_DELAY = 0.7

# 한 골프장에 기본적으로 1회 검색.
# 결과가 부족할 때만 2차 검색.
MAX_SEARCHES_PER_CLUB = 2


# ------------------------------------------------------------
# 공식 홈페이지로 자동 인정하지 않을 도메인
# ------------------------------------------------------------

NON_OFFICIAL_DOMAINS = {
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
    "www.youtube.com",
    "instagram.com",
    "facebook.com",
    "golfzon.com",
    "kimcaddie.com",
    "xgolf.com",
    "golping.golfzon.com",
}

NEWS_HINTS = (
    "news",
    "article",
    "press",
    "blog",
    "cafe",
)


# ============================================================
# 파일/secret
# ============================================================


def load_tavily_key():

    if not SECRETS_PATH.exists():
        raise RuntimeError(
            f"secrets 파일을 찾을 수 없습니다: {SECRETS_PATH}"
        )

    data = tomllib.loads(
        SECRETS_PATH.read_text(
            encoding="utf-8"
        )
    )

    key = str(
        data.get("TAVILY_API_KEY") or ""
    ).strip()

    if not key:
        raise RuntimeError(
            "TAVILY_API_KEY가 secrets.toml에 없습니다."
        )

    return key


def find_latest_diagnostic():

    if not DIAG_ROOT.exists():
        raise RuntimeError(
            "master_first50 진단 폴더가 없습니다."
        )

    candidates = sorted(
        DIAG_ROOT.glob("*/result.json"),
        reverse=True,
    )

    if not candidates:
        raise RuntimeError(
            "first50 result.json을 찾지 못했습니다."
        )

    return candidates[0]


# ============================================================
# 문자열
# ============================================================


def clean(value):

    if value is None:
        return ""

    return str(value).strip()


def normalize_name(value):

    text = clean(value).lower()

    text = re.sub(
        r"\s+",
        "",
        text,
    )

    for token in (
        "골프클럽",
        "컨트리클럽",
        "countryclub",
        "country",
        "golfclub",
        "golf",
        "cc",
        "gc",
        "클럽",
    ):
        text = text.replace(
            token,
            "",
        )

    text = re.sub(
        r"[^0-9a-z가-힣]",
        "",
        text,
    )

    return text


def domain_of(url):

    try:
        return (
            urlparse(url)
            .netloc
            .lower()
            .replace("www.", "")
        )
    except Exception:
        return ""


def is_non_official(url):

    domain = domain_of(url)

    if not domain:
        return True

    for blocked in NON_OFFICIAL_DOMAINS:

        b = blocked.replace(
            "www.",
            ""
        )

        if (
            domain == b
            or domain.endswith(
                "." + b
            )
        ):
            return True

    lower = url.lower()

    if any(
        hint in lower
        for hint in NEWS_HINTS
    ):
        return True

    return False


# ============================================================
# Tavily
# ============================================================


def tavily_search(
    api_key,
    query,
):

    url = "https://api.tavily.com/search"

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": SEARCH_DEPTH,
        "max_results": MAX_RESULTS,
    }

    response = requests.post(
        url,
        json=payload,
        timeout=TIMEOUT,
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
# 검색 Query
# ============================================================


def make_primary_query(
    club_name,
    address,
):

    locality = ""

    if address:
        parts = address.split()

        locality = " ".join(
            parts[:2]
        )

    return (
        f'"{club_name}" {locality} '
        "공식 홈페이지 "
        "코스 홀 회원제 대중제 "
        "예약 전화"
    ).strip()


def make_secondary_query(
    club_name,
):

    return (
        f'"{club_name}" '
        "골프장 코스 안내 "
        "예약 이용안내"
    )


# ============================================================
# 검색결과 identity 평가
# ============================================================


def identity_score(
    club,
    result,
):

    name = clean(
        club.get("name")
    )

    address = clean(
        club.get("address")
    )

    phone = clean(
        club.get("phone")
    )

    title = clean(
        result.get("title")
    )

    content = clean(
        result.get("content")
    )

    url = clean(
        result.get("url")
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

    normalized = normalize_name(
        name
    )

    if (
        normalized
        and normalized in normalize_name(
            title + content
        )
    ):
        score += 4
        reasons.append(
            "name_match"
        )

    # 주소의 시/군/구 단위 일부 일치
    if address:

        tokens = [
            x
            for x in address.split()
            if len(x) >= 2
        ]

        address_hits = sum(
            1
            for token in tokens[:4]
            if token.lower()
            in blob
        )

        if address_hits >= 2:
            score += 3
            reasons.append(
                "address_match"
            )

        elif address_hits == 1:
            score += 1
            reasons.append(
                "address_partial"
            )

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
            and digits in result_digits
        ):
            score += 4
            reasons.append(
                "phone_match"
            )

    if is_non_official(url):
        reasons.append(
            "non_official_domain"
        )

    return score, reasons


# ============================================================
# 필드 후보 추출
#
# 여기서는 보수적으로 "후보"만 생성합니다.
# catalog에는 쓰지 않습니다.
# ============================================================


def extract_holes(text):

    values = []

    patterns = [
        r"총\s*(\d{1,3})\s*홀",
        r"(\d{1,3})\s*홀\s*(?:규모|코스)",
        r"(\d{1,3})\s*holes?",
    ]

    for pattern in patterns:

        for match in re.findall(
            pattern,
            text,
            flags=re.I,
        ):

            try:
                n = int(match)

                if (
                    9 <= n <= 144
                    and n % 9 == 0
                ):
                    values.append(n)

            except Exception:
                pass

    return sorted(
        set(values)
    )


def extract_operation(text):

    values = []

    # 혼합형을 단순 키워드 동시등장으로 만들지 않음
    # 명시 문구만 후보로 인정

    mixed_patterns = (
        "회원제 및 대중제",
        "회원제와 대중제",
        "회원제·대중제",
        "회원제/대중제",
    )

    if any(
        x in text
        for x in mixed_patterns
    ):
        values.append(
            "혼합"
        )

    if re.search(
        r"(?:대중제|대중형|비회원제)\s*골프",
        text,
    ):
        values.append(
            "대중제"
        )

    if re.search(
        r"회원제\s*골프",
        text,
    ):
        values.append(
            "회원제"
        )

    return list(
        dict.fromkeys(values)
    )


def extract_phone(text):

    matches = re.findall(
        r"(?:0\d{1,2})[-\s)]?\d{3,4}[-\s]?\d{4}",
        text,
    )

    cleaned = []

    for value in matches:

        value = re.sub(
            r"\s+",
            "-",
            value.strip(),
        )

        if value not in cleaned:
            cleaned.append(value)

    return cleaned[:5]


def looks_like_booking_url(url):

    lower = url.lower()

    hints = (
        "reservation",
        "reserve",
        "booking",
        "book",
        "real",
        "login",
        "resv",
        "예약",
    )

    return any(
        hint in lower
        for hint in hints
    )


# ============================================================
# 결과 분석
# ============================================================


def analyze_results(
    club,
    results,
):

    enriched_results = []

    hole_evidence = {}
    operation_evidence = {}
    phone_evidence = {}

    official_candidates = []
    booking_candidates = []

    for result in results:

        score, reasons = (
            identity_score(
                club,
                result,
            )
        )

        url = result["url"]

        text = (
            result["title"]
            + "\n"
            + result["content"]
        )

        holes = extract_holes(
            text
        )

        operations = extract_operation(
            text
        )

        phones = extract_phone(
            text
        )

        official_possible = (
            score >= 4
            and not is_non_official(
                url
            )
        )

        if official_possible:

            official_candidates.append({
                "url": url,
                "identity_score": score,
                "reasons": reasons,
                "title":
                    result["title"],
            })

        if (
            official_possible
            and looks_like_booking_url(
                url
            )
        ):

            booking_candidates.append({
                "url": url,
                "identity_score": score,
                "title":
                    result["title"],
            })

        for n in holes:

            hole_evidence.setdefault(
                str(n),
                []
            ).append(
                url
            )

        for op in operations:

            operation_evidence.setdefault(
                op,
                []
            ).append(
                url
            )

        for phone in phones:

            phone_evidence.setdefault(
                phone,
                []
            ).append(
                url
            )

        enriched_results.append({
            **result,
            "identity_score":
                score,
            "identity_reasons":
                reasons,
            "holes_found":
                holes,
            "operation_found":
                operations,
            "phones_found":
                phones,
            "official_candidate":
                official_possible,
        })

    # 같은 도메인 중복 제거
    unique_official = []
    seen_domains = set()

    for item in sorted(
        official_candidates,
        key=lambda x:
            -x["identity_score"],
    ):

        domain = domain_of(
            item["url"]
        )

        if (
            domain
            and domain not in seen_domains
        ):

            seen_domains.add(
                domain
            )

            unique_official.append(
                item
            )

    return {
        "results":
            enriched_results,

        "official_candidates":
            unique_official,

        "booking_candidates":
            booking_candidates,

        "hole_evidence":
            hole_evidence,

        "operation_evidence":
            operation_evidence,

        "phone_evidence":
            phone_evidence,
    }


# ============================================================
# 자동 판정
#
# APPROVE라는 이름이지만 실제 DB 반영 승인이 아니라
# "검토 가능한 강한 후보"라는 뜻입니다.
# ============================================================


def build_candidate_summary(
    club,
    analysis,
):

    missing = (
        club.get("missing_fields")
        or []
    )

    candidate = {
        "official_url": None,
        "booking_url": None,
        "holes": None,
        "operation_type": None,
        "phone": None,
    }

    confidence = {}
    notes = []

    officials = (
        analysis[
            "official_candidates"
        ]
    )

    # 공식 홈페이지는
    # 단 하나의 강한 identity 후보일 때만
    if (
        "official_url" in missing
        and officials
    ):

        best = officials[0]

        if best[
            "identity_score"
        ] >= 7:

            candidate[
                "official_url"
            ] = best["url"]

            confidence[
                "official_url"
            ] = "REVIEW_A"

        else:

            notes.append(
                "공식 홈페이지 후보는 있으나 identity 재검토 필요"
            )

    # 홀수:
    # 검색결과에서 하나의 값만 나타나도
    # 총 홀수인지 코스 일부인지 알 수 없으므로
    # 자동 A 판정 금지.
    if "holes" in missing:

        hole_values = list(
            analysis[
                "hole_evidence"
            ].keys()
        )

        if len(
            hole_values
        ) == 1:

            candidate[
                "holes"
            ] = int(
                hole_values[0]
            )

            confidence[
                "holes"
            ] = "REVIEW_ONLY"

            notes.append(
                "홀수는 총 홀수/부분 코스 여부 확인 필요"
            )

        elif len(
            hole_values
        ) > 1:

            notes.append(
                "홀수 출처 간 복수 값 발견"
            )

    # 운영형태:
    # 한 종류만 검출될 경우 후보
    if (
        "operation_type"
        in missing
    ):

        ops = list(
            analysis[
                "operation_evidence"
            ].keys()
        )

        if len(ops) == 1:

            candidate[
                "operation_type"
            ] = ops[0]

            confidence[
                "operation_type"
            ] = "REVIEW_ONLY"

        elif len(ops) > 1:

            notes.append(
                "운영형태 출처/문구 충돌"
            )

    # 전화번호:
    # 하나의 번호가 여러 URL에서 반복되면 강한 후보
    if "phone" in missing:

        phones = (
            analysis[
                "phone_evidence"
            ]
        )

        if phones:

            ranked = sorted(
                phones.items(),
                key=lambda x:
                    -len(
                        set(x[1])
                    ),
            )

            phone, urls = (
                ranked[0]
            )

            candidate[
                "phone"
            ] = phone

            confidence[
                "phone"
            ] = (
                "REVIEW_A"
                if len(
                    set(urls)
                ) >= 2
                else "REVIEW_ONLY"
            )

    # 검색결과 자체에 직접 예약 URL이 나온 경우
    if (
        "booking_url"
        in missing
        and analysis[
            "booking_candidates"
        ]
    ):

        best = sorted(
            analysis[
                "booking_candidates"
            ],
            key=lambda x:
                -x[
                    "identity_score"
                ],
        )[0]

        if best[
            "identity_score"
        ] >= 7:

            candidate[
                "booking_url"
            ] = best["url"]

            confidence[
                "booking_url"
            ] = "REVIEW_A"

    return {
        "candidate":
            candidate,
        "confidence":
            confidence,
        "notes":
            notes,
    }


# ============================================================
# Main
# ============================================================


def main():

    print()
    print("=" * 72)
    print("Golf Master DB - FIRST 50 WEB ENRICHMENT")
    print("=" * 72)

    api_key = load_tavily_key()

    diagnostic_path = (
        find_latest_diagnostic()
    )

    diagnostic = json.loads(
        diagnostic_path.read_text(
            encoding="utf-8"
        )
    )

    catalog_bytes = (
        CATALOG_PATH.read_bytes()
    )

    catalog = json.loads(
        catalog_bytes.decode(
            "utf-8-sig"
        )
    )

    if len(catalog) != 553:
        raise RuntimeError(
            f"안전 중단: catalog가 553개가 아닙니다. 현재 {len(catalog)}개"
        )

    catalog_by_id = {
        c.get("id"): c
        for c in catalog
    }

    clubs = (
        diagnostic.get("clubs")
        or []
    )

    if len(clubs) != 50:
        raise RuntimeError(
            f"진단 대상이 50개가 아닙니다. 현재 {len(clubs)}개"
        )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
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

    final_path = (
        output_dir
        / "result.json"
    )

    report_path = (
        output_dir
        / "report.md"
    )

    completed = []
    search_calls = 0

    print()
    print(
        "진단파일:",
        diagnostic_path,
    )

    print(
        "대상:",
        len(clubs),
        "개",
    )

    print()
    print(
        "※ catalog.json은 수정하지 않습니다."
    )
    print()

    for index, diag_club in enumerate(
        clubs,
        start=1,
    ):

        club_id = diag_club.get(
            "id"
        )

        club = catalog_by_id.get(
            club_id
        )

        if not club:

            completed.append({
                "id": club_id,
                "name":
                    diag_club.get(
                        "name"
                    ),
                "status":
                    "HOLD",
                "reason":
                    "현재 catalog에서 ID를 찾지 못함",
            })

            continue

        name = clean(
            club.get("name")
        )

        missing = (
            diag_club.get(
                "missing_fields"
            )
            or []
        )

        print(
            f"[{index:02d}/50] {name}"
        )

        # 누락이 전혀 없으면 검색 생략
        if not missing:

            completed.append({
                "id": club_id,
                "name": name,
                "status":
                    "NO_SEARCH_NEEDED",
                "missing_fields": [],
                "searches": [],
                "analysis": {},
                "candidate_summary": {},
            })

            print(
                "  → 추가 검색 필요 없음"
            )

            continue

        query1 = make_primary_query(
            name,
            clean(
                club.get(
                    "address"
                )
            ),
        )

        searches = []

        try:

            print(
                "  검색 1:",
                query1,
            )

            results1 = tavily_search(
                api_key,
                query1,
            )

            search_calls += 1

            searches.append({
                "query":
                    query1,
                "results":
                    results1,
            })

            analysis = analyze_results(
                club,
                results1,
            )

            # 1차 결과가 너무 약할 경우에만 2차
            strongest = max(
                [
                    x.get(
                        "identity_score",
                        0,
                    )
                    for x
                    in analysis[
                        "results"
                    ]
                ]
                or [0]
            )

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
                        name
                    )
                )

                print(
                    "  검색 2:",
                    query2,
                )

                results2 = tavily_search(
                    api_key,
                    query2,
                )

                search_calls += 1

                searches.append({
                    "query":
                        query2,
                    "results":
                        results2,
                })

                combined = (
                    results1
                    + results2
                )

                analysis = (
                    analyze_results(
                        club,
                        combined,
                    )
                )

            summary = (
                build_candidate_summary(
                    diag_club,
                    analysis,
                )
            )

            # 결과 상태
            candidate_values = [
                v
                for v
                in summary[
                    "candidate"
                ].values()
                if v
                not in (
                    None,
                    "",
                    [],
                )
            ]

            if candidate_values:

                status = (
                    "PARTIAL"
                )

            else:

                status = "HOLD"

            completed.append({
                "id":
                    club_id,

                "name":
                    name,

                "status":
                    status,

                "missing_fields":
                    missing,

                "existing_facts":
                    diag_club.get(
                        "current_facts"
                    ),

                "existing_evidence":
                    diag_club.get(
                        "existing_evidence"
                    ),

                "searches":
                    searches,

                "analysis":
                    analysis,

                "candidate_summary":
                    summary,
            })

            print(
                "  →",
                status,
                "| 후보:",
                {
                    k: v
                    for k, v
                    in summary[
                        "candidate"
                    ].items()
                    if v
                },
            )

        except Exception as exc:

            completed.append({
                "id":
                    club_id,
                "name":
                    name,
                "status":
                    "ERROR",
                "missing_fields":
                    missing,
                "searches":
                    searches,
                "error":
                    f"{type(exc).__name__}: {exc}",
            })

            print(
                "  → ERROR:",
                type(exc).__name__,
                exc,
            )

        # 매 골프장마다 checkpoint 저장
        checkpoint = {
            "mode":
                "WEB_ENRICHMENT_REVIEW_ONLY",

            "created_at":
                datetime.now()
                .astimezone()
                .isoformat(),

            "catalog_count":
                len(catalog),

            "catalog_modified":
                False,

            "diagnostic_source":
                str(
                    diagnostic_path
                ),

            "search_calls":
                search_calls,

            "completed_count":
                len(completed),

            "clubs":
                completed,
        }

        checkpoint_path.write_text(
            json.dumps(
                checkpoint,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        time.sleep(
            REQUEST_DELAY
        )

    # --------------------------------------------------------
    # catalog 불변 검증
    # --------------------------------------------------------

    if (
        CATALOG_PATH.read_bytes()
        != catalog_bytes
    ):

        raise RuntimeError(
            "안전 중단: catalog.json 변경이 감지되었습니다."
        )

    # --------------------------------------------------------
    # 최종 결과
    # --------------------------------------------------------

    counts = {}

    for row in completed:

        status = row.get(
            "status",
            "UNKNOWN",
        )

        counts[status] = (
            counts.get(
                status,
                0,
            )
            + 1
        )

    final = {
        "mode":
            "WEB_ENRICHMENT_REVIEW_ONLY",

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(),

        "catalog_count":
            len(catalog),

        "catalog_modified":
            False,

        "search_calls":
            search_calls,

        "status_counts":
            counts,

        "clubs":
            completed,
    }

    final_path.write_text(
        json.dumps(
            final,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # 사람이 보기 쉬운 보고서
    # --------------------------------------------------------

    lines = [
        "# Golf Master DB - First 50 Web Enrichment",
        "",
        f"- catalog: {len(catalog)}개",
        f"- 대상: {len(completed)}개",
        f"- Tavily 검색 호출: {search_calls}회",
        "- catalog 수정: 없음",
        "",
        "## 결과",
        "",
    ]

    for key in (
        "NO_SEARCH_NEEDED",
        "PARTIAL",
        "HOLD",
        "ERROR",
    ):

        lines.append(
            f"- {key}: {counts.get(key, 0)}개"
        )

    lines.extend([
        "",
        "## 골프장별 결과",
        "",
        "| # | 골프장 | 상태 | 검색 | 후보 필드 |",
        "|---:|---|---|---:|---|",
    ])

    for i, row in enumerate(
        completed,
        start=1,
    ):

        candidate = (
            row.get(
                "candidate_summary",
                {}
            )
            .get(
                "candidate",
                {}
            )
        )

        fields = [
            k
            for k, v
            in candidate.items()
            if v not in (
                None,
                "",
                [],
            )
        ]

        lines.append(
            f"| {i} "
            f"| {row.get('name')} "
            f"| {row.get('status')} "
            f"| {len(row.get('searches') or [])} "
            f"| {', '.join(fields) if fields else '-'} |"
        )

    report_path.write_text(
        "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("FIRST 50 검색 완료")
    print("=" * 72)

    print()
    print(
        "Tavily 실제 호출:",
        search_calls,
        "회",
    )

    print(
        "결과:",
        counts,
    )

    print(
        "catalog.json 수정:",
        False,
    )

    print()
    print(
        "결과 JSON:",
        final_path,
    )

    print(
        "검토 보고서:",
        report_path,
    )

    print()
    print(
        "SUCCESS: 검색 결과만 저장했고 catalog.json은 변경하지 않았습니다."
    )


if __name__ == "__main__":
    main()