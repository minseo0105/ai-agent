from pathlib import Path
import json, datetime

PATH=Path("data/golf/review_runtime.json")

def load_runtime_summary(club_id):
    if not PATH.exists(): return None
    try:
        data=json.loads(PATH.read_text(encoding="utf-8"))
        return data.get(club_id)
    except Exception:
        return None

def save_runtime_summary(club_id, agg):
    try:
        data=json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    except Exception:
        data={}
    dimensions={}
    for d,a in (agg or {}).items():
        dimensions[d]={
            "verdict":a.get("verdict","후기 정보 부족"),
            "mentions":sum((a.get("counts") or {}).values())
        }
    data[club_id]={
        "updated":datetime.date.today().isoformat(),
        "note":"최근 실행한 AI 후기 분석 저장본",
        "dimensions":dimensions
    }
    PATH.parent.mkdir(parents=True,exist_ok=True)
    PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
