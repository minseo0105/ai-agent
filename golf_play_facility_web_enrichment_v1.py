# -*- coding: utf-8 -*-
"""
Golf Play/Facility Web Enrichment v1
====================================
목적:
- 553개 골프장 이용조건을 골프장당 통합 검색 1회로 조사
- 2인 / 3인 / 9홀×2 / 야간 / PAR3 / 야외연습장 후보 근거 수집
- catalog.json 자동 수정 금지
- 중단 후 재실행 가능
- 1회 실행 기본 최대 150 Tavily 호출
- 결과는 data/golf/enrichment/play_facility_web_v1 에 저장

중요:
- 이 스크립트는 검색 결과를 "확정"하지 않는다.
- 공식/예약/이용안내 URL과 문맥을 수집해 다음 검증 단계의 입력으로 사용한다.
"""

from __future__ import annotations

import json
import os
import re
import time
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "data" / "golf" / "catalog.json"
MASTER = ROOT / "data" / "golf" / "master" / "golf_master.json"
OUTROOT = ROOT / "data" / "golf" / "enrichment" / "play_facility_web_v1"

EXPECTED_COUNT = 553
MAX_CALLS_PER_RUN = 150
CHECKPOINT_EVERY = 25
SEARCH_DEPTH = "advanced"
MAX_RESULTS = 7

FIELDS = {
    "two_person": "2인 플레이",
    "three_person": "3인 플레이",
    "nine_hole_twice": "9홀×2 라운드",
    "night_round": "야간 라운드",
    "par3": "PAR3 연습장",
    "driving_range": "야외 연습장",
}

FIELD_PATTERNS = {
    "two_person": [
        r"2인\s*(플레이|라운드|라운딩|예약|내장)",
        r"2인플레이", r"2인라운드", r"2인\s*가능",
    ],
    "three_person": [
        r"3인\s*(플레이|라운드|라운딩|예약|내장)",
        r"3인플레이", r"3인라운드", r"3인\s*가능",
    ],
    "nine_hole_twice": [
        r"9홀\s*[x×X*]\s*2", r"9홀\s*2회", r"9홀.*두\s*바퀴",
        r"9홀.*18홀",
    ],
    "night_round": [
        r"야간\s*(라운드|라운딩|운영|개장|예약|3부)",
        r"나이트\s*(라운드|라운딩|운영)", r"3부\s*(운영|예약|라운드)",
    ],
    "par3": [
        r"(PAR|Par|par)\s*3\s*(연습장|코스)",
        r"파\s*3\s*(연습장|코스)",
    ],
    "driving_range": [
        r"야외\s*(골프)?\s*연습장",
        r"드라이빙\s*레인지",
        r"driving\s*range",
    ],
}

CONDITION_WORDS = [
    "주중", "주말", "평일", "토요일", "일요일", "공휴일",
    "조조", "시간대", "시즌", "기간", "이벤트", "회원",
    "추가요금", "별도요금", "캐디피", "카트비", "동반",
    "문의", "예약실", "선착순", "한시", "마감",
]
NEG_WORDS = ["불가", "불가능", "미운영", "운영하지 않", "없음", "종료"]

WEAK_DOMAINS = {
    "blog.naver.com", "m.blog.naver.com", "tistory.com", "youtube.com",
    "instagram.com", "facebook.com", "dbegl.com", "baigolf.com",
    "sbs.co.kr", "kakao.com",
}

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def get_secret_from_toml():
    p = ROOT / ".streamlit" / "secrets.toml"
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8-sig")
    # 단순 TOML 문자열 키 추출. 실제 키 값은 출력하지 않는다.
    for key in ("TAVILY_API_KEY", "TAVILY_KEY"):
        m = re.search(rf'(?m)^\s*{re.escape(key)}\s*=\s*["\']([^"\']+)["\']\s*$', txt)
        if m:
            return m.group(1).strip()
    return ""

def tavily_key():
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if key:
        return key
    key = get_secret_from_toml()
    if key:
        return key
    raise RuntimeError(
        "TAVILY_API_KEY를 찾지 못했습니다. "
        ".streamlit/secrets.toml 또는 환경변수를 확인하세요."
    )

