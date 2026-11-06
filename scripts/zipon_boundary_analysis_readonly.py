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


def run_match(archive, projects, normalizer):
    """지정한 정규화 함수로 레코드와 사업 이름을 모두 정규화해 매칭한다(전역 교체 후 복구)."""
    original = src.normalize_name
    src.normalize_name = normalizer
    try:
        built = to_projects_with(projects, normalizer)
        survey, rows, _ = src.build(archive, projects=built, protected=set())
    finally:
        src.normalize_name = original
    for r in rows:
        r['group'] = group(r['match_status'])
    return survey, rows


def to_projects_with(raw_rows, normalizer):
    out = []
    for r in raw_rows:
        n, rules = normalizer(r['project_name'])
        out.append({'project_id': r['project_id'], 'project_name': r['project_name'], 'normalized_name': n,
                    'normalization_rules': rules, 'official_external_id': r.get('external_id'),
                    'project_type': r.get('project_type'), 'program': None, 'district': r.get('sigungu'),
                    'dong': r.get('dong'), 'address': r.get('address'), 'lot_number': None,
                    'latitude': r.get('lat'), 'longitude': r.get('lon')})
    return out


def pct(n, total):
    return round(100 * n / total, 1) if total else 0.0


def compare(archive, raw_rows, stage_rows=None):
    _, before = run_match(archive, raw_rows, src.normalize_name_v1)
    _, after = run_match(archive, raw_rows, src.normalize_name)
    total = len(after)

    def counts(rows):
        c = collections.Counter(r['group'] for r in rows)
        review = collections.Counter(r['match_status'] for r in rows if r['group'] == 'REVIEW')
        return {'total': len(rows), 'EXACT': c['EXACT'], 'auto_apply': sum(1 for r in rows if r['auto_apply_candidate']),
                'REVIEW': c['REVIEW'], 'REVIEW_AMBIGUOUS': review['AMBIGUOUS'], 'REVIEW_PROBABLE': review['PROBABLE'],
                'NO_MATCH': c['NO_MATCH'],
                'EXACT_excluded': dict(collections.Counter(r['excluded_reason'] for r in rows if r['match_status'] == 'EXACT' and r['excluded_reason'])),
                'review_dup_layer_rows': sum(1 for r in rows if r.get('review_reason_code'))}
    result = {'before_v1': counts(before), 'after_v2': counts(after)}
    for key in ('before_v1', 'after_v2'):
        d = result[key]
        d['pct'] = {k: pct(d[k], d['total']) for k in ('EXACT', 'auto_apply', 'REVIEW', 'NO_MATCH')}
    by_id = {r['zipon_project_id']: r for r in before}
    moves = collections.Counter(); samples = collections.defaultdict(list); new_exact_check = collections.Counter()
    for r in after:
        b = by_id[r['zipon_project_id']]
        if b['match_status'] != r['match_status'] or b['official_source_record_id'] != r['official_source_record_id']:
            key = '%s -> %s' % (b['match_status'], r['match_status'])
            moves[key] += 1
            if len(samples[key]) < 6:
                samples[key].append({'project': r['zipon_project_name'], 'district': r['district'], 'type': r['project_type'],
                                     'official_name': r['official_name'], 'inside': r['representative_point_inside_polygon']})
        if r['match_status'] == 'EXACT' and b['match_status'] != 'EXACT':
            new_exact_check['inside' if r['representative_point_inside_polygon'] else 'outside' if r['representative_point_inside_polygon'] is False else 'no_coord'] += 1
        if b['match_status'] == 'EXACT' and r['match_status'] != 'EXACT':
            new_exact_check['REGRESSION_exact_lost'] += 1
    result['transitions'] = dict(moves); result['transition_samples'] = dict(samples)
    result['newly_exact_position_check'] = dict(new_exact_check)
    result['by_type_after'] = tabulate(after, 'project_type')
    result['by_type_before'] = tabulate(before, 'project_type')
    result['by_district_after'] = tabulate(after, 'district')
    # 유형 불일치: ZIP:ON 유형 × 공식 계열(선택된 레코드가 있는 건)
    cross = collections.Counter((r['project_type'], r['official_family']) for r in after if r['official_family'])
    result['type_x_official_family'] = {'%s | %s' % k: v for k, v in sorted(cross.items(), key=lambda kv: -kv[1])}
    mism = [r for r in after if r['type_consistency'] == 'MISMATCH']
    result['type_mismatch_count'] = {'matched_with_record': sum(1 for r in after if r['official_family']), 'MISMATCH': len(mism),
                                     'by_status': dict(collections.Counter(r['match_status'] for r in mism))}
    result['type_mismatch_samples'] = [{'project': r['zipon_project_name'], 'district': r['district'], 'zipon_type': r['project_type'],
                                        'official_name': r['official_name'], 'official_family': r['official_family'], 'status': r['match_status']} for r in mism[:25]]
    # 중복 레이어(사람 검토 대상) 요약
    dups = [r for r in after if r.get('duplicate_layer_evidence')]
    result['duplicate_layer'] = {'ambiguous_with_evidence': len(dups),
                                 'looks_like_stacked_rows': sum(1 for r in dups if r['duplicate_layer_evidence']['looks_like_stacked_rows']),
                                 'same_name_but_iou_below_0.9': sum(1 for r in dups if r['duplicate_layer_evidence']['same_normalized_name'] and not r['duplicate_layer_evidence']['looks_like_stacked_rows']),
                                 'different_names': sum(1 for r in dups if not r['duplicate_layer_evidence']['same_normalized_name']),
                                 'auto_merged': 0}
    if stage_rows:
        st = {r['project_id']: r for r in stage_rows}
        table = collections.defaultdict(collections.Counter)
        for r in after:
            s_ = st.get(r['zipon_project_id'], {})
            table[s_.get('status') or '(없음)'][r['group']] += 1
        result['status_x_match_group'] = {k: dict(v) for k, v in table.items()}
        stage_tab = collections.defaultdict(collections.Counter)
        for r in after:
            stage_tab[(st.get(r['zipon_project_id'], {}).get('stage_raw') or '(없음)')][r['group']] += 1
        result['stage_x_match_group'] = {k: dict(v) for k, v in sorted(stage_tab.items(), key=lambda kv: -sum(kv[1].values()))[:25]}
    return result, after


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--archive', required=True)
    ap.add_argument('--projects', help='운영 SELECT 결과(JSON 또는 MCP 결과 원문)')
    ap.add_argument('--out-dir', required=True, help='저장소 밖 경로')
    ap.add_argument('--layer-only', action='store_true')
    ap.add_argument('--compare', action='store_true', help='정규화 v1(개선 전) ↔ v2(개선 후) 비교')
    ap.add_argument('--stage-file', help='SELECT project_id,status,stage,stage_raw 결과')
    args = ap.parse_args(argv)
    out = Path(args.out_dir).resolve()
    if ROOT in out.parents or out == ROOT:
        sys.exit('--out-dir 은 저장소 밖이어야 합니다(SHP 파생물을 저장소에 두지 않는다).')
    out.mkdir(parents=True, exist_ok=True)
    layer = layer_profile(args.archive)
    (out / 'layer_profile.json').write_text(json.dumps(layer, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.layer_only or not args.projects:
        print(json.dumps({k: layer[k] for k in ('records', 'fields')}, ensure_ascii=False)); return 0
    if args.compare:
        raw = load_export(args.projects)
        stage = load_export(args.stage_file) if args.stage_file else None
        result, after = compare(args.archive, raw, stage)
        (out / 'compare_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        (out / 'match_rows_v2.json').write_text(json.dumps(after, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({k: result[k] for k in ('before_v1', 'after_v2', 'transitions', 'newly_exact_position_check', 'duplicate_layer', 'type_mismatch_count')}, ensure_ascii=False, indent=1))
        return 0
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
