"""요청 추적 · 오류 응답 · 상태 점검.

한 서비스의 장애가 다른 서비스나 프로세스를 끌어내리지 않게 하는 공통 층이다.

무엇을 하는가
  * 요청마다 request_id를 붙이고 응답 헤더(X-Request-Id)와 로그에 같은 값을 남긴다.
  * 처리되지 않은 예외를 JSON 오류 하나로 바꾼다. traceback은 서버 로그에만 남고
    화면에는 나가지 않는다. 오류를 200으로 숨기지도 않는다.
  * 로그 한 줄에 method · path · status · duration_ms · request_id를 남긴다.
  * 비밀값은 로그에 남기지 않는다. 헤더와 질의 문자열에서 걸러낸다.
"""
import logging
import os
import time
import uuid

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger('ailab.request')

# 이 이름이 들어간 헤더·질의 인자는 값을 적지 않는다. 비밀값이 로그로 새지 않게 한다.
SECRET_HINTS = ('authorization', 'apikey', 'api-key', 'api_key', 'token', 'secret', 'password',
                'key', 'cookie', 'set-cookie', 'x-ncp-apigw-api-key', 'servicekey')
REDACTED = '***'
# 화면에 그대로 내보내도 되는 문장. 서버 내부 사정은 적지 않는다.
INTERNAL_ERROR_MESSAGE = '잠시 문제가 발생했어요. 잠시 후 다시 시도해 주세요.'


def redact(mapping):
    """헤더·질의 인자에서 비밀값을 지운 사본."""
    safe = {}
    for name, value in (mapping or {}).items():
        lowered = str(name).lower()
        safe[name] = REDACTED if any(hint in lowered for hint in SECRET_HINTS) else value
    return safe


def request_id(request):
    """이 요청의 id. 미들웨어가 붙이기 전이면 빈 문자열."""
    return getattr(request.state, 'request_id', '') if hasattr(request, 'state') else ''


class RequestContextMiddleware(BaseHTTPMiddleware):
    """request_id 부여 · 접근 로그 · 처리되지 않은 예외의 마지막 방어선."""

    async def dispatch(self, request: Request, call_next):
        identifier = (request.headers.get('x-request-id') or '').strip()[:64] or uuid.uuid4().hex[:16]
        request.state.request_id = identifier
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = (time.perf_counter() - started) * 1000
            # traceback은 서버 로그에만 남긴다. 응답에는 내부 사정을 싣지 않는다.
            log.exception('request failed method=%s path=%s duration_ms=%.1f request_id=%s '
                          'error_type=%s query=%s', request.method, request.url.path, duration,
                          identifier, 'unhandled', redact(dict(request.query_params)))
            return JSONResponse(status_code=500,
                                content={'detail': INTERNAL_ERROR_MESSAGE, 'request_id': identifier},
                                headers={'X-Request-Id': identifier})
        duration = (time.perf_counter() - started) * 1000
        response.headers['X-Request-Id'] = identifier
        log.info('method=%s path=%s status=%s duration_ms=%.1f request_id=%s',
                 request.method, request.url.path, response.status_code, duration, identifier)
        return response


async def http_exception_handler(request: Request, exc: HTTPException):
    """의도한 오류. 원래 detail을 유지하면서 request_id만 덧붙인다."""
    identifier = request_id(request)
    detail = exc.detail
    content = dict(detail) if isinstance(detail, dict) else {'detail': detail}
    if 'detail' not in content:
        content = {'detail': detail}
    if identifier:
        content['request_id'] = identifier
    headers = dict(getattr(exc, 'headers', None) or {})
    if identifier:
        headers['X-Request-Id'] = identifier
    log.warning('method=%s path=%s status=%s request_id=%s error_type=http_exception',
                request.method, request.url.path, exc.status_code, identifier)
    return JSONResponse(status_code=exc.status_code, content=content, headers=headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """입력값 오류. 어떤 값이 들어왔는지는 응답에 싣지 않는다."""
    identifier = request_id(request)
    log.warning('method=%s path=%s status=422 request_id=%s error_type=validation',
                request.method, request.url.path, identifier)
    return JSONResponse(status_code=422,
                        content={'detail': '입력값을 확인해 주세요.', 'request_id': identifier},
                        headers={'X-Request-Id': identifier} if identifier else None)


async def unhandled_exception_handler(request: Request, exc: Exception):
    """미들웨어를 거치지 않는 경로까지 덮는 마지막 방어선."""
    identifier = request_id(request)
    log.exception('method=%s path=%s status=500 request_id=%s error_type=%s',
                  request.method, request.url.path, identifier, type(exc).__name__)
    return JSONResponse(status_code=500,
                        content={'detail': INTERNAL_ERROR_MESSAGE, 'request_id': identifier},
                        headers={'X-Request-Id': identifier} if identifier else None)


def configure_logging():
    """배포 환경에서 접근 로그가 보이도록 기본 수준만 맞춘다."""
    level = os.environ.get('AILAB_LOG_LEVEL', 'INFO').upper()
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level,
                            format='%(asctime)s %(levelname)s %(name)s %(message)s')
    log.setLevel(level)
