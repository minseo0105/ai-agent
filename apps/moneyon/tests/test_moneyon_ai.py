"""MONEY:ON AI 기능 테스트(오프라인, 비용 0). 실행: apps/moneyon에서
   ..\\..\\..\\..\\.venv\\Scripts\\python.exe -B -m unittest tests.test_moneyon_ai -v
"""
import asyncio
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

TMP = tempfile.mkdtemp()
os.environ.update(MONEYON_TRIAL_ENABLED='1', MONEYON_TRIAL_DB=f'{TMP}/trial.sqlite3', MONEYON_DB=f'{TMP}/dev.sqlite3',
                  MONEYON_AI_USAGE=f'{TMP}/ai_usage.json')

from fastapi.testclient import TestClient  # noqa: E402

import space_app  # noqa: E402
from services import moneyon_ai as ai  # noqa: E402


def events(body: str):
    out = []
    for block in body.strip().split('\n\n'):
        lines = dict(line.split(': ', 1) for line in block.split('\n') if ': ' in line)
        if 'event' in lines:
            out.append((lines['event'], json.loads(lines['data'])))
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {'MONEYON_AI_ENABLED': '1', 'MONEYON_AI_FAKE': '1', 'MONEYON_DEMO_ENTRY': '1',
                                                'MONEYON_AI_FIRST_TOKEN': '4', 'ANTHROPIC_API_KEY': ''})
        self.env.start()
        ai._person.clear()
        ai._gate['gate'] = None
        ai._client['c'] = None
        try:  # 앱이 지금 쓰는 사용량 파일을 지운다(discover로 함께 돌리면 이 모듈이 두 번 import되어 TMP가 둘이 된다)
            ai.usage_path().unlink()
        except FileNotFoundError:
            pass
        self.client = TestClient(space_app.app)

    def tearDown(self):
        self.env.stop()

    def start(self, demo=False):
        r = self.client.post('/api/moneyon/trial/demo' if demo else '/api/moneyon/trial/start')
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def ask(self, token, feature, body=None):
        r = self.client.post(f'/api/moneyon/trial/ai/{feature}', json=body or {}, headers={'X-Moneyon-Trial': token})
        return r, events(r.text) if r.status_code == 200 else []


class FactsTest(Base):
    def test_goal_simulation_with_interest(self):
        # 잔액 10,000 → 목표 50,000, 매주 5,000 저금, 주 2% 이자(100원 단위 버림, 상한 2,000)
        plan = ai.simulate_goal(10000, 50000, 5000, 200, 2000, 100)
        self.assertEqual(plan['rows'][0], {'주': 1, '저금': 5000, '이자': 300, '잔액': 15300})
        self.assertEqual(plan['rows'][6]['잔액'], 49200)   # 손 계산: 15,300 → 20,700 → … → 49,200
        self.assertEqual(plan['weeks'], 8)
        # 잔액이 크면 이자가 주 수를 줄인다: 40,000에서 매주 1,000 → 이자 없이 10주, 이자 포함 6주
        self.assertEqual(ai.simulate_goal(40000, 50000, 1000, 0)['weeks'], 10)
        self.assertEqual(ai.simulate_goal(40000, 50000, 1000, 200, 2000, 100)['weeks'], 6)
        self.assertFalse(ai.simulate_goal(0, 50000, 0, 200)['reachable'])

    def test_facts_have_no_names_or_notes(self):
        demo = self.start(demo=True)
        state = demo['state']
        book = next(b for b in state['books'] if b['name'] == '자전거')
        name = demo['child']['profile']['name']
        for feature in ai.FEATURES:
            facts = ai.facts_for(feature, state, book['id'], 5000)
            text = json.dumps(facts, ensure_ascii=False)
            self.assertNotIn(name, text)
            self.assertNotIn('자전거', text)          # 통장 이름 안 보냄
            self.assertNotIn('구매', text)            # 쓴 곳 메모 안 보냄
        coach = ai.facts_for('coach', state, book['id'], 5000)
        self.assertEqual((coach['목표 금액'], coach['지금 모은 돈']), (50000, 10000))
        self.assertEqual(coach['주간 저축 이자율(%)'], 2)  # 최신 주기의 저축 이자 2%(옛 주기를 읽으면 0이 되던 버그)
        self.assertEqual(coach['목표까지 주 수(이자 포함)'], 8)
        letter = ai.facts_for('letter', state)
        self.assertEqual(letter['카테고리별 쓴 돈']['간식'], 3000 + 1500 + 2000)

    def test_checks(self):
        facts = {'목표 금액': 50000, '목표까지 주 수(이자 포함)': 7}
        self.assertEqual(ai.check('일주일에 조금씩 모으면 7주 뒤 50,000원이 돼!', facts), '')
        self.assertEqual(ai.check('9주 뒤에 60,000원이 될 거야. 아주 좋아!', facts), 'numbers')
        self.assertEqual(ai.check('목표 5만 원까지 7주면 돼! 아주 좋아', facts), '')      # 만 단위도 값으로 읽는다
        self.assertEqual(ai.check('목표 5만 2,000원까지 7주면 돼! 좋아', facts), 'numbers')
        self.assertEqual(ai.check('이 적금 상품에 가입해 보자! 정말 좋아', facts), 'banned')


