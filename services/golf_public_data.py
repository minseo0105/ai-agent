import re
from datetime import date
import requests

# 공식 대상: 행정안전부_생활_골프장 조회서비스 (공공데이터포털 목록 ID 15154978)
PUBLIC_GOLF_DATASET_ID = "15154978"
PUBLIC_GOLF_DATASET_PAGE = "https://www.data.go.kr/data/15154978/openapi.do"

# 사용자 secrets에는 URL을 저장하지 않는다.
# 실제 REST operation endpoint는 공공데이터포털 활용명세에서 확인한 뒤
# 이 파일 한 곳에만 고정한다. 확인되지 않은 URL을 임의 추정하지 않는다.
PUBLIC_GOLF_API_ENDPOINT = None

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

def fetch_public_golf_records(service_key, page_size=1000, timeout=15):
    """사용자가 승인받은 공공데이터포털 API에서 JSON 레코드를 읽는다."""
    if not service_key:
        return []
    api_url = PUBLIC_GOLF_API_ENDPOINT
    if not api_url:
        raise RuntimeError(
            "공공데이터 인증키는 설정되어 있지만 골프장 API의 실제 REST 요청주소가 "
            "아직 소스에 확정되지 않았습니다."
        )
    params={
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": page_size,
        "type": "json",
        "_type": "json",
        "resultType": "json",
    }
    r=requests.get(api_url, params=params, timeout=timeout)
    r.raise_for_status()
    try:
        payload=r.json()
    except Exception as exc:
        raise RuntimeError("공공데이터 API 응답이 JSON이 아닙니다. 활용신청한 API의 응답형식을 확인하세요.") from exc
    return _walk_items(payload)

def _record_name(rec):
    return _pick(rec, [
        "사업장명","업소명","시설명","체육시설명","골프장명","개방시설명","개방장소명",
        "bplcnm","facltnm","name"
    ])

def _record_address(rec):
    return _pick(rec, [
        "소재지도로명주소","도로명주소","소재지주소","소재지전체주소","주소",
        "rdnwhladdr","sitewhladdr","address"
    ])

def _record_status(rec):
    return _pick(rec, [
        "영업상태명","영업상태","상세영업상태명","상태","trdstatenm","dtlstatenm","status"
    ])

def match_public_records(clubs, records):
    """이름 중심으로 보수적 매칭. 공공데이터에 없는 정보는 만들어내지 않는다."""
    idx={}
    for rec in records:
        name=_record_name(rec)
        key=_norm(name)
        if key:
            idx.setdefault(key, []).append(rec)

    matched=0
    for club in clubs:
        key=_norm(club.get("name"))
        candidates=idx.get(key, [])
        # 긴 포함관계만 보조 허용
        if not candidates and len(key)>=5:
            for rk, vals in idx.items():
                if len(rk)>=5 and (key in rk or rk in key):
                    candidates=vals
                    break
        if not candidates:
            club.setdefault("verification", {})
            club["verification"]["public_data"] = {
                "matched": False, "checked_at": date.today().isoformat()
            }
            continue
        rec=candidates[0]
        status=_record_status(rec)
        address=_record_address(rec)
        club.setdefault("verification", {})
        club["verification"]["public_data"]={
            "matched": True,
            "checked_at": date.today().isoformat(),
            "status": status or "등록정보 확인",
            "address": address,
        }
        # 기존 주소가 없을 때만 공공데이터 주소 보강
        if address and not club.get("address"):
            club["address"]=address
        matched += 1
    return clubs, matched

def dual_verification_summary(club):
    """VWorld + 공공데이터의 기본 검증상태."""
    vw=bool(club.get("vworld_x") is not None or club.get("pool_source","").startswith("VWorld"))
    pub=((club.get("verification") or {}).get("public_data") or {}).get("matched") is True
    if vw and pub: return "공공데이터 2중 확인"
    if vw: return "VWorld 확인"
    if pub: return "공공데이터 확인"
    return "기본정보 확인 필요"
