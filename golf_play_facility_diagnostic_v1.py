# -*- coding: utf-8 -*-
"""
Golf Play/Facility Conditions Diagnostic v1
- 추가 Tavily/LLM 호출 0
- catalog + 기존 pipeline_v3_1 결과를 재사용
- catalog.json 수정 0
- 2인/3인/9홀x2/야간/PAR3/야외연습장 현황과 기존자료 후보만 추출
"""
from __future__ import annotations
import json, re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "data" / "golf" / "catalog.json"
PIPE = ROOT / "data" / "golf" / "enrichment" / "pipeline_v3_1"
OUTROOT = ROOT / "data" / "golf" / "enrichment" / "play_facility_diagnostic"
EXPECTED = 553

FIELDS = {
    "two_person": {
        "path": ("play","two_person"),
        "label": "2인 플레이",
        "positive": [r"2인\s*(플레이|라운드|라운딩)?\s*(가능|예약|운영)", r"2인플레이\s*가능"],
        "negative": [r"2인\s*(플레이|라운드|라운딩)?\s*(불가|불가능|미운영)", r"2인플레이\s*불가"],
    },
    "three_person": {
        "path": ("play","three_person"),
        "label": "3인 플레이",
        "positive": [r"3인\s*(플레이|라운드|라운딩)?\s*(가능|예약|운영)", r"3인플레이\s*가능"],
        "negative": [r"3인\s*(플레이|라운드|라운딩)?\s*(불가|불가능|미운영)", r"3인플레이\s*불가"],
    },
    "nine_hole_twice": {
        "path": ("play","nine_hole_twice"),
        "label": "9홀×2",
        "positive": [r"9홀\s*[x×X*]\s*2", r"9홀\s*2회", r"9홀.*두\s*바퀴"],
        "negative": [],
    },
    "night_round": {
        "path": ("play","night_round"),
        "label": "야간 라운드",
        "positive": [r"야간\s*(라운드|라운딩|운영|개장|예약)\s*(가능|운영|실시|오픈)?", r"나이트\s*(라운드|라운딩|운영)"],
        "negative": [r"야간\s*(라운드|라운딩|운영)\s*(불가|미운영|없음|중단)"],
    },
    "par3": {
        "path": ("facilities","par3"),
        "label": "PAR3 연습장",
        "positive": [r"(PAR|Par|par)\s*3\s*(연습장|코스)", r"파3\s*(연습장|코스)"],
        "negative": [r"(PAR|Par|par)\s*3\s*(연습장|코스).{0,12}(없음|미운영)"],
    },
    "driving_range": {
        "path": ("facilities","driving_range"),
        "label": "야외 연습장",
        "positive": [r"야외\s*(골프)?\s*연습장", r"드라이빙\s*레인지", r"driving\s*range"],
        "negative": [r"야외\s*(골프)?\s*연습장.{0,12}(없음|미운영)"],
    },
}
TRUE = {True,"가능","있음","yes","Y","true","True","운영"}
FALSE = {False,"불가","없음","no","N","false","False","미운영"}

