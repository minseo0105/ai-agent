import re
from pathlib import Path

from services.golf_repository import (
    load_records,
    load_active_db,
)
from services.golf_master import (
    is_round_eligible,
    known_holes,
)


# ============================================================
# DATA SOURCE
# ============================================================

def _copy_records(records):
    """
    repository cache의 원본 record를 화면 처리 과정에서
    직접 변경하지 않도록 얕은 복사본을 만든다.
    """
    return [dict(c) for c in records]


def load_catalog():
    """
    활성 Golf Repository DB를 읽는다.

    현재 우선순위:
    checkpoint > precision > knowledge_base > master > catalog
    """
    clubs = _copy_records(load_records())
    return prepare_service_pool(clubs)


def load_service_catalog(use_master=True, master_path=None):
    """
    기존 화면과의 호환성을 위해 함수명/파라미터는 유지한다.

    과거:
        catalog.json
            ↓
        attach_master()
            ↓
        화면

    현재:
        golf_repository
            ↓
        최신 checkpoint DB
            ↓
        화면

    use_master / master_path는 기존 호출부 호환을 위해 남겨둔다.
    checkpoint 자체가 이미 정밀화된 Master DB이므로
    attach_master()를 다시 수행하지 않는다.
    """

    db = load_active_db()
    clubs = _copy_records(db["records"])

    clubs = prepare_service_pool(clubs)

    # 현재 어떤 DB를 읽었는지 화면에서 진단 가능하도록 기록
    runtime = {
        "version": db["file_name"],
        "file_name": db["file_name"],
        "active_db": str(db["path"]),
        "precision_db": db["precision_db"],
        "diagnostic": "ok",
    }

    for club in clubs:
        club["_golf_runtime"] = runtime

    return clubs


# ============================================================
# COORDINATES / REGION
# ============================================================

def _coord_lat_lon(club):
    """
    여러 좌표 필드명을 지원한다.
    대한민국 범위의 정상 좌표만 반환한다.
    """

    # nested location 구조 지원
    location = club.get("location") or {}

    nested_pairs = [
        ("lat", "lon"),
        ("latitude", "longitude"),
        ("lat", "lng"),
    ]

    if isinstance(location, dict):
        for a, b in nested_pairs:
            try:
                lat = float(location.get(a))
                lon = float(location.get(b))

                if (
                    33 <= lat <= 39.5
                    and
                    124 <= lon <= 132.5
                ):
                    return lat, lon

            except (TypeError, ValueError):
                pass

    # 기존 flat 구조 지원
    for a, b in [
        ("lat", "lon"),
        ("latitude", "longitude"),
        ("lat", "lng"),
        ("vworld_y", "vworld_x"),
        ("y", "x"),
    ]:
        try:
            lat = float(club.get(a))
            lon = float(club.get(b))

            if (
                33 <= lat <= 39.5
                and
                124 <= lon <= 132.5
            ):
                return lat, lon

        except (TypeError, ValueError):
            pass

    return None


def classify_search_region(lat, lon):
    """
    좌표 기반 검색권역 추정.
    """

    if (
        33.0 <= lat <= 34.0
        and
        126.0 <= lon <= 127.2
    ):
        return "제주권", "제주"

    if (
        36.85 <= lat <= 38.35
        and
        126.0 <= lon <= 128.0
    ):

        if (
            lon < 126.85
            and
            37.2 <= lat <= 37.9
        ):
            return "수도권", "인천"

        if (
            126.75 <= lon <= 127.25
            and
            37.40 <= lat <= 37.72
        ):
            return "수도권", "서울"

        return (
            "수도권",
            "경기북부"
            if lat >= 37.55
            else "경기남부",
        )

    if (
        37.0 <= lat <= 38.7
        and
        127.3 <= lon <= 129.6
    ):
        return (
            "강원권",
            "강원영동"
            if lon >= 128.45
            else "강원영서",
        )

    if (
        35.8 <= lat < 37.35
        and
        126.0 <= lon <= 128.7
    ):
        return (
            "충청권",
            "충북"
            if lon >= 127.35
            else "충남",
        )

    if (
        34.5 <= lat <= 37.2
        and
        128.0 <= lon <= 130.0
    ):
        return (
            "영남권",
            "경북"
            if lat >= 35.65
            else "경남",
        )

    if (
        34.0 <= lat <= 36.3
        and
        125.8 <= lon <= 128.0
    ):
        return (
            "호남권",
            "전북"
            if lat >= 35.45
            else "전남",
        )

    return "", ""


