"""Evidence-first extraction. Labels/counts/confidence are calculated, never trusted from LLM."""
import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from services.golf_api import GolfAPIError, collect_reviews, extract_observations, secret_status
from services.golf_catalog import normalize_name

ASPECTS = {"difficulty": "난이도", "fairway": "페어웨이", "green": "그린",
           "maintenance": "코스관리", "facilities": "시설", "caddie": "캐디"}
LABELS = {
    "difficulty": {"easy": "쉬운 편", "moderate": "보통", "hard": "어려운 편"},
    "fairway": {"wide": "넓은 편", "moderate": "보통", "narrow": "좁은 편"},
    "green": {"fast": "빠른 편", "moderate": "보통", "slow": "느린 편"},
    **{k: {"positive": "긍정적", "neutral": "보통", "negative": "부정적"}
       for k in ("maintenance", "facilities", "caddie")}}
ASPECT_TERMS = {
    "difficulty": r"난이도|어렵|어려|쉽|쉬[운웠워]|부담|전장|해저드|벙커|도전",
    "fairway": r"페어웨이|페어웨|훼어웨이|페어웨이폭",
    "green": r"그린|퍼팅", "maintenance": r"관리|잔디|디봇|보수|상태",
    "facilities": r"시설|클럽하우스|락커|라커|샤워|식당|주차|탈의",
    "caddie": r"캐디|캐디님", "scenery": r"경관|경치|풍경|전망|조망",
    "value": r"가성비|가격|그린피|비용|요금", "accessibility": r"접근|거리|이동|교통|IC|나들목"}
AD_PATTERN = re.compile(r"예약\s*(문의|대행|상담|모집)|회원권\s*(매매|분양|상담|급매)|"
                        r"협찬|원고료|소정의\s*(수수료|대가)|제공받|제공\s*받|광고\s*포함|체험단|"
                        r"특가\s*(예약|모집)|골프\s*패키지|프로모션|#광고|유료광고", re.I)
ROUND_PATTERN = re.compile(r"다녀왔|다녀온|라운[딩드].{0,12}(했|마쳤|즐겼)|"
                           r"플레이.{0,12}(했|마쳤)|치고\s*왔|쳤|돌았|방문했")
LIMITATION = "Naver 검색 결과 제목·요약문 기반이며 후기 전문을 읽은 분석이 아닙니다. 광고·실제 경험 여부와 최신 상태를 완전히 확인할 수 없습니다."


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


OBSERVATION_SCHEMA = object_schema({
    "aspect": {"type": "string", "enum": list(ASPECTS)},
    "value": {"type": "string", "enum": sorted({v for values in LABELS.values() for v in values})},
    "quote": {"type": "string"}, "course": {"type": "string"}})
EXTRACTION_SCHEMA = object_schema({"documents": {"type": "array", "items": object_schema({
    "id": {"type": "string"}, "eligible": {"type": "boolean"},
    "experience_quote": {"type": "string"}, "reason": {"type": "string"},
    "observations": {"type": "array", "items": OBSERVATION_SCHEMA}})}})


def canonical_url(url):
    try:
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
            return ""
        host = p.hostname.lower().removeprefix("www.")
        q = parse_qs(p.query)
        if host in ("blog.naver.com", "m.blog.naver.com"):
            parts = p.path.strip("/").split("/")
            if "blogId" in q and "logNo" in q:
                return f"https://blog.naver.com/{q['blogId'][0]}/{q['logNo'][0]}"
            if len(parts) == 2 and parts[1].isdigit():
                return f"https://blog.naver.com/{parts[0]}/{parts[1]}"
            host = "blog.naver.com"
        query = urlencode(sorted((k, v) for k, values in q.items()
                                 if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
                                 for v in values))
        return urlunsplit(("https", host, p.path.rstrip("/"), query, ""))
    except (ValueError, TypeError):
        return ""


def source_group(url, author_url=""):
    p = urlsplit(url)
    if p.hostname == "blog.naver.com":
        return f"naver:{p.path.strip('/').split('/')[0]}"
    author = canonical_url(author_url)
    # Unknown authors on a common site count as ONE source, never independent posts.
    return author or p.hostname


