from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

# 실행 위치: ai-agent/tools/diagnose_golf_db_completeness.py
PROJECT_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = PROJECT_DIR / "data" / "golf" / "catalog.json"
REPORT_PATH = PROJECT_DIR / "data" / "golf" / "db_completeness_report.json"

# 기본정보 갱신 정책: 6개월
REFRESH_DAYS = 183


def text(value):
    return str(value).strip() if value is not None else ""


def first_value(club, *keys):
    for key in keys:
        value = club.get(key)
        if text(value):
            return value
    return None


def valid_url(value):
    value = text(value)
    if not value:
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def get_address(club):
    return first_value(club, "address", "road_address", "lot_address")


def get_phone(club):
    return first_value(club, "phone", "tel", "telephone")


def get_operation_type(club):
    return first_value(
        club,
        "operation_type",
        "membership_type",
        "business_type",
        "club_type",
        "golf_type",
    )


def get_holes(club):
    value = club.get("holes")
    if value not in (None, "", 0, "0"):
        return value

    # courses 안에 각 코스 홀 수가 있으면 합산
    total = 0
    found = False
    for course in club.get("courses") or []:
        if not isinstance(course, dict):
            continue
        try:
            holes = int(course.get("holes") or 0)
        except (TypeError, ValueError):
            holes = 0
        if holes > 0:
            total += holes
            found = True

    return total if found else None


def has_course_structure(club):
    if club.get("courses"):
        return True

    kga = club.get("kga") or {}
    return bool(kga.get("course_combinations") or kga.get("ratings"))


def get_official_url(club):
    return first_value(
        club,
        "official_url",
        "homepage",
        "homepage_url",
        "website",
        "website_url",
    )


def get_booking_url(club):
    return first_value(
        club,
        "booking_url",
        "reservation_url",
        "reserve_url",
    )


def has_intro(club):
    profile = club.get("profile") or {}

    return bool(
        first_value(
            club,
            "description",
            "intro",
            "introduction",
            "course_overview",
        )
        or first_value(profile, "description", "intro", "summary")
    )


def has_experience_info(club):
    """
    후기 기반 체감정보가 이미 구조화되어 있는지 확인.
    현재/향후 여러 저장 구조를 모두 허용한다.
    """
    trait_keys = (
        "fairway",
        "green",
        "maintenance",
        "facility",
        "scenery",
        "pace",
        "value",
    )

    containers = (
        club.get("experience") or {},
        club.get("traits") or {},
        club.get("descriptive_traits") or {},
        club.get("review_summary") or {},
    )

    for obj in containers:
        if isinstance(obj, dict):
            if any(text(obj.get(key)) for key in trait_keys):
                return True

    return False


def public_data_matched(club):
    public = ((club.get("verification") or {}).get("public_data") or {})
    return public.get("matched") is True


def kga_matched(club):
    return (club.get("kga") or {}).get("matched") is True


def has_kga_ratings(club):
    return bool((club.get("kga") or {}).get("ratings"))


def parse_date(value):
    value = text(value)
    if not value:
        return None

    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def latest_checked_date(club):
    """
    기존 catalog에 들어 있을 수 있는 여러 확인일 필드 중
    가장 최근 날짜를 사용한다.
    """
    values = []

    for key in (
        "official_checked_at",
        "basic_checked_at",
        "profile_checked_at",
        "checked_at",
        "updated_at",
        "data_checked",
        "pool_checked",
    ):
        if club.get(key):
            values.append(club.get(key))

    verification = club.get("verification") or {}
    if isinstance(verification, dict):
        if verification.get("checked_at"):
            values.append(verification.get("checked_at"))

        public = verification.get("public_data") or {}
        if isinstance(public, dict) and public.get("checked_at"):
            values.append(public.get("checked_at"))

    kga = club.get("kga") or {}
    if isinstance(kga, dict):
        for key in ("checked_at", "ratings_checked_at"):
            if kga.get(key):
                values.append(kga.get(key))

    parsed = [parse_date(v) for v in values]
    parsed = [d for d in parsed if d is not None]

    return max(parsed) if parsed else None


def load_catalog():
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    if isinstance(raw, list):
        return raw

    # 혹시 catalog 최상위가 dict인 경우에도 안전하게 대응
    if isinstance(raw, dict):
        for key in ("clubs", "items", "courses", "data"):
            if isinstance(raw.get(key), list):
                return raw[key]

    raise ValueError(
        "catalog.json에서 골프장 목록을 찾지 못했습니다. "
        "최상위 구조를 확인해 주세요."
    )