def enrich_search_regions(clubs):
    """
    좌표가 있는데 area/subregion/city가 없는 경우만
    좌표 기반으로 보완한다.
    """

    for club in clubs:

        coord = _coord_lat_lon(club)

        if not coord:
            continue

        area, sub = classify_search_region(*coord)

        known_area = club.get("area")

        if known_area and known_area != area:

            lat, lon = coord

            sub = {
                "강원권":
                    "강원영동"
                    if lon >= 128.45
                    else "강원영서",

                "충청권":
                    "충북"
                    if lon >= 127.35
                    else "충남",

                "영남권":
                    "경북"
                    if lat >= 35.65
                    else "경남",

                "호남권":
                    "전북"
                    if lat >= 35.45
                    else "전남",

                "제주권":
                    "제주",

                "수도권":
                    "경기북부"
                    if lat >= 37.55
                    else "경기남부",

            }.get(
                known_area,
                "",
            )

        estimated = []

        for field, value in (
            ("area", area),
            ("subregion", sub),
            ("city", sub),
        ):

            if (
                value
                and
                not str(
                    club.get(field) or ""
                ).strip()
            ):
                club[field] = value
                estimated.append(field)

        if estimated:

            club.setdefault(
                "region_source",
                "coordinate_estimate",
            )

            provenance = club.setdefault(
                "region_field_sources",
                {},
            )

            for field in estimated:
                provenance[field] = (
                    "coordinate_estimate"
                )

    return clubs


# ============================================================
# ADDRESS → REGION
# ============================================================

def _city_from_address(address):
    """
    주소에서 시/군 이름 추출.
    """

    a = str(
        address or ""
    ).strip()

    if not a:
        return ""

    m = re.search(
        r"(?:^|\s)([가-힣]+(?:시|군))(?:\s|$)",
        a,
    )

    if m:
        return re.sub(
            r"(시|군)$",
            "",
            m.group(1),
        )

    metro = {
        "서울특별시": "서울",
        "서울시": "서울",
        "인천광역시": "인천",
        "인천시": "인천",
        "부산광역시": "부산",
        "대구광역시": "대구",
        "울산광역시": "울산",
        "광주광역시": "광주",
        "대전광역시": "대전",
        "세종특별자치시": "세종",
        "제주특별자치도": "제주",
    }

    for prefix, city in metro.items():

        if a.startswith(prefix):
            return city

    return ""


def _region_from_public_address(address):

    a = str(
        address or ""
    ).strip()

    if not a:
        return None

    city = _city_from_address(a)

    if a.startswith(
        ("서울특별시", "서울시")
    ):
        return (
            "수도권",
            "서울",
            city or "서울",
        )

    if a.startswith(
        ("인천광역시", "인천시")
    ):
        return (
            "수도권",
            "인천",
            city or "인천",
        )

    if a.startswith(
        ("제주특별자치도", "제주도")
    ):
        return (
            "제주권",
            "제주",
            city or "제주",
        )

    if a.startswith("충청북도"):
        return (
            "충청권",
            "충북",
            city,
        )

    if a.startswith("충청남도"):
        return (
            "충청권",
            "충남",
            city,
        )

    if a.startswith(
        ("강원특별자치도", "강원도")
    ):

        yeongdong = {
            "강릉",
            "동해",
            "속초",
            "삼척",
            "고성",
            "양양",
        }

        return (
            "강원권",
            "강원영동"
            if city in yeongdong
            else "강원영서",
            city,
        )

    if a.startswith("경상북도"):
        return (
            "영남권",
            "경북",
            city,
        )

    if a.startswith("경상남도"):
        return (
            "영남권",
            "경남",
            city,
        )

    if a.startswith(
        ("부산광역시", "울산광역시")
    ):
        return (
            "영남권",
            "경남",
            city
            or (
                "부산"
                if a.startswith("부산")
                else "울산"
            ),
        )

    if a.startswith("대구광역시"):
        return (
            "영남권",
            "경북",
            city or "대구",
        )

    if a.startswith(
        ("전북특별자치도", "전라북도")
    ):
        return (
            "호남권",
            "전북",
            city,
        )

    if a.startswith("전라남도"):
        return (
            "호남권",
            "전남",
            city,
        )

    if a.startswith("광주광역시"):
        return (
            "호남권",
            "전남",
            city or "광주",
        )

    if a.startswith(
        ("대전광역시", "세종특별자치시")
    ):
        return (
            "충청권",
            "충남",
            city
            or (
                "대전"
                if a.startswith("대전")
                else "세종"
            ),
        )

    if a.startswith("경기도"):

        north = {
            "고양",
            "파주",
            "의정부",
            "양주",
            "동두천",
            "포천",
            "연천",
            "가평",
            "구리",
            "남양주",
        }

        return (
            "수도권",
            "경기북부"
            if city in north
            else "경기남부",
            city,
        )

    return None


def _best_address(club):
    """
    checkpoint DB의 여러 주소 구조 중 가장 신뢰 가능한 주소 반환.
    """

    verification = (
        club.get("verification")
        or {}
    )

    public = (
        verification.get("public_data")
        or {}
    )

    candidates = [
        public.get("address"),
        club.get("address"),
    ]

    location = (
        club.get("location")
        or {}
    )

    if isinstance(location, dict):
        candidates.extend(
            [
                location.get("address"),
                location.get(
                    "road_address"
                ),
            ]
        )

    for value in candidates:

        value = str(
            value or ""
        ).strip()

        if value:
            return value

    return ""


