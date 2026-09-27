"""Reconcile all IDs; recover only unresolved entries from discovered official IDs."""
import argparse, hashlib, json, re, sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qs
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.development_stage import parse_progress, official_url, stage_view
from services.development_official import compact, now
from services.development_geocode import wanted_parts
from services.development_presentation import present_project
from build_zipon_geocode_targets import in_database

# Discovery leads only. A search result is never itself stage evidence.
LEADS={'신반포25차':'650900000613q27','현대연립':'740100001048D65',
       '이화연립':'710100002000x52','서초중앙하이츠2':'650900000666g26',
       '송파동 100번지':'710900000178R73','풍전연립':'740100001053I31',
       '신성빌라':'650900000633V77','반도아파트':'710100002009K86',
       '선화연립':'740100001039U18','목화연립':'740100001056t08'}
DATA=ROOT/'data/development'
CAT=ROOT/'services/development_stage_catalog.json'

def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def summary_fields(html):
    soup=BeautifulSoup(html,'html.parser');fields={}
    for th in soup.select('th'):
        td=th.find_next_sibling('td')
        if td:fields[compact(th.get_text())]=td.get_text(' ',strip=True)
    return fields

def identity_checks(project,fields,frame,cafe_id,summary_url):
    location=project['location'];name=project['identity']['official_project_name']
    address=fields.get('정비구역위치','');kind=fields.get('사업구분','')
    parts=wanted_parts(location['representative_address'] or '')
    numbers=re.findall(r'\d+(?:-\d+)*',name)
    title=fields.get('정비구역명칭','')
    title_numbers=re.findall(r'\d+(?:-\d+)*',title)
    expected={'RECONSTRUCTION':'재건축','REDEVELOPMENT':'재개발'}.get(project['classification']['canonical_project_type'])
    return {'district': bool(location['district'] and location['district'] in address),
            'dong':bool(parts['dong'] and parts['dong'] in address),
            'lot':bool(parts['lot'] and re.search(r'(?<![\d-])'+re.escape(parts['lot'])+r'(?![\d-])',address)),
            'project_type':bool(expected and expected in kind),
            'zone_numbers':numbers==title_numbers,
            'frame_name':compact(name) in compact(BeautifulSoup(frame,'html.parser').get_text()),
            'identifier':(parse_qs(urlsplit(summary_url).query).get('cafeId') or [None])[0]==cafe_id}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fetch-missing',action='store_true');args=ap.parse_args()
    catalog=json.loads(CAT.read_text(encoding='utf-8'))
    projects=json.loads((DATA/'pilot_canonical_verified_20260927.json').read_text(encoding='utf-8'))['projects']
    projects={p['raw']['candidate_ids'][0]:p for p in projects if p['raw']['candidate_ids'][0] in in_database()}
    assert set(projects)==set(catalog['projects']) and len(projects)==130
    original={pid:dict(v) for pid,v in catalog['projects'].items()}
    cache=DATA/'cache/official_stage_recovery';blocked=False;log=[]
    def fetch(url):
        import requests
        if not official_url(url):raise ValueError('UNTRUSTED_URL')
        path=cache/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        if path.exists():
            entry=json.loads(path.read_text(encoding='utf-8'))
            if entry.get('status')!=200:raise ValueError('CACHED_HTTP_ERROR')
            return entry
        response=requests.get(url,timeout=25,allow_redirects=False)
        soup=BeautifulSoup(response.content,'html.parser')
        for node in soup.select('script,style,input'):node.decompose()
        entry={'source_url':url,'status':response.status_code,'fetched_at':now(),'html':str(soup),
               'content_hash':hashlib.sha256(response.content).hexdigest()}
        dump(path,entry)
        if response.status_code!=200:raise ValueError('HTTP_ERROR')
        return entry
    for pid,p in projects.items():
        item=catalog['projects'][pid]
        item['identity']={'project_name':p['identity']['official_project_name'],
            'district':p['location']['district'],'address':p['location']['representative_address'],
            'project_type':p['classification']['canonical_project_type'],'program':p['classification']['program'],
            'external_id':p['identity']['official_external_id']}
        if stage_view(item):continue
        lead=next((v for k,v in LEADS.items() if item['identity']['project_name'].startswith(k)),None)
        if not args.fetch_missing or not lead or blocked:
            log.append({'project_id':pid,'result':'NO_CONFIRMED_ALTERNATE' if not lead else 'NOT_FETCHED'});continue
        try:
            url='https://cleanup.seoul.go.kr/assc/scrin-bbs/execute.do?cafeId='+lead
            frame=fetch(url);soup=BeautifulSoup(frame['html'],'html.parser')
            link=next((a.get('href') for a in soup.select('a[href]') if 'bsnsSumry' in a['href'] and 'div=sumry' in a['href']),None)
            if not link:
                log.append({'project_id':pid,'result':'NO_SUMMARY_LINK'});continue
            summary_url=urljoin(url,link);summary=fetch(summary_url)
            fields=summary_fields(summary['html']);checks=identity_checks(p,fields,frame['html'],lead,summary_url)
            parsed=parse_progress(frame['html'])
            recovery={'project_id':pid,'cafe_id':lead,'evidence_url':url,'summary_url':summary_url,
                      'identity_checks':checks,'summary_fields':fields,'result':'VERIFIED' if all(checks.values()) and parsed['current_stage'] else 'REVIEW_REQUIRED'}
            log.append(recovery)
            if recovery['result']=='VERIFIED':
                item['previous_observations']=[original[pid]]
                item.update({k:parsed[k] for k in ('current_stage','milestones')})
                item.update(stage_verified_level='OFFICIAL_DETAIL_VERIFIED',evidence_url=url,
                            content_hash=frame['content_hash'],fetched_at=frame['fetched_at'],cafe_id=lead,
                            identity_evidence=recovery,detail_page_matched=True)
        except Exception as exc:
            log.append({'project_id':pid,'result':'FETCH_FAILED','error_type':type(exc).__name__});blocked=True
    for item in catalog['projects'].values():
        if stage_view(item):
            source={k:item.get(k) for k in ('evidence_url','content_hash','fetched_at')}
            item['current_stage_evidence']=dict(source,selector='.progress .step + p')
            item['milestone_evidence']=dict(source,selector='.progress-cont li .txt/.date',
                                             date_policy='PRESERVE_TWO_DIGIT_YEAR_NO_CENTURY_INFERENCE')
    preserved=all(all(catalog['projects'][pid].get(k)==v for k,v in old.items()) for pid,old in original.items() if stage_view(old))
    assert preserved
    dump(CAT,catalog)
    from services.development_stage import catalog as get_catalog
    get_catalog.cache_clear()
    rendered=[present_project({'project_id':pid}) for pid in projects]
    coverage={'canonical':130,'direct_detail':sum(stage_view(v) is not None for v in catalog['projects'].values()),
              'unresolved':sum(r['stage']['label']=='세부 진행단계 확인 중' for r in rendered),
              'milestone_date':sum(any(m.get('stage_date') for m in v.get('milestones') or []) for v in catalog['projects'].values()),
              'preserved_original_detail':preserved,'missing_ids':len(set(projects)-set(catalog['projects'])),
              'db_write':False}
    coverage['list_fallback']=130-coverage['direct_detail']-coverage['unresolved']
    dump(DATA/'stage_reconciliation_20260927.json',{'coverage':coverage,'recovery':log,
         'rows':[{'project_id':pid,'identity':catalog['projects'][pid]['identity'],'stage':r['stage'],
                   'level':r['stage_verified_level']} for pid,r in zip(projects,rendered)]})
    print(json.dumps(coverage,ensure_ascii=False))

if __name__=='__main__':main()
