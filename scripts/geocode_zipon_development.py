"""Geocode ZIP:ON development addresses. Dry run by default, no database write.

Reuses services/development_geocode.py: one provider call per normalized address,
provider priority NAVER -> Kakao -> VWorld, and a coordinate is accepted only for a
single candidate whose addressElements still carry 서울특별시, the 자치구, the 동 and
the 번지 we asked for. Anything else becomes GEOCODE_REVIEW_REQUIRED, a provider
error becomes GEOCODE_FAILED, and without credentials the run still produces a
pending queue instead of failing.

  python scripts/geocode_zipon_development.py --check-config          # credentials only, no HTTP
  python scripts/geocode_zipon_development.py --check-connectivity    # one sample address, no data
  python scripts/geocode_zipon_development.py --dry-run               # queue only, no provider call
  python scripts/geocode_zipon_development.py --live                  # call the provider

--live still writes nothing to the database; scripts/apply_zipon_geocode.py is the
separate step that does. No credential value is printed, cached or stored.
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
                     'canonical_address': geo.normalize_address(address),
                     'normalized_address': geo.normalize_address(address),
                     'cache_key': geo.cache_key(address)})
    return sorted(rows, key=lambda r: (not r['in_database'], r['project_id']))


def provider_for(preferred, live):
    """Configured credentials only. Nothing is printed and nothing is stored."""
    from services.config import get_secret

    selected = geo.select_provider(get_secret, geo.requests_get, preferred)
    if not live:
        blocker = ('PROVIDER_RUN_NOT_REQUESTED' if selected['provider']
                   else selected['blocker'])
        return None, selected, blocker
    return selected['provider'], selected, selected['blocker']


def report(rows, resolved, selected, blocker, provider_used, preferred):
    """TOTAL / ACCEPTED / GEOCODE_REVIEW_REQUIRED / FAILED / PENDING plus every accepted row."""
    for row in rows:
        entry = resolved['results'].get(row['cache_key']) or {}
        confidence = entry.get('geocode_confidence', 'UNRESOLVED')
        row['geocode_status'] = ('GEOCODE_FAILED' if entry.get('error_type')
                                else STATUS.get(confidence, 'GEOCODE_REVIEW_REQUIRED'))
        row['coordinate_verified'] = bool(entry.get('coordinate_verified'))
        row['geocode_confidence'] = confidence
        row['review_reason'] = entry.get('review_reason')
        for field in ('latitude', 'longitude', 'geocode_source', 'geocoded_at',
                      'provider_candidate_count', 'matched_address', 'road_address',
                      'jibun_address', 'english_address', 'distance_m',
                      'coordinate_orientation', 'address_elements', 'endpoint'):
            row[field] = entry.get(field)
    counts = {}
    for row in rows:
        counts[row['geocode_status']] = counts.get(row['geocode_status'], 0) + 1
    accepted = [{'project_id': r['project_id'], 'canonical_address': r['canonical_address'],
                 'latitude': r['latitude'], 'longitude': r['longitude'],
                 'matched_address': r['matched_address'],
                 'geocode_confidence': r['geocode_confidence'],
                 'geocode_source': r['geocode_source'], 'district': r['district'],
                 'accuracy': (resolved['results'].get(r['cache_key']) or {}).get('accuracy')}
                for r in rows if r['geocode_status'] == 'ACCEPTED']
    return {'format': 'zipon-geocode-queue-v1', 'generated_at': now(), 'db_write': False,
            'provider': selected['name'] or preferred, 'provider_requested': preferred,
            'provider_priority': list(selected['priority']),
            'provider_configured': bool(provider_used), 'blocker': blocker,
            'provider_availability': selected['availability'],
            'provider_skipped': selected['skipped'],
            'policy': ['provider priority NAVER -> Kakao -> VWorld',
                       'one provider call per normalized address',
                       'NAVER x is the longitude and y is the latitude; the axes are never swapped',
                       'a coordinate is accepted only for a single exact 서울·자치구·동·번지 match',
                       'a 동 or 구 centroid response is never accepted as a representative point',
                       'ambiguous results stay GEOCODE_REVIEW_REQUIRED and carry no coordinate',
                       'cache rows match the Supabase geocode_cache columns',
                       'this runner never writes to the database'],
            'totals': {'candidates': len(rows),
                       'unique_normalized_addresses': len(resolved['results']),
                       'accepted': counts.get('ACCEPTED', 0),
                       'review_required': counts.get('GEOCODE_REVIEW_REQUIRED', 0),
                       'failed': counts.get('GEOCODE_FAILED', 0),
                       'pending_provider': counts.get('PENDING_PROVIDER', 0)},
            'provider_stats': resolved['stats'], 'accepted': accepted, 'items': rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--check-config', action='store_true',
                      help='report which provider is configured; no HTTP request')
    mode.add_argument('--check-connectivity', action='store_true',
                      help='one harmless sample address; confirms auth and the x/y axis order')
    mode.add_argument('--dry-run', action='store_true',
                      help='build the queue without calling the provider (default)')
    mode.add_argument('--live', action='store_true',
                      help='call the configured provider; still zero database writes')
    ap.add_argument('--provider', default=None, choices=sorted(geo.PROVIDER_SPECS),
                    help='force one provider instead of the NAVER -> Kakao -> VWorld priority')
    args = ap.parse_args()
    from services.config import get_secret

    if args.check_config:
        print(json.dumps(geo.status(get_secret, preferred=args.provider),
                         ensure_ascii=False, indent=2))
        return 0
    if args.check_connectivity:
        print(json.dumps(geo.status(get_secret, geo.requests_get, geo.SAMPLE_ADDRESS,
                                    preferred=args.provider), ensure_ascii=False, indent=2))
        return 0

    rows = candidates()
    cache = geo.GeocodeCache(CACHE_DIR)
    provider, selected, blocker = provider_for(args.provider, args.live)
    resolved = geo.resolve([r['address'] for r in rows], cache, provider)
    queue = report(rows, resolved, selected, blocker, provider, args.provider)
    QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'mode': 'LIVE' if args.live else 'DRY_RUN', 'db_write': False,
                      'provider': queue['provider'], 'blocker': blocker,
                      'total': queue['totals']['candidates'],
                      'accepted': queue['totals']['accepted'],
                      'review_required': queue['totals']['review_required'],
                      'failed': queue['totals']['failed'],
                      'pending': queue['totals']['pending_provider'],
                      'available': {k: v['configured']
                                    for k, v in queue['provider_availability'].items()},
                      'file': str(QUEUE_FILE.relative_to(ROOT))}, ensure_ascii=False))
    for row in queue['accepted'][:20]:
        print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
