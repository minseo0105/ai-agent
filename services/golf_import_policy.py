"""Fill-only import policy. All conflicting/conditional evidence remains reviewable."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import re
from urllib.parse import urlsplit

def get(record,path):
    for k in path.split('.'): record=record.get(k) if isinstance(record,dict) else None
    return record

def set_value(record,path,value):
    keys=path.split('.')
    for k in keys[:-1]:
        if not isinstance(record.get(k),dict): record[k]={}
        record=record[k]
    record[keys[-1]]=value

def norm(s): return re.sub(r'[\s|,]+','',str(s or ''))

def trusted(f,item,today):
    url=f.get('source_url','')
    if not url.startswith(('https://','http://')) or not f.get('quote'): return False
    try:
        if not 0 <= (date.fromisoformat(today)-date.fromisoformat(item['observed_at'])).days <= 7: return False
    except (KeyError,TypeError,ValueError): return False
    if item.get('review_method')=='human_official_source' and f.get('reviewed') is True: return True
    if item.get('schema_version')!=2 or url not in item.get('approved_source_urls',[]) or f.get('from_image') or not f.get('verified_quote'): return False
    host=lambda u:(urlsplit(u).hostname or '').removeprefix('www.')
    if not host(url): return False  # exact reviewed URL above also supports verified domain migrations
    return any(p.get('url')==url and len(norm(f['quote']))>=6 and norm(f['quote']) in norm(p.get('text')) for p in item.get('page_evidence',[]))

def metadata(f,item,volatile=False):
    m={'source_url':f['source_url'],'evidence_quote':f['quote'],'checked_at':item['observed_at'],
       'confidence':'official_source_human_reviewed' if f.get('reviewed') else 'official_homepage_extracted_quote_verified',
       'method':item.get('review_method','exact_page_quote'),'condition':f.get('condition') or ''}
    m['evidence_type']=f.get('evidence_type','excerpt')
    if volatile:
        expiry=date.fromisoformat(item['observed_at'])+timedelta(days=90)
        if f.get('valid_to'): expiry=min(expiry,date.fromisoformat(f['valid_to']))
        m['fresh_until']=expiry.isoformat()
    return m

def source(record,path,m):
    record.setdefault('field_evidence',{})[path]=deepcopy(m)
    sources=record.setdefault('sources',[])
    entry=next((s for s in sources if isinstance(s,dict) and s.get('source_url')==m['source_url']),None)
    if entry is None:
        entry={'source_type':'official_homepage','source_url':m['source_url'],'fields':[]};sources.append(entry)
    entry['checked_at']=m['checked_at']
    if path not in entry.setdefault('fields',[]): entry['fields'].append(path)

def apply_item(record,item,today,refresh=False,apply_players=False):
    before=deepcopy(record);ex=item.get('extraction') or {};changes=[];conflicts=[]
    ledger=record.setdefault('enrichment',{});history=ledger.setdefault('history',[]);candidates=ledger.setdefault('candidates',[])
    def hold(path,value,f,reason):
        c={'field':path,'value':value,'source':f.get('source_url',''),'evidence':f.get('quote',''),
           'confidence':'needs_review','condition':f.get('condition',''),'observed_at':item.get('observed_at'),
           'reason':reason,'valid_from':f.get('valid_from'),'valid_to':f.get('valid_to')}
        fingerprint=hashlib.sha256(json.dumps(c,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if not any(x.get('fingerprint')==fingerprint for x in candidates): candidates.append(dict(c,fingerprint=fingerprint))
        conflicts.append({'field':path,'existing':get(record,path),'new':value,'source_url':f.get('source_url',''),'kind':reason})
    def eligible(f):
        try:
            for key in ('valid_from','valid_to'):
                if f.get(key): date.fromisoformat(f[key])
        except (TypeError,ValueError): return False
        return trusted(f,item,today) and not f.get('condition') and not f.get('conflict') and not (f.get('valid_from') and f['valid_from']>today) and not (f.get('valid_to') and f['valid_to']<today)
    def put(path,value,f,volatile=False):
        old=get(record,path)
        placeholder=path=='course_overview' and old in ('상세 코스정보는 공식 홈페이지에서 확인합니다.','상세 코스정보는 공식 홈페이지에서 확인할 수 있습니다.')
        if not eligible(f): hold(path,value,f,'unverified_or_conditional');return
        if old not in (None,'',[],'unknown') and old!=value and not placeholder:
            hold(path,value,f,'existing_value_conflict');return
        m=metadata(f,item,volatile);previous=record.get('field_evidence',{}).get(path)
        if old==value and (not refresh or previous==m): return
        history.append({'field':path,'previous':deepcopy(old),'value':deepcopy(value),'previous_evidence':deepcopy(previous),'evidence':deepcopy(m),'recorded_at':today})
        set_value(record,path,value);source(record,path,m);changes.append(path)
        if item.get('review_method')=='human_official_source':
            approved=ledger.setdefault('approved_source_urls',[])
            if m['source_url'] not in approved: approved.append(m['source_url'])
        if path in ('operations.caddie.fee_team','operations.cart.fee_team'): get(record,path.rsplit('.',1)[0]).update(m)
    f=ex.get('phone')
    if isinstance(f,dict) and isinstance(f.get('value'),str) and re.fullmatch(r'(?:0\d{1,2}-\d{3,4}-\d{4}|1[568]\d{2}-\d{4})',f['value']): put('phone',f['value'],f)
    f=ex.get('course_description')
    if isinstance(f,dict) and isinstance(f.get('value'),str) and f['value'].strip(): put('course_overview',f['value'],f)
    for key,kind in [('caddie_fee','caddie'),('cart_fee','cart')]:
        f=ex.get(key)
        if isinstance(f,dict) and type(f.get('fee_team_krw')) is int and 0<=f['fee_team_krw']<=1000000: put(f'operations.{kind}.fee_team',f['fee_team_krw'],f,True)
    valid=[]
    for f in ex.get('green_fees') or []:
        if f.get('customer')=='member' or f.get('holes')!=18: continue
        if type(f.get('price_krw')) is not int or not 10000<=f['price_krw']<=2000000: continue
        if not eligible(f) or f.get('customer')!='nonmember': hold('pricing.fee_records',f,f,'fee_scope_review');continue
        m=metadata(f,item,True)
        valid.append({'record_type':'official_homepage_extract','day_type':f.get('day'),'session':f.get('session','all'),
          'member_type':'nonmember','holes':18,'greenfee':f['price_krw'],'valid_from':f.get('valid_from'),
          'valid_to':f.get('valid_to') or m['fresh_until'],**m})
    if valid:
        old=get(record,'pricing.fee_records') or []
        # Reconfirmation requires identical conditions and source. Dates are only refreshed after fresh collection.
        signature=lambda rows: sorted(json.dumps({k:v for k,v in r.items() if k not in ('checked_at','fresh_until','valid_to')},sort_keys=True,ensure_ascii=False) for r in rows)
        if old==valid:
            pass
        elif not old or refresh and signature(old)==signature(valid):
            if old!=valid:
                history.append({'field':'pricing.fee_records','previous':deepcopy(old),'value':deepcopy(valid),'recorded_at':today})
                set_value(record,'pricing.fee_records',valid)
                record['pricing'].update(last_checked=item['observed_at'],source_url=valid[0]['source_url'])
                for f in valid: source(record,'pricing.fee_records',f)
                if item.get('review_method')=='human_official_source':
                    approved=ledger.setdefault('approved_source_urls',[])
                    for f in valid:
                        if f['source_url'] not in approved: approved.append(f['source_url'])
                changes.append('pricing.fee_records')
        else: hold('pricing.fee_records',valid,{'source_url':valid[0]['source_url'],'quote':valid[0]['evidence_quote']},'existing_value_conflict')
    for key in ('two_person','three_person','night_round','caddie_mode_detail'):
        f=ex.get(key)
        if isinstance(f,dict): hold(key,f,f,'operating_rule_review')
    for f in ex.get('observations',[]): hold(f.get('field','observation'),f.get('value'),f,'conditional_observation')
    for f in ex.get('official_features',[]):
        if f.get('field') not in ('bunker_count','fairway_width_m','driving_range','practice_green','par3_course','course_characteristic'): continue
        if f.get('reviewed') is True:
            put('enrichment.facts.'+f['field'],f.get('value'),f)
        else: hold('enrichment.facts.'+f['field'],f.get('value'),f,'official_feature_review')
    if not history and not candidates and 'enrichment' not in before: record.pop('enrichment')
    if record!=before and not changes: changes.append('evidence_only')
    return changes,conflicts
