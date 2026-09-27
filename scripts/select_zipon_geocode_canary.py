"""Pick the ten highest address-quality canonical projects for the geocode canary.

Runs before any provider call and writes data/development/geocode_canary_20260927.json.
The file carries only the six identity fields the canary is allowed to record; no
coordinate, no evidence, no credential.

Eligibility (all required, so nothing is geocoded on a guessed address):
  * already in the database (the canonical 130)
  * address_verified with address_type LOT and a plain 번지 (123 or 123-4)
  * the 동 came from the official address token, not from a program listing
  * exactly one original address on the record, so there is no address conflict
  * the address is unique among the 130, so a shared registry address cannot look
    like a duplicate-coordinate bug later

Selection from the eligible set: a per-district quota (강동구 4, 송파구 3, 서초구 3) filled
in project_id order, skipping a 동 already taken in that district. Distinct 동 spread is
what makes the duplicate-coordinate check meaningful and the bbox realistic.

신속통합기획(FAST_TRACK) records are absent by construction: none of them carries an
address, so none of them is geocodable at all.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_official import now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
CANARY_FILE = DATA / 'geocode_canary_20260927.json'
QUOTA = {'강동구': 4, '송파구': 3, '서초구': 3}
FIELDS = ('project_id', 'project_name', 'canonical_address', 'district', 'project_type', 'program')


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def in_database():
    ids = {p['project_id'] for p in load('db_baseline_20260927.json')['projects']}
    return ids | {i for b in load('bulk_import_result_20260927.json')['batches']
                  for i in b['project_ids']}


def rows():
    ids = in_database()
    out = []
    for project in load('pilot_canonical_verified_20260927.json')['projects']:
        project_id = project['raw']['candidate_ids'][0]
        if project_id not in ids:
            continue
        location, classification = project['location'], project['classification']
        out.append({'project_id': project_id,
                    'project_name': project['identity']['official_project_name'],
                    'canonical_address': location['representative_address'],
                    'district': location['district'],
                    'project_type': classification['canonical_project_type'],
                    'program': classification['program'],
                    'dong': location['dong'], 'lot_number': location['lot_number'],
                    'address_type': location['address_type'],
                    'address_verified': location['address_verified'],
                    'dong_source': location['dong_source'],
                    'address_count': len(location['original_addresses'] or [])})
    return out


def eligible(candidates):
    shared = {row['canonical_address'] for row in candidates
              if sum(1 for other in candidates
                     if other['canonical_address'] == row['canonical_address']) > 1}
    keep = []
    for row in candidates:
        if not (row['address_verified'] and row['address_type'] == 'LOT'
                and row['dong_source'] == 'OFFICIAL_ADDRESS_TOKEN'
                and row['address_count'] == 1 and row['district'] and row['dong']
                and row['lot_number'] and re.fullmatch(r'\d+(?:-\d+)?', row['lot_number'])
                and row['canonical_address'] not in shared):
            continue
        keep.append(row)
    return keep


def select(candidates):
    """Per-district quota in project_id order, one project per 동."""
    chosen, seen = [], set()
    for district, quota in QUOTA.items():
        picked = 0
        for row in sorted((r for r in candidates if r['district'] == district),
                          key=lambda r: r['project_id']):
            if picked >= quota or (district, row['dong']) in seen:
                continue
            seen.add((district, row['dong']))
            chosen.append(row)
            picked += 1
    return chosen


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true', help='write the canary file (otherwise print only)')
    args = ap.parse_args()

    candidates = rows()
    pool = eligible(candidates)
    chosen = select(pool)
    document = {
        'format': 'zipon-geocode-canary-v1', 'generated_at': now(), 'db_write': False,
        'source': 'data/development/pilot_canonical_verified_20260927.json',
        'selected_from': {'canonical_in_database': len(candidates), 'eligible': len(pool)},
        'quota': QUOTA,
        'rule': ['already in the database',
                 'address_verified with address_type LOT and a plain 번지',
                 '동 taken from the official address token',
                 'exactly one original address on the record',
                 'the address is unique among the canonical rows in the database',
                 'per-district quota filled in project_id order, one project per 동'],
        'note': ('신속통합기획(FAST_TRACK) 기록은 주소가 없어 구조적으로 제외된다. '
                 '이 파일에는 좌표도, 증거도, 자격증명도 담지 않는다.'),
        'mix': {'districts': {d: sum(1 for r in chosen if r['district'] == d) for d in QUOTA},
                'project_types': {t: sum(1 for r in chosen if r['project_type'] == t)
                                  for t in sorted({r['project_type'] for r in chosen})},
                'distinct_dong': len({(r['district'], r['dong']) for r in chosen}),
                'sub_lot_addresses': sum(1 for r in chosen if '-' in r['lot_number'])},
        'items': [{field: row[field] for field in FIELDS} for row in chosen]}
    if args.write:
        CANARY_FILE.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n',
                               encoding='utf-8')
    print(json.dumps({'selected': len(document['items']), 'mix': document['mix'],
                      'eligible': len(pool), 'written': bool(args.write),
                      'file': str(CANARY_FILE.relative_to(ROOT))}, ensure_ascii=False))
    for row in document['items']:
        print(f"  {row['district']:6s} {row['project_type']:16s} "
              f"{row['canonical_address']:32s} {row['project_name'][:40]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
