"""개발사업 1건의 상세 조회(읽기 전용). DB 스키마·RPC·권한을 바꾸지 않는다.

지도 목록 RPC는 면적·세대수·고시일을 내려주지 않는다. RPC를 바꾸지 않고(운영 DB 변경 없이),
구역을 골랐을 때만 기존 REST 읽기 경로로 1건을 읽어 목록과 같은 `present_project()`로 만든다.
그래서 목록과 상세가 같은 사업을 같게 말한다.

여기에는 쓰기가 없다. 사업 행·출처·변경 이력을 읽기만 하고, 값이 NULL이면 NULL로 남긴다.
"""
import copy
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from urllib.parse import urlsplit

from services import development as development
from services import development_geocode as geo
from services import development_notify as notify
from services import development_presentation as presentation
from services import development_stage as stage
from services import development_timeline as timeline
from services import realestate_monitor as rm

CACHE_SECONDS = 60
CACHE_LIMIT = 256
SIDE_LIMIT = 5
DEADLINE = 8.0

# 기능이 구현되면 이 상수가 바뀌고 connections가 함께 바뀐다. 별도의 '사용 가능' 플래그는 두지 않는다.
ZONE_TRADES_IMPLEMENTED = False
RIGHTS_ENGINE_IMPLEMENTED = False
LISTINGS_IMPLEMENTED = False
ZONE_TARGET_TYPES = ('아파트', '연립·다세대', '단독·다가구', '토지')

DETAIL_COLUMNS = ('project_id,project_name,project_type,sigungu,dong,address,stage,stage_raw,stage_mapping_version,'
                  'status,validation_status,location,geometry_verified,geometry_source,geometry_verified_at,'
                  'last_verified_at,area_m2,planned_units,planned_floor,planned_far,selected_date,notice_date,'
                  'source_date,official_authority,external_id,field_evidence,confidence_level,revision')
SOURCE_COLUMNS = ('source_id,source_name,source_url,is_official,collected_at,verified_at,validation_status,'
                  'document_title,published_at,effective_at')
UPDATE_COLUMNS = ('update_id,update_kind,previous_stage,new_stage,previous_status,new_status,from_revision,'
                  'to_revision,title,changed_fields,recorded_at,published_at,effective_at')

_UUID = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
_CACHE = {}
UNAVAILABLE_MESSAGE = '개발사업 정보를 지금 불러올 수 없어요. 잠시 후 다시 시도해 주세요.'


class DetailError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _default_fetch(table, params):
    return rm._remote_request('GET', table, params=params)


def _safe_url(value):
    """http(s) 형식의 호스트가 있는 링크만. 그 밖(javascript: 등)은 버린다. http도 버린다."""
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value)
    except ValueError:
        return None
    return value if parts.scheme == 'https' and parts.hostname and not parts.username else None


def _source_item(row):
    url = _safe_url(row.get('source_url'))
    return {'name': row.get('source_name'), 'url': url,
            # is_official 플래그만 믿지 않고 호스트로 다시 확인한다.
            'official': bool(url and stage.official_url(url)),
            'flagged_official': bool(row.get('is_official')),
            'collected_at': row.get('collected_at'), 'verified_at': row.get('verified_at'),
            'validation_status': row.get('validation_status'), 'document_title': row.get('document_title'),
            'published_at': row.get('published_at'), 'effective_at': row.get('effective_at')}


def _update_item(row):
    kind = row.get('update_kind')
    return {'update_kind': kind, 'kind_label': notify.TITLES.get(kind, '정비사업 정보 변경'),
            'previous_stage': row.get('previous_stage'), 'new_stage': row.get('new_stage'),
            'previous_status': row.get('previous_status'), 'new_status': row.get('new_status'),
            'changed_fields': list(row.get('changed_fields') or []),
            'recorded_at': row.get('recorded_at'), 'published_at': row.get('published_at'),
            'effective_at': row.get('effective_at')}


def connections_for(row, *, api_status, coordinate_provider):
    """실제 서버 설정·상수·이 사업의 경계 검증 여부로 계산한다. 구현되지 않은 기능은 사용 가능으로 말하지 않는다."""
    key = bool((api_status or {}).get('public_data_key'))
    linked = list(rm.TRADE_APIS.keys())
    verified = bool(row.get('geometry_verified'))
    if not verified:
        matching = 'BLOCKED_NO_VERIFIED_BOUNDARY'
    else:
        matching = 'AVAILABLE' if ZONE_TRADES_IMPLEMENTED else 'NOT_IMPLEMENTED'
    state = 'NOT_CONNECTED' if not key else ('CONNECTED' if ZONE_TRADES_IMPLEMENTED else 'REGIONAL_ONLY')
    return {
        'trades': {'state': state, 'api_key_configured': key, 'linked_types': linked,
                   'unlinked_types': [t for t in ZONE_TARGET_TYPES if t not in linked],
                   'zone_panel': 'IMPLEMENTED' if ZONE_TRADES_IMPLEMENTED else 'NOT_IMPLEMENTED',
                   'zone_matching': matching, 'coordinate_provider_configured': bool(coordinate_provider)},
        'rights_engine': {'state': 'CONNECTED' if RIGHTS_ENGINE_IMPLEMENTED else 'NOT_CONNECTED'},
        'listings': {'state': 'CONNECTED' if LISTINGS_IMPLEMENTED else 'NOT_CONNECTED'},
    }


