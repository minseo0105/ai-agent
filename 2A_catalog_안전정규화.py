from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "data" / "golf" / "catalog.json"
BACKUP_DIR = ROOT / "data" / "golf" / "backups"
REPORT = ROOT / "data" / "golf" / "2A_normalization_report.json"

INVALID_COURSE_LABELS = {
    "", "(스코어 등록 불가)", "스코어 등록 불가", "score unavailable"
}

def clean(v):
    return str(v or "").strip()

def normalize_operation_type(v):
    s = clean(v)
    if not s:
        return ""
    compact = re.sub(r"\s+", "", s)
    if "회원" in compact and ("대중" in compact or "퍼블릭" in compact):
        return "혼합"
    if "회원" in compact:
        return "회원제"
    if "대중" in compact or "퍼블릭" in compact:
        return "대중제(퍼블릭)"
    return ""

def extract_courses_from_kga(kga):
    out = []
    for combo in (kga or {}).get("course_combinations") or []:
        if not isinstance(combo, str):
            continue
        combo = combo.strip()
        if combo in INVALID_COURSE_LABELS:
            continue
        for x in re.split(r"\s*\+\s*", combo):
            x = x.strip()
            if not x or "스코어 등록 불가" in x:
                continue
            if x not in out:
                out.append(x)
    return out

def infer_holes_only_from_explicit_evidence(club):
    # 추정 금지. 이름의 '(9홀)' 또는 KGA 티명 '(18)'처럼 숫자가 명시된 경우만 사용.
    name = clean(club.get("name"))
    m = re.search(r"\((9|18|27|36|45|54)\s*홀\)", name)
    if m:
        return int(m.group(1)), "name_explicit"

    ratings = ((club.get("kga") or {}).get("ratings") or [])
    explicit = []
    for r in ratings:
        tee = clean((r or {}).get("tee"))
        m = re.search(r"\((9|18|27|36|45|54)\)", tee)
        if m:
            explicit.append(int(m.group(1)))
    if explicit and len(set(explicit)) == 1:
        return explicit[0], "kga_tee_explicit"
    return None, ""

def city_from_address(addr):
    a = clean(addr)
    if not a:
        return ""
    patterns = [
        r"^(?:서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|울산광역시|세종특별자치시)\s+([가-힣]+(?:구|군))",
        r"^(?:경기도|강원특별자치도|강원도|충청북도|충청남도|전북특별자치도|전라북도|전라남도|경상북도|경상남도|제주특별자치도)\s+([가-힣]+(?:시|군))",
    ]
    for p in patterns:
        m = re.search(p, a)
        if m:
            return re.sub(r"(시|군|구)$", "", m.group(1))
    if a.startswith("서울"):
        return "서울"
    if a.startswith("인천"):
        return "인천"
    if a.startswith("부산"):
        return "부산"
    if a.startswith("대구"):
        return "대구"
    if a.startswith("광주"):
        return "광주"
    if a.startswith("대전"):
        return "대전"
    if a.startswith("울산"):
        return "울산"
    if a.startswith("세종"):
        return "세종"
    if a.startswith("제주"):
        return "제주"
    return ""

def recompute_basic_count(c):
    return sum(bool(clean(c.get(k))) for k in ("address", "phone", "official_url"))

