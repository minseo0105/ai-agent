from __future__ import annotations

import json
import re
import hashlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "data" / "golf" / "catalog.json"
# 입력 후보 파일은 프로젝트 루트에 복사할 필요 없이
# play_facility_diagnostic 아래의 최신 파일을 자동 탐색한다.
INPUT = None

def find_latest_candidate_file():
    base = ROOT / "data" / "golf" / "enrichment" / "play_facility_diagnostic"
    candidates = list(base.rglob("existing_evidence_candidates.json")) if base.exists() else []
    # 혹시 사용자가 루트에 둔 경우도 지원
    root_candidate = ROOT / "existing_evidence_candidates.json"
    if root_candidate.exists():
        candidates.append(root_candidate)
    if not candidates:
        raise FileNotFoundError(
            "existing_evidence_candidates.json을 찾지 못했습니다. "
            "먼저 golf_play_facility_diagnostic_v1.py를 실행했는지 확인해 주세요."
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)
OUTDIR = ROOT / "data" / "golf" / "master"
OUTDIR.mkdir(parents=True, exist_ok=True)

FIELDS = {
    "two_person": "2인 플레이",
    "three_person": "3인 플레이",
    "nine_twice": "9홀×2 라운드",
    "par3": "PAR3 연습장",
    "outdoor_practice": "야외 연습장",
    "night_round": "야간 라운드",
}

# 다른 골프장 이름이 강하게 섞인 대표 오염 패턴.
# 일반적인 검색 결과도 아래 identity 검사로 추가 차단한다.
KNOWN_CONTAMINATION = {
    "vworld_순창": ["자유CC", "자유그린길", "성원자유"],
    "vworld_탑블리스": ["자유CC", "자유그린길", "성원자유"],
    "vworld_오스타": ["자유CC", "자유그린길", "성원자유"],
}

OFFICIALISH = (
    ".co.kr", ".com", ".kr", "golf", "cc", "resort"
)
WEAK_DOMAINS = (
    "blog.naver.com", "tistory.com", "youtube.com", "instagram.com",
    "dbegl.com", "sbs.co.kr", "kakao", "baigolf", "acegolf",
    "1night2day.com", "tripmate", "peachegg"
)

EVENT_WORDS = (
    "이벤트", "기간", "까지", "~", "마감", "공지", "시즌",
    "주중", "주말", "조조", "시간대", "회원", "동반", "패키지",
    "별도문의", "상이", "가능여부"
)

NEGATIVE_WORDS = (
    "불가", "불가능", "운영하지 않", "없음", "미운영", "종료"
)

POSITIVE_BY_FIELD = {
    "two_person": ("2인 가능", "2인가능", "2인 플레이 가능", "2인플레이가능", "2인 예약"),
    "three_person": ("3인 가능", "3인가능", "3인 플레이 가능", "3인플레이가능", "3인이상"),
    "nine_twice": ("9홀×2", "9홀 x 2", "9홀x2", "9홀 2회", "9홀 두번", "18홀로 이용"),
    "par3": ("par3", "par 3", "파3", "파 3"),
    "outdoor_practice": ("야외 연습장", "야외연습장", "드라이빙레인지", "드라이빙 레인지"),
    "night_round": ("야간 라운드", "야간라운드", "야간", "3부"),
}

def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def norm(s) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(s or "").lower())

def snippets_text(item) -> str:
    return "\n".join(str(x) for x in (item.get("snippets") or []) if x)

def candidate_positive(text: str, field: str) -> bool:
    t = text.lower()
    return any(x.lower() in t for x in POSITIVE_BY_FIELD.get(field, ()))

def candidate_negative(text: str, field: str) -> bool:
    t = text.lower()
    # 필드 관련 문맥이 있으면서 부정어가 있을 때만 부정 증거로 본다.
    field_terms = POSITIVE_BY_FIELD.get(field, ())
    related = any(x.lower().replace(" 가능","").replace("가능","") in t for x in field_terms)
    return related and any(x in t for x in NEGATIVE_WORDS)

def looks_conditional(text: str) -> bool:
    t = text.lower()
    if any(w.lower() in t for w in EVENT_WORDS):
        return True
    if re.search(r"\d{1,2}/\d{1,2}\s*[~\-]\s*\d{1,2}/\d{1,2}", t):
        return True
    if re.search(r"~\s*\d{1,2}/\d{1,2}", t):
        return True
    return False

