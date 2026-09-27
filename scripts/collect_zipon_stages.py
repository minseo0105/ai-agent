"""Prepare stage audit/queue; --fetch reads official pages, never writes any DB."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import quote
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.development_stage import collect, official_url, VERSION
from services.development_official import now
from build_zipon_geocode_targets import in_database, load

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fetch', action='store_true')
    ap.add_argument('--cache-dir', type=Path, default=DATA/'cache/official_stage',
                    help='Use a new dated directory for a future refresh; preserve previous snapshots.')
    args = ap.parse_args()
    ids = in_database()
    targets = []
    for p in load('pilot_canonical_verified_20260927.json')['projects']:
        pid = p['raw']['candidate_ids'][0]
        if pid not in ids:
            continue
        alias = p['identity'].get('official_external_id')
        targets.append({'project_id': pid, 'project_name': p['identity']['official_project_name'],
                        'external_id': alias, 'official_source': p['provenance']['source_name'],
                        'source_url': p['provenance']['source_url'],
                        'detail_url': 'https://cleanup.seoul.go.kr/cafe/mainIndx.do?cafeUrl=' + quote(alias, safe='') if alias else None,
                        'previous_progress': p['progress'], 'previous_provenance': p['provenance']})
    targets.sort(key=lambda x:x['project_id'])
    dump(DATA/'stage_collection_queue_20260927.json', {'targets':targets, 'db_write':False,
        'endpoint_evidence':'Official cafeOpenPopup on Seoul district listing opens /cafe/mainIndx.do?cafeUrl=<alias>'})
    if not args.fetch:
        print(json.dumps({'queue':len(targets), 'with_detail_url':sum(bool(x['detail_url']) for x in targets), 'db_write':False}))
        return
    import requests
    cache = args.cache_dir
    cache.mkdir(parents=True, exist_ok=True)
    blocked = False
    def fetch(url):
        if not official_url(url):
            raise ValueError('UNTRUSTED_URL')
        key = hashlib.sha256(url.encode()).hexdigest()
        path = cache/(key+'.json')
        if path.exists():
            stored = json.loads(path.read_text(encoding='utf-8'))
            if stored.get('error'):
                raise RuntimeError(stored['error'])
            return stored['html']
        response = requests.get(url, timeout=25, allow_redirects=False)
        if response.status_code != 200:
            dump(path, {'source_url':url,'fetched_at':now(),'error':'HTTP_'+str(response.status_code)})
            raise RuntimeError('HTTP_'+str(response.status_code))
        html = response.content.decode('utf-8', 'replace')
        # Store only public project name, frame, and progress block; no scripts, cookies or headers.
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html,'html.parser')
        progress = soup.select_one('.progress-cont')
        frame = soup.select_one('iframe#contentFrame')
        from html import escape
        clean = (str(progress) if progress else '') + (str(frame) if frame else '')
        clean += '<div>' + escape(soup.get_text(' ',strip=True)) + '</div>'
        dump(path, {'source_url':url,'fetched_at':now(),'http_status':200,'html':clean,
                    'content_hash':hashlib.sha256(response.content).hexdigest()})
        return clean
    results=[]
    for t in targets:
        if blocked:
            results.append(dict(t, result_status='SKIPPED_HOST_UNAVAILABLE'))
            continue
        try:
            result = collect(t, fetch)
            if result.get('evidence_url'):
                evidence_cache = cache/(hashlib.sha256(result['evidence_url'].encode()).hexdigest()+'.json')
                if evidence_cache.exists():
                    result['fetched_at'] = json.loads(evidence_cache.read_text(encoding='utf-8'))['fetched_at']
            results.append(result)
        except Exception as exc:
            results.append(dict(t,result_status='FETCH_FAILED',error_type=type(exc).__name__))
            blocked=True
        if len(results)%20==0:
            print('PROCESSED',len(results),flush=True)
    counts=Counter(r.get('current_stage') or 'NO_DETAIL_STAGE' for r in results)
    summary={'canonical_projects':len(targets),'detail_urls':sum(bool(t['detail_url']) for t in targets),
             'detail_page_matched':sum(bool(r.get('detail_page_matched')) for r in results),
             'current_stage_extracted':sum(bool(r.get('current_stage')) for r in results),
             'stage_history_extracted':sum(any(m.get('stage_date') for m in r.get('milestones',[])) for r in results),
             'by_stage':dict(counts),'result_status':dict(Counter(r['result_status'] for r in results)),
             'db_write':False,'parser_version':VERSION}
    dump(DATA/'official_stage_result_20260927.json', {'summary':summary,'projects':results})
    # Public, minimal read-model; no mutation of canonical or DB values.
    catalog = {}
    for r in results:
        item = {key:r.get(key) for key in ('current_stage','milestones','stage_verified_level',
                'fetched_at','evidence_url','content_hash','cafe_id','detail_page_matched','parser_version')}
        old = r['previous_progress']
        item['list_stage'] = {'raw_stage':old.get('raw_stage'), 'source_url':old.get('stage_source_url'),
                              'source_name':r['official_source'], 'verified_at':old.get('stage_verified_at')}
        catalog[r['project_id']] = item
    dump(ROOT/'services/development_stage_catalog.json', {'version':VERSION,'projects':catalog})
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    main()
