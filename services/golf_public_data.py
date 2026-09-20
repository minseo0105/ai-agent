import re
from datetime import date
import requests

# 공식 대상: 행정안전부_생활_골프장 조회서비스 (공공데이터포털 목록 ID 15154978)
PUBLIC_GOLF_DATASET_ID = "15154978"
PUBLIC_GOLF_DATASET_PAGE = "https://www.data.go.kr/data/15154978/openapi.do"

# 사용자 secrets에는 URL을 저장하지 않는다.
# 공공데이터포털 15154978의 Swagger /info 명세에서 확인한 조회 경로.
# 페이지당 최대 100건, returnType=json. 원본 TM 좌표는 WGS84에 덮어쓰지 않는다.
PUBLIC_GOLF_API_ENDPOINT = "https://apis.data.go.kr/1741000/golf_courses/info"

def _norm(s):
    s = re.sub(r"\s+", "", str(s or "")).lower()
    for token in ["컨트리클럽","골프클럽","골프장","countryclub","golfclub","golf","club","cc","gc"]:
        s = s.replace(token, "")
    return re.sub(r"[^0-9a-z가-힣]", "", s)

def _walk_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    # 흔한 data.go.kr 응답 구조를 보수적으로 지원
    candidates = [
        payload.get("items"),
        (payload.get("response") or {}).get("body", {}).get("items"),
        (payload.get("response") or {}).get("body", {}).get("items", {}).get("item")
            if isinstance((payload.get("response") or {}).get("body", {}).get("items"), dict) else None,
        payload.get("data"),
        payload.get("records"),
    ]
    for c in candidates:
        if isinstance(c, list): return c
        if isinstance(c, dict):
            for k in ("item","items","data","records"):
                if isinstance(c.get(k), list): return c[k]
    return []

def _pick(d, names):
    if not isinstance(d, dict): return ""
    lower={str(k).lower():v for k,v in d.items()}
    for n in names:
        v=lower.get(n.lower())
        if v not in (None,""): return str(v).strip()
    return ""

def fetch_public_golf_records(service_key, page_size=100, timeout=15):
    """Official /info contract: 100 rows/page; never expose a keyed URL in errors."""
    if not service_key:
        return []
    from urllib.parse import unquote
    records = []
    for page in range(1, 101):
        try:
            response = requests.get(PUBLIC_GOLF_API_ENDPOINT, params={
                "serviceKey": unquote(service_key), "pageNo": page,
                "numOfRows": min(100, max(1, page_size)), "returnType": "json",
            }, timeout=timeout, allow_redirects=False)
            if response.status_code != 200:
                raise ValueError("HTTP failure")
            payload = response.json()
            head = (payload.get("response") or {}).get("header") or {}
            if str(head.get("resultCode", "")) not in ("00", "0", "INFO-000"):
                raise ValueError("API failure")
            body = payload["response"]["body"]
            total = int(body["totalCount"])
            items = _walk_items(payload)
            if not items and len(records) < total:
                raise ValueError("Incomplete response")
            records.extend(items)
            if len(records) >= total:
                return records
        except Exception:
            raise RuntimeError("공공데이터 조회 실패: 인증·응답 형식·연결 상태 확인 필요") from None
    raise RuntimeError("공공데이터 조회 한도 도달: 불완전한 결과는 적용하지 않습니다.")


def _record_name(record: dict) -> str:
    if not isinstance(record, dict):
        return ""

    return str(record.get("BPLC_NM") or "").strip()
def _record_phone(record: dict) -> str:
    if not isinstance(record, dict):
        return ""

    return str(record.get("TELNO") or "").strip()


