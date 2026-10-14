"""Live ZIP refresh: fresh database baseline, isolated sources, explicit write gate."""
import copy
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from services import development_collector as collector
from services import development_geocode as geocoder
from services import development_stage as stages
from services.development_official import digest, normalize_stage, now
from services.development_pipeline import stage_regression
from services.development_sources import OfficialHTTP, SourceError, PORTAL, acquire_archive, labeled_dates, collect_notices, collect_moa_cancellations
from services.supabase_auth import supabase_headers

VERSION = 'zipon-live-refresh-v1'
PROJECT_URL = 'https://nnxtkvjpzqqhjlgnprzo.supabase.co'
ROOT = Path(__file__).resolve().parents[1]


class RefreshError(Exception):
    pass


class Database:
    """ZIP credentials only. Never fall back to the Golf/shared database."""
    def __init__(self, apply=False):
        self.url = os.environ.get('ZIPON_IMPORT_SUPABASE_URL', '').rstrip('/')
        key = os.environ.get('ZIPON_IMPORT_SUPABASE_KEY', '')
        if self.url != PROJECT_URL or not key:
            raise RefreshError('ZIPON_DATABASE_CONFIG_REQUIRED')
        if key.startswith('sb_publishable_'):
            raise RefreshError('SERVER_CREDENTIAL_REQUIRED')
        if apply and os.environ.get('ZIPON_REFRESH_WRITE_ENABLED') != 'true':
            raise RefreshError('WRITE_GATE_DISABLED')
        self.apply = apply
        self.headers = supabase_headers(key)
        self.session = requests.Session()

    def request(self, method, table, payload=None, params=None):
        if method != 'GET' and not self.apply:
            raise RefreshError('DRY_RUN_WRITE_REFUSED')
        try:
            r = self.session.request(method, self.url + '/rest/v1/' + table,
                headers=self.headers, params=params, json=payload, timeout=30,
                allow_redirects=False)
            if not r.ok:
                raise RefreshError('DATABASE_HTTP_' + str(r.status_code))
            return r.json() if r.content else None
        except (requests.RequestException, ValueError):
            raise RefreshError('DATABASE_REQUEST_FAILED') from None

    def rows(self, table, select='*', filters=None):
        result = []
        for offset in range(0, 100000, 500):
            page = self.request('GET', table, params=dict(filters or {}, select=select,
                order=('project_id' if table == 'development_projects' else 'source_id') + '.asc',
                offset=offset, limit=500))
            result.extend(page)
            if len(page) < 500:
                return result
        raise RefreshError('DATABASE_PAGINATION_LIMIT')

    def storage(self, path, body=None):
        if body is not None and not self.apply:
            raise RefreshError('DRY_RUN_STORAGE_REFUSED')
        headers = dict(self.headers, **{'Content-Type': 'application/octet-stream', 'x-upsert': 'true'})
        try:
            r = self.session.request('GET' if body is None else 'POST',
                self.url + '/storage/v1/object/zipon-official-raw/' + path,
                headers=headers, data=body, timeout=60, allow_redirects=False)
            if body is None and r.status_code == 404:
                return None
            if not r.ok:
                raise RefreshError('RAW_STORAGE_HTTP_' + str(r.status_code))
            return r.content
        except requests.RequestException:
            raise RefreshError('RAW_STORAGE_UNAVAILABLE') from None


def candidate_payload(record):
    allowed = {'project_id','project_name','project_type','official_authority','external_id',
               'sido','sigungu','dong','address','stage_raw','status','validation_status',
               'area_m2','planned_units','field_evidence'}
    return {k: v for k, v in record.items() if k in allowed and v is not None}


