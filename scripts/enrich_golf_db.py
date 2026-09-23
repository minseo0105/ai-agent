"""정밀 골프 DB의 빈 필드를 DB 안에 이미 있는 공식 근거로만 채운다.

원칙 (data_layers.policy):
  - 사실 정보는 official_homepage / KGA / public_data 출처만 사용한다.
  - 추정하지 않는다. 대상 필드가 이미 채워져 있으면 덮어쓰지 않는다.
  - 채운 값은 레코드의 `_derived_fields`에 (필드, 값, 출처, 근거 필드) 로 남긴다.

사용:
  venv\\Scripts\\python.exe scripts\\enrich_golf_db.py <입력.json> <출력.json>
"""

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

EMPTY = (None, "", [], {}, "unknown", "확인 필요", "미확인", "없음")


def empty(value):
    return value in EMPTY


def derive(record, field, value, source, basis, target=None):
    (target if target is not None else record)[field] = value
    record.setdefault("_derived_fields", []).append({
        "field": field, "value": value, "source": source, "basis": basis,
        "derived_at": date.today().isoformat(), "method": "internal_official_evidence_v1",
    })


def normalize_business_type(value):
    text = str(value or "").strip()
    return {"정규대중": "대중제", "일반대중": "대중제", "비회원제": "대중제", "회원제": "회원제"}.get(text)


def enrich(record, stats):
    public = (record.get("verification") or {}).get("public_data") or {}
    kga = record.get("kga") or {}
    ident = record.get("identity_verification") or {}
    overview = record.get("club_overview") or {}
    groups = record.get("course_groups") if isinstance(record.get("course_groups"), list) else []

    # 주소: 공공데이터(행정안전부) → KGA
    if empty(record.get("address")):
        if public.get("matched") and not empty(public.get("address")):
            derive(record, "address", public["address"], "public_data", "verification.public_data.address")
            stats["address"] += 1
        elif kga.get("matched") and not empty(kga.get("address")):
            derive(record, "address", kga["address"], "KGA", "kga.address")
            stats["address"] += 1
    location = record.get("location")
    if isinstance(location, dict) and empty(location.get("address")) and not empty(record.get("address")):
        location["address"] = record["address"]

    # 전화: 공식 홈페이지 확인값 → 공공데이터
    if empty(record.get("phone")):
        if not empty(record.get("phone_official")):
            derive(record, "phone", record["phone_official"], "official_homepage", "phone_official")
            stats["phone"] += 1
        elif public.get("matched") and not empty(public.get("phone")):
            derive(record, "phone", public["phone"], "public_data", "verification.public_data.phone")
            stats["phone"] += 1

    # 운영형태: 공공데이터 업종 구분
    if empty(record.get("operation_type")):
        value = normalize_business_type(public.get("business_type"))
        if value and public.get("matched"):
            derive(record, "operation_type", value, "public_data", "verification.public_data.business_type")
            record["operation_type_source"] = "public_data"
            stats["operation_type"] += 1

    # 정식 명칭: 공식 홈페이지 신원 확인
    if empty(record.get("official_name")) and ident.get("confidence") == "confirmed" and not empty(ident.get("official_name")):
        derive(record, "official_name", ident["official_name"], "official_homepage", "identity_verification.official_name")
        stats["official_name"] += 1

    # 홀 수: 공식 개요 → 공식 코스 그룹 합계
    if empty(record.get("holes")):
        if overview.get("confidence") == "confirmed" and isinstance(overview.get("holes_count"), int):
            derive(record, "holes", overview["holes_count"], "official_homepage", "club_overview.holes_count")
            record["holes_source"] = "club_overview"
            stats["holes"] += 1
        elif groups and all(isinstance(g, dict) and isinstance(g.get("holes"), int) and g.get("confidence") == "confirmed" for g in groups):
            derive(record, "holes", sum(g["holes"] for g in groups), "official_homepage", "sum(course_groups.holes)")
            record["holes_source"] = "course_groups"
            stats["holes"] += 1

    # 코스 목록: 공식 코스 그룹명
    if empty(record.get("courses")) and groups:
        names = [str(g.get("name")).strip() for g in groups if isinstance(g, dict) and g.get("name")]
        if names:
            derive(record, "courses", names, "official_homepage", "course_groups.name")
            record["courses_source"] = "course_groups"
            stats["courses"] += 1


def main(src, dst):
    records = json.loads(Path(src).read_text(encoding="utf-8-sig"))
    stats = Counter()
    for record in records:
        if record.get("service_status") == "excluded":
            continue
        enrich(record, stats)
    Path(dst).write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"records={len(records)} filled={dict(stats)} -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
