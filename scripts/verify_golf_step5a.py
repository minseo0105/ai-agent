"""STEP 5-A: enrich ONLY public Lakeside metadata; one NAVER request, no LLM/storage."""
import csv
import io
import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.golf_api import AUTH_HEADERS, SEARCH_BASE, GolfAPIError, collect_reviews

PUBLIC_CSV = "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003647024&fileDetailSn=1&insertDataPrcus=N"


def enrich_lakeside():
    path = ROOT / "data/golf/catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    club = next(c for c in catalog["golf_clubs"] if c["id"] == "lakeside")
    response = requests.get(PUBLIC_CSV, timeout=(5, 25))
    response.raise_for_status()
    try:
        text = response.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = response.content.decode("cp949")
    source_names = {r["이름"] for r in club["source"]["rows"]}
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r["지역"] == "경기" and r["이름"] in source_names]
    if len(rows) != 2 or len({r["소재지"] for r in rows}) != 1 or len({r["사업자"] for r in rows}) != 1:
        raise ValueError("Public source identity changed; manual verification required.")
    club.update(operator=rows[0]["사업자"], area_sqm=sum(int(r["면적(제곱미터)"]) for r in rows),
                holes=sum(int(r["홀"]) for r in rows), address=rows[0]["소재지"],
                operation_types=[{"type": r["구분"], "holes": int(r["홀"]),
                                  "area_sqm": int(r["면적(제곱미터)"])} for r in rows],
                opening_year=None, course_composition=None, website=None, phone=None)
    club["source"]["rows"] = [{k: r[k] for k in ("이름", "사업자", "소재지", "면적(제곱미터)", "홀", "구분")} for r in rows]
    club["source"]["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    # Only government master data is persisted. No NAVER data enters this file.
    temporary = path.with_suffix(".step5a.tmp")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return club


def main():
    try:
        club = enrich_lakeside()
    except Exception:
        print(json.dumps({"status": "public_data_error", "naver_calls": 0}))
        return 1
    try:
        secrets = tomllib.loads((ROOT / ".streamlit/secrets.toml").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        secrets = {}
    report = {"basic_information": {k: club[k] for k in
              ("name", "address", "operator", "holes", "area_sqm", "operation_types", "opening_year", "course_composition", "website", "phone")},
              "endpoint": SEARCH_BASE + "/blog", "header_names": AUTH_HEADERS,
              "query": "레이크사이드CC 라운딩 후기", "total": None, "item_count": None,
              "llm_calls": 0, "naver_results_persisted": False}
    try:
        result = collect_reviews(club, secrets, query=report["query"], display=100, kind="blog")
        report.update(status="success", total=result["queries"][0]["provider_total"], item_count=len(result["records"]))
    except GolfAPIError as error:
        report.update(status="failed", error=str(error))
    # Counts only; titles/descriptions/credentials are never printed or saved.
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["status"] == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