def main():
    if not CATALOG.exists():
        raise SystemExit(f"catalog.json을 찾지 못했습니다: {CATALOG}")

    data = json.loads(CATALOG.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise SystemExit("catalog.json 최상위 구조가 list가 아닙니다. 변경하지 않았습니다.")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"catalog_before_2A_normalize_{stamp}.json"
    shutil.copy2(CATALOG, backup)

    stats = Counter()
    samples = []

    for c in data:
        changed = []

        ver = c.get("verification") or {}
        pub = ver.get("public_data") or {}
        kga = c.get("kga") or {}

        # 1) 공공데이터에서 이미 안전 매칭된 값만 상위 필드로 정규화
        if pub.get("matched") is True:
            paddr = clean(pub.get("address"))
            pphone = clean(pub.get("phone"))

            if paddr and not clean(c.get("address")):
                c["address"] = paddr
                changed.append("address")
                stats["address_filled"] += 1

            if pphone and not clean(c.get("phone")):
                c["phone"] = pphone
                changed.append("phone")
                stats["phone_filled"] += 1

            op = normalize_operation_type(pub.get("business_type"))
            if op and not clean(c.get("operation_type")):
                c["operation_type"] = op
                c["operation_type_source"] = "행정안전부_생활_골프장 조회서비스"
                changed.append("operation_type")
                stats["operation_type_filled"] += 1

        # 2) KGA 코스조합에서 개별 코스명만 추출. 홀수는 계산하지 않음.
        if kga.get("matched") is True and not (c.get("courses") or []):
            courses = extract_courses_from_kga(kga)
            if courses:
                c["courses"] = courses
                c["courses_source"] = "KGA course_combinations"
                changed.append("courses")
                stats["courses_filled"] += 1

        # 3) 홀수는 명시적 숫자 증거가 있는 경우에만 채움.
        if c.get("holes") in (None, "", 0):
            holes, src = infer_holes_only_from_explicit_evidence(c)
            if holes:
                c["holes"] = holes
                c["holes_source"] = src
                changed.append("holes")
                stats["holes_filled_explicit_only"] += 1

        # 4) 과거 오류 방지: city가 경기남부/경기북부 등 권역명으로 들어간 경우,
        #    실제 공공데이터 주소가 있을 때만 시/군으로 복원.
        current_city = clean(c.get("city"))
        addr = clean(c.get("address")) or clean(pub.get("address"))
        actual_city = city_from_address(addr)
        if current_city in {"경기남부", "경기북부", "강원영서", "강원영동", "충북", "충남", "경북", "경남", "전북", "전남"} and actual_city:
            if actual_city != current_city:
                c["city"] = actual_city
                c.setdefault("region_field_sources", {})["city"] = "public_address"
                changed.append("city")
                stats["city_repaired"] += 1

        new_count = recompute_basic_count(c)
        if c.get("service_basic_count") != new_count:
            c["service_basic_count"] = new_count
            changed.append("service_basic_count")
            stats["basic_count_recomputed"] += 1

        if changed:
            stats["clubs_changed"] += 1
            if len(samples) < 30:
                samples.append({"name": c.get("name"), "changed": changed})

    # 안전장치: 555개 구조가 갑자기 크게 바뀌지 않도록 개수 유지 확인
    if len(data) < 500:
        raise SystemExit(f"안전 중단: catalog 건수가 예상보다 적습니다({len(data)}). 백업만 생성했고 원본은 변경하지 않았습니다.")

    CATALOG.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    report = {
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "catalog_count": len(data),
        "backup": str(backup),
        "catalog": str(CATALOG),
        "rules": [
            "기존 안전 매칭 public_data만 사용",
            "운영형태는 public_data.business_type이 명시된 경우만 반영",
            "코스명은 KGA course_combinations에서 추출하되 홀수 추정 금지",
            "홀수는 이름 '(9홀)' 또는 KGA tee '(18)'처럼 숫자가 명시된 경우만 반영",
            "city 권역명 오류는 실제 주소에서 시/군이 확인되는 경우만 복원",
            "기존 값은 원칙적으로 덮어쓰지 않음"
        ],
        "stats": dict(stats),
        "samples": samples
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 60)
    print("2A 안전 정규화 완료")
    print(f"catalog: {len(data)}개")
    print(f"변경 골프장: {stats['clubs_changed']}개")
    print(f"운영형태 보강: {stats['operation_type_filled']}개")
    print(f"코스명 보강: {stats['courses_filled']}개")
    print(f"홀수 보강(명시적 증거만): {stats['holes_filled_explicit_only']}개")
    print(f"city 오류 복원: {stats['city_repaired']}개")
    print(f"주소 보강: {stats['address_filled']}개")
    print(f"전화 보강: {stats['phone_filled']}개")
    print("-" * 60)
    print("백업:", backup)
    print("리포트:", REPORT)
    print("=" * 60)

if __name__ == "__main__":
    main()
