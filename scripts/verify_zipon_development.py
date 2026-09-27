"""Official verification sprint for the ZIP:ON development pilot.

Offline by default. --fetch-official attempts one cached GET per official
identity; a denied or dropped host is recorded and not retried. No database
write, no migration, no import is performed by this script.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_geocode as geo
from services.development_official import DetailCache, detail_target, official_read
from services.development_verify import build, manifest, report

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
CACHE = DATA / 'cache'
PROJECT_REF = 'nnxtkvjpzqqhjlgnprzo'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha256(path)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fetch-official', action='store_true',
                    help='attempt the official detail read (one request per identity, cached)')
    ap.add_argument('--geocode', action='store_true',
                    help='use the VWorld provider if VWORLD_API_KEY/VWORLD_DOMAIN are configured')
    args = ap.parse_args()

    pilot_path = DATA / 'pilot_20260927.json'
    inputs = {name: {'path': f'data/development/{name}', 'sha256': sha256(DATA / name)}
              for name in ('pilot_20260927.json', 'pilot_canonical_20260927.json',
                           'pilot_duplicate_review_20260927.json', 'canary_20260927.json')}
    records = load(pilot_path)['records']
    canary = load(DATA / 'canary_20260927.json')['records']
    previous = load(DATA / 'pilot_canonical_20260927.json')
    pairs = load(DATA / 'pilot_duplicate_review_20260927.json')['pairs']
    inputs['candidates'] = len(records)
    inputs['previous_canonical_projects'] = len(previous['projects'])
    inputs['probable_duplicate_pairs'] = len(pairs)

    detail_cache = DetailCache(CACHE / 'official_detail')
    failures = []
    if args.fetch_official:
        import requests
        fetched = official_read(records, requests.get, detail_cache)
    else:
        fetched = {'details': {}, 'log': [], 'host_state': {}, 'discovery': {},
                   'stats': {'requests': 0, 'cache_hits': 0, 'duplicates_avoided': 0}}
    unique_targets = {t['cache_key'] for t in (detail_target(r) for r in records)}
    discovery = fetched.get('discovery') or {}
    detail_stats = dict(fetched['stats'], unique_official_identities=len(unique_targets),
                        candidates=len(records),
                        official_pages_requested=sum(1 for e in discovery.values()
                                                     if e.get('result_status') in ('FETCHED', 'FETCH_FAILED'))
                                                 + fetched['stats']['requests'],
                        official_pages_fetched=sum(1 for e in discovery.values()
                                                   if e.get('result_status') == 'FETCHED'),
                        detail_pages_fetched=sum(1 for e in fetched['log']
                                                 if e.get('result_status') == 'FETCHED'),
                        duplicate_requests_avoided=len(records) - len(unique_targets)
                        + fetched['stats']['duplicates_avoided']
                        + sum(1 for e in discovery.values()
                              if e.get('result_status') == 'SKIPPED_HOST_UNAVAILABLE')
                        + sum(1 for e in fetched['log']
                              if e.get('result_status') in ('SKIPPED_HOST_UNAVAILABLE', 'DEDUPED_IN_RUN')),
                        cache_directory='data/development/cache/official_detail',
                        cache_entries=len(list((CACHE / 'official_detail').glob('*.json'))),
                        list_page_discovery={url: {'result_status': entry.get('result_status'),
                                                   'detail_endpoint_confirmed':
                                                       bool((entry.get('detail_endpoint') or {}).get('confirmed')),
                                                   'error_type': (entry.get('evidence') or {}).get('error_type')}
                                             for url, entry in (fetched.get('discovery') or {}).items()})
    for host, state in fetched['host_state'].items():
        failures.append({'source': host, 'url': f'https://{host}/', 'failure_reason': state['reason'],
                         'observed_at': state['observed_at'],
                         'retry_recommendation': 'allow the host in the environment network policy, then rerun '
                                                 'scripts/verify_zipon_development.py --fetch-official'})
    for run in load(pilot_path)['runs']:
        if run['status'] == 'FAILED':
            failures.append({'source': run['source'], 'url': run['source_url'],
                             'failure_reason': ','.join(run['errors']) or 'UNKNOWN',
                             'observed_at': run['finished_at'],
                             'retry_recommendation': 'no confirmed alternative official endpoint; recollect '
                                                     'once the host answers. Counts are never substituted.'})

    geocode_cache = geo.GeocodeCache(CACHE / 'geocode')
    from services.config import get_secret  # local config only; nothing is written back
    key, domain = str(get_secret('VWORLD_API_KEY') or ''), str(get_secret('VWORLD_DOMAIN') or '')
    provider = None
    if key and args.geocode:
        import requests

        def http_get(url, params=None, timeout=10):
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        provider = geo.vworld_provider(key, domain, http_get)
    else:
        failures.append({'source': 'geocoder', 'url': 'https://api.vworld.kr/req/address',
                         'failure_reason': 'VWORLD_API_KEY_NOT_CONFIGURED' if not key
                                           else 'GEOCODE_NETWORK_RUN_NOT_REQUESTED',
                         'observed_at': None,
                         'retry_recommendation': 'reuse the VWorld credentials this project already uses for '
                                                 'golf (no new paid API), allow api.vworld.kr in the network '
                                                 'policy, then rerun with --geocode'})
    addresses = [r['address'] for r in records if r.get('address')]
    geocoded = geo.resolve(addresses, geocode_cache, provider)
    geocode_stats = dict(geocoded['stats'], unique_normalized_addresses=len(geocoded['results']),
                         addresses_submitted=len(addresses),
                         provider_configured=bool(provider),
                         cache_directory='data/development/cache/geocode')

    projects, resolved = build(records, canary, previous, pairs, fetched['details'], geocoded['results'])
    plan = manifest(projects, project_ref=PROJECT_REF)
    summary = report(projects, resolved, inputs=inputs, detail_stats=detail_stats,
                     geocode_stats=geocode_stats, failures=failures)
    summary['import'] = plan['totals']
    summary['official_detail_log'] = fetched['log'][:20]

    written = [
        write(DATA / 'pilot_canonical_verified_20260927.json',
              {'format': 'zipon-canonical-v2', 'generated_at': summary['generated_at'],
               'db_write': False, 'source_inputs': inputs, 'projects': projects}),
        write(DATA / 'pilot_duplicate_resolved_20260927.json',
              {'format': 'zipon-duplicate-resolution-v1', 'generated_at': summary['generated_at'],
               'policy': ['SAME_PROJECT requires a shared official identifier or an official detail read',
                          'name similarity alone never merges',
                          'zone/phase, district and representative-lot differences keep projects separate'],
               'totals': summary['identity'], 'pairs': resolved}),
        write(DATA / 'pilot_verification_report_20260927.json', summary),
        write(DATA / 'import_manifest_verified_20260927.json', plan),
    ]
    assert sha256(pilot_path) == inputs['pilot_20260927.json']['sha256'], 'raw pilot must not change'
    summary['files'] = written
    print(json.dumps({k: summary[k] for k in ('identity', 'quality_state', 'stage', 'status', 'address',
                                              'geocoding', 'boundary', 'official_cache', 'import')},
                     ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    main()
