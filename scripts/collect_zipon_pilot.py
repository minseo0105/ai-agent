"""Collect public official pages to a local review artifact. No DB access."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.development_collector import collect

if __name__ == '__main__':
    data=collect()
    path=Path(__file__).resolve().parents[1]/'data/development/pilot_20260927.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    for district in ('강동구','송파구','서초구'):
        rows=[r for r in data['records'] if r['sigungu']==district]
        print(district,len(rows),'official',sum(r['source']['is_official'] for r in rows),
              'coordinates',sum(bool(r['location']) for r in rows),'verified polygons',sum(r['geometry_verified'] for r in rows))
    for run in data['runs']:print(run['source'],run['status'],run['new_count'],run['errors'])