def enrich_public_address_regions(clubs):
    """
    공공데이터 또는 정밀 DB 주소가 있으면
    지역분류에 사용한다.

    기존 코드처럼 public_data matched=True인 경우는
    가장 높은 우선순위로 처리한다.
    """

    for club in clubs:

        verification = (
            club.get("verification")
            or {}
        )

        public = (
            verification.get("public_data")
            or {}
        )

        public_matched = (
            public.get("matched")
            is True
        )

        address = _best_address(club)

        if not address:
            continue

        region = _region_from_public_address(
            address
        )

        if not region:
            continue

        area, subregion, city = region

        # 공공데이터 안전매칭이면 기존 값을 갱신 가능.
        # 일반 주소라면 비어 있는 값만 보완.
        overwrite = public_matched

        if (
            area
            and (
                overwrite
                or not club.get("area")
            )
        ):
            club["area"] = area

        if (
            subregion
            and (
                overwrite
                or not club.get("subregion")
            )
        ):
            club["subregion"] = subregion

        if (
            city
            and (
                overwrite
                or not club.get("city")
            )
        ):
            club["city"] = city

        source = (
            "public_address"
            if public_matched
            else "master_address"
        )

        club.setdefault(
            "region_source",
            source,
        )

    return clubs


# ============================================================
# SEARCH
# ============================================================

def find_clubs(query, clubs=None):

    clubs = (
        load_catalog()
        if clubs is None
        else clubs
    )

    clubs = [
        c
        for c in clubs
        if service_status(c)
        != "excluded"
    ]

    q = re.sub(
        r"\s+",
        "",
        str(query or ""),
    ).lower()

    if not q:
        return []

    out = []

    for c in clubs:

        aliases = (
            c.get("aliases")
            or []
        )

        if not isinstance(
            aliases,
            list,
        ):
            aliases = []

        values = [
            c.get("name", ""),
            c.get("city", ""),
            c.get("region", ""),
            c.get("subregion", ""),
            c.get("area", ""),
            _best_address(c),
        ] + aliases

        if any(
            q
            in re.sub(
                r"\s+",
                "",
                str(x),
            ).lower()
            for x in values
        ):
            out.append(c)

    return out


# ============================================================
# INFORMATION HELPERS
# ============================================================

def _has_information(value):

    if value is None:
        return False

    if isinstance(value, str):

        return (
            value.strip().lower()
            not in {
                "",
                "확인 필요",
                "확인필요",
                "미확인",
                "정보 없음",
                "unknown",
                "null",
                "none",
            }
        )

    if isinstance(value, dict):
        return any(
            _has_information(v)
            for v in value.values()
        )

    if isinstance(
        value,
        (list, tuple),
    ):
        return any(
            _has_information(v)
            for v in value
        )

    return isinstance(
        value,
        (int, float, bool),
    )


def _official_url(club):

    for key in (
        "official_url",
        "website",
        "homepage",
    ):

        value = str(
            club.get(key)
            or ""
        ).strip()

        if value:
            return value

    sources = club.get("sources") or []

    if isinstance(sources, list):

        for source in sources:

            if not isinstance(
                source,
                dict,
            ):
                continue

            source_type = str(
                source.get("source_type")
                or ""
            ).lower()

            url = str(
                source.get("source_url")
                or source.get("url")
                or ""
            ).strip()

            if (
                url
                and "official"
                in source_type
            ):
                return url

    return ""


# ============================================================
# PRICE NORMALIZATION
# ============================================================

def _pricing_records(club):
    """
    checkpoint ontology의 pricing.fee_records를 반환.
    """

    pricing = (
        club.get("pricing")
        or {}
    )

    if not isinstance(
        pricing,
        dict,
    ):
        return []

    records = (
        pricing.get("fee_records")
        or []
    )

    if not isinstance(
        records,
        list,
    ):
        return []

    return [
        r
        for r in records
        if isinstance(r, dict)
    ]


def _legacy_fee(club):

    fee = (
        club.get("fee")
        or {}
    )

    return (
        fee
        if isinstance(fee, dict)
        else {}
    )


def _green_fee(
    fee,
    weekend=False,
):

    primary = (
        "weekend_green"
        if weekend
        else "weekday_green"
    )

    legacy = (
        "weekend"
        if weekend
        else "weekday"
    )

    value = fee.get(primary)

    if value is None:
        value = fee.get(legacy)

    return value


def _record_price(record):
    """
    fee_record에서 대표 가격 추출.
    exact → min → max 순.
    """

    for key in (
        "price",
        "green_fee",
        "amount",
        "fee",
        "price_min",
        "min_price",
        "price_max",
        "max_price",
    ):

        value = record.get(key)

        if (
            isinstance(value, (int, float))
            and
            not isinstance(value, bool)
        ):
            return value

    return None


