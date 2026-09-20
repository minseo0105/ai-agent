from __future__ import annotations

import copy
import json
import re
import shutil
import sys
import tomllib
from datetime import date, datetime
from pathlib import Path
from difflib import SequenceMatcher


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from services.golf_public_data import (
    fetch_public_golf_records,
    _record_name,
    _record_address,
    _record_phone,
    _record_business_status,
    _public_record_is_operating,
)

CATALOG_PATH = BASE_DIR / "data" / "golf" / "catalog.json"
BACKUP_DIR = BASE_DIR / "data" / "golf" / "backups"
REPORT_PATH = BASE_DIR / "data" / "golf" / "public_enrichment_report.json"
SECRETS_PATH = BASE_DIR / ".streamlit" / "secrets.toml"

DATASET_ID = "15154978"
SOURCE_NAME = "행정안전부_생활_골프장 조회서비스"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json_atomic(path: Path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def meaningful(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def normalize_name(value: str) -> str:
    s = str(value or "").lower().strip()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"(주식회사|\(주\)|㈜)", "", s)
    s = s.replace("컨트리클럽", "")
    s = s.replace("골프클럽", "")
    s = s.replace("골프장", "")
    s = s.replace("countryclub", "")
    s = s.replace("golfclub", "")
    s = re.sub(r"[^0-9a-z가-힣]", "", s)
    return s


def simplify_name(value: str) -> str:
    s = normalize_name(value)
    for suffix in ("cc", "gc"):
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    return s


def address_region(address: str):
    """
    공공데이터 주소로 앱의 권역/세부권역을 판정.
    주소가 명확하지 않으면 None을 반환해 기존 값을 유지한다.
    """
    a = str(address or "").strip()
    if not a:
        return None

    # 특별/광역시
    if a.startswith("서울특별시") or a.startswith("서울시"):
        return ("수도권", "서울", "서울")
    if a.startswith("인천광역시") or a.startswith("인천시"):
        return ("수도권", "인천", "인천")

    if a.startswith("제주특별자치도") or a.startswith("제주도"):
        return ("제주권", "제주", "제주")

    if a.startswith("충청북도"):
        return ("충청권", "충북", "충북")
    if a.startswith("충청남도"):
        return ("충청권", "충남", "충남")

    if a.startswith("경상북도"):
        return ("영남권", "경북", "경북")
    if a.startswith("경상남도"):
        return ("영남권", "경남", "경남")

    if a.startswith("전북특별자치도") or a.startswith("전라북도"):
        return ("호남권", "전북", "전북")
    if a.startswith("전라남도"):
        return ("호남권", "전남", "전남")

    # 광역시는 앱의 기존 영남/호남 권역에 편입
    if a.startswith(("부산광역시", "대구광역시", "울산광역시")):
        return ("영남권", "경남" if a.startswith(("부산", "울산")) else "경북",
                "부산" if a.startswith("부산") else "울산" if a.startswith("울산") else "대구")
    if a.startswith("광주광역시"):
        return ("호남권", "전남", "광주")
    if a.startswith(("대전광역시", "세종특별자치시")):
        return ("충청권", "충남", "대전" if a.startswith("대전") else "세종")

    if a.startswith("강원특별자치도") or a.startswith("강원도"):
        # 태백산맥 기준을 행정주소만으로 완벽히 판별할 수 없으므로
        # 영동의 명확한 시군만 영동, 나머지는 영서로 둔다.
        yeongdong = ("강릉시", "동해시", "속초시", "삼척시", "고성군", "양양군")
        sub = "강원영동" if any(x in a for x in yeongdong) else "강원영서"
        return ("강원권", sub, sub)

    if a.startswith("경기도"):
        # 서비스에서 사용하는 경기남/북 구분.
        north = (
            "고양시", "파주시", "의정부시", "양주시", "동두천시",
            "포천시", "연천군", "가평군", "구리시", "남양주시"
        )
        sub = "경기북부" if any(x in a for x in north) else "경기남부"
        return ("수도권", sub, sub)

    return None


def read_service_key() -> str:
    if not SECRETS_PATH.exists():
        raise FileNotFoundError(".streamlit/secrets.toml을 찾을 수 없습니다.")

    with SECRETS_PATH.open("rb") as f:
        secrets = tomllib.load(f)

    key = str(secrets.get("DATA_GO_KR_SERVICE_KEY") or "").strip()
    if not key:
        raise RuntimeError("DATA_GO_KR_SERVICE_KEY가 secrets.toml에 없습니다.")
    return key


def build_public_indexes(records):
    exact = {}
    simple = {}

    for rec in records:
        name = _record_name(rec)
        nkey = normalize_name(name)
        skey = simplify_name(name)
        if nkey:
            exact.setdefault(nkey, []).append(rec)
        if skey:
            simple.setdefault(skey, []).append(rec)

    return exact, simple


def choose_safe_record(club_name, exact_idx, simple_idx):
    """
    1) 정규화 exact가 공공데이터에서 유일하면 안전매칭.
    2) 단순화명(cc/gc 제거)이 유일하고 문자열 유사도가 사실상 1.0이면 안전매칭.
    그 외는 보류.
    """
    nkey = normalize_name(club_name)
    candidates = exact_idx.get(nkey, [])
    if len(candidates) == 1:
        return candidates[0], "exact"

    skey = simplify_name(club_name)
    candidates = simple_idx.get(skey, [])
    if len(candidates) == 1:
        public_name = _record_name(candidates[0])
        ratio = SequenceMatcher(
            None, simplify_name(club_name), simplify_name(public_name)
        ).ratio()
        if ratio >= 0.999:
            return candidates[0], "normalized_1.00"

    return None, None


def main():
    print()
    print("=" * 64)
    print("골프장 공공데이터 최종 안전 보강")
    print("=" * 64)

    if not CATALOG_PATH.exists():
        raise FileNotFoundError("catalog.json이 없습니다.")

    catalog = load_json(CATALOG_PATH)
    if not isinstance(catalog, list):
        raise ValueError("catalog.json 최상위 구조가 list가 아닙니다.")

    before_count = len(catalog)
    original = copy.deepcopy(catalog)

    print("공공데이터 652건 조회 중...")
    service_key = read_service_key()
    records = fetch_public_golf_records(service_key)

    exact_idx, simple_idx = build_public_indexes(records)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"catalog_before_public_enrichment_{stamp}.json"
    shutil.copy2(CATALOG_PATH, backup_path)

    today = date.today().isoformat()

    stats = {
        "catalog_total": before_count,
        "public_total": len(records),
        "matched": 0,
        "exact": 0,
        "normalized_1_00": 0,
        "address_added": 0,
        "phone_added": 0,
        "region_corrected": 0,
        "public_operating": 0,
        "public_not_operating": 0,
        "held": 0,
    }
    examples = []

    try:
        for club in catalog:
            if not isinstance(club, dict):
                continue

            club_name = str(club.get("name") or "").strip()
            if not club_name:
                continue

            rec, match_type = choose_safe_record(
                club_name, exact_idx, simple_idx
            )

            if rec is None:
                stats["held"] += 1
                continue

            stats["matched"] += 1

            if match_type == "exact":
                stats["exact"] += 1
            elif match_type == "normalized_1.00":
                stats["normalized_1_00"] += 1

            public_name = _record_name(rec)
            address = _record_address(rec)
            phone = _record_phone(rec)
            business = _record_business_status(rec)
            operating = _public_record_is_operating(rec)

            if operating:
                stats["public_operating"] += 1
            else:
                stats["public_not_operating"] += 1

            if public_name:
                club["public_data_name"] = public_name

            # 기존 검증 주소/전화는 덮어쓰지 않는다.
            if address and not meaningful(club.get("address")):
                club["address"] = address
                stats["address_added"] += 1

            if phone and not meaningful(club.get("phone")):
                club["phone"] = phone
                stats["phone_added"] += 1

            verification = club.setdefault("verification", {})
            verification["public_data"] = {
                "matched": True,
                "checked_at": today,
                "dataset_id": DATASET_ID,
                "source_name": SOURCE_NAME,
                "match_type": match_type,
                "public_name": public_name,
                "address": address,
                "phone": phone,
                "status": business.get("status", ""),
                "detail_status": business.get("detail_status", ""),
                "closed_date": business.get("closed_date", ""),
                "data_updated_at": business.get("data_updated_at", ""),
                "last_modified_at": business.get("last_modified_at", ""),
                "business_type": business.get("business_type", ""),
                "management_no": business.get("management_no", ""),
                "operating_in_public_data": operating,
            }

            sources = verification.get("sources", [])
            if not isinstance(sources, list):
                sources = []
            if "data.go.kr" not in sources:
                sources.append("data.go.kr")
            verification["sources"] = sources
            verification["checked_at"] = today

            # 공공데이터 매칭만으로 예약가능/완전검증 상태로 올리지 않는다.
            current_status = str(verification.get("status") or "").lower()
            if current_status in ("", "unverified"):
                verification["status"] = "partial"

            # 주소가 확보된 경우에만 좌표 추정 지역을 교정한다.
            region = address_region(address)
            if region:
                area, subregion, city = region

                old_area = club.get("area")
                old_subregion = club.get("subregion")
                old_city = club.get("city")

                # 공식/수동 검증 지역은 건드리지 않고,
                # 좌표 추정/미확인/빈 값만 공공주소로 교정.
                region_source = str(club.get("region_source") or "").lower()
                can_replace = (
                    not region_source
                    or region_source in {
                        "coordinate_estimate",
                        "estimated",
                        "vworld_coordinate",
                        "unknown",
                        "unverified",
                    }
                    or not meaningful(old_area)
                    or not meaningful(old_subregion)
                )

                if can_replace:
                    club["area"] = area
                    club["subregion"] = subregion
                    club["city"] = city
                    club["region_source"] = "public_address"
                    club["region_checked_at"] = today

                    if (
                        old_area != area
                        or old_subregion != subregion
                        or old_city != city
                    ):
                        stats["region_corrected"] += 1
                        if len(examples) < 20:
                            examples.append({
                                "name": club_name,
                                "before": {
                                    "area": old_area,
                                    "subregion": old_subregion,
                                    "city": old_city,
                                },
                                "after": {
                                    "area": area,
                                    "subregion": subregion,
                                    "city": city,
                                },
                                "address": address,
                            })

        if len(catalog) != before_count:
            raise RuntimeError(
                "안전장치 작동: catalog 레코드 수가 변경되어 저장을 중단합니다."
            )

        save_json_atomic(CATALOG_PATH, catalog)

        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "stats": stats,
            "region_examples": examples,
            "backup": str(backup_path),
            "catalog": str(CATALOG_PATH),
        }
        save_json_atomic(REPORT_PATH, report)

    except Exception:
        # 어떤 오류든 원본 catalog로 즉시 복구
        save_json_atomic(CATALOG_PATH, original)
        raise

    print()
    print(f"전체 catalog              : {stats['catalog_total']}건")
    print(f"공공데이터                : {stats['public_total']}건")
    print(f"안전 매칭/보강            : {stats['matched']}건")
    print(f"  - exact                 : {stats['exact']}건")
    print(f"  - 표기차이 1.00          : {stats['normalized_1_00']}건")
    print(f"보류                      : {stats['held']}건")
    print()
    print(f"새 주소 추가              : {stats['address_added']}건")
    print(f"새 전화번호 추가           : {stats['phone_added']}건")
    print(f"주소 기반 지역 교정        : {stats['region_corrected']}건")
    print()
    print(f"공공데이터상 영업          : {stats['public_operating']}건")
    print(f"공공데이터상 비영업/기타    : {stats['public_not_operating']}건")
    print()
    print("※ '공공데이터상 영업'은 실시간 예약 가능을 의미하지 않습니다.")
    print()
    print("백업:", backup_path)
    print("보고서:", REPORT_PATH)
    print("catalog:", CATALOG_PATH)

    if examples:
        print()
        print("[지역 교정 예시 - 최대 20건]")
        for ex in examples:
            b = ex["before"]
            a = ex["after"]
            print(
                f"{ex['name']} | "
                f"{b.get('area')}/{b.get('subregion')}/{b.get('city')} "
                f"→ {a.get('area')}/{a.get('subregion')}/{a.get('city')} "
                f"| {ex['address']}"
            )

    print("=" * 64)
    print()


if __name__ == "__main__":
    main()
