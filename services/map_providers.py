"""Basemap providers for ZIP:ON. Kept separate from the geocoder providers.

OpenStreetMap needs no key and already carries Korean labels for Korea, so it is
the working default. Kakao / NAVER / VWorld read better for Korean addresses and
POIs, but their web SDKs need a map key that the browser itself must load, which
is a separate decision from the server-side service role key. Until such a key is
configured on purpose, those providers are listed as options and nothing is
shipped to the browser.
"""

PROVIDERS = {
    'osm': {
        'label': 'OpenStreetMap',
        'kind': 'raster_tiles',
        'url_template': 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        'attribution': '© OpenStreetMap contributors',
        'max_zoom': 19,
        'korean_labels': True,
        'requires_browser_key': False,
        'secret': None,
        'note': '키 없이 사용할 수 있는 기본 지도입니다.',
    },
    'vworld': {
        'label': '브이월드 (국토교통부)',
        'kind': 'raster_tiles',
        'url_template': 'https://api.vworld.kr/req/wmts/1.0.0/{key}/Base/{z}/{y}/{x}.png',
        'attribution': '© 국토교통부 브이월드',
        'max_zoom': 19,
        'korean_labels': True,
        'requires_browser_key': True,
        'secret': 'VWORLD_MAP_KEY',
        'note': '공공 지도. 타일 요청에 브라우저로 전달되는 지도 키가 필요합니다.',
    },
    'kakao': {
        'label': '카카오맵',
        'kind': 'js_sdk',
        'url_template': None,
        'attribution': '© Kakao',
        'max_zoom': 19,
        'korean_labels': True,
        'requires_browser_key': True,
        'secret': 'KAKAO_JAVASCRIPT_KEY',
        'note': '한글 주소·POI 가독성이 가장 좋지만 JavaScript 지도 키가 브라우저에 노출됩니다.',
    },
    'naver': {
        'label': '네이버 지도',
        'kind': 'js_sdk',
        'url_template': None,
        'attribution': '© NAVER',
        'max_zoom': 19,
        'korean_labels': True,
        'requires_browser_key': True,
        'secret': 'NAVER_MAP_CLIENT_ID',
        'note': '한글 표기가 좋습니다. 지도 Client ID가 브라우저에 노출되며 도메인 등록이 필요합니다.',
    },
}
FALLBACK = 'osm'


def config(get_secret):
    """어떤 basemap을 쓸 수 있는지. 키 값은 절대 담지 않는다."""
    options = []
    for name, spec in PROVIDERS.items():
        configured = not spec['requires_browser_key'] or bool(
            str(get_secret(spec['secret']) or '').strip() if spec['secret'] else '')
        options.append({'id': name, 'label': spec['label'], 'kind': spec['kind'],
                        'korean_labels': spec['korean_labels'],
                        'requires_browser_key': spec['requires_browser_key'],
                        'configured': configured, 'note': spec['note'],
                        'url_template': spec['url_template'] if name == FALLBACK else None,
                        'attribution': spec['attribution'], 'max_zoom': spec['max_zoom']})
    active = next((o for o in options if o['configured'] and o['korean_labels']
                   and o['id'] != FALLBACK), None)
    chosen = active['id'] if active and active['kind'] == 'raster_tiles' else FALLBACK
    return {'active': chosen, 'fallback': FALLBACK, 'providers': options,
            'tile': {'url_template': PROVIDERS[chosen]['url_template'],
                     'attribution': PROVIDERS[chosen]['attribution'],
                     'max_zoom': PROVIDERS[chosen]['max_zoom']},
            'note': '한글 표기가 더 좋은 지도를 쓰려면 브라우저용 지도 키를 따로 등록해야 합니다.'}