def prepare_candidates(club, records, limit=600):
    grouped, excluded = {}, []
    names = [normalize_name(n) for n in [club["name"], *club.get("aliases", [])]]
    for raw in records:
        row = dict(raw)
        row["url"] = canonical_url(row.get("url", ""))
        if not row["url"]:
            excluded.append({"url": "", "title": row.get("title", ""), "category": "invalid", "reason": "유효한 URL 없음"})
            continue
        if row["url"] in grouped:
            prior = grouped[row["url"]]
            for text in (row.get("title", ""), row.get("description", "")):
                if text and text not in prior["snippets"]:
                    prior["snippets"].append(text)
            prior["description"] = "\n".join(prior["snippets"])
            excluded.append({"url": row["url"], "title": row.get("title", ""), "category": "duplicate", "reason": "동일 URL 중복 (요약 병합)"})
        else:
            row["snippets"] = [row.get("title", ""), row.get("description", "")]
            grouped[row["url"]] = row
    candidates, titles, texts = [], [], []
    for row in grouped.values():
        text = " ".join(row["snippets"])
        title, snippet = normalize_name(row.get("title", "")), normalize_name(row.get("description", ""))
        reason, category = None, None
        if AD_PATTERN.search(text):
            reason, category = "광고·협찬·예약/판매 홍보 표현", "advertising"
        elif (not any(n in normalize_name(text) for n in names)
              or any(normalize_name(n) in normalize_name(text) for n in club.get("excluded_names", []))):
            reason, category = "대상 골프장과 무관하거나 유사명 혼동", "irrelevant"
        elif not title or len(row.get("description", "")) < 20:
            reason, category = "제목 또는 요약 근거 부족", "short"
        elif any(title == t or (min(len(title), len(t)) >= 18 and SequenceMatcher(None, title, t).ratio() >= .94) for t in titles):
            reason, category = "동일·거의 동일한 제목", "duplicate"
        elif any(SequenceMatcher(None, snippet, t).ratio() >= .90 for t in texts):
            reason, category = "동일·거의 동일한 요약문", "duplicate"
        if reason:
            excluded.append({"url": row["url"], "title": row.get("title", ""), "category": category, "reason": reason})
            continue
        titles.append(title)
        texts.append(snippet)
        row["id"] = f"E{len(candidates) + 1:03d}"
        row["source_group"] = source_group(row["url"], row.get("author_url", ""))
        row["dimension_candidates"] = {a: [s for s in row["snippets"] if re.search(ASPECT_TERMS[a], s, re.I)] for a in ASPECTS}
        candidates.append(row)
    if len(candidates) > limit:
        raise GolfAPIError("검증 범위(600개)를 초과했습니다.")
    return candidates, excluded, len(grouped)


def unknown_metric():
    return {"label": "정보 부족", "evidence_count": 0, "confidence": "low",
            "evidence_ids": [], "summary": "독립적인 유효 근거가 2건 이상 필요합니다."}


def aggregate(aspect, observations, evidence):
    result = unknown_metric()
    groups = defaultdict(list)
    for o in observations:
        groups[evidence[o["evidence_id"]]["source_group"]].append(o)
    # Each author/domain contributes at most once. Conflicting same-source opinions abstain.
    independent = [rows[0] for rows in groups.values() if len({r["value"] for r in rows}) == 1]
    ids = sorted({o["evidence_id"] for o in independent})
    result.update(evidence_count=len(ids), evidence_ids=ids)
    if len(ids) < 2:
        return result
    counts = Counter(o["value"] for o in independent)
    winner, count = counts.most_common(1)[0]
    opposing = set(counts) - {"neutral", "moderate"}
    if len(opposing) >= 2 and max(counts[v] for v in opposing) / len(ids) <= .7:
        label = "평가가 엇갈림"
    elif count < 2 or count / len(ids) < .7:
        label = "평가가 엇갈림"
    else:
        label = LABELS[aspect][winner]
    result.update(label=label, confidence="medium",
                  summary=f"독립 출처 {len(ids)}곳의 검색 요약 근거: " +
                  ", ".join(f"{LABELS[aspect][v]} {n}건" for v, n in counts.items()) +
                  ". 요약문 기반으로 신뢰도는 최대 보통입니다.")
    return result


