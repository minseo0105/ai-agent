
from __future__ import annotations

import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, date
from typing import Optional

import requests
import streamlit as st


DB_NAME = "realestate_monitor.db"

CHEONGYAK_APT_URL = (
    "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"
)

CHEONGYAK_UNSOLD_URL = (
    "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getRemndrLttotPblancDetail"
)

# 실거래 매매 API
TRADE_APIS = {
    "아파트": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "연립·다세대": "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    "단독·다가구": "https://apis.data.go.kr/1613000/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade",
    "오피스텔": "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade",
}

PROPERTY_TYPES = list(TRADE_APIS.keys())

# 화면 표시용 지역명 → 법정동 시군구코드 앞 5자리
REGION_LAWD = {
    # 서울
    "서울 > 종로구": "11110",
    "서울 > 중구": "11140",
    "서울 > 용산구": "11170",
    "서울 > 성동구": "11200",
    "서울 > 광진구": "11215",
    "서울 > 동대문구": "11230",
    "서울 > 중랑구": "11260",
    "서울 > 성북구": "11290",
    "서울 > 강북구": "11305",
    "서울 > 도봉구": "11320",
    "서울 > 노원구": "11350",
    "서울 > 은평구": "11380",
    "서울 > 서대문구": "11410",
    "서울 > 마포구": "11440",
    "서울 > 양천구": "11470",
    "서울 > 강서구": "11500",
    "서울 > 구로구": "11530",
    "서울 > 금천구": "11545",
    "서울 > 영등포구": "11560",
    "서울 > 동작구": "11590",
    "서울 > 관악구": "11620",
    "서울 > 서초구": "11650",
    "서울 > 강남구": "11680",
    "서울 > 송파구": "11710",
    "서울 > 강동구": "11740",

    # 경기
    "경기 > 수원시 장안구": "41111",
    "경기 > 수원시 권선구": "41113",
    "경기 > 수원시 팔달구": "41115",
    "경기 > 수원시 영통구": "41117",

    "경기 > 성남시 수정구": "41131",
    "경기 > 성남시 중원구": "41133",
    "경기 > 성남시 분당구": "41135",

    "경기 > 의정부시": "41150",

    "경기 > 안양시 만안구": "41171",
    "경기 > 안양시 동안구": "41173",

    "경기 > 부천시 원미구": "41192",
    "경기 > 부천시 소사구": "41194",
    "경기 > 부천시 오정구": "41196",

    "경기 > 광명시": "41210",
    "경기 > 평택시": "41220",
    "경기 > 동두천시": "41250",

    "경기 > 안산시 상록구": "41271",
    "경기 > 안산시 단원구": "41273",

    "경기 > 고양시 덕양구": "41281",
    "경기 > 고양시 일산동구": "41285",
    "경기 > 고양시 일산서구": "41287",

    "경기 > 과천시": "41290",
    "경기 > 구리시": "41310",
    "경기 > 남양주시": "41360",
    "경기 > 오산시": "41370",
    "경기 > 시흥시": "41390",
    "경기 > 군포시": "41410",
    "경기 > 의왕시": "41430",
    "경기 > 하남시": "41450",

    "경기 > 용인시 처인구": "41461",
    "경기 > 용인시 기흥구": "41463",
    "경기 > 용인시 수지구": "41465",

    "경기 > 파주시": "41480",
    "경기 > 이천시": "41500",
    "경기 > 안성시": "41550",
    "경기 > 김포시": "41570",
    "경기 > 화성시": "41590",
    "경기 > 광주시": "41610",
    "경기 > 양주시": "41630",
    "경기 > 포천시": "41650",
    "경기 > 여주시": "41670",
    "경기 > 연천군": "41800",
    "경기 > 가평군": "41820",
    "경기 > 양평군": "41830",
}

SEOUL_REGIONS = [k for k in REGION_LAWD if k.startswith("서울 >")]
GYEONGGI_REGIONS = [k for k in REGION_LAWD if k.startswith("경기 >")]
ALL_REGIONS = SEOUL_REGIONS + GYEONGGI_REGIONS


