from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
p=OUT/'services/golf_pricing.py';s=p.read_text(encoding='utf-8');s=s.replace('    status = " ".join(str(row.get(k) or "")','    if row.get("validation_status") == "needs_review":\n        return 1\n    status = " ".join(str(row.get(k) or "")');p.write_text(s,encoding='utf-8')
p=OUT/'services/golf_service.py';s=p.read_text(encoding='utf-8').replace('현재 기간 요금표가 없어 가장 최근 공식 요금으로 표시','현재 조건 적용이 확인되지 않은 참고 요금')
# Expose verified official facility facts separately from review opinions.
needle='def _completeness_block(club):'
helper='''def _official_facilities(club):
    labels = {"driving_range": "골프연습장", "par3_course": "PAR3 코스", "practice_green": "연습 그린"}
    facts = (club.get("enrichment") or {}).get("facts") or {}
    evidence = club.get("field_evidence") or {}
    result = []
    for key, label in labels.items():
        value = facts.get(key)
        proof = evidence.get("enrichment.facts." + key) or {}
        if value is None or not proof.get("source_url"):
            continue
        result.append({"label": label, "value": str(value), "source_url": proof["source_url"],
                       "checked_at": proof.get("observed_at") or proof.get("checked_at") or ""})
    return result


'''
assert needle in s;s=s.replace(needle,helper+needle)
needle='"completeness": _completeness_block(club),';assert needle in s;s=s.replace(needle,needle+'\n        "official_facilities": _official_facilities(club),')
p.write_text(s,encoding='utf-8')
p=OUT/'web/src/lib/golf.ts';s=p.read_text(encoding='utf-8').replace('  completeness: {','  official_facilities?: { label: string; value: string; source_url: string; checked_at: string }[];\n  completeness: {');p.write_text(s,encoding='utf-8')
p=OUT/'web/src/components/golf/GolfDetail.tsx';p.parent.mkdir(parents=True,exist_ok=True);s=(ROOT/'web/src/components/golf/GolfDetail.tsx').read_text(encoding='utf-8')
needle='      {(club.completeness || club.sources.items.length > 0 || club.sources.public_status) && ('
section='''      {!!club.official_facilities?.length && (
        <Section title="공식 안내 시설">
          <div className="space-y-3 text-sm">
            {club.official_facilities.map((facility) => (
              <div key={facility.label}>
                <div className="font-bold">{facility.label}</div>
                <p className="mt-1 text-muted">{facility.value}</p>
                <a href={facility.source_url} target="_blank" rel="noreferrer" className="text-xs text-golf underline">
                  공식 출처{facility.checked_at ? ` · ${facility.checked_at} 확인` : ""}
                </a>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">시설 존재에 관한 안내입니다. 현재 이용 가능 시간·요금은 공식 홈페이지에서 확인해 주세요.</p>
        </Section>
      )}

'''
assert needle in s;s=s.replace(needle,section+needle);p.write_text(s,encoding='utf-8')
# Preserve the collection date when rebuilding from saved originals.
p=OUT/'scripts/build_golf_review_evidence.py';s=(ROOT/'scripts/build_golf_review_evidence.py').read_text(encoding='utf-8')
s=s.replace("    args=ap.parse_args();", "    ap.add_argument('--source-date', default=date.today().isoformat(), type=lambda value: date.fromisoformat(value).isoformat())\n    args=ap.parse_args();")
s=s.replace("('refinement_'+today)","('refinement_'+args.source_date)")
s=s.replace("policy.extract(r,club,today)","policy.extract(r,club,raw.get('observed_at') or args.source_date)")
s=s.replace(" if o.get('status') in ('human_reviewed','rejected')","")
s=s.replace("'observed_at':today,'collection_status'","'observed_at':raw.get('observed_at') or prior.get('observed_at') or args.source_date,'collection_status'")
p.write_text(s,encoding='utf-8')
