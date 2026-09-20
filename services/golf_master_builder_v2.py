"""Review-only Golf Master Builder 2. Never imports the app or writes catalog.

The dossier is an editorial input, not untrusted search output. A source reviewer
must establish publisher identity and scope before recording assertions. This
module checks those assertions; it does not infer facts from arbitrary page text.
"""
from copy import deepcopy
from collections import Counter
from datetime import date
import hashlib
import json
import re
from urllib.parse import urlparse


TEST_IDS = ("88cc", "lavie", "lakeside", "rainbow", "blackstone", "blueheron",
            "southsprings", "silkriver", "club72", "clubd_theplayers")
FIELDS = ("name", "address", "phone", "operation_type", "holes", "courses",
          "official_url", "booking_url", "external_booking_url", "description")
PRIORITY = {"official": 1, "government": 2, "association": 3, "secondary": 4}


def norm(value):
    return re.sub(r"\s+", "", str(value or "")).casefold()


def parse_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def fresh(value, as_of):
    day = parse_date(value)
    return day is not None and 0 <= (as_of - day).days <= 730


def public_url(value):
    parsed = urlparse(str(value or ""))
    return (parsed.scheme == "https" and bool(parsed.hostname)
            and not parsed.username and not parsed.password)


def identity_valid(source, club_id):
    """Positive, reviewed publisher/branch evidence, never name-match scoring."""
    identity = source.get("identity") or {}
    return bool(
        source.get("club_id") == club_id
        and public_url(source.get("url"))
        and source.get("reviewed_by") and parse_date(source.get("checked_at"))
        and identity.get("method") in {"operator_legal_review", "authority_link_review"}
        and identity.get("publisher") and identity.get("branch")
        and identity.get("basis") and identity.get("evidence_url")
        and (identity.get("address_or_phone_match") is True
             or (identity.get("method") == "authority_link_review"
                 and identity.get("operator_relationship_explicit") is True))
    )


def claim_reason(claim, source, club_id, as_of):
    if not source or source.get("club_id") != club_id:
        return "출처 또는 대상 불일치"
    if not source.get("reviewed_by") or not source.get("checked_at"):
        return "출처 검토 기록 없음"
    checked = parse_date(source.get("checked_at"))
    published = parse_date(source.get("source_date"))
    if checked is None or checked > as_of or (published and published > as_of):
        return "잘못된 날짜 또는 미래 날짜"
    kind = source.get("kind")
    if kind not in PRIORITY or not public_url(source.get("url")):
        return "사실정보 출처 자격 미충족"
    if kind == "official" and not identity_valid(source, club_id):
        return "공식 운영주체·지점 identity 근거 부족"
    if not claim.get("quote") or not claim.get("locator") or not claim.get("review_note"):
        return "문맥을 검토한 필드별 근거 부족"
    if claim.get("scope") != "club" or claim.get("temporal") == "historical":
        return "전체 골프장 범위 아님 또는 과거 참고"
    field, value = claim.get("field"), claim.get("value")
    if field not in FIELDS or value in (None, "", [], {}):
        return "지원하지 않는 필드 또는 빈 값"
    if field == "holes":
        if type(value) is not int or not 1 <= value <= 108:
            return "홀수 형식 오류"
        if claim.get("assertion") != "explicit_club_total":
            return "라운드/대회/개별 코스 홀수는 전체 홀수로 사용 불가"
        if not re.search(rf"(?<!\d){value}\s*(?:홀|holes?|h\b)", claim["quote"], re.I):
            return "인용 근거에서 전체 홀수 수치 확인 불가"
    if field == "courses":
        if not isinstance(value, list) or claim.get("assertion") != "physical_courses":
            return "KGA 조합과 물리 코스는 별도 정보"
        names = [norm(c.get("name")) for c in value if isinstance(c, dict)]
        if len(names) != len(value) or not all(names) or len(set(names)) != len(names):
            return "코스명 누락 또는 중복"
        for course in value:
            holes = course.get("holes")
            if holes is not None and (type(holes) is not int or not 1 <= holes <= 36
                                       or not course.get("holes_evidence")):
                return "코스별 홀수 근거 부족"
    if field == "operation_type":
        if value not in {"회원제", "대중제", "혼합"}:
            return "운영형태 형식 오류"
        if claim.get("temporal") != "current" or not fresh(source.get("source_date"), as_of):
            return "현재 운영형태의 최근 작성일·효력일 확인 필요"
        if claim.get("assertion") != "explicit_current_operation":
            return "과거/현재 단어 동시 출현은 운영형태 근거 아님"
        if value == "혼합" and not claim.get("simultaneous_operation_evidence"):
            return "동시 운영을 확인하는 명시적 근거 부족"
    if field in {"official_url", "booking_url"}:
        if not identity_valid(source, club_id) or not public_url(value):
            return "공식 URL identity 미확인"
        # Exact URLs preserve branch paths. Never promote a search candidate/domain root.
        if value not in source.get("authorized_urls", []):
            return "운영주체가 관리/지정하는 정확한 URL 확인 필요"
        if field == "booking_url" and claim.get("assertion") != "official_booking_link":
            return "공식 예약 링크 근거 없음"
    return None