def _pricing_green_fee(
    club,
    weekend=False,
):
    """
    정밀 pricing에서 평일/주말 대표 그린피 추출.

    동적요금은 '현재 확정가'라고 단정하지 않고
    검색/예상 계산용 대표값으로만 사용한다.
    """

    records = _pricing_records(club)

    if not records:
        return None

    wanted = (
        {
            "weekend",
            "sat",
            "sun",
            "holiday",
            "주말",
            "토",
            "일",
            "공휴일",
        }
        if weekend
        else
        {
            "weekday",
            "weekdays",
            "mon",
            "tue",
            "wed",
            "thu",
            "fri",
            "평일",
            "주중",
        }
    )

    prices = []

    for record in records:

        day_type = str(
            record.get("day_type")
            or record.get("day")
            or record.get("weekday_type")
            or ""
        ).strip().lower()

        if day_type:

            if not any(
                token in day_type
                for token in wanted
            ):
                continue

        price = _record_price(
            record
        )

        if price is not None:
            prices.append(price)

    if not prices:

        # day_type 구조가 없는 경우
        for record in records:

            price = _record_price(
                record
            )

            if price is not None:
                prices.append(price)

    if not prices:
        return None

    return min(prices)


def _operations(club):

    operations = (
        club.get("operations")
        or {}
    )

    return (
        operations
        if isinstance(
            operations,
            dict,
        )
        else {}
    )


def _team_fee_from_operations(
    club,
    kind,
):
    """
    operations.caddie / operations.cart 구조에서
    팀 단위 요금을 가능한 범위에서 추출한다.
    """

    operations = _operations(club)

    info = operations.get(kind)

    if not isinstance(
        info,
        dict,
    ):
        return None

    for key in (
        "fee_team",
        "team_fee",
        "price_team",
        "fee",
        "price",
        "amount",
    ):

        value = info.get(key)

        if (
            isinstance(value, (int, float))
            and
            not isinstance(value, bool)
        ):
            return value

    return None


def estimate_per_person(
    c,
    weekend=False,
    players=4,
):
    """
    1인 예상비용.

    우선순위:
    1. 기존 verified fee
    2. checkpoint pricing
    3. cart/caddie는 legacy → operations

    가격을 확인할 수 없으면 None.
    """

    f = _legacy_fee(c)

    g = None

    # 기존 verified fee
    if f.get("verified"):
        g = _green_fee(
            f,
            weekend,
        )

    # 정밀 DB pricing
    if g is None:
        g = _pricing_green_fee(
            c,
            weekend,
        )

    if g is None:
        return None

    cart = (
        f.get("cart_team")
        or _team_fee_from_operations(
            c,
            "cart",
        )
        or 0
    )

    caddie = (
        f.get("caddie_team")
        or _team_fee_from_operations(
            c,
            "caddie",
        )
        or 0
    )

    extra = 0

    if players == 3:

        extra_key = (
            "three_person_weekend_extra"
            if weekend
            else "three_person_weekday_extra"
        )

        extra = (
            f.get(extra_key)
            or 0
        )

    try:

        return round(
            g
            + cart / players
            + caddie / players
            + extra
        )

    except (
        TypeError,
        ZeroDivisionError,
    ):
        return None


# ============================================================
# REVIEW SEED
# ============================================================

def load_review_seed(path=None):

    import json

    if path is None:

        path = (
            Path(__file__)
            .resolve()
            .parents[1]
            / "data"
            / "golf"
            / "review_seed.json"
        )

    else:
        path = Path(path)

    try:

        if not path.exists():
            return {}

        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        return (
            data
            if isinstance(data, dict)
            else {}
        )

    except Exception:
        return {}


# ============================================================
# AI CONDITION PARSER
# ============================================================

