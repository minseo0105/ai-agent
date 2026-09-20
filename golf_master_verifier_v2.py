# -*- coding: utf-8 -*-
"""
Golf Master Verifier v2
========================================================
- catalog.json 수정 없음
- Tavily 추가 호출 없음
- LLM 호출 없음
- Pipeline v3.1 수집결과 재사용
- V1보다 보수적인 필드 단위 검증
- A_VERIFIED / B_SUPPORTED / SOURCE_CONFLICT / REVIEW / HOLD
"""

from __future__ import annotations

import json
import re
import hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
from urllib.parse import urlparse
from typing import Any


ROOT = Path(__file__).resolve().parent

CATALOG_PATH = ROOT / "data" / "golf" / "catalog.json"

PIPELINE_ROOT = (
    ROOT / "data" / "golf" / "enrichment" / "pipeline_v3_1"
)

OUTPUT_ROOT = (
    ROOT / "data" / "golf" / "enrichment" / "verifier_v2"
)

EXPECTED_COUNT = 553
VERSION = "2.0"


THIRD_PARTY = {
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


def clean(v: Any) -> str:
    return "" if v is None else str(v).strip()


def valid(v: Any) -> bool:
    if v is None:
        return False

    if isinstance(v, str):
        return v.strip().lower() not in {
            "",
            "없음",
            "미확인",
            "확인 필요",
            "정보 없음",
            "none",
            "null",
            "unknown",
            "-",
        }

    if isinstance(v, (list, dict, tuple)):
        return bool(v)

    return True


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sha(b: bytes):
    return hashlib.sha256(b).hexdigest()


def domain(url):
    try:
        d = urlparse(clean(url)).netloc.lower().split(":")[0]
        if d.startswith("www."):
            d = d[4:]
        return d
    except Exception:
        return ""


def third_party(url):
    d = domain(url)

    if not d:
        return True

    return any(
        d == x or d.endswith("." + x)
        for x in THIRD_PARTY
    )


def same_domain(a, b):
    da = domain(a)
    db = domain(b)

    if not da or not db:
        return False

    return (
        da == db
        or da.endswith("." + db)
        or db.endswith("." + da)
    )


def phone_norm(v):
    return re.sub(r"\D", "", clean(v))


def same_phone(a, b):
    aa = phone_norm(a)
    bb = phone_norm(b)

    return (
        len(aa) >= 8
        and len(bb) >= 8
        and aa == bb
    )


def op_norm(v):
    x = clean(v)

    if x in {
        "대중제",
        "비회원제",
        "퍼블릭",
        "대중제_명시",
    }:
        return "대중제"

    if x in {
        "회원제",
        "회원제_명시",
    }:
        return "회원제"

    if x in {
        "혼합",
        "혼합형",
        "회원제+대중제",
        "혼합_홀수명시",
    }:
        return "혼합"

    return None


def public(club):
    return (
        (club.get("verification") or {})
        .get("public_data")
        or {}
    )


def public_phone(club):
    p = public(club)

    for key in ("phone", "TELNO", "telno"):
        if valid(p.get(key)):
            return p[key]

    return None


def public_op(club):
    p = public(club)

    if p.get("matched") is not True:
        return None

    return op_norm(
        p.get("business_type")
        or p.get("DTL_SALS_STTS_NM")
    )


def verified_value(club, field):
    data = club.get("verified_basic_info") or {}
    item = data.get(field)

    if not isinstance(item, dict):
        return None

    for key in ("value", "verified_value"):
        if valid(item.get(key)):
            return item[key]

    if item.get("verified") is True and valid(club.get(field)):
        return club[field]

    if (
        item.get("confidence") in {"A", "VERIFIED"}
        and valid(club.get(field))
    ):
        return club[field]

    return None


def latest_pipeline():
    candidates = []

    for p in PIPELINE_ROOT.rglob("result_*.json"):
        try:
            d = load(p)
        except Exception:
            continue

        if (
            d.get("complete") is True
            and d.get("catalog_count") == EXPECTED_COUNT
        ):
            candidates.append(p)

    if not candidates:
        raise RuntimeError(
            "완료된 pipeline_v3_1 결과를 찾지 못했습니다."
        )

    return max(candidates, key=lambda x: x.stat().st_mtime)


def candidate_rows(row, field):
    return (
        (row.get("field_candidates") or {})
        .get(field)
        or []
    )


# ============================================================
# OFFICIAL URL
# ============================================================

def verify_official(club, row):

    existing_verified = verified_value(
        club, "official_url"
    )

    if valid(existing_verified):
        return {
            "status": "A_VERIFIED",
            "value": existing_verified,
            "reason": "existing_verified_basic_info",
        }

    current = club.get("official_url")

    candidates = []

    for x in candidate_rows(row, "official_url"):

        url = clean(x.get("value"))

        if not url or third_party(url):
            continue

        candidates.append(x)

    # 기존 URL이 있고 검색결과와 동일 도메인
    if valid(current):

        supports = [
            x for x in candidates
            if same_domain(
                current,
                x.get("value"),
            )
        ]

        if supports:
            return {
                "status": "A_VERIFIED",
                "value": current,
                "reason": "existing_domain_supported_by_search",
                "evidence_count": len(supports),
            }

        # 기존 URL 자체가 제3자면 확실한 문제
        if third_party(current):
            return {
                "status": "SOURCE_CONFLICT",
                "value": current,
                "reason": "existing_url_is_third_party",
            }

        # 기존 공식 도메인을 검색이 못 찾았다고
        # 곧바로 충돌시키지 않는다.
        return {
            "status": "B_SUPPORTED",
            "value": current,
            "reason": "existing_non_third_party_domain",
        }

    # 신규 후보
    grouped = defaultdict(list)

    for x in candidates:
        d = domain(x.get("value"))

        if d:
            grouped[d].append(x)

    if not grouped:
        return {
            "status": "HOLD",
            "value": None,
            "reason": "no_safe_domain_candidate",
        }

    ranked = sorted(
        grouped.items(),
        key=lambda x: (
            max(
                int(y.get("identity_score") or 0)
                for y in x[1]
            ),
            len(x[1]),
        ),
        reverse=True,
    )

    best_domain, best_rows = ranked[0]

    best_score = max(
        int(x.get("identity_score") or 0)
        for x in best_rows
    )

    # 검색결과만으로 공식 운영주체임을 확정하지 않는다.
    if best_score >= 8:
        return {
            "status": "B_SUPPORTED",
            "value": best_rows[0]["value"],
            "reason": "strong_non_third_party_domain_candidate",
            "identity_score": best_score,
        }

    return {
        "status": "REVIEW",
        "value": best_rows[0]["value"],
        "reason": "weak_domain_candidate",
    }


# ============================================================
# BOOKING
# ============================================================

def verify_booking(club, row, official):

    verified = verified_value(
        club, "booking_url"
    )

    if valid(verified):
        return {
            "status": "A_VERIFIED",
            "value": verified,
            "reason": "existing_verified_booking",
        }

    current = club.get("booking_url")

    official_url = (
        official.get("value")
        or club.get("official_url")
    )

    if valid(current):

        if (
            valid(official_url)
            and same_domain(
                current,
                official_url,
            )
        ):
            return {
                "status": "A_VERIFIED",
                "value": current,
                "reason": "existing_booking_on_official_domain",
            }

        return {
            "status": "REVIEW",
            "value": current,
            "reason": "existing_booking_domain_not_confirmed",
        }

    candidates = []

    for x in candidate_rows(row, "booking_url"):

        url = clean(x.get("value"))

        if not url:
            continue

        if third_party(url):
            continue

        if (
            valid(official_url)
            and same_domain(
                url,
                official_url,
            )
        ):
            candidates.append(x)

    if not candidates:
        return {
            "status": "HOLD",
            "value": None,
            "reason": "no_official_domain_booking_candidate",
        }

    best = max(
        candidates,
        key=lambda x: int(
            x.get("identity_score") or 0
        ),
    )

    return {
        "status": "B_SUPPORTED",
        "value": best.get("value"),
        "reason": "booking_candidate_on_official_domain",
    }


# ============================================================
# PHONE
# ============================================================

def verify_phone(club, row):

    verified = verified_value(
        club, "phone"
    )

    if valid(verified):
        return {
            "status": "A_VERIFIED",
            "value": verified,
            "reason": "existing_verified_phone",
        }

    direct = club.get("phone")
    pub = public_phone(club)

    web = []

    for x in candidate_rows(row, "phone"):
        if valid(x.get("value")):
            web.append(x.get("value"))

    # catalog + public 일치
    if (
        valid(direct)
        and valid(pub)
        and same_phone(direct, pub)
    ):
        return {
            "status": "A_VERIFIED",
            "value": direct,
            "reason": "catalog_and_public_data_agree",
        }

    # public + web 일치
    if valid(pub):

        support = [
            x for x in web
            if same_phone(pub, x)
        ]

        if support:
            return {
                "status": "A_VERIFIED",
                "value": pub,
                "reason": "public_data_and_web_agree",
            }

        # 정확 매칭된 공공데이터는 검색 미검출만으로
        # 충돌시키지 않는다.
        if public(club).get("matched") is True:
            return {
                "status": "B_SUPPORTED",
                "value": pub,
                "reason": "exact_public_data_phone",
            }

    if valid(direct):

        support = [
            x for x in web
            if same_phone(direct, x)
        ]

        if support:
            return {
                "status": "A_VERIFIED",
                "value": direct,
                "reason": "catalog_phone_supported_by_web",
            }

        return {
            "status": "B_SUPPORTED",
            "value": direct,
            "reason": "existing_catalog_phone",
        }

    groups = defaultdict(list)

    for x in web:
        n = phone_norm(x)

        if len(n) >= 8:
            groups[n].append(x)

    if not groups:
        return {
            "status": "HOLD",
            "value": None,
            "reason": "no_phone",
        }

    ranked = sorted(
        groups.values(),
        key=len,
        reverse=True,
    )

    best = ranked[0]

    if len(best) >= 2:
        return {
            "status": "B_SUPPORTED",
            "value": best[0],
            "reason": "multiple_web_results_agree",
        }

    return {
        "status": "REVIEW",
        "value": best[0],
        "reason": "single_web_phone",
    }


# ============================================================
# OPERATION TYPE
# ============================================================

def verify_operation(club, row):

    verified = verified_value(
        club, "operation_type"
    )

    if valid(verified):
        return {
            "status": "A_VERIFIED",
            "value": op_norm(verified) or verified,
            "reason": "existing_verified_operation",
        }

    direct = op_norm(
        club.get("operation_type")
    )

    pub = public_op(club)

    web = []

    for x in candidate_rows(
        row, "operation_type"
    ):
        n = op_norm(x.get("value"))

        if n:
            web.append(n)

    counts = Counter(web)

    # catalog와 exact public이 서로 충돌하는 경우는
    # 실제 출처 충돌로 보존
    if (
        direct
        and pub
        and direct != pub
    ):
        return {
            "status": "SOURCE_CONFLICT",
            "value": direct,
            "reason": "catalog_vs_public_data",
            "catalog_value": direct,
            "public_value": pub,
            "web_counts": dict(counts),
        }

    # catalog + public 일치
    if (
        direct
        and pub
        and direct == pub
    ):
        return {
            "status": "A_VERIFIED",
            "value": direct,
            "reason": "catalog_and_public_data_agree",
        }

    # exact public data
    if pub:

        if counts.get(pub, 0) >= 1:
            return {
                "status": "A_VERIFIED",
                "value": pub,
                "reason": "public_data_and_web_agree",
            }

        # 검색결과에 다른 키워드가 있다고 바로 conflict하지 않음
        return {
            "status": "B_SUPPORTED",
            "value": pub,
            "reason": "exact_public_data_operation",
            "web_counts": dict(counts),
        }

    if direct:

        if counts.get(direct, 0) >= 1:
            return {
                "status": "A_VERIFIED",
                "value": direct,
                "reason": "catalog_and_web_agree",
            }

        return {
            "status": "B_SUPPORTED",
            "value": direct,
            "reason": "existing_catalog_operation",
            "web_counts": dict(counts),
        }

    if not counts:
        return {
            "status": "HOLD",
            "value": None,
            "reason": "no_operation_evidence",
        }

    ranked = counts.most_common()

    # 검색 텍스트만으로는 A 불가
    if (
        len(ranked) == 1
        or (
            len(ranked) > 1
            and ranked[0][1] > ranked[1][1]
        )
    ):
        return {
            "status": "REVIEW",
            "value": ranked[0][0],
            "reason": "web_only_operation_candidate",
            "web_counts": dict(counts),
        }

    return {
        "status": "REVIEW",
        "value": None,
        "reason": "ambiguous_web_operation",
        "web_counts": dict(counts),
    }


# ============================================================
# HOLES
# ============================================================

def structural_hole_evidence(row):

    """
    Pipeline의 검색결과 원문에서 '총/전체 N홀' 같은
    구조적 표현만 다시 검사한다.

    단순 '18홀' 언급은 총 홀수 근거로 사용하지 않는다.
    """

    values = []

    patterns = [
        r"총\s*(\d{1,3})\s*홀",
        r"전체\s*(\d{1,3})\s*홀",
        r"총\s*(\d{1,3})\s*holes?",
        r"total\s*(\d{1,3})\s*holes?",
    ]

    for result in row.get("results") or []:

        text = (
            clean(result.get("title"))
            + " "
            + clean(result.get("content"))
        )

        for pattern in patterns:

            for m in re.findall(
                pattern,
                text,
                flags=re.I,
            ):
                try:
                    n = int(m)
                except Exception:
                    continue

                if (
                    9 <= n <= 144
                    and n % 9 == 0
                ):
                    values.append(n)

    return values


def verify_holes(club, row):

    verified = verified_value(
        club, "holes"
    )

    if valid(verified):
        return {
            "status": "A_VERIFIED",
            "value": verified,
            "reason": "existing_verified_holes",
        }

    current = club.get("holes")

    evidence = structural_hole_evidence(
        row
    )

    counts = Counter(evidence)

    if valid(current):

        try:
            current_n = int(current)
        except Exception:
            current_n = None

        if (
            current_n
            and counts.get(current_n, 0) >= 1
        ):
            return {
                "status": "A_VERIFIED",
                "value": current_n,
                "reason": "existing_holes_supported_by_total_holes_expression",
                "support_count": counts[current_n],
            }

        # 웹에서 다른 총 홀수가 잡혀도
        # 검색 snippet만으로 기존값을 conflict 처리하지 않는다.
        return {
            "status": "B_SUPPORTED",
            "value": current,
            "reason": "existing_catalog_holes",
            "structural_web_counts": dict(counts),
        }

    if not counts:
        return {
            "status": "HOLD",
            "value": None,
            "reason": "no_structural_total_holes_evidence",
        }

    ranked = counts.most_common()

    best, count = ranked[0]

    if (
        len(ranked) >= 2
        and ranked[0][1] == ranked[1][1]
    ):
        return {
            "status": "REVIEW",
            "value": None,
            "reason": "conflicting_total_holes_expressions",
            "counts": dict(counts),
        }

    # 검색 snippet만이므로 자동입력 A로 올리지 않는다.
    return {
        "status": "B_SUPPORTED",
        "value": best,
        "reason": "structural_total_holes_candidate",
        "support_count": count,
        "counts": dict(counts),
    }


# ============================================================
# ONE CLUB
# ============================================================

def verify_club(club, row):

    official = verify_official(
        club, row
    )

    booking = verify_booking(
        club,
        row,
        official,
    )

    holes = verify_holes(
        club, row
    )

    operation = verify_operation(
        club, row
    )

    phone = verify_phone(
        club, row
    )

    fields = {
        "official_url": official,
        "booking_url": booking,
        "holes": holes,
        "operation_type": operation,
        "phone": phone,
    }

    statuses = [
        x["status"]
        for x in fields.values()
    ]

    if "SOURCE_CONFLICT" in statuses:
        overall = "SOURCE_CONFLICT"

    elif "REVIEW" in statuses:
        overall = "REVIEW"

    elif "HOLD" in statuses:
        overall = "PARTIAL"

    elif "B_SUPPORTED" in statuses:
        overall = "SUPPORTED"

    else:
        overall = "A_VERIFIED"

    return {
        "id": clean(club.get("id")),
        "name": clean(club.get("name")),
        "address": clean(club.get("address")),
        "overall_status": overall,
        "fields": fields,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 78)
    print("Golf Master Verifier v2")
    print("=" * 78)

    original = CATALOG_PATH.read_bytes()
    original_hash = sha(original)

    catalog = json.loads(
        original.decode("utf-8-sig")
    )

    if len(catalog) != EXPECTED_COUNT:
        raise RuntimeError(
            f"catalog={len(catalog)} / expected={EXPECTED_COUNT}"
        )

    print("현재 catalog:", len(catalog))

    pipeline_path = latest_pipeline()

    print("Pipeline:")
    print(pipeline_path)

    pipeline = load(pipeline_path)

    pindex = {
        clean(x.get("id")): x
        for x in pipeline.get("clubs") or []
        if clean(x.get("id"))
    }

    print(
        "Pipeline records:",
        len(pindex)
    )

    results = []

    overall = Counter()

    field_counts = {
        f: Counter()
        for f in (
            "official_url",
            "booking_url",
            "holes",
            "operation_type",
            "phone",
        )
    }

    print()
    print("553개 재판정 중...")

    for i, club in enumerate(
        catalog,
        1,
    ):

        cid = clean(
            club.get("id")
        )

        row = pindex.get(
            cid,
            {},
        )

        result = verify_club(
            club,
            row,
        )

        result["catalog_position"] = i

        results.append(result)

        overall[
            result["overall_status"]
        ] += 1

        for field, info in (
            result["fields"].items()
        ):
            field_counts[field][
                info["status"]
            ] += 1

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    run = OUTPUT_ROOT / stamp

    run.mkdir(
        parents=True,
        exist_ok=False,
    )

    auto_safe = []
    supported = []
    conflicts = []
    review = []
    hold = []

    for club in results:

        for field, info in club[
            "fields"
        ].items():

            record = {
                "id": club["id"],
                "name": club["name"],
                "field": field,
                "value": info.get("value"),
                "status": info["status"],
                "reason": info.get("reason"),
                "detail": info,
            }

            if info["status"] == "A_VERIFIED":
                auto_safe.append(record)

            elif info["status"] == "B_SUPPORTED":
                supported.append(record)

            elif info["status"] == "SOURCE_CONFLICT":
                conflicts.append(record)

            elif info["status"] == "REVIEW":
                review.append(record)

            else:
                hold.append(record)

    output = {
        "verifier_version": VERSION,
        "created_at": datetime.now().astimezone().isoformat(),
        "mode": "DRY_RUN_ONLY",
        "catalog_count": len(catalog),
        "catalog_sha256": original_hash,
        "catalog_modified": False,
        "pipeline_result": str(pipeline_path),
        "overall_counts": dict(overall),
        "field_counts": {
            k: dict(v)
            for k, v in field_counts.items()
        },
        "A_VERIFIED_count": len(auto_safe),
        "B_SUPPORTED_count": len(supported),
        "SOURCE_CONFLICT_count": len(conflicts),
        "REVIEW_count": len(review),
        "HOLD_count": len(hold),
        "clubs": results,
    }

    save(
        run / "verification_result.json",
        output,
    )

    save(
        run / "A_VERIFIED.json",
        auto_safe,
    )

    save(
        run / "B_SUPPORTED.json",
        supported,
    )

    save(
        run / "SOURCE_CONFLICT.json",
        conflicts,
    )

    save(
        run / "REVIEW.json",
        review,
    )

    save(
        run / "HOLD.json",
        hold,
    )

    # catalog 불변성 확인
    if CATALOG_PATH.read_bytes() != original:
        raise RuntimeError(
            "catalog.json 변경 감지"
        )

    print()
    print("=" * 78)
    print("VERIFIER v2 DRY RUN COMPLETE")
    print("=" * 78)

    print()
    print("[전체 골프장]")

    for status in (
        "A_VERIFIED",
        "SUPPORTED",
        "REVIEW",
        "PARTIAL",
        "SOURCE_CONFLICT",
    ):
        print(
            f"{status}: "
            f"{overall.get(status, 0)}"
        )

    print()
    print("[필드별]")

    for field, counts in (
        field_counts.items()
    ):

        print()
        print(field)

        for status in (
            "A_VERIFIED",
            "B_SUPPORTED",
            "SOURCE_CONFLICT",
            "REVIEW",
            "HOLD",
        ):
            print(
                f"  {status}: "
                f"{counts.get(status, 0)}"
            )

    print()
    print("[전체 필드]")
    print(
        "A_VERIFIED:",
        len(auto_safe)
    )
    print(
        "B_SUPPORTED:",
        len(supported)
    )
    print(
        "SOURCE_CONFLICT:",
        len(conflicts)
    )
    print(
        "REVIEW:",
        len(review)
    )
    print(
        "HOLD:",
        len(hold)
    )

    print()
    print("추가 Tavily 호출: 0")
    print("LLM 호출: 0")
    print("catalog.json 수정: False")

    print()
    print("결과 폴더:")
    print(run)

    print()
    print(
        "자동반영 검토대상:",
        run / "A_VERIFIED.json"
    )

    print(
        "강한 보조정보:",
        run / "B_SUPPORTED.json"
    )

    print(
        "출처충돌:",
        run / "SOURCE_CONFLICT.json"
    )


if __name__ == "__main__":
    main()