def field_result(claims, sources, field, club_id, as_of):
    eligible, reference = [], []
    for claim in claims:
        if claim.get("field") != field:
            continue
        source = sources.get(claim.get("source_id"))
        reason = claim_reason(claim, source, club_id, as_of)
        if reason:
            reference.append({"claim": deepcopy(claim), "reason": reason})
        else:
            eligible.append(claim)
    result = {"value": None, "confidence": "needs_review", "source": [],
              "source_date": None, "checked_at": None, "reference": reference,
              "reason": "필드별 근거 없음"}
    if not eligible:
        if reference:
            result["reason"] = reference[0]["reason"]
        return result
    rank = min(PRIORITY[sources[c["source_id"]]["kind"]] for c in eligible)
    preferred = [c for c in eligible if PRIORITY[sources[c["source_id"]]["kind"]] == rank]
    # Current-operation assertions have dates. The latest explicit statement wins;
    # older assertions stay visible and are never combined into "mixed".
    if field == "operation_type":
        newest = max(sources[c["source_id"]]["source_date"] for c in preferred)
        preferred = [c for c in preferred if sources[c["source_id"]]["source_date"] == newest]
    values = {json.dumps(c["value"], ensure_ascii=False, sort_keys=True) for c in preferred}
    if len(values) != 1:
        result.update(reason="동일 우선순위 출처 간 충돌", conflicts=deepcopy(preferred))
        return result
    if rank == 4:
        # Different domains alone are NOT independent sources (syndication/copies).
        groups = {sources[c["source_id"]].get("independence_group") for c in preferred}
        groups.discard(None)
        if len(groups) < 2:
            result.update(reason="독립적인 보조출처 2개 미확인", conflicts=deepcopy(preferred))
            return result
    used = [sources[c["source_id"]] for c in preferred]
    result.update(value=deepcopy(preferred[0]["value"]), confidence="source_supported",
                  source=[c["source_id"] for c in preferred],
                  source_date=max((s["source_date"] for s in used if s.get("source_date")), default=None),
                  checked_at=max(s["checked_at"] for s in used),
                  reason="출처 검토 근거 있음; 사용자 최종 검토 전",
                  evidence=deepcopy(preferred),
                  alternatives=[deepcopy(c) for c in eligible if c not in preferred])
    return result


