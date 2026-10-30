"""Public trial capabilities never authenticate against family accounts."""
import os
import sqlite3
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from api import moneyon as core
from services.moneyon_trial import TrialLedger, Trials
from services import moneyon_savings as savings

def no_cache(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Vary'] = 'X-Moneyon-Trial'


router = APIRouter(prefix='/api/moneyon/trial', tags=['moneyon-trial'], dependencies=[Depends(no_cache)])


@lru_cache(maxsize=4)
def store(path):
    return TrialLedger(path)


def trials():
    # Persistent prototype storage must be explicitly enabled. This flag does
    # not enable the real-family development API or perform any bank calls.
    if os.environ.get('MONEYON_TRIAL_ENABLED') != '1':
        raise HTTPException(503, '체험 모드가 아직 준비되지 않았어요.')
    path = Path(os.environ.get('MONEYON_TRIAL_DB', 'data/moneyon/trial.sqlite3')).resolve()
    family = Path(os.environ.get('MONEYON_DB', 'data/moneyon/development.sqlite3')).resolve()
    if path == family or path.is_symlink():
        raise HTTPException(503, '체험 DB는 가족 DB와 분리해야 해요.')
    return Trials(store(str(path)))


BUSY = '지금 체험하는 사람이 많아요. 잠시 후 다시 눌러 주세요.'


def busy():
    return HTTPException(503, BUSY, headers={'Retry-After': '5'})


class Auth:
    def __init__(self, x_moneyon_trial: str = Header(default='', max_length=100),
                 x_moneyon_trial_version: int = Header(default=0)):
        self.token = x_moneyon_trial
        self.generation = x_moneyon_trial_version


def execute(service, auth, child, operation, write=False):
    try:
        with service.ledger.db():
            row = service.resolve(auth.token, child, auth.generation if write else None)
            ctx = (service.ledger, row['family'], {'child': row['child']}, '')
            return operation(row, ctx)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except (ValueError, sqlite3.IntegrityError) as e:
        raise HTTPException(409, str(e))
    except sqlite3.OperationalError:
        raise busy()


@router.post('/start')
def start(service=Depends(trials)):
    try:
        return service.start()
    except sqlite3.OperationalError:
        raise busy()


@router.get('/state')
def resume(auth=Depends(Auth), service=Depends(trials)):
    return execute(service, auth, None, lambda row, ctx: service.snapshot(row))


class Reset(BaseModel):
    key: str = Field(min_length=8, max_length=100)


@router.post('/reset')
def reset(req: Reset, auth=Depends(Auth), service=Depends(trials)):
    try:
        return service.reset(auth.token, auth.generation, req.key)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except sqlite3.OperationalError:
        raise busy()


@router.get('/children/{child}')
def state(child: str, auth=Depends(Auth), service=Depends(trials)):
    return execute(service, auth, child, lambda row, ctx: core.state(child, ctx))


class Transaction(core.Transaction):
    kind: Literal['expense', 'deposit', 'withdraw']
    amount: int = Field(ge=100, le=10000000, multiple_of=100, strict=True)
    book_id: str | None = None


@router.post('/children/{child}/transactions')
def transaction(child: str, req: Transaction, auth=Depends(Auth), service=Depends(trials)):
    def operation(row,ctx):
        with service.ledger.db() as db:
            default=savings.migrate(db,child)
            book=req.book_id or default
            previous=db.execute('SELECT id FROM transactions WHERE child=? AND request_key=?',(child,req.key)).fetchone()
            if req.kind in ('deposit','withdraw'):
                own=next((b for b in savings.balances(db,child) if b['id']==book),None)
                if not own: raise ValueError('내 저축통장을 선택해 주세요.')
                if own['status']=='pending': raise ValueError('엄마가 승인하면 이 통장을 쓸 수 있어요.')
                if not previous and req.kind=='withdraw' and req.amount>own['balance']: raise ValueError(f"이 저축통장에는 {own['balance']:,}원이 있어요. 그보다 많이는 꺼낼 수 없어요.")
            # Do not call core.transaction here: its state refresh would migrate the new entry before assignment.
            from services.moneyon_banking import MERCHANTS
            service.ledger.transact(row['family'],child,req.kind,req.key,req.amount,
                MERCHANTS[req.merchant][0] if req.merchant else req.category,req.merchant or req.note,
                today=service.day(row),metadata={'merchant':req.merchant} if req.merchant else None)
            if req.kind in ('deposit','withdraw'):
                tx=db.execute('SELECT id FROM transactions WHERE child=? AND request_key=?',(child,req.key)).fetchone()[0]
                savings.assign(db,child,tx,book)
            return service.snapshot(row)['state']
    return execute(service,auth,child,operation,True)


class Book(Reset):
    name: str = Field(min_length=1,max_length=30)
    target: int = Field(ge=100,le=10000000,multiple_of=100,strict=True)
    icon: str = '🐷'
    color: str = 'blue'
    nickname: str = Field(default='',max_length=20)


@router.post('/children/{child}/books')
def book(child:str,req:Book,auth=Depends(Auth),service=Depends(trials)):
    def operation(row,ctx):
        with service.ledger.db() as db:
            savings.create(db,child,req.name,req.target,req.icon,req.color,req.nickname,req.key,approval=True)
        return service.snapshot(row)['state']
    return execute(service,auth,child,operation,True)


@router.post('/children/{child}/books/{book}/approve')
def approve_book(child:str,book:str,auth=Depends(Auth),service=Depends(trials)):
    # 체험에서는 아이 화면과 엄마 화면이 한 체험 안에 있다. 이 체험의 토큰으로 자기 통장만 승인할 수 있다(execute가 확인).
    def operation(row,ctx):
        with service.ledger.db() as db:
            savings.approve(db,child,book)
        return service.snapshot(row)['state']
    return execute(service,auth,child,operation,True)


class PaymentRule(BaseModel):
    mode: Literal['manual','automatic']
    approved: Literal[True]


@router.post('/children/{child}/payment-rule')
def payment_rule(child:str,req:PaymentRule,auth=Depends(Auth),service=Depends(trials)):
    def operation(row,ctx):
        with service.ledger.db() as db:
            cycle=db.execute('SELECT end FROM cycles WHERE child=? AND start<=? AND end>?',(child,service.day(row).isoformat(),service.day(row).isoformat())).fetchone()
            if not cycle: raise ValueError('다음 주 설정을 확인할 수 없어요.')
            db.execute('INSERT OR REPLACE INTO moneyon_payment_rules VALUES(?,?,?)',(child,cycle['end'],req.mode))
        return service.snapshot(row)['state']
    return execute(service,auth,child,operation,True)


class RewardChoice(Reset):
    payout: str
    choice: Literal['all','partial','keep']
    amount: int = Field(default=0,ge=0,le=10000000,strict=True)
    book_id: str | None = None


@router.post('/children/{child}/reward-saving')
def reward_saving(child:str,req:RewardChoice,auth=Depends(Auth),service=Depends(trials)):
    def operation(row,ctx):
        with service.ledger.db() as db:
            old=db.execute('SELECT * FROM moneyon_reward_choices WHERE payout=? OR (child=? AND request_key=?)',(req.payout,child,req.key)).fetchone()
            if old:
                if (old['child'],old['payout'],old['request_key'],old['choice'],old['book'],old['amount'])!=(child,req.payout,req.key,req.choice,req.book_id,req.amount): raise ValueError('이 이자는 이미 저축 방법을 골랐어요.')
                return service.snapshot(row)['state']
            available=savings.payout_available(db,child,req.payout)
            paid=db.execute('SELECT wallet FROM transactions WHERE child=? AND id=?',(child,req.payout)).fetchone()[0]
            if req.choice=='keep':
                if req.amount or req.book_id: raise ValueError('그대로 두기는 0원으로 선택해 주세요.')
            elif req.choice=='all':
                if req.amount!=paid or available<paid: raise ValueError('이미 사용한 이자는 전액 다시 저축할 수 없어요.')
            elif req.amount<100 or req.amount%100 or req.amount>available:
                raise ValueError('남아 있는 이자 안에서 100원 단위로 골라 주세요.')
            transaction=None
            if req.choice!='keep':
                if not req.book_id: raise ValueError('저축통장을 선택해 주세요.')
                savings.migrate(db,child)
                service.ledger.transact(row['family'],child,'deposit',req.key,req.amount,note='받은 이자 저축하기',today=service.day(row))
                transaction=db.execute('SELECT id FROM transactions WHERE child=? AND request_key=?',(child,req.key)).fetchone()[0]
                savings.assign(db,child,transaction,req.book_id)
            db.execute('INSERT INTO moneyon_reward_choices VALUES(?,?,?,?,?,?,?)',(req.payout,child,req.choice,req.amount,req.book_id,transaction,req.key))
        return service.snapshot(row)['state']
    return execute(service,auth,child,operation,True)


class Allowance(Reset):
    amount: int = Field(ge=100, le=10000000, multiple_of=100, strict=True)


@router.post('/children/{child}/allowance')
def allowance(child: str, req: Allowance, auth=Depends(Auth), service=Depends(trials)):
    def operation(row, ctx):
        service.allowance(row, req.amount, req.key)
        return service.snapshot(row)
    return execute(service, auth, child, operation, True)


class DateChange(BaseModel):
    day: date


@router.post('/children/{child}/date')
def advance(child: str, req: DateChange, auth=Depends(Auth), service=Depends(trials)):
    def operation(row, ctx):
        service.advance(row, req.day)
        return service.snapshot(row)
    return execute(service, auth, child, operation, True)


class Approval(Reset):
    cycle_id: str
    approved: Literal[True]
    reward_type: Literal['allowance_bonus', 'savings_interest'] | None = None


@router.post('/children/{child}/approve')
def approve(child: str, req: Approval, auth=Depends(Auth), service=Depends(trials)):
    def operation(row, ctx):
        with service.ledger.db() as db:
            cycle = db.execute('SELECT policy FROM cycles WHERE child=? AND id=?', (child, req.cycle_id)).fetchone()
        import json
        if cycle and json.loads(cycle['policy']).get('dual_rewards'):
            service.ledger.settle_rewards(row['family'], child, req.cycle_id, req.key, service.day(row), req.reward_type)
        else:
            core.banking(ctx).settle_reward_interest(row['family'], child, req.key, req.cycle_id, service.day(row))
        return service.snapshot(row)
    return execute(service, auth, child, operation, True)


@router.post('/children/{child}/claim')
def claim(child: str, req: Reset, auth=Depends(Auth), service=Depends(trials)):
    # "이자 받기": every finished week's waiting interest, once.
    def operation(row, ctx):
        service.claim(row, req.key)
        return service.snapshot(row)
    return execute(service, auth, child, operation, True)


@router.post('/children/{child}/goals')
def goal(child: str, req: core.Goal, auth=Depends(Auth), service=Depends(trials)):
    return execute(service, auth, child, lambda row, ctx: core.goal(child, req, ctx), True)


@router.post('/children/{child}/experiment')
def experiment(child: str, req: core.Experiment, auth=Depends(Auth), service=Depends(trials)):
    def operation(row, ctx):
        snapshot = service.snapshot(row)['state']
        if not snapshot.get('rewards'):
            return core.experiment(child, req, ctx)
        if req.spend > snapshot['wallet']:
            raise ValueError('사용 가능한 돈보다 큰 금액이에요.')
        current = next(c for c in snapshot['cycles'] if not c['ended'])
        from services.moneyon import reward
        left = snapshot['wallet'] - req.spend
        item = next(i for i in snapshot['rewards']['items'] if i['cycle_id'] == current['id'] and i['reward_type'] == 'allowance_bonus')
        bonus = reward(max(0, item['base'] - req.spend), current['policy']['dual_rewards']['allowance_bonus'])
        savings = reward(snapshot['vault'], current['policy']['dual_rewards']['savings_interest'])
        return dict(left=left, eligible=left, interest=bonus, savings_interest=savings, total=left+bonus)
    return execute(service, auth, child, operation)


@router.post('/children/{child}/quiz')
def quiz(child: str, req: core.Quiz, auth=Depends(Auth), service=Depends(trials)):
    return execute(service, auth, child, lambda row, ctx: core.quiz(child, req, ctx), True)


@router.patch('/children/{child}/transactions/{transaction_id}/category')
def category(child: str, transaction_id: str, req: core.CategoryChange, auth=Depends(Auth), service=Depends(trials)):
    return execute(service, auth, child, lambda row, ctx: core.category_change(child, transaction_id, req, ctx), True)
