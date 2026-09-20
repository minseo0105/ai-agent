"""Fast GPT semantic analyzer: shortlist + compact context + parallel batches + 24h disk cache."""
import json, re, hashlib, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

DIMS={"difficulty":"난이도","fairway":"페어웨이","green":"그린","maintenance":"코스관리","facilities":"시설"}
LABELS={
"difficulty":{"hard":"어려운 편","easy":"쉬운 편"},
"fairway":{"wide":"넓은 편","narrow":"좁은 편"},
"green":{"fast":"빠른 편","slow":"느린 편"},
"maintenance":{"positive":"관리 좋음","negative":"관리 아쉬움"},
"facilities":{"positive":"시설 좋음","negative":"시설 아쉬움"}}
VALID={
"difficulty":{"hard","easy","mixed","unknown"},"fairway":{"wide","narrow","mixed","unknown"},
"green":{"fast","slow","mixed","unknown"},"maintenance":{"positive","negative","mixed","unknown"},
"facilities":{"positive","negative","mixed","unknown"}}
CACHE_DIR=Path("data/golf/gpt_cache")
CACHE_TTL=24*60*60
MAX_REVIEWS=10
BATCH_SIZE=5
MAX_CONTEXT_CHARS=2200

GOLF_RE=re.compile(
 r"(레이크\s*사이드|라운딩|라운드|티샷|세컨|페어웨이|그린|핀|벙커|해저드|"
 r"잔디|코스|홀|클럽하우스|락커|샤워|난이도|전반|후반|드라이버)", re.I)

def _compact(text):
    """Keep only golf-relevant paragraphs/sentences; cap context sent to GPT."""
    text=re.sub(r"\s+"," ",str(text or "")).strip()
    parts=re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+|\s*[|｜]\s*", text)
    hits=[p.strip() for p in parts if len(p.strip())>=20 and GOLF_RE.search(p)]
    if not hits: return text[:MAX_CONTEXT_CHARS]
    # preserve order and dedupe
    seen=[]; total=0
    for p in hits:
        key=re.sub(r"\s+"," ",p)[:180]
        if key in seen: continue
        if total+len(p)>MAX_CONTEXT_CHARS: break
        seen.append(key); total+=len(p)+1
    return " ".join(seen)[:MAX_CONTEXT_CHARS]

def _shortlist(records):
    scored=[]
    for r in records:
        txt=(r.get("title","")+" "+r.get("description",""))[:8000]
        score=len(GOLF_RE.findall(txt))
        if r.get("published_at"): score+=4
        if re.search(r"(라운딩|라운드|후기|리뷰)",r.get("title",""),re.I): score+=5
        scored.append((score,r))
    scored.sort(key=lambda x:(x[0],x[1].get("published_at") or ""),reverse=True)
    return [r for _,r in scored[:MAX_REVIEWS]]

def _cache_key(records,model):
    seed=model+"|"+"|".join((r.get("url") or "")+"|"+(r.get("published_at") or "") for r in records)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]

def _read_cache(key):
    p=CACHE_DIR/f"{key}.json"
    try:
        if p.exists() and time.time()-p.stat().st_mtime<CACHE_TTL:
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception: pass
    return None

def _write_cache(key,data):
    try:
        CACHE_DIR.mkdir(parents=True,exist_ok=True)
        (CACHE_DIR/f"{key}.json").write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
    except Exception:
        pass  # Streamlit Cloud local disk is best-effort only.

