from __future__ import annotations

import argparse, json, os, re, time, html
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "data" / "golf" / "catalog.json"
OUT = ROOT / "data" / "golf" / "enrichment"
RESULT = OUT / "golf_master_builder_test10.json"
REPORT = OUT / "golf_master_builder_test10_report.json"
TAVILY_URL = "https://api.tavily.com/search"
TIMEOUT = 20
HEADERS = {"User-Agent":"Mozilla/5.0 (compatible; GolfMasterDB/1.0)"}

# 공식 홈페이지로 절대 자동승인하지 않는 유형.
PLATFORM = {
    "kakao.golf","kimcaddie.com","xgolf.com","golfmon.net","goltou.kr",
    "greenfeeguide.co.kr","czgolf.kr","yeoksamgolf.com"
}
COMMUNITY = {
    "naver.com","blog.naver.com","m.blog.naver.com","cafe.naver.com",
    "daum.net","v.daum.net","tistory.com","youtube.com","instagram.com",
    "facebook.com","namu.wiki"
}
NEWS_HINTS = ("news","daily","times","press","journal","herald","today","ilbo","media")

def s(v): return str(v or "").strip()
def host(url):
    try: return urlparse(url).netloc.lower().split(":")[0].removeprefix("www.")
    except: return ""
def root_url(url):
    p=urlparse(url); return f"{p.scheme}://{p.netloc}/" if p.scheme and p.netloc else ""
def domain_in(h, pool):
    return any(h==d or h.endswith("."+d) for d in pool)

def key():
    if os.getenv("TAVILY_API_KEY"): return os.getenv("TAVILY_API_KEY")
    p=ROOT/".streamlit"/"secrets.toml"
    if p.exists():
        try:
            import tomllib
            d=tomllib.loads(p.read_text(encoding="utf-8"))
            return s(d.get("TAVILY_API_KEY") or d.get("TAVILY_KEY"))
        except: pass
    return ""

def pub(c): return ((c.get("verification") or {}).get("public_data") or {})
def missing(c):
    return [k for k,ok in [
        ("operation_type",bool(s(c.get("operation_type")))),
        ("holes",bool(c.get("holes"))),
        ("courses",bool(c.get("courses") or [])),
        ("official_url",bool(s(c.get("official_url")))),
        ("booking_url",bool(s(c.get("booking_url")))),
    ] if not ok]

def norm_name(x):
    x=re.sub(r"[^0-9a-z가-힣]","",s(x).lower())
    for t in ("컨트리클럽","골프클럽","골프앤리조트","골프리조트","골프장","countryclub","golfclub"):
        x=x.replace(t,"")
    return x.replace("cc","").replace("gc","")

def strip_html(x):
    x=re.sub(r"(?is)<script.*?</script>|<style.*?</style>"," ",x or "")
    x=re.sub(r"(?s)<[^>]+>"," ",x)
    return re.sub(r"\s+"," ",html.unescape(x)).strip()