def build_analysis(club, collection, candidates, excluded, unique_count, extraction, model):
    docs = extraction.get("documents") if isinstance(extraction, dict) else None
    expected = {r["id"] for r in candidates}
    if not isinstance(docs, list) or any(not isinstance(d, dict) for d in docs):
        raise GolfAPIError("AI 응답 구조가 올바르지 않아 저장하지 않았습니다.")
    ids = [d.get("id") for d in docs]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise GolfAPIError("AI 응답의 출처 ID가 누락·중복되어 저장하지 않았습니다.")
    by_id = {r["id"]: r for r in candidates}
    evidence, observations, warnings = {}, [], []
    audit = list(excluded)
    for doc in docs:
        row = by_id[doc["id"]]
        quote = doc.get("experience_quote", "")
        if (doc.get("eligible") is not True or not isinstance(quote, str) or len(quote) < 5
                or not any(quote in snippet for snippet in row["snippets"])
                or not ROUND_PATTERN.search(quote)):
            audit.append({"url": row["url"], "title": row["title"],
                          "reason": "실제 라운딩 경험 근거 부족 또는 AI 부적격 판정",
                          "model_reason": str(doc.get("reason", ""))[:300]})
            continue
        accepted = []
        seen = set()
        for o in doc.get("observations", []):
            if not isinstance(o, dict):
                warnings.append(f"{row['id']}: 잘못된 근거 구조 제외")
                continue
            aspect, value, text, course = (o.get(k, "") for k in ("aspect", "value", "quote", "course"))
            if (aspect not in ASPECTS or value not in LABELS.get(aspect, {})
                    or not isinstance(text, str) or len(text) < 5
                    or not any(text in snippet for snippet in row["snippets"])
                    or not re.search(ASPECT_TERMS[aspect], text, re.I)
                    or not isinstance(course, str)
                    or (course and (not re.fullmatch(r"[가-힣A-Za-z0-9 ]{1,20}코스", course)
                                    or course not in text))):
                warnings.append(f"{row['id']}: 인용문/항목/코스 검증 실패 근거 제외")
                continue
            key = (aspect, course)
            if key not in seen:
                seen.add(key)
                accepted.append({**o, "evidence_id": row["id"]})
        if not accepted:
            audit.append({"url": row["url"], "title": row["title"], "reason": "검증된 평가항목 근거 없음"})
            continue
        evidence[row["id"]] = {**row, "experience_quote": quote}
        observations.extend(accepted)
    metrics = {a: aggregate(a, [o for o in observations if o["aspect"] == a], evidence) for a in ASPECTS}
    courses = []
    for name in sorted({o["course"] for o in observations if o["course"]}):
        cm = {a: aggregate(a, [o for o in observations if o["aspect"] == a and o["course"] == name], evidence) for a in ASPECTS}
        supported = {a: m for a, m in cm.items() if m["label"] != "정보 부족"}
        if supported:
            courses.append({"name": name, "metrics": supported})
    supported = [(a, m) for a, m in metrics.items() if m["label"] != "정보 부족"]
    summary = (" · ".join(f"{ASPECTS[a]} {m['label']}" for a, m in supported[:3])
               if supported else "검색 요약에서 독립적인 후기 근거가 충분하지 않아 특성을 판단할 수 없습니다.")
    result = {"schema_version": 1, "club_id": club["id"], "club_name": club["name"],
              "status": "analyzed" if supported else "insufficient_evidence",
              "analyzed_at": datetime.now(timezone.utc).isoformat(),
              "collected_at": collection["collected_at"], "source_type": "naver_search_snippets",
              "model": model, "analysis_version": "hub-session-experiment-v2", "experimental": True,
              "storage": "session_only",
              "raw_result_count": collection["raw_result_count"], "unique_result_count": unique_count,
              "candidate_count": len(candidates), "review_count": len(evidence),
              "independent_source_count": len({e["source_group"] for e in evidence.values()}),
              "queries": collection["queries"], "metrics": metrics, "courses": courses,
              "positive_keywords": [ASPECTS[a] for a, m in supported if m["label"] == "긍정적"],
              "negative_keywords": [ASPECTS[a] for a, m in supported if m["label"] == "부정적"],
              "summary": summary, "confidence": "medium" if supported else "low",
              "evidence": evidence, "observations": observations,
              "excluded": audit, "validation_warnings": warnings, "limitations": [LIMITATION]}
    validate_analysis(result)
    return result