def main():
    print()
    print("=" * 72)
    print("골프장 Master DB 1단계 완성도 진단")
    print("=" * 72)

    if not CATALOG_PATH.exists():
        print(f"[오류] catalog.json을 찾지 못했습니다.")
        print(f"찾은 위치: {CATALOG_PATH}")
        print()
        print("이 파일을 ai-agent/tools 폴더에 넣었는지 확인해 주세요.")
        return

    clubs = load_catalog()
    total = len(clubs)

    checks = {
        "주소": lambda c: bool(get_address(c)),
        "전화번호": lambda c: bool(get_phone(c)),
        "공공데이터 매칭": public_data_matched,
        "KGA 매칭": kga_matched,
        "KGA Course/Slope": has_kga_ratings,
        "운영형태(회원제/대중제)": lambda c: bool(get_operation_type(c)),
        "총 홀수": lambda c: bool(get_holes(c)),
        "코스 구성": has_course_structure,
        "공식 홈페이지": lambda c: valid_url(get_official_url(c)),
        "공식 예약 페이지": lambda c: valid_url(get_booking_url(c)),
        "골프장 소개": has_intro,
        "후기 체감정보": has_experience_info,
    }

    completeness = {}

    for label, check in checks.items():
        filled = sum(1 for club in clubs if check(club))
        completeness[label] = {
            "filled": filled,
            "missing": total - filled,
            "filled_pct": round(filled / total * 100, 1) if total else 0.0,
        }

    # 6개월 갱신 상태
    cutoff = date.today() - timedelta(days=REFRESH_DAYS)

    fresh = 0
    due = 0
    never_checked = 0

    for club in clubs:
        checked = latest_checked_date(club)

        if checked is None:
            never_checked += 1
        elif checked <= cutoff:
            due += 1
        else:
            fresh += 1

    # 2단계에서 웹검색 대상으로 삼을 기본정보
    # 하나의 골프장에 빈칸이 여러 개 있어도 골프장 1건으로 계산
    search_checks = {
        "운영형태": lambda c: bool(get_operation_type(c)),
        "홀수": lambda c: bool(get_holes(c)),
        "코스구성": has_course_structure,
        "공식홈페이지": lambda c: valid_url(get_official_url(c)),
        "예약페이지": lambda c: valid_url(get_booking_url(c)),
    }

    search_targets = []

    for index, club in enumerate(clubs):
        missing = [
            label
            for label, check in search_checks.items()
            if not check(club)
        ]

        if not missing:
            continue

        search_targets.append(
            {
                "index": index,
                "name": text(
                    first_value(
                        club,
                        "name",
                        "golf_name",
                        "club_name",
                        "official_name",
                    )
                )
                or f"record_{index}",
                "region": text(club.get("region")),
                "city": text(club.get("city")),
                "address": text(get_address(club)),
                "missing": missing,
            }
        )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "catalog_path": str(CATALOG_PATH),
        "total_courses": total,
        "refresh_policy": {
            "basic_info": "6개월",
            "days_used_for_diagnosis": REFRESH_DAYS,
            "cutoff_date": cutoff.isoformat(),
            "review_intelligence": "기본정보와 별도 갱신",
        },
        "field_completeness": completeness,
        "refresh_status": {
            "fresh_under_6m": fresh,
            "due_6m_or_more": due,
            "never_checked": never_checked,
        },
        "basic_search_target_count": len(search_targets),
        "basic_search_targets": search_targets,
        "safety": {
            "catalog_modified": False,
            "paid_api_called": False,
            "web_search_called": False,
            "llm_called": False,
        },
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"전체 골프장 : {total}건")
    print()
    print("[데이터 완성도]")

    for label, result in completeness.items():
        print(
            f"{label:<25}"
            f"{result['filled']:>4}건 "
            f"({result['filled_pct']:>5.1f}%)"
            f"  | 미확인 {result['missing']:>4}건"
        )

    print()
    print("[기본정보 6개월 갱신 상태]")
    print(f"최근 6개월 내 확인 : {fresh}건")
    print(f"6개월 이상 경과    : {due}건")
    print(f"확인일 없음        : {never_checked}건")

    print()
    print("[2단계 검색 예상 대상]")
    print(f"기본정보 검색 필요 골프장 : {len(search_targets)}건")
    print("※ 한 골프장에 빈 필드가 여러 개여도 1건으로 계산")

    print()
    print("[안전 확인]")
    print("catalog.json 수정     : 없음")
    print("웹검색                : 없음")
    print("Tavily 호출           : 없음")
    print("GPT / Claude 호출     : 없음")
    print("API 비용              : 0원")

    print()
    print(f"상세 진단 보고서 저장:")
    print(REPORT_PATH)
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