def identity(record, known, all_candidates):
    """Exact official ID selects the existing canonical UUID. Similar names never merge."""
    official = [p for p in known if record.get('external_id') and
                p.get('official_authority') == record.get('official_authority') and
                p.get('external_id') == record['external_id']]
    if len(official) > 1:
        return None, 'DUPLICATE_OFFICIAL_ID'
    row = official[0] if official else next((p for p in known if p['project_id'] == record['project_id']), None)
    if row:
        if any(row.get(f) != record.get(f) for f in ('sigungu','project_type','official_authority','external_id')):
            return row, 'OFFICIAL_IDENTITY_CONFLICT'
        if ''.join(row['project_name'].split()) != ''.join(record['project_name'].split()):
            return row, 'PROJECT_NAME_CHANGED'
    if not record.get('external_id'):
        return row, 'NO_OFFICIAL_IDENTIFIER'
    name = ''.join(record['project_name'].split())
    for other in known + all_candidates:
        if other['project_id'] in (record['project_id'], (row or {}).get('project_id')):
            continue
        other_name = ''.join(other['project_name'].split())
        if other.get('sigungu') == record.get('sigungu') and min(len(name), len(other_name)) >= 3:
            if name in other_name or other_name in name:
                return row, 'DUPLICATE_SUSPECTED'
    return row, None


def observation(record, http):
    alias = record.get('external_id')
    if not alias:
        return {}, None
    detail = stages.collect(dict(project_id=record['project_id'], project_name=record['project_name'],
        detail_url='https://cleanup.seoul.go.kr/cafe/mainIndx.do?cafeUrl=' + quote(alias, safe='')), http.text)
    if detail.get('result_status') != 'VERIFIED':
        return {}, detail.get('result_status', 'DETAIL_UNAVAILABLE')
    normalized = normalize_stage(detail['current_stage'])['normalized_stage']
    current = [m for m in detail['milestones'] if m.get('is_current')]
    dates = {m.get('stage_date') for m in current if m.get('stage_date')}
    if len(dates) > 1:
        return detail, 'CONFLICTING_STAGE_DATES'
    date = next(iter(dates), None)
    if date and any(m.get('date_precision') != 'ISO_DATE' for m in current if m.get('stage_date')):
        return detail, 'AMBIGUOUS_DATE'
    obs = dict(detail, stage_raw=detail['current_stage'], stage=normalized,
               status='COMPLETED' if normalized in ('COMPLETED','TRANSFER_NOTICE') else 'UNKNOWN',
               stage_date=date, date_basis={'stage_date': 'CURRENT_MILESTONE'} if date else {})
    # A milestone date is NOT a notice date. Only the explicit 이전고시 label establishes that meaning.
    if date and normalized == 'TRANSFER_NOTICE':
        obs.update(notice_date=date)
        obs['date_basis']['notice_date'] = 'OFFICIAL_LABEL'
    obs['raw_content_hash'] = obs['content_hash']
    for field,value in labeled_dates(http.text(detail['evidence_url'])).items():
        if value is None:
            return {}, 'AMBIGUOUS_DATE'
        if obs.get(field) and obs[field]!=value:
            return {}, 'CONFLICTING_OFFICIAL_DATES'
        obs[field]=value
        obs['date_basis'][field]='OFFICIAL_LABEL'
    obs['content_hash'] = digest({'detail_hash': obs['raw_content_hash'], 'candidate': candidate_payload(record)})
    return obs, None


def decision(previous, record, obs):
    if not obs:
        return None
    if obs.get('stage') == 'UNKNOWN':
        return 'UNMAPPED_STAGE'
    if stage_regression((previous or {}).get('stage_raw'), obs.get('stage_raw')):
        return 'STAGE_REGRESSION'
    if obs.get('stage') in ('CANCELLED','ASSOCIATION_DISSOLVED','ASSOCIATION_LIQUIDATION'):
        return 'STATUS_REVIEW_REQUIRED'
    if previous and previous.get('validation_status') == 'VERIFIED':
        for f in ('stage','stage_raw','notice_date','source_date'):
            if obs.get(f) is not None and obs[f] != previous.get(f):
                return 'VERIFIED_PROTECTED'
    return None