def has_identity_contamination(item, text: str) -> tuple[bool, str]:
    cid = str(item.get("id") or "")
    for bad in KNOWN_CONTAMINATION.get(cid, []):
        if bad.lower() in text.lower():
            return True, f"known_cross_course:{bad}"

    name = str(item.get("name") or "")
    nn = norm(name)
    # 이름이 너무 짧으면 자동 identity 판정을 하지 않는다.
    if len(nn) >= 4:
        # 검색 스니펫 전체에 대상 이름/핵심 이름이 전혀 없으면 약한 identity로 본다.
        variants = {nn}
        for suffix in ("골프클럽","컨트리클럽","cc","gc","g.c"):
            variants.add(norm(name.lower().replace(suffix, "")))
        variants = {v for v in variants if len(v) >= 3}
        if variants and not any(v in norm(text) for v in variants):
            return True, "target_name_not_found_in_snippets"
    return False, ""

def source_strength(text: str) -> str:
    t = text.lower()
    if any(d in t for d in WEAK_DOMAINS):
        return "WEAK"
    # 공식 예약/홈페이지 문구가 직접 잡힌 경우만 강한 증거 후보
    if "공식 홈페이지" in text or "공식홈페이지" in text or "reservation" in t or "reserv" in t:
        return "STRONG_CANDIDATE"
    return "MEDIUM"

def classify(item):
    text = snippets_text(item)
    field = str(item.get("field") or "")
    raw_status = str(item.get("candidate_status") or "")
    contaminated, contam_reason = has_identity_contamination(item, text)
    strength = source_strength(text)
    conditional = looks_conditional(text)

    if contaminated:
        return "CONTAMINATED_HOLD", {
            "reason": contam_reason,
            "source_strength": strength,
            "conditional": conditional,
        }

    if raw_status == "negative_candidate" or candidate_negative(text, field):
        # 부정 정보도 대상 동일성이 확보됐을 때 중요한 근거이므로 별도 보존
        return "NEGATIVE_EVIDENCE", {
            "reason": "negative_candidate_or_negative_phrase",
            "source_strength": strength,
            "conditional": conditional,
        }

    if not candidate_positive(text, field):
        return "REFERENCE_ONLY", {
            "reason": "positive_phrase_not_clear",
            "source_strength": strength,
            "conditional": conditional,
        }

    if conditional:
        return "CONDITIONAL", {
            "reason": "time/member/day/time/event_condition_detected",
            "source_strength": strength,
            "conditional": True,
        }

    if strength == "STRONG_CANDIDATE":
        # '확정'이라고 부르지 않고 VERIFIED_CANDIDATE로 둔다.
        # 공식 도메인/원문 identity 최종 확인 전 canonical 자동반영 금지.
        return "VERIFIED_CANDIDATE", {
            "reason": "direct_positive_phrase_with_stronger_source_signal",
            "source_strength": strength,
            "conditional": False,
        }

    return "REFERENCE_ONLY", {
        "reason": "third_party_or_insufficient_source_strength",
        "source_strength": strength,
        "conditional": False,
    }

def fact_status(club, field):
    vb = (club.get("verified_basic_info") or {}).get(field) or {}
    if vb.get("verified") is True or str(vb.get("confidence") or "").upper() == "A":
        return "VERIFIED"
    val = club.get(field)
    if val not in (None, "", [], {}):
        return "CURRENT_UNVERIFIED"
    return "MISSING"

