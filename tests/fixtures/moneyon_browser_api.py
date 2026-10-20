"""Loopback-only browser fixture. Never imported by api.main or deployed."""
import os
from datetime import date
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from api import moneyon
from api import moneyon_trial
from services.moneyon import Ledger
from services.moneyon_demo import DemoWorkspaces

if not os.environ.get('MONEYON_TEST_DB'):
    raise RuntimeError('An explicit disposable MONEYON_TEST_DB is required.')
app = FastAPI()
app.include_router(moneyon.router)
app.include_router(moneyon_trial.router)
os.environ['MONEYON_TRIAL_ENABLED'] = '1'
os.environ['MONEYON_TRIAL_DB'] = os.environ['MONEYON_TEST_DB'] + '.trial.sqlite3'
db = Ledger(os.environ['MONEYON_TEST_DB'])
app.dependency_overrides[moneyon.ledger] = lambda: db
os.environ['MONEYON_DEMO'] = '1'


def test_identity(request: Request):
    demo = request.headers.get('x-moneyon-demo')
    try:
        return DemoWorkspaces(db).resolve('browser-test-family', demo) if demo else 'browser-test-family'
    except PermissionError as e:
        raise HTTPException(403, str(e))


app.dependency_overrides[moneyon.identity] = test_identity
clock = {'today': date(2026, 10, 12)}
moneyon.today = lambda: clock['today']


class Clock(BaseModel):
    day: date


@app.post('/__test__/clock')
def advance(req: Clock):
    clock['today'] = req.day
    return {'ok': True}


@app.get('/__test__/ready')
def ready():
    return {'ok': True}
