"""서울 25개 수집 결과의 주소를 좌표로 바꾼다. DB에 쓰지 않는다.

  python scripts/geocode_zipon_seoul25.py --input data/development/seoul25_raw_20261001.json --check-config
  python scripts/geocode_zipon_seoul25.py --input ... --dry-run     # provider 호출 없음
  python scripts/geocode_zipon_seoul25.py --input ... --live --out data/development/seoul25_geocode_20261001.json

새 geocoder를 만들지 않습니다. services/development_geocode.py를 그대로 씁니다 —
provider 우선순위 NAVER -> Kakao -> VWorld, 정규화 주소 1건당 provider 호출 1회,
파일 캐시(data/development/cache/geocode) 재사용, 후보가 여럿이면 채택하지 않음.

그 위에 자치구 검증을 한 겹 더 합니다. 사업의 district와 지오코딩이 답한 자치구가
다르면 좌표를 버립니다. 좌표가 없는 사업 때문에 실행이 실패하지는 않습니다 —
해당 사업은 좌표 없이 목록에만 남습니다.

집계: geocoded / failed / sigungu_mismatch / unverifiable
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_collector as dc
from services import development_geocode as geo
from services.config import get_secret

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / 'data/development/cache/geocode'


def verdict(record, evaluation):
    """이 결과를 이 사업의 좌표로 쓸 수 있는지. 쓸 수 없으면 왜인지."""
    if not evaluation:
        return 'failed', ['NO_GEOCODE_RESULT']
    confidence = evaluation.get('geocode_confidence')
    if confidence != 'EXACT' or not evaluation.get('coordinate_verified'):
        reason = evaluation.get('review_reason') or evaluation.get('error_type') or confidence
        bucket = 'unverifiable' if confidence == 'GEOCODE_REVIEW' else 'failed'
        return bucket, [str(reason or 'UNRESOLVED')]
    # 기존 수집기의 검증 계약을 그대로 통과시킨다. 자치구 비교가 여기 들어 있다.
    flat = {'result_status': 'MATCHED', 'accuracy': evaluation.get('accuracy'),
            'longitude': evaluation.get('longitude'), 'latitude': evaluation.get('latitude'),
            'source_url': evaluation.get('geocode_source') or evaluation.get('endpoint'),
            'address_elements': evaluation.get('address_elements'),
            'matched_address': evaluation.get('matched_address')}
    reasons = dc.location_rejections(record, flat)
    if not reasons:
        return 'geocoded', []
    if 'GEOCODE_SIGUNGU_MISMATCH' in reasons:
        return 'sigungu_mismatch', reasons
    if 'GEOCODE_SIGUNGU_UNVERIFIABLE' in reasons:
        return 'unverifiable', reasons
    return 'failed', reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--cache', type=Path, default=CACHE_DIR)
    parser.add_argument('--provider', default=None, choices=sorted(geo.PROVIDER_SPECS))
    parser.add_argument('--limit', type=int, default=None,
                        help='주소 몇 건까지만 시도한다. 비용을 통제할 때 쓴다')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-config', action='store_true', help='자격증명만 확인, HTTP 없음')
    mode.add_argument('--dry-run', action='store_true', help='큐만 만든다, provider 호출 없음')
    mode.add_argument('--live', action='store_true', help='provider를 실제 호출한다')
    args = parser.parse_args()

    selection = geo.select_provider(get_secret, geo.requests_get, args.provider)
    if args.check_config:
        print(json.dumps({'provider': selection['name'], 'blocker': selection['blocker'],
                          'availability': selection['availability'],
                          'skipped': selection['skipped']}, ensure_ascii=False, indent=2))
        return

    collected = json.loads(args.input.read_text(encoding='utf-8'))
    records = collected.get('records') or []
    with_address = [r for r in records if r.get('address')]
    if args.limit:
        with_address = with_address[:args.limit]

    cache = geo.GeocodeCache(args.cache)
    provider = selection['provider'] if args.live else None
    if args.live and provider is None:
        # 자격증명이 없으면 추측하지 않고 멈춘다.
        parser.error(selection['blocker'])
    resolution = geo.resolve([r['address'] for r in with_address], cache, provider)

    tally = Counter()
    rows, by_district = [], {}
    for record in with_address:
        evaluation = resolution['results'].get(geo.cache_key(record['address']))
        bucket, reasons = verdict(record, evaluation)
        tally[bucket] += 1
        stats = by_district.setdefault(record['sigungu'], Counter())
        stats[bucket] += 1
        row = {'project_id': record['project_id'], 'sigungu': record['sigungu'],
               'project_name': record.get('project_name'), 'address': record['address'],
               'bucket': bucket, 'reasons': reasons,
               'geocode_source': (evaluation or {}).get('geocode_source'),
               'answered_sigungu': ((evaluation or {}).get('address_elements') or {}).get('SIGUGUN'),
               'candidates': (evaluation or {}).get('provider_candidate_count'),
               # 복수 후보에서 하나를 고른 경우 그 근거를 남긴다.
               'disambiguation': (evaluation or {}).get('disambiguation')}
        if bucket == 'geocoded':
            row['longitude'] = evaluation['longitude']
            row['latitude'] = evaluation['latitude']
            row['location'] = f"SRID=4326;POINT({evaluation['longitude']} {evaluation['latitude']})"
        rows.append(row)

    report = {
        'format': 'zipon-seoul25-geocode-v1',
        'generated_from': args.input.name,
        'db_write': False, 'supabase_write': 'NONE',
        'mode': 'LIVE' if args.live else 'DRY_RUN',
        'provider': selection['name'] if args.live else None,
        'totals': {'projects': len(records), 'with_address': len(with_address),
                   'no_address': len(records) - len([r for r in records if r.get('address')]),
                   'geocoded': tally['geocoded'], 'failed': tally['failed'],
                   'sigungu_mismatch': tally['sigungu_mismatch'],
                   'unverifiable': tally['unverifiable']},
        'provider_stats': resolution['stats'],
        'disambiguated': sum(1 for r in rows if r.get('disambiguation')),
        'reject_reasons': dict(sorted(Counter(
            reason for r in rows if r['bucket'] != 'geocoded' for reason in r['reasons']).items())),
        'by_district': {d: dict(sorted(c.items())) for d, c in sorted(by_district.items())},
        'items': rows,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                            encoding='utf-8')
    print(json.dumps({k: report[k] for k in
                      ('mode', 'provider', 'totals', 'disambiguated', 'provider_stats',
                       'reject_reasons')},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