def main():
    if not CATALOG.exists():
        raise FileNotFoundError(f"catalog 없음: {CATALOG}")
    input_path = find_latest_candidate_file()
    print(f"자동 선택 입력 파일: {input_path}")

    before_hash = sha256(CATALOG)
    catalog = load_json(CATALOG)
    items = load_json(input_path)

    if isinstance(catalog, dict):
        clubs = catalog.get("clubs") or catalog.get("records") or catalog.get("data") or []
    else:
        clubs = catalog
    if not isinstance(clubs, list):
        raise ValueError("catalog 구조를 읽을 수 없습니다.")

    if isinstance(items, dict):
        items = items.get("items") or items.get("records") or items.get("candidates") or []
    if not isinstance(items, list):
        raise ValueError("existing_evidence_candidates.json 구조를 읽을 수 없습니다.")

    by_id = {str(c.get("id")): c for c in clubs if c.get("id")}
    classified = []
    stats = Counter()
    field_stats = defaultdict(Counter)

    for item in items:
        cls, detail = classify(item)
        row = dict(item)
        row["review_class"] = cls
        row["review_detail"] = detail
        row["auto_apply"] = False
        classified.append(row)
        stats[cls] += 1
        field_stats[str(item.get("field") or "unknown")][cls] += 1

    # Master DB: catalog canonical 값과 evidence를 분리.
    evidence_by_id = defaultdict(lambda: defaultdict(list))
    for row in classified:
        cid = str(row.get("id") or "")
        field = str(row.get("field") or "")
        evidence_by_id[cid][field].append({
            "label": row.get("label"),
            "candidate_status": row.get("candidate_status"),
            "review_class": row.get("review_class"),
            "snippets": row.get("snippets") or [],
            "source": row.get("source"),
            "review_detail": row.get("review_detail"),
            "canonical_auto_apply": False,
        })

    records = []
    fact_fields = [
        "operation_type", "holes", "courses", "official_url",
        "booking_url", "phone", "address", "description"
    ]
    for club in clubs:
        cid = str(club.get("id") or "")
        facts = {}
        for f in fact_fields:
            value = club.get(f)
            if f == "address" and not value:
                value = club.get("road_address") or club.get("lot_address")
            facts[f] = {
                "value": value,
                "status": fact_status(club, f),
                "verification": (club.get("verified_basic_info") or {}).get(f),
            }

        objective = {}
        for f, label in FIELDS.items():
            evs = evidence_by_id.get(cid, {}).get(f, [])
            classes = [e.get("review_class") for e in evs]
            if "CONTAMINATED_HOLD" in classes:
                state = "HOLD"
            elif "NEGATIVE_EVIDENCE" in classes:
                state = "NEGATIVE_EVIDENCE"
            elif "VERIFIED_CANDIDATE" in classes:
                state = "VERIFIED_CANDIDATE"
            elif "CONDITIONAL" in classes:
                state = "CONDITIONAL"
            elif evs:
                state = "REFERENCE_ONLY"
            else:
                state = "UNKNOWN"
            objective[f] = {
                "label": label,
                "state": state,
                "evidence": evs,
            }

        records.append({
            "id": cid,
            "name": club.get("name"),
            "area": club.get("area"),
            "city": club.get("city"),
            "facts": facts,
            "objective_features": objective,
            "kga_summary": {
                "matched": (club.get("kga") or {}).get("matched"),
                "matched_name": (club.get("kga") or {}).get("matched_name"),
                "checked_at": (club.get("kga") or {}).get("checked_at"),
            },
            "public_data_summary": {
                "matched": ((club.get("verification") or {}).get("public_data") or {}).get("matched"),
                "operating": ((club.get("verification") or {}).get("public_data") or {}).get("operating_in_public_data"),
                "business_type": ((club.get("verification") or {}).get("public_data") or {}).get("business_type"),
            },
        })

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    master = {
        "schema_version": "1.0",
        "built_at": now,
        "catalog_count": len(clubs),
        "candidate_count": len(items),
        "candidate_source": str(input_path),
        "policy": {
            "canonical_catalog_modified": False,
            "verified_candidate_is_not_auto_applied": True,
            "conditional_information_is_not_treated_as_always_available": True,
            "contaminated_evidence_is_never_used_for_filter_confirmation": True,
        },
        "classification_counts": dict(stats),
        "records": records,
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    classified_path = OUTDIR / f"objective_evidence_classified_{stamp}.json"
    master_path = OUTDIR / f"golf_master_{stamp}.json"
    latest_path = OUTDIR / "golf_master.json"
    report_path = OUTDIR / f"objective_evidence_report_{stamp}.json"

    classified_path.write_text(json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8")
    master_path.write_text(json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8")

    # stable master path. catalog이 아니므로 실패해도 원본 서비스 DB에는 영향 없음.
    latest_path.write_text(json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "built_at": now,
        "catalog_count": len(clubs),
        "input_candidates": len(items),
        "candidate_source": str(input_path),
        "classification_counts": dict(stats),
        "field_counts": {k: dict(v) for k, v in field_stats.items()},
        "catalog_sha256_before": before_hash,
        "catalog_sha256_after": sha256(CATALOG),
        "catalog_unchanged": before_hash == sha256(CATALOG),
        "outputs": {
            "master": str(latest_path),
            "master_timestamped": str(master_path),
            "classified": str(classified_path),
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if sha256(CATALOG) != before_hash:
        raise RuntimeError("중단: catalog.json 해시가 변경되었습니다.")

    print("=" * 64)
    print("Golf Objective Evidence Classifier + Master DB")
    print("=" * 64)
    print(f"catalog: {len(clubs)}")
    print(f"입력 evidence: {len(items)}")
    for key in ("VERIFIED_CANDIDATE","CONDITIONAL","REFERENCE_ONLY","NEGATIVE_EVIDENCE","CONTAMINATED_HOLD"):
        print(f"{key:22s}: {stats.get(key, 0)}")
    print("-" * 64)
    for field, label in FIELDS.items():
        s = field_stats.get(field, {})
        print(f"{label:12s}: {sum(s.values())}건 / {dict(s)}")
    print("-" * 64)
    print(f"catalog.json 수정: {sha256(CATALOG) != before_hash}")
    print(f"Master DB: {latest_path}")
    print(f"분류 결과: {classified_path}")
    print(f"보고서: {report_path}")
    print("=" * 64)
    print("주의: VERIFIED_CANDIDATE도 catalog 자동반영하지 않았습니다.")
    print("다음 단계에서 강한 후보만 원문/공식 출처 확인 후 승격합니다.")

if __name__ == "__main__":
    main()
