import io, json, re, shutil
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
import requests

BASE=Path(__file__).resolve().parents[1]
CATALOG=BASE/"data"/"golf"/"catalog.json"
BACKUPS=BASE/"data"/"golf"/"backups"
REPORT=BASE/"data"/"golf"/"kga_rating_apply_report.json"

# KGA 공식 공개 코스레이팅 현황 PDF (2024-07-15)
DEFAULT_PDF="https://www.kgagolf.or.kr/infor/infor_data/AllRatings_24.pdf"
SOURCE_DATE="2024-07-15"

def norm(s):
    s=str(s or "").lower()
    s=re.sub(r"\([^)]*\)","",s)
    s=re.sub(r"[^0-9a-z가-힣]","",s)
    for x in ("컨트리클럽","골프클럽","골프장","countryclub","golfclub","cc","gc"):
        s=s.replace(x,"")
    return s

def _reader(data):
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf가 필요합니다. .\\venv\\Scripts\\python.exe -m pip install pypdf") from e
    return PdfReader(io.BytesIO(data))

def fetch_pdf_text(url=DEFAULT_PDF):
    r=requests.get(url,timeout=60,headers={"User-Agent":"Mozilla/5.0"})
    r.raise_for_status()
    reader=_reader(r.content)
    return "\n".join((p.extract_text() or "") for p in reader.pages)

def parse_ratings(text):
    """
    KGA PDF의 행 텍스트를 보수적으로 파싱.
    끝부분의 rating/slope + yardage 패턴을 먼저 잡고,
    앞부분을 골프장/코스/티/성별로 분리한다.
    파싱이 불확실한 행은 버린다.
    """
    rows=[]
    lines=[re.sub(r"\s+"," ",x).strip() for x in text.splitlines()]
    for line in lines:
        if not line or "코스레이팅" in line or "WORLD HANDICAP" in line:
            continue
        # ... 티 남자 75.2/146 7,026
        m=re.search(r"(.+?)\s+(남자|여자)\s+(\d{2}\.\d)\s*/\s*(\d{2,3})\s+([\d,]{4,6})\s*$",line)
        if not m:
            continue
        prefix,gender,cr,slope,yards=m.groups()
        yards=int(yards.replace(",",""))
        cr=float(cr); slope=int(slope)
        if not (55<=cr<=85 and 55<=slope<=155 and 3000<=yards<=8000):
            continue

        # 티는 마지막 토큰, 그 앞을 골프장/코스로 둔다.
        parts=prefix.rsplit(" ",1)
        if len(parts)!=2:
            continue
        course_part,tee=parts
        # PDF에 '골프장 코스'가 공백으로 존재하므로 kga catalog와 후속 fuzzy match
        rows.append({"raw_course":course_part.strip(),"tee":tee.strip(),"gender":gender,
                     "course_rating":cr,"slope_rating":slope,"length_yds":yards})
    return rows

def split_against_catalog(raw, catalog):
    """이미 안전 매칭된 KGA 이름을 이용해 raw_course 앞부분을 골프장명으로 결정."""
    candidates=[]
    nr=norm(raw)
    for c in catalog:
        kga=c.get("kga") or {}
        if not kga.get("matched"): continue
        names=[kga.get("matched_name"),c.get("name")]
        for n in names:
            nn=norm(n)
            if nn and nr.startswith(nn):
                candidates.append((len(nn),c,n))
    if candidates:
        _,club,name=max(candidates,key=lambda x:x[0])
        # 원문에서 이름 표기가 다를 수 있어 course는 조합들과 유사도 비교
        combos=(club.get("kga") or {}).get("course_combinations") or []
        best_combo=""
        best=0
        for combo in combos:
            score=SequenceMatcher(None,norm(combo),nr).ratio()
            if norm(combo) and norm(combo) in nr:
                score=1.0
            if score>best:
                best,best_combo=score,combo
        return club,best_combo if best>=0.55 else ""
    return None,""

def apply(url=DEFAULT_PDF):
    catalog=json.loads(CATALOG.read_text(encoding="utf-8"))
    text=fetch_pdf_text(url)
    parsed=parse_ratings(text)

    grouped={}
    unmatched=0
    for r in parsed:
        club,combo=split_against_catalog(r["raw_course"],catalog)
        if not club:
            unmatched+=1
            continue
        rr={k:v for k,v in r.items() if k!="raw_course"}
        rr["course"]=combo
        grouped.setdefault(club.get("id"),[]).append(rr)

    # 중복 제거
    for cid,items in grouped.items():
        seen=set(); unique=[]
        for r in items:
            key=(r.get("course"),r["tee"],r["gender"],r["course_rating"],r["slope_rating"],r["length_yds"])
            if key not in seen:
                seen.add(key); unique.append(r)
        grouped[cid]=unique

    BACKUPS.mkdir(parents=True,exist_ok=True)
    backup=BACKUPS/f"catalog_before_kga_ratings_{datetime.now():%Y%m%d_%H%M%S}.json"
    shutil.copy2(CATALOG,backup)

    clubs_added=0; ratings_added=0
    for c in catalog:
        ratings=grouped.get(c.get("id"))
        if not ratings: continue
        kga=c.setdefault("kga",{})
        kga["ratings"]=ratings
        kga["ratings_source_name"]="대한골프협회(KGA) 코스레이팅 현황"
        kga["ratings_source_url"]=url
        kga["ratings_source_date"]=SOURCE_DATE
        kga["ratings_checked_at"]=date.today().isoformat()
        clubs_added+=1; ratings_added+=len(ratings)

    tmp=CATALOG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    check=json.loads(tmp.read_text(encoding="utf-8"))
    if len(check)!=len(catalog):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("저장 검증 실패")
    tmp.replace(CATALOG)

    report={"source":url,"source_date":SOURCE_DATE,"parsed_rows":len(parsed),
            "matched_clubs":clubs_added,"ratings_saved":ratings_added,
            "unmatched_parsed_rows":unmatched,"backup":str(backup)}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report