def parse_ai_conditions(
    text,
    current_area="전체",
    current_weekend=False,
    current_players=4,
    current_budget=None,
):

    t = str(
        text or ""
    ).strip()

    area = current_area
    weekend = current_weekend
    players = current_players
    budget = current_budget
    city = None
    traits = []

    city_map = {
        "서울": ["서울"],
        "인천": ["인천"],
        "용인": [
            "용인",
            "기흥",
            "처인",
            "수지",
        ],
        "성남": [
            "성남",
            "분당",
        ],
        "광주": [
            "경기광주",
            "광주",
        ],
        "이천": ["이천"],
        "여주": ["여주"],
        "안성": ["안성"],
        "화성": ["화성"],
        "가평": ["가평"],
        "양평": ["양평"],
        "포천": ["포천"],
        "춘천": ["춘천"],
        "원주": ["원주"],
        "홍천": ["홍천"],
        "횡성": ["횡성"],
        "강릉": ["강릉"],
        "속초": ["속초"],
        "고성": ["고성"],
        "청주": ["청주"],
        "충주": ["충주"],
        "음성": ["음성"],
        "보은": ["보은"],
        "천안": ["천안"],
        "아산": ["아산"],
        "대전": ["대전"],
        "세종": ["세종"],
        "부산": ["부산"],
        "대구": ["대구"],
        "울산": ["울산"],
        "창원": ["창원"],
        "김해": ["김해"],
        "양산": ["양산"],
        "경주": ["경주"],
        "포항": ["포항"],
        "거제": ["거제"],
        "광주광역시": [
            "광주광역시"
        ],
        "전주": ["전주"],
        "익산": ["익산"],
        "군산": ["군산"],
        "순천": ["순천"],
        "여수": ["여수"],
        "목포": ["목포"],
        "제주": [
            "제주",
            "서귀포",
        ],
        "서귀포": ["서귀포"],
    }

    for c, words in city_map.items():

        if any(
            w in t
            for w in words
        ):
            city = c
            break

    if any(
        x in t
        for x in [
            "제주",
            "서귀포",
        ]
    ):
        area = "제주권"

    elif any(
        x in t
        for x in [
            "호남",
            "전북",
            "전남",
            "광주광역시",
            "전주",
            "익산",
            "군산",
            "순천",
            "여수",
            "목포",
        ]
    ):
        area = "호남권"

    elif any(
        x in t
        for x in [
            "영남",
            "경북",
            "경남",
            "부산",
            "대구",
            "울산",
            "창원",
            "김해",
            "양산",
            "경주",
            "포항",
            "거제",
        ]
    ):
        area = "영남권"

    elif any(
        x in t
        for x in [
            "강원",
            "춘천",
            "원주",
            "홍천",
            "횡성",
            "강릉",
            "속초",
            "고성",
        ]
    ):
        area = "강원권"

    elif any(
        x in t
        for x in [
            "충청",
            "충북",
            "충남",
            "청주",
            "충주",
            "음성",
            "보은",
            "대전",
            "세종",
            "천안",
            "아산",
        ]
    ):
        area = "충청권"

    elif any(
        x in t
        for x in [
            "수도권",
            "서울",
            "경기",
            "인천",
            "용인",
            "성남",
            "분당",
            "이천",
            "여주",
            "안성",
            "화성",
            "가평",
            "양평",
            "포천",
        ]
    ):
        area = "수도권"

    if any(
        x in t
        for x in [
            "주말",
            "토요일",
            "일요일",
            "공휴일",
            "이번주말",
            "이번 주말",
        ]
    ):
        weekend = True

    elif any(
        x in t
        for x in [
            "주중",
            "평일",
            "월요일",
            "화요일",
            "수요일",
            "목요일",
            "금요일",
        ]
    ):
        weekend = False

    if any(
        x in t
        for x in [
            "3인",
            "3명",
            "세 명",
        ]
    ):
        players = 3

    elif any(
        x in t
        for x in [
            "4인",
            "4명",
            "네 명",
        ]
    ):
        players = 4

    m = re.search(
        r"(?:(\d{1,3})\s*만\s*원|\b(\d{5,6})\s*원)",
        t,
    )

    if m:

        budget = (
            int(m.group(1)) * 10000
            if m.group(1)
            else int(m.group(2))
        )

    trait_map = {
        "fairway_wide": [
            "페어웨이 넓",
            "넓은 페어웨이",
            "티샷 부담 적",
            "넓은 곳",
        ],
        "maintenance_good": [
            "관리 좋",
            "관리 잘",
            "잔디 좋",
            "컨디션 좋",
        ],
        "easy": [
            "쉬운",
            "편한 코스",
            "초보",
            "난이도 낮",
        ],
        "green_fast": [
            "그린 빠",
            "빠른 그린",
        ],
        "facilities_good": [
            "시설 좋",
            "클럽하우스 좋",
            "시설 좋은",
        ],
    }

    for key, words in trait_map.items():

        if any(
            w in t
            for w in words
        ):
            traits.append(key)

    return {
        "area": area,
        "city": city,
        "weekend": weekend,
        "players": players,
        "budget": budget,
        "traits": traits,
    }


# ============================================================
# TRAITS / RECOMMENDATION
# ============================================================

def _trait_match(c, trait):

    rt = (
        c.get("review_traits")
        or {}
    )

    if (
        isinstance(rt, dict)
        and
        rt.get(trait) is True
    ):
        return True

    evaluation = (
        c.get("evaluation")
        or {}
    )

    evaluation_text = ""

    if isinstance(
        evaluation,
        dict,
    ):
        evaluation_text = " ".join(
            str(v)
            for v in evaluation.values()
            if isinstance(
                v,
                (str, int, float),
            )
        )

    blob = (
        str(
            c.get(
                "course_overview",
                "",
            )
        )
        + " "
        + str(
            c.get(
                "review_traits",
                "",
            )
        )
        + " "
        + evaluation_text
    ).lower()

    phrases = {
        "fairway_wide": [
            "페어웨이 넓",
            "페어웨이 폭은 넓",
            "넓은 페어웨이",
        ],
        "maintenance_good": [
            "관리 좋",
            "관리 잘",
            "잔디 관리",
            "잔디 좋",
        ],
        "easy": [
            "쉬운 코스",
            "편한 코스",
            "초보",
        ],
        "green_fast": [
            "그린 빠",
            "빠른 그린",
        ],
        "facilities_good": [
            "시설 좋",
            "클럽하우스 좋",
        ],
    }

    return any(
        p in blob
        for p in phrases.get(
            trait,
            [],
        )
    )


