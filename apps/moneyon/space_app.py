"""Standalone Space: no portal middleware, real-family routes or DB adapters.

Only the phase-4 trial router is registered. No secrets are needed. SQLite
is intentionally ephemeral; a lost workspace asks the visitor to start again.
"""
import hashlib
import os
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event, Lock, Thread
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from api.moneyon_trial import router, trials
from api.moneyon_ai import router as ai_router

POOL_TARGET = int(os.environ.get('MONEYON_TRIAL_POOL', '0') or 0)
KEEP = int(os.environ.get('MONEYON_TRIAL_KEEP', '3000') or 3000)
last_request = [0.0]


def maintain(stop):
    # Seeds waiting samples and removes expired visitors only while no API
    # request arrived for a second, so it never competes with a busy demo.
    next_cleanup = 0.0
    while not stop.wait(0.2):
        try:
            if time.monotonic() - last_request[0] < 1:
                continue
            service = trials()
            if service.refill(POOL_TARGET):
                continue
            if time.monotonic() >= next_cleanup:
                # A full batch means more are waiting: continue on the next idle tick.
                removed = service.cleanup(limit=50, keep=KEEP)
                next_cleanup = time.monotonic() + (0 if removed >= 50 else 60)
        except Exception:
            stop.wait(5)


@asynccontextmanager
async def lifespan(app):
    stop = Event()
    if POOL_TARGET > 0:
        Thread(target=maintain, args=(stop,), name='moneyon-maintenance', daemon=True).start()
    # AI를 켰으면 첫 요청 전에 SDK를 불러 두고 클라이언트를 만든다(첫 버튼의 '첫 글자' 지연을 줄인다)
    from services import moneyon_ai
    if moneyon_ai.config()['enabled'] and not moneyon_ai.config()['fake']:
        moneyon_ai.async_client()
    yield
    stop.set()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(router)
# AI 기능(오라클 전용, MONEYON_AI_ENABLED=1일 때만 동작). HF Space에는 이 사본을 올리지 않는다.
app.include_router(ai_router)
STATIC = Path(os.environ.get('MONEYON_STATIC_DIR', 'web/out')).resolve()
lock = Lock()
windows = OrderedDict()
# Per minute. Starts and token-less writes count per peer; writes from a trial
# the server has already accepted count per trial (one visitor's taps no longer
# share a quota with everyone behind the same HF proxy peer).
START_LIMIT, WRITE_LIMIT, TRIAL_LIMIT = 300, 600, 300
# sha256 of tokens that got a 2xx answer. Unknown or wrong tokens never get their
# own bucket, so inventing tokens cannot escape the peer limit.
verified = OrderedDict()


def trial_digest(request):
    token = request.headers.get('x-moneyon-trial', '')
    return hashlib.sha256(token.encode()).hexdigest() if 0 < len(token) <= 100 else None


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    # Never show a traceback or a non-JSON body; the screen turns this into a friendly notice.
    return JSONResponse({'detail':'서버가 잠시 바빠요. 잠시 후 다시 시도해 주세요.'},status_code=500,headers={'Cache-Control':'no-store'})


@app.middleware('http')
async def boundary(request: Request, call_next):
    path = request.url.path
    if path.startswith('/api/'):
        if path != '/api/health':
            last_request[0] = time.monotonic()
        if path != '/api/health' and not path.startswith('/api/moneyon/trial/'):
            return JSONResponse({'detail':'체험 전용 Space예요.'},status_code=404)
        if request.method in ('POST','PATCH'):
            origin=request.headers.get('origin')
            if origin:
                parsed=urlsplit(origin)
                # HF terminates HTTPS before forwarding HTTP to the container.
                # Match the original Host; never trust forwarded-host headers.
                if parsed.scheme not in ('http','https') or parsed.netloc.lower()!=request.headers.get('host','').lower() or parsed.path not in ('','/'):
                    return JSONResponse({'detail':'이 체험 화면에서 요청해 주세요.'},status_code=403)
            try:
                length=int(request.headers.get('content-length','0') or '0')
            except ValueError:
                return JSONResponse({'detail':'잘못된 요청 길이예요.'},status_code=400)
            if length > 16384:
                return JSONResponse({'detail':'요청이 너무 커요.'},status_code=413)
            body=bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body)>16384:
                    return JSONResponse({'detail':'요청이 너무 커요.'},status_code=413)
            request._body=bytes(body)
            # Peer address only: do not trust arbitrary X-Forwarded-For input.
            # Shared HF proxy peers can share a quota; capabilities still
            # enforce visitor isolation independently of this coarse limit.
            peer=request.client.host if request.client else 'unknown'
            category='start' if path.endswith('/start') else 'write'
            digest=None if category=='start' else trial_digest(request)
            now=time.monotonic()
            with lock:
                trial=digest is not None and digest in verified
                key=('trial',digest) if trial else (peer,category)
                queue=windows.setdefault(key,deque())
                windows.move_to_end(key)
                while queue and queue[0] < now-60:queue.popleft()
                if len(queue)>=(START_LIMIT if category=='start' else TRIAL_LIMIT if trial else WRITE_LIMIT):
                    return JSONResponse({'detail':'잠시 쉬었다가 다시 체험해 주세요.'},status_code=429,headers={'Retry-After':'60'})
                queue.append(now)
                while len(windows)>8192:windows.popitem(last=False)
    response=await call_next(request)
    if path.startswith('/api/moneyon/trial/') and not path.endswith('/start'):
        # Every route except /start resolves the token, so 2xx proves it is live
        # and 403 means it expired or never existed.
        digest=trial_digest(request)
        if digest:
            with lock:
                if 200<=response.status_code<300:
                    verified[digest]=True
                    verified.move_to_end(digest)
                    while len(verified)>8192:verified.popitem(last=False)
                elif response.status_code==403:
                    verified.pop(digest,None)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    if path.startswith('/api/'):response.headers['Cache-Control']='no-store'
    # Hashed build assets never change; HTML and unhashed files must revalidate so
    # a new deploy shows up on the first navigation, not only after F5.
    elif path.startswith('/_next/static/'):response.headers['Cache-Control']='public, max-age=31536000, immutable'
    else:response.headers['Cache-Control']='no-cache, must-revalidate'
    return response


@app.get('/api/health')
def health():
    return {'ok':True,'service':'moneyon-trial','storage':'ephemeral','family_api':False}


class ExportedSite(StaticFiles):
    async def get_response(self,path,scope):
        path=path.replace('\\','/')
        # Next export uses /moneyon.html; reject every other application path.
        if path in ('','.'):
            return await super().get_response('index.html',scope)
        if path.rstrip('/') == 'moneyon':
            return await super().get_response('moneyon.html',scope)
        if path == 'moneyon/characters/izani-bee.png':
            return await super().get_response(path,scope)
        if not path.startswith('_next/'):
            return JSONResponse({'detail':'페이지를 찾을 수 없어요.'},status_code=404)
        return await super().get_response(path,scope)


app.mount('/',ExportedSite(directory=STATIC,check_dir=False,html=True),name='web')
