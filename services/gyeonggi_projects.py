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


# ---------- 공통 필드 매핑(응답에서 탐지, 미검증) ----------

def _norm(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(text or ""))).strip()


# (공통 필드, 정확 일치 후보, 정규식 후보). 값이 있는 첫 필드를 쓴다. 근거는 mapping에 남긴다.
FIELD_RULES = [
    ("sigun", ["SIGUN_NM", "시군명"], []),
    ("sigun_code", ["SIGUN_CD"], []),
    ("name", ["정비구역명", "사업장명", "구역명"], [r"(ZONE|DSTRCT|BIZPLC|BIZ|PRJCT|BSNS)_?NM$"]),
    ("business_type", ["정비유형", "사업유형", "사업구분"], [r"(IMPRV|BIZ|BSNS|PRJCT)_?(TYPE|DIV|KIND|SE)(_NM)?$"]),
    ("stage", ["현추진상황", "추진단계", "진행단계", "사업단계"], [r"(PROGRS|PRGS|STEP|STAGE|STTUS)(_NM|_DIV|_SE)?$"]),
    ("address", ["위치", "소재지", "주소"], [r"^REFINE_LOTNO_ADDR$", r"(LOTNO|LOCPLC|LC|LOC)_?ADDR$", r"ADDR$"]),
    ("road_address", [], [r"^REFINE_ROADNM_ADDR$", r"ROADNM_?ADDR$"]),
    ("area_m2", ["구역면적", "면적"], [r"(ZONE|DSTRCT|BIZ)?_?AR(EA)?$"]),
    ("base_date", ["기준일자", "데이터기준일자"], [r"(DATA_)?(STD|CRTR|BASE)_?(DE|DT|YMD)$"]),
]
EXCLUDE_FOR = {"name": {"SIGUN_NM"}}
DATE_VALUE = re.compile(r"^(19|20)\d{2}[-./]?\d{2}([-./]?\d{2})?$")
VERIFIED_MAPPING: dict = {}  # 실제 응답을 사람이 확인한 뒤 {데이터셋: {공통필드: 원본필드}}로 채운다.


def detect_mapping(rows, dataset=None):
    fields = []
    for row in rows:
        for k in row:
            if k not in fields:
                fields.append(k)
    verified = VERIFIED_MAPPING.get(dataset or "", {})
    mapping, basis = {}, {}
    for common, exact, patterns in FIELD_RULES:
        if common in verified and verified[common] in fields:
            mapping[common], basis[common] = verified[common], "VERIFIED"
            continue
        found = next((f for f in exact if f in fields), None)
        if not found:
            for pattern in patterns:
                found = next((f for f in fields if re.search(pattern, f, re.I)
                              and f not in EXCLUDE_FOR.get(common, set())
                              and f not in mapping.values()), None)
                if found:
                    break
        if found:
            mapping[common], basis[common] = found, "DETECTED"
    # 날짜처럼 보이는 값이 들어 있는 원본 필드(인가일 등). 해석하지 않고 원본 필드명 그대로 보여 준다.
    date_fields = [f for f in fields if f not in mapping.values()
                   and any(DATE_VALUE.match(_norm(r.get(f))) for r in rows if r.get(f))]
    status = "VERIFIED" if basis and all(v == "VERIFIED" for v in basis.values()) else "UNVERIFIED"
    return {"fields": fields, "mapping": mapping, "basis": basis, "date_fields": date_fields,
            "unmapped": [f for f in fields if f not in mapping.values() and f not in date_fields],
            "status": status}


def _sigungu(address, sigun):
    """주소에서 '수원시 팔달구'처럼 시·구를, 그리고 읍·면·동·리·가를 뽑는다. 못 찾으면 None."""
    text = _norm(address)
    tokens = text.replace("경기도", " ").split()
    gu = next((t for t in tokens if re.fullmatch(r"[가-힣]+구", t)), None)
    dong = next((t for t in tokens if re.fullmatch(r"[가-힣0-9]+(동|읍|면|리|가)", t)
                 and t != sigun and not t.endswith("시")), None)
    return (f"{sigun} {gu}" if sigun and gu else sigun), dong


def _to_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _name_key(text):
    text = _norm(text)
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"(주택|재개발|재건축|정비|사업|구역|지구|일대|조합|가로|소규모|아파트|\s)", "", text)
    return text


def _parse_date(value):
    m = re.match(r"^((?:19|20)\d{2})[-./]?(\d{2})(?:[-./]?(\d{2}))?$", _norm(value))
    if not m:
        return None
    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1), tzinfo=timezone.utc)


