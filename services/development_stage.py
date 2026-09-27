"""Read-only Seoul official stage extraction. No database or credential access."""
from datetime import date
import hashlib
import re
import json
from pathlib import Path
from functools import lru_cache
from urllib.parse import urljoin, urlsplit, parse_qs
from bs4 import BeautifulSoup
from services.development_official import compact, normalize_stage, now

VERSION = 'seoul-official-stage-v1'
HOST = 'cleanup.seoul.go.kr'

@lru_cache(maxsize=1)
def catalog():
    path = Path(__file__).with_name('development_stage_catalog.json')
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))['projects']

def observation(row):
    packaged = catalog().get(row.get('project_id'), {})
    stored = (row.get('field_evidence') or {}).get('official_stage') or {}
    details = [e for e in (stored, packaged) if stage_view(e)]
    # Preserve a more recent official observation already stored in the DB.
    detail = max(details, key=lambda e:e.get('fetched_at') or '', default=None)
    return detail, packaged.get('list_stage') or {}
DESCRIPTIONS = {
    'PLANNING': '정비사업의 기본 방향과 계획을 마련하는 단계입니다.',
    'SAFETY_DIAGNOSIS': '건축물의 안전성과 재건축 필요성을 검토하는 단계입니다.',
    'DESIGNATED': '정비사업을 추진할 공식 구역이 지정된 단계입니다.',
    'COMMITTEE': '조합 설립을 준비하는 주민 추진조직이 승인된 단계입니다.',
    'ASSOCIATION_APPROVED': '사업을 추진할 조합 설립이 인가된 단계입니다.',
    'IMPLEMENTATION_APPROVED': '건축계획을 포함한 사업시행계획이 승인된 단계입니다.',
    'MANAGEMENT_DISPOSITION': '조합원 분양과 권리배분 등을 정하는 관리처분계획이 인가된 단계입니다.',
    'DEMOLITION': '기존 건축물 철거에 관한 신고가 이루어진 단계입니다.',
    'CONSTRUCTION': '공사 착수에 관한 신고가 이루어진 단계입니다.',
    'SALES': '일반분양에 관한 승인 절차가 진행된 단계입니다.',
    'COMPLETED': '공사를 마치고 준공 인가를 받은 단계입니다.',
    'TRANSFER_NOTICE': '새 주택과 토지의 권리 이전을 고시하는 단계입니다.',
    'ASSOCIATION_DISSOLVED': '조합 해산 절차가 진행된 단계입니다.',
    'ASSOCIATION_LIQUIDATION': '조합의 잔여 재산과 채무 등을 정리하는 단계입니다.',
}

def official_url(url):
    p = urlsplit(url)
    return p.scheme == 'https' and p.hostname == HOST and not p.username and not p.password

def discover(html, url, expected_name):
    soup = BeautifulSoup(html, 'html.parser')
    # The alias page itself must identify the expected project, not a similarly named project.
    matched = compact(expected_name) in compact(soup.get_text(' ', strip=True))
    frame = soup.select_one('iframe#contentFrame')
    target = urljoin(url, frame.get('src', '')) if frame else None
    cafe_id = (parse_qs(urlsplit(target).query).get('cafeId') or [None])[0] if target else None
    return {'detail_page_matched': matched, 'cafe_id': cafe_id,
            'evidence_url': target if target and official_url(target) and cafe_id else None}

def parse_progress(html):
    soup = BeautifulSoup(html, 'html.parser')
    block = soup.select_one('.progress-cont')
    if block is None:
        return {'current_stage': None, 'milestones': [], 'evidence': None}
    marker = block.select_one('.progress .step')
    current = block.select_one('.progress p')
    current = current.get_text(' ', strip=True) if current and marker and compact(marker.text) == '현재단계' else None
    milestones = []
    for index, item in enumerate(block.select('li')):
        label = item.select_one('.txt')
        if not label:
            continue
        stage = label.get_text(' ', strip=True)
        raw_date = item.select_one('.date')
        raw_date = raw_date.get_text(' ', strip=True) if raw_date else None
        value = None
        match = re.fullmatch(r'(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\.?', raw_date or '')
        if match:
            try:
                value = date(*map(int, match.groups())).isoformat()
            except ValueError:
                pass
        elif re.fullmatch(r'\d{2}\.\d{2}\.\d{2}', raw_date or ''):
            # Preserve Seoul's two-digit year verbatim; never guess the century.
            try:
                _, month, day = map(int, raw_date.split('.'))
                date(2000, month, day)
                value = raw_date
            except ValueError:
                pass
        milestones.append({'stage_name': stage, 'stage_date': value, 'date_raw': raw_date,
                           'date_precision': 'SOURCE_SHORT_YEAR' if value and len(value) == 8 else 'ISO_DATE' if value else None,
                           'stage_order': index + 1, 'is_current': bool(current and compact(stage) == compact(current))})
    # A conflicting active marker is a layout/identity review, not an inferred current stage.
    active = [x.select_one('.txt').get_text(' ', strip=True) for x in block.select('li.active') if x.select_one('.txt')]
    if active and (not current or any(compact(x) != compact(current) for x in active)):
        current = None
        for item in milestones:
            item['is_current'] = False
    return {'current_stage': current, 'milestones': milestones, 'evidence': str(block)}

def collect(target, fetch):
    result = dict(target, parser_version=VERSION, fetched_at=now(), db_write=False,
                  current_stage=None, milestones=[], stage_verified_level='OFFICIAL_LIST_MAPPED')
    if not target.get('detail_url'):
        return dict(result, result_status='NO_DETAIL_IDENTIFIER')
    if not official_url(target['detail_url']):
        return dict(result, result_status='UNTRUSTED_URL')
    html = fetch(target['detail_url'])
    identity = discover(html, target['detail_url'], target['project_name'])
    result.update(identity)
    if not identity['detail_page_matched'] or not identity['evidence_url']:
        return dict(result, result_status='IDENTITY_OR_FRAME_UNRESOLVED')
    parsed = parse_progress(fetch(identity['evidence_url']))
    result.update(parsed)
    result['content_hash'] = hashlib.sha256((parsed['evidence'] or '').encode()).hexdigest()
    result['normalized_stage'] = normalize_stage(parsed['current_stage'])['normalized_stage']
    result['result_status'] = 'VERIFIED' if parsed['current_stage'] else 'NO_CURRENT_STAGE'
    if parsed['current_stage']:
        result['stage_verified_level'] = 'OFFICIAL_DETAIL_VERIFIED'
    return result

def stage_view(evidence):
    """Only an explicit detail observation with a source may override a list stage."""
    if not isinstance(evidence, dict) or evidence.get('stage_verified_level') != 'OFFICIAL_DETAIL_VERIFIED':
        return None
    if not evidence.get('current_stage') or not official_url(evidence.get('evidence_url') or '') or not evidence.get('content_hash'):
        return None
    milestones = evidence.get('milestones') or []
    stage = evidence['current_stage']
    index = next((i for i, m in enumerate(milestones) if m.get('is_current') and compact(m['stage_name']) == compact(stage)), None)
    return {'label': stage, 'description': DESCRIPTIONS.get(normalize_stage(stage)['normalized_stage']),
            'timeline': {'steps': [m['stage_name'] for m in milestones], 'current_index': index,
                         'current_label': stage, 'total': len(milestones), 'note': None,
                         'milestones': milestones}, 'evidence': evidence}
