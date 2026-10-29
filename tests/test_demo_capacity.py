"""11/17 시연(100명) 용량 설정: AI LAB 대화 문지기·스레드 수. docs/DEMO_READINESS.md

  python -m unittest tests.test_demo_capacity -v
"""
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from fastapi.testclient import TestClient

import api.main as main


def answers(body: str):
    out, event = [], None
    for line in body.splitlines():
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: ") and event == "answer":
            out.append(json.loads(line[6:]))
    return out


class ChatGateTest(unittest.TestCase):
    def setUp(self):
        self.slots = threading.BoundedSemaphore(2)
        self.waiting = [0]
        for p in (mock.patch.object(main, "_chat_slots", self.slots), mock.patch.object(main, "_chat_waiting", self.waiting),
                  mock.patch.object(main, "CHAT_QUEUE", 2), mock.patch.object(main, "CHAT_WAIT", 0.3)):
            p.start()
            self.addCleanup(p.stop)

    def test_busy_answer_without_ai_when_full(self):
        lock, state = threading.Lock(), {"now": 0, "max": 0, "calls": 0}

        def slow_agent(messages, provider, mode):
            with lock:
                state["now"] += 1
                state["calls"] += 1
                state["max"] = max(state["max"], state["now"])
            time.sleep(0.6)
            with lock:
                state["now"] -= 1
            yield {"type": "answer", "text": "ok"}

        body = {"messages": [{"role": "user", "content": "안녕"}]}
        with mock.patch.object(main, "run_agent", side_effect=slow_agent), TestClient(main.app) as client:
            with ThreadPoolExecutor(max_workers=10) as people:
                results = list(people.map(lambda i: answers(client.post("/api/chat", json=body).text)[0], range(10)))
        busy = [r for r in results if r.get("busy")]
        self.assertLessEqual(state["max"], 2)                 # 동시 상한
        self.assertEqual(state["calls"], 10 - len(busy))      # 넘친 사람은 AI를 부르지 않는다
        self.assertGreaterEqual(len(busy), 1)
        self.assertTrue(all(r["text"] == main.CHAT_BUSY for r in busy))
        self.assertEqual(self.waiting[0], 0)
        self.assertTrue(self.slots.acquire(blocking=False) and self.slots.acquire(blocking=False))  # 자리가 모두 돌아옴

    def test_slot_released_when_agent_fails(self):
        def broken(*a):
            raise RuntimeError("boom")
            yield  # pragma: no cover

        with mock.patch.object(main, "run_agent", side_effect=broken), TestClient(main.app, raise_server_exceptions=False) as client:
            for _ in range(4):
                client.post("/api/chat", json={"messages": [{"role": "user", "content": "x"}]})
        self.assertTrue(self.slots.acquire(blocking=False) and self.slots.acquire(blocking=False))


class ThreadLimitTest(unittest.TestCase):
    def test_threadpool_raised_for_100_people(self):
        import anyio

        with TestClient(main.app) as client:
            total = client.portal.call(lambda: anyio.to_thread.current_default_thread_limiter().total_tokens)
        self.assertEqual(total, main.THREADS)
        self.assertGreaterEqual(main.THREADS, 100)


if __name__ == "__main__":
    unittest.main()
