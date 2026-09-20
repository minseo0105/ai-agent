"""Public catalog import or ephemeral HUB pilot. Never persist search/AI results."""
import argparse
import csv
import io
import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.golf_api import GolfAPIError, secret_status
from services.golf_analysis import ASPECTS, analyze_pilot, next_query, prepare_candidates, search_pilot
from services.golf_cache import new_experiment
from services.golf_catalog import DATA_DIR, load_catalog

SOURCE_URL = "https://www.data.go.kr/data/15118920/fileData.do"
DOWNLOAD_URL = "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003647024&fileDetailSn=1&insertDataPrcus=N"
SELECTION = [
    ("lakeside", "레이크사이드CC", ["레이크사이드CC(대중제)", "레이크사이드CC(회원제)"], ["레이크사이드", "레이크사이드 컨트리클럽"]),
    ("namseoul", "남서울CC", ["남서울컨트리클럽"], ["남서울 컨트리클럽", "남서울 골프장"]),
    ("taekwang", "태광CC", ["태광컨트리클럽(회원제)", "태광컨트리클럽(대중제)"], ["태광 컨트리클럽", "태광 골프장"]),
    ("hansung", "한성CC", ["한성컨트리클럽"], ["한성 컨트리클럽", "한성 골프장"]),
    ("suwon", "수원CC", ["수원컨트리클럽"], ["수원 컨트리클럽", "수원 골프장"]),
    ("gold", "골드CC", ["골드컨트리클럽"], ["골드 컨트리클럽", "골드 골프장"]),
    ("korea", "코리아CC", ["코리아컨트리클럽"], ["코리아 컨트리클럽"]),
    ("88", "88CC", ["국가보훈부 88골프장"], ["88컨트리클럽", "88골프장", "팔팔CC"]),
    ("kiheung", "기흥CC", ["기흥컨트리클럽"], ["기흥 컨트리클럽"]),
    ("asiana", "아시아나CC", ["아시아나컨트리클럽"], ["아시아나 컨트리클럽", "아시아나 골프장"]),
]


def import_catalog():
    import requests
    response = requests.get(DOWNLOAD_URL, timeout=(5, 25))
    response.raise_for_status()
    try:
        text = response.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = response.content.decode("cp949")
    rows = list(csv.DictReader(io.StringIO(text)))
    now = datetime.now(timezone.utc).isoformat()
    clubs = []
    for club_id, name, source_names, aliases in SELECTION:
        matches = [r for r in rows if r["지역"] == "경기" and r["이름"] in source_names]
        if len(matches) != len(source_names) or len({r["소재지"] for r in matches}) != 1:
            raise ValueError("공공데이터의 골프장 이름/주소가 변경되었습니다. 수동 확인이 필요합니다.")
        address = matches[0]["소재지"]
        clubs.append({"id": club_id, "name": name, "aliases": aliases + source_names,
                      "excluded_names": ["뉴코리아", "코리아대중"] if club_id == "korea" else [],
                      "region": "경기", "city": address.split()[1], "address": address,
                      "holes": sum(int(r["홀"]) for r in matches),
                      "phone": None, "latitude": None, "longitude": None,
                      "kakao_place_id": None, "map_url": None,
                      "source": {"provider": "문화체육관광부", "url": SOURCE_URL,
                                 "as_of": "2024-12-31", "retrieved_at": now,
                                 "rows": [{k: r[k] for k in ("이름", "소재지", "홀", "구분")} for r in matches]}})
    # Only public catalog data is allowed on disk, never review data.
    (DATA_DIR / "catalog.json").write_text(json.dumps({"schema_version": 1, "scope": "수도권 MVP 10개",
                "golf_clubs": clubs}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Imported 10 clubs from MCST public CSV. No review API calls.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-catalog", action="store_true")
    parser.add_argument("--club", default="lakeside", choices=["lakeside"])
    parser.add_argument("--search", action="store_true", help="One live HUB blog request, memory only")
    parser.add_argument("--analyze", action="store_true", help="Experimental AI + deficient dimensions only; max 6 NAVER calls")
    args = parser.parse_args()
    if args.build_catalog:
        import_catalog()
        return 0
    try:
        secrets = tomllib.loads((ROOT / ".streamlit/secrets.toml").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        secrets = {}
    status = secret_status(secrets)
    club = next((c for c in load_catalog() if c["id"] == args.club), None)
    if not club:
        parser.error("Unknown club ID")
    required = list(status) if args.analyze else list(status)[:2]
    report = {"club_id": club["id"], "status": "ready" if all(status[k] for k in required) else "blocked_missing_credentials",
              "missing_keys": [k for k in required if not status[k]], "storage": "memory_only"}
    state = new_experiment()
    if (args.search or args.analyze) and report["status"] == "ready":
        try:
            search_pilot(club, secrets, state)
            if args.analyze:
                analyze_pilot(club, secrets, state)
                while next_query(state):
                    search_pilot(club, secrets, state)
                    analyze_pilot(club, secrets, state)
            report["status"] = "completed"
        except GolfAPIError as error:
            report.update(status="failed", error=str(error))
    report.update(naver_calls=state["naver_calls"], openai_calls=state["openai_calls"])
    if state["collection"]:
        candidates, exclusions, _ = prepare_candidates(club, state["collection"]["records"])
        report.update(queries=state["collection"]["queries"], raw_result_count=state["collection"]["raw_result_count"],
                      candidate_count=len(candidates), duplicate_count=sum(e["category"] == "duplicate" for e in exclusions),
                      advertising_or_irrelevant_count=sum(e["category"] in ("advertising", "irrelevant") for e in exclusions))
    if state["analysis"]:
        result = state["analysis"]
        report.update(valid_evidence_count=result["review_count"], metrics=result["metrics"],
                      insufficient=[ASPECTS[a] for a, m in result["metrics"].items() if m["label"] == "정보 부족"],
                      conflicting=[ASPECTS[a] for a, m in result["metrics"].items() if m["label"] == "평가가 엇갈림"])
    # Aggregate-only terminal report; do not print snippets, URLs, credentials or model payloads.
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] in ("ready", "completed") else 2


if __name__ == "__main__":
    sys.exit(main())
