"""단계 근거가 약한 사업을 근거와 함께 정리한다. DB write 없음, 네트워크 호출 없음.

두 가지를 본다.
  1) 공식 상세로 승격되지 않은 목록 전용(OFFICIAL_LIST_MAPPED) 사업
  2) 단계는 있으나 날짜 근거가 없는 사업

이미 받아 둔 공식 상세 수집 결과만 읽는다. 상세 페이지가 있다는 것만으로 승격하지
않는다. 사업명·공식 ID·자치구·유형이 같은 사업임이 확인될 때만 승격 후보다.
두 자리 연도나 의미가 불분명한 날짜는 해석하지 않고 그대로 남긴다.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_official import compact, now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
OUTPUT = DATA / 'stage_evidence_review_20260928.json'
# 네 자리 연도만 확실하다. '15.12.16' 같은 두 자리 연도는 세기를 추정하지 않는다.
FULL_DATE = re.compile(r'^(19|20)\d{2}[-.]\d{1,2}[-.]\d{1,2}$')


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def date_status(value):
    text = str(value or '').strip()
    if not text:
        return 'MISSING'
    if FULL_DATE.match(text):
        return 'VERIFIED'
    return 'AMBIGUOUS_NOT_INTERPRETED'


def promotion(record, canonical):
    """상세 페이지가 정말 같은 사업인지. 아니면 승격하지 않는다."""
    checks = {
        'detail_url_present': bool(record.get('detail_url')),
        'detail_page_matched': record.get('detail_page_matched') is True,
        'external_id_matches': bool(record.get('external_id'))
                               and record.get('external_id') == canonical['identity']['official_external_id'],
        'name_matches': compact(record.get('project_name') or '')
                        == compact(canonical['identity']['official_project_name']),
        'current_stage_extracted': bool(record.get('current_stage')),
        'official_host': str(record.get('detail_url') or '').startswith('https://cleanup.seoul.go.kr/'),
    }
    if all(checks.values()):
        return 'PROMOTE_TO_DETAIL_VERIFIED', 'HIGH', checks
    if not checks['detail_url_present']:
        return 'NO_OFFICIAL_DETAIL_URL', 'LOW', checks
    if not checks['detail_page_matched']:
        return 'DETAIL_PAGE_DID_NOT_MATCH', 'LOW', checks
    if not checks['current_stage_extracted']:
        return 'DETAIL_HAS_NO_STAGE', 'LOW', checks
    return 'MANUAL_REVIEW', 'LOW', checks


def build():
    replay = load('production_stage_replay_20260927.json')
    official = {p['project_id']: p for p in load('official_stage_result_20260927.json')['projects']}
    canonical = {p['raw']['candidate_ids'][0]: p
                 for p in load('pilot_canonical_verified_20260927.json')['projects']}
    list_only, dates, ambiguous_only = [], [], []
    for row in replay['rows']:
        project_id = row['project_id']
        record = official.get(project_id) or {}
        project = canonical.get(project_id)
        if project is None:
            continue
        milestones = record.get('milestones') or []
        dated = [m for m in milestones if date_status(m.get('stage_date')) == 'VERIFIED']
        ambiguous = [m for m in milestones
                     if date_status(m.get('stage_date')) == 'AMBIGUOUS_NOT_INTERPRETED']
        if row.get('level') == 'OFFICIAL_LIST_MAPPED':
            action, confidence, checks = promotion(record, project)
            list_only.append({
                'project_id': project_id,
                'project_name': project['identity']['official_project_name'],
                'district': project['location']['district'],
                'project_type': project['classification']['canonical_project_type'],
                'current_stage_label': (row.get('stage') or {}).get('label'),
                'official_list_url': project['progress']['stage_source_url'],
                'official_detail_url': record.get('detail_url'),
                'detail_page_matched': record.get('detail_page_matched'),
                'detail_current_stage': record.get('current_stage'),
                'identity_checks': checks,
                'recommended_action': action, 'confidence': confidence})
        # 운영의 '날짜 근거 114건'은 값이 있는 milestone을 가진 사업을 센 것이다. 그 값 대부분은
        # 두 자리 연도라 우리가 해석하지 않을 뿐, 근거가 없는 것은 아니다. 둘을 구분해 센다.
        has_any_date = bool(dated or ambiguous)
        if not has_any_date:
            dates.append({
                'project_id': project_id,
                'project_name': project['identity']['official_project_name'],
                'district': project['location']['district'],
                'project_type': project['classification']['canonical_project_type'],
                'current_stage_label': (row.get('stage') or {}).get('label'),
                'official_detail_url': record.get('detail_url'),
                'milestones_found': len(milestones),
                'milestones': [{'stage_name': m.get('stage_name'),
                                'raw_value': m.get('stage_date'),
                                'normalized_value': (m.get('stage_date')
                                                     if date_status(m.get('stage_date')) == 'VERIFIED'
                                                     else None),
                                'verification_status': date_status(m.get('stage_date')),
                                'source_label': record.get('official_source'),
                                'official_url': record.get('detail_url')}
                               for m in milestones],
                'ambiguous_dates': len(ambiguous),
                'recommended_action': 'NEEDS_OFFICIAL_DETAIL_DATE',
                'confidence': 'LOW',
                'reason': '공식 상세에서 날짜가 있는 milestone을 찾지 못했습니다.'})
        elif not dated:
            ambiguous_only.append({
                'project_id': project_id,
                'project_name': project['identity']['official_project_name'],
                'district': project['location']['district'],
                'official_detail_url': record.get('detail_url'),
                'milestones_found': len(milestones),
                'ambiguous_dates': len(ambiguous),
                'sample_raw_value': ambiguous[0].get('stage_date') if ambiguous else None,
                'recommended_action': 'KEEP_RAW_DO_NOT_INTERPRET',
                'confidence': 'MEDIUM',
                'reason': ('공식 상세의 날짜가 두 자리 연도라 세기를 확정할 수 없습니다. '
                           '원문 그대로 보관하고 해석하지 않습니다.')})
    return list_only, dates, ambiguous_only


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    list_only, dates, ambiguous_only = build()
    promote = sum(1 for r in list_only if r['recommended_action'] == 'PROMOTE_TO_DETAIL_VERIFIED')
    counts = {}
    for row in list_only:
        counts[row['recommended_action']] = counts.get(row['recommended_action'], 0) + 1
    document = {'format': 'zipon-stage-evidence-review-v1', 'generated_at': now(),
                'db_write': False, 'network_called': False,
                'note': ('상세 페이지가 있다는 것만으로 승격하지 않습니다. 두 자리 연도는 '
                         '세기를 추정하지 않고 원문 그대로 둡니다.'),
                'totals': {'list_only': len(list_only), 'promotable': promote,
                           'by_action': counts, 'date_evidence_missing': len(dates),
                           'date_evidence_present': 130 - len(dates),
                           'ambiguous_year_only': len(ambiguous_only),
                           'fully_verified_dates': 130 - len(dates) - len(ambiguous_only)},
                'list_only_projects': list_only, 'date_gap_projects': dates,
                'ambiguous_date_projects': ambiguous_only}
    if args.write:
        OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n',
                          encoding='utf-8')
    print(json.dumps(document['totals'], ensure_ascii=False))
    for row in list_only:
        print(f"  LIST_ONLY {row['recommended_action']:28s} {row['district']:5s} {row['project_name'][:32]:34s} "
              f"detail={'Y' if row['official_detail_url'] else 'N'} matched={row['detail_page_matched']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
