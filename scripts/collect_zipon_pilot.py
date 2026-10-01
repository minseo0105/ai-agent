"""Collect public official pages to a local review artifact. No DB access.

  python scripts/collect_zipon_pilot.py                        # 기존 세 구(기본값, 동작 불변)
  python scripts/collect_zipon_pilot.py --district 성동구
  python scripts/collect_zipon_pilot.py --districts 성동구,마포구,용산구
  python scripts/collect_zipon_pilot.py --all-seoul

자치구 코드는 services.realestate_monitor.REGION_LAWD의 서울 25개 항목이 유일한
출처다. 인자를 주지 않으면 지금까지와 같은 강동·송파·서초만 수집하고 같은 파일에
쓴다. 서울 전체 수집은 --all-seoul로 명시할 때만 일어난다.
"""
import argparse
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.development_collector import (collect, normalize_districts, UnknownDistrict,
                                            SEOUL_DISTRICTS, PILOT_DISTRICTS)

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument('--district', help='자치구 1개')
    scope.add_argument('--districts', help='쉼표로 구분한 자치구 목록')
    scope.add_argument('--all-seoul', action='store_true', help='서울 25개 자치구 전체')
    parser.add_argument('--out', type=Path, help='수집 artifact 경로')
    args = parser.parse_args()

    requested = SEOUL_DISTRICTS if args.all_seoul else (
        [d for d in re.split(r'[,\s]+', args.districts) if d] if args.districts
        else args.district)
    try:
        districts = normalize_districts(requested)
    except UnknownDistrict as exc:
        # 오타를 조용히 건너뛰면 '그 구는 수집된 게 없다'로 보인다. 이름을 돌려주고 멈춘다.
        parser.error(str(exc) + ' (서울 자치구 이름만 받습니다. 경기/전국은 이 수집기 범위가 아닙니다)')
    default_name = ('pilot_20260927.json' if tuple(districts) == tuple(PILOT_DISTRICTS)
                    else 'collected_' + '_'.join(districts) + '.json')
    path = args.out or ROOT / 'data/development' / default_name

    data = collect(districts=districts)
    if not data['records'] and path.exists():
        # 전부 실패한 수집으로 기존 캡처를 덮으면 근거가 사라진다. 쓰지 않고 멈춘다.
        for run in data['runs']:
            print(run['source'], run['status'], run['new_count'], run['errors'])
        parser.error('COLLECTED_ZERO_RECORDS; ' + str(path) + ' 를 덮어쓰지 않았습니다')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    for district in districts:
        rows = [r for r in data['records'] if r['sigungu'] == district]
        print(district, len(rows), 'official', sum(r['source']['is_official'] for r in rows),
              'coordinates', sum(bool(r['location']) for r in rows),
              'verified polygons', sum(r['geometry_verified'] for r in rows))
    for run in data['runs']:
        print(run['source'], run['status'], run['new_count'], run['errors'])


if __name__ == '__main__':
    main()
