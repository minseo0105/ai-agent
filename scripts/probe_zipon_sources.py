"""Official read-only probe, no database or geocoder use."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.development_sources import OfficialHTTP, acquire_archive, SourceError
from services.development_collector import collect, SEOUL_DISTRICTS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all-seoul',action='store_true')
    parser.add_argument('--shp',action='store_true')
    parser.add_argument('--out',default='reports/zipon-live-probe')
    args=parser.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    http=OfficialHTTP(out/'raw')
    if args.shp:
        try:
            manifest=acquire_archive(http,out/'shp')
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
            from analyze_seoul_polygon_source import analyse
            survey=analyse(manifest['path'])
            report={'status':'SUCCEEDED','archive':manifest,'record_count':survey['record_count'],
                'source_crs':survey['source_crs_label'],'outside_seoul':survey['outside_seoul'],
                'converted':survey['converted_to_epsg4326'],'schema':survey['schema']}
        except Exception as exc:
            report={'status':'FAILED','code':str(exc) if isinstance(exc,SourceError) else type(exc).__name__}
    else:
        report=collect(fetch=http.get,districts=SEOUL_DISTRICTS if args.all_seoul else ['강동구'])
    (out/'probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('records','schema')},ensure_ascii=False))


if __name__=='__main__':main()
