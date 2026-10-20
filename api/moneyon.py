"""Family scoped MONEY:ON API. Explicit local-development opt-in only."""
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from api.access import _token
from services import access
from services.moneyon import Ledger, period, reward
from services.moneyon_banking import MockBankingAdapter, MERCHANTS
from services.moneyon_demo import DemoWorkspaces

router = APIRouter(prefix='/api/moneyon', tags=['moneyon'])


def ledger():
    # An ephemeral production filesystem must never silently become the family DB.
    if os.environ.get('MONEYON_LOCAL_DEV') != '1' or os.environ.get('APP_ENV', '').lower() in ('production', 'prod'):
        raise HTTPException(503, 'MONEY:ON은 현재 로컬 개발 모드에서만 사용할 수 있어요.')
    return Ledger(os.environ.get('MONEYON_DB', 'data/moneyon/development.sqlite3'))


def identity(request: Request):
    who = access.identify(_token(request))
    if not who:
        raise HTTPException(401, 'AI LAB 로그인이 필요해요.')
    family = 'member:' + who['id'] if who['role'] == 'member' else 'admin:local'
    demo_id = request.headers.get('x-moneyon-demo', '')
    if demo_id:
        require_demo()
        try:
            return DemoWorkspaces(ledger()).resolve(family, demo_id)
        except PermissionError as e:
            raise HTTPException(403, str(e))
    return family


def session(request: Request, x_moneyon_session: str = Header(default=''), family=Depends(identity), db=Depends(ledger)):
    try:
        child = request.path_params.get('child')
        auth = db.authorize(family, x_moneyon_session, child=child)
        return db, family, auth, x_moneyon_session
    except PermissionError as e:
        raise HTTPException(403, str(e))


def parent(ctx):
    if ctx[2]['child']:
        raise HTTPException(403, '부모 인증이 필요해요.')


def today():
    return datetime.now(timezone(timedelta(hours=9))).date()


def business_date(ctx):
    return DemoWorkspaces(ctx[0]).business_date(ctx[1], today())


def require_demo():
    if os.environ.get('MONEYON_DEMO') != '1' or os.environ.get('APP_ENV', '').lower() in ('production', 'prod'):
        raise HTTPException(403, '데모 전용 환경에서만 사용할 수 있어요.')


def banking(ctx):
    return MockBankingAdapter(ctx[0])


class Pin(BaseModel):
    pin: str = Field(pattern=r'^\d{6,12}$')


@router.post('/unlock')
def unlock(req: Pin, family=Depends(identity), db=Depends(ledger)):
    token = db.unlock(family, req.pin)
    if not token:
        raise HTTPException(403, 'PIN이 다르거나 잠시 잠긴 상태예요. 5회 실패하면 5분 뒤 재시도해 주세요.')
    return {'token': token}


@router.post('/lock')
def lock(x_moneyon_session: str = Header(default=''), family=Depends(identity), db=Depends(ledger)):
    db.lock(family, x_moneyon_session)
    return {'ok': True}


class Policy(BaseModel):
    frequency: Literal['weekly', 'monthly'] = 'weekly'
    amount: int = Field(default=10000, ge=1, le=10000000, strict=True)
    pay_day: int = Field(default=0, ge=0, le=31, strict=True)
    rate_bps: int = Field(default=1000, ge=0, le=10000, strict=True)
    cap: int = Field(default=1000, ge=0, le=1000000, strict=True)
    rollover: bool = True


