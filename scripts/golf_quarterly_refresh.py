"""골프 DB 분기 갱신: 공식 홈페이지 재수집 → 인용 검증 → DB 반영(갱신 규칙) → 보고서.

- 대상: 추천 Pool 중 공식 홈페이지가 있는 골프장 (기본 전체, --limit 로 제한 가능)
- 반영: scripts/apply_golf_review.py 의 규칙(--refresh)을 그대로 사용
    빈칸 채움 / 자동수집 값은 갱신 / 정밀 작업 값과 다르면 덮어쓰지 않고 '확인 필요'로 보고
- 산출물: data/golf/enrichment_review/ 에 수집 원본(json)과 보고서(md)

사용:
  venv\\Scripts\\python.exe scripts\\golf_quarterly_refresh.py            # 전체
  venv\\Scripts\\python.exe scripts\\golf_quarterly_refresh.py --limit 5  # 시험
  venv\\Scripts\\python.exe scripts\\golf_quarterly_refresh.py --dry-run  # DB 저장 없이 보고서만
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_golf_review import apply_review  # noqa: E402
from golf_official_enrich import MODEL, OUT_DIR, run  # noqa: E402
from services import golf_service as gs  # noqa: E402

# claude-opus-5 공개 요금 (USD / 1M tokens) — 보고서의 비용 추정용
PRICE_IN, PRICE_OUT = 5.0, 25.0


def targets(limit=None):
    _, _, pool = gs.load_pools()
    clubs = sorted((c for c in pool if str(c.get("official_url") or "").startswith("http")), key=lambda c: c["id"])
    return clubs[:limit] if limit else clubs


def write_report(review_path, applied):
    review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    results = review["results"]
    usage = review["usage"]
    cost = usage["input_tokens"] / 1e6 * PRICE_IN + usage["output_tokens"] / 1e6 * PRICE_OUT
    failed = [r for r in results if r["status"] != "pending_review"]
    changed = [s for s in applied["items"] if s["changes"]]
    conflicts = [s for s in applied["items"] if s["conflicts"]]

    lines = [
        f"# 골프 DB 분기 갱신 보고서 · {date.today().isoformat()}",
        "",
        f"- 대상 {len(results)}곳 · 수집 성공 {len(results) - len(failed)}곳 · 실패 {len(failed)}곳",
        f"- DB 반영 {applied['changed']}곳{' (dry-run: 저장 안 함)' if applied['dry_run'] else ''} · 확인 필요 {len(conflicts)}곳",
        f"- DB 파일: {applied['db']}" + (f" · 백업: {applied['backup']}" if applied["backup"] else ""),
        f"- 모델 {MODEL} · 토큰 입력 {usage['input_tokens']:,} / 출력 {usage['output_tokens']:,} · 추정 비용 ${cost:.2f}",
        f"- 수집 원본: {Path(review_path).name}",
        "",
        "## 반영된 변경",
    ]
    lines += [f"- {s['name']}: {', '.join(s['changes'])}" for s in changed] or ["- 없음"]
    lines += ["", "## 확인 필요 (정밀 DB 값과 공식 홈페이지 값이 다름 · 덮어쓰지 않음)"]
    for s in conflicts:
        for c in s["conflicts"]:
            lines.append(f"- {s['name']} · {c['field']}: DB={c['existing']} / 홈페이지={c['new']} · {c['source_url']}")
    if not conflicts:
        lines.append("- 없음")
    lines += ["", "## 수집 실패"]
    lines += [f"- {r['name']} ({r['status']}): {r.get('error', '')}" for r in failed] or ["- 없음"]

    report = Path(review_path).with_suffix(".md")
    report.write_text("\n".join(lines), encoding="utf-8")
    return report, cost


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    clubs = targets(args.limit or None)
    print(f"[quarterly] 대상 {len(clubs)}곳", flush=True)
    review_path = run(clubs, label="quarterly")
    applied = apply_review(review_path, refresh=True, dry_run=args.dry_run)
    report, cost = write_report(review_path, applied)
    print(f"[quarterly] 반영 {applied['changed']}곳 · 추정 비용 ${cost:.2f} · 보고서 {report}", flush=True)


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    main()
