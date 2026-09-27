"""Refresh job structure for ZIP:ON development data. Nothing is scheduled here.

The jobs are declared and callable through one entry point so a scheduler can be
wired up later without changing the pipeline. scheduler.py is deliberately not
touched in this sprint.
"""
from services.development_collector import MAX_IMPORT_BATCH

JOBS = {
    'daily': {
        'cadence': 'DAILY',
        'cron_hint': '0 7 * * *',
        'purpose': '공식 신규 고시·공고 탐지',
        'listing_scope': 'NEW_NOTICES_ONLY',
        'compare': 'LISTING_SNAPSHOT_HASH',
        'detail_budget': 10,
        'write_limit': MAX_IMPORT_BATCH,
        'steps': ['COLLECT', 'SNAPSHOT', 'CONTENT_HASH', 'CHANGE_DETECTION', 'VALIDATE',
                  'CANONICAL_UPDATE', 'DEVELOPMENT_UPDATES'],
        'records_source_missing': False,
    },
    'weekly': {
        'cadence': 'WEEKLY',
        'cron_hint': '0 8 * * 1',
        'purpose': '사업 목록 및 stage/status 변경 감지',
        'listing_scope': 'ALL_DISTRICT_LISTINGS',
        'compare': 'LISTING_SNAPSHOT_HASH',
        'detail_budget': 30,
        'write_limit': MAX_IMPORT_BATCH,
        'steps': ['COLLECT', 'SNAPSHOT', 'CONTENT_HASH', 'CHANGE_DETECTION', 'VALIDATE',
                  'CANONICAL_UPDATE', 'DEVELOPMENT_UPDATES'],
        'records_source_missing': True,
    },
    'monthly': {
        'cadence': 'MONTHLY',
        'cron_hint': '0 9 1 * *',
        'purpose': '전체 정합성·누락·중복 검사',
        'listing_scope': 'ALL_DISTRICT_LISTINGS',
        'compare': 'FULL_RECONCILIATION',
        'detail_budget': 0,
        'write_limit': 0,
        'steps': ['COLLECT', 'SNAPSHOT', 'CONTENT_HASH', 'CHANGE_DETECTION', 'REPORT_ONLY'],
        'records_source_missing': True,
    },
    'half_yearly': {
        'cadence': 'HALF_YEARLY',
        'cron_hint': '0 9 1 1,7 *',
        'purpose': '전체 source 재검증',
        'listing_scope': 'ALL_SOURCES_AND_DETAILS',
        'compare': 'REVERIFY_EVERY_SOURCE',
        'detail_budget': None,
        'write_limit': MAX_IMPORT_BATCH,
        'steps': ['COLLECT', 'SNAPSHOT', 'CONTENT_HASH', 'CHANGE_DETECTION', 'VALIDATE',
                  'CANONICAL_UPDATE', 'DEVELOPMENT_UPDATES'],
        'records_source_missing': True,
    },
}
# Geocoding and boundaries are event driven, never part of a periodic sweep.
EVENT_DRIVEN = {
    'geocode': 'FIRST_TIME_OR_ADDRESS_CHANGED',
    'polygon': 'NEW_PROJECT_OR_BOUNDARY_CHANGED',
}


def job(name):
    if name not in JOBS:
        raise KeyError('UNKNOWN_JOB_' + str(name))
    return dict(JOBS[name], name=name)


def names():
    return list(JOBS)
