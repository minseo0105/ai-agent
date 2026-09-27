"""Auto-resolve what can be resolved among the quarantined development candidates.

Offline and evidence-only. Nothing is merged and nothing is deleted: the two
directions available without the official detail pages are

  1. an address supplement, when the official 구역명 is itself a lot ("천호동 392-9"),
     which the list row already states; and
  2. a DIFFERENT_PROJECT finding, when official evidence separates two candidates
     (different zone/phase tokens, different dong, or different representative lot).

SAME_PROJECT is never concluded here, so the canary pair 마천2 / 마천2재정비촉진구역
stays untouched. A candidate is AUTO_RESOLVED only once every bulk-import gate
passes with the supplemented evidence.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_identity import program_identities
from services.development_official import compact, dong_from_address, lot_number, normalize_stage
from services.development_quality import tokens
from services.development_official import now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
OUTPUT = DATA / 'quarantine_resolution_20260927.json'
LOT_SHAPED_NAME = re.compile(r'[가-힣]+(동|가|리)\s*\d')


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def supplement_address(record):
    """A 구역명 that is a lot is an official representative address, not a guess."""
    name = (record.get('project_name') or '').strip()
    if record.get('address') or not LOT_SHAPED_NAME.match(name):
        return None
    return {'address': f"서울특별시 {record['sigungu']} {name}",
            'address_type': 'LOT', 'address_source': '공식 목록 구역명(지번 표기)',
            'address_source_url': (record.get('source') or {}).get('source_url'),
            'basis': 'OFFICIAL_LIST_ZONE_NAME_IS_A_LOT'}


def separation(left, right):
    """Official evidence that two candidates are different projects."""
    if compact(left['district']) != compact(right['district']):
        return 'OFFICIAL_DISTRICT_MISMATCH'
    left_tokens, right_tokens = set(tokens(left['name'])), set(tokens(right['name']))
    # A registry name carries the lot as well as the zone ("천호동 214-19…(천호 3-1구역)"),
    # so a larger token set is not a different zone. Only a genuine conflict separates.
    if left_tokens and right_tokens and not (left_tokens <= right_tokens or right_tokens <= left_tokens):
        return 'OFFICIAL_ZONE_OR_PHASE_MISMATCH'
    if left['dong'] and right['dong'] and compact(left['dong']) != compact(right['dong']):
        return 'OFFICIAL_DONG_MISMATCH'
    if left['lot'] and right['lot'] and left['lot'] != right['lot']:
        return 'OFFICIAL_REPRESENTATIVE_LOT_MISMATCH'
    return None


def view(record, supplement):
    address = (supplement or {}).get('address') or record.get('address')
    return {'project_id': record['project_id'], 'name': record.get('project_name'),
            'district': record.get('sigungu'), 'address': address,
            'dong': dong_from_address(address, record.get('sigungu')),
            'lot': lot_number(address), 'external_id': record.get('external_id'),
            'stage_raw': record.get('stage_raw')}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    quarantine = load('bulk_import_quarantine_20260927.json')['items']
    canonical = load('pilot_canonical_verified_20260927.json')['projects']
    raw = {r['project_id']: r for r in load('pilot_20260927.json')['records']}
    pairs = load('pilot_duplicate_resolved_20260927.json')['pairs']
    identities = program_identities(canonical)
    by_id = {p['raw']['candidate_ids'][0]: p for p in canonical}

    supplements = {pid: supplement_address(record) for pid, record in raw.items()}
    views = {pid: view(record, supplements.get(pid)) for pid, record in raw.items()}

    # Re-decide the probable-duplicate pairs with the supplemented addresses.
    pair_findings = []
    resolved_pairs = {}
    for pair in pairs:
        left, right = (views[pid] for pid in pair['candidate_ids'])
        basis = separation(left, right)
        finding = {'candidate_ids': pair['candidate_ids'], 'names': pair['names'],
                   'previous_decision': pair['decision'],
                   'decision': 'DIFFERENT_PROJECT' if basis else 'STILL_AMBIGUOUS',
                   'basis': [basis] if basis else ['OFFICIAL_DETAIL_READ_REQUIRED'],
                   'evidence': [{k: side[k] for k in ('project_id', 'name', 'district', 'dong',
                                                      'lot', 'address', 'external_id')}
                                for side in (left, right)],
                   'address_supplemented': [pid for pid in pair['candidate_ids']
                                            if supplements.get(pid)]}
        pair_findings.append(finding)
        resolved_pairs[tuple(sorted(pair['candidate_ids']))] = finding['decision']

    # Re-evaluate latent program/registry name overlap with the same evidence.
    overlap_findings = []
    overlap_resolved = {}
    program_rows = {pid: v for pid, v in views.items()
                    if not (by_id.get(pid) or {}).get('classification', {}).get('official_registry_row', True)}
    for pid, item in ((q['project_id'], q) for q in quarantine):
        if 'LATENT_PROGRAM_IDENTITY_OVERLAP' not in item['reasons']:
            continue
        registry = views[pid]
        name = compact(registry['name'])
        matches = [other for other, side in program_rows.items()
                   if side['district'] == registry['district']
                   and compact(side['name']) and compact(side['name']) in name
                   and compact(side['name']) != name]
        bases = {other: separation(registry, program_rows[other]) for other in matches}
        decided = all(bases.values()) and bool(bases)
        overlap_findings.append({'project_id': pid, 'name': registry['name'],
                                 'overlaps': [{'project_id': other, 'name': program_rows[other]['name'],
                                               'basis': bases[other] or 'OFFICIAL_DETAIL_READ_REQUIRED'}
                                              for other in matches],
                                 'decision': 'DIFFERENT_PROJECT' if decided else 'STILL_AMBIGUOUS'})
        overlap_resolved[pid] = decided

    auto, review = [], []
    for item in quarantine:
        pid = item['project_id']
        record = raw[pid]
        supplement = supplements.get(pid)
        remaining = []
        for reason in item['reasons']:
            if reason == 'NO_OFFICIAL_ADDRESS' and supplement:
                continue
            if reason == 'IDENTITY_NOT_SETTLED' and all(
                    decision == 'DIFFERENT_PROJECT'
                    for key, decision in resolved_pairs.items() if pid in key):
                continue
            if reason == 'LATENT_PROGRAM_IDENTITY_OVERLAP' and overlap_resolved.get(pid):
                continue
            if reason == 'QUALITY_STATE_NEEDS_REVIEW':
                # Derived from the gates below; recomputed rather than trusted.
                continue
            remaining.append(reason)
        if not record.get('external_id'):
            remaining.append('NO_OFFICIAL_EXTERNAL_ID')
        if not ((supplement or {}).get('address') or record.get('address')):
            remaining.append('NO_OFFICIAL_ADDRESS')
        if normalize_stage(record.get('stage_raw'))['normalized_stage'] == 'UNKNOWN':
            remaining.append('STAGE_NOT_OFFICIALLY_MAPPED')
        entry = {'project_id': pid, 'project_name': record.get('project_name'),
                 'district': record.get('sigungu'),
                 'previous_reasons': item['reasons'],
                 'address_supplement': supplement,
                 'remaining_reasons': sorted(set(remaining))}
        (review if entry['remaining_reasons'] else auto).append(entry)

    payload = {'format': 'zipon-quarantine-resolution-v1', 'generated_at': now(), 'db_write': False,
               'policy': ['evidence only: address supplement and DIFFERENT_PROJECT findings',
                          'SAME_PROJECT is never concluded here and nothing is merged or deleted',
                          'auto resolved candidates still go through the normal bulk import gates'],
               'totals': {'quarantined': len(quarantine), 'auto_resolved': len(auto),
                          'still_review_required': len(review),
                          'address_supplements': sum(1 for s in supplements.values() if s),
                          'pairs_resolved_different': sum(1 for f in pair_findings
                                                          if f['decision'] == 'DIFFERENT_PROJECT'),
                          'pairs_still_ambiguous': sum(1 for f in pair_findings
                                                       if f['decision'] == 'STILL_AMBIGUOUS'),
                          'overlaps_resolved_different': sum(1 for f in overlap_findings
                                                             if f['decision'] == 'DIFFERENT_PROJECT')},
               'auto_resolved': sorted(auto, key=lambda e: e['project_id']),
               'still_review_required': sorted(review, key=lambda e: e['project_id']),
               'pair_findings': pair_findings, 'overlap_findings': overlap_findings}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload['totals'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
