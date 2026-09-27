"""Opt-in isolated REST smoke test. Never reads production configuration.

No network on import or --help. See docs/zipon_rest_compatibility.md.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import socket
import errno
from urllib.parse import urlsplit, unquote
from unittest.mock import patch
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
TABLES = ('app_settings', 'alert_rules', 'notifications', 'source_snapshots',
          'development_projects', 'development_project_sources',
          'development_updates', 'development_collection_runs', 'geocode_cache')


class CheckFailed(Exception):
    pass


def require(ok, label):
    if not ok:
        raise CheckFailed(label)


def configuration():
    names = ('ZIPON_TEST_SUPABASE_URL', 'ZIPON_TEST_SUPABASE_SERVICE_ROLE_KEY',
             'ZIPON_TEST_PROJECT_REF', 'ZIPON_TEST_DATABASE_URL')
    values = [os.environ.get(n, '').strip() for n in names]
    for name, value in zip(names, values):
        require(bool(value), 'Missing environment variable: ' + name)
    url, key, ref, dsn = values
    require(bool(re.fullmatch(r'[a-z0-9]{20}', ref)), 'Invalid test project ref')
    u = urlsplit(url)
    require(u.scheme == 'https' and u.netloc == ref + '.supabase.co'
            and u.path in ('', '/') and not u.query and not u.fragment,
            'REST target does not match explicitly selected test project')
    # Permit a single matching outer quote pair copied with the URI, not arbitrary rewriting.
    if len(dsn) >= 2 and dsn[0] == dsn[-1] and dsn[0] in ('"', "'"):
        dsn = dsn[1:-1].strip()
    require(not any(ch.isspace() or ord(ch) < 32 for ch in dsn),
            'DB_URI_FORMAT: whitespace/control character in URI')
    try:
        d = urlsplit(dsn)
        port = d.port
    except ValueError:
        raise CheckFailed('DB_URI_FORMAT: invalid host or port syntax') from None
    require(d.scheme in ('postgres', 'postgresql'), 'DB_SCHEME: expected postgresql or postgres')
    direct = d.hostname == 'db.' + ref + '.supabase.co'
    pooled = bool(re.fullmatch(r'[a-z0-9-]+\.pooler\.supabase\.com', d.hostname or ''))
    require(direct or pooled, 'DB_HOST: expected selected direct host or Supabase session pooler host')
    require(unquote(d.username or '') == ('postgres.' + ref if pooled else 'postgres'),
            'DB_USERNAME_REF: username does not match expected project ref')
    require(port in (None, 5432), 'DB_PORT: session pooler requires 5432')
    require(d.path == '/postgres', 'DB_DATABASE: expected /postgres')
    require(not d.query and '?' not in dsn, 'DB_QUERY: query string is not allowed')
    require(not d.fragment and '#' not in dsn, 'DB_FRAGMENT: fragment is not allowed')
    require(bool(d.password), 'DB_CREDENTIAL_INPUT: URI credential field is incomplete')
    return url.rstrip('/'), key, dsn



def isolated_transport(request, url, key):
    """Keep backend payload logic; adapt only new-key authentication in this process.

    sb_secret keys are opaque API keys, not bearer JWTs. Do not change production
    code or interpret a passing adapted test as unmodified-backend readiness.
    """
    def send(method, request_url, **kwargs):
        require(request_url.startswith(url + '/rest/v1/'),
                'REST request outside selected test target blocked')
        headers = dict(kwargs.get('headers') or {})
        require(headers.get('apikey') == key, 'Unexpected REST API key blocked')
        if key.startswith('sb_secret_'):
            headers = {k: v for k, v in headers.items() if k.lower() != 'authorization'}
        kwargs['headers'] = headers
        # Never forward credentials to a redirected host.
        kwargs['allow_redirects'] = False
        stage('REST_' + method)
        response = request(method, request_url, **kwargs)
        require(not (300 <= response.status_code < 400), 'REST redirect blocked')
        return response
    return SimpleNamespace(request=send)


STAGE = 'CONFIGURATION'

def stage(name):
    global STAGE
    STAGE = name
    print('STAGE:', name, flush=True)


def connection_category(exc):
    # Inspect privately; emit ONLY fixed categories, never the exception text.
    text = str(exc).lower()
    code = getattr(exc, 'sqlstate', None)
    if isinstance(exc, socket.gaierror) or any(x in text for x in ('could not translate host', 'name or service not known', 'getaddrinfo failed')):
        return 'DNS_HOST'
    if 'tenant or user not found' in text or 'tenant not found' in text:
        return 'POOLER_TENANT_USERNAME_REF_OR_ENDPOINT'
    if code == '28P01' or 'password authentication failed' in text or 'authentication failed' in text:
        return 'AUTHENTICATION_PASSWORD'
    if 'unsupported startup parameter' in text or 'unsupported connection parameter' in text:
        return 'POOLER_STARTUP_PARAMETER'
    if any(x in text for x in ('ssl', 'tls', 'certificate')):
        return 'SSL_TLS'
    if isinstance(exc, (TimeoutError, socket.timeout)) or 'timeout' in text or 'timed out' in text:
        return 'CONNECTION_TIMEOUT'
    if getattr(exc, 'errno', None) in (errno.ENETUNREACH, errno.EHOSTUNREACH) or any(x in text for x in ('network is unreachable', 'no route to host', 'address family')):
        return 'IP_FAMILY_OR_NETWORK_ROUTE'
    if isinstance(exc, ConnectionRefusedError) or 'connection refused' in text or 'actively refused' in text:
        return 'TCP_PORT_REFUSED'
    if code and code.startswith('28'):
        return 'AUTHENTICATION_ROLE'
    return 'OTHER_POSTGRESQL_OR_TRANSPORT'


def network_preflight(host, port):
    stage('DNS_PREFLIGHT')
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    unique = list(dict.fromkeys((family, address) for family, _, _, _, address in addresses))
    require(bool(unique), 'DNS_HOST: no addresses returned')
    stage('TCP_PREFLIGHT')
    reachable = False
    for family, address in unique:
        label = 'IPv4' if family == socket.AF_INET else 'IPv6'
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(4)
                probe.connect(address)
            print('TCP:', label, 'REACHABLE')
            reachable = True
        except OSError as exc:
            print('TCP:', label, connection_category(exc))
    require(reachable, 'TCP_PREFLIGHT: no reachable endpoint; see family categories above')


def connect_database(psycopg, opts):
    stage('PSYCOPG_CONNECT')
    conn = psycopg.connect(**opts, autocommit=True)
    try:
        # Poolers may reject libpq startup options; apply session timeouts after login.
        stage('POSTGRES_SESSION_SETUP')
        conn.execute("SET statement_timeout = '20s'")
        conn.execute("SET lock_timeout = '5s'")
        return conn
    except BaseException:
        conn.close()
        raise


def report_error(exc):
    print('FAILURE STAGE:', STAGE)
    # Never print exception text, request headers, URLs, response bodies or DSNs.
    if isinstance(exc, CheckFailed):
        print('FAIL:', str(exc))  # Only static labels produced by this script.
        return
    response = getattr(exc, 'response', None)
    if response is not None:
        code = ''
        try:
            candidate = response.json().get('code', '')
            if re.fullmatch(r'(?:[0-9A-Z]{5}|PGRST[0-9]{3})', str(candidate)):
                code = candidate
        except (ValueError, AttributeError):
            pass
        causes = {'42501': 'insufficient privilege / RLS',
                  '23503': 'foreign key violation', '23505': 'unique violation',
                  '23514': 'check constraint violation', '23502': 'NOT NULL violation',
                  '22P02': 'invalid input representation',
                  'PGRST205': 'table absent from schema cache',
                  'PGRST204': 'column absent from schema cache',
                  'PGRST301': 'JWT verification failed'}
        reason = causes.get(code, {401: 'authentication rejected', 403: 'access denied',
            404: 'endpoint/resource not found', 429: 'rate limit'}.get(
                response.status_code, 'unclassified response; inspect privately in Dashboard logs'))
        print(f'FAIL: HTTP={response.status_code} code={code or "unavailable"} cause={reason}')
    else:
        code = getattr(exc, 'sqlstate', None)
        safe_code = code if isinstance(code, str) and re.fullmatch(r'[0-9A-Z]{5}', code) else 'unavailable'
        print('FAIL:', type(exc).__name__, 'SQLSTATE=' + safe_code, 'CATEGORY=' + connection_category(exc))


def read_sql(conn, query, params=()):
    stage('POSTGRES_READ_ONLY')
    with conn.transaction():
        conn.execute('SET TRANSACTION READ ONLY')
        return conn.execute(query, params).fetchall()


def cleanup(conn, tag, pid, sid, uid):
    stage('EXACT_RUN_CLEANUP')
    # Exact per-run identifiers only. No broad TEST prefix deletion or TRUNCATE.
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout = '20s'")
        conn.execute("SET LOCAL lock_timeout = '5s'")
        conn.execute('DELETE FROM public.development_updates WHERE update_id=%s AND project_id=%s AND title=%s', (uid, pid, tag))
        conn.execute('''UPDATE public.development_projects SET canonical_source_id=NULL,
            status='UNKNOWN', stage=NULL, validation_status='UNVERIFIED', geometry_verified=false
            WHERE project_id=%s AND project_name=%s''', (pid, tag))
        conn.execute('DELETE FROM public.development_project_sources WHERE source_id=%s AND project_id=%s AND source_name=%s', (sid, pid, tag))
        conn.execute('DELETE FROM public.development_projects WHERE project_id=%s AND project_name=%s', (pid, tag))
        conn.execute('DELETE FROM public.source_snapshots WHERE source=%s AND item_key=%s', (tag, tag))
        conn.execute('DELETE FROM public.notifications WHERE event_key=%s AND title=%s', (tag, tag))
        conn.execute('DELETE FROM public.alert_rules WHERE region=%s AND event_type=%s', (tag, tag))
    # Verify removal; never restore sequences or delete unrelated rows.
    queries = [
        ('development_updates', 'update_id=%s', (uid,)),
        ('development_project_sources', 'source_id=%s', (sid,)),
        ('development_projects', 'project_id=%s', (pid,)),
        ('source_snapshots', 'source=%s AND item_key=%s', (tag, tag)),
        ('notifications', 'event_key=%s', (tag,)),
        ('alert_rules', 'region=%s AND event_type=%s', (tag, tag))]
    for table, predicate, params in queries:
        require(read_sql(conn, f'SELECT count(*) FROM public.{table} WHERE {predicate}', params)[0][0] == 0,
                'Cleanup left rows in ' + table)
    print('PASS: exact-run cleanup (identity sequences are not reset)')


def exercise(m, conn, tag, pid, sid, uid):
    def step(label, fn):
        print('CHECK:', label, flush=True)
        value = fn()
        print('PASS:', label)
        return value

    def rest(method, table, **kw):
        print('REST:', method, table, flush=True)
        return m._remote_request(method, table, **kw)

    require(step('app_settings SELECT', lambda: rest('GET', 'app_settings', params={'select': '*'})) == [], 'app_settings must be empty')
    require(m.get_auto_monitor_enabled(ROOT) is False, 'Empty settings should disable monitor')
    require(step('alert_rules SELECT', lambda: m.get_alert_rules(ROOT)) == [], 'alert_rules must be empty')
    step('backend alert_rules INSERT', lambda: m.save_alert_rules(ROOT, [tag], [tag], 5.0, 60.0, ['TEST'], ['TEST']))
    rows = rest('GET', 'alert_rules', params={'region': 'eq.' + tag, 'event_type': 'eq.' + tag})
    require(len(rows) == 1 and rows[0]['enabled'] is True and rows[0]['max_price_100m'] == 5.0, 'Alert insert roundtrip')
    aid = rows[0]['id']
    require(read_sql(conn, 'SELECT count(*) FROM public.alert_rules WHERE id=%s AND region=%s', (aid, tag))[0][0] == 1,
            'REST and SQL target identity handshake failed')
    step('backend alert_rules PATCH', lambda: m.toggle_alert_rule(ROOT, aid))
    require(next(r for r in m.get_alert_rules(ROOT) if r['id'] == aid)['enabled'] is False, 'Alert PATCH roundtrip')
    require(step('backend notifications INSERT', lambda: m._notify(ROOT, tag, 'TEST', tag, 'TEST synthetic smoke data')) is True,
            'Notification insert response')
    step('backend snapshot first INSERT', lambda: require(m._snapshot_new(ROOT, tag, tag, {'TEST': tag, 'v': 1}) is True, 'Snapshot first insert'))
    step('backend snapshot existing PATCH', lambda: require(m._snapshot_new(ROOT, tag, tag, {'TEST': tag, 'v': 2}) is False, 'Snapshot existing update'))
    first = rest('GET', 'source_snapshots', params={'source': 'eq.' + tag, 'item_key': 'eq.' + tag})[0]
    require(first['payload']['v'] == 2, 'Snapshot backend update roundtrip')
    first['payload'] = {'TEST': tag, 'v': 3}
    step('snapshot REST composite-key UPSERT', lambda: rest('POST', 'source_snapshots',
        params={'on_conflict': 'source,item_key'}, payload=first,
        prefer='resolution=merge-duplicates,return=representation'))
    snapshots = rest('GET', 'source_snapshots', params={'source': 'eq.' + tag, 'item_key': 'eq.' + tag})
    require(len(snapshots) == 1 and snapshots[0]['payload']['v'] == 3, 'Snapshot UPSERT roundtrip')
    require(any(n['event_key'] == tag and n['title'] == tag for n in m.get_notifications(ROOT)), 'Notification roundtrip')

    now = datetime.now(timezone.utc).isoformat()
    project = {'project_id': pid, 'project_type': 'OTHER', 'project_name': tag,
        'location': 'SRID=4326;POINT(127.005 37.005)', 'location_source': tag,
        'geometry': 'SRID=4326;POLYGON((127 37,127.01 37,127.01 37.01,127 37.01,127 37))',
        'geometry_source': tag, 'field_evidence': {'TEST': tag}}
    step('development project + geography + Polygon REST INSERT', lambda: rest('POST', 'development_projects', payload=project))
    source = {'source_id': sid, 'project_id': pid, 'source_name': tag,
        'source_type': 'OFFICIAL_NOTICE', 'source_url': 'https://example.invalid/TEST/' + tag,
        'is_official': True, 'verified_at': now, 'verified_by': tag, 'validation_status': 'VERIFIED',
        'raw_snapshot': {'TEST': tag, 'synthetic': True}, 'content_hash': hashlib.sha256(tag.encode()).hexdigest()}
    step('synthetic official source REST INSERT', lambda: rest('POST', 'development_project_sources', payload=source))
    # Synthetic official evidence solely exercises constraints; never real business evidence.
    step('canonical source + verified polygon REST PATCH', lambda: rest('PATCH', 'development_projects',
        params={'project_id': 'eq.' + pid}, payload={'canonical_source_id': sid,
        'geometry_verified': True, 'geometry_verified_at': now, 'last_verified_at': now}))
    step('development history REST INSERT', lambda: rest('POST', 'development_updates', payload={
        'update_id': uid, 'project_id': pid, 'source_id': sid, 'update_kind': 'INITIAL',
        'to_revision': 1, 'title': tag, 'new_snapshot': project,
        'event_hash': hashlib.sha256((tag + ':history').encode()).hexdigest()}))
    for table, key, value in [('development_projects', 'project_id', pid),
                              ('development_project_sources', 'source_id', sid),
                              ('development_updates', 'update_id', uid)]:
        rows = rest('GET', table, params={key: 'eq.' + value})
        require(len(rows) == 1 and rows[0][key] == value, 'Development REST roundtrip: ' + table)
    spatial = read_sql(conn, '''
        WITH p AS (SELECT * FROM public.development_projects WHERE project_id=%s),
        cases AS (
          SELECT 'verified_polygon' label, geometry boundary, geometry_verified verified,
                 location, 'INSIDE' expected FROM p
          UNION ALL SELECT 'unverified_polygon',geometry,false,location,'NEARBY' FROM p
          UNION ALL SELECT 'point_only',NULL::extensions.geometry,false,location,'NEARBY' FROM p
          UNION ALL SELECT 'no_spatial_data',NULL::extensions.geometry,false,NULL::extensions.geography,'UNKNOWN' FROM p
        ), classified AS (
          SELECT label,expected,CASE
            WHEN verified AND boundary IS NOT NULL AND extensions.ST_Contains(boundary,
                 extensions.ST_GeomFromText('POINT(127.005 37.005)',4326)) THEN 'INSIDE'
            WHEN boundary IS NOT NULL AND extensions.ST_DWithin(boundary::extensions.geography,
                 extensions.ST_GeogFromText('SRID=4326;POINT(127.005 37.005)'),1000) THEN 'NEARBY'
            WHEN location IS NOT NULL AND extensions.ST_DWithin(location,
                 extensions.ST_GeogFromText('SRID=4326;POINT(127.005 37.005)'),1000) THEN 'NEARBY'
            ELSE 'UNKNOWN' END actual FROM cases)
        SELECT label,expected=actual FROM classified''', (pid,))
    require(len(spatial) == 4 and all(passed for _, passed in spatial), 'Stored PostGIS classification')
    shape = read_sql(conn, '''SELECT extensions.ST_SRID(geometry), extensions.GeometryType(geometry),
        extensions.ST_X(location::extensions.geometry),extensions.ST_Y(location::extensions.geometry)
        FROM public.development_projects WHERE project_id=%s''', (pid,))[0]
    require(shape == (4326, 'POLYGON', 127.005, 37.005), 'PostGIS spatial persistence')
    print('PASS: PostGIS INSIDE / NEARBY / UNKNOWN (read-only SQL, not a REST spatial RPC)')
    step('backend alert_rules DELETE', lambda: m.delete_alert_rule(ROOT, aid))
    require(rest('GET', 'alert_rules', params={'id': 'eq.' + str(aid)}) == [], 'Alert DELETE roundtrip')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--execute', action='store_true', help='Explicitly run writes against the selected empty NEW database')
    mode.add_argument('--cleanup-run', metavar='UUID', help='Recover only a previously recorded run; no test inserts')
    args = ap.parse_args()
    conn = None
    run_id = None
    try:
        url, key, dsn = configuration()
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        opts = conninfo_to_dict(dsn)
        opts.update(sslmode='require', connect_timeout=10)
        parsed = urlsplit(dsn)
        print('TARGET:', 'host=' + parsed.hostname, 'port=5432', 'database=postgres',
              'username=' + unquote(parsed.username), 'project_ref=' + urlsplit(url).hostname.split('.')[0])
        print('URI CHECKS: ref/username/host match; port=5432; database=postgres; query absent')
        network_preflight(opts['host'], 5432)
        conn = connect_database(psycopg, opts)
        stage('POSTGRES_ROLE_CHECK')
        require(read_sql(conn, 'SELECT current_user')[0][0] == 'postgres', 'SQL cleanup requires postgres role')
        run_id = uuid.UUID(args.cleanup_run) if args.cleanup_run else uuid.uuid4()
        tag = 'TEST_ZIPON_' + str(run_id)
        pid, sid, uid = [str(uuid.uuid5(run_id, name)) for name in ('project', 'source', 'update')]
        print('TEST_RUN_ID:', run_id, flush=True)
        if args.cleanup_run:
            cleanup(conn, tag, pid, sid, uid)
            return 0
        stage('POSTGRES_EMPTY_CHECK')
        for table in TABLES:
            require(read_sql(conn, f'SELECT count(*) FROM public.{table}')[0][0] == 0,
                    'New test database must be empty: ' + table)
        # Record only recovery identifiers; NEVER credentials, URLs, server responses.
        journal = ROOT / 'reports' / 'zipon-rest-tests'
        journal.mkdir(parents=True, exist_ok=True)
        (journal / (str(run_id) + '.json')).write_text(json.dumps({'run_id': str(run_id),
            'tag': tag, 'project_id': pid, 'source_id': sid, 'update_id': uid}), encoding='utf-8')
        sys.path.insert(0, str(ROOT))
        from services import realestate_monitor as monitor
        def forbid(*a, **kw):
            raise CheckFailed('Production config or local SQLite access blocked')
        transport = isolated_transport(monitor.requests.request, url, key)
        if key.startswith('sb_secret_'):
            print('AUTH MODE: secret apikey only; test-local adapter; production backend unchanged')
        success = False
        try:
            with patch.object(monitor, '_supabase_config', return_value=(url, key)), \
                 patch.object(monitor, '_secret', side_effect=forbid), \
                 patch.object(monitor, '_db', side_effect=forbid), \
                 patch.object(monitor, 'requests', transport):
                # Check REST also sees the empty target before any write.
                for table in TABLES:
                    print('CHECK: REST preflight', table, flush=True)
                    require(monitor._remote_request('GET', table, params={'select': '*', 'limit': '1'}) == [],
                            'REST test target must be empty: ' + table)
                exercise(monitor, conn, tag, pid, sid, uid)
                success = True
        except (Exception, KeyboardInterrupt) as exc:
            report_error(exc)
        finally:
            # Reconnect after network errors; never silently report cleanup success.
            if conn.closed:
                conn = connect_database(psycopg, opts)
            cleanup(conn, tag, pid, sid, uid)
        if success:
            for table in TABLES:
                require(read_sql(conn, f'SELECT count(*) FROM public.{table}')[0][0] == 0,
                        'Final nonempty table (no unrelated data will be deleted): ' + table)
            print('REST COMPATIBILITY: PASS; CLEANUP: PASS')
            if key.startswith('sb_secret_'):
                print('SCOPE: test-local apikey adapter applied; unmodified production auth not certified')
            return 0
        print('REST COMPATIBILITY: FAIL; CLEANUP: PASS')
        return 1
    except (Exception, KeyboardInterrupt) as exc:
        report_error(exc)
        if run_id is None and not args.cleanup_run:
            print('TEST DATA CREATED: NO; CLEANUP REQUIRED: NO (before run initialization)')
        else:
            print('Retain TEST_RUN_ID for exact-run cleanup recovery; never delete unrelated data.')
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == '__main__':
    sys.exit(main())
