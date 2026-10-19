import sys,json,re,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin,urlsplit
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from services import golf_service as gs
OUT=Path(__file__).parent/'official-pages-25';OUT.mkdir(exist_ok=True)
def fetch(url):
 response=requests.get(url,timeout=10);response.raise_for_status()
 raw=response.content
 choices=['utf-8','cp949',response.apparent_encoding or 'utf-8']
 decoded=min((raw.decode(e,errors='replace') for e in choices),key=lambda x:x.count('\ufffd'))
 soup=BeautifulSoup(decoded,'html.parser')
 links=[{'text':a.get_text(' ',strip=True),'url':urljoin(response.url,a.get('href',''))} for a in soup.select('a[href]')]
 for x in soup(['script','style']):x.decompose()
 return {'url':response.url,'text':soup.get_text(' ',strip=True),'links':links}
def inspect(c):
 out={'id':c['id'],'name':c['name'],'official_url':c.get('official_url'),'observed_at':'2026-09-25','pages':[]}
 if not str(c.get('official_url') or '').startswith('http'):out['status']='no_official_url';return out
 try:
  home=fetch(c['official_url']);out['pages'].append(home)
  links=[l['url'] for l in home['links'] if re.search('요금|이용료',l['text']) and urlsplit(l['url']).hostname==urlsplit(home['url']).hostname]
  for url in list(dict.fromkeys(links))[:1]:
   if url!=home['url']:
    try:out['pages'].append(fetch(url))
    except Exception as e:out['fee_page_error']=type(e).__name__
  out['status']='fetched'
 except Exception as e:out.update(status='unavailable',error=type(e).__name__)
 (OUT/(hashlib.sha256(c['id'].encode()).hexdigest()[:20]+'.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 return {k:v for k,v in out.items() if k!='pages'}|{'pages':len(out['pages'])}
pool=gs.load_pools()[2]
targets=[r for r in pool if not (r.get('pricing') or {}).get('fee_records') or not r.get('phone')]
with ThreadPoolExecutor(max_workers=6) as ex:result=list(ex.map(inspect,targets))
(OUT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'scope':len(pool),'attempted':len(result),'fetched':sum(r['status']=='fetched' for r in result)},ensure_ascii=False))