def _coordinate_provider_configured():
    try:
        return geo.select_provider(rm._secret, geo.requests_get)['provider'] is not None
    except Exception:
        return False


def _gather(pid, fetch, deadline):
    """프로젝트·출처·이력을 병렬로 읽는다. 프로젝트가 안 오면 실패, 곁가지는 마감 시 unavailable."""
    jobs = {
        'project': ('development_projects', {'select': DETAIL_COLUMNS, 'project_id': 'eq.' + pid, 'limit': 1}),
        'sources': ('development_project_sources', {'select': SOURCE_COLUMNS, 'project_id': 'eq.' + pid,
                                                    'order': 'collected_at.desc.nullslast', 'limit': SIDE_LIMIT}),
        'updates': ('development_updates', {'select': UPDATE_COLUMNS, 'project_id': 'eq.' + pid,
                                            'order': 'recorded_at.desc', 'limit': SIDE_LIMIT}),
    }
    pool = ThreadPoolExecutor(max_workers=len(jobs))
    futures = {name: pool.submit(fetch, table, params) for name, (table, params) in jobs.items()}
    done, _ = wait(list(futures.values()), timeout=deadline)
    pool.shutdown(wait=False, cancel_futures=True)
    out = {}
    for name, future in futures.items():
        if future in done and future.exception() is None:
            out[name] = ('ok', future.result())
        else:
            out[name] = ('unavailable', None)
    return out


def _timeline(row, present):
    unknown = present['stage_guide']['stage'] == 'UNKNOWN'
    stage_block = present['stage']
    current = None if unknown else (stage_block.get('official_text') or stage_block.get('label'))
    official = present['official_source'] or {}
    return timeline.process_timeline(
        project_type=row.get('project_type'), program=present.get('program'),
        stage_history=present.get('stage_history'), current_official_stage=current,
        verified_level=present.get('stage_verified_level'),
        source={'name': official.get('name'), 'url': official.get('url'), 'fetched_at': present.get('last_checked')})


def _evict(cache, now):
    expired = [k for k, (t, _) in cache.items() if now - t >= CACHE_SECONDS]
    for key in expired:
        cache.pop(key, None)
    while len(cache) >= CACHE_LIMIT:
        cache.pop(min(cache, key=lambda k: cache[k][0]))


def project_detail(project_id, *, fetch=None, cache=None, remote=None, api_status=None,
                   coordinate_provider=None, clock=time.monotonic, deadline=DEADLINE):
    if not isinstance(project_id, str) or not _UUID.fullmatch(project_id):
        raise DetailError(422, 'INVALID_ID', '사업 번호 형식이 올바르지 않습니다.')
    pid = str(uuid.UUID(project_id))
    cache = _CACHE if cache is None else cache
    now = clock()
    hit = cache.get(pid)
    if hit and now - hit[0] < CACHE_SECONDS:
        return copy.deepcopy(hit[1])
    if not (rm._using_remote_db() if remote is None else remote):
        raise DetailError(503, 'NOT_CONFIGURED', UNAVAILABLE_MESSAGE)

    parts = _gather(pid, fetch or _default_fetch, deadline)
    state, rows = parts['project']
    if state != 'ok':
        raise DetailError(503, 'UNAVAILABLE', UNAVAILABLE_MESSAGE)
    if not rows:
        raise DetailError(404, 'NOT_FOUND', '해당 개발사업을 찾을 수 없습니다.')
    row = dict(rows[0])
    lon, lat = development._coordinates(row)
    present_row = dict(row, longitude=lon, latitude=lat, boundary=None)
    present = presentation.present_project(present_row)

    verified = bool(row.get('geometry_verified'))
    project = dict(present, facts={k: row.get(k) for k in (
        'area_m2', 'planned_units', 'planned_floor', 'planned_far', 'selected_date', 'notice_date',
        'source_date', 'official_authority', 'external_id')},
        boundary={'verified': verified, 'source': row.get('geometry_source') if verified else None,
                  'verified_at': row.get('geometry_verified_at') if verified else None})

    side = {}
    for name, items, convert in (('sources', parts['sources'], _source_item), ('updates', parts['updates'], _update_item)):
        side_state, side_rows = items
        side[name] = ({'state': 'ok', 'items': [convert(r) for r in (side_rows or [])[:SIDE_LIMIT]]}
                      if side_state == 'ok' else {'state': 'unavailable', 'items': []})
    collected = [i['collected_at'] for i in side['sources']['items'] if i['collected_at']]
    result = {
        'project': project,
        'process_timeline': _timeline(row, present),
        'sources': side['sources'], 'recent_updates': side['updates'],
        'provenance': {'last_verified_at': row.get('last_verified_at'),
                       'last_collected_at': max(collected) if collected else None,
                       'source_date': row.get('source_date'), 'notice_date': row.get('notice_date'),
                       'generated_at': datetime.now(timezone.utc).isoformat()},
        'connections': connections_for(
            row, api_status=rm.get_api_status() if api_status is None else api_status,
            coordinate_provider=_coordinate_provider_configured() if coordinate_provider is None else coordinate_provider),
    }
    if side['sources']['state'] == 'ok' and side['updates']['state'] == 'ok':
        _evict(cache, now)  # 일부만 성공한 결과는 캐시하지 않아 일시 장애 뒤에 바로 다시 읽는다.
        cache[pid] = (now, copy.deepcopy(result))
    return result