class Child(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    grade: int = Field(default=1, ge=1, le=6)
    avatar: Literal['🪙', '🐰', '🐻', '🧑‍🚀'] = '🪙'
    theme: Literal['moneyon', 'adventure', 'animals'] = 'moneyon'
    policy: Policy
    status: Literal['active', 'paused', 'archived'] = 'active'


def save(req, ctx, child=None):
    parent(ctx)
    p = req.policy
    if (p.frequency == 'weekly' and p.pay_day > 6) or (p.frequency == 'monthly' and p.pay_day < 1):
        raise HTTPException(422, '매주는 월요일 0~일요일 6, 매월은 1~31일을 입력해 주세요.')
    try:
        cid = ctx[0].save_child(ctx[1], req.model_dump(exclude={'policy', 'status'}), p.model_dump(), child, req.status)
        return {'id': cid}
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get('/children')
def children(ctx=Depends(session)):
    parent(ctx)
    return ctx[0].children(ctx[1])


@router.post('/children')
def create(req: Child, ctx=Depends(session)):
    return save(req, ctx)


@router.put('/children/{child}')
def update(child: str, req: Child, ctx=Depends(session)):
    return save(req, ctx, child)


@router.post('/children/{child}/select')
def select(child: str, ctx=Depends(session)):
    parent(ctx)
    try:
        return {'token': ctx[0].child_session(ctx[1], ctx[3], child)}
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get('/children/{child}')
def state(child: str, ctx=Depends(session)):
    try:
        return ctx[0].state(ctx[1], child, business_date(ctx))
    except PermissionError as e:
        raise HTTPException(403, str(e))


class Transaction(BaseModel):
    kind: Literal['payment', 'expense', 'interest', 'deposit', 'withdraw']
    key: str = Field(min_length=8, max_length=100)
    amount: int = Field(default=0, ge=0, le=10000000, strict=True)
    category: Literal['', '간식', '문구', '장난감', '게임', '책', '선물', '기타'] = ''
    note: str = Field(default='', max_length=200)
    cycle_id: str | None = None
    merchant: Literal['편의점', '문구점', '서점', '게임'] | None = None


@router.post('/children/{child}/transactions')
def transaction(child: str, req: Transaction, ctx=Depends(session)):
    if req.kind in ('payment', 'interest'):
        parent(ctx)
    try:
        adapter = banking(ctx)
        day = business_date(ctx)
        if req.kind == 'payment':
            adapter.transfer_allowance(ctx[1], child, req.key, day)
        elif req.kind == 'interest':
            adapter.settle_reward_interest(ctx[1], child, req.key, req.cycle_id, day)
        elif req.kind == 'deposit':
            adapter.transfer_to_savings(ctx[1], child, req.key, req.amount, day)
        elif req.kind == 'withdraw':
            adapter.transfer_from_savings(ctx[1], child, req.key, req.amount, day)
        elif req.merchant:
            adapter.simulate_purchase(ctx[1], child, req.key, req.merchant, req.amount, day)
        else:
            ctx[0].transact(ctx[1], child, req.kind, req.key, req.amount, req.category, req.note, req.cycle_id, day)
        return ctx[0].state(ctx[1], child, day)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except (ValueError, sqlite3.IntegrityError) as e:
        raise HTTPException(409, str(e))


class Goal(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    amount: int = Field(ge=1, le=10000000, strict=True)


@router.post('/children/{child}/goals')
def goal(child: str, req: Goal, ctx=Depends(session)):
    try:
        ctx[0].goal(ctx[1], child, req.name, req.amount)
        return {'ok': True}
    except PermissionError as e:
        raise HTTPException(403, str(e))


class Experiment(BaseModel):
    spend: int = Field(ge=0, le=10000000, strict=True)


@router.post('/children/{child}/experiment')
def experiment(child: str, req: Experiment, ctx=Depends(session)):
    s = state(child, ctx)
    current = next((c for c in s['cycles'] if not c['ended']), None)
    if not current:
        raise HTTPException(409, '먼저 이번 주기의 용돈을 지급해 주세요.')
    if req.spend > s['wallet']:
        raise HTTPException(422, '사용 가능한 돈보다 큰 금액이에요.')
    left = s['wallet'] - req.spend
    eligible = max(0, current['eligible'] - req.spend)
    interest = reward(eligible, current['policy'])
    return {'left': left, 'eligible': eligible, 'interest': interest, 'total': left + interest}


class Cancellation(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


@router.post('/children/{child}/transactions/{transaction_id}/cancel')
def cancel(child: str, transaction_id: str, req: Cancellation, ctx=Depends(session)):
    parent(ctx)
    try:
        ctx[0].cancel_expense(ctx[1], child, transaction_id, req.reason, business_date(ctx))
        return ctx[0].state(ctx[1], child, business_date(ctx))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


class Quiz(BaseModel):
    quest: Literal['interest', 'needs']
    answer: int = Field(strict=True)


@router.post('/children/{child}/quiz')
def quiz(child: str, req: Quiz, ctx=Depends(session)):
    try:
        correct = ctx[0].complete_quiz(ctx[1], child, req.quest, req.answer)
        return {'correct': correct, 'message': '정답! 가상 XP를 받았어요.' if correct else '다시 도전해 봐! 이자는 남긴 돈의 일정 부분이고, 필요한 소비는 생활에 꼭 쓰는 돈이야.'}
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get('/dashboard')
def dashboard(ctx=Depends(session)):
    parent(ctx)
    kids = ctx[0].children(ctx[1])
    states = {c['id']: ctx[0].state(ctx[1], c['id'], business_date(ctx)) for c in kids}
    active = [states[c['id']] for c in kids if c['status'] != 'archived']
    return {'states': states, 'summary': {'children': len(active), 'paid': sum(s['report']['paid'] for s in active), 'spent': sum(s['report']['spent'] for s in active), 'interest': sum(s['report']['interest'] for s in active), 'pending': sum(sum(c['ended'] and not c['settled'] for c in s['cycles']) for s in active)}, 'missions': {'all_goals': bool(active) and all(s['goals'] for s in active), 'all_records': bool(active) and all(s['report']['record_days'] >= 3 for s in active)}}


@router.get('/banking')
def parent_banking(ctx=Depends(session)):
    parent(ctx)
    adapter = banking(ctx)
    visible = adapter.get_accounts(ctx[1])
    history = [t for a in visible for t in adapter.get_transactions(ctx[1], a['id'])]
    history.sort(key=lambda t: t['seq'], reverse=True)
    return {'accounts': visible, 'transactions': history, 'demo_enabled': os.environ.get('MONEYON_DEMO') == '1', 'workspace': DemoWorkspaces(ctx[0]).info(ctx[1]), 'business_date': business_date(ctx).isoformat(), 'merchants': {k: {'category': v[0], 'amount': v[1]} for k, v in MERCHANTS.items()}}


class CategoryChange(BaseModel):
    category: Literal['간식', '문구', '장난감', '게임', '책', '선물', '기타']


@router.patch('/children/{child}/transactions/{transaction_id}/category')
def category_change(child: str, transaction_id: str, req: CategoryChange, ctx=Depends(session)):
    try:
        banking(ctx).change_category(ctx[1], child, transaction_id, req.category)
        return ctx[0].state(ctx[1], child, business_date(ctx))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post('/demo/start')
def demo_start(ctx=Depends(session)):
    parent(ctx)
    require_demo()
    return DemoWorkspaces(ctx[0]).create(ctx[1], ctx[3], today())


@router.post('/demo/reset')
def demo_reset(ctx=Depends(session)):
    parent(ctx)
    require_demo()
    try:
        return DemoWorkspaces(ctx[0]).create(ctx[1], ctx[3], today(), reset=True)
    except PermissionError as e:
        raise HTTPException(403, str(e))


class DemoDate(BaseModel):
    date: date


@router.post('/demo/date')
def demo_date(req: DemoDate, ctx=Depends(session)):
    parent(ctx)
    require_demo()
    try:
        return DemoWorkspaces(ctx[0]).advance(ctx[1], req.date)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
