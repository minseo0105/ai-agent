"""Deterministic, offline identity refinement. No database/network/config imports."""
import copy
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit
import uuid

TYPE_MAP={'RECONSTRUCTION':'RECONSTRUCTION','REDEVELOPMENT':'REDEVELOPMENT',
          'SHINTONG':'FAST_TRACK','FAST_TRACK':'FAST_TRACK','MOATOWN':'MOATOWN'}
def compact(value):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',value or '')).lower()

def normalize_name(value):
    text=compact(value)
    # Keep parenthetical content and every zone/phase number; only remove formatting.
    text=re.sub(r'[()\[\]{}·ㆍ,._]','',text)
    suffixes=('조합설립추진위원회','추진위원회','정비사업조합','정비사업구역','사업조합',
              '주택재건축정비사업','주택재개발정비사업','재건축정비사업','재개발정비사업',
              '주택재건축','주택재개발','재정비촉진구역','아파트','구역','재건축사업','재개발사업','재건축','재개발','조합')
    while True:
        previous=text
        for suffix in suffixes:
            if text.endswith(suffix):text=text[:-len(suffix)];break
        if text==previous:break
    return text

def normalize_address(value):
    text=compact(value).replace('서울특별시','서울').replace('서울시','서울')
    return re.sub(r'번지(?=일대|$)','',text).removesuffix('일대')

def official_key(row):
    source=row.get('source') or {}
    system=(row.get('official_authority') or '').strip().lower()
    external=(row.get('external_id') or '').strip()
    if source.get('is_official') is True and system and external:
        return (system,external)
    return None

def tokens(value):
    # Separate zone numbers/letters cannot be merged even when similarity is high.
    return tuple(re.findall(r'[a-z]?\d+(?:-\d+)*|[a-z](?=구역)',compact(value)))

def normalized(row):
    return {'name':normalize_name(row.get('project_name')), 'district':compact(row.get('sigungu')),
            'dong':compact(row.get('dong')), 'address':normalize_address(row.get('address')),
            'type':TYPE_MAP.get(row.get('project_type'),'OTHER')}

def probable(a,b):
    x,y=normalized(a),normalized(b)
    if not x['district'] or x['district']!=y['district'] or not x['name'] or not y['name']:return None
    if x['dong'] and y['dong'] and x['dong']!=y['dong']:return None
    if tokens(a.get('project_name')) and tokens(b.get('project_name')) and tokens(a.get('project_name'))!=tokens(b.get('project_name')):return None
    compatible=x['type']==y['type']
    scope_pair='FAST_TRACK' in (x['type'],y['type']) and {x['type'],y['type']}<= {'FAST_TRACK','REDEVELOPMENT','RECONSTRUCTION'}
    if not compatible and not scope_pair:return None
    if x['name']==y['name']:
        return 'NORMALIZED_NAME_AND_DISTRICT' if compatible else 'POSSIBLE_PROGRAM_PROJECT_SCOPE'
    ratio=SequenceMatcher(None,x['name'],y['name']).ratio()
    if x['address'] and x['address']==y['address'] and ratio>=0.65:return 'EXACT_ADDRESS_AND_SIMILAR_NAME'
    if compatible and tokens(a.get('project_name')) and tokens(a.get('project_name'))==tokens(b.get('project_name')) and ratio>=0.85:
        return 'SAME_DISTRICT_TYPE_ZONE_AND_SIMILAR_NAME'
    if compatible and x['dong'] and x['dong']==y['dong'] and ratio>=0.9:return 'SAME_DONG_AND_SIMILAR_NAME'
    return None

def unique_values(values):
    indexed={json.dumps(v,ensure_ascii=False,sort_keys=True):v for v in values if v not in (None,'',[],{})}
    return [indexed[k] for k in sorted(indexed)]

