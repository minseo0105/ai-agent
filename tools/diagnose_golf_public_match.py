from __future__ import annotations

import json
import re
import hashlib
import sys
from pathlib import Path
from difflib import SequenceMatcher

# 프로젝트 루트를 Python 검색 경로에 추가
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import streamlit as st

from services.golf_public_data import (
    fetch_public_golf_records,
    _record_name,
    _record_address,
)


CATALOG_PATH = BASE_DIR / "data" / "golf" / "catalog.json"
OUTPUT_PATH = BASE_DIR / "data" / "golf" / "public_match_diagnostic.json"


CATALOG_PATH = BASE_DIR / "data" / "golf" / "catalog.json"
OUTPUT_PATH = BASE_DIR / "data" / "golf" / "public_match_diagnostic.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_name(value: str | None) -> str:
    """
    골프장 명칭 비교용 정규화.
    원본 이름은 절대 변경하지 않고 비교할 때만 사용.
    """
    s = str(value or "").strip().lower()

    # 법인표기 제거
    s = re.sub(r"\(주\)|㈜|주식회사", "", s)

    # 공백/기호 제거
    s = re.sub(r"[\s\.\-_·ㆍ/()]+", "", s)

    # 흔한 골프장 표기 통일
    replacements = {
        "컨트리클럽": "cc",
        "countryclub": "cc",
        "골프클럽": "gc",
        "golfclub": "gc",
        "골프장": "",
    }

    for old, new in replacements.items():
        s = s.replace(old, new)

    return s.strip()


def simplify_name(value: str | None) -> str:
    """
    CC / GC 등의 접미사까지 제거한 2차 비교용 이름.
    """
    s = normalize_name(value)

    for suffix in ("cc", "gc"):
        if s.endswith(suffix):
            s = s[:-2]

    return s.strip()


def get_public_name(record):
    return _record_name(record)


def get_public_address(record):
    return _record_address(record)

    for key in possible_keys:
        value = row.get(key)
        if value:
            return str(value).strip()

    return ""


def address_tokens(address: str) -> set[str]:
    """
    주소 중 시/군/구 수준의 비교 가능한 토큰 추출.
    """
    if not address:
        return set()

    parts = re.split(r"\s+", address.strip())

    result = set()

    for part in parts[:5]:
        part = part.strip()

        if not part:
            continue

        if (
            part.endswith("시")
            or part.endswith("군")
            or part.endswith("구")
            or part.endswith("도")
        ):
            result.add(part)

    return result


def address_bonus(catalog_address: str, public_address: str) -> float:
    a = address_tokens(catalog_address)
    b = address_tokens(public_address)

    if not a or not b:
        return 0.0

    common = a & b

    if len(common) >= 2:
        return 0.05

    if len(common) == 1:
        return 0.02

    return 0.0


def similarity_score(
    catalog_name: str,
    public_name: str,
    catalog_address: str = "",
    public_address: str = "",
) -> float:

    a1 = normalize_name(catalog_name)
    b1 = normalize_name(public_name)

    a2 = simplify_name(catalog_name)
    b2 = simplify_name(public_name)

    score1 = SequenceMatcher(None, a1, b1).ratio()
    score2 = SequenceMatcher(None, a2, b2).ratio()

    score = max(score1, score2)

    score += address_bonus(catalog_address, public_address)

    return min(score, 1.0)


