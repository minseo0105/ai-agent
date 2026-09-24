"""Conservative, source-linked review observations; never official course facts.
Regex observations are candidates until a human verifies source, scope and meaning.
Display consensus requires two independent reviewed authors within the time window.
"""
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, parse_qs, unquote

ROOT=Path(__file__).resolve().parents[1]
STORE=ROOT/'data/golf/review_evidence.json'
LABELS={'fairway':{'wide':'넓다는 의견','narrow':'좁다는 의견'},
        'bunkers':{'many':'벙커가 많다는 의견','few':'벙커가 적다는 의견'},
        'facilities':{'positive':'시설이 좋다는 의견','negative':'시설이 아쉽다는 의견'},
        'maintenance':{'positive':'관리가 좋다는 의견','negative':'관리가 아쉽다는 의견'},
        'green':{'fast':'그린이 빠르다는 의견','slow':'그린이 느리다는 의견'}}
NAMES={'fairway':'페어웨이','bunkers':'벙커','facilities':'시설','maintenance':'코스관리','green':'그린'}
PATTERNS={
 'fairway':{'wide':r'(?:페어웨이|훼어웨이)[^.!?\n]{0,18}넓|넓은\s*(?:페어웨이|훼어웨이)',
            'narrow':r'(?:페어웨이|훼어웨이)[^.!?\n]{0,18}좁|좁은\s*(?:페어웨이|훼어웨이)'},
 'bunkers':{'many':r'벙커[^.!?\n]{0,12}많|많은\s*벙커','few':r'벙커[^.!?\n]{0,12}적(?:다|고|은|었|어|습|게)'},
 'facilities':{'positive':r'(?:시설|클럽하우스|락커|라커|샤워실)[^.!?\n]{0,16}(?:깔끔|깨끗|쾌적|훌륭|좋)',
               'negative':r'(?:시설|클럽하우스|락커|라커|샤워실)[^.!?\n]{0,16}(?:낡|노후|불편|아쉽|아쉬|더럽)'},
 'maintenance':{'positive':r'(?:코스|잔디|그린|페어웨이)[^.!?\n]{0,12}관리[^.!?\n]{0,12}(?:좋|잘|훌륭)',
                'negative':r'(?:코스|잔디|그린|페어웨이)[^.!?\n]{0,12}관리[^.!?\n]{0,12}(?:나쁘|아쉽|아쉬|안\s*좋|안\s*되)'},
 'green':{'fast':r'그린(?:\s*스피드|\s*속도)?[^.!?\n]{0,10}(?:빠르(?:다|고|네|게|더|지|며|던)|빠른|빨랐)',
          'slow':r'그린(?:\s*스피드|\s*속도)?[^.!?\n]{0,10}(?:느리|느린|느렸)'}}

def canonical(url):
    u=urlsplit(url);host=(u.hostname or '').lower().removeprefix('www.')
    q=parse_qs(u.query);parts=u.path.strip('/').split('/')
    if host in ('blog.naver.com','m.blog.naver.com'):
        account=q.get('blogId',[parts[0] if parts else ''])[0]
        post=q.get('logNo',[parts[1] if len(parts)>1 else ''])[0]
        return f'https://blog.naver.com/{account}/{post}',f'naver:{account}'
    if host.endswith('.tistory.com'):return f'https://{host}{u.path}',host
    return f'https://{host}{u.path}'+('?' + u.query if u.query else ''),host

def clean(text):
    text=re.sub(r'!\[[^\]]*\]\([^\n]*?\)',' ',text or '')
    text=re.sub(r'\[([^\]]+)\]\([^\n]*?\)',r'\1',text)
    return text.replace('**','').replace('\u200b','')

def published(raw,text):
    for k in ('published_date','published_at'):
        value=str(raw.get(k) or '')[:10]
        try:return date.fromisoformat(value).isoformat(),'provider_metadata'
        except ValueError:pass
    # Only date lines near article header; never infer from arbitrary body/event dates.
    head=text[:2200]
    m=re.search(r'(?:^|\n)\s*(?:by[^\n]{0,60}?\s+)?(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\.(?:\s+\d{1,2}:\d{2}|\s*(?:\n|$))',head)
    if m:
        try:return date(*map(int,m.groups())).isoformat(),'article_header'
        except ValueError:pass
    return '', 'unknown'