def _recommendation_score(
    c,
    city=None,
    traits=None,
    budget=None,
    weekend=False,
    players=4,
):

    traits = traits or []

    score = 0
    reasons = []

    city_text = (
        f'{c.get("city","")} '
        f'{_best_address(c)}'
    )

    if (
        city
        and city in city_text
    ):
        score += 30
        reasons.append(
            f"{city} 지역 일치"
        )

    matched_traits = [
        t
        for t in traits
        if _trait_match(c, t)
    ]

    score += (
        len(matched_traits)
        * 28
    )

    trait_labels = {
        "fairway_wide":
            "넓은 페어웨이",

        "maintenance_good":
            "코스관리",

        "easy":
            "편한 코스",

        "green_fast":
            "빠른 그린",

        "facilities_good":
            "시설",
    }

    for t in matched_traits:

        reasons.append(
            f"{trait_labels.get(t,t)} "
            "조건 일치"
        )

    cost = estimate_per_person(
        c,
        weekend,
        players,
    )

    if cost is not None:

        score += 6

        if budget:

            gap = max(
                budget - cost,
                0,
            )

            score += min(
                gap / 10000,
                8,
            )

            reasons.append(
                f"예산 내 · "
                f"1인 약 {cost:,}원"
            )

        else:

            reasons.append(
                f"1인 예상 약 "
                f"{cost:,}원"
            )

    else:

        reasons.append(
            "요금 확인 필요"
        )

    fee = _legacy_fee(c)

    if fee.get("verified"):
        score += 2

    if _pricing_records(c):
        score += 2

    if (
        c.get("data_checked")
        or
        (
            c.get("verification")
            or {}
        ).get("checked_at")
    ):
        score += 1

    if _official_url(c):
        score += 1

    return score, reasons


# ============================================================
# SUBREGION
# ============================================================

def _subregion_match(
    club,
    subregion,
):

    if not subregion:
        return True

    text = " ".join(
        str(
            club.get(k)
            or ""
        )
        for k in (
            "subregion",
            "city",
            "region",
            "area",
            "name",
        )
    )

    aliases = {
        "경기남부": [
            "경기남부",
            "용인",
            "성남",
            "광주",
            "이천",
            "여주",
            "안성",
            "화성",
            "수원",
            "평택",
        ],

        "경기북부": [
            "경기북부",
            "가평",
            "포천",
            "양주",
            "파주",
            "고양",
            "남양주",
            "의정부",
        ],

        "충북": [
            "충북",
            "청주",
            "충주",
            "음성",
            "보은",
            "제천",
            "진천",
        ],

        "충남": [
            "충남",
            "천안",
            "아산",
            "공주",
            "당진",
            "태안",
            "대전",
            "세종",
        ],

        "강원영서": [
            "강원영서",
            "춘천",
            "원주",
            "홍천",
            "횡성",
        ],

        "강원영동": [
            "강원영동",
            "강릉",
            "속초",
            "고성",
            "동해",
            "삼척",
        ],

        "경북": [
            "경북",
            "대구",
            "경주",
            "포항",
            "구미",
        ],

        "경남": [
            "경남",
            "부산",
            "울산",
            "창원",
            "김해",
            "양산",
            "거제",
        ],

        "전북": [
            "전북",
            "전주",
            "익산",
            "군산",
        ],

        "전남": [
            "전남",
            "광주",
            "순천",
            "여수",
            "목포",
        ],

        "제주": [
            "제주",
            "서귀포",
        ],

        "서울": ["서울"],
        "인천": ["인천"],
    }

    return any(
        x in text
        for x in aliases.get(
            subregion,
            [subregion],
        )
    )


# ============================================================
# SERVICE ASSESSMENT
# ============================================================

