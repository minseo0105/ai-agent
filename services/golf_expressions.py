"""STEP 5-B: deterministic snippet expressions, session memory only, no LLM or scraping."""
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit


class GolfAPIError(RuntimeError):
    """Golf review analysis/search error."""
    pass


def clean_text(value):
    """Normalize lightweight HTML/search text without depending on the retired golf_api module."""
    import html
    import re as _re
    value = html.unescape(str(value or ""))
    value = _re.sub(r"<[^>]+>", " ", value)
    return _re.sub(r"\\s+", " ", value).strip()


DIMENSIONS = {
    "difficulty": ("난이도", "hard", "easy"),
    "fairway": ("페어웨이", "wide", "narrow"),
    "green": ("그린", "fast", "slow"),
    "maintenance": ("코스관리", "positive", "negative"),
    "facilities": ("시설", "positive", "negative"),
}
WORDS = {
    "difficulty": {"hard": "어렵다", "easy": "쉽거나 무난하다"},
    "fairway": {"wide": "페어웨이가 넓거나 티샷 부담이 적다", "narrow": "페어웨이가 좁거나 티샷 부담이 크다"},
    "green": {"fast": "그린이 빠르다", "slow": "그린이 느리다"},
    "maintenance": {"positive": "코스관리가 좋다", "negative": "코스관리가 아쉽다"},
    "facilities": {"positive": "시설이 좋거나 깔끔하다", "negative": "시설이 낡거나 불편하다"},
}
RULE_VERSION = "tavily-5year-v1"
VOLATILE = set()
MIN_INDEPENDENT = 2
STRONG_MIN = 5
STRONG_SHARE = .80
STRONG_MARGIN = 3
MAX_CALLS = 6
FIRST_QUERY = "레이크사이드CC 라운딩 후기"
NOTICE = "Tavily 웹 검색 결과의 관련 본문을 바탕으로 최근 5년 후기 표현을 분류한 참고정보입니다. 출처 원문을 함께 확인하세요."

# Tight subject/predicate bridges, not arbitrary .{N} gaps across unrelated nouns.
P = r"(?:은|는|이|가|의|도|을|를)?\s*"
A = r"(?:(?:정말|매우|너무|조금|비교적|대체로|다소|아주|꽤|상당히|엄청|제법|전체적으로|참)\s*){0,2}"
B = P + A
NEGATION = re.compile(r"^\s*(?:지\s*(?:않|못)|지는\s*않|진\s*않|(?:다는|은|다는\s*건|다는\s*것은)\s*아니|다고\s*할\s*수\s*없|안\s*되|못|되어\s*있지\s*않|된\s*것은\s*아니)")
COURSE = re.compile(r"(동|남|서)\s*코스")
TARGET = re.compile(r"레이크\s*사이드", re.I)
GOLF_CONTEXT = re.compile(r"라운[딩드]|코스|골프장|티샷|페어웨이|그린(?!피)|퍼팅|클럽하우스|전장|홀\b")
PROMOTION = re.compile(r"회원권.{0,12}(?:매매|판매|분양|급매|매물|거래|시세|상담)|"
                       r"(?:매매|판매|분양|급매).{0,12}회원권|예약\s*(?:판매|대행|문의|상담|모집)|"
                       r"골프\s*패키지.{0,15}(?:판매|특가|모집|예약)|"
                       r"(?:구매|판매)\s*(?:링크|문의)|#광고|유료\s*광고|원고료|협찬|제공\s*받", re.I)
POSSIBLE_PROMOTION = re.compile(r"프로모션|이벤트|특가|할인\s*코드|추천\s*상품|회원권|패키지")
NON_GOLF = re.compile(r"예약(?:하기|이|은|가|을)?|찾기|찾아가|주차|길\s*찾|맛집|음식|식당")
MENTIONS = {
    "difficulty": re.compile(r"난이도|공략|플레이|코스.{0,12}(?:어렵|어려|쉽|쉬|무난|까다)|티샷.{0,8}부담"),
    "fairway": re.compile(r"페어웨이|페어웨|훼어웨이|티샷\s*(?:부담|하기)"),
    "green": re.compile(r"그린(?!피)|퍼팅"),
    "maintenance": re.compile(r"관리|잔디.{0,8}(?:상태|아쉽)|코스.{0,8}(?:상태|컨디션)"),
    "facilities": re.compile(r"시설|클럽하우스|라커|락커|샤워|탈의실"),
}


