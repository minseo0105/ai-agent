"""MONEY:ON AI 라우터(오라클 전용). 경로는 체험 경로 아래(/api/moneyon/trial/ai/…) — space_app의 경계·요청 제한을 그대로 탄다.

POST /api/moneyon/trial/ai/{letter|coach|parent} → text/event-stream
  event: queue    {"position": n}           순서대로 쓰고 있어요(앞에 n명)
  event: thinking {}                         꿀벌이 생각 중
  event: delta    {"text": "..."}            글자가 써지듯
  event: replace  {"text": "...", "source"}  AI 글이 검사에 걸려 준비된 결과로 바꿈
  event: done     {"source": "ai|prepared|rule", "model", "reason"}
"""
import asyncio
import hashlib
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.moneyon_trial import Auth, busy, trials
from services import moneyon_ai as ai

log = logging.getLogger('moneyon.ai')
router = APIRouter(prefix='/api/moneyon/trial', tags=['moneyon-ai'])


class AiRequest(BaseModel):
    book_id: str | None = Field(default=None, max_length=80)
    weekly: int | None = Field(default=None, ge=0, le=1000000)


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get('/ai/config')
def ai_config():
    cfg = ai.config()
    return {'enabled': cfg['enabled'], 'features': cfg['features'] if cfg['enabled'] else [], 'demo_entry': cfg['demo_entry']}


def _facts(service, auth, feature, req):
    import sqlite3
    try:
        with service.ledger.db():
            row = service.resolve(auth.token)
            state = service.snapshot(row)['state']
        return ai.facts_for(feature, state, req.book_id, req.weekly)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except sqlite3.OperationalError:
        raise busy()


async def _type_out(text, chunk=6, delay=0.035):
    """준비된 결과도 글자가 써지듯 같은 흐름으로 보여 준다."""
    for i in range(0, len(text), chunk):
        yield sse('delta', {'text': text[i:i + chunk]})
        await asyncio.sleep(delay)


async def stream_feature(feature, facts, digest):
    cfg = ai.config()
    model = ai.model_for(feature)
    yield sse('thinking', {})

    async def give_fallback(reason):
        text, source = ai.fallback(feature, facts)
        ai.add_usage(model, fallback_used=True)
        async for chunk in _type_out(text):
            yield chunk
        yield sse('done', {'source': source, 'model': None, 'reason': reason})

    if not ai.person_allowed(digest, feature):
        async for c in give_fallback('person_limit'):
            yield c
        return
    if not ai.budget_left():
        async for c in give_fallback('daily_budget'):
            yield c
        return

    # 동시 상한: 넘치면 대기열 순번을 보여 주며 기다린다(최대 queue_wait초)
    events: asyncio.Queue = asyncio.Queue()

    async def on_wait(position):
        await events.put(sse('queue', {'position': position}))

    gate = ai.gate()
    acquiring = asyncio.ensure_future(gate.acquire(cfg['queue_wait'], on_wait))
    try:
        while not acquiring.done():
            try:
                yield await asyncio.wait_for(events.get(), timeout=0.25)
            except asyncio.TimeoutError:
                pass
    except BaseException:
        # 기다리는 동안 화면을 닫으면: 기다림을 취소하고, 이미 순서를 받았으면 돌려준다(자리 새지 않게)
        if not acquiring.done():
            acquiring.cancel()
        elif not acquiring.cancelled() and acquiring.exception() is None and acquiring.result():
            await gate.release()
        raise
    while not events.empty():
        events.get_nowait()
    if not acquiring.result():
        async for c in give_fallback('queue_full'):
            yield c
        return
    yield sse('thinking', {})

    text, source, reason, usage = '', 'ai', '', None
    try:
        client = None if cfg['fake'] else ai.async_client()
        if not cfg['fake'] and client is None:
            async for c in give_fallback('no_key'):
                yield c
            return
        started = time.monotonic()
        first_deadline = started + cfg['first_token']  # 요청 시작부터 첫 글자까지(연결·응답 시작 포함)
        stream_cm, entered = None, False
        if cfg['fake']:
            chunks = ai.fake_stream(feature, facts)
        else:
            stream_cm = client.messages.stream(**ai.request_kwargs(feature, facts, model))
            try:
                stream = await asyncio.wait_for(stream_cm.__aenter__(), timeout=max(0.01, first_deadline - time.monotonic()))
            except asyncio.TimeoutError:
                reason = 'first_token_timeout'
                raise
            entered = True
            chunks = stream.text_stream
        try:
            it = chunks.__aiter__()
            try:
                first = await asyncio.wait_for(it.__anext__(), timeout=max(0.01, first_deadline - time.monotonic()))
            except (asyncio.TimeoutError, StopAsyncIteration):
                reason = 'first_token_timeout'
                raise
            text = first
            yield sse('delta', {'text': first})
            while True:
                left = cfg['total'] - (time.monotonic() - started)
                if left <= 0:
                    reason = 'total_timeout'
                    raise asyncio.TimeoutError
                try:
                    piece = await asyncio.wait_for(it.__anext__(), timeout=left)
                except StopAsyncIteration:
                    break
                text += piece
                yield sse('delta', {'text': piece})
            if entered:
                final = await stream.get_final_message()
                usage = (final.usage.input_tokens, final.usage.output_tokens)
                if final.stop_reason in ('refusal', 'max_tokens'):
                    reason = f'stop_{final.stop_reason}'
        finally:
            if entered:
                await stream_cm.__aexit__(None, None, None)
    except (asyncio.TimeoutError, StopAsyncIteration):
        reason = reason or 'timeout'
    except Exception as e:  # 키·네트워크·한도·거절 오류: 준비된 결과로
        reason = f'error:{type(e).__name__}'
        log.warning('moneyon ai %s failed: %s', feature, type(e).__name__)
    finally:
        await gate.release()

    if usage:
        ai.add_usage(model, *usage)
    problem = reason or ai.check(text, facts)
    if problem:
        fb_text, fb_source = ai.fallback(feature, facts)
        ai.add_usage(model, fallback_used=True)
        if text:
            # 이미 일부 보였으면 한 번에 바꾼다(화면은 페이드로 교체)
            yield sse('replace', {'text': fb_text, 'source': fb_source})
        else:
            async for c in _type_out(fb_text):
                yield c
        yield sse('done', {'source': fb_source, 'model': None, 'reason': problem})
        return
    yield sse('done', {'source': source, 'model': model, 'reason': ''})