class StreamTest(Base):
    def test_fake_stream_thinking_delta_done(self):
        t = self.start(demo=True)['token']
        r, ev = self.ask(t, 'letter')
        kinds = [e for e, _ in ev]
        self.assertEqual(kinds[0], 'thinking')
        self.assertIn('delta', kinds)
        self.assertEqual(ev[-1][0], 'done')
        text = ''.join(d['text'] for e, d in ev if e == 'delta')
        self.assertIn('원', text)
        self.assertEqual(r.headers['content-type'].split(';')[0], 'text/event-stream')

    def test_no_key_uses_prepared_or_rule(self):
        t = self.start(demo=True)['token']
        with mock.patch.dict(os.environ, {'MONEYON_AI_FAKE': '0'}):
            _, ev = self.ask(t, 'parent')
        self.assertEqual(ev[-1], ('done', {'source': 'rule', 'model': None, 'reason': 'no_key'}))
        self.assertIn('대화 팁', ''.join(d['text'] for e, d in ev if e == 'delta'))

    def test_first_token_timeout_falls_back(self):
        class Slow:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            @property
            async def text_stream(self):
                await asyncio.sleep(5)
                yield '늦은 글'

        class FakeClient:
            class messages:
                @staticmethod
                def stream(**kw):
                    return Slow()

        t = self.start(demo=True)['token']
        with mock.patch.dict(os.environ, {'MONEYON_AI_FAKE': '0', 'MONEYON_AI_FIRST_TOKEN': '0.2'}), \
                mock.patch.object(ai, 'async_client', lambda: FakeClient()):
            _, ev = self.ask(t, 'letter')
        self.assertEqual(ev[-1][1]['reason'], 'first_token_timeout')
        self.assertEqual(ev[-1][1]['source'], 'rule')

    def test_slow_connection_counts_toward_first_token(self):
        """응답 시작(__aenter__) 자체가 늦어도 4초 규칙으로 대체된다(처음에는 이 구간이 시간 제한 밖이었다)."""
        class SlowStart:
            async def __aenter__(self):
                await asyncio.sleep(5)
                return self

            async def __aexit__(self, *a):
                return False

        class FakeClient:
            class messages:
                @staticmethod
                def stream(**kw):
                    return SlowStart()

        t = self.start(demo=True)['token']
        with mock.patch.dict(os.environ, {'MONEYON_AI_FAKE': '0', 'MONEYON_AI_FIRST_TOKEN': '0.2'}), \
                mock.patch.object(ai, 'async_client', lambda: FakeClient()):
            _, ev = self.ask(t, 'letter')
        self.assertEqual(ev[-1][1]['reason'], 'first_token_timeout')

    def test_bad_ai_text_is_replaced(self):
        async def bad(feature, facts):
            yield '이 적금 상품에 가입해 봐! 99,999원 보너스야'

        t = self.start(demo=True)['token']
        with mock.patch.object(ai, 'fake_stream', bad):
            _, ev = self.ask(t, 'letter')
        self.assertIn('replace', [e for e, _ in ev])
        self.assertEqual(ev[-1][1]['reason'], 'banned')

    def test_coach_needs_book_and_weekly(self):
        t = self.start(demo=True)['token']
        r, _ = self.ask(t, 'coach', {})
        self.assertEqual(r.status_code, 400)

    def test_switch_off_and_wrong_token(self):
        t = self.start()['token']
        with mock.patch.dict(os.environ, {'MONEYON_AI_FEATURES': 'letter'}):
            self.assertEqual(self.ask(t, 'parent')[0].status_code, 404)
        with mock.patch.dict(os.environ, {'MONEYON_AI_ENABLED': '0'}):
            self.assertEqual(self.client.get('/api/moneyon/trial/ai/config').json()['features'], [])
        self.assertEqual(self.ask('x' * 43, 'letter')[0].status_code, 403)


class GuardTest(Base):
    def test_person_limit(self):
        t = self.start(demo=True)['token']
        for _ in range(3):
            self.assertEqual(self.ask(t, 'letter')[1][-1][1]['source'], 'ai')
        self.assertEqual(self.ask(t, 'letter')[1][-1][1]['reason'], 'person_limit')

    def test_queue_position_shown(self):
        async def run():
            g = ai.Gate(1, 5)
            seen = []

            async def on_wait(p):
                seen.append(p)

            self.assertTrue(await g.acquire(1))
            waiter = asyncio.ensure_future(g.acquire(2, on_wait))
            await asyncio.sleep(0.1)
            self.assertEqual(seen, [1])           # 앞에 1명(지금 쓰는 사람) → 순번 1
            await g.release()
            self.assertTrue(await waiter)
            self.assertFalse(await ai.Gate(0, 0).acquire(0.1))  # 대기열이 꽉 차면 바로 거절
        asyncio.run(run())

    def test_daily_budget(self):
        t = self.start(demo=True)['token']
        ai.add_usage('claude-haiku-5-5', 50_000_000, 0)  # $5 사용
        _, ev = self.ask(t, 'letter')
        self.assertEqual(ev[-1][1]['reason'], 'daily_budget')

    def test_trials_are_isolated(self):
        a, b = self.start(demo=True), self.start(demo=True)
        self.assertNotEqual(a['child']['id'], b['child']['id'])
        r = self.client.get(f"/api/moneyon/trial/children/{a['child']['id']}", headers={'X-Moneyon-Trial': b['token']})
        self.assertEqual(r.status_code, 403)  # 다른 사람 통장은 읽지 못한다
        self.assertEqual(self.client.get(f"/api/moneyon/trial/children/{a['child']['id']}", headers={'X-Moneyon-Trial': a['token']}).status_code, 200)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