def paired(subject, predicate):
    return subject + B + predicate


RULES = {
    "difficulty": {
        "hard": [paired(r"(?:코스(?:\s*자체)?|플레이|공략|라운[딩드]|골프장|티샷)", r"(?:어렵|어려[운웠워]|까다롭|까다로|쉽지\s*않)"),
                 paired("난이도", "높"), r"(?:어려운|까다로운)\s*(?:코스|골프장|플레이|공략)", paired(r"플레이\s*부담", "(?:크|큰|많)")],
        "easy": [paired(r"(?:코스(?:\s*자체)?|플레이|공략|라운[딩드]|골프장)", r"(?:쉽|쉬[운웠워]|무난)"),
                 paired("난이도", "낮"), r"(?:쉬운|무난한)\s*(?:코스|골프장)",
                 paired(r"(?:플레이|공략|티샷)\s*부담", "(?:적|없)"), r"편하게\s*플레이"]},
    "fairway": {
        "wide": [paired(r"(?:페어웨이|훼어웨이)(?:\s*폭)?", "넓"), r"넓은\s*(?:페어웨이|훼어웨이)",
                 paired(r"티샷\s*부담", "(?:적|없)"), r"티샷하기\s*편"],
        "narrow": [paired(r"(?:페어웨이|훼어웨이)(?:\s*폭)?", "좁"), r"좁은\s*(?:페어웨이|훼어웨이)",
                   paired(r"티샷\s*부담", "(?:크|큰|많)"), paired("티샷", "(?:까다롭|까다로)")]},
    "green": {
        "fast": [paired(r"그린(?:\s*(?:스피드|속도))?", r"(?:빠르|빠른|빠름|빠[른르]|빨랐|빨라)"), r"빠른\s*그린"],
        "slow": [paired(r"그린(?:\s*(?:스피드|속도))?", r"(?:느리|느린|느렸|느려|느림)"), r"느린\s*그린"]},
    "maintenance": {
        "positive": [paired(r"(?:코스\s*|페어웨이\s*|그린\s*|잔디\s*)?관리(?:\s*상태)?", r"(?:잘|좋|훌륭)"),
                     paired(r"(?:잔디\s*상태|코스\s*(?:상태|컨디션))", "좋")],
        "negative": [paired(r"(?:코스\s*|페어웨이\s*|그린\s*|잔디\s*)?관리(?:\s*상태)?", r"(?:아쉽|아쉬|안\s*좋|부족|나쁘|불량)"),
                     paired(r"(?:잔디(?:\s*상태)?|코스\s*(?:상태|컨디션))", r"(?:안\s*좋|아쉽|아쉬|나쁘|불량)")]},
    "facilities": {
        "positive": [paired(r"(?:(?:샤워\s*)?시설|클럽하우스|라커|락커|샤워실)", r"(?:좋|깔끔|만족|깨끗|훌륭)")],
        "negative": [paired(r"(?:(?:샤워\s*)?시설|클럽하우스|라커|락커|샤워실)", r"(?:낡|아쉽|아쉬|오래|불편|노후|안\s*좋)")]},
}
COMPILED = {d: {v: [re.compile(p) for p in patterns] for v, patterns in dirs.items()} for d, dirs in RULES.items()}


def url_identity(link):
    """Normalize ONLY comparison identity; never alter displayed/original link."""
    try:
        p = urlsplit(link)
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
            return None, None
        host = p.hostname.lower()
        if host in ("blog.search.com", "m.blog.search.com"):
            q = parse_qs(p.query)
            parts = p.path.strip("/").split("/")
            author = q.get("blogId", [parts[0]])[0]
            post = q.get("logNo", [parts[1] if len(parts) == 2 else ""])[0]
            if post.isdigit():
                return f"search:{author}:{post}", f"search:{author}"
        return (host, p.path.rstrip("/"), p.query), host
    except (TypeError, ValueError):
        return None, None


