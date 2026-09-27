"""실거래(국토교통부) 주소를 개발사업과 같은 규칙으로 좌표로 바꾼다.

provider도 판정 기준도 services/development_geocode.py 것을 그대로 쓴다. 실거래는
개발사업 주변 영향을 보기 위한 기준점이므로, 개발사업보다 느슨하게 붙이면 엉뚱한
사업구역과 묶인다. 그래서 여기서도 단일 정확 일치만 좌표가 되고 나머지는 좌표 없이
남는다. 좌표가 없는 실거래는 지도에 찍히지 않고 "위치 확인 필요"로 남는 편이 맞다.

MOLIT canonical_address에는 시도·자치구가 없어서(예: '천호동 423-1') 그대로 검색하면
다른 구의 같은 이름 주소에 붙는다. region_label을 붙여 전체 주소를 만든 뒤에만 조회한다.
"""
from services import development_geocode as geo

TRADE_ADDRESS_FIELDS = ('canonical_address', 'address_jibun', 'address_road')


def full_address(trade):
    """실거래 항목에서 시도·자치구가 포함된 전체 주소를 만든다. 못 만들면 None."""
    label = str((trade or {}).get('region_label') or '').replace('>', ' ')
    tail = next((str(trade.get(field)).strip() for field in TRADE_ADDRESS_FIELDS
                 if (trade or {}).get(field)), '')
    if not label.strip() or not tail:
        return None
    address = geo.normalize_address(label + ' ' + tail)
    parts = geo.wanted_parts(address)
    if not parts['district']:
        # 자치구를 모르면 동 이름만으로 좌표를 붙이지 않는다.
        return None
    return address


def resolve_trades(trades, cache, get_secret, http_get=None, preferred=None):
    """실거래 목록의 주소를 한 번씩만 조회하고, 검증된 좌표만 붙여서 돌려준다.

    자격증명이 없으면 호출하지 않고 좌표 없는 목록을 그대로 돌려준다. 요금이 드는
    호출이므로 캐시가 먼저이고, 같은 주소는 목록 안에서 한 번만 조회한다.
    """
    selected = geo.select_provider(get_secret, http_get or geo.requests_get, preferred)
    planned = [(trade, full_address(trade)) for trade in trades or []]
    resolved = geo.resolve([address for _, address in planned if address], cache,
                           selected['provider'])
    rows, located = [], 0
    for trade, address in planned:
        row = dict(trade)
        entry = resolved['results'].get(geo.cache_key(address)) if address else None
        row['geocode_address'] = address
        row['geocode_status'] = (entry or {}).get('geocode_confidence',
                                                  'NO_ADDRESS' if not address else 'UNRESOLVED')
        row['geocode_source'] = (entry or {}).get('geocode_source')
        if entry and entry.get('coordinate_verified'):
            row['latitude'] = entry['latitude']
            row['longitude'] = entry['longitude']
            row['coordinate_verified'] = True
            row['matched_address'] = entry.get('matched_address')
            located += 1
        else:
            row['coordinate_verified'] = False
        rows.append(row)
    return {'items': rows, 'provider': selected['name'], 'blocker': selected['blocker'],
            'total': len(rows), 'located': located,
            'stats': resolved['stats'], 'db_write': False}