def domain(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""

def norm(s):
    return re.sub(r"[^0-9a-z가-힣]", "", str(s or "").lower())

def likely_same_course(name, text):
    nn = norm(name)
    if not nn:
        return False
    variants = {nn}
    stripped = nn
    for suffix in ("골프클럽", "컨트리클럽", "골프장", "리조트", "cc", "gc"):
        stripped = stripped.replace(norm(suffix), "")
    if len(stripped) >= 3:
        variants.add(stripped)
    nt = norm(text)
    return any(len(v) >= 3 and v in nt for v in variants)

def extract_field_evidence(name, results):
    out = {}
    combined_items = []
    for r in results:
        title = str(r.get("title") or "")
        content = str(r.get("content") or "")
        url = str(r.get("url") or "")
        text = f"{title}\n{content}"
        same = likely_same_course(name, text)
        d = domain(url)
        weak = d in WEAK_DOMAINS or any(d.endswith("." + x) for x in WEAK_DOMAINS)
        combined_items.append({
            "title": title,
            "url": url,
            "domain": d,
            "content": content[:1800],
            "identity_match": same,
            "weak_source": weak,
            "score": r.get("score"),
        })

    for field, pats in FIELD_PATTERNS.items():
        evidence = []
        for item in combined_items:
            text = f"{item['title']}\n{item['content']}"
            for pat in pats:
                m = re.search(pat, text, re.I)
                if not m:
                    continue
                start = max(0, m.start() - 180)
                end = min(len(text), m.end() + 260)
                snippet = re.sub(r"\s+", " ", text[start:end]).strip()
                lower = snippet.lower()
                negative = any(w in lower for w in NEG_WORDS)
                conditional = any(w in lower for w in CONDITION_WORDS)
                evidence.append({
                    "url": item["url"],
                    "domain": item["domain"],
                    "title": item["title"],
                    "snippet": snippet,
                    "identity_match": item["identity_match"],
                    "weak_source": item["weak_source"],
                    "negative_signal": negative,
                    "conditional_signal": conditional,
                    "search_score": item["score"],
                })
                break
        out[field] = evidence[:8]
    return out, combined_items

def make_query(club):
    name = str(club.get("name") or "").strip()
    area = str(club.get("area") or "").strip()
    city = str(club.get("city") or "").strip()
    loc = " ".join(x for x in (area, city) if x)
    # 한 번의 검색에서 핵심 조건을 모두 찾도록 구성
    return (
        f'"{name}" {loc} '
        f'2인 3인 플레이 야간 라운드 9홀 2회 PAR3 연습장 '
        f'드라이빙레인지 이용안내 예약'
    ).strip()

def tavily_search(key, query):
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": key,
        "query": query,
        "search_depth": SEARCH_DEPTH,
        "max_results": MAX_RESULTS,
        "include_answer": False,
        "include_raw_content": False,
    }
    last = None
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=35)
            r.raise_for_status()
            data = r.json()
            return data.get("results") or []
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Tavily 검색 실패: {last}")