def _record_business_status(record: dict) -> dict:
    """
    공공데이터의 영업상태를 원문 그대로 보존한다.
    '영업/정상'이라고 해서 예약 가능을 의미하지 않는다.
    """
    if not isinstance(record, dict):
        return {}

    return {
        "status": str(record.get("SALS_STTS_NM") or "").strip(),
        "detail_status": str(record.get("DTL_SALS_STTS_NM") or "").strip(),
        "closed_date": str(record.get("CLSBIZ_YMD") or "").strip(),
        "data_updated_at": str(record.get("DAT_UPDT_PNT") or "").strip(),
        "last_modified_at": str(record.get("LAST_MDFCN_PNT") or "").strip(),
        "business_type": str(record.get("DTIL_TPBIZ_NM") or "").strip(),
        "management_no": str(record.get("MNG_NO") or "").strip(),
    }


def _public_record_is_operating(record: dict) -> bool:
    """
    공공데이터상 영업 상태인지 판별.
    실제 티타임/예약 가능 여부와는 무관하다.
    """
    if not isinstance(record, dict):
        return False

    status = str(record.get("SALS_STTS_NM") or "").strip()
    detail = str(record.get("DTL_SALS_STTS_NM") or "").strip()
    closed_date = str(record.get("CLSBIZ_YMD") or "").strip()

    if closed_date:
        return False

    return (
        status in {"영업/정상", "영업"}
        or detail == "영업"
    )

def _record_address(record: dict) -> str:
    """공공데이터 골프장 주소 추출 - 도로명주소 우선."""
    if not isinstance(record, dict):
        return ""
    road = str(record.get("ROAD_NM_ADDR") or "").strip()
    lot = str(record.get("LOTNO_ADDR") or "").strip()
    return road or lot


def _record_status(record: dict) -> str:
    if not isinstance(record, dict):
        return ""
    return (
        str(record.get("SALS_STTS_NM") or "").strip()
        or str(record.get("DTL_SALS_STTS_NM") or "").strip()
    )


def match_public_records(clubs, records):
    """정규화 이름이 유일하게 1건 매칭될 때만 공공데이터를 보강한다."""
    idx = {}
    for rec in records:
        name = _record_name(rec)
        key = _norm(name)
        if key:
            idx.setdefault(key, []).append(rec)

    matched = 0
    for club in clubs:
        if not isinstance(club, dict):
            continue

        key = _norm(club.get("name"))
        candidates = idx.get(key, [])
        verification = club.setdefault("verification", {})

        if len(candidates) != 1:
            verification.setdefault("public_data", {"matched": False})
            verification["public_data_last_attempt"] = {
                "matched": False,
                "checked_at": date.today().isoformat(),
                "reason": "ambiguous" if candidates else "not_found",
            }
            continue

        rec = candidates[0]
        public_name = _record_name(rec)
        address = _record_address(rec)
        phone = _record_phone(rec)
        business = _record_business_status(rec)

        verification["public_data"] = {
            "matched": True,
            "checked_at": date.today().isoformat(),
            "dataset_id": PUBLIC_GOLF_DATASET_ID,
            "source_name": "행정안전부_생활_골프장 조회서비스",
            "public_name": public_name,
            "status": business.get("status") or "등록정보 확인",
            "detail_status": business.get("detail_status", ""),
            "closed_date": business.get("closed_date", ""),
            "data_updated_at": business.get("data_updated_at", ""),
            "last_modified_at": business.get("last_modified_at", ""),
            "business_type": business.get("business_type", ""),
            "management_no": business.get("management_no", ""),
            "address": address,
            "operating_in_public_data": _public_record_is_operating(rec),
        }

        if public_name and not club.get("public_data_name"):
            club["public_data_name"] = public_name
        if address and not club.get("address"):
            club["address"] = address
        if phone and not club.get("phone"):
            club["phone"] = phone

        matched += 1

    return clubs, matched


def dual_verification_summary(club):
    """데이터 출처 확인 요약. 운영/예약 가능 판정은 아니다."""
    verification = club.get("verification") or {}
    pub = ((verification.get("public_data") or {}).get("matched") is True)
    vw = bool(
        club.get("vworld_x") is not None
        or str(club.get("pool_source") or "").startswith("VWorld")
    )
    if vw and pub:
        return "공공데이터 2중 확인"
    if vw:
        return "VWorld 확인"
    if pub:
        return "공공데이터 확인"
    return "기본정보 확인 필요"
