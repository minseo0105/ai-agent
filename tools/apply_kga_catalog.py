import json, shutil
from datetime import datetime
from pathlib import Path
from services.golf_kga_enrichment_v2_1 import diagnose_kga_matches

BASE_DIR=Path(__file__).resolve().parents[1]
CATALOG=BASE_DIR/"data"/"golf"/"catalog.json"
BACKUPS=BASE_DIR/"data"/"golf"/"backups"
REPORT=BASE_DIR/"data"/"golf"/"kga_apply_report.json"

def main():
    catalog=json.loads(CATALOG.read_text(encoding="utf-8"))
    diagnostic=diagnose_kga_matches(catalog)
    safe={x["catalog_id"]:x for x in diagnostic["matches"] if x.get("safe")}
    BACKUPS.mkdir(parents=True,exist_ok=True)
    backup=BACKUPS/f"catalog_before_kga_{datetime.now():%Y%m%d_%H%M%S}.json"
    shutil.copy2(CATALOG,backup)

    matched=0
    course_rows=0
    for club in catalog:
        m=safe.get(club.get("id"))
        if not m:
            continue
        rows=m.get("kga_rows") or []
        combos=[]
        for r in rows:
            c=str(r.get("course") or "").strip()
            if c and c not in combos:
                combos.append(c)
        club["kga"]={
            "matched":True,
            "status":"KGA 코스정보 확인",
            "matched_name":m.get("match_name"),
            "match_type":m.get("match_type"),
            "match_score":m.get("score"),
            "checked_at":diagnostic.get("checked_at"),
            "region":next((r.get("region") for r in rows if r.get("region")),""),
            "address":next((r.get("address") for r in rows if r.get("address")),""),
            "course_combinations":combos,
            "source_name":"대한골프협회(KGA) 코스레이팅 DB",
            "source_url":diagnostic.get("source"),
        }
        matched+=1
        course_rows+=len(combos)

    tmp=CATALOG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    check=json.loads(tmp.read_text(encoding="utf-8"))
    if len(check)!=len(catalog):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("저장 검증 실패: catalog 건수가 달라졌습니다.")
    tmp.replace(CATALOG)

    result={"catalog_count":len(catalog),"kga_matched":matched,
            "course_combinations_saved":course_rows,"backup":str(backup)}
    REPORT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("="*64)
    print("KGA 안전 매칭 catalog 적용 완료")
    print("="*64)
    print(f"전체 catalog            : {len(catalog)}건")
    print(f"KGA 안전 매칭 적용       : {matched}건")
    print(f"코스 조합 저장           : {course_rows}건")
    print(f"백업                    : {backup}")
    print("기존 필드 덮어쓰기        : 없음")
    print("Course/Slope 임의 생성    : 없음")

if __name__=="__main__":
    main()