def tavily(k,q,n=8):
    r=requests.post(TAVILY_URL,json={
        "api_key":k,"query":q,"search_depth":"advanced","max_results":n,
        "include_answer":False,"include_raw_content":True
    },timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("results") or []

def source_type(url):
    h=host(url)
    if domain_in(h,COMMUNITY): return "community"
    if domain_in(h,PLATFORM): return "platform"
    if any(x in h for x in NEWS_HINTS): return "news"
    if h.endswith(".go.kr") or h.endswith(".or.kr"): return "institution"
    return "web"

def fetch_site(url):
    try:
        r=requests.get(root_url(url),headers=HEADERS,timeout=12,allow_redirects=True)
        if r.status_code>=400: return "",r.url
        ct=r.headers.get("content-type","")
        if "text/html" not in ct: return "",r.url
        return strip_html(r.text[:100000]),r.url
    except:
        return "",""

def identity(c,text):
    """직접 접속한 사이트 본문과 기존 DB를 교차검증."""
    name=norm_name(c.get("name"))
    compact=norm_name(text)
    score=0; why=[]
    if name and len(name)>=2 and name in compact:
        score+=5; why.append("name")

    a=s(c.get("address") or pub(c).get("address"))
    toks=[x for x in re.findall(r"[가-힣]{2,}",a)
          if x not in {"경기도","강원도","충청북도","충청남도","전라북도","전라남도","경상북도","경상남도","제주특별자치도"}]
    hits=[x for x in toks[:6] if x in text]
    if len(hits)>=2: score+=4; why.append("address2")
    elif len(hits)==1: score+=2; why.append("address1")

    ph=re.sub(r"\D","",s(c.get("phone") or pub(c).get("phone")))
    digits=re.sub(r"\D","",text)
    if len(ph)>=8 and ph[-8:] in digits:
        score+=5; why.append("phone")
    return score,why

def facts(text):
    holes=sorted(set(int(x) for x in re.findall(r"(?<!\d)(9|18|27|36|45|54|63|72)\s*홀",text or "")))
    member="회원제" in (text or "")
    public=any(x in (text or "") for x in ("대중제","대중형","퍼블릭"))
    op="혼합" if member and public else ("회원제" if member else ("대중제(퍼블릭)" if public else ""))
    return {"holes":holes,"operation_type":op}

def query_set(c):
    n=s(c.get("name"))
    a=s(c.get("address") or pub(c).get("address"))
    loc=" ".join(a.split()[:2]) if a else ""
    return [
        f'"{n}" {loc} 공식 홈페이지',
        f'"{n}" {loc} 홀 코스 회원제 대중제',
        f'"{n}" {loc} 예약 골프',
    ]

def build_one(k,c):
    qs=query_set(c)
    raw=[]; seen=set()
    for q in qs:
        for x in tavily(k,q,8):
            u=s(x.get("url"))
            if u and u not in seen:
                seen.add(u); raw.append(x)
        time.sleep(.2)

    # 검색 결과의 사실 후보. 공식 URL 판정에는 사용하지 않고 교차합의에만 사용.
    evidence=[]
    fact_votes=defaultdict(list)
    for x in raw:
        u=s(x.get("url")); typ=source_type(u)
        text=" ".join([s(x.get("title")),s(x.get("content")),s(x.get("raw_content"))[:12000]])
        f=facts(text)
        evidence.append({"type":typ,"host":host(u),"url":u,"title":s(x.get("title")),
                         "holes":f["holes"],"operation_type":f["operation_type"]})
        for hv in f["holes"]:
            fact_votes["holes"].append((hv,typ,u))
        if f["operation_type"]:
            fact_votes["operation_type"].append((f["operation_type"],typ,u))

    # 공식사이트: platform/community/news 제외 + 사이트 직접 접속 + identity 확인.
    official_candidates=[]
    checked_hosts=set()
    for x in raw:
        u=s(x.get("url")); h=host(u); typ=source_type(u)
        if not h or h in checked_hosts or typ in {"platform","community","news"}: continue
        checked_hosts.add(h)
        body,final=fetch_site(u)
        if not body: continue
        sc,why=identity(c,body)
        if "name" in why and sc>=7:
            official_candidates.append({"host":host(final or u),"url":root_url(final or u),
                                        "score":sc,"reasons":why,"page_source":u,
                                        "site_facts":facts(body)})
    official_candidates.sort(key=lambda z:z["score"],reverse=True)

    official=None
    if official_candidates:
        if len(official_candidates)==1 or official_candidates[0]["score"]>=official_candidates[1]["score"]+2:
            official=official_candidates[0]

    proposed={}; grades={}; sources={}
    if official:
        proposed["official_url"]=official["url"]; grades["official_url"]="A"
        sources["official_url"]=[official["page_source"]]
        sf=official["site_facts"]
        if len(sf["holes"])==1:
            proposed["holes"]=sf["holes"][0]; grades["holes"]="A"
            sources["holes"]=[official["page_source"]]
        if sf["operation_type"]:
            proposed["operation_type"]=sf["operation_type"]; grades["operation_type"]="A"
            sources["operation_type"]=[official["page_source"]]

        # 예약 URL은 확인된 공식 host의 검색 결과만.
        for x in raw:
            u=s(x.get("url"))
            if host(u)==official["host"] and any(k in (u+" "+s(x.get("title"))).lower()
                for k in ("reservation","reserve","booking","book","예약")):
                proposed["booking_url"]=u; grades["booking_url"]="A"
                sources["booking_url"]=[u]; break

    # 공식사이트에서 못 얻은 사실은 서로 다른 비커뮤니티 출처 2곳 이상 합의 시 B.
    for field in ("holes","operation_type"):
        if field in proposed: continue
        votes=[v for v in fact_votes[field] if v[1] not in {"community"}]
        grouped=defaultdict(list)
        for val,typ,u in votes:
            grouped[str(val)].append((typ,u))
        winners=[]
        for val,arr in grouped.items():
            distinct_hosts={host(u) for _,u in arr}
            # 서로 다른 2개 도메인 + 최소 한 곳은 플랫폼/뉴스 외 web/institution
            strong=any(t in {"web","institution"} for t,_ in arr)
            if len(distinct_hosts)>=2 and strong:
                winners.append((len(distinct_hosts),val,arr))
        winners.sort(reverse=True)
        if winners and (len(winners)==1 or winners[0][0]>winners[1][0]):
            _,val,arr=winners[0]
            proposed[field]=int(val) if field=="holes" else val
            grades[field]="B"
            sources[field]=[u for _,u in arr[:4]]

    return {
        "name":s(c.get("name")),
        "missing_before":missing(c),
        "queries":qs,
        "proposed":proposed,
        "grades":grades,
        "sources":sources,
        "official_candidates":official_candidates[:5],
        "evidence":evidence[:25],
        "review_needed":[f for f in missing(c) if f not in proposed],
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=10)
    args=ap.parse_args()
    k=key()
    if not k: raise SystemExit("TAVILY_API_KEY를 찾지 못했습니다.")
    clubs=json.loads(CATALOG.read_text(encoding="utf-8-sig"))
    OUT.mkdir(parents=True,exist_ok=True)

    def pri(c):
        p=pub(c)
        if c.get("service_status")=="service": return 0
        if c.get("service_status")=="candidate" and p.get("operating_in_public_data") is True: return 1
        return 2
    targets=[c for c in clubs if missing(c)]
    targets.sort(key=lambda c:(pri(c),s(c.get("name"))))
    targets=targets[:args.limit]

    result={"generated_at":datetime.now().isoformat(timespec="seconds"),
            "mode":"MASTER_DB_TEST10_NO_APPLY","catalog_modified":False,"results":[]}

    print("="*78)
    print("Golf Master DB Builder - 다중출처 검증 TEST")
    print(f"대상: {len(targets)}개 | 골프장당 검색 3회 | catalog 수정 없음")
    print("등급 A=직접 검증 공식/기관, B=서로 다른 신뢰 출처 합의, C=미반영")
    print("="*78)

    for i,c in enumerate(targets,1):
        print(f"[{i}/{len(targets)}] {s(c.get('name'))}")
        try:
            r=build_one(k,c)
            r["status"]="ok"
            print("  → 제안:",r["proposed"] or "없음")
            print("  → 등급:",r["grades"] or "없음")
            if r["review_needed"]: print("  → 확인 필요:",", ".join(r["review_needed"]))
        except Exception as e:
            r={"name":s(c.get("name")),"status":"error","error":f"{type(e).__name__}: {e}"}
            print("  → 오류:",r["error"])
        result["results"].append(r)
        RESULT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        time.sleep(.5)

    grade_count=Counter()
    field_count=Counter()
    for r in result["results"]:
        for f,g in (r.get("grades") or {}).items():
            grade_count[g]+=1; field_count[f]+=1
    report={
        "generated_at":datetime.now().isoformat(timespec="seconds"),
        "courses":len(targets),
        "planned_search_calls":len(targets)*3,
        "field_proposals":dict(field_count),
        "grade_counts":dict(grade_count),
        "catalog_modified":False,
        "result_file":str(RESULT)
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*78)
    print("TEST 완료")
    print("제안 필드:",dict(field_count))
    print("등급:",dict(grade_count))
    print("catalog.json 수정: 없음")
    print("결과:",RESULT)
    print("="*78)

if __name__=="__main__":
    main()