def load(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def get_nested(d, path):
    cur=d
    for k in path:
        if not isinstance(cur,dict): return None
        cur=cur.get(k)
    return cur

def latest_pipeline():
    files=list(PIPE.rglob("result_*.json")) + list(PIPE.rglob("result.json"))
    if not files: return None
    return max(files,key=lambda p:p.stat().st_mtime)

def flatten_text(obj, acc=None):
    if acc is None: acc=[]
    if isinstance(obj,str):
        acc.append(obj)
    elif isinstance(obj,dict):
        for k,v in obj.items():
            if k.lower() not in {"raw_content"}:  # 과도한 원문은 제외하되 snippet/content는 사용
                flatten_text(v,acc)
    elif isinstance(obj,list):
        for v in obj: flatten_text(v,acc)
    return acc

def pipeline_records(data):
    # 다양한 저장 구조에서 club id/name 단위 레코드를 최대한 안전하게 찾음
    found=[]
    def walk(x):
        if isinstance(x,dict):
            if any(k in x for k in ("id","club_id")) and any(k in x for k in ("name","club_name")):
                found.append(x)
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(data)
    return found

def detect(text, spec):
    pos=[]; neg=[]
    for pat in spec["positive"]:
        for m in re.finditer(pat,text,re.I):
            pos.append(text[max(0,m.start()-80):min(len(text),m.end()+100)].replace("\n"," "))
    for pat in spec["negative"]:
        for m in re.finditer(pat,text,re.I):
            neg.append(text[max(0,m.start()-80):min(len(text),m.end()+100)].replace("\n"," "))
    status="none"
    if pos and neg: status="conflict"
    elif neg: status="negative_candidate"
    elif pos: status="positive_candidate"
    return status,(pos+neg)[:4]

def main():
    catalog=load(CATALOG)
    if len(catalog)!=EXPECTED:
        raise RuntimeError(f"안전 중단: catalog={len(catalog)} / expected={EXPECTED}")
    pipefile=latest_pipeline()
    pdata=load(pipefile) if pipefile else {}
    precs=pipeline_records(pdata)

    by_id={str(c.get("id") or ""):[] for c in catalog}
    by_name={}
    for r in precs:
        rid=str(r.get("id") or r.get("club_id") or "")
        name=str(r.get("name") or r.get("club_name") or "").strip()
        if rid in by_id: by_id[rid].append(r)
        if name: by_name.setdefault(name,[]).append(r)

    summary={}
    candidates=[]
    current_rows=[]
    for key,spec in FIELDS.items():
        known_true=known_false=missing=0
        cand_pos=cand_neg=cand_conf=0
        for club in catalog:
            val=get_nested(club,spec["path"])
            if val in TRUE: known_true+=1
            elif val in FALSE: known_false+=1
            else:
                missing+=1
                recs=by_id.get(str(club.get("id") or ""),[]) or by_name.get(str(club.get("name") or "").strip(),[])
                text=" \n ".join(flatten_text(recs))
                status,snips=detect(text,spec) if text else ("none",[])
                if status!="none":
                    if status=="positive_candidate": cand_pos+=1
                    elif status=="negative_candidate": cand_neg+=1
                    else: cand_conf+=1
                    candidates.append({
                        "id":club.get("id"),"name":club.get("name"),"field":key,
                        "label":spec["label"],"candidate_status":status,
                        "snippets":snips,"source":"existing_pipeline_v3_1",
                        "auto_apply":False
                    })
            current_rows.append({"id":club.get("id"),"name":club.get("name"),"field":key,"current":val})
        summary[key]={
            "label":spec["label"],"known_true":known_true,"known_false":known_false,"missing":missing,
            "existing_evidence_positive":cand_pos,"existing_evidence_negative":cand_neg,
            "existing_evidence_conflict":cand_conf,
            "still_needs_web_search": missing-cand_pos-cand_neg-cand_conf
        }

    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    out=OUTROOT/stamp
    out.mkdir(parents=True,exist_ok=True)
    report={
        "created_at":datetime.now().astimezone().isoformat(),
        "catalog_count":len(catalog),"pipeline_source":str(pipefile) if pipefile else None,
        "tavily_calls":0,"llm_calls":0,"catalog_modified":False,
        "summary":summary,"candidate_count":len(candidates)
    }
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"existing_evidence_candidates.json").write_text(json.dumps(candidates,ensure_ascii=False,indent=2),encoding="utf-8")

    print("="*78)
    print("Golf Play / Facility Diagnostic v1")
    print("="*78)
    print("catalog:",len(catalog))
    print("기존 pipeline:",pipefile or "없음")
    print()
    for key,x in summary.items():
        print(f"[{x['label']}]")
        print(f"  현재 가능/있음: {x['known_true']}")
        print(f"  현재 불가/없음: {x['known_false']}")
        print(f"  미확인: {x['missing']}")
        print(f"  기존자료 후보(+/-/충돌): {x['existing_evidence_positive']} / {x['existing_evidence_negative']} / {x['existing_evidence_conflict']}")
        print(f"  추가 웹조사 대상(최대): {x['still_needs_web_search']}")
    print()
    print("기존자료 후보 총:",len(candidates))
    print("Tavily 호출: 0")
    print("LLM 호출: 0")
    print("catalog.json 수정: False")
    print("결과:",out/"report.json")
    print("후보:",out/"existing_evidence_candidates.json")

if __name__=="__main__":
    main()
