import json,hashlib,re
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[2]
data=json.loads((ROOT/'data/golf/review_evidence.json').read_text(encoding='utf-8'))
lines=[]
for c in data['clubs'].values():
 p=ROOT/'data/golf/runtime/refinement_2026-09-24'/(hashlib.sha256(c['id'].encode()).hexdigest()[:20]+'.json')
 raw=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
 for s in c['sources']:
  if not s['observations'] or not s['published_at'] or s['published_at']<'2024-09-25':continue
  r=next((r for r in raw.get('results',[]) if r['url']==s['original_url']),{})
  body=r.get('raw_content') or r.get('content') or ''
  body=re.sub(r'!\[[^\]]*\]\([^\n]*?\)','',body)
  lines.append('\nCLUB '+c['id']+' '+s['source']+' '+s['published_at']+' full='+str(s['full_text_available'])+' sponsor='+str(s['sponsored_suspected'])+' firsthand='+str(s['first_person_signal']))
  lines.append('HEADER '+body[:500])
  for o in s['observations']:
   pos=body.find(o['evidence'])
   lines.append('OBS '+o['id']+' '+o['dimension']+' '+o['label']+' '+o['evidence'])
   lines.append('CONTEXT '+(body[max(0,pos-600):pos+len(o['evidence'])+400] if pos>=0 else 'not exact in markdown'))
Path(__file__).with_name('review-context.txt').write_text('\n'.join(lines),encoding='utf-8')