def service_assessment(club):
    """
    checkpoint DB를 기준으로
    service / candidate / excluded 분류.

    중요:
    정보가 없다는 이유만으로 excluded 처리하지 않는다.
    """

    import math

    holes = known_holes(club)

    round_eligible = (
        is_round_eligible(club)
    )

    round_confirmed = (
        holes is not None
        and
        round_eligible
    )

    round_explicitly_bad = (
        not round_eligible
    )

    fee = _legacy_fee(club)

    actual_fee = any(
        isinstance(
            fee.get(k),
            (int, float),
        )
        and
        not isinstance(
            fee.get(k),
            bool,
        )
        and
        math.isfinite(
            fee[k]
        )
        and
        fee[k] >= 0

        for k in (
            "weekday_green",
            "weekend_green",
            "weekday",
            "weekend",
            "cart_team",
            "caddie_team",
            "three_person_weekday_extra",
            "three_person_weekend_extra",
        )
    )

    # checkpoint pricing도 실제 가격정보로 인정
    if _pricing_records(club):
        actual_fee = True

    homepage = bool(
        _official_url(club)
    )

    verification = (
        club.get("verification")
        or {}
    )

    public_data = (
        verification.get(
            "public_data"
        )
        or {}
    )

    public_matched = (
        public_data.get(
            "matched"
        )
        is True
    )

    public_operating = (
        public_data.get(
            "operating_in_public_data"
        )
    )

    public_status = str(
        public_data.get(
            "status"
        )
        or ""
    ).strip()

    public_detail = str(
        public_data.get(
            "detail_status"
        )
        or ""
    ).strip()

    closed_date = str(
        public_data.get(
            "closed_date"
        )
        or ""
    ).strip()

    if (
        public_operating is None
        and
        public_matched
    ):

        public_operating = (
            not closed_date
            and
            (
                public_status
                in {
                    "영업/정상",
                    "영업",
                }
                or
                public_detail
                == "영업"
            )
        )

    public_non_operating = (
        public_matched
        and
        (
            bool(closed_date)
            or
            public_operating
            is False
        )
    )

    trust = []

    if (
        club.get("data_source")
        == "official"
    ):
        trust.append(
            "official"
        )

    if homepage:
        trust.append(
            "official_homepage_record"
        )

    if _has_information(
        club.get("data_checked")
    ):
        trust.append(
            "data_checked_record"
        )

    if fee.get("verified") is True:
        trust.append(
            "verified_fee_record"
        )

    if _pricing_records(club):
        trust.append(
            "precision_pricing"
        )

    if _has_information(
        club.get("course_details")
    ):
        trust.append(
            "precision_course_details"
        )

    if public_matched:
        trust.append(
            "공공데이터"
        )

    if public_operating is True:
        trust.append(
            "공공데이터상 영업"
        )

    courses = (
        club.get("courses")
        or
        club.get("course_details")
    )

    basic_count = sum(
        (
            holes is not None,
            _has_information(
                _best_address(club)
            ),
            _has_information(
                club.get("phone")
            ),
            homepage,
            _has_information(
                courses
            ),
            actual_fee,
        )
    )

    if (
        public_non_operating
        or
        round_explicitly_bad
    ):
        status = "excluded"

    elif (
        round_confirmed
        and
        trust
        and
        basic_count >= 2
    ):
        status = "service"

    else:
        status = "candidate"

    return (
        status,
        trust,
        basic_count,
    )


def service_status(club):

    return service_assessment(
        club
    )[0]


def is_recommendable(club):
    """
    추천 가능 여부.
    실시간 예약 가능 여부를 뜻하지 않는다.
    """

    return (
        service_status(club)
        == "service"
    )


# ============================================================
# PREPARE SERVICE POOL
# ============================================================

def prepare_service_pool(clubs):

    from datetime import date

    enrich_search_regions(clubs)
    enrich_public_address_regions(
        clubs
    )

    for club in clubs:

        status, sources, count = (
            service_assessment(club)
        )

        club["service_status"] = (
            status
        )

        club["service_basic_count"] = (
            count
        )

        verification = (
            club.setdefault(
                "verification",
                {},
            )
        )

        previous_sources = (
            verification.get(
                "sources"
            )
            or []
        )

        if isinstance(
            previous_sources,
            str,
        ):
            previous_sources = [
                previous_sources
            ]

        if str(
            club.get(
                "pool_source"
            )
            or ""
        ).startswith("VWorld"):

            sources = [
                "VWorld"
            ] + sources

        verification["sources"] = list(
            dict.fromkeys(
                previous_sources
                + sources
            )
        )

        verification["status"] = (
            "verified"
            if status == "service"
            else
            "partial"
            if sources
            else
            "unverified"
        )

        verification.setdefault(
            "checked_at",
            club.get(
                "data_checked"
            )
            or
            (
                verification.get(
                    "public_data"
                )
                or {}
            ).get(
                "checked_at"
            )
            or
            club.get(
                "pool_checked"
            ),
        )

        verification[
            "assessed_at"
        ] = date.today().isoformat()

    return clubs


# ============================================================
# POOL COUNTS
# ============================================================

def pool_counts(clubs):

    from collections import Counter

    counts = Counter(
        c.get(
            "service_status"
        )
        or
        service_status(c)

        for c in clubs
    )

    return {
        "count":
            len(clubs),

        "service":
            counts["service"],

        "candidate":
            counts["candidate"],

        "excluded":
            counts["excluded"],

        "unclassified":
            sum(
                not c.get("area")
                for c in clubs
            ),
    }


# ============================================================
# OBJECTIVE CONDITIONS
# ============================================================