def source_for(record, obs):
    source = copy.deepcopy(record['source'])
    if obs:
        source.update(source_url=obs['evidence_url'], content_hash=obs['content_hash'],
            raw_snapshot={'listing': record['field_evidence'], 'detail': obs},
            collected_at=obs['fetched_at'])
    return source


def review(db, record, source, reason, report, apply, observation=None):
    item = {'candidate_key': record['project_id'], 'source_hash': source['content_hash'],
            'reason': reason, 'candidate': candidate_payload(record), 'source': source}
    if observation:
        item['candidate']={'project':item['candidate'],'observation':observation}
    report['reviews'].append({'project_id': record['project_id'], 'reason': reason})
    if apply:
        # On-conflict upsert with ignore-duplicates is append-only; never resets review state.
        headers = db.headers
        db.headers = dict(headers, Prefer='resolution=ignore-duplicates')
        try:
            db.request('POST', 'development_review_queue', item,
                {'on_conflict':'candidate_key,source_hash,reason'})
        finally:
            db.headers = headers


def reconcile(db, result, protected):
    pid = result.get('project_id')
    if not pid or result.get('result') in ('review_required','unchanged','refused','skipped'):
        return
    rows = db.request('GET', 'development_projects', params={'project_id':'eq.'+pid,'select':'*'})
    if len(rows) != 1 or rows[0]['revision'] != result['revision']:
        raise RefreshError('RECONCILIATION_REVISION_FAILED')
    if protected and any(rows[0].get(k) != protected.get(k) for k in
                          ('project_id','external_id','official_authority','project_type','sigungu')):
        raise RefreshError('RECONCILIATION_IDENTITY_FAILED')
    history = db.request('GET', 'development_updates', params={
        'project_id':'eq.'+pid,'to_revision':'eq.'+str(result['revision']),'select':'update_id'})
    if len(history) != 1:
        raise RefreshError('RECONCILIATION_HISTORY_FAILED')