def courses_in(text):
    return sorted({m.group(1) + "코스" for m in COURSE.finditer(text)})


def classify_document(title, description):
    text = title + " " + description
    if re.search(r"(맞춤형\s*해외\s*골프|골프\s*여행\s*전문|전체메뉴|카테고리\s*이동|커뮤니티|예약확인)", text, re.I):
        return "irrelevant", "후기 본문이 아닌 포털·메뉴·여행상품 페이지"
    if not TARGET.search(text) or not GOLF_CONTEXT.search(text):
        return "irrelevant", "대상 골프장/라운딩 관련성 부족"
    if re.search(r"로얄\s*레이크\s*사이드|미야자키|후쿠오카|태국|촌부리", title):
        return "irrelevant", "해외 동명 골프장 문맥"
    # Another club explicitly named in the title cannot be attributed to Lakeside.
    without_target = re.sub(r"레이크\s*사이드\s*(?:CC|컨트리\s*클럽)?", "", title, flags=re.I)
    if re.search(r"[가-힣A-Za-z]{2,}\s*(?:CC|컨트리클럽)", without_target, re.I):
        return "irrelevant", "제목에서 다른 골프장 확인"
    if re.search(r"맛집|카페|부동산|분양|아파트", title) and not re.search(r"라운[딩드]|코스\s*후기", title):
        return "irrelevant", "지역/주변시설 소개"
    if PROMOTION.search(text):
        return "promotional", "명백한 판매·예약 대행·홍보 표현"
    if re.search(r"웨지|퍼터|샤프트|드라이버|골프\s*용품|골프\s*장비", title):
        return "uncertain", "장비·상품 리뷰 혼재: 홍보 여부 불명확"
    if POSSIBLE_PROMOTION.search(text):
        return "uncertain", "홍보 또는 회원권 소개 가능성: 삭제하지 않고 보류"
    return "relevant", "대상 골프장/코스 검색결과"


def detect_expressions(title, description):
    """Return exact snippet spans. Negation and questions stay uncertain."""
    matches = []
    document_courses = courses_in(title + " " + description)
    for field, text in (("title", title), ("description", description)):
        # Delimit truncation and contrast; never join unrelated snippet fragments.
        clauses = re.split(r"[.!。\n…]+|(?:지만|반면|그러나)|[,;]|(?<=\?)", text)
        for clause in clauses:
            for dimension in DIMENSIONS:
                found = []
                for direction, patterns in COMPILED[dimension].items():
                    for pattern in patterns:
                        for match in pattern.finditer(clause):
                            before = clause[max(0, match.start() - 12):match.start()]
                            after = clause[match.end():match.end() + 20]
                            if dimension == "maintenance" and re.search(r"시설|클럽하우스|라커|락커|예약|주차", before):
                                continue
                            if dimension == "difficulty" and NON_GOLF.search(match.group()):
                                continue
                            hashtag = bool(re.search(r"#[^\s#]*$", clause[:match.start()]))
                            ambiguous = bool(hashtag or "?" in clause or NEGATION.search(after) or re.search(r"(?:다고\s*(?:들었|하던)|것\s*같|듯|일까)", after))
                            value = "uncertain" if ambiguous else direction
                            local_courses = courses_in(clause)
                            scope = local_courses if local_courses else document_courses
                            found.append({"dimension": dimension, "classification": value,
                                          "expression": match.group(), "context": clause.strip(), "field": field,
                                          "course_name": scope[0] if len(scope) == 1 else None,
                                          "scope_ambiguous": len(scope) > 1,
                                          "reason": "해시태그·부정·추측 문맥" if ambiguous else "주어와 방향 표현 인접"})
                if not found and MENTIONS[dimension].search(clause):
                    found.append({"dimension": dimension, "classification": "uncertain", "expression": clause.strip(),
                                  "context": clause.strip(), "field": field,
                                  "course_name": document_courses[0] if len(document_courses) == 1 else None,
                                  "scope_ambiguous": len(document_courses) > 1, "reason": "항목 언급만 있고 방향 표현 불명확"})
                matches.extend(found)
    # Identical matches from overlapping rules/title+description must not inflate counts.
    unique = {}
    for m in matches:
        unique[(m["dimension"], m["classification"], m["expression"], m["course_name"])] = m
    return list(unique.values())


