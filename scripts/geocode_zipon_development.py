"""Geocode ZIP:ON development addresses. Dry run by default, no database write.

Reuses services/development_geocode.py: one provider call per normalized address,
and a coordinate is accepted only for a single exact candidate whose returned
address still carries the district and the lot we asked for. Anything else becomes
GEOCODE_REVIEW_REQUIRED, a provider error becomes GEOCODE_FAILED, and without
credentials the run still produces a pending queue.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_geocode as geo
from services.development_official import now

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
QUEUE_FILE = DATA / 'geocode_queue_20260927.json'
CACHE_DIR = DATA / 'cache/geocode'
STATUS = {'EXACT': 'ACCEPTED', 'GEOCODE_REVIEW': 'GEOCODE_REVIEW_REQUIRED',
          'UNRESOLVED': 'PENDING_PROVIDER'}


def load(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))


def candidates():
    """Projects with an official address, newest evidence first. Deduped by address."""
    projects = load('pilot_canonical_verified_20260927.json')['projects']
    in_db = {p['project_id'] for p in load('db_baseline_20260927.json')['projects']}
    in_db |= {r['project_id'] for b in load('bulk_import_plan_20260927.json')['batches']
              for r in b['candidates']}
    rows = []
    for project in projects:
        address = project['location']['representative_address']
        if not address:
            continue
        rows.append({'project_id': project['raw']['candidate_ids'][0],
                     'canonical_id': project['canonical_id'],
                     'project_name': project['identity']['official_project_name'],
                     'district': project['location']['district'],
                     'address': address, 'in_database': project['raw']['candidate_ids'][0] in in_db,
                     'normalized_address': geo.normalize_address(address),
                     'cache_key': geo.cache_key(address)})
    return sorted(rows, key=lambda r: (not r['in_database'], r['project_id']))


def provider_for(name, enabled):
    """Configured credentials only. Nothing is printed and nothing is stored."""
    from services.config import get_secret

    def http_get(url, params=None, headers=None, timeout=10):
        import requests
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()

    availability = geo.provider_availability(get_secret)
    if not enabled:
        ready = [key for key, value in availability.items() if value['configured']]
        return None, availability, ('PROVIDER_RUN_NOT_REQUESTED' if ready
                                   else 'NO_GEOCODER_CREDENTIAL_CONFIGURED')
    provider, blocker = geo.build_provider(name, get_secret, http_get)
    return provider, availability, blocker


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true',
                    help='call the configured provider (otherwise the queue stays pending)')
    ap.add_argument('--provider', default='vworld', choices=sorted(geo.PROVIDER_SPECS),
                    help='geocoder to use when --apply is given')
    args = ap.parse_args()

    rows = candidates()
    cache = geo.GeocodeCache(CACHE_DIR)
    provider, availability, blocker = provider_for(args.provider, args.apply)
    resolved = geo.resolve([r['address'] for r in rows], cache, provider)

    for row in rows:
        entry = resolved['results'].get(row['cache_key']) or {}
        confidence = entry.get('geocode_confidence', 'UNRESOLVED')
        row['geocode_status'] = ('GEOCODE_FAILED' if entry.get('error_type')
                                else STATUS.get(confidence, 'GEOCODE_REVIEW_REQUIRED'))
        row['coordinate_verified'] = bool(entry.get('coordinate_verified'))
        for field in ('latitude', 'longitude', 'geocode_source', 'geocoded_at',
                      'provider_candidate_count'):
            row[field] = entry.get(field)
    counts = {}
    for row in rows:
        counts[row['geocode_status']] = counts.get(row['geocode_status'], 0) + 1

    queue = {'format': 'zipon-geocode-queue-v1', 'generated_at': now(), 'db_write': False,
             'provider': args.provider, 'provider_configured': bool(provider),
             'blocker': blocker, 'provider_availability': availability,
             'policy': ['one provider call per normalized address',
                        'a coordinate is accepted only for a single exact district and lot match',
                        'ambiguous results stay GEOCODE_REVIEW_REQUIRED and carry no coordinate',
                        'cache rows match the Supabase geocode_cache columns'],
             'totals': {'candidates': len(rows),
                        'unique_normalized_addresses': len(resolved['results']),
                        'accepted': counts.get('ACCEPTED', 0),
                        'review_required': counts.get('GEOCODE_REVIEW_REQUIRED', 0),
                        'failed': counts.get('GEOCODE_FAILED', 0),
                        'pending_provider': counts.get('PENDING_PROVIDER', 0)},
             'provider_stats': resolved['stats'], 'items': rows}
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'totals': queue['totals'], 'provider': args.provider,
                      'provider_configured': queue['provider_configured'], 'blocker': blocker,
                      'available': {k: v['configured'] for k, v in availability.items()},
                      'file': str(QUEUE_FILE.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
