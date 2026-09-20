# -*- coding: utf-8 -*-

"""
Golf Play / Facility Evidence Verifier v2

목적
--------------------------------------------------
1. play_facility_web_v1에서 수집한 최신 결과 자동 탐색
2. 추가 Tavily 검색 없음
3. GPT / LLM 호출 없음
4. catalog.json 수정 없음
5. 골프장별 6개 조건의 검색 근거를 안전하게 재분류

분류
--------------------------------------------------
VERIFIED_CANDIDATE
SUPPORTED_B
CONDITIONAL
NEGATIVE_CANDIDATE
REFERENCE_ONLY
CONTAMINATED_HOLD
UNKNOWN

주의
--------------------------------------------------
이 단계에서는 어떤 값도 catalog.json에 자동 반영하지 않습니다.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


# ============================================================
# 기본 경로
# ============================================================

ROOT = Path(__file__).resolve().parent

CATALOG = ROOT / "data" / "golf" / "catalog.json"

WEBROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "play_facility_web_v1"
)

OUTROOT = (
    ROOT
    / "data"
    / "golf"
    / "enrichment"
    / "play_facility_verifier_v2"
)

EXPECTED_CATALOG_COUNT = 553


# ============================================================
# 검증 대상 필드
# ============================================================

FIELDS = {
    "two_person": "2인 플레이",
    "three_person": "3인 플레이",
    "nine_hole_twice": "9홀×2 라운드",
    "night_round": "야간 라운드",
    "par3": "PAR3 연습장",
    "driving_range": "야외 연습장",
}


# ============================================================
# 단독 확정 근거로 사용하지 않을 약한 출처
# ============================================================

WEAK_DOMAINS = (
    "naver.com",
    "daum.net",
    "tistory.com",
    "youtube.com",
    "instagram.com",
    "facebook.com",
    "kakao.com",
    "sbs.co.kr",
    "dbegl.com",
    "baigolf",
)


# ============================================================
# 기본 함수
# ============================================================

def load_json(path: Path):
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def save_json(path: Path, data):
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


def sha256(path: Path):
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def get_domain(url):
    try:
        return (
            urlparse(
                str(url or "")
            )
            .netloc
            .lower()
            .replace("www.", "")
        )
    except Exception:
        return ""


def is_weak_source(url):
    d = get_domain(url)

    return any(
        weak in d
        for weak in WEAK_DOMAINS
    )


def same_domain(a, b):
    if not a or not b:
        return False

    return (
        a == b
        or a.endswith("." + b)
        or b.endswith("." + a)
    )


# ============================================================
# catalog에서 이미 확인된 공식 도메인 수집
# ============================================================

def get_official_domains(club):

    domains = set()

    for key in (
        "official_url",
        "booking_url",
        "website",
        "homepage",
    ):
        value = club.get(key)

        d = get_domain(value)

        if d:
            domains.add(d)

    verified = (
        club.get("verified_basic_info")
        or {}
    )

    if isinstance(verified, dict):

        for item in verified.values():

            if not isinstance(item, dict):
                continue

            for key in (
                "source_url",
                "url",
            ):

                d = get_domain(
                    item.get(key)
                )

                if d:
                    domains.add(d)

    return domains


# ============================================================
# 가장 최신 웹조사 결과 자동 탐색
# ============================================================

def find_latest_web_result():

    if not WEBROOT.exists():
        raise FileNotFoundError(
            f"폴더 없음: {WEBROOT}"
        )

    files = list(
        WEBROOT.glob(
            "result_*.json"
        )
    )

    if not files:
        raise FileNotFoundError(
            "play_facility_web_v1의 "
            "result_*.json 파일을 찾지 못했습니다."
        )

    return max(
        files,
        key=lambda p: p.stat().st_mtime,
    )


# ============================================================
# evidence 분류
# ============================================================

def classify_evidence(
    club,
    evidence_list,
):

    # --------------------------------------------------------
    # 1. 근거 자체가 없음
    # --------------------------------------------------------

    if not evidence_list:

        return (
            "UNKNOWN",
            {
                "reason": "no_evidence"
            },
        )

    # --------------------------------------------------------
    # 2. 대상 골프장 identity가 잡힌 결과만 추림
    # --------------------------------------------------------

    identity_matches = [
        e
        for e in evidence_list
        if e.get("identity_match") is True
    ]

    if not identity_matches:

        return (
            "CONTAMINATED_HOLD",
            {
                "reason":
                    "no_target_identity_match"
            },
        )

    # --------------------------------------------------------
    # 3. 블로그/포털 등 약한 출처 제외
    # --------------------------------------------------------

    usable = [
        e
        for e in identity_matches
        if (
            not e.get("weak_source")
            and not is_weak_source(
                e.get("url")
            )
        )
    ]

    # --------------------------------------------------------
    # 4. 강한 출처에서 부정 문구가 발견됨
    #
    # 자동 False로 확정하지 않는다.
    # NEGATIVE_CANDIDATE로만 저장.
    # --------------------------------------------------------

    negative = [
        e
        for e in usable
        if e.get("negative_signal")
    ]

    if negative:

        return (
            "NEGATIVE_CANDIDATE",
            {
                "reason":
                    "negative_phrase_on_stronger_identity_source",
                "evidence_count":
                    len(negative),
            },
        )

    # --------------------------------------------------------
    # 5. 조건부 문구
    #
    # 예:
    # 주중만
    # 특정 시간대
    # 회원 동반
    # 이벤트 기간
    # 추가요금
    # --------------------------------------------------------

    conditional = [
        e
        for e in usable
        if e.get("conditional_signal")
    ]

    if conditional:

        return (
            "CONDITIONAL",
            {
                "reason":
                    "day_time_member_fee_event_condition",
                "evidence_count":
                    len(conditional),
            },
        )

    # --------------------------------------------------------
    # 6. 기존 catalog에 확인된 공식 도메인이 있는지
    # --------------------------------------------------------

    official_domains = (
        get_official_domains(club)
    )

    official_evidence = []

    for e in usable:

        d = get_domain(
            e.get("url")
        )

        if not d:
            continue

        if any(
            same_domain(
                d,
                official_domain,
            )
            for official_domain
            in official_domains
        ):

            official_evidence.append(e)

    # --------------------------------------------------------
    # 7. 공식 도메인 + identity 일치
    #
    # 이것도 아직 catalog에 자동 적용하지 않는다.
    # --------------------------------------------------------

    if official_evidence:

        return (
            "VERIFIED_CANDIDATE",
            {
                "reason":
                    "identity_match_and_existing_official_domain",
                "evidence_count":
                    len(official_evidence),
            },
        )

    # --------------------------------------------------------
    # 8. 서로 다른 비약한 출처 2개 이상
    #
    # B급 지지 근거
    # --------------------------------------------------------

    domains = {
        get_domain(
            e.get("url")
        )
        for e in usable
        if get_domain(
            e.get("url")
        )
    }

    if len(domains) >= 2:

        return (
            "SUPPORTED_B",
            {
                "reason":
                    "two_or_more_nonweak_identity_domains",
                "domain_count":
                    len(domains),
            },
        )

    # --------------------------------------------------------
    # 9. 비약한 출처 하나
    # --------------------------------------------------------

    if usable:

        return (
            "REFERENCE_ONLY",
            {
                "reason":
                    "single_nonweak_identity_source",
                "evidence_count":
                    len(usable),
            },
        )

    # --------------------------------------------------------
    # 10. identity는 맞지만 약한 출처뿐
    # --------------------------------------------------------

    return (
        "REFERENCE_ONLY",
        {
            "reason":
                "identity_found_but_only_weak_sources"
        },
    )


# ============================================================
# 메인
# ============================================================

def main():

    print(
        "=" * 76
    )

    print(
        "Golf Play / Facility Evidence Verifier v2"
    )

    print(
        "=" * 76
    )

    # --------------------------------------------------------
    # catalog 안전검사
    # --------------------------------------------------------

    if not CATALOG.exists():

        raise FileNotFoundError(
            f"catalog 없음: {CATALOG}"
        )

    catalog_hash_before = (
        sha256(CATALOG)
    )

    catalog = load_json(
        CATALOG
    )

    if isinstance(
        catalog,
        list,
    ):

        clubs = catalog

    else:

        clubs = (
            catalog.get("clubs")
            or catalog.get("records")
            or catalog.get("data")
            or []
        )

    if len(clubs) != EXPECTED_CATALOG_COUNT:

        raise RuntimeError(
            "안전 중단: "
            f"catalog={len(clubs)} / "
            f"expected={EXPECTED_CATALOG_COUNT}"
        )

    clubs_by_id = {
        str(
            c.get("id")
            or ""
        ): c
        for c in clubs
    }

    # --------------------------------------------------------
    # 최신 웹조사 결과 자동 탐색
    # --------------------------------------------------------

    source = (
        find_latest_web_result()
    )

    print(
        "자동 선택 source:"
    )

    print(
        source
    )

    print()

    web_data = load_json(
        source
    )

    records = (
        web_data.get("records")
        or []
    )

    errors = (
        web_data.get("errors")
        or []
    )

    # --------------------------------------------------------
    # 통계 준비
    # --------------------------------------------------------

    overall = Counter()

    field_stats = defaultdict(
        Counter
    )

    rows = []

    buckets = defaultdict(
        list
    )

    seen_ids = set()

    # --------------------------------------------------------
    # 전체 record 검증
    # --------------------------------------------------------

    for rec in records:

        cid = str(
            rec.get("id")
            or ""
        )

        seen_ids.add(
            cid
        )

        club = (
            clubs_by_id.get(
                cid,
                {},
            )
        )

        field_result = {}

        for field, label in FIELDS.items():

            evidence_list = (
                rec
                .get(
                    "fields",
                    {},
                )
                .get(
                    field,
                    [],
                )
                or []
            )

            classification, detail = (
                classify_evidence(
                    club,
                    evidence_list,
                )
            )

            overall[
                classification
            ] += 1

            field_stats[
                field
            ][
                classification
            ] += 1

            result = {
                "label":
                    label,

                "class":
                    classification,

                "detail":
                    detail,

                "evidence":
                    evidence_list,

                # 매우 중요:
                # 아직 자동 적용하지 않음
                "auto_apply":
                    False,
            }

            field_result[
                field
            ] = result

            flat_item = {
                "id":
                    cid,

                "name":
                    rec.get("name")
                    or club.get("name"),

                "field":
                    field,

                "label":
                    label,

                "class":
                    classification,

                "detail":
                    detail,

                "evidence":
                    evidence_list,

                "auto_apply":
                    False,
            }

            buckets[
                classification
            ].append(
                flat_item
            )

        rows.append(
            {
                "id":
                    cid,

                "name":
                    rec.get("name")
                    or club.get("name"),

                "checked_at":
                    rec.get("checked_at"),

                "fields":
                    field_result,
            }
        )

    # --------------------------------------------------------
    # error / 누락 확인
    # --------------------------------------------------------

    error_ids = {
        str(
            e.get("id")
            or ""
        )
        for e in errors
    }

    missing_ids = [
        cid
        for cid
        in clubs_by_id
        if (
            cid not in seen_ids
            and cid not in error_ids
        )
    ]

    # --------------------------------------------------------
    # 결과 폴더
    # --------------------------------------------------------

    stamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    outdir = (
        OUTROOT
        / stamp
    )

    outdir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # 전체 결과 저장
    # --------------------------------------------------------

    verifier_result = {
        "schema_version":
            "2.0",

        "created_at":
            datetime.now()
            .astimezone()
            .isoformat(
                timespec="seconds"
            ),

        "source":
            str(source),

        "catalog_count":
            len(clubs),

        "web_records":
            len(records),

        "web_errors":
            errors,

        "missing_ids":
            missing_ids,

        "records":
            rows,
    }

    save_json(
        outdir
        / "verifier_result.json",
        verifier_result,
    )

    # --------------------------------------------------------
    # 분류별 파일
    # --------------------------------------------------------

    classification_names = [
        "VERIFIED_CANDIDATE",
        "SUPPORTED_B",
        "CONDITIONAL",
        "NEGATIVE_CANDIDATE",
        "REFERENCE_ONLY",
        "CONTAMINATED_HOLD",
        "UNKNOWN",
    ]

    for classification in classification_names:

        save_json(
            outdir
            / f"{classification}.json",

            buckets[
                classification
            ],
        )

    # --------------------------------------------------------
    # 보고서
    # --------------------------------------------------------

    report = {
        "source":
            str(source),

        "catalog_count":
            len(clubs),

        "web_records":
            len(records),

        "web_error_count":
            len(errors),

        "missing_count":
            len(missing_ids),

        "overall_field_classification":
            dict(overall),

        "field_stats":
            {
                field:
                    dict(stats)

                for field, stats
                in field_stats.items()
            },

        "verified_candidate_count":
            len(
                buckets[
                    "VERIFIED_CANDIDATE"
                ]
            ),

        "supported_b_count":
            len(
                buckets[
                    "SUPPORTED_B"
                ]
            ),

        "conditional_count":
            len(
                buckets[
                    "CONDITIONAL"
                ]
            ),

        "negative_candidate_count":
            len(
                buckets[
                    "NEGATIVE_CANDIDATE"
                ]
            ),

        "reference_only_count":
            len(
                buckets[
                    "REFERENCE_ONLY"
                ]
            ),

        "contaminated_hold_count":
            len(
                buckets[
                    "CONTAMINATED_HOLD"
                ]
            ),

        "unknown_count":
            len(
                buckets[
                    "UNKNOWN"
                ]
            ),

        "catalog_sha256_before":
            catalog_hash_before,

        "catalog_sha256_after":
            sha256(
                CATALOG
            ),

        "catalog_unchanged":
            (
                catalog_hash_before
                == sha256(
                    CATALOG
                )
            ),
    }

    save_json(
        outdir
        / "report.json",
        report,
    )

    # --------------------------------------------------------
    # catalog 변경 여부 최종검사
    # --------------------------------------------------------

    catalog_hash_after = (
        sha256(
            CATALOG
        )
    )

    if (
        catalog_hash_after
        != catalog_hash_before
    ):

        raise RuntimeError(
            "catalog.json 변경 감지! "
            "안전 중단합니다."
        )

    # --------------------------------------------------------
    # 화면 출력
    # --------------------------------------------------------

    print(
        "catalog:",
        len(clubs),
    )

    print(
        "웹 records:",
        len(records),
    )

    print(
        "웹 errors:",
        len(errors),
    )

    print(
        "누락:",
        len(missing_ids),
    )

    print()

    print(
        "[전체 필드 판정]"
    )

    print(
        "-" * 76
    )

    for classification in classification_names:

        print(
            f"{classification:22s}: "
            f"{overall.get(classification, 0)}"
        )

    print()

    print(
        "[필드별 판정]"
    )

    print(
        "-" * 76
    )

    for field, label in FIELDS.items():

        print(
            f"{label:12s}: "
            f"{dict(field_stats[field])}"
        )

    print()

    print(
        "-" * 76
    )

    print(
        "VERIFIED_CANDIDATE:",
        len(
            buckets[
                "VERIFIED_CANDIDATE"
            ]
        ),
    )

    print(
        "SUPPORTED_B:",
        len(
            buckets[
                "SUPPORTED_B"
            ]
        ),
    )

    print(
        "CONDITIONAL:",
        len(
            buckets[
                "CONDITIONAL"
            ]
        ),
    )

    print(
        "NEGATIVE_CANDIDATE:",
        len(
            buckets[
                "NEGATIVE_CANDIDATE"
            ]
        ),
    )

    print(
        "REFERENCE_ONLY:",
        len(
            buckets[
                "REFERENCE_ONLY"
            ]
        ),
    )

    print(
        "CONTAMINATED_HOLD:",
        len(
            buckets[
                "CONTAMINATED_HOLD"
            ]
        ),
    )

    print(
        "UNKNOWN:",
        len(
            buckets[
                "UNKNOWN"
            ]
        ),
    )

    print(
        "-" * 76
    )

    print(
        "catalog.json 수정:",
        False,
    )

    print()

    print(
        "결과 폴더:"
    )

    print(
        outdir
    )

    print()

    print(
        "=" * 76
    )

    print(
        "검증 완료"
    )

    print(
        "=" * 76
    )

    print(
        "다음 단계:"
    )

    print(
        "VERIFIED_CANDIDATE와 SUPPORTED_B를 "
        "dry-run 검토한 뒤 안전한 값만 Master DB에 반영합니다."
    )


if __name__ == "__main__":
    main()