def prepare_evidence(records):
    grouped, excluded, duplicate_count = {}, [], 0
    for record in records:
        link = record.get("url", record.get("link", ""))
        identity, author = url_identity(link)
        if identity is None:
            excluded.append({"classification": "irrelevant", "reason": "유효한 URL 없음", "link": link})
            continue
        title, description = clean_text(record.get("title")), clean_text(record.get("description"))
        if identity in grouped:
            duplicate_count += 1
            ev = grouped[identity]
            variant = {"title": title, "description": description, "query": record.get("query", "")}
            if variant not in ev["variants"]:
                ev["variants"].append(variant)
            if record.get("query") not in ev["queries"]:
                ev["queries"].append(record.get("query"))
            continue
        grouped[identity] = {"evidence_id": f"E{len(grouped) + 1:03d}", "title": title,
            "description": description, "link": link, "postdate": record.get("published_at", record.get("postdate")),
            "query": record.get("query", ""), "queries": [record.get("query", "")], "source_group": author,
            "variants": [{"title": title, "description": description, "query": record.get("query", "")}]}
    evidence = []
    for ev in grouped.values():
        decisions = [classify_document(v["title"], v["description"]) for v in ev["variants"]]
        classification, reason = next((x for x in decisions if x[0] == "promotional"),
            next((x for x in decisions if x[0] == "irrelevant"),
                 next((x for x in decisions if x[0] == "uncertain"), decisions[0])))
        ev.update(classification=classification, reason=reason)
        course_names = sorted({c for v in ev["variants"] for c in courses_in(v["title"] + " " + v["description"])})
        ev.update(course_name=course_names[0] if len(course_names) == 1 else None, course_names=course_names)
        observations = [o for v in ev["variants"] for o in detect_expressions(v["title"], v["description"])] if classification in ("relevant", "uncertain") else []
        ev["observations"] = observations
        ev["detected_dimension"] = sorted({o["dimension"] for o in observations})
        ev["detected_expression"] = list(dict.fromkeys(o["expression"] for o in observations))
        evidence.append(ev)
    return evidence, {"raw_item_count": len(records), "unique_url_count": len(grouped),
                      "duplicate_count": duplicate_count,
                      "irrelevant_count": len(excluded) + sum(e["classification"] == "irrelevant" for e in evidence),
                      "promotional_count": sum(e["classification"] == "promotional" for e in evidence),
                      "uncertain_document_count": sum(e["classification"] == "uncertain" for e in evidence)}, excluded