def _player_condition(
    club,
    players,
):
    """
    정밀 DB의 operations.players를 먼저 확인한다.
    None = 확인 필요
    """

    operations = _operations(club)

    player_info = (
        operations.get("players")
    )

    if not isinstance(
        player_info,
        dict,
    ):
        return None

    keys = {
        2: [
            "two_player",
            "2_player",
            "2p",
            "two",
        ],
        3: [
            "three_player",
            "3_player",
            "3p",
            "three",
        ],
        4: [
            "four_player",
            "4_player",
            "4p",
            "four",
        ],
    }

    for key in keys.get(
        players,
        [],
    ):

        if key in player_info:

            value = player_info[key]

            if isinstance(
                value,
                bool,
            ):
                return value

    return None


# ============================================================
# RECOMMENDATION POOL
# ============================================================

def recommendation_pool(
    clubs,
    area="전체",
    text="",
    budget=None,
    players=4,
    weekend=False,
    limit=6,
    offset=0,
    city=None,
    traits=None,
):
    """
    조건 적합 후보군 반환.

    unknown 정보는 자동 탈락시키지 않는다.
    명시적으로 불가인 경우만 제외한다.
    """

    traits = traits or []

    pool = [
        c
        for c in clubs
        if (
            area == "전체"
            or
            c.get("area")
            == area
        )
        and
        is_recommendable(c)
    ]

    if budget:

        filtered = []

        for c in pool:

            estimate = (
                estimate_per_person(
                    c,
                    weekend,
                    players,
                )
            )

            # 가격 미확인은 후보 유지
            if (
                estimate is None
                or
                estimate <= budget
            ):
                filtered.append(c)

        pool = filtered

    if players in (
        2,
        3,
    ):

        filtered = []

        for c in pool:

            condition = (
                _player_condition(
                    c,
                    players,
                )
            )

            # 명시적 False만 제외.
            # None(미확인)은 유지.
            if condition is not False:
                filtered.append(c)

        pool = filtered

    scored = []

    for c in pool:

        score, reasons = (
            _recommendation_score(
                c,
                city=city,
                traits=traits,
                budget=budget,
                weekend=weekend,
                players=players,
            )
        )

        scored.append(
            (
                score,
                c,
                reasons,
            )
        )

    scored.sort(
        key=lambda x: (
            -x[0],
            not bool(
                _pricing_records(
                    x[1]
                )
                or
                _legacy_fee(
                    x[1]
                ).get(
                    "verified"
                )
            ),
            x[1].get(
                "city",
                "",
            ),
            x[1].get(
                "name",
                "",
            ),
        )
    )

    if not scored:
        return []

    start = max(
        int(offset or 0),
        0,
    )

    if start >= len(scored):
        start = 0

    selected = scored[
        start:
        start + limit
    ]

    day = (
        "주말"
        if weekend
        else "주중"
    )

    result = []

    for score, c, reasons in selected:

        base = (
            f'{c.get("region","")} '
            f'{c.get("city","")} · '
            f'{day} {players}인'
        )

        display_reasons = (
            [base]
            + reasons[:3]
        )

        result.append(
            (
                c,
                display_reasons,
            )
        )

    return result


def recommend_clubs(
    clubs,
    area="전체",
    text="",
    budget=None,
    players=4,
    limit=6,
    weekend=False,
):

    cond = parse_ai_conditions(
        text,
        area,
        weekend,
        players,
        budget,
    )

    return recommendation_pool(
        clubs,
        cond["area"],
        text,
        cond["budget"],
        cond["players"],
        cond["weekend"],
        limit=limit,
        offset=0,
        city=cond.get(
            "city"
        ),
        traits=cond.get(
            "traits"
        ),
    )


# ============================================================
# COUNTS
# ============================================================

def catalog_count(clubs=None):

    clubs = (
        clubs
        or load_catalog()
    )

    return len(clubs)


def catalog_area_counts(
    clubs=None,
):

    clubs = (
        clubs
        or load_catalog()
    )

    out = {}

    for c in clubs:

        area = (
            c.get("area")
            or "기타"
        )

        out[area] = (
            out.get(
                area,
                0,
            )
            + 1
        )

    return out


# ============================================================
# DIAGNOSTIC
# ============================================================

if __name__ == "__main__":

    clubs = (
        load_service_catalog()
    )

    counts = pool_counts(
        clubs
    )

    db = load_active_db()

    print(
        "========================================"
    )
    print(
        " GOLF CATALOG STATUS"
    )
    print(
        "========================================"
    )

    print(
        f"DB: {db['file_name']}"
    )

    print(
        f"Precision DB: "
        f"{db['precision_db']}"
    )

    print(
        f"Records: {len(clubs)}"
    )

    print(
        f"Service: "
        f"{counts['service']}"
    )

    print(
        f"Candidate: "
        f"{counts['candidate']}"
    )

    print(
        f"Excluded: "
        f"{counts['excluded']}"
    )

    print(
        f"Unclassified: "
        f"{counts['unclassified']}"
    )

    print(
        "========================================"
    )