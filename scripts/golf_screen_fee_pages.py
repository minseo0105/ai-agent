"""AI를 쓰기 전에, 홈페이지에 '고정 그린피'가 실제로 적혀 있는 곳만 골라낸다. (AI 호출 없음 = 무료)

국내 골프장 상당수는 그린피를 실시간 변동가로 운영해 홈페이지에 금액을 올리지 않는다.
그런 곳까지 AI로 재수집하면 비용만 나가므로, 페이지를 먼저 받아
'그린피' 근처에 금액이 있는지를 보고 후보를 추린다.

결과: data/golf/enrichment_review/screen_<날짜>.json

사용:
  venv\\Scripts\\python.exe scripts\\golf_screen_fee_pages.py [--limit N] [--workers 6]
"""

import argparse
import importlib.util
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("enrich", ROOT / "scripts" / "golf_official_enrich.py")
enrich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enrich)

OUT_DIR = ROOT / "data" / "golf" / "enrichment_review"
# 그린피가 '변동'이라 금액을 안 적는다는 표현
DYNAMIC = ("일자별", "시간대별", "기후별", "실시간", "변동", "상이", "예약 시", "예약시",
           "별도 공지", "별도공지", "공지사항을 통해", "문의", "탄력", "시즌별 상이")
GREEN = re.compile(r"그린\s*피|그린피|green\s*fee", re.I)


def classify(pages):
    """(판정, 근거) — 그린피 금액이 실제로 적혀 있는지."""
    best = ("그린피 금액 없음", "")
    for page in pages:
        text = page["text"]
        for match in GREEN.finditer(text):
            window = text[match.start():match.start() + 260]
            amounts = enrich.MONEY_RE.findall(window)
            if not amounts:
                continue
            if any(word in window for word in DYNAMIC):
                best = ("변동가 안내 동반", window[:160])
                continue
            return "그린피 금액 있음", window[:160]
        if any(word in text for word in DYNAMIC) and GREEN.search(text) and best[0] == "그린피 금액 없음":
            best = ("변동가로 미공개", "")
    return best


def screen(club):
    fetcher = enrich._thread_fetcher()
    t0 = time.time()
    row = {"id": club["id"], "name": club["name"], "area": club.get("area"),
           "official_url": club.get("official_url")}
    try:
        pages, images = enrich.crawl(club["official_url"], fetcher, collect_images=True)
        verdict, evidence = classify(pages)
        if verdict == "그린피 금액 없음" and images:
            verdict = "요금표 이미지 가능성"
        row.update(verdict=verdict, evidence=evidence, pages=len(pages), images=images[:4],
                   chars=sum(len(p["text"]) for p in pages))
        if not pages or row["chars"] < 200:
            row["verdict"] = "접속 불가/본문 없음"
    except Exception as exc:
        row.update(verdict="오류", evidence=str(exc)[:120])
    row["seconds"] = round(time.time() - t0, 1)
    print(f"- {row['name']}: {row['verdict']} ({row['seconds']}s)", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    targets = enrich.pick_missing_fees(args.limit)
    print(f"검사 대상 {len(targets)}곳 (AI 호출 없음)", flush=True)

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(screen, c) for c in targets]
        for fut in as_completed(futures):
            rows.append(fut.result())
        list(ex.map(lambda _: enrich._close_thread_fetcher(), range(args.workers)))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"screen_{date.today().isoformat()}_{int(time.time())}.json"
    out.write_text(json.dumps({"created_at": date.today().isoformat(), "results": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")

    summary = {}
    for row in rows:
        summary[row["verdict"]] = summary.get(row["verdict"], 0) + 1
    print("\n=== 결과 ===")
    for k, v in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"{v:4d}  {k}")
    worth = [r for r in rows if r["verdict"] in ("그린피 금액 있음", "요금표 이미지 가능성", "변동가 안내 동반")]
    print(f"\nAI 재수집 가치 있는 곳: {len(worth)}곳")
    print("ids:", ",".join(r["id"] for r in worth))
    print("saved", out)


if __name__ == "__main__":
    main()
