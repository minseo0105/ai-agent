import json
import math
import re
from datetime import date, datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "golf"
CATALOG_PATH = DATA_DIR / "catalog.json"
META_PATH = DATA_DIR / "catalog_meta.json"

VWORLD_URL = "https://api.vworld.kr/req/data"
VWORLD_DATASET = "LT_P_SGISGOLF"
VWORLD_KOREA_GEOM_FILTER = "BOX(124,33,132,39.5)"
QUARTER_MONTHS = 3


def _read_json(path, default):
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_pool_meta():
    return _read_json(
        META_PATH,
        {
            "last_updated": None,
            "source": "baseline_catalog",
            "count": 0,
            "status": "ready",
        },
    )


def _months_since(d1, d2):
    return (d2.year - d1.year) * 12 + d2.month - d1.month


def quarterly_refresh_due(today=None):
    today = today or date.today()
    meta = load_pool_meta()
    # 최초 baseline catalog는 날짜와 무관하게 한 번 VWorld 갱신 가능
    if "baseline" in str(meta.get("source") or "").lower():
        return True
    raw = meta.get("last_updated")
    if not raw:
        return True
    try:
        last = datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except Exception:
        return True
    return _months_since(last, today) >= QUARTER_MONTHS


def next_refresh_text():
    raw = load_pool_meta().get("last_updated")
    if not raw:
        return "지금 갱신 가능"
    try:
        last = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        idx = last.year * 12 + (last.month - 1) + QUARTER_MONTHS
        return f"{idx // 12}.{idx % 12 + 1:02d}"
    except Exception:
        return "확인 필요"


def _normalize_name(name):
    s = re.sub(r"\s+", "", str(name or "")).lower()
    for token in ["컨트리클럽", "countryclub", "골프클럽"]:
        s = s.replace(token, "")
    return s.replace("cc", "").replace("gc", "")


def _safe_id(name):
    token = re.sub(r"[^0-9a-z가-힣]+", "_", _normalize_name(name)).strip("_")
    return f"vworld_{token}" if token else "vworld_golf"


def _coords_from_geometry(geometry):
    """
    VWorld GeoJSON의 geometry에서 대표 좌표를 뽑는다.
    Point/Polygon/MultiPolygon 모두 최대한 보수적으로 지원.
    """
    if not isinstance(geometry, dict):
        return None, None

    coords = geometry.get("coordinates")
    gtype = str(geometry.get("type") or "")

    if gtype == "Point" and isinstance(coords, list) and len(coords) >= 2:
        try:
            return float(coords[0]), float(coords[1])
        except Exception:
            return None, None

    points = []

    def walk(v):
        if isinstance(v, list):
            if len(v) >= 2 and all(isinstance(x, (int, float)) for x in v[:2]):
                points.append((float(v[0]), float(v[1])))
            else:
                for child in v:
                    walk(child)

    walk(coords)
    if not points:
        return None, None

    # 단순 대표점(평균). 검색/Pool 표시용이며 정밀 GIS 계산용이 아님.
    x = sum(p[0] for p in points) / len(points)
    y = sum(p[1] for p in points) / len(points)
    return x, y


def _feature_name(feature):
    props = feature.get("properties") or {}
    for key in ["golf_name", "GOLF_NAME", "golfName", "name"]:
        value = props.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _feature_to_club(feature):
    name = _feature_name(feature)
    if not name:
        return None

    x, y = _coords_from_geometry(feature.get("geometry"))
    props = feature.get("properties") or {}

    return {
        "id": _safe_id(name),
        "name": name,
        "aliases": [],
        "area": "",
        "region": "",
        "city": "",
        "holes": None,
        "courses": [],
        "play": {"three_person": "확인 필요"},
        "fee": {
            "verified": False,
            "basis": "공식 요금 확인 필요",
        },
        "phone": "",
        "address": "",
        "official_url": "",
        "course_overview": "상세 코스정보는 공식 홈페이지에서 확인합니다.",
        "course_source": "vworld",
        "pool_source": "VWorld LT_P_SGISGOLF",
        "pool_checked": date.today().isoformat(),
        "vworld_x": x,
        "vworld_y": y,
        "vworld_properties": {
            k: v for k, v in props.items()
            if k not in {"golf_name", "GOLF_NAME"} and v not in (None, "")
        },
    }


