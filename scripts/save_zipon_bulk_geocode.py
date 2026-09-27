"""Turn a production bulk-geocode response into the three repository artifacts.

The bulk geocode runs on the Space, because that is where the NAVER credential is.
This script takes the saved JSON of GET /api/realestate/geocode/bulk?aggregate=true
and writes the result, review and apply-ready files. It writes nothing to the
database and it refuses a response that carries anything credential-shaped.

  python scripts/save_zipon_bulk_geocode.py response.json            # check only
  python scripts/save_zipon_bulk_geocode.py response.json --write    # write the three files
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_bulk_geocode import ARTIFACT_FIELDS, BULK_VERSION
from services.development_official import now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
RESULT_FILE = DATA / 'bulk_geocode_result_20260927.json'
REVIEW_FILE = DATA / 'bulk_geocode_review_20260927.json'
APPLY_FILE = DATA / 'geocode_apply_ready_20260927.json'
# 자격증명 모양. 하나라도 걸리면 저장하지 않는다.
FORBIDDEN = (re.compile(r'sb_secret_[A-Za-z0-9_-]{10,}'), re.compile(r'eyJ[A-Za-z0-9_-]{30,}'),
             re.compile(r'(?i)x-ncp-apigw-api-key'), re.compile(r'(?i)client_secret'))


class Rejected(Exception):
    pass


def check(response):
    """형식과 불변식을 먼저 본다. 어긋나면 파일을 만들지 않는다."""
    if response.get('format') != BULK_VERSION:
        raise Rejected('UNEXPECTED_FORMAT_' + str(response.get('format')))
    if response.get('db_write') is not False:
        raise Rejected('RESPONSE_CLAIMS_A_DATABASE_WRITE')
    for pattern in FORBIDDEN:
        if pattern.search(json.dumps(response, ensure_ascii=False)):
            raise Rejected('RESPONSE_CONTAINS_A_CREDENTIAL_SHAPED_VALUE')
    artifact = (response.get('artifact') or {}).get('items') or []
    if not artifact:
        raise Rejected('NO_ARTIFACT_ROWS')
    if list((response.get('artifact') or {}).get('fields') or []) != list(ARTIFACT_FIELDS):
        raise Rejected('ARTIFACT_FIELDS_CHANGED')
    outcomes = {row['outcome'] for row in artifact}
    unknown = outcomes - {'ACCEPTED', 'REVIEW_REQUIRED', 'FAILED', 'PENDING_PROVIDER'}
    if unknown:
        raise Rejected('UNKNOWN_OUTCOME_' + ','.join(sorted(unknown)))
    accepted_ids = {row['project_id'] for row in artifact if row['outcome'] == 'ACCEPTED'}
    apply_items = (response.get('apply_ready') or {}).get('items') or []
    apply_ids = {row['project_id'] for row in apply_items}
    if apply_ids - accepted_ids:
        raise Rejected('APPLY_READY_CONTAINS_A_ROW_THAT_IS_NOT_ACCEPTED')
    review_ids = {row['project_id'] for row in (response.get('review') or {}).get('items') or []}
    if review_ids & apply_ids:
        raise Rejected('APPLY_READY_CONTAINS_A_REVIEW_ROW')
    for row in artifact:
        if row['outcome'] != 'ACCEPTED' and (row['longitude'] is not None
                                             or row['latitude'] is not None):
            raise Rejected('A_NON_ACCEPTED_ROW_CARRIES_A_COORDINATE')
    return {'artifact': len(artifact), 'accepted': len(accepted_ids),
            'review': len(review_ids), 'apply_ready': len(apply_ids)}


def documents(response):
    common = {'generated_at': now(), 'db_write': False, 'source': BULK_VERSION,
              'provider': response.get('provider'),
              'target_total': response.get('target_total'), 'scope': response.get('scope')}
    result = dict(common, format='zipon-bulk-geocode-result-v1',
                  totals=response.get('totals'), sanity=response.get('sanity'),
                  map_readiness=response.get('map_readiness'),
                  policy=response.get('policy'),
                  fields=list(ARTIFACT_FIELDS),
                  items=(response.get('artifact') or {}).get('items') or [])
    review = dict(common, format='zipon-bulk-geocode-review-v1',
                  note='자동 선택하지 않는다. 사람이 공식 주소와 NAVER 후보를 비교한다.',
                  items=(response.get('review') or {}).get('items') or [])
    apply_ready = dict(response.get('apply_ready') or {}, generated_at=now())
    return result, review, apply_ready


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('response', type=Path, help='saved JSON of the aggregate bulk response')
    ap.add_argument('--write', action='store_true', help='write the three artifact files')
    args = ap.parse_args()
    response = json.loads(args.response.read_text(encoding='utf-8'))
    try:
        counts = check(response)
    except Rejected as rejected:
        print(json.dumps({'written': False, 'rejected': rejected.args[0]}, ensure_ascii=False))
        return 1
    result, review, apply_ready = documents(response)
    if args.write:
        RESULT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        REVIEW_FILE.write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
        APPLY_FILE.write_text(json.dumps(apply_ready, ensure_ascii=False, indent=2) + '\n',
                              encoding='utf-8')
    print(json.dumps({'written': bool(args.write), 'counts': counts, 'db_write': False,
                      'files': [str(f.relative_to(ROOT)) for f in
                                (RESULT_FILE, REVIEW_FILE, APPLY_FILE)]}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
