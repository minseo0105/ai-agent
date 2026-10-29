"""시연(11/17) 부하 테스트: 가상 사용자 N명이 휴대폰처럼 공개 주소를 돈다. docs/DEMO_READINESS.md 4절.

시나리오(사람마다): AI LAB 메인 → 머니온 체험 시작 → 기록 1건(사람마다 고유 금액) → AI 3기능(편지·코치·리포트, SSE 끝까지)
→ 내 기록에 내 금액만 있는지(섞임 검사) → STOCK:ON 뉴스 속 숨은 종목(이슈 넘기며 회사 '왜 움직였나' 2번, 일부는 직접 입력:
이미 저장된 단어라 AI 호출 없음) → 오늘 시장 탭(15초마다 live, 60초마다 overview)을 HOLD초 유지.

머니온 AI는 서버에서 MONEYON_AI_FAKE=1일 때만 돌린다(비용 0). 이 스크립트는 그 설정을 바꾸지 않는다.
결과: 이름별 횟수·중앙값·p95·최대·5xx/연결 실패·4xx, 머니온 AI 결과 출처(ai/prepared/rule)와 이유, 섞임 수.
만든 체험 토큰은 --tokens 파일에 남긴다(테스트 뒤 서버에서 지우는 데 쓴다).

  python scripts/demo_load_test.py --base https://140-245-88-198.sslip.io --users 100 --ramp 60 --hold 300 --out reports/load.json
"""
import argparse
import asyncio
import json
import random
import re
import statistics
import time
from collections import Counter, defaultdict

import httpx

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 KAKAOTALK 10.8.0"
rows = []          # (name, status, seconds, error)
ai_done = Counter()
ai_reason = Counter()
ai_first = defaultdict(list)   # feature → 첫 글자까지 초
ai_queue = Counter()
mixed = {"checked": 0, "bad": 0}
tokens = []


def record(name, status, sec, err=""):
    rows.append((name, status, sec, err))


async def req(client, name, method, url, **kw):
    t = time.perf_counter()
    try:
        r = await client.request(method, url, **kw)
        record(name, r.status_code, time.perf_counter() - t)
        return r
    except Exception as e:  # 연결 실패·시간 초과
        record(name, 0, time.perf_counter() - t, type(e).__name__)
        return None


async def sse(client, feature, url, headers, body):
    t = time.perf_counter()
    first, source, reason, status = None, None, None, 0
    try:
        async with client.stream("POST", url, headers=headers, json=body, timeout=60) as r:
            status = r.status_code
            event = None
            async for line in r.aiter_lines():
                if line.startswith("event: "):
                    event = line[7:].strip()
                    if event == "queue":
                        ai_queue[feature] += 1
                elif line.startswith("data: ") and event:
                    if event == "delta" and first is None:
                        first = time.perf_counter() - t
                    if event == "done":
                        d = json.loads(line[6:])
                        source, reason = d.get("source"), d.get("reason") or ""
        record(f"mo_ai_{feature}", status, time.perf_counter() - t)
    except Exception as e:
        record(f"mo_ai_{feature}", 0, time.perf_counter() - t, type(e).__name__)
    if first is not None:
        ai_first[feature].append(first)
    ai_done[f"{feature}:{source}"] += 1
    if reason:
        ai_reason[f"{feature}:{reason}"] += 1


