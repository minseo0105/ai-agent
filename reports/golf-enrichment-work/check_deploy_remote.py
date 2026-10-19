from pathlib import Path
import json,os,subprocess,sys
import requests
ROOT=str(Path(__file__).resolve().parents[2])
env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never')
p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,cwd=ROOT,env=env)
cred=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
s=requests.Session();s.headers.update({'Accept':'application/vnd.github+json'})
if cred.get('password'):s.headers['Authorization']='Bearer '+cred['password']
base='https://api.github.com/repos/minseo0105/ai-agent'
for path in ['/actions/variables/HF_SPACE','/actions/workflows/deploy-space.yml/runs?per_page=3']:
 r=s.get(base+path,timeout=25)
 if r.status_code!=200:print(json.dumps({'path':path,'status':r.status_code}));continue
 d=r.json()
 if 'value' in d:print(json.dumps({'space':d['value']}))
 else:print(json.dumps([{'id':x['id'],'sha':x['head_sha'],'status':x['status'],'conclusion':x['conclusion'],'url':x['html_url']} for x in d.get('workflow_runs',[])],ensure_ascii=False))
if len(sys.argv)>1:
 run=sys.argv[1];r=s.get(base+'/actions/runs/'+run+'/jobs',timeout=25)
 if r.status_code==200:print(json.dumps([{'name':x['name'],'status':x['status'],'conclusion':x['conclusion'],'steps':[(z['name'],z['status'],z['conclusion']) for z in x.get('steps',[])]} for x in r.json().get('jobs',[])]))