def _secret(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        if "realestate" in st.secrets and name in st.secrets["realestate"]:
            value = st.secrets["realestate"][name]
            if value is None:
                return default
            return str(value).strip()
    except Exception:
        pass
    return default


def get_public_data_key() -> str:
    key = _secret("PUBLIC_DATA_API_KEY")
    if not key:
        raise RuntimeError(
            "PUBLIC_DATA_API_KEY가 없습니다. "
            ".streamlit/secrets.toml의 [realestate] 섹션에 등록해주세요."
        )
    return key


def get_api_status():
    return {"public_data_key": bool(_secret("PUBLIC_DATA_API_KEY"))}


def _db(base_dir: Path):
    return sqlite3.connect(base_dir / DB_NAME)


def init_db(base_dir: Path):
    con = _db(base_dir)
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS alert_rules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        region TEXT NOT NULL,
        lawd_cd TEXT,
        max_price_100m REAL NOT NULL,
        min_area REAL NOT NULL,
        event_type TEXT NOT NULL,
        supply_type TEXT DEFAULT '전체',
        property_type TEXT DEFAULT '아파트',
        enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT UNIQUE,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS source_snapshots(
        source TEXT NOT NULL,
        item_key TEXT NOT NULL,
        payload TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        PRIMARY KEY(source, item_key)
    );
    """)

    cols = [row[1] for row in cur.execute("PRAGMA table_info(alert_rules)").fetchall()]

    if "supply_type" not in cols:
        cur.execute(
            "ALTER TABLE alert_rules ADD COLUMN supply_type TEXT DEFAULT '전체'"
        )

    if "property_type" not in cols:
        cur.execute(
            "ALTER TABLE alert_rules ADD COLUMN property_type TEXT DEFAULT '아파트'"
        )

    con.commit()
    con.close()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _normalize(text: str) -> str:
    return str(text or "").replace(" ", "").strip()


def region_terms(region_label: str) -> list[str]:
    left, _, right = region_label.partition(">")
    terms = [left.strip()]
    terms.extend([x.strip() for x in right.strip().split() if x.strip()])
    return [x for x in terms if x]


def region_matches_text(region_label: str, text: str) -> bool:
    compact = _normalize(text)
    terms = region_terms(region_label)
    locality_terms = terms[1:] if len(terms) > 1 else terms
    return all(_normalize(term) in compact for term in locality_terms)


def _parse_date(value: str):
    if not value:
        return None

    value = str(value).strip()

    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            pass

    return None


def classify_supply_type(raw: dict) -> str:
    candidate_keys = [
        "HOUSE_SECD_NM",
        "HOUSE_DTL_SECD_NM",
        "BSNS_MBY_NM",
        "CNSTRCT_ENTRPS_NM",
        "HSSPLY_ADRES",
        "HOUSE_NM",
    ]

    text = " ".join(str(raw.get(k) or "") for k in candidate_keys)
    compact = _normalize(text)

    public_keywords = [
        "LH",
        "SH",
        "GH",
        "한국토지주택공사",
        "서울주택도시공사",
        "경기주택도시공사",
        "공공분양",
        "공공주택",
        "신혼희망타운",
    ]

    private_keywords = [
        "민영",
        "민간분양",
        "주식회사",
        "(주)",
    ]

    if any(_normalize(k) in compact for k in public_keywords):
        return "공공"

    if any(_normalize(k) in compact for k in private_keywords):
        return "민간"

    return "미분류"


def classify_subscription_status(begin_date: str, end_date: str) -> str:
    begin = _parse_date(begin_date)
    end = _parse_date(end_date)
    today = date.today()

    if begin and today < begin:
        return "접수예정"

    if begin and end and begin <= today <= end:
        return "접수중"

    if end and today > end:
        return "접수마감"

    return "일정확인"


def classify_subscription_kind(raw: dict, fallback="일반분양") -> str:
    text = " ".join(
        str(raw.get(k) or "")
        for k in [
            "HOUSE_SECD_NM",
            "HOUSE_DTL_SECD_NM",
            "HOUSE_NM",
        ]
    )
    compact = _normalize(text)

    if "신혼희망타운" in compact:
        return "신혼희망타운"

    if "사전청약" in compact:
        return "사전청약"

    return fallback


def fetch_apt_subscriptions(page=1, per_page=100):
    params = {
        "page": page,
        "perPage": per_page,
        "serviceKey": get_public_data_key(),
    }

    response = requests.get(
        CHEONGYAK_APT_URL,
        params=params,
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    rows = data.get("data") or []
    result = []

    for row in rows:
        house_no = str(row.get("HOUSE_MANAGE_NO") or "")
        pblanc_no = str(row.get("PBLANC_NO") or "")

        begin_date = str(row.get("RCEPT_BGNDE") or "")
        end_date = str(row.get("RCEPT_ENDDE") or "")

        result.append({
            "id": f"apt:{house_no}:{pblanc_no}",
            "name": str(row.get("HOUSE_NM") or "APT 청약"),
            "type": "신규청약",
            "region": str(row.get("SUBSCRPT_AREA_CODE_NM") or ""),
            "address": str(row.get("HSSPLY_ADRES") or ""),
            "announce_date": str(row.get("RCRIT_PBLANC_DE") or ""),
            "apply_begin": begin_date,
            "apply_end": end_date,
            "apply_date": f"{begin_date} ~ {end_date}".strip(" ~"),
            "homepage": str(row.get("HMPG_ADRES") or ""),
            "supply_type": classify_supply_type(row),
            "subscription_kind": classify_subscription_kind(row),
            "status": classify_subscription_status(begin_date, end_date),
            "raw": row,
        })

    return result


def fetch_unsold_subscriptions(page=1, per_page=100):
    params = {
        "page": page,
        "perPage": per_page,
        "serviceKey": get_public_data_key(),
    }

    response = requests.get(
        CHEONGYAK_UNSOLD_URL,
        params=params,
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    rows = data.get("data") or []
    result = []

    for row in rows:
        house_no = str(row.get("HOUSE_MANAGE_NO") or "")
        pblanc_no = str(row.get("PBLANC_NO") or "")

        begin_date = str(row.get("RCEPT_BGNDE") or "")
        end_date = str(row.get("RCEPT_ENDDE") or "")

        result.append({
            "id": f"remndr:{house_no}:{pblanc_no}",
            "name": str(row.get("HOUSE_NM") or "무순위 청약"),
            "type": "무순위청약",
            "region": str(row.get("SUBSCRPT_AREA_CODE_NM") or ""),
            "address": str(row.get("HSSPLY_ADRES") or ""),
            "announce_date": str(row.get("RCRIT_PBLANC_DE") or ""),
            "apply_begin": begin_date,
            "apply_end": end_date,
            "apply_date": f"{begin_date} ~ {end_date}".strip(" ~"),
            "homepage": str(row.get("HMPG_ADRES") or ""),
            "supply_type": classify_supply_type(row),
            "subscription_kind": "무순위/잔여세대",
            "status": classify_subscription_status(begin_date, end_date),
            "raw": row,
        })

    return result


def filter_subscriptions(
    items,
    regions=None,
    supply_types=None,
    subscription_kinds=None,
    statuses=None,
):
    regions = regions or []
    supply_types = supply_types or []
    subscription_kinds = subscription_kinds or []
    statuses = statuses or []

    filtered = []

    for item in items:
        text = f"{item.get('region', '')} {item.get('address', '')}"

        if regions:
            if not any(region_matches_text(region, text) for region in regions):
                continue

        if supply_types:
            if item.get("supply_type") not in supply_types:
                continue

        if subscription_kinds:
            if item.get("subscription_kind") not in subscription_kinds:
                continue

        if statuses:
            if item.get("status") not in statuses:
                continue

        filtered.append(item)

    return filtered


def _xml_text(node, tag, default=""):
    child = node.find(tag)
    if child is None:
        return default
    return (child.text or "").strip()


def _first_xml_text(node, tags, default=""):
    for tag in tags:
        value = _xml_text(node, tag)
        if value:
            return value
    return default


def _parse_money_100m(amount_text: str) -> float:
    try:
        return int(str(amount_text).replace(",", "").strip()) / 10000.0
    except Exception:
        return 0.0


def _parse_float(text: str) -> float:
    try:
        return float(str(text).strip())
    except Exception:
        return 0.0


def _trade_item_to_common(item, property_type: str, lawd_cd: str, deal_ymd: str):
    amount_text = _first_xml_text(
        item,
        ["dealAmount", "dealAmount "],
        "",
    )

    if property_type == "단독·다가구":
        area_text = _first_xml_text(
            item,
            ["totalFloorAr", "buildingAr", "excluUseAr", "plottageAr"],
            "",
        )
    else:
        area_text = _first_xml_text(
            item,
            ["excluUseAr", "area", "buildingAr"],
            "",
        )

    year = _xml_text(item, "dealYear")
    month = _xml_text(item, "dealMonth")
    day = _xml_text(item, "dealDay")

    if year and month and day:
        try:
            deal_date = f"{year}-{int(month):02d}-{int(day):02d}"
        except Exception:
            deal_date = deal_ymd
    else:
        deal_date = deal_ymd

    if property_type == "아파트":
        name = _first_xml_text(
            item,
            ["aptNm", "aptName"],
            "아파트",
        )
    elif property_type == "연립·다세대":
        name = _first_xml_text(
            item,
            ["mhouseNm", "houseType"],
            "연립·다세대",
        )
    elif property_type == "오피스텔":
        name = _first_xml_text(
            item,
            ["offiNm", "offiName"],
            "오피스텔",
        )
    else:
        name = _first_xml_text(
            item,
            ["houseType"],
            "단독·다가구",
        )

    floor = _first_xml_text(
        item,
        ["floor"],
        "-",
    )

    build_year = _first_xml_text(
        item,
        ["buildYear"],
        "-",
    )

    umd = _first_xml_text(
        item,
        ["umdNm", "umdName"],
        "",
    )

    jibun = _first_xml_text(
        item,
        ["jibun"],
        "",
    )

    road_name = _first_xml_text(
        item,
        ["roadNm", "roadName"],
        "",
    )

    # 거래 고유키용 보조값
    sequence = _first_xml_text(
        item,
        ["aptSeq", "sggCd"],
        "",
    )

    price_100m = _parse_money_100m(amount_text)
    area = _parse_float(area_text)

    return {
        "id": (
            f"{property_type}:{lawd_cd}:{sequence}:"
            f"{name}:{deal_date}:{floor}:{amount_text}:{area_text}"
        ),
        "property_type": property_type,
        "name": name,
        "region": umd,
        "jibun": jibun,
        "road_name": road_name,
        "area": area,
        "price_100m": price_100m,
        "price_text": f"{price_100m:.2f}억원",
        "date": deal_date,
        "floor": floor,
        "build_year": build_year,
    }


def fetch_trade(
    property_type: str,
    lawd_cd: str,
    deal_ymd: str,
    rows=1000,
):
    if property_type not in TRADE_APIS:
        raise ValueError(f"지원하지 않는 주택유형입니다: {property_type}")

    params = {
        "serviceKey": get_public_data_key(),
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "pageNo": 1,
        "numOfRows": rows,
    }

    response = requests.get(
        TRADE_APIS[property_type],
        params=params,
        timeout=25,
    )
    response.raise_for_status()

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        raise RuntimeError(
            f"{property_type} API 응답을 XML로 해석하지 못했습니다."
        ) from e

    header = root.find(".//header")
    if header is not None:
        result_code = _xml_text(header, "resultCode")
        result_msg = _xml_text(header, "resultMsg")

        if result_code not in ("000", "00", ""):
            raise RuntimeError(
                f"{property_type} API 오류 {result_code}: {result_msg}"
            )

    result = []

    for item in root.findall(".//item"):
        result.append(
            _trade_item_to_common(
                item,
                property_type,
                lawd_cd,
                deal_ymd,
            )
        )

    return result


def fetch_trades_multi(
    region_labels: list[str],
    property_types: list[str],
    deal_ymd: str,
):
    all_rows = []
    errors = []

    for region_label in region_labels:
        lawd_cd = REGION_LAWD.get(region_label)

        if not lawd_cd:
            errors.append(f"{region_label}: 지역코드를 찾을 수 없습니다.")
            continue

        for property_type in property_types:
            try:
                rows = fetch_trade(
                    property_type,
                    lawd_cd,
                    deal_ymd,
                )

                for row in rows:
                    row["region_label"] = region_label

                all_rows.extend(rows)

            except Exception as e:
                errors.append(
                    f"{region_label} · {property_type}: {e}"
                )

    all_rows.sort(
        key=lambda x: (
            x.get("date", ""),
            x.get("region_label", ""),
            x.get("property_type", ""),
        ),
        reverse=True,
    )

    return all_rows, errors


def save_alert_rules(
    base_dir: Path,
    regions: list[str],
    event_types: list[str],
    max_price_100m: float,
    min_area: float,
    supply_types: list[str],
    property_types: list[str],
):
    init_db(base_dir)

    supply_value = ",".join(supply_types or ["전체"])

    # 실거래가 선택되어도 주택유형을 고르지 않았다면 아파트 기본
    trade_property_types = property_types or ["아파트"]

    con = _db(base_dir)

    for region in regions:
        lawd_cd = REGION_LAWD.get(region, "")

        for event_type in event_types:

            if event_type == "신규실거래":
                for property_type in trade_property_types:
                    con.execute("""
                        INSERT INTO alert_rules(
                            region,
                            lawd_cd,
                            max_price_100m,
                            min_area,
                            event_type,
                            supply_type,
                            property_type,
                            enabled,
                            created_at
                        )
                        VALUES(?,?,?,?,?,?,?,1,?)
                    """, (
                        region,
                        lawd_cd,
                        max_price_100m,
                        min_area,
                        event_type,
                        supply_value,
                        property_type,
                        _now(),
                    ))
            else:
                con.execute("""
                    INSERT INTO alert_rules(
                        region,
                        lawd_cd,
                        max_price_100m,
                        min_area,
                        event_type,
                        supply_type,
                        property_type,
                        enabled,
                        created_at
                    )
                    VALUES(?,?,?,?,?,?,?,1,?)
                """, (
                    region,
                    lawd_cd,
                    max_price_100m,
                    min_area,
                    event_type,
                    supply_value,
                    "해당없음",
                    _now(),
                ))

    con.commit()
    con.close()


def get_alert_rules(base_dir: Path):
    init_db(base_dir)

    con = _db(base_dir)
    con.row_factory = sqlite3.Row

    rows = [
        dict(row)
        for row in con.execute(
            "SELECT * FROM alert_rules ORDER BY id DESC"
        )
    ]

    con.close()

    for row in rows:
        row["enabled"] = bool(row["enabled"])

    return rows


def toggle_alert_rule(base_dir: Path, rule_id: int):
    con = _db(base_dir)

    con.execute("""
        UPDATE alert_rules
        SET enabled =
            CASE enabled
                WHEN 1 THEN 0
                ELSE 1
            END
        WHERE id=?
    """, (rule_id,))

    con.commit()
    con.close()


def delete_alert_rule(base_dir: Path, rule_id: int):
    con = _db(base_dir)
    con.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
    con.commit()
    con.close()


def get_notifications(base_dir: Path, limit=100):
    init_db(base_dir)

    con = _db(base_dir)
    con.row_factory = sqlite3.Row

    rows = [
        dict(row)
        for row in con.execute(
            "SELECT * FROM notifications ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    ]

    con.close()

    for row in rows:
        row["is_read"] = bool(row["is_read"])

    return rows


def mark_notification_read(base_dir: Path, notification_id: int):
    con = _db(base_dir)
    con.execute(
        "UPDATE notifications SET is_read=1 WHERE id=?",
        (notification_id,),
    )
    con.commit()
    con.close()


def _snapshot_new(base_dir: Path, source: str, item_key: str, payload: dict):
    con = _db(base_dir)

    exists = con.execute("""
        SELECT 1
        FROM source_snapshots
        WHERE source=? AND item_key=?
    """, (source, item_key)).fetchone() is not None

    now = _now()
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)

    if exists:
        con.execute("""
            UPDATE source_snapshots
            SET payload=?, last_seen_at=?
            WHERE source=? AND item_key=?
        """, (
            payload_json,
            now,
            source,
            item_key,
        ))
    else:
        con.execute("""
            INSERT INTO source_snapshots(
                source,
                item_key,
                payload,
                first_seen_at,
                last_seen_at
            )
            VALUES(?,?,?,?,?)
        """, (
            source,
            item_key,
            payload_json,
            now,
            now,
        ))

    con.commit()
    con.close()

    return not exists


def _notify(
    base_dir: Path,
    event_key: str,
    category: str,
    title: str,
    message: str,
):
    con = _db(base_dir)

    try:
        con.execute("""
            INSERT INTO notifications(
                event_key,
                category,
                title,
                message,
                is_read,
                created_at
            )
            VALUES(?,?,?,?,0,?)
        """, (
            event_key,
            category,
            title,
            message,
            _now(),
        ))
        con.commit()
        created = True

    except sqlite3.IntegrityError:
        created = False

    con.close()
    return created


def _rule_supply_matches(rule: dict, item: dict) -> bool:
    rule_supply = str(rule.get("supply_type") or "전체")
    allowed = [x.strip() for x in rule_supply.split(",") if x.strip()]

    if not allowed or "전체" in allowed:
        return True

    return item.get("supply_type") in allowed


def run_monitoring_once(base_dir: Path):
    init_db(base_dir)

    rules = [
        row
        for row in get_alert_rules(base_dir)
        if row["enabled"]
    ]

    report = {
        "events": 0,
        "notifications": 0,
        "errors": [],
        "fetched": {
            "subscriptions": 0,
            "trades": 0,
        },
    }

    apt_subscriptions = []
    unsold_subscriptions = []

    if any(
        r["event_type"] in ("신규청약", "무순위청약")
        for r in rules
    ):
        try:
            apt_subscriptions = fetch_apt_subscriptions()
            report["fetched"]["subscriptions"] += len(apt_subscriptions)
        except Exception as e:
            report["errors"].append(f"신규청약 조회 실패: {e}")

        try:
            unsold_subscriptions = fetch_unsold_subscriptions()
            report["fetched"]["subscriptions"] += len(unsold_subscriptions)
        except Exception as e:
            report["errors"].append(f"무순위청약 조회 실패: {e}")

    for rule in rules:

        if rule["event_type"] in ("신규청약", "무순위청약"):
            items = (
                unsold_subscriptions
                if rule["event_type"] == "무순위청약"
                else apt_subscriptions
            )

            for item in items:
                text = f"{item.get('region','')} {item.get('address','')}"

                if not region_matches_text(rule["region"], text):
                    continue

                if not _rule_supply_matches(rule, item):
                    continue

                if not _snapshot_new(
                    base_dir,
                    "cheongyak",
                    item["id"],
                    item,
                ):
                    continue

                report["events"] += 1

                message = (
                    f"{rule['region']} · "
                    f"{item.get('supply_type','')} · "
                    f"{item.get('status','')} · "
                    f"접수 {item.get('apply_date','')} · "
                    f"{item.get('address','')}"
                )

                if _notify(
                    base_dir,
                    f"rule{rule['id']}:{item['id']}",
                    rule["event_type"],
                    item["name"],
                    message,
                ):
                    report["notifications"] += 1

        elif rule["event_type"] == "신규실거래":
            if not rule["lawd_cd"]:
                report["errors"].append(
                    f"{rule['region']}: 실거래 지역코드가 없습니다."
                )
                continue

            property_type = rule.get("property_type") or "아파트"

            try:
                trades = fetch_trade(
                    property_type,
                    rule["lawd_cd"],
                    datetime.now().strftime("%Y%m"),
                )
                report["fetched"]["trades"] += len(trades)

            except Exception as e:
                report["errors"].append(
                    f"{rule['region']} · {property_type} 실거래 조회 실패: {e}"
                )
                continue

            for item in trades:
                if rule["min_area"] > 0 and item["area"] < rule["min_area"]:
                    continue

                if rule["max_price_100m"] > 0 and item["price_100m"] > rule["max_price_100m"]:
                    continue

                if not _snapshot_new(
                    base_dir,
                    f"trade:{property_type}",
                    item["id"],
                    item,
                ):
                    continue

                report["events"] += 1

                area_text = (
                    f"{item['area']:.1f}㎡ · "
                    if item["area"] > 0
                    else ""
                )

                message = (
                    f"{rule['region']} · "
                    f"{property_type} · "
                    f"{area_text}"
                    f"{item['price_text']} · "
                    f"{item['date']} · "
                    f"{item['floor']}층"
                )

                if _notify(
                    base_dir,
                    f"rule{rule['id']}:{item['id']}",
                    "신규실거래",
                    item["name"],
                    message,
                ):
                    report["notifications"] += 1

    return report