async def user(uid, base, start_at, hold, words, codes):
    await asyncio.sleep(start_at)
    limits = httpx.Limits(max_connections=6, max_keepalive_connections=6)
    async with httpx.AsyncClient(base_url=base, headers={"User-Agent": UA}, timeout=30, limits=limits, follow_redirects=True) as c:
        r = await req(c, "page_home", "GET", "/")
        if r is not None and r.status_code == 200:
            assets = re.findall(r'/_next/static/[^"\']+\.js', r.text)[:3]
            await asyncio.gather(*(req(c, "static", "GET", a) for a in assets))
        await asyncio.sleep(random.uniform(2, 5))

        # 머니온
        await req(c, "page_moneyon", "GET", "/moneyon/")
        r = await req(c, "mo_demo_start", "POST", "/moneyon/api/moneyon/trial/demo")
        if r is not None and r.status_code == 200:
            d = r.json()
            token, child = d["token"], d["child"]["id"]
            tokens.append(token)
            h = {"X-Moneyon-Trial": token, "X-Moneyon-Trial-Version": str(d.get("generation", 1))}
            books = [b for b in d["state"].get("books") or [] if b.get("status") != "pending" and b.get("target")]
            mine = f"lt{uid:04d}"   # 사람마다 고유 메모(체험 잔액이 적어 금액 대신 메모로 구분)
            await asyncio.sleep(random.uniform(1, 3))
            await req(c, "mo_write", "POST", f"/moneyon/api/moneyon/trial/children/{child}/transactions", headers=h,
                      json={"kind": "expense", "key": f"load-{uid}-{int(time.time())}", "amount": 100, "category": "기타", "note": mine})
            for feature in ("letter", "coach", "parent"):
                await asyncio.sleep(random.uniform(1, 4))
                body = {"book_id": books[0]["id"], "weekly": 1000} if feature == "coach" and books else {}
                if feature == "coach" and not books:
                    continue
                await sse(c, feature, f"/moneyon/api/moneyon/trial/ai/{feature}", h, body)
            r = await req(c, "mo_state", "GET", "/moneyon/api/moneyon/trial/state", headers=h)
            if r is not None and r.status_code == 200:
                txs = r.json()["state"].get("transactions") or []
                notes = [t.get("note") or "" for t in txs]
                load_notes = [n for n in notes if re.fullmatch(r"lt\d{4}", n)]
                mixed["checked"] += 1
                if load_notes != [mine]:
                    mixed["bad"] += 1

        # STOCK:ON 뉴스 속 숨은 종목
        await asyncio.sleep(random.uniform(1, 3))
        await req(c, "page_stock", "GET", "/stock")
        await req(c, "st_lifemap", "GET", "/api/stock/lifemap")
        for code in random.sample(codes, min(2, len(codes))):
            await asyncio.sleep(random.uniform(3, 8))     # 이슈 넘기기·지도 보기
            await req(c, "st_why", "GET", f"/api/stock/why/{code}")
        if words and uid % 5 == 0:
            await req(c, "st_word", "POST", "/api/stock/lifemap/word", json={"word": random.choice(words)},
                      headers={"X-Stockon-Session": f"loadtest{uid:04d}session"})

        # 오늘 시장 탭: 15초마다 live, 60초마다 overview
        await req(c, "st_overview", "GET", "/api/stock/overview")
        end = time.monotonic() + hold
        n = 0
        while time.monotonic() < end:
            await req(c, "st_live", "GET", "/api/stock/live")
            n += 1
            if n % 4 == 0:
                await req(c, "st_overview", "GET", "/api/stock/overview")
            await asyncio.sleep(15)


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None


def summary():
    by = defaultdict(list)
    for name, status, sec, err in rows:
        by[name].append((status, sec, err))
    table = {}
    for name in sorted(by):
        xs = by[name]
        secs = [s for st, s, e in xs if st]
        table[name] = {
            "n": len(xs),
            "median_ms": round(statistics.median(secs) * 1000) if secs else None,
            "p95_ms": round(pct(secs, 95) * 1000) if secs else None,
            "max_ms": round(max(secs) * 1000) if secs else None,
            "err5xx_or_conn": sum(1 for st, s, e in xs if st == 0 or st >= 500),
            "err4xx": sum(1 for st, s, e in xs if 400 <= st < 500),
            "errors": dict(Counter(e or str(st) for st, s, e in xs if st == 0 or st >= 400)),
        }
    total = len(rows)
    bad = sum(v["err5xx_or_conn"] for v in table.values())
    return {
        "requests": total, "error_rate_5xx_conn": round(bad / total * 100, 2) if total else 0,
        "by_name": table,
        "ai_done": dict(ai_done), "ai_reason": dict(ai_reason), "ai_queue_events": dict(ai_queue),
        "ai_first_token_ms": {f: {"median": round(statistics.median(v) * 1000), "p95": round(pct(v, 95) * 1000)} for f, v in ai_first.items() if v},
        "mixed": mixed,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--ramp", type=float, default=60)
    ap.add_argument("--hold", type=float, default=300)
    ap.add_argument("--out", default="load.json")
    ap.add_argument("--tokens", default="load_tokens.txt")
    ap.add_argument("--words", default="캠핑,보안", help="이미 저장된 직접 입력 단어(AI 호출 없음)")
    a = ap.parse_args()
    async with httpx.AsyncClient(base_url=a.base, timeout=30) as c:
        life = (await c.get("/api/stock/lifemap")).json()
    codes = sorted({co["code"] for t in life.get("topics", []) for s in t["map"]["stages"] for co in s["companies"] if co.get("code")})
    words = [w for w in a.words.split(",") if w]
    print(f"회사 {len(codes)}곳, 저장 단어 {len(words)}개, 사용자 {a.users}명, ramp {a.ramp}s, hold {a.hold}s")
    t0 = time.time()
    await asyncio.gather(*(user(i, a.base, a.ramp * i / a.users, a.hold, words, codes) for i in range(a.users)))
    s = summary()
    s.update(started=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0)), seconds=round(time.time() - t0), users=a.users)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    with open(a.tokens, "w", encoding="utf-8") as f:
        f.write("\n".join(tokens))
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
