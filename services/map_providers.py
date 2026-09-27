"""Basemap providers for ZIP:ON. Kept separate from the geocoder providers.

OpenStreetMap needs no key and already carries Korean labels for Korea, so it is
the working default. Kakao / NAVER / VWorld read better for Korean addresses and
POIs, but their web SDKs need a map key that the browser itself must load, which
is a separate decision from the server-side service role key. Until such a key is
configured on purpose, those providers are listed as options and nothing is
shipped to the browser.

NAVER Dynamic Map은 웹 지도 SDK이므로 Client ID가 브라우저 요청에 실린다. 이것은
구조적으로 피할 수 없고, 그래서 NAVER 콘솔의 Web 서비스 URL 등록(도메인 제한)이 실제
보호 장치다. 반대로 Client Secret은 지오코딩 서버 호출에만 쓰이며 어떤 경우에도
브라우저로 내려가지 않는다. 그 구분을 코드로 남겨 두기 위해 basemap 항목은 브라우저에
노출될 수 있는 키 이름(browser_key_name)을 적고, 서버 전용 키는 SERVER_ONLY_SECRETS에
따로 모아 둔다.
"""

# NAVER 콘솔에 등록해야 하는 Web 서비스 URL. 여기 없는 도메인에서는 지도가 뜨지 않는다.
NAVER_WEB_SERVICE_URL = 'https://minseo2-digital-ai-lab.hf.space'
# Dynamic Map v3 로더. 브라우저가 직접 불러야 하므로 Client ID가 이 URL에 실린다.
NAVER_MAPS_SCRIPT = 'https://oapi.map.naver.com/openapi/v3/maps.js'
# 신 콘솔은 ncpKeyId, 구 콘솔은 ncpClientId를 쓴다. 어느 쪽인지 브라우저에서 확인할 수
# 있게 둘 다 내려주고, 스크립트 로드가 실패하면 예비 이름으로 한 번 더 시도한다.
NAVER_MAPS_KEY_PARAM = 'ncpKeyId'
NAVER_MAPS_KEY_PARAM_FALLBACK = 'ncpClientId'
# 절대 브라우저로 내려가지 않는 키. config()는 값이 아니라 이름만 담는다.
SERVER_ONLY_SECRETS = ('NAVER_MAP_CLIENT_SECRET', 'KAKAO_REST_API_KEY', 'VWORLD_API_KEY')

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
        'web_service_url': NAVER_WEB_SERVICE_URL,
        'note': ('한글 표기가 좋습니다. 웹 지도 SDK라 Client ID는 브라우저에 노출될 수밖에 없고, '
                 'NAVER 콘솔에 Web 서비스 URL을 등록해 도메인으로 제한합니다. '
                 'Client Secret은 서버 지오코딩 전용이며 브라우저로 내려가지 않습니다.'),
    },
}
FALLBACK = 'osm'


def sdk_config(get_secret):
    """NAVER Dynamic Map을 브라우저에서 띄우기 위한 설정.

    지도 Client ID는 웹 지도 SDK 요청에 실리므로 브라우저에 내려갈 수밖에 없다. 그것이
    이 함수가 있는 이유이고, 보호 장치는 NAVER 콘솔의 Web 서비스 URL 등록이다.
    SERVER_ONLY_SECRETS(특히 NAVER_MAP_CLIENT_SECRET)는 여기에 절대 담지 않는다.
    """
    client_id = str(get_secret('NAVER_MAP_CLIENT_ID') or '').strip()
    # 운영자가 콘솔 세대에 맞춰 이름만 바꿔 끼울 수 있게 해 둔다.
    key_param = str(get_secret('NAVER_MAP_KEY_PARAM') or '').strip() or NAVER_MAPS_KEY_PARAM
    fallback = (NAVER_MAPS_KEY_PARAM_FALLBACK if key_param != NAVER_MAPS_KEY_PARAM_FALLBACK
                else NAVER_MAPS_KEY_PARAM)
    return {'provider': 'naver', 'configured': bool(client_id),
            'client_id': client_id or None, 'script_url': NAVER_MAPS_SCRIPT,
            'key_param': key_param, 'key_param_fallback': fallback,
            'web_service_url': NAVER_WEB_SERVICE_URL,
            'note': ('지도 Client ID는 브라우저에 노출되며 Web 서비스 URL 등록으로 제한됩니다.'
                     if client_id else
                     '지도 Client ID가 등록되지 않아 NAVER 지도를 띄울 수 없습니다.')}


def config(get_secret):
    """어떤 basemap을 쓸 수 있는지. 서버 전용 키 값은 절대 담지 않는다.

    예외는 하나뿐이다: NAVER 지도 Client ID는 브라우저가 SDK를 부를 때 필요한 값이라
    sdk에 담아 내려준다. 그 외의 키는 이름만 나온다.
    """
    options = []
    for name, spec in PROVIDERS.items():
        configured = not spec['requires_browser_key'] or bool(
            str(get_secret(spec['secret']) or '').strip() if spec['secret'] else '')
        options.append({'id': name, 'label': spec['label'], 'kind': spec['kind'],
                        'korean_labels': spec['korean_labels'],
                        'requires_browser_key': spec['requires_browser_key'],
                        'configured': configured, 'note': spec['note'],
                        'url_template': spec['url_template'] if name == FALLBACK else None,
                        'attribution': spec['attribution'], 'max_zoom': spec['max_zoom'],
                        'browser_key_name': spec['secret'],
                        'web_service_url': spec.get('web_service_url')})
    active = next((o for o in options if o['configured'] and o['korean_labels']
                   and o['id'] != FALLBACK), None)
    chosen = active['id'] if active and active['kind'] == 'raster_tiles' else FALLBACK
    sdk = sdk_config(get_secret)
    # Dynamic Map이 준비되면 그것이 기본 지도다. 준비되지 않으면 raster 선택으로 남는다.
    if sdk['configured']:
        chosen = 'naver'
    return {'active': chosen, 'fallback': FALLBACK, 'providers': options, 'sdk': sdk,
            'tile': {'url_template': PROVIDERS[chosen]['url_template'],
                     'attribution': PROVIDERS[chosen]['attribution'],
                     'max_zoom': PROVIDERS[chosen]['max_zoom']},
            'note': '한글 표기가 더 좋은 지도를 쓰려면 브라우저용 지도 키를 따로 등록해야 합니다.',
            'browser_exposure': {
                'exposed_key_kind': 'map client id only',
                'protected_by': 'NAVER 콘솔 Web 서비스 URL 등록(도메인 제한)',
                'web_service_url': NAVER_WEB_SERVICE_URL,
                'never_sent_to_browser': list(SERVER_ONLY_SECRETS)}}