def normalize(dataset, fetched, now=None):
    """원본 행 → 서울 사업과 같은 이름의 공통 필드 + 원본 보존 + 결측·중복 표시."""
    spec, rows = DATASETS[dataset], fetched["rows"]
    detected = detect_mapping(rows, dataset)
    m = detected["mapping"]
    now = now or _now()
    out = []
    for row in rows:
        get = lambda k: _norm(row.get(m[k])) if k in m and row.get(m[k]) not in (None, "") else None
        sigun = get("sigun")
        address = get("address") or get("road_address")
        sigungu, dong = _sigungu(address, sigun) if address else (sigun, None)
        base = get("base_date")
        base_dt = _parse_date(base) if base else None
        identity = "|".join([dataset, sigun or "", get("name") or "", address or ""])
        record = {
            "project_id": "gg:" + dataset + ":" + hashlib.sha1(identity.encode()).hexdigest()[:16],
            "name": get("name"),
            "type_label": get("business_type"),  # 원본 표기 그대로(재개발·재건축·가로주택정비 등)
            "program_label": spec["default_program"],  # 정책·계획 유형. 일반 정비사업은 원본에 없으면 비운다.
            "sido": "경기도",
            "district": sigungu,
            "sigun": sigun,
            "dong": dong,
            "address": address,
            "stage": {"label": get("stage"), "official_text": get("stage")},
            "stage_dates": {f: _norm(row.get(f)) for f in detected["date_fields"] if row.get(f)},
            "area_m2": _to_float(get("area_m2")),
            "latitude": None, "longitude": None, "mappable": False, "has_location": False,
            "location_notice": "검증된 주소 좌표가 아직 없어 지도에 표시하지 않아요." if address else "주소가 없어 지도에 표시할 수 없어요.",
            "coordinate_verified": False,
            "official_source": {"name": spec["title"], "provider": spec["provider"], "url": spec["url"],
                                "data_go_kr": spec["data_go_kr"], "service": spec["service"]},
            "collected_at": fetched["fetched_at"],
            "source_base_date": base,
            "needs_refresh": (base_dt is None) or (now - base_dt > timedelta(days=STALE_DAYS)),
            "freshness_note": ("원본 기준일 필드를 확인하지 못했어요(수집일만 확인됨)." if base is None
                               else ("원본 기준일이 1년 넘게 지나 최신 정보 확인이 필요해요." if base_dt and now - base_dt > timedelta(days=STALE_DAYS) else None)),
            "boundary": None,  # 공식 정비구역 경계 미연결
            "mapping_status": detected["status"],
            "source_dataset": dataset,
            "raw": dict(row),
        }
        record["missing"] = [k for k in ("name", "sigun", "type_label", "address") if not record[k]] + \
            ([] if record["stage"]["label"] else ["stage"])
        record["sigun_valid"] = sigun in GYEONGGI_SIGUN
        out.append(record)
    return out, detected


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
                      "mapping": {k: detected[k] for k in ("mapping", "basis", "status", "date_fields", "unmapped", "fields")}}
    mark_duplicates(records)
    return records, meta


# ---------- 경기 주소 좌표 검증(서울 검증기와 분리) ----------

GYEONGGI_BOUNDS = {"longitude": (126.25, 127.90), "latitude": (36.85, 38.35)}
ACCEPTED_ACCURACY = ("PARCEL", "BUILDING", "ROAD_ADDRESS")


def wanted(address):
    text = _norm(address)
    tokens = text.split()
    si = next((t for t in tokens if re.fullmatch(r"[가-힣]+(시|군)", t)), None)
    gu = next((t for t in tokens if re.fullmatch(r"[가-힣]+구", t)), None)
    dong = next((t for t in tokens if re.fullmatch(r"[가-힣0-9]+(동|읍|면|리|가)", t)), None)
    lot = re.search(r"(?:^|\s)(산?\d+(?:-\d+)?)(?:번지)?(?:\s*(?:일대|외\s*\d+\s*필지))?\s*$", text)
    return {"si": si, "gu": gu, "dong": dong, "lot": lot.group(1) if lot else None}


def verify_coordinate(address, response):
    """provider 응답에서 '경기도·시군(구)·동·지번이 모두 일치하는 후보가 정확히 하나'일 때만 좌표를 채택한다."""
    parts = wanted(address)
    if not parts["si"] or not parts["lot"]:
        return {"coordinate_verified": False, "reason": "ADDRESS_HAS_NO_LOT_OR_SIGUN"}
    if not response or response.get("result_status") != "MATCHED":
        return {"coordinate_verified": False, "reason": "NO_MATCH"}
    passing = []
    for c in response.get("candidates") or []:
        lon, lat = c.get("longitude"), c.get("latitude")
        el = c.get("address_elements") or {}
        if el:
            sigungu = el.get("SIGUGUN", "")
            ok_region = el.get("SIDO", "") == "경기도" and sigungu.split()[0:1] == [parts["si"]] and \
                (not parts["gu"] or parts["gu"] in sigungu.split())
            ok_dong = not parts["dong"] or el.get("DONGMYUN", "") == parts["dong"] or el.get("RI", "") == parts["dong"]
            ok_lot = el.get("LAND_NUMBER", "") == parts["lot"]
        else:
            text = _norm(c.get("matched_address"))
            ok_region = "경기" in text and parts["si"] in text.split() and (not parts["gu"] or parts["gu"] in text.split())
            ok_dong = not parts["dong"] or parts["dong"] in text.split()
            ok_lot = text.endswith(parts["lot"]) or f" {parts['lot']} " in f" {text} "
        ok_bounds = isinstance(lon, (int, float)) and isinstance(lat, (int, float)) and \
            GYEONGGI_BOUNDS["longitude"][0] <= lon <= GYEONGGI_BOUNDS["longitude"][1] and \
            GYEONGGI_BOUNDS["latitude"][0] <= lat <= GYEONGGI_BOUNDS["latitude"][1]
        if c.get("accuracy") in ACCEPTED_ACCURACY and ok_region and ok_dong and ok_lot and ok_bounds:
            passing.append(c)
    if len(passing) != 1:
        return {"coordinate_verified": False, "reason": "NO_CANDIDATE_PASSED" if not passing else "MULTIPLE_CANDIDATES"}
    c = passing[0]
    return {"coordinate_verified": True, "latitude": c["latitude"], "longitude": c["longitude"],
            "geocode_source": response.get("provider"), "matched_address": c.get("matched_address"),
            "reason": None}


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
