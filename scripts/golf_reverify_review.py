"""이미 수집해 둔 결과를 다시 검증한다. (페이지만 다시 받으므로 AI 비용 없음)

인용 검증 규칙이 개선되면(예: '18.8만' 같은 만원 표기 인식) 예전에 걸러졌던 값이
되살아날 수 있다. 원문을 다시 받아 인용이 실제로 있는지 확인하고 verified_quote를 다시 매긴다.
값을 새로 만들지 않고, 기존 수집 결과의 검증 결과만 갱신한다.

결과: 입력 파일과 같은 폴더에 <원본이름>_reverified.json

사용:
  venv\\Scripts\\python.exe scripts\\golf_reverify_review.py <review.json> [--only-missing]
"""

import argparse
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("enrich", ROOT / "scripts" / "golf_official_enrich.py")
enrich = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enrich)

from services import golf_service as gs  # noqa: E402


def refetch(result):
    """수집 당시 읽었던 페이지들을 다시 받아 본문을 되살린다."""
    fetcher = enrich._thread_fetcher()
    pages = []
    for page in result.get("pages") or []:
        got = fetcher.get(page["url"], want_amounts=True)
        if got:
            pages.append({"url": got[0], "text": enrich.page_text(got[1])})
    return pages


def reverify(result):
    ex = result.get("extraction") or {}
    if not ex.get("green_fees"):
        return result, 0
    pages = refetch(result)
    if not pages:
        result["reverify"] = "본문을 다시 받지 못함"
        return result, 0

    gained = 0
    for row in ex["green_fees"]:
        before = bool(row.get("verified_quote"))
        after = enrich.verify_quote(pages, row["source_url"], row["quote"], row["price_krw"])
        row["verified_quote"] = after
        if after and not before:
            gained += 1
    for key in ("caddie_fee", "cart_fee"):
        if ex.get(key):
            ex[key]["verified_quote"] = enrich.verify_quote(
                pages, ex[key]["source_url"], ex[key]["quote"], ex[key].get("fee_team_krw"))
    result["reverify"] = f"재검증 완료 (+{gained}행)"
    print(f"- {result['name']}: +{gained}행", flush=True)
    return result, gained


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("review")
    ap.add_argument("--only-missing", action="store_true", help="아직 요금이 비어 있는 곳만")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    path = Path(args.review)
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results") or []

    if args.only_missing:
        _, _, pool = gs.load_pools()
        missing = {c["id"] for c in pool if not (c.get("pricing") or {}).get("fee_records")}
        targets = [r for r in results if r["id"] in missing and (r.get("extraction") or {}).get("green_fees")]
    else:
        targets = [r for r in results if (r.get("extraction") or {}).get("green_fees")]
    print(f"재검증 대상 {len(targets)}곳", flush=True)

    total = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(reverify, r) for r in targets]
        for fut in as_completed(futures):
            _, gained = fut.result()
            total += gained
        list(ex.map(lambda _: enrich._close_thread_fetcher(), range(args.workers)))

    out = path.with_name(path.stem + "_reverified.json")
    data["reverified_at"] = time.strftime("%Y-%m-%d")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n되살아난 행: {total}개\nsaved {out}")


if __name__ == "__main__":
    main()