def validate_analysis(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Invalid analysis schema")
    required = ("club_id", "club_name", "status", "analyzed_at", "collected_at", "source_type",
                "model", "analysis_version", "raw_result_count", "unique_result_count", "candidate_count",
                "review_count", "independent_source_count", "queries", "metrics", "courses",
                "positive_keywords", "negative_keywords", "summary", "confidence", "evidence",
                "observations", "excluded", "validation_warnings", "limitations")
    if any(k not in data for k in required) or not isinstance(data["metrics"], dict) or set(data["metrics"]) != set(ASPECTS):
        raise ValueError("Missing analysis fields")
    if datetime.fromisoformat(data["analyzed_at"]).tzinfo is None:
        raise ValueError("Missing analysis timezone")
    if any(not isinstance(data[k], int) or data[k] < 0 for k in
           ("raw_result_count", "unique_result_count", "candidate_count", "review_count", "independent_source_count")):
        raise ValueError("Invalid counts")
    if not data["review_count"] <= data["candidate_count"] <= data["unique_result_count"] <= data["raw_result_count"]:
        raise ValueError("Inconsistent counts")
    if not isinstance(data["courses"], list) or not isinstance(data["evidence"], dict):
        raise ValueError("Invalid evidence structure")
    evidence = data["evidence"]
    if data["review_count"] != len(evidence):
        raise ValueError("Invalid review count")
    pairs = [*data["metrics"].items(), *((a, m) for c in data["courses"] for a, m in c["metrics"].items())]
    for aspect, metric in pairs:
        if aspect not in ASPECTS or metric["label"] not in [*LABELS[aspect].values(), "정보 부족", "평가가 엇갈림"]:
            raise ValueError("Invalid metric label")
        ids = metric["evidence_ids"]
        if not set(ids) <= set(evidence) or metric["evidence_count"] != len(set(ids)):
            raise ValueError("Invalid evidence references")
        count = len({evidence[i]["source_group"] for i in ids})
        if metric["label"] != "정보 부족" and count < 2:
            raise ValueError("Unsupported label")
        if metric["confidence"] not in ("low", "medium"):
            raise ValueError("Snippet confidence must be capped")


def next_query(state):
    if state["naver_calls"] >= 6:
        return None
    if not state["collection"]:
        return "레이크사이드CC 라운딩 후기"
    if not state["analysis_current"] or not state["analysis"]:
        return None
    used = {a["query"] for a in state["attempts"]}
    for aspect, name in ASPECTS.items():
        query = f"레이크사이드CC {name} 후기"
        if state["analysis"]["metrics"][aspect]["evidence_count"] < 2 and query not in used:
            return query
    return None


def search_pilot(club, secrets, state, *, collector=collect_reviews):
    from services.golf_api import hub_headers
    hub_headers(secrets)  # missing keys consume no HTTP budget
    if club["id"] != "lakeside" or state["club_id"] != "lakeside":
        raise GolfAPIError("레이크사이드CC만 검증할 수 있습니다.")
    query = next_query(state)
    if not query or state["busy"]:
        raise GolfAPIError("추가 검색 대상이 없거나 검색 중입니다. 세션당 최대 6회입니다.")
    state["busy"] = True
    state["naver_calls"] += 1  # count failed attempts too; never auto-retry
    attempt = {"query": query, "status": "started"}
    state["attempts"].append(attempt)
    try:
        incoming = collector(club, secrets, query=query, display=100, kind="blog")
        old = state["collection"]
        state["collection"] = {"collected_at": incoming["collected_at"],
                               "queries": (old["queries"] if old else []) + incoming["queries"],
                               "records": (old["records"] if old else []) + incoming["records"],
                               "raw_result_count": (old["raw_result_count"] if old else 0) + incoming["raw_result_count"]}
        state["analysis_current"] = False
        attempt["status"] = "success"
    except GolfAPIError:
        attempt["status"] = "failed"
        raise
    finally:
        state["busy"] = False


def analyze_pilot(club, secrets, state, *, extractor=extract_observations):
    """Only explicitly invoked. Keep all intermediate results in the supplied session dict."""
    import json
    if club["id"] != "lakeside" or not state["collection"] or state["busy"]:
        raise GolfAPIError("레이크사이드CC 검색을 먼저 완료해주세요.")
    if not secret_status(secrets)["OPENAI_API_KEY"]:
        raise GolfAPIError("OPENAI_API_KEY 설정이 필요합니다.")
    if state["analysis_current"]:
        return state["analysis"]
    state["busy"] = True
    try:
        collection = state["collection"]
        candidates, excluded, unique = prepare_candidates(club, collection["records"])
        model = str(secrets.get("GOLF_OPENAI_MODEL") or "gpt-5.6-terra")
        cached = state["extractions"]
        signatures = {r["id"]: hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False).encode()).hexdigest() for r in candidates}
        pending = [r for r in candidates if signatures[r["id"]] not in cached]
        for start in range(0, len(pending), 25):
            if state["openai_calls"] >= 30:
                raise GolfAPIError("실험용 OpenAI 호출 상한(세션당 30회)에 도달했습니다.")
            batch = pending[start:start + 25]
            state["openai_calls"] += 1
            extraction, model = extractor(club, batch, secrets, EXTRACTION_SCHEMA)
            # Validate returned IDs/types before allowing reuse or aggregation.
            build_analysis(club, collection, batch, [], unique, extraction, model)
            for doc in extraction["documents"]:
                cached[signatures[doc["id"]]] = doc
        extraction = {"documents": [cached[signatures[r["id"]]] for r in candidates]}
        result = build_analysis(club, collection, candidates, excluded, unique, extraction, model if candidates else None)
        state["analysis"] = result
        state["analysis_current"] = True
        return result
    finally:
        state["busy"] = False