def extract(raw,club,observed_at):
    from services.golf_tavily import _name_keys
    title=raw.get('title') or '';url=raw.get('url') or ''
    if not url.startswith(('https://','http://')):return None
    host=(urlsplit(url).hostname or '').removeprefix('www.')
    official=(urlsplit(club.get('official_url') or '').hostname or '').removeprefix('www.')
    if host==official or host in ('instagram.com','youtube.com','youtu.be','facebook.com'):return None
    core=min(_name_keys(club['name']),key=len)
    normalized=re.sub(r'\s+','',title).lower()
    # Short names need explicit golf suffix, avoiding region names and other branches.
    identified=(core in normalized if len(core)>=3 else bool(re.search(re.escape(core)+r'(?:cc|gc|컨트리|골프)',normalized)))
    if not identified:return None
    body=clean(raw.get('raw_content') or raw.get('content') or '')
    # Do not classify snippets as complete reviews. Keep them as candidates only.
    is_full=bool(raw.get('raw_content')) and len(body)>500
    day,method=published(raw,body)
    source,author=canonical(url)
    sponsored=bool(re.search(r'협찬|체험단|제공받|소정의\s*(?:원고료|수수료)|회원권\s*(?:분양|매매)',body))
    first_person=bool(re.search(r'다녀왔|다녀온|라운딩했|라운드했|방문했|플레이했|저는|우리는|동반자',body))
    # Remove typical recommendation/footer content before finding evidence.
    for marker in ('이 블로그 인기글','이 블로그의 체크인','이 카테고리 글','관련글','다른 글 더보기','카테고리의 다른 글'):
        body=body.split(marker)[0]
    snippets=[];word_budget=25
    for sentence in re.split(r'\n+|(?<=[.!?])\s+',body):
        sentence=sentence.strip(' >#-*\t')
        if not 8<=len(sentence)<=220:continue
        hits=[]
        for dim,labels in PATTERNS.items():
            for label,pattern in labels.items():
                if re.search(pattern,sentence):hits.append((dim,label))
        if not hits:continue
        words=sentence.split()
        if len(words)>word_budget:continue
        word_budget-=len(words)
        scoped=bool(re.search(r'\d+\s*번?\s*홀|(?:동|서|남|북|마스터|챔피온|밸리|레이크)\s*코스|보다|않|아니|없|듯|겠|하지만|반면',sentence))
        for dim,label in hits:
            fingerprint=hashlib.sha256((club['id']+source+dim+label+sentence).encode()).hexdigest()[:24]
            snippets.append({'id':fingerprint,'dimension':dim,'label':label,'evidence':sentence,
                'scope':'needs_scope_review' if scoped else 'unspecified',
                'status':'needs_review','confidence':'unreviewed_extraction'})
        if word_budget<3:break
    return {'source':source,'original_url':url,'author_key':author,'title':title,'published_at':day,
            'date_method':method,'observed_at':observed_at,'full_text_available':is_full,
            'sponsored_suspected':sponsored,'first_person_signal':first_person,
            'content_hash':hashlib.sha256(body.encode()).hexdigest(),'observations':snippets}

def summarize(entry,today=None):
    today=today or date.today();result={}
    for dim in LABELS:
        by_author={};links=[]
        seen_hashes=set()
        for source in entry.get('sources',[]):
            try:age=(today-date.fromisoformat(source.get('published_at',''))).days
            except ValueError:continue
            if not 0<=age<=(365 if dim in ('maintenance','green','facilities') else 730):continue
            if source.get('sponsored_suspected') or not source.get('full_text_available'):continue
            if source.get('content_hash') in seen_hashes:continue
            seen_hashes.add(source.get('content_hash'))
            for obs in source.get('observations',[]):
                if obs.get('dimension')!=dim or obs.get('status')!='human_reviewed' or obs.get('scope')!='whole_course':continue
                if not obs.get('reviewed_at') or not obs.get('evidence'):continue
                label=obs.get('label')
                if label not in LABELS[dim]:continue
                by_author.setdefault(source['author_key'],set()).add(label)
                links.append({'url':source['source'],'title':source['title'],'date':source['published_at'],'preview':obs['evidence']})
        counts=Counter(label for labels in by_author.values() for label in labels)
        n=len(by_author)
        if n==1:
            verdict=(LABELS[dim][next(iter(counts))] if len(counts)==1 else '의견 엇갈림')+' · 후기 1명, 추가 확인 필요';status='single_review'
        elif n<2:verdict='검증된 독립 후기 부족';status='insufficient'
        elif len(counts)>1:verdict='후기 의견 엇갈림';status='mixed'
        else:verdict=LABELS[dim][next(iter(counts))];status='supported'
        result[dim]={'name':NAMES[dim],'verdict':verdict,'status':status,'authors':n,'counts':dict(counts),'evidence':links,'confidence':'review_consensus' if status=='supported' else 'insufficient_or_mixed'}
    return result

def detail_block(club_id):
    try:data=json.loads(STORE.read_text(encoding='utf-8'))
    except (OSError,ValueError):return None
    entry=data.get('clubs',{}).get(club_id)
    if not entry:return None
    summary=summarize(entry)
    links=[];scoped=[]
    for s in entry.get('sources',[]):
        try:age=(date.today()-date.fromisoformat(s.get('published_at',''))).days
        except ValueError:continue
        if not 0<=age<=730 or s.get('sponsored_suspected') or not s.get('full_text_available') or not s.get('first_person_signal'):continue
        approved=[o for o in s.get('observations',[]) if o.get('status')=='human_reviewed']
        links.append({'url':s['source'],'title':s['title'],'date':s['published_at'],'year':int(s['published_at'][:4]),
                      'preview':approved[0]['evidence'] if approved else '수집한 후기 원문 · 특징은 검토 중'})
        for o in approved:
            if o.get('scope')=='whole_course':continue
            if o['dimension'] in ('maintenance','green','facilities') and age>365:continue
            scoped.append({'name':NAMES[o['dimension']]+' · '+o['scope'],
                           'verdict':LABELS[o['dimension']][o['label']]+' · 개별 후기',
                           'sub':s['published_at']+' · 골프장 전체로 일반화하지 않음'})
    return {'observed_at':entry.get('observed_at'),'source_count':len(entry.get('sources',[])),
            'candidate_count':sum(len(s.get('observations',[])) for s in entry.get('sources',[])),
            'dimensions':summary,'links':links,'scoped_cards':scoped,
            'note':'후기 의견이며 공식 제원이 아닙니다. 미검토 후보는 검색 조건에 사용하지 않습니다.'}
