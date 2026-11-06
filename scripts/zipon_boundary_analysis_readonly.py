"""개발사업 ↔ 서울시 SHP 경계 매칭 분석(읽기 전용).

* 입력: 운영 DB에서 SELECT로 뽑은 개발사업 목록(JSON 또는 MCP 결과 원문)과 공식 SHP zip.
* 출력: --out-dir(기본 저장소 밖)에만 쓴다. DB·저장소 data/에 쓰지 않고, GeoJSON(경계 파생물)을 만들지 않는다.
  SHP는 공공누리 4유형(상업적 이용금지·변경금지)이므로 이 분석은 내부 검토용이며 서비스/배포/DB 저장에 쓰지 않는다.
* 매칭 규칙은 scripts/analyze_seoul_polygon_source.py 의 match()를 그대로 쓴다(새 규칙을 만들지 않는다).
  그 등급을 EXACT / REVIEW(PROBABLE+AMBIGUOUS) / NO_MATCH 로 묶어 보고한다.
"""
import argparse, collections, importlib.util, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location('seoul_src', ROOT / 'scripts/analyze_seoul_polygon_source.py')
src = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(src)

EXPORT_COLUMNS = ('project_id', 'project_name', 'sigungu', 'dong', 'project_type', 'external_id',
                  'official_authority', 'address', 'lon', 'lat')


def load_export(path):
    """JSON 배열 파일, 또는 Supabase MCP 결과 원문({"result": "...<untrusted-data>[...]</untrusted-data>"})을 읽는다."""
    text = Path(path).read_text(encoding='utf-8')
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get('result'), str):
            text = data['result']
    except ValueError:
        pass
    m = re.search(r'<untrusted-data-[^>]*>\s*(\[.*\])\s*</untrusted-data-', text, flags=re.S)
    body = m.group(1) if m else text[text.index('['):text.rindex(']') + 1]
    try:
        return json.loads(body)
    except ValueError:
        return json.loads(body.encode().decode('unicode_escape').encode('latin-1').decode('utf-8'))


def to_projects(rows):
    projects = []
    for r in rows:
        name = r['project_name']
        normalized, rules = src.normalize_name(name)
        projects.append({
            'project_id': r['project_id'], 'project_name': name, 'normalized_name': normalized,
            'normalization_rules': rules, 'official_external_id': r.get('external_id'),
            'project_type': r.get('project_type'), 'program': None,
            'district': r.get('sigungu'), 'dong': r.get('dong'), 'address': r.get('address'),
            'lot_number': None, 'latitude': r.get('lat'), 'longitude': r.get('lon')})
    return projects


def group(status):
    return 'EXACT' if status == 'EXACT' else 'NO_MATCH' if status == 'NO_MATCH' else 'REVIEW'


