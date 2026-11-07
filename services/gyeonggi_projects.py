"""경기데이터드림 정비사업 수집·정규화(읽기 전용, DB 쓰기 없음).

- 두 API(일반 정비사업 GenrlimprvBizpropls, 소규모 주택정비 TBGRISSMSCLBSNSM)를 페이지 단위로 모두 받는다.
- 원본 행은 그대로 보존(raw)하고, 서울 사업 화면과 같은 이름의 공통 필드를 따로 만든다.
- 응답 필드명은 아직 사람이 확인하지 않았으므로 공통 필드 매핑은 '응답에서 탐지(UNVERIFIED)'로만 표시한다.
  탐지되지 않은 값은 비워 두고 추측해서 채우지 않는다.
- 좌표는 원본 좌표가 있어도 쓰지 않고, 검증된 주소 지오코딩(verify_coordinate)을 통과한 경우에만 붙인다.
- 투자금·수익률 같은 원본에 없는 값은 만들지 않는다.
- 인증키는 서버 환경변수 GYEONGGI_API_KEY로만 읽고, 오류 문구·로그·응답에 담지 않는다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
import threading
import time
import unicodedata

BASE_URL = "https://openapi.gg.go.kr/"
KEY_NAME = "GYEONGGI_API_KEY"
PAGE_SIZE = 1000  # 경기데이터드림 1회 최대 요청 건수
MAX_PAGES = 50
TIMEOUT = 20
RETRIES = 3
CACHE_TTL = 6 * 3600
STALE_DAYS = 365

DATASETS = {
    "general": {
        "service": "GenrlimprvBizpropls",
        "title": "경기도 일반 정비사업 추진현황",
        "provider": "경기도",
        "url": "https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=S62GFEEN7JMLMA0PH6CF19108891&infSeq=1",
        "data_go_kr": "https://www.data.go.kr/data/15119846/fileData.do",
        "default_program": None,
    },
    "small": {
        "service": "TBGRISSMSCLBSNSM",
        "title": "경기도 소규모 주택정비사업 정보(경기부동산포털)",
        "provider": "경기도",
        "url": "https://data.gg.go.kr/portal/data/service/selectServicePage.do?infId=13H5REOHIUBGL1CYYHSG35587037&infSeq=1",
        "data_go_kr": "https://www.data.go.kr/data/15130792/fileData.do",
        "default_program": "소규모주택정비",
    },
}

# 경기도 31개 시·군(인천 제외).
GYEONGGI_SIGUN = [
    "수원시", "성남시", "의정부시", "안양시", "부천시", "광명시", "평택시", "동두천시", "안산시", "고양시",
    "과천시", "구리시", "남양주시", "오산시", "시흥시", "군포시", "의왕시", "하남시", "용인시", "파주시",
    "이천시", "안성시", "김포시", "화성시", "광주시", "양주시", "포천시", "여주시", "연천군", "가평군", "양평군",
]

# 경기데이터드림 공통 결과 코드. 재시도할 것(서버 측 일시 오류)과 하지 않을 것(키·요청 문제)을 나눈다.
NO_DATA = "INFO-200"
OK = "INFO-000"
RETRYABLE_CODES = {"ERROR-500", "ERROR-600", "ERROR-601"}


class GyeonggiError(Exception):
    """사용자에게 보여도 되는 오류. 키 값은 절대 담지 않는다."""

    def __init__(self, code, message, retryable=False):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.retryable = code, message, retryable


def _now():
    return datetime.now(timezone.utc)


def _mask(text, key):
    text = str(text)
    if key:
        text = text.replace(key, "***")
    return re.sub(r"(?i)(KEY=)[^&\s'\"]+", r"\1***", text)


def _parse_page(service, payload):
    """한 페이지 응답 → (rows, total, code, message)."""
    if not isinstance(payload, dict):
        raise GyeonggiError("PARSE_ERROR", "응답이 JSON 객체가 아니에요")
    if service not in payload:
        result = payload.get("RESULT") or {}
        code, message = result.get("CODE") or "UNKNOWN", result.get("MESSAGE") or ""
        if code == NO_DATA:
            return [], 0, code, message
        raise GyeonggiError(code, message or "알 수 없는 응답", retryable=code in RETRYABLE_CODES)
    blocks = payload[service]
    head = (blocks[0] or {}).get("head") or [] if blocks else []
    total, code, message = None, OK, ""
    for item in head:
        if "list_total_count" in item:
            total = int(item["list_total_count"])
        if "RESULT" in item:
            code, message = item["RESULT"].get("CODE") or OK, item["RESULT"].get("MESSAGE") or ""
    if code != OK:
        raise GyeonggiError(code, message, retryable=code in RETRYABLE_CODES)
    rows = next((b.get("row") for b in blocks[1:] if isinstance(b, dict) and "row" in b), []) or []
    return rows, total, code, message


def fetch_dataset(dataset, http_get, get_secret, *, page_size=PAGE_SIZE, retries=RETRIES,
                  sleep=time.sleep, max_pages=MAX_PAGES):
    """데이터셋 전체를 페이지 단위로 받는다. http_get(url, params, timeout) → 응답 객체(status_code, json())."""
    spec = DATASETS[dataset]
    key = str(get_secret(KEY_NAME) or "").strip()
    if not key:
        raise GyeonggiError("NOT_CONFIGURED", f"서버 환경변수 {KEY_NAME}가 설정되지 않았어요")
    rows, total, code, pages = [], None, OK, 0
    for page in range(1, max_pages + 1):
        params = {"KEY": key, "Type": "json", "pIndex": page, "pSize": page_size}
        page_rows = None
        for attempt in range(retries + 1):
            try:
                response = http_get(BASE_URL + spec["service"], params=params, timeout=TIMEOUT)
                status = getattr(response, "status_code", 200)
                if status == 429 or status >= 500:
                    raise GyeonggiError(f"HTTP_{status}", "경기데이터드림 응답 오류", retryable=True)
                if status >= 400:
                    raise GyeonggiError(f"HTTP_{status}", "경기데이터드림 요청 거부")
                page_rows, page_total, code, _ = _parse_page(spec["service"], response.json())
                break
            except GyeonggiError as exc:
                if not exc.retryable or attempt == retries:
                    raise GyeonggiError(exc.code, _mask(exc.message, key), exc.retryable) from None
            except Exception as exc:  # 망 오류·타임아웃·JSON 오류
                name = type(exc).__name__
                transient = isinstance(exc, (OSError, TimeoutError)) or "Timeout" in name or "Connection" in name
                if not transient or attempt == retries:
                    raise GyeonggiError("TIMEOUT" if "Timeout" in name else "REQUEST_FAILED",
                                        f"{name}: {_mask(exc, key)[:120]}", retryable=transient) from None
            sleep(min(2 ** attempt, 8))
        pages += 1
        if total is None:
            total = page_total
        rows.extend(page_rows)
        if not page_rows or (total is not None and len(rows) >= total) or len(page_rows) < page_size:
            break
    complete = total is not None and len(rows) == total
    return {"dataset": dataset, "service": spec["service"], "rows": rows, "total": total,
            "received": len(rows), "pages": pages, "result_code": code,
            "complete": complete if total else code == NO_DATA or total == 0,
            "fetched_at": _now().isoformat()}


# ---------- 필드 매핑(실제 응답으로 필드명 확인됨, 값 형식은 미검증) ----------

def _norm(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text or ""))).strip()


# 운영 서버에서 실제 응답으로 확인한 필드명(2026-11 검증). 값의 단위·날짜 형식·최신성은 검증되지 않았다.
FIELDS = {
    "general": {
        "sigun": "SIGUN_NM", "name": "IMPRV_ZONE_NM", "address": "LOCPLC_ADDR", "business_type": "BIZ_TYPE_NM",
        "stage": "BIZ_STEP_NM", "area": "ZONE_AR", "existing_households": "EXISTNG_HOUSNG_HSHLD_CNT",
        "planned_households": "BIZ_IMPLMTN_HSHLD_CNT_TOTSUM", "implementer": "BIZ_IMPLMNTR_NM",
    },
    "small": {
        "sigun": "SIGNGU_NM", "name": "BIZ_NM", "address": "DETAIL_ADDR", "stage": "PROPLSN_STEP",
        "area": "BIZ_IMPLMTN_AR", "biz_div": "BIZ_DIV",
    },
}
# 단계별 인가·고시일(원본 필드명 → 표시 이름). 값은 원문 그대로 보여 준다.
DATE_FIELDS = {
    "general": [("ASSOCTN_FOUND_CONFMTN_DE", "조합설립인가일"), ("BIZ_IMPLMTN_CONFMTN_DE", "사업시행인가일"),
                ("MANAGE_DISPOSIT_CONFMTN_DE", "관리처분인가일")],
    "small": [("ASSOCTN_FOUND_CONFMTN_LPERD", "조합설립인가"), ("BIZ_IMPLMTN_PLAN_CONFMTN_LPERD", "사업시행계획인가"),
              ("STRCONTR_LPERD", "착공"), ("COMPLTN_LPERD", "준공")],
}
LABELS = {"area": "사업(구역) 면적", "existing_households": "기존 세대수", "planned_households": "계획 세대수",
          "implementer": "사업 시행자", "biz_div": "사업구분 코드(BIZ_DIV)"}

# 표준 단계(서울 stage_guide 코드와 같은 이름을 쓰되, 원본 단계명은 별도로 보관한다).
STD_STAGES = [
    ("CANDIDATE", "정비예정구역"), ("DESIGNATED", "정비구역 지정"), ("COMMITTEE", "추진위원회·주민합의체"),
    ("ASSOCIATION_APPROVED", "조합설립인가"), ("PLAN_DELIBERATION", "건축심의"), ("IMPLEMENTATION_APPROVED", "사업시행(계획)인가"),
    ("MANAGEMENT_DISPOSITION", "관리처분인가"), ("CONSTRUCTION", "착공"), ("COMPLETED", "준공"),
    ("TRANSFER_NOTICE", "이전고시"), ("CLOSED", "청산"),
]
STD_LABEL = dict(STD_STAGES)
STAGE_MAP = {
    "general": {"예정구역": "CANDIDATE", "정비구역": "DESIGNATED", "추진위원회": "COMMITTEE", "조합설립": "ASSOCIATION_APPROVED",
                "사업시행": "IMPLEMENTATION_APPROVED", "관리처분": "MANAGEMENT_DISPOSITION", "착공": "CONSTRUCTION",
                "준공": "COMPLETED", "청산": "CLOSED"},
    "small": {"주민합의체 구성": "COMMITTEE", "조합설립인가": "ASSOCIATION_APPROVED", "건축심의": "PLAN_DELIBERATION",
              "사업시행계획인가": "IMPLEMENTATION_APPROVED", "사업시행인가": "IMPLEMENTATION_APPROVED", "착공": "CONSTRUCTION",
              "준공": "COMPLETED", "이전고시": "TRANSFER_NOTICE"},
}
FINISHED = {"COMPLETED", "TRANSFER_NOTICE", "CLOSED"}


def standard_stage(dataset, raw):
    """원본 단계명 → 표준 단계 코드. 표에 없는 값·빈 값은 UNKNOWN(추정하지 않음)."""
    key = re.sub(r"\s+", " ", _norm(raw))
    code = STAGE_MAP[dataset].get(key) or STAGE_MAP[dataset].get(key.replace(" ", ""))
    return code or "UNKNOWN"


def detect_mapping(rows, dataset=None):
    """확인된 필드명이 실제 응답에 있는지 본다. 없는 필드는 missing_fields로 보고하고 다른 필드로 대신하지 않는다."""
    fields = []
    for row in rows:
        for k in row:
            if k not in fields:
                fields.append(k)
    spec = FIELDS.get(dataset or "", {})
    dates = [f for f, _ in DATE_FIELDS.get(dataset or "", [])]
    mapping = {k: v for k, v in spec.items() if v in fields}
    expected = list(spec.values()) + dates
    missing = [f for f in expected if f not in fields]
    return {"fields": fields, "mapping": mapping, "basis": {k: "VERIFIED_NAME" for k in mapping},
            "date_fields": [f for f in dates if f in fields], "missing_fields": missing,
            "unmapped": [f for f in fields if f not in expected],
            "status": "VERIFIED_NAMES" if not missing else "FIELDS_MISSING"}


def split_region(value, address=None):
    """'수원시 장안구'·'광명시' 같은 시군구 값(없으면 주소) → (시군, 시군구). 31개 시군으로 확인되지 않으면 시군 None."""
    texts = [_norm(value), _norm(address).replace("경기도", "").strip() if address else ""]
    sigun = next((s for t in texts for s in GYEONGGI_SIGUN if t == s or t.startswith(s + " ") or t.startswith(s)), None)
    if not sigun:
        return None, None
    gu = None
    for t in texts:
        if t.startswith(sigun):
            m = re.match(r"\s*([가-힣]+구)(?:\s|$)", t[len(sigun):])
            if m:
                gu = m.group(1)
                break
    return sigun, f"{sigun} {gu}" if gu else sigun


def _dong(address):
    for t in _norm(address).split():
        if re.fullmatch(r"[가-힣0-9]+(동|읍|면|리|가)", t) and not t.endswith("시"):
            return t
    return None


def _parse_date(value):
    m = re.match(r"^((?:19|20)\d{2})[-./]?(\d{2})(?:[-./]?(\d{2}))?$", _norm(value))
    if not m:
        return None
    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1), tzinfo=timezone.utc)


def _name_key(text):
    text = _norm(text)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"(주택|재개발|재건축|정비|사업|구역|지구|일대|조합|가로|소규모|아파트|\s)", "", text)
    return text


def normalize(dataset, fetched, now=None):
    """원본 행 → 공통 필드 + 원본 보존. 원본에 없는 값은 만들지 않고, 값 형식이 미검증인 항목은 원문 문자열로 둔다."""
    spec, rows = DATASETS[dataset], fetched["rows"]
    detected = detect_mapping(rows, dataset)
    f = FIELDS[dataset]
    out = []
    for row in rows:
        def get(key):
            name = f.get(key)
            value = row.get(name) if name else None
            return _norm(value) if value not in (None, "") and _norm(value) else None
        address = get("address")
        sigun, district = split_region(get("sigun"), address)
        stage_raw = get("stage")
        std = standard_stage(dataset, stage_raw)
        identity = "|".join([dataset, get("sigun") or "", get("name") or "", address or ""])
        values = [{"key": k, "label": LABELS[k], "value": get(k), "source_field": f[k]}
                  for k in ("area", "existing_households", "planned_households", "implementer", "biz_div") if k in f]
        dates = [{"label": label, "value": _norm(row.get(field)) or None, "source_field": field}
                 for field, label in DATE_FIELDS[dataset]]
        record = {
            "project_id": "gg-" + dataset + "-" + hashlib.sha1(identity.encode()).hexdigest()[:16],
            "name": get("name"),
            # 일반 정비사업은 원본 BIZ_TYPE_NM(재건축·재개발·주거환경개선)을 그대로 쓴다.
            # 소규모는 BIZ_DIV 코드의 공식 의미가 확인되지 않아 세부 유형으로 바꾸지 않는다.
            "type_label": get("business_type") if dataset == "general" else "소규모주택정비",
            "program_label": spec["default_program"],
            "biz_div": get("biz_div") if dataset == "small" else None,
            "sido": "경기도",
            "sigun": sigun,
            "sigungu_raw": get("sigun"),
            "district": district,
            "dong": _dong(address) if address else None,
            "address": address,
            "stage_raw": stage_raw,
            "stage_std": std,
            "stage_std_label": STD_LABEL.get(std),
            "completed": std in FINISHED,
            "values": values,
            "stage_dates": dates,
            "latitude": None, "longitude": None, "mappable": False, "has_location": False, "coordinate_verified": False,
            "location_notice": "검증된 주소 좌표가 아직 없어 지도에 표시하지 않아요." if address else "주소가 없어 지도에 표시할 수 없어요.",
            "official_source": {"name": spec["title"], "provider": spec["provider"], "url": spec["url"],
                                "data_go_kr": spec["data_go_kr"], "service": spec["service"]},
            "collected_at": fetched["fetched_at"],
            "source_base_date": None,
            "needs_refresh": True,
            "freshness_note": "원본에 데이터 기준일 필드가 없어 수집일만 확인됐어요. 최신 단계는 시군 공고로 확인해 주세요.",
            "boundary": None,
            "mapping_status": detected["status"],
            "source_dataset": dataset,
            "raw": dict(row),
        }
        record["missing"] = [k for k in ("name", "sigun", "address") if not record[k]] + \
            ([] if record["type_label"] else ["type_label"]) + ([] if stage_raw else ["stage"])
        record["sigun_valid"] = sigun in GYEONGGI_SIGUN
        out.append(record)
    return out, detected


STAGE_STEPS = [label for code, label in STD_STAGES if code not in ("TRANSFER_NOTICE", "CLOSED", "PLAN_DELIBERATION")]


def to_project(r):
    """경기 레코드 → 서울 사업 화면(DevelopmentProject)과 같은 모양. 모르는 값은 null·'확인 필요'로 둔다."""
    std_label = r["stage_std_label"]
    index = STAGE_STEPS.index(std_label) if std_label in STAGE_STEPS else None
    stage_label = r["stage_raw"] or "단계 미입력"
    return {
        "project_id": r["project_id"], "name": r["name"] or "(사업명 없음)", "official_id": None,
        "official_authority": r["sigun"], "type_label": r["type_label"] or "유형 미입력",
        "program": {"code": "SMALL_SCALE", "label": r["program_label"]} if r["program_label"] else None,
        "program_label": r["program_label"], "stage_verified_level": "OFFICIAL_LIST_MAPPED",
        "stage_timeline": {"steps": STAGE_STEPS, "current_index": index, "current_label": std_label, "total": len(STAGE_STEPS),
                           "note": None if index is not None else f"원본 단계 '{stage_label}'를 표준 단계에 대응하지 않았어요."},
        "stage_description": None,
        "location_accuracy": {"code": "NO_VERIFIED_COORDINATE", "label": "위치 확인 필요",
                              "note": "경기도 원본에는 검증된 좌표가 없어 주소 기준으로만 표시해요."},
        "distance_label": None, "district": r["district"], "dong": r["dong"], "address": r["address"],
        "stage": {"label": stage_label, "official_text": r["stage_raw"]},
        "stage_basis": f"경기데이터드림 원본 단계: {stage_label}" + (f" → 표준 단계: {std_label}" if std_label else " (표준 단계 미대응)"),
        "status_label": "완료·청산" if r["completed"] else "추진 중",
        "trust": {"code": "GYEONGGI_OPEN_DATA", "label": "경기도 공공데이터", "tone": "info",
                  "note": "경기데이터드림 목록 자료예요. 사업별 공식 고시로 확인된 단계가 아니에요."},
        "official_source": {"name": r["official_source"]["name"], "url": r["official_source"]["url"]},
        "last_checked": r["collected_at"], "data_dates": {"stage_collected": (r["collected_at"] or "")[:10] or None, "db_reflected": None},
        "stage_guide": None,
        "stage_display": {"raw": r["stage_raw"], "label": std_label, "family": "GYEONGGI_LIST",
                          "legal_stage_confirmed": False, "needs_official_check": True},
        "naver_real_estate": None,
        "spatial": {"code": "UNKNOWN", "label": "구역 경계 없음", "confirmed_boundary": False},
        "distance_m": None, "latitude": r["latitude"], "longitude": r["longitude"], "mappable": r["mappable"],
        "has_location": r["has_location"], "location_notice": r["location_notice"],
        "sido": "경기도", "completed": r["completed"],
        "gyeonggi": {"dataset": r["source_dataset"], "dataset_title": r["official_source"]["name"], "service": r["official_source"]["service"],
                     "stage_raw": r["stage_raw"], "stage_std": r["stage_std"], "stage_std_label": std_label,
                     "sigungu_raw": r["sigungu_raw"], "values": r["values"], "stage_dates": r["stage_dates"],
                     "biz_div": r["biz_div"], "missing": r["missing"], "duplicate_of": r.get("duplicate_of", []),
                     "duplicate_basis": r.get("duplicate_basis", []), "collected_at": r["collected_at"],
                     "freshness_note": r["freshness_note"], "format_note": "면적·세대수·날짜는 원본 값을 그대로 보여 줘요(단위·형식 미검증)."},
    }


def detail_for(project, connections):
    """상세 패널(ZoneDetail) 모양. 경기 원본에 없는 사업정보·이력·경계는 비워 두고 '확인 필요'로 남긴다."""
    g = project["gyeonggi"]
    return {
        "project": dict(project, facts={"area_m2": None, "planned_units": None, "planned_floor": None, "planned_far": None,
                                        "selected_date": None, "notice_date": None, "source_date": None,
                                        "official_authority": project["official_authority"], "external_id": None},
                        boundary={"verified": False, "source": None, "verified_at": None}),
        "process_timeline": {
            "verified": False,
            "flow": {"code": "RECONSTRUCTION" if project["type_label"] == "재건축" else "REDEVELOPMENT" if project["type_label"] == "재개발" else "GENERIC",
                     "label": project["type_label"], "note": "일반적인 절차 안내이며 이 사업의 공식 일정이 아니에요.", "basis": "GUIDE_RULE"},
            "guide_note": "경기도 목록 자료의 단계만 확인됐어요.", "source": None, "program_label": project["program_label"],
            "current_official": {"name": g["stage_raw"], "official_name": g["stage_raw"], "index": None, "recognised": g["stage_std"] != "UNKNOWN",
                                 "in_standard_steps": False},
            "steps": [], "pre_steps": [], "extra_steps": [], "closing_steps": [], "progress": None,
            "closing_note": "준공·청산 등 완료 단계 사업이에요." if project["completed"] else None,
            "unverified_note": "경기데이터드림 목록의 단계명이에요. 사업별 고시로 확인된 일정은 아니에요.",
        },
        "sources": {"state": "ok", "items": []},
        "recent_updates": {"state": "unavailable", "items": []},
        "provenance": {"last_verified_at": None, "last_collected_at": g["collected_at"], "source_date": None,
                       "notice_date": None, "generated_at": _now().isoformat()},
        "connections": connections,
    }


def mark_duplicates(records):
    """같은 시군에서 정규화한 사업명 또는 주소가 같은 사업을 중복 후보로 표시한다(삭제하지 않음)."""
    groups = {}
    for r in records:
        if r["sigun"] and r["name"]:
            groups.setdefault(("name", r["sigun"], _name_key(r["name"])), []).append(r)
        if r["sigun"] and r["address"]:
            groups.setdefault(("addr", r["sigun"], re.sub(r"\s", "", r["address"])), []).append(r)
    for r in records:
        r["duplicate_of"] = []
    count = 0
    for (kind, _, key), members in groups.items():
        if not key or len(members) < 2:
            continue
        count += 1
        for r in members:
            others = [o["project_id"] for o in members if o is not r]
            r["duplicate_of"] = sorted(set(r["duplicate_of"]) | set(others))
            r.setdefault("duplicate_basis", [])
            if kind not in r["duplicate_basis"]:
                r["duplicate_basis"].append(kind)
    return count


def quality_report(records, meta):
    fields = ("name", "sigun", "type_label", "address", "stage")
    stage_counts = {}
    for r in records:
        key = (r["source_dataset"], r["stage_raw"] or "(미입력)", r["stage_std"])
        stage_counts[" / ".join(key)] = stage_counts.get(" / ".join(key), 0) + 1
    missing = {f: sum(1 for r in records if f in r["missing"]) for f in fields}
    by_sigun = {s: 0 for s in GYEONGGI_SIGUN}
    unknown = {}
    for r in records:
        if r["sigun_valid"]:
            by_sigun[r["sigun"]] += 1
        else:
            unknown[r["sigun"] or "(없음)"] = unknown.get(r["sigun"] or "(없음)", 0) + 1
    return {
        "total": len(records),
        "datasets": meta,
        "missing": missing,
        "duplicates": sum(1 for r in records if r["duplicate_of"]),
        "by_sigun": by_sigun,
        "sigun_without_projects": [s for s, n in by_sigun.items() if n == 0],
        "unknown_sigun": unknown,
        "needs_refresh": sum(1 for r in records if r["needs_refresh"]),
        "completed": sum(1 for r in records if r["completed"]),
        "stage_mapping": stage_counts,
        "unknown_stage": sum(1 for r in records if r["stage_std"] == "UNKNOWN"),
        "coordinate_verified": sum(1 for r in records if r["coordinate_verified"]),
    }


# ---------- 캐시(메모리, single-flight, 실패 시 이전 값 유지) ----------

_cache: dict = {}
_locks = {k: threading.Lock() for k in DATASETS}


def load(dataset, http_get, get_secret, *, ttl=CACHE_TTL, clock=time.monotonic, **kw):
    """캐시가 유효하면 그대로, 아니면 다시 받는다. 다시 받다 실패하면 이전 값을 stale로 돌려준다."""
    hit = _cache.get(dataset)
    if hit and clock() - hit["at"] < ttl:
        return dict(hit["value"], cache="HIT")
    with _locks[dataset]:
        hit = _cache.get(dataset)
        if hit and clock() - hit["at"] < ttl:
            return dict(hit["value"], cache="HIT")
        try:
            value = fetch_dataset(dataset, http_get, get_secret, **kw)
        except GyeonggiError as exc:
            if hit:
                return dict(hit["value"], cache="STALE", error={"code": exc.code, "message": exc.message})
            raise
        _cache[dataset] = {"at": clock(), "value": value}
        return dict(value, cache="MISS")


def collect(http_get, get_secret, datasets=None, **kw):
    """두 데이터셋을 받아 정규화·중복·품질까지 만든다. 한쪽이 실패해도 다른 쪽은 돌려준다."""
    records, meta = [], {}
    for name in datasets or list(DATASETS):
        try:
            fetched = load(name, http_get, get_secret, **kw)
        except GyeonggiError as exc:
            meta[name] = {"status": "ERROR", "code": exc.code, "message": exc.message,
                          "service": DATASETS[name]["service"]}
            continue
        rows, detected = normalize(name, fetched)
        records.extend(rows)
        meta[name] = {"status": "OK" if fetched["complete"] else "INCOMPLETE", "service": fetched["service"],
                      "total": fetched["total"], "received": fetched["received"], "pages": fetched["pages"],
                      "result_code": fetched["result_code"], "fetched_at": fetched["fetched_at"],
                      "cache": fetched.get("cache"), "error": fetched.get("error"),
                      "mapping": {k: detected[k] for k in ("mapping", "status", "date_fields", "missing_fields", "unmapped", "fields")}}
    mark_duplicates(records)
    return records, meta


# ---------- 경기 주소 좌표 검증(서울 검증기와 분리) ----------

GYEONGGI_BOUNDS = {"longitude": (126.25, 127.90), "latitude": (36.85, 38.35)}
ACCEPTED_ACCURACY = ("PARCEL", "BUILDING", "ROAD_ADDRESS")


PARSER_VERSION = 2  # 지오코딩 질의 주소 규칙 버전. 실패 캐시는 버전이 다르면 다시 시도한다.
MAX_DIAGNOSTICS = 10  # 캐시에 남기는 후보별 진단 수(검증은 모든 후보에 한다)


def geocode_target(address):
    """원본 주소(바꾸지 않음) → 지오코딩용 질의 주소와 검증용 구성요소.

    '번지'·'일원'·'일대'·'번지일원'·'외 N필지'와 괄호 속 부가 설명을 떼고, 시군·구·읍면동·리·지번을 뽑는다.
    시군·읍면동·지번 중 하나라도 없거나 지번이 여러 개면 질의를 만들지 않는다(추측해서 보완하지 않음).
    """
    text = unicodedata.normalize("NFKC", str(address or ""))
    text = re.sub(r"\([^)]*\)", " ", text)          # 괄호 속 부가 설명
    text = re.sub(r"\(.*$", " ", text)              # 닫히지 않은 괄호 뒤
    text = re.sub(r"외\s*\d+\s*(?:개\s*)?필지", " ", text)
    text = re.sub(r"번지|일원|일대", " ", text)
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"(?<=\d),\s*", " , ", text)      # 지번 나열(178-57, 178-58)을 따로 센다
    tokens = [t for t in text.split() if t not in ("경기도", "경기")]
    out = {"query": None, "si": None, "gu": None, "dong": None, "ri": None, "lot": None, "mountain": False, "reason": None}
    si_i = next((i for i, t in enumerate(tokens) if t in GYEONGGI_SIGUN), None)
    if si_i is None:
        return dict(out, reason="NO_SIGUN")
    out["si"] = tokens[si_i]
    rest = tokens[si_i + 1:]
    if rest and re.fullmatch(r"[가-힣]+구", rest[0]):
        out["gu"], rest = rest[0], rest[1:]
    dong_i = next((i for i, t in enumerate(rest) if re.fullmatch(r"[가-힣0-9]+(동|읍|면|가)", t)), None)
    if dong_i is None:
        return dict(out, reason="NO_DONG")
    out["dong"] = rest[dong_i]
    rest = rest[dong_i + 1:]
    if rest and re.fullmatch(r"[가-힣0-9]+리", rest[0]):
        out["ri"], rest = rest[0], rest[1:]
    lots, mountain, i = [], False, 0
    while i < len(rest):
        t = rest[i]
        if t == "산" and i + 1 < len(rest) and re.fullmatch(r"\d+(-\d+)?", rest[i + 1]):
            lots.append(rest[i + 1]); mountain = True; i += 2; continue
        m = re.fullmatch(r"(산)?(\d+(?:-\d+)?)", t)
        if m:
            lots.append(m.group(2)); mountain = mountain or bool(m.group(1))
        i += 1
    if not lots:
        return dict(out, reason="NO_LOT")
    if len(set(lots)) > 1:
        return dict(out, reason="MULTIPLE_LOTS")
    lot = lots[0]
    out.update(lot=lot, mountain=mountain)
    out["query"] = " ".join(x for x in ["경기도", out["si"], out["gu"], out["dong"], out["ri"], ("산 " if mountain else "") + lot] if x)
    return out


def wanted(address):
    """이전 이름 호환: 검증용 구성요소."""
    t = geocode_target(address)
    return {"si": t["si"], "gu": t["gu"], "dong": t["dong"], "lot": t["lot"]}


def _lot_core(value):
    return re.sub(r"\s|산", "", str(value or ""))


def verify_coordinate(address, response):
    """provider 응답에서 '경기도·시군(구)·읍면동(리)·지번이 모두 일치하는 후보가 정확히 하나'일 때만 좌표를 채택한다.

    실패하면 후보별로 어떤 조건이 틀렸는지(diagnostics)를 남긴다. 주소·좌표 외 민감정보는 담지 않는다.
    """
    target = geocode_target(address)
    base = {"coordinate_verified": False, "parser_version": PARSER_VERSION, "query": target["query"],
            "parsed": {k: target[k] for k in ("si", "gu", "dong", "ri", "lot", "mountain")}}
    if target["reason"]:
        return dict(base, reason="ADDRESS_HAS_NO_LOT_OR_SIGUN", parse_reason=target["reason"])
    if not response or response.get("result_status") != "MATCHED":
        return dict(base, reason="NO_MATCH", provider_status=(response or {}).get("result_status"))
    # 모든 후보를 검증한다(앞쪽 일부만 보면 뒤에 숨은 두 번째 일치 후보를 놓쳐 잘못 확정할 수 있다).
    # 저장하는 진단만 앞 MAX_DIAGNOSTICS건으로 줄인다.
    candidates = response.get("candidates") or []
    passing, diagnostics = [], []
    for c in candidates:
        lon, lat = c.get("longitude"), c.get("latitude")
        el = c.get("address_elements") or {}
        if el:
            sigungu = (el.get("SIGUGUN") or "").split()
            jibun = _norm(c.get("jibun_address") or c.get("matched_address"))
            checks = {
                "sido": el.get("SIDO", "") == "경기도",
                "sigun": sigungu[:1] == [target["si"]],
                "gu": not target["gu"] or target["gu"] in sigungu[1:],
                "dong": el.get("DONGMYUN", "") == target["dong"],
                "ri": not target["ri"] or el.get("RI", "") == target["ri"],
                "lot": _lot_core(el.get("LAND_NUMBER")) == target["lot"],
                "mountain": target["mountain"] == bool(re.search(r"(^|\s)산\s?\d", jibun) or "산" in str(el.get("LAND_NUMBER") or "")),
            }
        else:
            text = _norm(c.get("matched_address"))
            words = text.split()
            checks = {
                "sido": words[:1] in (["경기도"], ["경기"]),
                "sigun": target["si"] in words,
                "gu": not target["gu"] or target["gu"] in words,
                "dong": target["dong"] in words,
                "ri": not target["ri"] or target["ri"] in words,
                "lot": bool(words) and _lot_core(words[-1]) == target["lot"],
                "mountain": target["mountain"] == ("산" in words or bool(words and words[-1].startswith("산"))),
            }
        checks["accuracy"] = c.get("accuracy") in ACCEPTED_ACCURACY
        checks["bounds"] = isinstance(lon, (int, float)) and isinstance(lat, (int, float)) and \
            GYEONGGI_BOUNDS["longitude"][0] <= lon <= GYEONGGI_BOUNDS["longitude"][1] and \
            GYEONGGI_BOUNDS["latitude"][0] <= lat <= GYEONGGI_BOUNDS["latitude"][1]
        failed = sorted(k for k, ok in checks.items() if not ok)
        if len(diagnostics) < MAX_DIAGNOSTICS:
            diagnostics.append({"matched_address": c.get("matched_address"), "accuracy": c.get("accuracy"), "failed_checks": failed})
        if not failed:
            passing.append(c)
    if len(passing) != 1:
        return dict(base, reason="NO_CANDIDATE_PASSED" if not passing else "MULTIPLE_CANDIDATES",
                    candidate_count=len(candidates), passing_count=len(passing), diagnostics=diagnostics,
                    diagnostics_truncated=len(candidates) > MAX_DIAGNOSTICS,
                    failed_checks=sorted({f for d in diagnostics for f in d["failed_checks"]}))
    c = passing[0]
    return dict(base, coordinate_verified=True, latitude=c["latitude"], longitude=c["longitude"],
                geocode_source=response.get("provider"), matched_address=c.get("matched_address"), reason=None,
                candidate_count=len(candidates))


def plan_geocode(addresses, cap):
    """실제 실행과 dry run이 같은 순서·같은 규칙을 쓰도록 주소별 처리를 정한다.

    CALL: provider를 부른다(최대 cap건). SKIP_UNPARSEABLE: 질의를 만들 수 없어 부르지 않고 사유만 기록한다.
    DEFER: 이번 실행에서 처리하지 않는다(cap에 닿은 뒤의 주소, 파싱 실패 주소 포함).
    """
    plan, calls = [], 0
    for address in addresses:
        target = geocode_target(address)
        if calls >= cap:
            plan.append((address, "DEFER", target))
        elif target["reason"]:
            plan.append((address, "SKIP_UNPARSEABLE", target))
        else:
            plan.append((address, "CALL", target))
            calls += 1
    return plan


def needs_geocode(entry, retry_failed=False):
    """캐시 항목을 다시 지오코딩할지. 성공은 유지, 실패는 규칙 버전이 바뀌었거나 명시적으로 요청했을 때만 다시 한다."""
    if not entry:
        return True
    if entry.get("coordinate_verified"):
        return False
    return retry_failed or entry.get("parser_version") != PARSER_VERSION


def attach_coordinates(records, lookup):
    """lookup(address) → verify_coordinate 결과(캐시된 것). 검증된 것만 좌표를 붙인다."""
    for r in records:
        if not r["address"]:
            continue
        result = lookup(r["address"]) or {}
        if result.get("coordinate_verified"):
            r.update(latitude=result["latitude"], longitude=result["longitude"], mappable=True,
                     has_location=True, coordinate_verified=True, location_notice=None)
    return records


def region_summary(records):
    """31개 시군별 사업 수·지도 표시 가능 수와 검증된 좌표의 범위(지도 중심·확대용)."""
    out = []
    for sigun in GYEONGGI_SIGUN:
        rs = [r for r in records if r["sigun"] == sigun]
        pts = [(r["latitude"], r["longitude"]) for r in rs if r["coordinate_verified"]]
        bbox = None
        if pts:
            lats, lons = [p[0] for p in pts], [p[1] for p in pts]
            bbox = {"south": min(lats), "north": max(lats), "west": min(lons), "east": max(lons)}
        out.append({"sigun": sigun, "projects": len(rs), "mappable": len(pts), "bbox": bbox,
                    "districts": sorted({r["district"] for r in rs if r["district"] and r["district"] != sigun})})
    return out


def public_record(r, include_raw=False):
    return r if include_raw else {k: v for k, v in r.items() if k != "raw"}
