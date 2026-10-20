"""Standalone Space: no portal middleware, real-family routes or DB adapters.

Only the phase-4 trial router is registered. No secrets are needed. SQLite
is intentionally ephemeral; a lost workspace asks the visitor to start again.
"""
import os
import time
from collections import OrderedDict, deque
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from api.moneyon_trial import router

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)
STATIC = Path(os.environ.get('MONEYON_STATIC_DIR', 'web/out')).resolve()
lock = Lock()
windows = OrderedDict()


@app.middleware('http')
async def boundary(request: Request, call_next):
    path = request.url.path
    if path.startswith('/api/'):
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
            now=time.monotonic()
            with lock:
                key=(peer,category)
                queue=windows.setdefault(key,deque())
                windows.move_to_end(key)
                while queue and queue[0] < now-60:queue.popleft()
                if len(queue)>=(60 if category=='start' else 600):
                    return JSONResponse({'detail':'잠시 쉬었다가 다시 체험해 주세요.'},status_code=429,headers={'Retry-After':'60'})
                queue.append(now)
                while len(windows)>4096:windows.popitem(last=False)
    response=await call_next(request)
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
