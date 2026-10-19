from pathlib import Path
import sys,json,requests
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from services.config import get_secret
from services import realestate_monitor as rm
names=['PUBLIC_DATA_API_KEY','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','TAVILY_API_KEY','VWORLD_API_KEY','NAVER_MAP_CLIENT_ID','NAVER_MAP_CLIENT_SECRET','ANTHROPIC_API_KEY','OPENAI_API_KEY']
print(json.dumps({'configured_locally':{n:bool(get_secret(n,section='realestate')) for n in names}}),flush=True)
c=rm._supabase_config()
if not c:
 print('Supabase local configuration unavailable');raise SystemExit()
url,key=c
headers={'apikey':key,'Authorization':'Bearer '+key,'Accept':'application/openapi+json'}
try:
 resp=requests.get(url+'/rest/v1/',headers=headers,timeout=25)
 print('schema_http_status',resp.status_code,flush=True)
 if resp.ok:
  d=resp.json();definitions=d.get('definitions',{})
  print(json.dumps({'exposed_tables':{t:{k:v.get('type',v.get('format')) for k,v in spec.get('properties',{}).items()} for t,spec in definitions.items()}},ensure_ascii=False),flush=True)
 for table in ['alert_rules','notifications','source_snapshots','app_settings']:
  resp=requests.get(url+'/rest/v1/'+table,headers={**headers,'Accept':'application/json'},params={'select':'*','limit':0},timeout=20)
  print(json.dumps({'table':table,'read_status':resp.status_code}),flush=True)
except Exception as e:
 print('schema_read_failed',type(e).__name__)