def tabulate(rows, key):
    table = collections.defaultdict(collections.Counter)
    for r in rows:
        table[r[key] or '(없음)'][r['group']] += 1
    out = []
    for k, c in sorted(table.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(c.values())
        out.append({key: k, 'total': total, 'EXACT': c['EXACT'], 'REVIEW': c['REVIEW'], 'NO_MATCH': c['NO_MATCH'],
                    'exact_pct': round(100 * c['EXACT'] / total, 1)})
    return out


def summarize(rows):
    for r in rows:
        r['group'] = group(r['match_status'])
    total = len(rows)
    by = collections.Counter(r['group'] for r in rows)
    auto = sum(1 for r in rows if r['auto_apply_candidate'])
    excluded = collections.Counter(r['excluded_reason'] for r in rows if r['match_status'] == 'EXACT' and r['excluded_reason'])
    detail = collections.Counter(r['match_status'] for r in rows)
    claims = collections.Counter(r['official_source_record_id'] for r in rows
                                 if r['group'] == 'EXACT' and r['official_source_record_id'])
    shared = {k: v for k, v in claims.items() if v > 1}
    return {'total_projects': total, 'by_group': dict(by), 'by_status': dict(detail),
            'auto_apply_candidates': auto, 'exact_excluded_reasons': dict(excluded),
            'boundary_matchable_pct': round(100 * by['EXACT'] / total, 1) if total else 0,
            'auto_candidate_pct': round(100 * auto / total, 1) if total else 0,
            'official_records_claimed_by_multiple_projects': shared,
            'by_type': tabulate(rows, 'project_type'), 'by_district': tabulate(rows, 'district')}


def risk_cases(rows, limit=25):
    pick = lambda pred: [r for r in rows if pred(r)][:limit]
    slim = lambda r: {k: r.get(k) for k in ('zipon_project_id', 'zipon_project_name', 'district', 'project_type',
                                            'official_name', 'match_status', 'confidence_reason',
                                            'representative_point_inside_polygon', 'distance_to_polygon_m')}
    return {
        'exact_but_point_outside_polygon': [slim(r) for r in pick(lambda r: r['excluded_reason'] == 'REPRESENTATIVE_POINT_OUTSIDE_POLYGON')],
        'ambiguous_multi_candidate': [slim(r) for r in pick(lambda r: r['match_status'] == 'AMBIGUOUS')],
        'probable_partial_name': [slim(r) for r in pick(lambda r: r['match_status'] == 'PROBABLE')],
    }


def layer_profile(archive):
    """레이어 구조: 필드·값 분포·코드정의표. 원본은 수정하지 않는다."""
    bundle = src.read_archive(archive)
    reader = bundle['reader']
    fields = [f[0] for f in reader.fields[1:]]
    rows = [dict(zip(fields, rec)) for rec in (sr.record for sr in reader.iterShapeRecords())]
    dist = lambda f, n=15: dict(collections.Counter(str(r.get(f)) for r in rows).most_common(n))
    names = [str(r.get('DGM_NM') or '') for r in rows]
    kw = {k: sum(1 for n in names if k in n) for k in
          ('재개발', '재건축', '모아', '신속', '가로주택', '소규모', '주택정비', '재정비촉진', '역세권', '미리내')}
    dates = sorted(str(r.get('CREATE_DAT')) for r in rows if r.get('CREATE_DAT'))
    return {'records': len(rows), 'fields': fields,
            'PROPEL_CD': dist('PROPEL_CD'), 'LCLAS_CL': dist('LCLAS_CL'), 'MLSFC_CL': dist('MLSFC_CL'),
            'SCLAS_CL': dist('SCLAS_CL'), 'ATRB_SE': dist('ATRB_SE'), 'GRP': dist('GRP'),
            'SIGNGU_SE_districts': len({r.get('SIGNGU_SE') for r in rows}),
            'name_keywords': kw, 'duplicate_names': sum(1 for _, c in collections.Counter(names).items() if c > 1),
            'create_date_range': [dates[0], dates[-1]] if dates else None,
            'code_table_rows': [[str(c)[:40] for c in row][:6] for row in bundle['code_table_rows'][:60]]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--archive', required=True)
    ap.add_argument('--projects', help='운영 SELECT 결과(JSON 또는 MCP 결과 원문)')
    ap.add_argument('--out-dir', required=True, help='저장소 밖 경로')
    ap.add_argument('--layer-only', action='store_true')
    args = ap.parse_args(argv)
    out = Path(args.out_dir).resolve()
    if ROOT in out.parents or out == ROOT:
        sys.exit('--out-dir 은 저장소 밖이어야 합니다(SHP 파생물을 저장소에 두지 않는다).')
    out.mkdir(parents=True, exist_ok=True)
    layer = layer_profile(args.archive)
    (out / 'layer_profile.json').write_text(json.dumps(layer, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.layer_only or not args.projects:
        print(json.dumps({k: layer[k] for k in ('records', 'fields')}, ensure_ascii=False)); return 0
    projects = to_projects(load_export(args.projects))
    survey, rows, _features = src.build(args.archive, projects=projects, protected=set())
    summary = summarize(rows)
    summary['source_crs'] = survey.get('source_crs_label')
    (out / 'match_rows.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    (out / 'match_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'risk_cases.json').write_text(json.dumps(risk_cases(rows), ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('total_projects', 'by_group', 'by_status', 'auto_apply_candidates',
                                              'boundary_matchable_pct', 'auto_candidate_pct')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