def refine(records,canary=()):
    rows=sorted(copy.deepcopy(records),key=lambda r:r['project_id'])
    groups=defaultdict(list)
    for row in rows:
        key=official_key(row);n=normalized(row)
        # Conflicting district/type must remain separate even with a matching ID.
        group=('official',*key,n['district'],n['type'],tokens(row.get('project_name'))) if key and n['district'] else ('candidate',row['project_id'])
        groups[group].append(row)
    canonical=[];mapping={};canary_ids={r['project_id'] for r in canary}
    for group,members in sorted(groups.items()):
        cid=str(uuid.uuid5(uuid.NAMESPACE_URL,'zipon-canonical-v1:'+json.dumps(group,ensure_ascii=False)))
        conflicts=[]
        def field(name,values):
            choices=unique_values(values)
            if len(choices)>1:conflicts.append({'field':name,'values':choices});return None
            return choices[0] if choices else None
        names=unique_values([r.get('project_name') for r in members])
        normalized_names=unique_values([normalize_name(n) for n in names])
        name=field('project_name',names) if len(normalized_names)>1 else (names[0] if len(names)==1 else normalized_names[0])
        addresses=unique_values([normalize_address(r.get('address')) for r in members])
        address=field('address',addresses)
        stages=unique_values([r.get('stage') for r in members]);raw_stages=unique_values([r.get('stage_raw') for r in members])
        stage=field('stage',stages)
        if len(raw_stages)>1:conflicts.append({'field':'stage_raw','values':raw_stages})
        status=field('status',[r.get('status') for r in members])
        sources=unique_values([r.get('source') for r in members])
        external=unique_values([{'system':official_key(r)[0],'external_id':official_key(r)[1]} for r in members if official_key(r)])
        point=field('representative_point',[r.get('location') for r in members])
        boundary=field('boundary',[r.get('geometry') for r in members])
        existing=sorted(canary_ids & {r['project_id'] for r in members})
        if len(existing)>1:conflicts.append({'field':'existing_canary_ids','values':existing})
        db_id=existing[0] if len(existing)==1 else (members[0]['project_id'] if len(members)==1 else None)
        result={'canonical_id':cid,'project_name':name,'original_names':names,
          'normalized_name':field('normalized_name',normalized_names),
          'project_type':normalized(members[0])['type'],'original_types':unique_values([r.get('project_type') for r in members]),
          'district':field('district',[r.get('sigungu') for r in members]),
          'dong':field('dong',[r.get('dong') for r in members]),'address':address,
          'original_addresses':unique_values([r.get('address') for r in members]),
          'official_external_ids':external,'source_urls':unique_values([s.get('source_url') for s in sources]),
          'source_count':len(sources),'sources':sources,'stage':stage,'observed_stages':raw_stages,'status':status,
          'collected_at':max((s.get('collected_at') or '' for s in sources),default='') or None,
          'validation_status':field('validation_status',[r.get('validation_status') for r in members]),
          'identity_confidence':'HIGH' if external else 'LOW',
          'identity_basis':['OFFICIAL_SYSTEM_EXTERNAL_ID'] if external else ['SOURCE_CANDIDATE_ID_ONLY'],
          'representative_point':point,'boundary':boundary,
          'spatial_verification':{'boundary_verified':bool(boundary) and all(r.get('geometry_verified') is True for r in members),
            'point_status':'REVIEW_REQUIRED' if point else 'UNRESOLVED',
            'required_point_fields':['latitude','longitude','geocode_source','geocode_confidence','geocoded_at','address_used'],
            'strategy':['official_coordinates','exact_address_geocode_with_cache','unresolved'],
            'boundary_policy':'OFFICIAL_GIS_WITH_VERIFIED_PROVENANCE_ONLY'},
          'geocoding':{'latitude':None,'longitude':None,'geocode_source':None,'geocode_confidence':'UNRESOLVED','geocoded_at':None,'address_used':address},
          'raw_candidate_count':len(members),'candidate_ids':[r['project_id'] for r in members],
          'raw_candidates':members,'conflicts':conflicts,
          'import_plan':{'db_project_id':db_id,'db_project_type':'SHINTONG' if normalized(members[0])['type']=='FAST_TRACK' else normalized(members[0])['type'],
             'already_in_canary':bool(existing),'requires_identity_review':not bool(external) or bool(conflicts) or db_id is None,
             'source_policy':'PRESERVE_ALL_SOURCE_OBSERVATIONS; never use canonical JSON directly as existing importer payload'}}
        for r in members:mapping[r['project_id']]=cid
        canonical.append(result)
    reviews=[]
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if mapping[a['project_id']]==mapping[b['project_id']]:continue
            same_id=official_key(a) and official_key(a)==official_key(b)
            reason='OFFICIAL_ID_WITH_CONFLICTING_DISTRICT_OR_TYPE' if same_id else probable(a,b)
            if reason:
                reviews.append({'candidate_ids':[a['project_id'],b['project_id']],
                    'canonical_ids':[mapping[a['project_id']],mapping[b['project_id']]],
                    'names':[a.get('project_name'),b.get('project_name')],
                    'reason':reason,'decision':'PROBABLE_DUPLICATE','auto_merge':False,
                    'field_differences':[{'field':k,'values':[a.get(k),b.get(k)]} for k in ('stage_raw','status','address','project_type') if a.get(k) and b.get(k) and a.get(k)!=b.get(k)],
                    'evidence':[{'district':r.get('sigungu'),'type':r.get('project_type'),'address':r.get('address'),
                        'external_id':r.get('external_id'),'source_url':r.get('source',{}).get('source_url')} for r in (a,b)]})
    review_ids={i for r in reviews for i in r['canonical_ids']}
    for row in canonical:
        row['duplicate_class']='EXACT_DUPLICATE' if row['raw_candidate_count']>1 else 'PROBABLE_DUPLICATE' if row['canonical_id'] in review_ids else 'UNIQUE'
        row['import_plan']['requires_identity_review'] |= row['canonical_id'] in review_ids
    anomalies=[];external_index=defaultdict(list)
    for row in canonical:
        for name,key in [('missing_name','project_name'),('missing_district','district'),('missing_source','sources'),('missing_url','source_urls')]:
            if not row[key]:anomalies.append({'canonical_id':row['canonical_id'],'issue':name})
        for conflict in row['conflicts']:anomalies.append({'canonical_id':row['canonical_id'],'issue':'conflict','detail':conflict})
        if row['source_count']>10:anomalies.append({'canonical_id':row['canonical_id'],'issue':'excessive_sources'})
        for identity in row['official_external_ids']:external_index[tuple(identity.values())].append(row['canonical_id'])
    for key,ids in external_index.items():
        if len(ids)>1:anomalies.append({'issue':'external_id_multiple_canonical','identity':key,'canonical_ids':ids})
    def metric(predicate):
        count=sum(bool(predicate(r)) for r in canonical)
        return {'count':count,'total':len(canonical),'percent':round(count/len(canonical)*100,2) if canonical else 0}
    report={'original_candidates':len(rows),'canonical_projects':len(canonical),'exact_duplicates_merged':len(rows)-len(canonical),
      'probable_duplicate_pairs':len(reviews),'probable_canonical_projects':len(review_ids),
      'review_pairs_with_field_differences':sum(bool(r['field_differences']) for r in reviews),
      'quality':{'address':metric(lambda r:r['address']),'official_id':metric(lambda r:r['official_external_ids']),
        'official_source':metric(lambda r:any(s.get('is_official') is True and s.get('source_url') for s in r['sources'])),
        'stage':metric(lambda r:r['stage']),'observed_stage':metric(lambda r:r['observed_stages']),
        'known_status':metric(lambda r:r['status'] and r['status']!='UNKNOWN'),
        'coordinates':metric(lambda r:r['representative_point']),
        'verified_polygon':metric(lambda r:r['spatial_verification']['boundary_verified'])},
      'by_district':dict(sorted(Counter(r['district'] or 'MISSING' for r in canonical).items())),
      'by_type':dict(sorted(Counter(r['project_type'] for r in canonical).items())),
      'validation_status':dict(Counter(r['validation_status'] or 'CONFLICT' for r in canonical)),
      'status_distribution':dict(Counter(r['status'] or 'CONFLICT' for r in canonical)),
      'anomalies':anomalies,'conflict_count':sum(len(r['conflicts']) for r in canonical),
      'import_ready':'REVIEW REQUIRED','db_write':False,'canary_preserved':len(canary_ids & set(mapping)),
      'batch_plan':{'maximum_batch_size':10,'automatic_import':False,'review_then_verify_each_batch':True},
      'spatial_gaps':['Official list parsers do not extract coordinates or GIS boundaries.',
                      'No geocoder provider configured; cache alone cannot manufacture coordinates.']}
    return {'format':'zipon-canonical-v1','projects':sorted(canonical,key=lambda r:r['canonical_id'])}, {'pairs':reviews}, report