def _extract_features(payload):
    """
    VWorld GetFeature 응답의 일반적인 GeoJSON 구조와
    response.result.featureCollection 구조를 모두 지원.
    """
    if not isinstance(payload, dict):
        return []

    if isinstance(payload.get("features"), list):
        return payload["features"]

    response = payload.get("response")
    if isinstance(response, dict):
        status = str(response.get("status") or "").upper()
        if status and status not in {"OK", "SUCCESS"}:
            error = response.get("error") or {}
            raise RuntimeError(
                f"VWorld 오류: {error.get('text') or error.get('code') or status}"
            )

        result = response.get("result") or {}
        fc = result.get("featureCollection") or result.get("featurecollection") or {}
        if isinstance(fc, dict) and isinstance(fc.get("features"), list):
            return fc["features"]

        if isinstance(result.get("features"), list):
            return result["features"]

    return []


def _total_count(payload):
    try:
        response = payload.get("response") or {}
        record = response.get("record") or {}
        for key in ["total", "totalCount", "totalcount"]:
            if record.get(key) is not None:
                return int(record[key])
    except Exception:
        pass
    return None


def fetch_vworld_golf_pool(api_key, domain, page_size=1000, max_pages=20):
    if not api_key:
        raise ValueError("VWORLD_API_KEY가 설정되지 않았습니다.")
    if not domain:
        raise ValueError("VWORLD_DOMAIN이 설정되지 않았습니다.")

    all_features = []
    seen = set()

    for page in range(1, max_pages + 1):
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": VWORLD_DATASET,
            "key": api_key,
            "domain": domain,
            "format": "json",
            "crs": "EPSG:4326",
            "geomFilter": VWORLD_KOREA_GEOM_FILTER,
            "size": page_size,
            "page": page,
        }

        r = requests.get(VWORLD_URL, params=params, timeout=40)
        r.raise_for_status()

        try:
            payload = r.json()
        except Exception as exc:
            raise RuntimeError("VWorld 응답이 JSON이 아닙니다.") from exc

        features = _extract_features(payload)
        if not features:
            if page == 1:
                raise RuntimeError(
                    "VWorld에서 골프장 데이터를 찾지 못했습니다. "
                    "인증키/인증 URL 또는 API 응답을 확인해주세요."
                )
            break

        added = 0
        for f in features:
            name = _feature_name(f)
            if not name:
                continue

            x, y = _coords_from_geometry(f.get("geometry"))
            dedup_key = (_normalize_name(name), round(x or 0, 4), round(y or 0, 4))
            if dedup_key in seen:
                continue

            seen.add(dedup_key)
            all_features.append(f)
            added += 1

        total = _total_count(payload)
        if total is not None and len(all_features) >= total:
            break
        if len(features) < page_size:
            break
        if added == 0:
            break

    clubs = []
    for f in all_features:
        club = _feature_to_club(f)
        if club:
            clubs.append(club)

    return enrich_vworld_regions(clubs)