def latest_checkpoint():
    if not OUTROOT.exists():
        return None
    files = list(OUTROOT.rglob("checkpoint_*.json"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)

def save_checkpoint(state):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    processed = len(state.get("records") or [])
    p = OUTROOT / f"checkpoint_{processed:04d}_{stamp}.json"
    save_json(p, state)
    return p

def main():
    if not CATALOG.exists():
        raise FileNotFoundError(CATALOG)

    before_hash = sha256(CATALOG)
    catalog = load_json(CATALOG)
    if isinstance(catalog, dict):
        clubs = catalog.get("clubs") or catalog.get("records") or catalog.get("data") or []
    else:
        clubs = catalog

    if len(clubs) != EXPECTED_COUNT:
        raise RuntimeError(f"안전 중단: catalog={len(clubs)} / expected={EXPECTED_COUNT}")

    key = tavily_key()

    cp = latest_checkpoint()
    if cp:
        state = load_json(cp)
        print("기존 checkpoint 재개:", cp)
    else:
        state = {
            "schema_version": "1.0",
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "catalog_count": len(clubs),
            "records": [],
            "errors": [],
        }

    done_ids = {str(x.get("id") or "") for x in state.get("records") or []}
    done_ids |= {str(x.get("id") or "") for x in state.get("errors") or []}

    remaining = [c for c in clubs if str(c.get("id") or "") not in done_ids]
    calls = 0

    print("=" * 72)
    print("Golf Play / Facility Web Enrichment v1")
    print("=" * 72)
    print("catalog:", len(clubs))
    print("이미 처리:", len(done_ids))
    print("남은 골프장:", len(remaining))
    print("이번 실행 최대 Tavily:", MAX_CALLS_PER_RUN)
    print("catalog.json 자동수정: False")
    print()

    for idx, club in enumerate(remaining, 1):
        if calls >= MAX_CALLS_PER_RUN:
            break

        cid = str(club.get("id") or "")
        name = str(club.get("name") or "")
        query = make_query(club)

        try:
            results = tavily_search(key, query)
            calls += 1
            fields, raw_results = extract_field_evidence(name, results)
            record = {
                "id": cid,
                "name": name,
                "query": query,
                "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "fields": fields,
                "results": raw_results,
            }
            state["records"].append(record)
            hits = sum(1 for v in fields.values() if v)
            print(f"[{len(done_ids)+idx}/{len(clubs)}] {name} / 조건근거 {hits}종")
        except Exception as e:
            state["errors"].append({
                "id": cid,
                "name": name,
                "error": str(e),
                "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            })
            print(f"[ERROR] {name}: {e}")

        if (calls and calls % CHECKPOINT_EVERY == 0):
            p = save_checkpoint(state)
            print("  checkpoint:", p.name)

    state["last_run_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    state["last_run_calls"] = calls
    state["processed_count"] = len(state.get("records") or []) + len(state.get("errors") or [])
    state["complete"] = state["processed_count"] >= len(clubs)

    cpout = save_checkpoint(state)

    # 매 실행마다 현재 누적 결과도 timestamp 파일로 저장
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = OUTROOT / f"result_{stamp}.json"
    save_json(result_path, state)

    # 간단 집계
    counts = {f: 0 for f in FIELDS}
    identity_good = {f: 0 for f in FIELDS}
    conditional = {f: 0 for f in FIELDS}
    negative = {f: 0 for f in FIELDS}
    for rec in state.get("records") or []:
        for f, evs in (rec.get("fields") or {}).items():
            if evs:
                counts[f] += 1
            if any(e.get("identity_match") and not e.get("weak_source") for e in evs):
                identity_good[f] += 1
            if any(e.get("conditional_signal") for e in evs):
                conditional[f] += 1
            if any(e.get("negative_signal") for e in evs):
                negative[f] += 1

    report = {
        "created_at": state["last_run_at"],
        "catalog_count": len(clubs),
        "processed_count": state["processed_count"],
        "complete": state["complete"],
        "this_run_tavily_calls": calls,
        "field_course_hits": counts,
        "field_course_stronger_identity_hits": identity_good,
        "field_course_conditional_hits": conditional,
        "field_course_negative_hits": negative,
        "catalog_sha256_before": before_hash,
        "catalog_sha256_after": sha256(CATALOG),
        "catalog_unchanged": before_hash == sha256(CATALOG),
        "result": str(result_path),
    }
    report_path = OUTROOT / f"report_{stamp}.json"
    save_json(report_path, report)

    if sha256(CATALOG) != before_hash:
        raise RuntimeError("안전 중단: catalog.json이 변경되었습니다.")

    print()
    print("=" * 72)
    print("이번 실행 완료")
    print("=" * 72)
    print("누적 처리:", state["processed_count"], "/", len(clubs))
    print("이번 Tavily:", calls)
    print("완료 여부:", state["complete"])
    print("catalog.json 수정:", False)
    print()
    for f, label in FIELDS.items():
        print(
            f"{label}: 근거발견 {counts[f]} / "
            f"강한 identity {identity_good[f]} / "
            f"조건부 {conditional[f]} / 부정 {negative[f]}"
        )
    print()
    print("checkpoint:", cpout)
    print("result:", result_path)
    print("report:", report_path)
    if not state["complete"]:
        print()
        print("아직 남았습니다. 같은 명령을 다시 실행하면 이어서 처리합니다.")

if __name__ == "__main__":
    main()
