"""Post-container smoke test; uses only disposable trial workspaces."""
import argparse
import json
import urllib.error
import urllib.request


def check(url):
    def request(path,body=None,headers=None):
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(url.rstrip('/')+path,data=data,headers={'Content-Type':'application/json',**(headers or {})})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                content=response.read()
                return response.status,json.loads(content) if 'application/json' in response.headers.get('Content-Type','') else content
        except urllib.error.HTTPError as e:return e.code,None
    status,health=request('/api/health')
    assert status==200 and health['family_api'] is False
    assert request('/')[0]==200
    for path in ('/api/moneyon/unlock','/api/admin/settings','/api/access/login','/api/realestate','/docs','/.env'):
        assert request(path)[0]==404,path
    _,a=request('/api/moneyon/trial/start',{})
    _,b=request('/api/moneyon/trial/start',{})
    assert (a['state']['wallet'],a['state']['vault'])==(28500,15000)
    assert a['state']['rewards']['estimates']=={'allowance_bonus':2800,'savings_interest':300}
    header={'X-Moneyon-Trial':a['token'],'X-Moneyon-Trial-Version':'1'}
    child='/api/moneyon/trial/children/'+a['child']['id']
    assert request(child,headers={'X-Moneyon-Trial':b['token']})[0]==403
    status,paid=request(child+'/allowance',{'amount':1000,'key':'space-smoke-payment'},header)
    assert status==200 and paid['state']['wallet']==29500
    status,reset=request('/api/moneyon/trial/reset',{'key':'space-smoke-reset'},header)
    assert status==200 and reset['state']['wallet']==28500
    assert request(child,headers=header)[0]==403
    print(json.dumps({'ok':True,'url':url,'trial_only':True,'seed':True,'isolation':True,'allowance':True,'reset':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:7860')
    check(parser.parse_args().url)