def _safe_body_preview(response, limit=700):
    """API 키 등 민감정보 없이 VWorld 오류 본문 일부만 진단용으로 반환."""
    text = (response.text or "").strip()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def test_vworld_connection(api_key, domain, sample_size=5):
    """
    catalog.json을 수정하지 않는 VWorld 진단.
    JSON/XML/HTML 여부, HTTP 상태, Content-Type, VWorld 메시지를 확인한다.
    """
    params = {
        "service": "data",
        "request": "GetFeature",
        "data": VWORLD_DATASET,
        "key": api_key.strip(),
        "domain": domain.strip(),
        "format": "json",
        "crs": "EPSG:4326",
        "geomFilter": VWORLD_KOREA_GEOM_FILTER,
        "size": 1000,
        "page": 1,
    }

    try:
        response = requests.get(VWORLD_URL, params=params, timeout=25)
    except requests.RequestException as ex:
        return {
            "ok": False,
            "http_status": None,
            "content_type": "",
            "response_format": "연결 실패",
            "message": str(ex),
            "count": 0,
            "coordinate_ok": 0,
            "coordinate_bad": 0,
            "samples": [],
            "crs_requested": "EPSG:4326",
        }

    content_type = response.headers.get("Content-Type", "")
    body = (response.text or "").lstrip()
    fmt = "JSON" if body.startswith(("{", "[")) else (
        "XML" if body.startswith("<?xml") or body.startswith("<response") else
        "HTML" if "<html" in body[:300].lower() else "기타"
    )

    try:
        payload = response.json()
    except ValueError:
        return {
            "ok": False,
            "http_status": response.status_code,
            "content_type": content_type,
            "response_format": fmt,
            "message": _safe_body_preview(response) or "응답 본문이 비어 있습니다.",
            "count": 0,
            "coordinate_ok": 0,
            "coordinate_bad": 0,
            "samples": [],
            "crs_requested": "EPSG:4326",
        }

    # 실제 파서도 통과하는지 확인
    try:
        clubs = fetch_vworld_golf_pool(
            api_key=api_key.strip(),
            domain=domain.strip(),
            page_size=1000,
            max_pages=20,
        )
    except Exception as ex:
        # JSON 자체는 받았으나 VWorld 오류 JSON 또는 구조 차이
        msg = ""
        if isinstance(payload, dict):
            # 흔한 VWorld 응답 구조에서 오류 메시지 후보 수집
            candidates = [
                payload.get("message"),
                payload.get("error"),
                payload.get("response"),
            ]
            for x in candidates:
                if isinstance(x, str) and x.strip():
                    msg = x.strip()
                    break
        return {
            "ok": False,
            "http_status": response.status_code,
            "content_type": content_type,
            "response_format": "JSON",
            "message": msg or str(ex),
            "count": 0,
            "coordinate_ok": 0,
            "coordinate_bad": 0,
            "samples": [],
            "crs_requested": "EPSG:4326",
        }

    coord_ok, coord_bad = [], []
    for club in clubs:
        x, y = club.get("vworld_x"), club.get("vworld_y")
        try:
            lon, lat = float(x), float(y)
            valid = 124.0 <= lon <= 132.5 and 33.0 <= lat <= 39.5
        except (TypeError, ValueError):
            valid = False
        row = {"name": club.get("name") or "", "lat": y, "lon": x}
        (coord_ok if valid else coord_bad).append(row)

    samples = coord_ok[:sample_size]
    if len(samples) < sample_size:
        samples += coord_bad[:sample_size-len(samples)]

    return {
        "ok": bool(clubs),
        "http_status": response.status_code,
        "content_type": content_type,
        "response_format": "JSON",
        "message": "정상 응답" if clubs else "JSON 응답은 받았지만 골프장 데이터가 없습니다.",
        "count": len(clubs),
        "coordinate_ok": len(coord_ok),
        "coordinate_bad": len(coord_bad),
        "samples": samples,
        "crs_requested": "EPSG:4326",
    }



def classify_korea_subregion(lat, lon):
    """
    WGS84 좌표를 라운드 탐색용 중권역으로 분류한다.
    행정경계 API가 아니라 검색 UX용 근사 분류이며, 기존 검증된 region/city는 덮어쓰지 않는다.
    """
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return "", ""

    # 제주
    if 33.0 <= lat <= 34.0 and 126.0 <= lon <= 127.2:
        return "제주권", "제주"

    # 수도권: 서울/인천/경기. 경기남북은 한강·서울권 기준의 검색용 근사 분류
    if 36.85 <= lat <= 38.35 and 126.0 <= lon <= 128.0:
        if lon < 126.85 and 37.2 <= lat <= 37.9:
            return "수도권", "인천"
        if 126.75 <= lon <= 127.25 and 37.40 <= lat <= 37.72:
            return "수도권", "서울"
        return "수도권", "경기북부" if lat >= 37.55 else "경기남부"

    # 강원
    if 37.0 <= lat <= 38.7 and 127.3 <= lon <= 129.6:
        return "강원권", "강원영동" if lon >= 128.45 else "강원영서"

    # 충청
    if 35.8 <= lat < 37.35 and 126.0 <= lon <= 128.7:
        return "충청권", "충북" if lon >= 127.35 else "충남"

    # 영남
    if 34.5 <= lat <= 37.2 and 128.0 <= lon <= 130.0:
        return "영남권", "경북" if lat >= 35.65 else "경남"

    # 호남
    if 34.0 <= lat <= 36.3 and 125.8 <= lon <= 128.0:
        return "호남권", "전북" if lat >= 35.45 else "전남"

    return "", ""


def enrich_vworld_regions(clubs):
    """빈 지역정보에만 좌표 기반 중권역을 채운다."""
    for club in clubs:
        lat = club.get("vworld_y") or club.get("latitude") or club.get("lat")
        lon = club.get("vworld_x") or club.get("longitude") or club.get("lon")
        area, subregion = classify_korea_subregion(lat, lon)
        if area and not str(club.get("area") or "").strip():
            club["area"] = area
        # VWorld 신규건의 city는 시군 대신 검색용 중권역으로 사용
        if subregion and not str(club.get("city") or "").strip():
            club["city"] = subregion
        if subregion:
            club["subregion"] = subregion
    return clubs