def refresh(*, job='weekly', apply=False, directory='reports/zipon-refresh', limit=10,
            db=None, http=None, districts=None, shp=True):
    if not 1 <= limit <= 100:
        raise RefreshError('INVALID_CANARY_LIMIT')
    db = db or Database(apply)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    http = http or OfficialHTTP(directory / 'raw')
    run_id = str(uuid.uuid4())
    report = {'version':VERSION,'run_id':run_id,'started_at':now(),'dry_run':not apply,
              'job':job,'status':'RUNNING','sources':[],'reviews':[],'results':[], 'errors':[],
              'counts':{'new':0,'changed':0,'unchanged':0,'source_updated':0,'review_required':0},
              'before':{},'after':{},'spatial':[]}
    started, lease = False, False
    state = {}
    try:
        if apply:
            lease = db.request('POST','rpc/zipon_refresh_lease',{'p_owner':run_id})
            if not lease:
                raise RefreshError('CONCURRENT_REFRESH_REFUSED')
            db.request('POST','development_collection_runs',{'run_id':run_id,
                'source_name':'ZIP:ON automated '+job,'source_type':'OFFICIAL_WEBSITE',
                'collector_version':VERSION,'dry_run':False,'scope':{'job':job}})
            started = True
        known = db.rows('development_projects')
        sources = db.rows('development_project_sources',
                         'source_id,project_id,source_url,content_hash,collected_at,evidence')
        report['before'] = coverage(known)
        if apply:
            saved = db.storage('state.json')
            state = json.loads(saved) if saved else {}
        collection = collector.collect(fetch=http.get,districts=districts or collector.SEOUL_DISTRICTS)
        report['sources'] = collection['runs']
        if any(r['source']=='seoul_moa' and r['status']!='SUCCEEDED' for r in collection['runs']):
            try:
                cancellations=collect_moa_cancellations(http)
                report['sources'].append({'source':'moa_official_cancellations','status':'SUCCEEDED',
                    'source_complete':True,'scope':'OFFICIAL_CANCELLATIONS_ONLY','found':len(cancellations),'errors':[]})
                for item in cancellations:
                    report['reviews'].append({'project_id':None,'reason':'MOA_CANCELLATION_REVIEW'})
                    if apply:
                        db.headers=dict(db.headers,Prefer='resolution=ignore-duplicates')
                        try:
                            db.request('POST','development_review_queue',{
                              'candidate_key':'moa-cancellation:'+digest({'name':item['official_name'],'sigungu':item['sigungu']}),
                              'source_hash':item['content_hash'],'reason':'MOA_CANCELLATION_REVIEW','candidate':item,
                              'source':{'source_name':'Official Moa cancellation','source_url':item['source_url'],
                                        'is_official':True,'raw_snapshot':item}},
                              {'on_conflict':'candidate_key,source_hash,reason'})
                        finally:
                            db.headers.pop('Prefer',None)
            except SourceError as exc:
                report['sources'].append({'source':'moa_official_cancellations','status':'FAILED',
                                         'source_complete':False,'errors':[str(exc)]})
        notice_targets=set()
        try:
            notices=collect_notices(http,state.get('notice_ids',[]))
            report['sources'].append({k:v for k,v in notices.items() if k not in ('items','seen','target_aliases')})
            report['notices']=[{k:v for k,v in n.items() if k!='raw_snapshot'} for n in notices['items']]
            notice_targets=set(notices['target_aliases'])
            if notices['source_complete']:
                state['notice_ids']=notices['seen']
            for n in notices['items']:
                # Documents without structured project/field meaning remain review evidence.
                report['reviews'].append({'project_id':None,'reason':'OFFICIAL_NOTICE_REVIEW','notice_id':n['notice_id']})
                if apply:
                    db.headers=dict(db.headers,Prefer='resolution=ignore-duplicates')
                    try:
                        db.request('POST','development_review_queue',{
                            'candidate_key':'notice:'+n['notice_id'],'source_hash':n['content_hash'],
                            'reason':'OFFICIAL_NOTICE_REVIEW','candidate':{k:v for k,v in n.items() if k!='raw_snapshot'},
                            'source':{'source_name':'Official notice','source_url':n['source_url'],'is_official':True,
                                      'raw_snapshot':n['raw_snapshot']}},
                            {'on_conflict':'candidate_key,source_hash,reason'})
                    finally:
                        db.headers.pop('Prefer',None)
        except SourceError as exc:
            report['sources'].append({'source':'official_notices','status':'FAILED','source_complete':False,'errors':[str(exc)]})
        records = collection['records']
        complete = {r['source_url'] for r in collection['runs'] if r['source_complete']}
        existing = {p['project_id']:p for p in known}
        sys.path.insert(0,str(ROOT/'scripts'))
        import analyze_seoul_polygon_source as polygons
        protected_ids = polygons.conflicted_ids()
        written = 0
        all_seen = set()
        for record in sorted(records,key=lambda r:r['project_id']):
            previous, reason = identity(record,known,records)
            if previous:
                record['project_id'] = previous['project_id']
            all_seen.add(record['project_id'])
            if record['project_id'] in protected_ids:
                reason = reason or 'PROTECTED_IDENTITY'
            if record['source']['source_url'] not in complete:
                continue
            obs = {}
            review_obs = {}
            if not reason:
                same = any(s['project_id']==record['project_id'] and
                    (s['content_hash']==record['source']['content_hash'] or
                     ((s.get('evidence') or {}).get('observation') or {}).get('listing_content_hash')==record['source']['content_hash']) for s in sources)
                if same and job != 'monthly' and record.get('external_id') not in notice_targets:
                    report['counts']['unchanged'] += 1
                    continue
                try:
                    obs, detail_reason = observation(record,http)
                    if detail_reason:
                        review_obs = obs
                        if detail_reason not in ('AMBIGUOUS_DATE','CONFLICTING_STAGE_DATES','CONFLICTING_OFFICIAL_DATES','IDENTITY_OR_FRAME_UNRESOLVED'):
                            report['errors'].append({'source':'official_detail','code':detail_reason})
                        # Safe candidate registration remains possible with listing evidence.
                    if detail_reason:
                        obs = {}
                        if detail_reason in ('AMBIGUOUS_DATE','CONFLICTING_STAGE_DATES','CONFLICTING_OFFICIAL_DATES','IDENTITY_OR_FRAME_UNRESOLVED'):
                            reason = detail_reason
                    else:
                        obs['listing_content_hash'] = record['source']['content_hash']
                    reason = reason or decision(previous,record,obs)
                except SourceError as exc:
                    report['errors'].append({'source':'official_detail','code':str(exc)})
            source = source_for(record,review_obs or obs)
            if reason:
                review(db,record,source,reason,report,apply,observation=review_obs or obs)
                continue
            semantic_same = any(s['project_id']==record['project_id'] and s['content_hash']==source['content_hash']
                                and s['source_url']==source['source_url'] for s in sources)
            if semantic_same:
                report['counts']['unchanged'] += 1
                continue
            if apply and written >= limit:
                report['errors'].append({'code':'WRITE_BUDGET_DEFERRED'})
                continue
            if apply:
                # Persist the exact public evidence before any project mutation.
                for obj in http.objects:
                    if not obj.get('stored'):
                        db.storage('objects/'+obj['sha256'],Path(obj['path']).read_bytes())
                        obj['stored']=True
                try:
                    result = db.request('POST','rpc/zipon_refresh_project',{
                        'p_candidate':candidate_payload(record),'p_source':source,'p_observation':obs,
                        'p_expected_revision':(previous or {}).get('revision',0),'p_run_id':run_id})
                    reconcile(db,result,previous)
                except RefreshError as exc:
                    report['errors'].append({'project_id':record['project_id'],'code':str(exc)})
                    continue
                written += 1
            else:
                result = {'project_id':record['project_id'],'result':'new' if previous is None else 'changed',
                          'dry_run':True,'observation':obs}
            report['results'].append(result)
            result['change_types']=change_types(previous,record,obs)
            kind = result.get('result','unchanged')
            report['counts'][kind] = report['counts'].get(kind,0)+1
        # Missing detection is per source, per completed scope; never compare against unseen districts.
        scope = set(collection['districts'])
        for row in known:
            row_urls = {s['source_url'] for s in sources if s['project_id']==row['project_id']}
            if row['project_id'] not in all_seen and row.get('sigungu') in scope and row_urls & complete:
                report['reviews'].append({'project_id':row['project_id'],'reason':'SOURCE_MISSING'})
                if apply and written < limit:
                    result=db.request('POST','rpc/zipon_record_source_missing',{
                        'p_project_id':row['project_id'],'p_reason':'ABSENT_FROM_COMPLETE_SCOPED_SOURCE','p_run_id':run_id})
                    report['results'].append(result)
                    written += 1
        # Fresh rows after field writes are the only basis for spatial matching.
        current = db.rows('development_projects') if apply else known
        # First coordinates only. Reuse provider validation and durable content-addressed cache.
        selected = geocoder.select_provider(lambda key:os.environ.get(key,''),geocoder.requests_get)
        geocode_targets=[p for p in current if p.get('address') and not p.get('location')
                         and p.get('validation_status')!='VERIFIED' and p['project_id'] not in protected_ids
                         and p.get('canonical_source_id')]
        if selected['provider'] and geocode_targets:
            for p in geocode_targets[:max(0,limit-written) if apply else limit]:
                address=geocoder.geocode_address(p['address'])
                cache_path='geocode/'+geocoder.cache_key(address)+'.json'
                cached=db.storage(cache_path) if apply else None
                try:
                    evaluation=json.loads(cached) if cached else None
                    if evaluation and not evaluation.get('coordinate_verified'):
                        at=datetime.fromisoformat(evaluation.get('geocoded_at') or '2000-01-01T00:00:00+00:00')
                        if datetime.now(timezone.utc).timestamp()-at.timestamp()>30*86400:
                            evaluation,cached=None,None
                    evaluation=evaluation or geocoder.evaluate(address,selected['provider'](address))
                except Exception:
                    report['errors'].append({'source':'geocode','project_id':p['project_id'],'code':'GEOCODE_PROVIDER_FAILED'})
                    continue
                if evaluation.get('result_status')=='ERROR':
                    report['errors'].append({'source':'geocode','project_id':p['project_id'],'code':'GEOCODE_PROVIDER_FAILED'})
                    continue
                if evaluation.get('coordinate_verified'):
                    evaluation['geocode_status']='ACCEPTED'
                if apply and not cached:
                    db.storage(cache_path,json.dumps(evaluation,ensure_ascii=False).encode())
                    try:
                        db.headers=dict(db.headers,Prefer='resolution=merge-duplicates')
                        db.request('POST','geocode_cache',{
                          'normalized_address':address,'address_hash':hashlib.sha256(address.encode()).hexdigest(),
                          'normalizer_version':geocoder.CACHE_VERSION,'provider':selected['name'],'provider_version':'v1',
                          'result_status':'MATCHED' if evaluation.get('coordinate_verified') else 'AMBIGUOUS',
                          'location':f"SRID=4326;POINT({evaluation['longitude']} {evaluation['latitude']})" if evaluation.get('coordinate_verified') else None,
                          'matched_address':evaluation.get('matched_address'),'accuracy':evaluation.get('accuracy') or 'UNKNOWN',
                          'source_url':evaluation.get('endpoint'),'raw_snapshot':evaluation,'collected_at':now(),
                          'expires_at':datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+30*86400,timezone.utc).isoformat()},
                          {'on_conflict':'address_hash,normalizer_version,provider,provider_version'})
                    finally:
                        db.headers.pop('Prefer',None)
                if evaluation.get('geocode_confidence')!='EXACT':
                    report['spatial'].append({'project_id':p['project_id'],'kind':'LOCATION','result':'review_required'})
                    if apply:
                        src={'content_hash':digest(evaluation),'source_url':'https://cleanup.seoul.go.kr/',
                             'is_official':True,'source_name':'Official address geocode','raw_snapshot':evaluation}
                        review(db,dict(p,source=src),src,'LOCATION_CANDIDATE',report,True)
                    continue
                src={'content_hash':digest(evaluation),'source_url':'https://cleanup.seoul.go.kr/',
                     'is_official':True,'source_name':'Official address geocode','raw_snapshot':evaluation}
                if apply:
                    try:
                        result=db.request('POST','rpc/zipon_refresh_spatial',{'p_project_id':p['project_id'],'p_kind':'LOCATION',
                          'p_expected_revision':p['revision'],'p_run_id':run_id,'p_source':src,
                          'p_payload':{'longitude':evaluation['longitude'],'latitude':evaluation['latitude'],
                              'geocode_source':evaluation['geocode_source'],'confidence':'EXACT','evidence':evaluation}})
                        reconcile(db,result,p);report['spatial'].append(result);written+=1
                        if result.get('result')=='location_set':report['counts']['changed']+=1
                    except RefreshError as exc:
                        report['errors'].append({'project_id':p['project_id'],'code':str(exc)})
                else:
                    report['spatial'].append({'project_id':p['project_id'],'kind':'LOCATION','dry_run':True})
            current=db.rows('development_projects') if apply else known
        elif geocode_targets:
            report['errors'].append({'source':'geocode','code':'GEOCODER_CONFIG_REQUIRED'})
        if shp and job in ('weekly','monthly','canary'):
            try:
                previous_manifest=state.get('shp')
                if apply and previous_manifest:
                    archive_body=db.storage('archives/'+previous_manifest['sha256']+'.zip')
                    if archive_body:
                        (directory/'shp').mkdir(parents=True,exist_ok=True)
                        (directory/'shp'/(previous_manifest['sha256']+'.zip')).write_bytes(archive_body)
                manifest = acquire_archive(http,directory/'shp',previous_manifest,force=job=='monthly')
                archive = manifest['path']
                if apply and manifest.get('downloaded',True):
                    db.storage('archives/'+manifest['sha256']+'.zip',Path(archive).read_bytes())
                polygon_projects=[]
                from services.development import _point
                for p in current:
                    lon,lat=_point(p.get('location'))
                    name,rules=polygons.normalize_name(p['project_name'])
                    polygon_projects.append(dict(project_id=p['project_id'],project_name=p['project_name'],
                        normalized_name=name,normalization_rules=rules,official_external_id=p.get('external_id'),
                        project_type=p['project_type'],program=None,district=p.get('sigungu'),dong=p.get('dong'),
                        address=p.get('address'),lot_number=None,longitude=lon,latitude=lat))
                # Do not skip pending work solely because the archive is unchanged.
                fingerprint=digest([(p['project_id'],p.get('revision')) for p in current])
                if manifest['unchanged'] and state.get('shp',{}).get('db_fingerprint') == fingerprint:
                    report['shp']={'status':'SOURCE_UNCHANGED','sha256':manifest['sha256']}
                else:
                    survey,rows,features=polygons.build(archive,projects=polygon_projects,protected=protected_ids)
                    validate_survey(survey,state.get('shp'))
                    report['shp']={'status':'SUCCEEDED','version':manifest['version'],'sha256':manifest['sha256'],
                        'crs':survey['source_crs_label'],'schema':survey['schema'],'candidates':len(features)}
                    feature_map={f['properties']['zipon_project_id']:f for f in features}
                    from apply_zipon_polygons import evidence_for
                    for r in rows:
                        pid=r['zipon_project_id']; p=next(x for x in current if x['project_id']==pid)
                        if not r['auto_apply_candidate']:
                            continue
                        feature=feature_map[pid]
                        src={'source_name':'서울시 공식 UQ120','source_type':'OFFICIAL_WEBSITE','source_url':PORTAL,
                             'content_hash':digest(feature['geometry']),'is_official':True,'collected_at':now(),
                             'raw_snapshot':{'archive_hash':manifest['sha256'],'version':manifest['version']}}
                        source_meta=dict(polygons.SOURCE,version=manifest['version'],source_sha256=manifest['sha256'])
                        payload={'geometry':feature['geometry'],'geometry_source':polygons.SOURCE['dataset'],
                                 'evidence':evidence_for(r,source_meta)}
                        if p.get('geometry') and same_geometry(p.get('geometry'),feature['geometry']):
                            continue
                        if not apply:
                            report['spatial'].append({'project_id':pid,'kind':'BOUNDARY','dry_run':True})
                        elif written < limit:
                            try:
                                result=db.request('POST','rpc/zipon_refresh_spatial',{'p_project_id':pid,'p_kind':'BOUNDARY',
                                    'p_payload':payload,'p_source':src,'p_expected_revision':p['revision'],'p_run_id':run_id})
                                reconcile(db,result,p);report['spatial'].append(result);written+=1
                                if result.get('result')=='boundary_set':report['counts']['changed']+=1
                            except RefreshError as exc:
                                report['errors'].append({'project_id':pid,'code':str(exc)})
                    manifest['db_fingerprint']=fingerprint
                    manifest['schema_fingerprint']=survey['schema_fingerprint']
                state['shp']=manifest
            except (SourceError,SystemExit,ValueError) as exc:
                report['shp']={'status':'SOURCE_UNAVAILABLE','code':str(exc) if isinstance(exc,SourceError) else 'SHP_SCHEMA_OR_CRS_FAILED'}
                report['errors'].append({'source':'shp','code':report['shp']['code']})
        if apply:
            # Durable raw evidence is a prerequisite for success, not an ephemeral Actions cache.
            for obj in http.objects:
                db.storage('objects/'+obj['sha256'],Path(obj['path']).read_bytes())
            db.storage('state.json',json.dumps(state,ensure_ascii=False).encode())
        report['after']=coverage(db.rows('development_projects') if apply else known)
        for source_run in report['sources']:
            for code in source_run.get('errors',[]):
                report['errors'].append({'source':source_run['source'],'code':code})
        failed=any(r.get('status')!='SUCCEEDED' for r in report['sources']) or bool(report['errors'])
        report['status']='PARTIAL' if failed else 'SUCCEEDED'
    except Exception as exc:
        report['status']='FAILED'
        report['errors'].append({'code':str(exc) if isinstance(exc,(RefreshError,SourceError)) else type(exc).__name__})
    finally:
        report['finished_at']=now()
        report['counts']['review_required'] += len(report['reviews'])
        if started:
            try:
                db.storage('runs/'+run_id+'.json',json.dumps(report,ensure_ascii=False).encode())
                db.request('PATCH','development_collection_runs',{
                    'finished_at':report['finished_at'],'status':report['status'],
                    'source_complete':report['status']=='SUCCEEDED','new_count':report['counts']['new'],
                    'changed_count':report['counts']['changed'],'unchanged_count':report['counts']['unchanged'],
                    'validation_failed_count':len(report['errors']),'missing_count':sum(r['reason']=='SOURCE_MISSING' for r in report['reviews']),
                    'errors':report['errors'],'scope':{'job':job,'sources':report['sources'],'summary':report['counts'],
                        'before':report['before'],'after':report['after'],'shp':report.get('shp')}},
                    {'run_id':'eq.'+run_id})
            except Exception:
                report['status']='FAILED';report['errors'].append({'code':'RUN_FINALIZATION_FAILED'})
        if lease:
            try:
                db.request('POST','rpc/zipon_refresh_lease',{'p_owner':run_id,'p_release':True})
            except Exception:
                report['errors'].append({'code':'LEASE_RELEASE_FAILED'})
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def coverage(rows):
    return {'projects':len(rows),'locations':sum(p.get('location') is not None for p in rows),
            'verified_boundaries':sum(bool(p.get('geometry_verified')) for p in rows),
            'verified_projects':sum(p.get('validation_status')=='VERIFIED' for p in rows)}