def kga_audit(club, as_of):
    kga = club.get("kga") or {}
    combos = deepcopy(kga.get("course_combinations") or [])
    valid, quarantine = [], []
    frequencies = Counter((norm(r.get("course")), norm(r.get("tee")), norm(r.get("gender")))
                          for r in kga.get("ratings") or [])
    for row in kga.get("ratings") or []:
        reason = None
        key = (norm(row.get("course")), norm(row.get("tee")), norm(row.get("gender")))
        cr, slope = row.get("course_rating"), row.get("slope_rating")
        if not kga.get("matched") or kga.get("match_type") != "exact":
            reason = "골프장 exact 매칭 재확인 필요"
        elif not key[0] or key[0] not in {norm(c) for c in combos}:
            reason = "코스조합 누락 또는 조합 불일치"
        elif not key[1] or key[2] not in {"남자", "여자", "남", "여", "male", "female"}:
            reason = "티/성별 누락 또는 형식 오류"
        elif type(cr) not in (int, float) or not 55 <= cr <= 85 or type(slope) is not int or not 55 <= slope <= 155:
            reason = "18홀 레이팅 값 범위 오류; 9홀은 별도 검토"
        elif frequencies[key] > 1:
            reason = "동일 조합/티/성별 중복: 첫 행도 임의 채택하지 않음"
        if reason:
            quarantine.append({"row": deepcopy(row), "reason": reason})
        else:
            valid.append(deepcopy(row))
    return {"course_combinations": combos, "ratings_structurally_valid": valid,
            "ratings_quarantined": quarantine, "source": kga.get("source_url"),
            "ratings_source": kga.get("ratings_source_url"),
            "source_date": kga.get("ratings_source_date"),
            "checked_at": kga.get("ratings_checked_at") or kga.get("checked_at"),
            "confidence": "legacy_requires_source_review",
            "older_than_730_days_or_undated": not fresh(kga.get("ratings_source_date"), as_of),
            "note": "기존 catalog의 구조 검사 결과. 원본 PDF 재대조/최신판 검증 전이며 물리 코스로 합산하지 않음."}


def build_club(club, dossier, as_of):
    source_ids = [s["id"] for s in dossier.get("sources", [])]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("출처 ID 중복")
    sources = {s["id"]: deepcopy(s) for s in dossier.get("sources", [])}
    claims = deepcopy(dossier.get("claims", []))
    public = (club.get("verification") or {}).get("public_data") or {}
    if (public.get("matched") is True and public.get("match_type") == "exact"
            and public.get("management_no") and public.get("dataset_id") == "15154978"):
        sid = club["id"] + "-public-existing"
        sources[sid] = {"id": sid, "club_id": club["id"], "kind": "government",
                        "url": "https://www.data.go.kr/data/15154978/openapi.do",
                        "source_date": (public.get("last_modified_at") or "")[:10] or None,
                        "checked_at": public.get("checked_at"),
                        "reviewed_by": "existing catalog exact public match; no fresh API call",
                        "management_no": public["management_no"],
                        "note": "기존 exact 매칭 공공 레코드. source_date는 레코드 수정일이며 재조회하지 않음."}
        for field in ("address", "phone"):
            if public.get(field):
                claims.append({"field": field, "value": public[field], "source_id": sid,
                               "quote": public[field], "scope": "club", "temporal": "undated",
                               "locator": "management_no=" + public["management_no"],
                               "review_note": "기존 공공 exact 매칭 레코드의 해당 필드"})
    facts = {field: field_result(claims, sources, field, club["id"], as_of) for field in FIELDS}
    courses = facts["courses"]
    if courses["value"]:
        evidence = courses.get("evidence", [])
        complete = all(c.get("complete_course_inventory") is True for c in evidence)
        rows = courses["value"]
        if complete and all(type(c.get("holes")) is int for c in rows):
            total = sum(c["holes"] for c in rows)
            if facts["holes"]["value"] is not None and facts["holes"]["value"] != total:
                facts["holes"].update(value=None, confidence="needs_review",
                                      reason="전체 홀수와 완전한 코스 합계 충돌")
            elif facts["holes"]["value"] is None and not facts["holes"].get("conflicts"):
                facts["holes"] = {**deepcopy(courses), "value": total,
                                  "reason": "전체 물리 코스 목록의 근거 있는 홀수 합산"}
    baseline = {k: deepcopy(club.get(k)) for k in FIELDS if k != "description"}
    baseline["description"] = club.get("course_overview")
    diffs = [{"field": k, "before": baseline.get(k), "proposed": v["value"]}
             for k, v in facts.items() if v["value"] is not None and v["value"] != baseline.get(k)]
    return {"id": club["id"], "name": club["name"], "baseline": baseline,
            "facts": facts, "sources": deepcopy(list(sources.values())),
            "kga": kga_audit(club, as_of),
            "public_data_reference": deepcopy((club.get("verification") or {}).get("public_data")),
            "review_information": {"included": False, "reason": "후기 기반 정보는 별도 기존 서비스에서 관리"},
            "proposed_changes": diffs, "review_notes": dossier.get("notes", []),
            "apply_allowed": False}


