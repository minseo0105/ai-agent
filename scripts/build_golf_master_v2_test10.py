"""Run only the fixed 10-club review. No catalog apply option exists."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.golf_master_builder_v2 import TEST_IDS, build_report, digest, markdown_report


def check_url(task):
    import requests
    club_id, url = task
    result = {"club_id": club_id, "url": url,
              "checked_at": datetime.now().astimezone().isoformat(),
              "purpose": "HTTP availability only; does not certify identity or facts"}
    try:
        # Do not follow cross-host/branch redirects or disable TLS verification.
        # No keys, cookies, search API, LLM or raw page persistence.
        with requests.get(url, timeout=(8, 15), allow_redirects=False, stream=True) as response:
            result["status"] = response.status_code
            result["redirect"] = response.headers.get("Location")
            result["content_type"] = response.headers.get("Content-Type")
    except requests.RequestException as error:
        result["error"] = type(error).__name__
    return result


def run(fetch=False, reuse_http_report=None):
    catalog_path = ROOT / "data/golf/catalog.json"
    raw = catalog_path.read_bytes()
    catalog = json.loads(raw.decode("utf-8-sig"))
    dossier_path = ROOT / "data/golf/builder2/test10_sources.json"
    dossier_raw = dossier_path.read_bytes()
    dossier = json.loads(dossier_raw.decode("utf-8"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = ROOT / "data/golf/backups" / f"catalog_before_builder2_{stamp}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open("xb") as handle:
        handle.write(raw)
    if digest(backup.read_bytes()) != digest(raw):
        raise RuntimeError("백업 검증 실패")
    report = build_report(catalog, dossier)
    report.update(catalog_sha256=digest(raw), dossier_sha256=digest(dossier_raw),
                  backup=backup.relative_to(ROOT).as_posix(), http_checks=[])
    if reuse_http_report:
        prior = json.loads(Path(reuse_http_report).read_text(encoding="utf-8"))
        allowed = {(c['id'], c.get('official_url')) for c in catalog if c['id'] in TEST_IDS}
        allowed.update((cid, s['url']) for cid in TEST_IDS for s in dossier[cid]['sources'])
        report['http_checks'] = [c for c in prior.get('http_checks', [])
                                 if (c.get('club_id'), c.get('url')) in allowed]
        report['http_checks_reused_from'] = str(reuse_http_report)
    if fetch:
        tasks = []
        for c in catalog:
            if c.get("id") not in TEST_IDS:
                continue
            urls = [c.get("official_url")] + [s["url"] for s in dossier[c["id"]]["sources"]]
            tasks.extend((c["id"], url) for url in dict.fromkeys(urls) if url)
        with ThreadPoolExecutor(max_workers=4) as executor:
            report["http_checks"] = list(executor.map(check_url, tasks))
    if catalog_path.read_bytes() != raw:
        raise RuntimeError("실행 중 catalog가 변경되었습니다. 결과를 게시하지 않습니다.")
    out = ROOT / "data/golf/enrichment/builder2" / stamp
    out.mkdir(parents=True, exist_ok=False)
    (out / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps({"output": str(out), "clubs": report["test_count"],
                      "catalog_unchanged": catalog_path.read_bytes() == raw,
                      "http_checks": len(report["http_checks"]),
                      "supported_fields": sum(v["value"] is not None for c in report["clubs"] for v in c["facts"].values()),
                      "kga_quarantined": sum(len(c["kga"]["ratings_quarantined"]) for c in report["clubs"])}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fetch", action="store_true", help="Read-only HTTP availability checks; no page persistence")
    mode.add_argument("--reuse-http-report", help="Reuse timestamped HTTP checks from an earlier result.json without new requests")
    args = parser.parse_args()
    run(fetch=args.fetch, reuse_http_report=args.reuse_http_report)