def change_types(previous,record,obs):
    if previous is None:return ['NEW_PROJECT']
    result=['SOURCE_UPDATED']
    for field,kind in [('stage_raw','STAGE_CHANGED'),('notice_date','NOTICE_DATE_CHANGED'),
                       ('status','STATUS_CHANGED'),('address','ADDRESS_CHANGED')]:
        value=obs.get(field) if field in obs else record.get(field)
        if field=='status' and value=='UNKNOWN':continue
        if value is not None and value!=previous.get(field):result.append(kind)
    return result


def validate_survey(survey,previous=None):
    if survey.get('outside_seoul') or not survey.get('converted_to_epsg4326'):
        raise SourceError('CRS_SANITY_FAILED')
    if any(not (survey.get('schema',{}).get(role) or {}).get('used_for_matching') for role in ('name','district')):
        raise SourceError('UNCONFIRMED_SHP_SCHEMA')
    previous_schema=(previous or {}).get('schema_fingerprint')
    if previous_schema and previous_schema!=survey.get('schema_fingerprint'):
        raise SourceError('SHP_SCHEMA_CHANGED_REVIEW_REQUIRED')


def same_geometry(stored, candidate):
    """Compare actual shapes; never treat an unknown EWKB value as unchanged."""
    try:
        from shapely import wkb
        from shapely.geometry import shape
        existing = shape(stored) if isinstance(stored,dict) else wkb.loads(bytes.fromhex(stored))
        return existing.equals(shape(candidate))
    except Exception:
        return False
