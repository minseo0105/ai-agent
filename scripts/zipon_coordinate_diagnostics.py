"""Allowlisted diagnostics only: never log response messages, headers or URLs."""
import re


def safe_error(exc):
    response = getattr(exc, 'response', None)
    status = getattr(response, 'status_code', None)
    code = None
    if response is not None:
        try:
            candidate = response.json().get('code')
            if isinstance(candidate, str) and re.fullmatch(r'(?:PGRST[0-9]{3}|[0-9A-Z]{5})', candidate):
                code = candidate
        except (ValueError, AttributeError, TypeError):
            pass
    category = 'UNKNOWN'
    if code in ('PGRST202', 'PGRST203', '42883'):
        category = 'RPC_SIGNATURE_OR_SCHEMA_CACHE'
    elif status == 401 or code in ('PGRST301', 'PGRST302', 'PGRST303'):
        category = 'AUTHENTICATION'
    elif status == 403 or code == '42501':
        category = 'AUTHORIZATION'
    elif code in ('42703', '42P01'):
        category = 'SCHEMA'
    elif code in ('22023', '22P02', '23502', '23503', '23514', 'PGRST102'):
        category = 'PAYLOAD_OR_CONSTRAINT'
    elif status is not None:
        category = 'HTTP_ERROR_UNCLASSIFIED'
    elif type(exc).__name__ in ('Timeout', 'ConnectTimeout', 'ReadTimeout', 'ConnectionError', 'SSLError'):
        category = 'NETWORK'
    elif isinstance(exc, (ValueError, TypeError, AttributeError)):
        category = 'RESPONSE_PARSING'
    return {'error_type': type(exc).__name__, 'http_status': status,
            'server_code': code, 'failure_category': category}
