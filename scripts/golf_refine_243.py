"""Resumeable review-source collection scoped to the current recommendation pool.
One Tavily basic search per club. Raw results stay in ignored runtime storage.
No master DB or legacy review summaries are changed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys

def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(tmp,path)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project',default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument('--limit',type=int,default=0)
    ap.add_argument('--workers',type=int,default=3)
    ap.add_argument('--collect',action='store_true',help='Calls Tavily: one basic request per uncached club')
    args=ap.parse_args();root=Path(args.project).resolve();sys.path.insert(0,str(root))
    from services import golf_service as gs
    from services.config import get_secret
    from services.golf_tavily import _one, _name_keys
    _,_,pool=gs.load_pools();pool=sorted(pool,key=lambda r:r['id'])
    out=root/'data/golf/runtime'/('refinement_'+date.today().isoformat())
    atomic(out/'scope.json',{'observed_at':date.today().isoformat(),'count':len(pool),'clubs':[{'id':r['id'],'name':r['name']} for r in pool]})
    if not args.collect:
        print(json.dumps({'scope':len(pool),'note':'Use --collect to search; default is audit only.'}));return
    key=get_secret('TAVILY_API_KEY')
    if not key:raise RuntimeError('TAVILY_API_KEY missing')
    targets=pool[:args.limit] if args.limit else pool
    def collect(r):
        path=out/(hashlib.sha256(r['id'].encode()).hexdigest()[:20]+'.json')
        core=min(_name_keys(r['name']),key=len)
        query=f"{core} 라운딩 후기"
        if path.exists():
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved.get('status')=='ok' and saved.get('query')==query:return r['name'],'cached',len(saved.get('results',[]))
        payload={'id':r['id'],'name':r['name'],'observed_at':date.today().isoformat(),'query':query}
        try:
            payload['results']=_one(key,query,8);payload['status']='ok'
        except Exception as e:
            payload.update(status='error',error_type=type(e).__name__)
        atomic(path,payload)
        return r['name'],payload['status'],len(payload.get('results',[]))
    counts={}
    with ThreadPoolExecutor(max_workers=max(1,min(args.workers,4))) as executor:
        futures=[executor.submit(collect,r) for r in targets]
        for n,f in enumerate(as_completed(futures),1):
            name,status,size=f.result();counts[status]=counts.get(status,0)+1
            print(f'{n}/{len(targets)} {name}: {status} ({size})',flush=True)
    print(json.dumps({'scope':len(pool),'processed':len(targets),'status':counts},ensure_ascii=False))
if __name__=='__main__':main()