def main():

    print()
    print("=" * 60)
    print("골프장 공공데이터 매칭 진단")
    print("=" * 60)

    if not CATALOG_PATH.exists():
        raise FileNotFoundError(
            f"catalog.json을 찾을 수 없습니다: {CATALOG_PATH}"
        )

    before_hash = sha256_file(CATALOG_PATH)

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    if isinstance(catalog, dict):
        catalog_rows = (
            catalog.get("courses")
            or catalog.get("items")
            or catalog.get("data")
            or []
        )
    else:
        catalog_rows = catalog

    if not isinstance(catalog_rows, list):
        raise ValueError("catalog.json 구조를 인식하지 못했습니다.")

    # secrets.toml의 키 사용
    service_key = st.secrets.get("DATA_GO_KR_SERVICE_KEY")

    if not service_key:
        raise RuntimeError(
            "DATA_GO_KR_SERVICE_KEY가 secrets.toml에 없습니다."
        )

    print("공공데이터 조회 중...")

    public_rows = fetch_public_golf_records(service_key)

    if not isinstance(public_rows, list):
        raise RuntimeError("공공데이터 조회 결과가 list가 아닙니다.")

    # 공공데이터 이름 인덱스
    exact_index = {}

    valid_public_rows = []

    for row in public_rows:

        if not isinstance(row, dict):
            continue

        name = get_public_name(row)

        if not name:
            continue

        row_copy = dict(row)
        row_copy["_diagnostic_name"] = name
        row_copy["_diagnostic_address"] = get_public_address(row)

        valid_public_rows.append(row_copy)

        key = normalize_name(name)

        if key:
            exact_index.setdefault(key, []).append(row_copy)

    results = []

    exact_count = 0
    probable_count = 0
    ambiguous_count = 0
    unmatched_count = 0

    for club in catalog_rows:

        if not isinstance(club, dict):
            continue

        catalog_name = str(club.get("name") or "").strip()
        catalog_address = str(club.get("address") or "").strip()

        normalized = normalize_name(catalog_name)

        exact_candidates = exact_index.get(normalized, [])

        # --------------------------------------
        # 1. 정확 이름 매칭
        # --------------------------------------

        if len(exact_candidates) == 1:

            row = exact_candidates[0]

            results.append(
                {
                    "catalog_name": catalog_name,
                    "match_type": "exact_match",
                    "public_name": row["_diagnostic_name"],
                    "similarity": 1.0,
                    "public_address": row["_diagnostic_address"],
                    "candidate_count": 1,
                }
            )

            exact_count += 1
            continue

        # 정확 이름이 여러 개면 바로 자동매칭하지 않음
        if len(exact_candidates) > 1:

            results.append(
                {
                    "catalog_name": catalog_name,
                    "match_type": "ambiguous",
                    "public_name": "",
                    "similarity": 1.0,
                    "public_address": "",
                    "candidate_count": len(exact_candidates),
                    "candidates": [
                        {
                            "name": r["_diagnostic_name"],
                            "address": r["_diagnostic_address"],
                        }
                        for r in exact_candidates[:10]
                    ],
                }
            )

            ambiguous_count += 1
            continue

        # --------------------------------------
        # 2. 유사명칭 탐색
        # --------------------------------------

        candidates = []

        for row in valid_public_rows:

            public_name = row["_diagnostic_name"]
            public_address = row["_diagnostic_address"]

            score = similarity_score(
                catalog_name,
                public_name,
                catalog_address,
                public_address,
            )

            if score >= 0.88:
                candidates.append(
                    {
                        "name": public_name,
                        "address": public_address,
                        "similarity": round(score, 4),
                    }
                )

        candidates.sort(
            key=lambda x: x["similarity"],
            reverse=True,
        )

        # --------------------------------------
        # 유사 후보 1개
        # --------------------------------------

        if len(candidates) == 1:

            best = candidates[0]

            results.append(
                {
                    "catalog_name": catalog_name,
                    "match_type": "probable_match",
                    "public_name": best["name"],
                    "similarity": best["similarity"],
                    "public_address": best["address"],
                    "candidate_count": 1,
                }
            )

            probable_count += 1
            continue

        # --------------------------------------
        # 유사 후보 여러 개
        # --------------------------------------

        if len(candidates) > 1:

            # 1위가 2위보다 충분히 명확하게 높아도
            # 이번 진단에서는 자동 병합하지 않음.
            results.append(
                {
                    "catalog_name": catalog_name,
                    "match_type": "ambiguous",
                    "public_name": candidates[0]["name"],
                    "similarity": candidates[0]["similarity"],
                    "public_address": candidates[0]["address"],
                    "candidate_count": len(candidates),
                    "candidates": candidates[:10],
                }
            )

            ambiguous_count += 1
            continue

        # --------------------------------------
        # 미매칭
        # --------------------------------------

        results.append(
            {
                "catalog_name": catalog_name,
                "match_type": "unmatched",
                "public_name": "",
                "similarity": 0.0,
                "public_address": "",
                "candidate_count": 0,
            }
        )

        unmatched_count += 1

    summary = {
        "catalog_total": len(catalog_rows),
        "public_total": len(public_rows),
        "public_valid_name_total": len(valid_public_rows),
        "exact_match": exact_count,
        "probable_match": probable_count,
        "ambiguous": ambiguous_count,
        "unmatched": unmatched_count,
        "automatic_safe_candidates": exact_count,
        "manual_review_candidates": probable_count + ambiguous_count,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    diagnostic_output = {
        "summary": summary,
        "results": results,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            diagnostic_output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    after_hash = sha256_file(CATALOG_PATH)

    print()
    print(f"현재 catalog           : {len(catalog_rows)}건")
    print(f"공공데이터             : {len(public_rows)}건")
    print()
    print(f"정확 이름 매칭          : {exact_count}건")
    print(f"유사명칭 후보           : {probable_count}건")
    print(f"판단 보류(복수 후보)     : {ambiguous_count}건")
    print(f"미매칭                  : {unmatched_count}건")
    print()
    print(f"자동매칭 안전 후보       : {exact_count}건")
    print(
        f"수동확인 필요            : "
        f"{probable_count + ambiguous_count}건"
    )
    print()
    print(
        "catalog 변경            : "
        + ("없음" if before_hash == after_hash else "⚠ 변경됨")
    )

    print("=" * 60)

    # 샘플 출력
    probable = [
        r for r in results
        if r["match_type"] == "probable_match"
    ]

    ambiguous = [
        r for r in results
        if r["match_type"] == "ambiguous"
    ]

    unmatched = [
        r for r in results
        if r["match_type"] == "unmatched"
    ]

    print()
    print("[유사명칭 후보 - 최대 20건]")

    for r in probable[:20]:
        print(
            f'{r["catalog_name"]} | '
            f'{r["public_name"]} | '
            f'{r["similarity"]:.2f} | '
            f'{r["public_address"]}'
        )

    print()
    print("[판단 보류 - 최대 20건]")

    for r in ambiguous[:20]:
        names = [
            x.get("name", "")
            for x in r.get("candidates", [])
        ]

        print(
            f'{r["catalog_name"]} | '
            + " / ".join(names)
        )

    print()
    print("[미매칭 - 최대 20건]")

    for r in unmatched[:20]:
        print(r["catalog_name"])

    print()
    print("진단 결과 저장:")
    print(OUTPUT_PATH)
    print()


if __name__ == "__main__":
    main()