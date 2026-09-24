"""Read-only HTTP discovery: never applies guessed contact numbers to the DB."""
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

def inspect(r):
    out={'id':r['id'],'name':r['name'],'url':r['official_url'],'address':r.get('address'),'candidates':[]}
    try:
        response=requests.get(r['official_url'],timeout=12)
        response.raise_for_status()
        raw=response.content
        charset=re.search(br'charset\s*=\s*["\x27]?([a-zA-Z0-9_-]+)',raw[:10000])
        enc=charset.group(1).decode() if charset else response.apparent_encoding
        soup=BeautifulSoup(raw.decode(enc or 'utf-8',errors='replace'),'html.parser')
        for tag in soup(['script','style']): tag.decompose()
        text=re.sub(r'\s+',' ',soup.get_text(' ',strip=True))
        out['url']=response.url
        for m in re.finditer(r'(?<!\d)(?:0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}|1[568]\d{2}[-.\s]?\d{4})(?!\d)',text):
            if len(out['candidates'])>=12: break
            out['candidates'].append({'phone':m.group(),'context':text[max(0,m.start()-95):m.end()+85]})
        out['status']='candidate' if out['candidates'] else 'no_phone_in_static_page'
    except Exception as e:
        out['status']='unavailable';out['error']=type(e).__name__
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('db');p.add_argument('out');args=p.parse_args()
    rows=json.loads(Path(args.db).read_text(encoding='utf-8-sig'))
    targets=[r for r in rows if not r.get('phone') and str(r.get('official_url') or '').startswith('http')]
    with ThreadPoolExecutor(max_workers=4) as ex:
        result=list(ex.map(inspect,targets))
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'attempted':len(result),'with_candidates':sum(bool(r['candidates']) for r in result)},ensure_ascii=False))