def dedupe_golf_pool(clubs):
    """
    이름+근접좌표로 명백한 중복만 합친다.
    기존 상세정보가 있는 레코드를 우선 보존한다.
    """
    def norm_name(v):
        s = re.sub(r"[^0-9a-zA-Z가-힣]", "", str(v or "").lower())
        for token in ("골프클럽", "골프장", "컨트리클럽", "countryclub"):
            s = s.replace(token, "")
        return s

    def richness(x):
        keys = ("region", "city", "area", "fees", "course", "play", "review")
        return sum(bool(x.get(k)) for k in keys)

    out = []
    by_name = {}
    for club in clubs:
        key = norm_name(club.get("name"))
        if not key:
            out.append(club)
            continue

        existing_idx = by_name.get(key)
        if existing_idx is None:
            by_name[key] = len(out)
            out.append(club)
            continue

        old = out[existing_idx]
        # 더 풍부한 레코드를 기본으로 하고 빈 값만 보완
        if richness(club) > richness(old):
            old, club = club, old
            out[existing_idx] = old
        for k, v in club.items():
            if (k not in old or old.get(k) in (None, "", [], {})) and v not in (None, "", [], {}):
                old[k] = v
    return out



def golf_name_key(value):
    """기존 catalog명과 VWorld명을 비교하기 위한 강한 이름 정규화."""
    s = str(value or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"[^0-9a-zA-Z가-힣]", "", s)
    aliases = (
        "컨트리클럽", "골프클럽", "골프장", "컨트리", "countryclub",
        "golfclub", "golf", "club", "cc", "gc"
    )
    for token in aliases:
        s = s.replace(token, "")
    return s