@router.post('/ai/{feature}')
async def ai_feature(feature: str, req: AiRequest, auth=Depends(Auth), service=Depends(trials)):
    cfg = ai.config()
    if not cfg['enabled'] or feature not in cfg['features']:
        raise HTTPException(404, 'AI 기능이 꺼져 있어요.')
    if feature == 'coach' and (not req.book_id or req.weekly is None):
        raise HTTPException(400, '저축통장과 일주일 저금액을 골라 주세요.')
    facts = await run_in_threadpool(_facts, service, auth, feature, req)
    digest = hashlib.sha256(auth.token.encode()).hexdigest()
    return StreamingResponse(stream_feature(feature, facts, digest), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ---------------------------------------------------------------
# 시연 모드: 버튼 하나로 시연용 체험 데이터(각자 자기 통장에 복사)
# ---------------------------------------------------------------

DEMO_EXPENSES = [('간식', 1500), ('문구', 3000), ('책', 5000), ('간식', 2000), ('게임', 3000)]
DEMO_BOOK = ('자전거', 50000, '⭐', 'mint')
DEMO_DEPOSIT = 10000


def seed_demo(service):
    from services import moneyon_savings as savings
    result = service.start()
    token = result['token']
    with service.ledger.db() as db:
        row = service.resolve(token)
        family, child, day = row['family'], row['child'], service.day(row)
        savings.migrate(db, child)
        for i, (category, amount) in enumerate(DEMO_EXPENSES):
            service.ledger.transact(family, child, 'expense', f'demo-expense-{i}', amount, category, '', today=day)
        name, target, icon, color = DEMO_BOOK
        book = savings.create(db, child, name, target, icon, color, '', 'demo-book')
        service.ledger.transact(family, child, 'deposit', 'demo-deposit', DEMO_DEPOSIT, '', '', today=day)
        tx = db.execute('SELECT id FROM transactions WHERE child=? AND request_key=?', (child, 'demo-deposit')).fetchone()[0]
        savings.assign(db, child, tx, book)
        snap = service.snapshot(service.resolve(token))
    return dict(token=token, **snap)


@router.post('/demo')
def demo_start(service=Depends(trials)):
    import sqlite3
    if not ai.config()['demo_entry']:
        raise HTTPException(404, '시연 모드가 꺼져 있어요.')
    try:
        return seed_demo(service)
    except sqlite3.OperationalError:
        raise busy()
