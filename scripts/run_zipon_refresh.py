"""Entry point for the ZIP:ON incremental refresh jobs. Dry run by default.

Nothing is scheduled: a scheduler can call entry(job) later. Official hosts are
blocked in this environment, so the listing comes from the stored official
snapshot or from a local scenario fixture, never from a live fetch here.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import development_notify as notify
from services import development_pipeline as pipeline
from services.development_identity import program_identities
from services.development_official import digest, normalize_stage, now
from services.development_schedule import EVENT_DRIVEN, JOBS, job

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/development'
BASELINE = DATA / 'db_baseline_20260927.json'
NEW_PROJECT_URL = 'https://nnxtkvjpzqqhjlgnprzo.supabase.co'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def baseline_state():
    """Declared database baseline: the canary rows plus the first reviewed batch.

    This is what the operator reported as imported; it is not a database read.
    Use --apply with credentials to verify against the server instead.
    """
    rows = load(BASELINE)['projects']
    return pipeline.known_state(rows)


def scenario_inputs(scenario, records, known):
    """Which official rows this run sees, and the baseline it compares against.

    Only the 'simulated-change' scenario alters anything, and every mutation is a
    local fixture: it is never presented as official data.
    """
    baseline_rows = [r for r in records if r['project_id'] in known]
    if scenario == 'official':
        return {'rows': records, 'known': known, 'kind': 'OFFICIAL_SNAPSHOT',
                'note': 'data/development/pilot_20260927.json', 'fixture': {}}
    if scenario == 'unchanged':
        return {'rows': baseline_rows, 'known': known,
                'kind': 'OFFICIAL_SNAPSHOT_LIMITED_TO_BASELINE',
                'note': 'the official pilot rows for the 18 known projects', 'fixture': {}}
    rows = copy.deepcopy(baseline_rows)
    state = copy.deepcopy(known)
    ranked = sorted((r for r in rows if r['external_id'] and rank_of(r['stage_raw']) is not None),
                    key=lambda r: (rank_of(r['stage_raw']), r['project_id']))
    forward, backwards, verified = ranked[0], ranked[-1], ranked[1]
    forward['stage_raw'] = '관리처분인가'
    forward['planned_units'] = 480
    forward['source'] = dict(forward['source'], content_hash=digest({'fixture': 'forward'}))
    backwards['stage_raw'] = '추진위원회승인'
    backwards['source'] = dict(backwards['source'], content_hash=digest({'fixture': 'backwards'}))
    verified['stage_raw'] = '착공'
    verified['source'] = dict(verified['source'], content_hash=digest({'fixture': 'verified'}))
    state[verified['project_id']] = dict(state[verified['project_id']], validation_status='VERIFIED')
    mutated = {forward['project_id'], backwards['project_id'], verified['project_id']}
    dropped = next(r for r in reversed(rows) if r['project_id'] not in mutated)
    rows = [r for r in rows if r['project_id'] != dropped['project_id']]
    overlap = next((r for r in records if r['project_id'] not in known
                    and '(천호 A1-2)' in (r['project_name'] or '')), None)
    if overlap:
        rows.append(copy.deepcopy(overlap))
    return {'rows': rows, 'known': state, 'kind': 'SIMULATED_LOCAL_FIXTURE',
            'note': 'baseline rows mutated locally to exercise every branch',
            'fixture': {'forward_stage_change': forward['project_id'],
                        'backwards_stage_change': backwards['project_id'],
                        'verified_master_row': verified['project_id'],
                        'dropped_from_listing': dropped['project_id'],
                        'latent_overlap_candidate': overlap['project_id'] if overlap else None}}


def rank_of(stage_raw):
    return pipeline.STAGE_ORDER.get(normalize_stage(stage_raw)['normalized_stage'])


def planned_events(plan_result, records):
    """What the notification consumer would receive. Nothing is delivered."""
    by_id = {r['project_id']: r for r in records}
    rows = []
    for entry in plan_result['entries']:
        if entry['kind'] == 'UNCHANGED':
            continue
        record = by_id.get(entry['project_id'], {})
        rows.append({'project_id': entry['project_id'],
                     'to_revision': (entry.get('expected_revision') or 0) + 1,
                     'update_kind': entry['update_kind'],
                     'previous_stage': entry.get('previous_stage'), 'new_stage': entry.get('new_stage'),
                     'previous_status': entry.get('previous_status'), 'new_status': entry.get('new_status'),
                     'changed_fields': entry['changed_fields'],
                     'event_hash': digest({'project_id': entry['project_id'],
                                           'revision': (entry.get('expected_revision') or 0) + 1,
                                           'kind': entry['update_kind']}),
                     'new_snapshot': {'master': {'project_name': record.get('project_name')},
                                      'change': {'pipeline_kind': entry['kind'],
                                                 'review_required': entry['review_required'],
                                                 'review_reasons': entry.get('review_reasons', [])}}})
    consumer = notify.CollectingConsumer()
    drafts = notify.NotificationDraftConsumer()
    result = notify.consume(rows, consumer)
    notify.consume(rows, drafts)
    return {'rendered': result['delivered'], 'skipped_duplicates': result['skipped_duplicates'],
            'by_severity': {s: sum(1 for e in consumer.events if e['severity'] == s)
                            for s in sorted({e['severity'] for e in consumer.events})},
            'requires_human_review': sum(1 for e in consumer.events if e['requires_human_review']),
            'sample': consumer.events[:5], 'draft_rows_not_written': len(drafts.drafts),
            'db_write': False}


def entry(name, *, scenario='unchanged', records=None, known=None, canonical=None, apply=False,
          transport=None):
    """One refresh job. apply=False keeps everything local."""
    definition = job(name)
    records = records if records is not None else load(DATA / 'pilot_20260927.json')['records']
    known = known if known is not None else baseline_state()
    canonical = canonical if canonical is not None else load(
        DATA / 'pilot_canonical_verified_20260927.json')['projects']
    identities = program_identities(canonical)
    inputs = scenario_inputs(scenario, records, known)
    listing, listing_kind, listing_note = inputs['rows'], inputs['kind'], inputs['note']
    previous = load(BASELINE).get('listing_digests', {}) if scenario == 'unchanged' else {}
    result = pipeline.plan(listing, inputs['known'], previous_digests=previous,
                           identities=identities, detail_budget=definition['detail_budget'])
    if not definition['records_source_missing']:
        result['entries'] = [e for e in result['entries'] if e['kind'] != 'SOURCE_MISSING']
        result['counts'] = {k: sum(1 for e in result['entries'] if e['kind'] == k)
                            for k in sorted({e['kind'] for e in result['entries']})}
        result['writes_planned'] = sum(1 for e in result['entries']
                                       if not e['quarantine'] and e['kind'] != 'UNCHANGED')
    over_limit = result['writes_planned'] > definition['write_limit']
    report = {'job': definition, 'scenario': scenario, 'listing_kind': listing_kind,
              'listing_note': listing_note, 'official_data': listing_kind.startswith('OFFICIAL'),
              'fixture': inputs['fixture'],
              'event_driven': EVENT_DRIVEN, 'generated_at': now(),
              'plan': {k: v for k, v in result.items() if k != 'entries'},
              'entries': result['entries'],
              'quarantine': pipeline.quarantine_report(result, listing),
              'notifications': planned_events(result, listing)}
    if over_limit:
        report['run'] = {'status': 'WRITE_LIMIT_EXCEEDED', 'db_write': False,
                         'write_limit': definition['write_limit'],
                         'writes_planned': result['writes_planned'],
                         'action': 'select a reviewed batch of at most '
                                   f"{definition['write_limit']} candidates first"}
    else:
        report['run'] = pipeline.run(result, listing, transport=transport, dry_run=not apply,
                                     max_writes=definition['write_limit'])
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--job', default='weekly', choices=list(JOBS))
    ap.add_argument('--scenario', default='all',
                    choices=['all', 'official', 'unchanged', 'simulated-change'])
    ap.add_argument('--apply', action='store_true', help='requires ZIPON_IMPORT_* credentials')
    args = ap.parse_args()
    if args.apply:
        url = os.environ.get('ZIPON_IMPORT_SUPABASE_URL', '').strip().rstrip('/')
        if not url or not os.environ.get('ZIPON_IMPORT_SUPABASE_KEY', '').strip():
            raise SystemExit('ZIPON_IMPORT_SUPABASE_URL/KEY are not set; refusing to apply')
        if url != NEW_PROJECT_URL:
            raise SystemExit('NEW_PROJECT_URL_MISMATCH; refusing to apply')
        raise SystemExit('this sprint is implementation only: rerun without --apply')
    scenarios = ['official', 'unchanged', 'simulated-change'] if args.scenario == 'all' \
        else [args.scenario]
    reports = {name: entry(args.job, scenario=name) for name in scenarios}
    out = DATA / f'refresh_{args.job}_dryrun_20260927.json'
    out.write_text(json.dumps({'format': 'zipon-refresh-dryrun-v1', 'generated_at': now(),
                               'db_write': False, 'job': args.job, 'scenarios': reports},
                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for name, report in reports.items():
        print(name, json.dumps({'counts': report['plan']['counts'],
                                'detail_targets': len(report['plan']['detail_verification_targets']),
                                'writes': report['plan']['writes_planned'],
                                'quarantined': len(report['quarantine']['items']),
                                'review_required': len(report['plan']['review_required']),
                                'run': report['run'].get('status', 'DRY_RUN'),
                                'events': report['notifications']['rendered']}, ensure_ascii=False))
    print('written:', out.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