def _summarize(evidence, dimension, course=None):
    name, left, right = DIMENSIONS[dimension]
    ids = {left: [], right: [], "uncertain": []}
    for ev in evidence:
        if ev["classification"] not in ("relevant", "uncertain"):
            continue
        obs = [o for o in ev["observations"] if o["dimension"] == dimension and
               (course is None or (o["course_name"] == course and not o["scope_ambiguous"]))]
        if not obs:
            continue
        dirs = {o["classification"] for o in obs} - {"uncertain"}
        value = next(iter(dirs)) if len(dirs) == 1 and ev["classification"] == "relevant" else "uncertain"
        ids[value].append(ev["evidence_id"])
    by_id = {e["evidence_id"]: e for e in evidence}
    # One author/site, one directional contribution. Contradictory author posts abstain.
    sources = defaultdict(set)
    for direction in (left, right):
        for eid in ids[direction]:
            sources[by_id[eid]["source_group"]].add(direction)
    independent = {d: sum(values == {d} for values in sources.values()) for d in (left, right)}
    n = sum(independent.values())
    counts = {d: len(eids) for d, eids in ids.items()}
    winner = max((left, right), key=lambda d: independent[d])
    losing = right if winner == left else left
    wins, loses = independent[winner], independent[losing]
    if n < MIN_INDEPENDENT:
        label = "정보 부족"
    elif n >= STRONG_MIN and wins / n >= STRONG_SHARE and wins - loses >= STRONG_MARGIN:
        label = f"최근 검색결과에서는 ‘{WORDS[dimension][winner]}’라는 표현이 많이 확인됨"
    elif independent[left] >= 2 and independent[right] >= 2:
        label = "평가가 엇갈림"
    elif loses:
        label = "뚜렷한 경향 없음"
    else:
        label = f"‘{WORDS[dimension][winner]}’라는 표현이 {n}개 독립 출처에서 확인됨 (표본 적음)"
    return {"name": name, "label": label, "counts": counts, "evidence_ids": ids,
            "related_evidence_count": sum(counts.values()), "independent_counts": independent,
            "independent_valid_count": n, "scope": course or "검색 표본 전체 (코스별 표현 포함)",
            "decision_basis": {"minimum": MIN_INDEPENDENT, "strong_minimum": STRONG_MIN,
                "strong_share": STRONG_SHARE, "strong_margin": STRONG_MARGIN}}


def freshness_dates(as_of=None):
    today = as_of or datetime.now(timezone(timedelta(hours=9))).date()
    try:
        cutoff = today.replace(year=today.year - 5)
    except ValueError:  # February 29: calendar-month boundary, not 730-day approximation.
        cutoff = today.replace(year=today.year - 5, day=28)
    return today, cutoff


def mark_freshness(evidence, today, cutoff):
    for ev in evidence:
        value = str(ev.get("postdate") or "")
        try:
            published = datetime.strptime(value, "%Y%m%d").date() if re.fullmatch(r"\d{8}", value) else None
        except ValueError:
            published = None
        ev["published_date"] = published.isoformat() if published else None
        ev["freshness"] = ("unknown" if published is None or published > today
                           else "recent" if published >= cutoff else "historical")


def dimension_summary(evidence, dimension, course=None, *, apply_freshness=True):
    recent = [e for e in evidence if e.get("freshness") == "recent"]
    historical = [e for e in evidence if e.get("freshness") == "historical"]
    unknown = [e for e in evidence if e.get("freshness") == "unknown"]
    eligible = recent if apply_freshness and dimension in VOLATILE else evidence
    metric = _summarize(eligible, dimension, course)
    recent_metric = _summarize(recent, dimension, course)
    historical_metric = _summarize(historical, dimension, course)
    unknown_metric = _summarize(unknown, dimension, course)
    directional_ids = lambda m: {eid for value, ids in m["evidence_ids"].items() if value != "uncertain" for eid in ids}
    valid_ids = directional_ids(metric)
    latest = max((e["published_date"] for e in eligible if e["evidence_id"] in valid_ids
                  and e.get("freshness") != "unknown"), default=None)
    reason = ""
    if metric["independent_valid_count"] < MIN_INDEPENDENT:
        reason = ("시설에 대한 명시적 평가 표현을 확인하기 어렵습니다." if dimension == "facilities"
                  else f"현재 검색결과에서 {DIMENSIONS[dimension][0]}을 직접 설명하는 독립적인 표현이 충분하지 않습니다.")
        if dimension in VOLATILE:
            reason += " 최근 5년의 유효 근거만 현재 판단에 사용합니다."
        if recent_metric["independent_valid_count"] == 1:
            left, right = DIMENSIONS[dimension][1:]
            direction = max((left, right), key=lambda d: recent_metric["independent_counts"][d])
            reason = f"‘{WORDS[dimension][direction]}’라는 최근 표현이 일부 확인됩니다. 현재 판단하기에는 근거가 부족합니다."
    metric.update(recent_valid_evidence_count=len(directional_ids(recent_metric)),
                  recent_independent_count=recent_metric["independent_valid_count"], latest_evidence_date=latest,
                  historical_evidence_ids=historical_metric["evidence_ids"],
                  historical_counts=historical_metric["counts"],
                  undated_evidence_ids=unknown_metric["evidence_ids"],
                  recent_evidence_ids=recent_metric["evidence_ids"],
                  freshness_policy="recent_only" if dimension in VOLATILE else "all_dates",
                  insufficiency_reason=reason)
    return metric