def _analyze_batch(api_key, batch, model, club_name):
    client=OpenAI(api_key=api_key)
    docs=[]
    for x in batch:
        docs.append({"id":x["id"],"title":x["title"],"date_hint":x["date_hint"],
                     "url":x["url"],"text":x["text"]})
    prompt=club_name+""" 실제 라운딩 후기 분석. 광고/메뉴/일반론/타 골프장/추측은 무시하고 원문에 없는 사실은 만들지 마라.
date_hint가 있으면 날짜로 사용. 없으면 본문/제목에 명시된 게시일만 YYYY-MM-DD, 아니면 "".
코스는 동/남/서가 명시될 때만.
difficulty hard/easy/mixed/unknown; fairway wide/narrow/mixed/unknown; green fast/slow/mixed/unknown;
maintenance positive/negative/mixed/unknown; facilities positive/negative/mixed/unknown.
각 항목은 직접 근거가 있을 때만 판단하고 evidence에는 이를 뒷받침하는 짧은 원문 구절을 넣어라.
source_quality high/medium/low. 실제 라운딩인지 불확실하면 low.
JSON만:
{"reviews":[{"id":0,"date":"","course":"","source_quality":"high","summary":"",
"dimensions":{"difficulty":{"label":"unknown","evidence":""},"fairway":{"label":"unknown","evidence":""},
"green":{"label":"unknown","evidence":""},"maintenance":{"label":"unknown","evidence":""},
"facilities":{"label":"unknown","evidence":""}}}]}
문서:"""+json.dumps(docs,ensure_ascii=False)
    r=client.chat.completions.create(
        model=model,messages=[{"role":"user","content":prompt}],
        response_format={"type":"json_object"})
    return json.loads(r.choices[0].message.content).get("reviews",[])

def analyze_reviews_with_gpt(api_key, records, club_name, model="gpt-5-mini"):
    selected=_shortlist(records)
    key=_cache_key(selected,model+"|"+club_name)
    cached=_read_cache(key)
    if cached is not None:
        return cached

    docs=[]
    bases={}
    for i,r in enumerate(selected):
        d={"id":i,"title":r.get("title",""),"date_hint":r.get("published_at",""),
           "url":r.get("url",""),"text":_compact(r.get("description",""))}
        docs.append(d); bases[i]=d

    batches=[docs[i:i+BATCH_SIZE] for i in range(0,len(docs),BATCH_SIZE)]
    raw=[]
    # 15 reviews => at most 3 concurrent GPT calls.
    with ThreadPoolExecutor(max_workers=min(3,len(batches) or 1)) as ex:
        futs=[ex.submit(_analyze_batch,api_key,b,model,club_name) for b in batches]
        for f in as_completed(futs):
            raw.extend(f.result())

    cleaned=[]
    for x in raw:
        b=bases.get(x.get("id"))
        if not b or x.get("source_quality")=="low": continue
        ds={}
        for d in DIMS:
            z=(x.get("dimensions") or {}).get(d) or {}
            lab=z.get("label","unknown")
            if lab not in VALID[d]: lab="unknown"
            ds[d]={"label":lab,"evidence":str(z.get("evidence") or "").strip()[:260]}
        cleaned.append({"date":str(x.get("date") or b["date_hint"] or ""),"course":str(x.get("course") or ""),
            "quality":x.get("source_quality","medium"),"summary":str(x.get("summary") or "")[:220],
            "dimensions":ds,"title":b["title"],"url":b["url"]})
    cleaned.sort(key=lambda x:x.get("date") or "",reverse=True)
    _write_cache(key,cleaned)
    return cleaned

def aggregate(reviews):
    result={}
    for d in DIMS:
        counts={}; evidence={}
        for r in reviews:
            lab=r["dimensions"][d]["label"]
            if lab in ("unknown","mixed"): continue
            counts[lab]=counts.get(lab,0)+1
            evidence.setdefault(lab,[]).append(r)
        rank=sorted(counts.items(),key=lambda x:x[1],reverse=True)
        dominant=rank[0][0] if rank and (len(rank)==1 or rank[0][1]>rank[1][1]) else None
        result[d]={"counts":counts,"evidence":evidence,"dominant":dominant,
                   "verdict":LABELS[d].get(dominant,"의견 엇갈림" if rank else "후기 더 필요")}
    return result
