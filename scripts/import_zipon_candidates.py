"""Default is local inspection only. --apply-new-db is an explicit future write action."""
import argparse
import json
import os
from pathlib import Path
import sys
import re
import uuid
from datetime import datetime
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.development_collector import import_batch
from services.supabase_auth import supabase_headers

STAGE = 'START'
class ImportDiagnostic(ValueError):
    def __init__(self, reason):
        self.safe_reason = reason
        self.failure_stage = STAGE
        super().__init__(reason)

def check(ok, reason):
    if not ok: raise ImportDiagnostic(reason)

def validate_records(records):
    check(isinstance(records,list), 'RECORDS_NOT_ARRAY')
    seen=set()
    for index, record in enumerate(records,1):
        try:
            pid=str(uuid.UUID(record['project_id']))
            check(pid not in seen, 'DUPLICATE_PROJECT_ID')
            seen.add(pid)
            for name in ('project_name','project_type','sigungu'):
                check(isinstance(record.get(name),str) and bool(record[name].strip()), 'INVALID_'+name.upper())
            src=record['source']
            check(src.get('source_type')=='OFFICIAL_WEBSITE' and src.get('is_official') is True, 'INVALID_SOURCE_TYPE')
            check(bool(re.fullmatch(r'https://(?:cleanup[.]seoul[.]go[.]kr|news[.]seoul[.]go[.]kr)/[^\s]+',src.get('source_url',''))),'INVALID_OFFICIAL_SOURCE_URL')
            check(bool(re.fullmatch(r'[0-9a-f]{64}',src.get('content_hash',''))),'INVALID_CONTENT_HASH')
            check(isinstance(src.get('raw_snapshot'),dict),'INVALID_SNAPSHOT')
            check(bool(src.get('source_name')),'MISSING_SOURCE_NAME')
            datetime.fromisoformat(src['collected_at'])
        except ImportDiagnostic as exc:
            raise ImportDiagnostic('CANDIDATE_'+str(index)+'_'+exc.safe_reason) from None
        except (KeyError,TypeError,ValueError):
            raise ImportDiagnostic('CANDIDATE_'+str(index)+'_INVALID_FIELD_OR_TIMESTAMP') from None

def import_configuration():
    # Import credentials intentionally never fall back to TEST or production settings.
    url=os.environ.get('ZIPON_IMPORT_SUPABASE_URL','').strip().rstrip('/')
    key=os.environ.get('ZIPON_IMPORT_SUPABASE_KEY','').strip()
    check(bool(url),'MISSING_ZIPON_IMPORT_SUPABASE_URL')
    check(bool(key),'MISSING_ZIPON_IMPORT_SUPABASE_KEY')
    check('/rest/v1' not in url,'PROJECT_URL_MUST_NOT_INCLUDE_REST_V1')
    check(url=='https://nnxtkvjpzqqhjlgnprzo.supabase.co','NEW_PROJECT_URL_MISMATCH')
    check(not key.startswith('sb_publishable_'),'SERVER_SECRET_KEY_REQUIRED')
    check(not any(c.isspace() for c in key),'KEY_CONTAINS_WHITESPACE')
    return url,supabase_headers(key)

def safe_failure(exc):
    print('IMPORT FAILED')
    print('STAGE:',STAGE)
    print('TYPE:',type(exc).__name__)
    print('REASON:',exc.safe_reason if isinstance(exc,ImportDiagnostic) else {
        'JSONDecodeError':'INVALID_JSON_RESPONSE_OR_FILE',
        'FileNotFoundError':'INPUT_FILE_NOT_FOUND',
        'Timeout':'REQUEST_TIMEOUT', 'ConnectionError':'CONNECTION_FAILED'
    }.get(type(exc).__name__,'UNCLASSIFIED_ERROR_DETAILS_SUPPRESSED'))


def main():
    global STAGE
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('file',type=Path)
    ap.add_argument('--apply-new-db',action='store_true')
    ap.add_argument('--check-config',action='store_true',help='Validate local inputs only; no HTTP or DB writes')
    args=ap.parse_args()
    STAGE='CANDIDATE_FILE_VALIDATION'
    records=json.loads(args.file.read_text(encoding='utf-8'))['records']
    validate_records(records)
    print('CANDIDATES:',len(records))
    if not args.apply_new_db and not args.check_config:
        print('LOCAL INSPECTION ONLY; no DB connection')
        return 0
    if not 1 <= len(records) <= 10:
        raise ImportDiagnostic('CANARY_LIMIT_1_TO_10')
    STAGE='IMPORT_CONFIGURATION'
    url,headers=import_configuration()
    if args.check_config:
        print('CONFIGURATION: PASS; no HTTP requests or DB writes')
        return 0
    def request(method,table,**kwargs):
        global STAGE
        STAGE='REST_'+method+'_'+table
        payload=kwargs.pop('payload',None)
        r=requests.request(method,url+'/rest/v1/'+table,json=payload,
            headers=headers,timeout=30,allow_redirects=False,**kwargs)
        if not 200<=r.status_code<300:
            raise ImportDiagnostic('HTTP_STATUS_'+str(r.status_code))
        STAGE='REST_RESPONSE_'+table
        return r.json() if r.content else []
    result=import_batch(records,request)
    print(json.dumps(result,ensure_ascii=False))
    return 1 if result['errors'] else 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        safe_failure(exc)
        sys.exit(1)
