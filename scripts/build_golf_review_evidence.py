"""Offline evidence index and completeness audit for the recommendation pool."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--project',default=str(Path(__file__).resolve().parents[1]));ap.add_argument('--output',required=True)
    ap.add_argument('--source-date', default=date.today().isoformat(), type=lambda value: date.fromisoformat(value).isoformat())
    args=ap.parse_args();root=Path(args.project);sys.path.insert(0,str(root))
    # During staging the new policy module is loaded from this script's sibling services.
    import importlib.util
    spec=importlib.util.spec_from_file_location('review_evidence',Path(__file__).resolve().parents[1]/'services/golf_review_evidence.py')
    policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
    from services import golf_service as gs
    _,_,pool=gs.load_pools();today=date.today().isoformat()
    folder=root/'data/golf/runtime'/('refinement_'+args.source_date)
    previous=root/'data/golf/review_evidence.json'
    old=json.loads(previous.read_text(encoding='utf-8')) if previous.exists() else {}
    output={'schema_version':1,'as_of':today,'scope_count':len(pool),'clubs':{}};audit=[]
    for club in sorted(pool,key=lambda r:r['id']):
        p=folder/(hashlib.sha256(club['id'].encode()).hexdigest()[:20]+'.json')
        raw=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        sources=[];seen=set()
        prior=old.get('clubs',{}).get(club['id'],{})
        prior_by_url={s['source']:s for s in prior.get('sources',[])}
        for r in raw.get('results',[]):
            source=policy.extract(r,club,raw.get('observed_at') or args.source_date)
            if not source or source['source'] in seen:continue
            seen.add(source['source'])
            prev=prior_by_url.get(source['source'],{})
            if prev.get('content_hash')==source['content_hash']:
                if prev.get('first_person_review_note'):
                    source['first_person_signal']=prev['first_person_signal']
                    source['first_person_review_note']=prev['first_person_review_note']
                reviewed={o['id']:o for o in prev.get('observations',[])}
                source['observations']=[reviewed.get(o['id'],o) for o in source['observations']]
            elif any(o.get('status')=='human_reviewed' for o in prev.get('observations',[])):
                source={**prev,'pending_revision':source}
            sources.append(source)
        # Failed or sparse collections never erase previously saved evidence.
        sources.extend(s for s in prior.get('sources',[]) if s['source'] not in seen)
        entry={'id':club['id'],'name':club['name'],'observed_at':raw.get('observed_at') or prior.get('observed_at') or args.source_date,'collection_status':raw.get('status','not_collected'),'sources':sources}
        output['clubs'][club['id']]=entry
        missing=[]
        for key in ('phone','official_url','address','holes'):
            if club.get(key) in (None,'',[],{},'unknown'):missing.append(key)
        if not (club.get('pricing') or {}).get('fee_records'):missing.append('green_fee')
        for key in ('cart','caddie'):
            if ((club.get('operations') or {}).get(key) or {}).get('fee_team') is None:missing.append(key+'_fee')
        audit.append({'id':club['id'],'name':club['name'],'missing_fields':missing,'review_sources':len(sources),'dated_sources':sum(bool(s['published_at']) for s in sources),'candidate_observations':sum(len(s['observations']) for s in sources),'collection_status':entry['collection_status']})
    dest=Path(args.output);dest.mkdir(parents=True,exist_ok=True)
    (dest/'review_evidence.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    stats={'scope':len(pool),'clubs_with_sources':sum(bool(a['review_sources']) for a in audit),'sources':sum(a['review_sources'] for a in audit),'clubs_with_candidates':sum(bool(a['candidate_observations']) for a in audit),'candidate_observations':sum(a['candidate_observations'] for a in audit),'dated_sources':sum(a['dated_sources'] for a in audit),'items':audit}
    (dest/'refinement_243_audit.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in stats.items() if k!='items'},ensure_ascii=False))
if __name__=='__main__':main()