def build_report(catalog, dossier, as_of=None):
    as_of = as_of or date.today()
    selected = []
    for club_id in TEST_IDS:
        matches = [c for c in catalog if c.get("id") == club_id]
        if len(matches) != 1:
            raise ValueError(f"테스트 ID 누락 또는 중복: {club_id}")
        selected.append(build_club(matches[0], dossier.get(club_id, {}), as_of))
    return {"schema_version": "golf-master-builder-2/1", "as_of": as_of.isoformat(),
            "catalog_count": len(catalog), "test_count": len(selected),
            "mode": "review_only", "catalog_modified": False,
            "source_priority": list(PRIORITY), "clubs": selected,
            "limits": ["검토자가 기록한 필드별 assertion 입력을 검증하는 반자동 Builder",
                       "검색문서 자동 판별/LLM 자동 추출 없음", "catalog 반영 기능 없음",
                       "source_supported는 사용자 승인이나 완전한 정확도 인증이 아님"]}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def markdown_report(report):
    lines = ["# Golf Master DB Builder 2 — 10개 검토 보고서", "",
             f"기준일: {report['as_of']} · catalog {report['catalog_count']}개 · 테스트 10개",
             "", "catalog는 변경하지 않았습니다. 아래 값은 적용 전 검토 후보입니다.",
             "원문 작성일이 없는 값은 날짜 미상이며, checked_at은 출처 확인일입니다.", "",
             "| 골프장 | 전체 홀수 후보 | 운영형태 후보 | 변경 후보 수 | KGA 격리 행 |",
             "|---|---:|---|---:|---:|"]
    for c in report["clubs"]:
        lines.append(f"| {c['name']} | {c['facts']['holes']['value'] or '확인필요'} | "
                     f"{c['facts']['operation_type']['value'] or '확인필요'} | "
                     f"{len(c['proposed_changes'])} | {len(c['kga']['ratings_quarantined'])} |")
    for c in report["clubs"]:
        lines += ["", f"## {c['name']}", ""]
        for field, value in c["facts"].items():
            display = json.dumps(value["value"], ensure_ascii=False)
            lines.append(f"- **{field}**: {display} — {value['reason']} "
                         f"(출처일 {value['source_date'] or '미상'}, 확인일 {value['checked_at'] or '없음'})")
        lines += ["", "출처 및 identity 근거:", ""]
        for source in c["sources"]:
            lines.append(f"- [{source['id']}]({source['url']}): {source.get('identity', {}).get('basis', source.get('note', ''))}")
        lines += ["", "검토 사항:", ""] + [f"- {n}" for n in c["review_notes"]]
        for diff in c["proposed_changes"]:
            lines.append(f"- 변경 후보 `{diff['field']}`: {json.dumps(diff['before'], ensure_ascii=False)} → {json.dumps(diff['proposed'], ensure_ascii=False)}")
        for field, value in c["facts"].items():
            for ref in value["reference"]:
                lines.append(f"- 보류 `{field}`: {ref['reason']}")
        lines.append(f"- KGA 구조 유효 {len(c['kga']['ratings_structurally_valid'])}행 / 격리 {len(c['kga']['ratings_quarantined'])}행. PDF 원문 재검증 전.")
    lines += ["", "## 실제 HTTP 확인 (본문 사실 재검증과 별개)", ""]
    if report.get("http_checks_reused_from"):
        lines.append(f"기존 실행의 실제 HTTP 확인 기록 재사용: `{report['http_checks_reused_from']}`")
    for check in report.get("http_checks", []):
        lines.append(f"- {check['club_id']} [{check['url']}]({check['url']}): {check.get('status') or check.get('error')} "
                     f"{('redirect: ' + check['redirect']) if check.get('redirect') else ''}")
    lines += ["", "## 무결성", "", f"- catalog SHA-256: `{report.get('catalog_sha256', '')}`",
              f"- 백업: `{report.get('backup', '')}`", "- catalog 반영 코드, NAVER 호출, 외부 LLM 호출 없음."]
    if report.get("validation"):
        lines += ["", "## 테스트", "", report["validation"]]
    return "\n".join(lines) + "\n"