def analyze_records(records, *, as_of=None, apply_freshness=True):
    evidence, stats, excluded = prepare_evidence(records)
    today, cutoff = freshness_dates(as_of)
    mark_freshness(evidence, today, cutoff)
    evidence.sort(key=lambda e: (e["freshness"] == "recent", e["freshness"] != "unknown", e["published_date"] or ""), reverse=True)
    dimensions = {d: dimension_summary(evidence, d, apply_freshness=apply_freshness) for d in DIMENSIONS}
    valid_ids = {eid for m in dimensions.values() for direction, eids in m["evidence_ids"].items()
                 if direction != "uncertain" for eid in eids}
    stats["valid_evidence_count"] = len(valid_ids)
    stats["related_document_count"] = sum(e["classification"] == "relevant" for e in evidence)
    stats["over_5_years_count"] = sum(e["freshness"] == "historical" for e in evidence)
    stats["unknown_date_count"] = sum(e["freshness"] == "unknown" for e in evidence)
    stats["historical_related_count"] = sum(e["freshness"] == "historical" and e["classification"] in ("relevant", "uncertain") and bool(e["observations"]) for e in evidence)
    courses = {}
    for course in sorted({c for e in evidence for c in e["course_names"]}):
        cm = {d: dimension_summary(evidence, d, course, apply_freshness=apply_freshness) for d in DIMENSIONS}
        courses[course] = {"label": "코스별 참고정보" if any(m["independent_valid_count"] >= 2 for m in cm.values()) else "코스별 정보 부족", "dimensions": cm}
    return {"rule_version": RULE_VERSION, "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "as_of": today.isoformat(), "recent_cutoff": cutoff.isoformat(),
            "stats": stats, "dimensions": dimensions, "courses": courses, "evidence": evidence,
            "excluded": excluded, "notice": NOTICE, "storage": "session_only", "external_llm_calls": 0}



def new_expression_session():
    return {
        "tavily_calls": 0, "attempts": [], "records": [], "result": None,
        "history": [], "busy": False, "error": None,
    }


def restart_expression_session(state):
    if state["busy"]:
        raise GolfAPIError("검색이 진행 중입니다.")
    state.clear()
    state.update(new_expression_session())


def get_expression_session(session_state):
    if "golf_tavily_session" not in session_state:
        session_state["golf_tavily_session"] = new_expression_session()
    state = session_state["golf_tavily_session"]
    today, _ = freshness_dates()
    if state["result"] and (
        state["result"].get("rule_version") != RULE_VERSION
        or state["result"].get("as_of") != today.isoformat()
    ):
        state["result"] = analyze_records(state["records"], as_of=today)
    return state


def run_tavily_search(club, api_key, state, *, searcher, query=None, max_results=20):
    """Exactly one explicit Tavily request. Results live only in Streamlit session."""
    if club["id"] != "lakeside":
        raise GolfAPIError("현재는 레이크사이드CC 검증만 지원합니다.")
    if state["busy"]:
        raise GolfAPIError("검색이 진행 중입니다.")
    query = query or f"{club['name']} 라운딩 후기 코스 페어웨이 그린 관리 시설"
    if any(a.get("query") == query and a.get("status") == "success" for a in state["attempts"]):
        return state["result"]

    state["busy"] = True
    attempt = {"query": query, "status": "started"}
    state["attempts"].append(attempt)
    try:
        incoming = searcher(api_key, query=query, max_results=max_results)
        state["tavily_calls"] += 1
        attempt.update(status="success", returned_items=len(incoming))
        state["records"].extend(incoming)
        state["result"] = analyze_records(state["records"])
        state["history"].append({"query": query, "returned_items": len(incoming)})
        return state["result"]
    except Exception as error:
        attempt["status"] = "failed"
        state["error"] = str(error)
        raise
    finally:
        state["busy"] = False