def _valid_wgs84(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        return 33.0 <= lat <= 39.5 and 124.0 <= lon <= 132.5
    except (TypeError, ValueError):
        return False


def propagate_vworld_coordinates(merged, vworld_clubs):
    """
    VWorld 신규 레코드의 좌표를 기존 상세 레코드에도 재매칭한다.
    1) 정규화 이름 일치
    2) 충분히 긴 이름의 포함관계
    기존 상세정보는 유지하고 좌표/중권역만 보완한다.
    """
    vw = []
    for x in vworld_clubs:
        lat = x.get("vworld_y") or x.get("latitude") or x.get("lat")
        lon = x.get("vworld_x") or x.get("longitude") or x.get("lon")
        key = golf_name_key(x.get("name"))
        if key and _valid_wgs84(lat, lon):
            vw.append((key, x, float(lat), float(lon)))

    matched = 0
    for club in merged:
        lat = club.get("vworld_y") or club.get("latitude") or club.get("lat")
        lon = club.get("vworld_x") or club.get("longitude") or club.get("lon")
        if _valid_wgs84(lat, lon):
            continue

        key = golf_name_key(club.get("name"))
        if not key:
            continue

        candidates = []
        for vkey, vx, vlat, vlon in vw:
            exact = key == vkey
            contained = min(len(key), len(vkey)) >= 4 and (key in vkey or vkey in key)
            if exact or contained:
                score = 100 if exact else min(len(key), len(vkey))
                candidates.append((score, vx, vlat, vlon))

        if not candidates:
            continue

        candidates.sort(key=lambda z: z[0], reverse=True)
        _, vx, vlat, vlon = candidates[0]
        club["vworld_y"] = vlat
        club["vworld_x"] = vlon
        club["latitude"] = vlat
        club["longitude"] = vlon
        club["coord_source"] = "VWorld name rematch"

        area, subregion = classify_korea_subregion(vlat, vlon)
        if area and not club.get("area"):
            club["area"] = area
        if subregion:
            club["subregion"] = subregion
            if not club.get("city"):
                club["city"] = subregion
        matched += 1

    return merged, matched


def merge_with_existing(vworld_clubs, existing):
    """
    VWorld는 전국 골프장 Pool의 골격(골프장명/공간정보)으로 사용한다.
    기존 catalog에 검증해둔 지역/요금/3인/코스/전화/공식URL 등은 보존한다.
    """
    existing_by_name = {
        _normalize_name(c.get("name")): c
        for c in existing
        if c.get("name")
    }

    merged = []
    used_ids = set()
    matched_existing_names = set()

    for vw in vworld_clubs:
        key = _normalize_name(vw.get("name"))
        old = existing_by_name.get(key)

        if old:
            item = dict(vw)

            # 기존 검증/수작업 상세정보를 우선 보존
            for field in [
                "id", "name", "aliases", "area", "region", "city",
                "holes", "courses", "play", "fee", "phone", "address",
                "official_url", "course_overview", "course_source",
                "review_traits", "facilities", "verification", "data_checked", "data_source",
            ]:
                if old.get(field) not in (None, "", [], {}):
                    item[field] = old[field]

            matched_existing_names.add(key)
        else:
            item = vw

        # id 충돌 방지
        base_id = item["id"]
        candidate = base_id
        seq = 2
        while candidate in used_ids:
            candidate = f"{base_id}_{seq}"
            seq += 1
        item["id"] = candidate

        merged.append(item)
        used_ids.add(candidate)

    # VWorld에서 이름 매칭이 안 된 기존 상세 골프장도 삭제하지 않고 유지
    for old in existing:
        key = _normalize_name(old.get("name"))
        if key in matched_existing_names:
            continue

        item = dict(old)
        item["pool_status"] = "vworld_match_pending"

        base_id = item.get("id") or _safe_id(item.get("name"))
        candidate = base_id
        seq = 2
        while candidate in used_ids:
            candidate = f"{base_id}_{seq}"
            seq += 1
        item["id"] = candidate

        merged.append(item)
        used_ids.add(candidate)

    return merged


def refresh_pool(api_key, domain, force=False):
    if not force and not quarterly_refresh_due():
        meta = load_pool_meta()
        return {
            "updated": False,
            "reason": "quarter_not_due",
            "count": meta.get("count", 0),
        }

    existing = _read_json(CATALOG_PATH, [])
    vworld_clubs = fetch_vworld_golf_pool(api_key=api_key, domain=domain)

    if not vworld_clubs:
        raise RuntimeError("VWorld 골프장 Pool이 비어 있어 갱신을 중단했습니다.")

    merged = merge_with_existing(vworld_clubs, existing)
    merged, coord_rematched = propagate_vworld_coordinates(merged, vworld_clubs)
    merged = enrich_vworld_regions(merged)
    merged = dedupe_golf_pool(merged)

    # 비정상 응답 안전장치
    if existing and len(merged) < max(50, int(len(existing) * 0.5)):
        raise RuntimeError(
            f"갱신 결과가 비정상적으로 적습니다({len(merged)}개). "
            "기존 catalog.json은 변경하지 않았습니다."
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    backup = DATA_DIR / f"catalog_backup_{date.today().isoformat()}.json"
    if CATALOG_PATH.exists():
        backup.write_text(
            CATALOG_PATH.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    _write_json(CATALOG_PATH, merged)

    meta = {
        "last_updated": date.today().isoformat(),
        "source": "VWorld LT_P_SGISGOLF",
        "count": len(merged),
        "vworld_count": len(vworld_clubs),
        "coordinate_rematched": coord_rematched,
        "status": "updated",
        "refresh_cycle": "quarterly",
        "backup": backup.name if backup.exists() else None,
    }
    _write_json(META_PATH, meta)

    return {
        "updated": True,
        "count": len(merged),
        "vworld_count": len(vworld_clubs),
        "coordinate_rematched": coord_rematched,
        "backup": str(backup),
    }


def refresh_pool_dual(api_key, domain, public_service_key="", force=False):
    """
    1) VWorld로 전국 Pool 갱신
    2) 공공데이터포털 승인 API가 설정되어 있으면 같은 catalog를 교차확인
    공공 API 미설정/실패 시 VWorld 갱신 결과는 유지하고 오류를 결과에 기록한다.
    """
    result = refresh_pool(api_key=api_key, domain=domain, force=force)
    result["public_data"] = {"enabled": bool(public_service_key), "matched": 0}
    if not public_service_key:
        return result

    try:
        from services.golf_public_data import fetch_public_golf_records, match_public_records
        records = fetch_public_golf_records(public_service_key)
        clubs = _read_json(CATALOG_PATH, [])
        clubs, matched = match_public_records(clubs, records)
        _write_json(CATALOG_PATH, clubs)
        meta = load_pool_meta()
        meta["public_data_checked"] = date.today().isoformat()
        meta["public_data_records"] = len(records)
        meta["public_data_matched"] = matched
        meta["source"] = "VWorld + 공공데이터포털" if matched else meta.get("source")
        _write_json(META_PATH, meta)
        result["public_data"] = {
            "enabled": True, "records": len(records), "matched": matched, "status": "ok"
        }
    except Exception as exc:
        result["public_data"] = {
            "enabled": True, "matched": 0, "status": "error", "message": str(exc)[:300]
        }
    return result
