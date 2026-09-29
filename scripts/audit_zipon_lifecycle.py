"""130건의 사업 생애주기를 공식 근거로 감사한다. DB write 없음.

  python scripts/audit_zipon_lifecycle.py          # 결과를 화면에만
  python scripts/audit_zipon_lifecycle.py --write  # 검토 산출물로 저장

판정 규칙(추측하지 않는다):
  * 공식 종결 단계(준공인가·이전고시)만 COMPLETED다.
  * 착공/공사중은 COMPLETED가 아니다. CONSTRUCTION으로 둔다.
  * 조합해산·청산처럼 끝났을 수도 있는 단계는 COMPLETED로 올리지 않는다.
    가설만 적고 REVIEW_REQUIRED로 남긴다.
  * 사업명이 오래돼 보인다거나 목록에 없다는 이유로 완료라고 하지 않는다.
  * 판정 근거가 없으면 UNKNOWN이며, UNKNOWN은 기본 지도에서 숨기지 않는다.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_official import STATUS_FROM_STAGE, STATUS_HYPOTHESIS, now
from services.development_presentation import DEFAULT_LIFECYCLES, LIFECYCLE_LABELS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
RESULT_FILE = DATA / 'lifecycle_audit_20260929.json'
# 이 단계들은 끝났을 수도 있지만 공식 종결 고시가 아니다. 사람이 확인할 일로 남긴다.
NEEDS_REVIEW_HYPOTHESES = ('COMPLETED_PROBABLE_POST_TRANSFER', 'AMBIGUOUS_COMPLETED_OR_CANCELLED')


def stored_projects():
    canonical = json.loads((DATA / 'pilot_canonical_verified_20260927.json')
                           .read_text(encoding='utf-8'))['projects']
    baseline = json.loads((DATA / 'db_baseline_20260927.json').read_text(encoding='utf-8'))['projects']
    bulk = json.loads((DATA / 'bulk_import_result_20260927.json').read_text(encoding='utf-8'))
    stored = {p['project_id'] for p in baseline} | {i for b in bulk['batches'] for i in b['project_ids']}
    return [p for p in canonical if p['raw']['candidate_ids'][0] in stored]


def judge(project):
    """한 사업의 생애주기 후보와 그 근거."""
    progress = project.get('progress') or {}
    status = project.get('status') or {}
    stage = progress.get('normalized_stage')
    hypothesis = status.get('status_hypothesis') or STATUS_HYPOTHESIS.get(stage)
    if STATUS_FROM_STAGE.get(stage):
        candidate, confidence, reason = 'COMPLETED', 'OFFICIAL_TERMINAL_STAGE', '공식 종결 단계입니다.'
    elif stage == 'CONSTRUCTION':
        candidate, confidence, reason = ('CONSTRUCTION', 'OFFICIAL_STAGE',
                                         '착공 단계입니다. 완료가 아닙니다.')
    elif hypothesis in NEEDS_REVIEW_HYPOTHESES:
        candidate, confidence, reason = ('UNKNOWN', 'HYPOTHESIS_ONLY',
                                         '끝났을 수 있으나 공식 종결 고시가 확인되지 않았습니다.')
    elif stage and stage != 'UNKNOWN':
        candidate, confidence, reason = ('UNKNOWN', 'STAGE_WITHOUT_TERMINAL_EVIDENCE',
                                         '진행 단계는 있으나 종결 근거가 없습니다.')
    else:
        candidate, confidence, reason = ('UNKNOWN', 'NO_STAGE_EVIDENCE',
                                         '공식 단계 정보가 없습니다.')
    review = candidate == 'UNKNOWN' and confidence == 'HYPOTHESIS_ONLY'
    return candidate, confidence, reason, review, hypothesis, stage


def audit():
    rows = []
    for project in stored_projects():
        candidate, confidence, reason, review, hypothesis, stage = judge(project)
        status = project.get('status') or {}
        rows.append({
            'project_id': project['raw']['candidate_ids'][0],
            'project_name': project['identity']['official_project_name'],
            'district': project['location']['district'],
            'current_stage': stage,
            'lifecycle_candidate': candidate,
            'lifecycle_label': LIFECYCLE_LABELS[candidate],
            'in_default_map': candidate in DEFAULT_LIFECYCLES,
            'evidence': reason,
            'evidence_date': (project.get('dates') or {}).get('stage_date_raw'),
            'official_source_url': status.get('status_source_url')
            or (project.get('provenance') or {}).get('source_url'),
            'confidence': confidence,
            'status_hypothesis': hypothesis,
            'review_required': review,
            'reason': reason,
        })
    counts = {}
    for row in rows:
        counts[row['lifecycle_candidate']] = counts.get(row['lifecycle_candidate'], 0) + 1
    return {
        'format': 'zipon-lifecycle-audit-v1', 'generated_at': now(),
        'db_write': False, 'bulk_update_applied': False,
        'rule': '공식 종결 단계(준공인가·이전고시)만 COMPLETED. 착공은 완료가 아니다. '
                '이름이나 오래됨을 근거로 완료라고 하지 않는다. 애매하면 UNKNOWN.',
        'default_lifecycles': list(DEFAULT_LIFECYCLES),
        'totals': dict(counts, projects=len(rows),
                       review_required=sum(1 for r in rows if r['review_required']),
                       hidden_from_default_map=sum(1 for r in rows if not r['in_default_map'])),
        'items': rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args()
    report = audit()
    if args.write:
        RESULT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
    print(json.dumps({'totals': report['totals'], 'db_write': False,
                      'written': bool(args.write)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
