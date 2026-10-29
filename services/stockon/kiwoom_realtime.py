"""STOCK:ON 키움 실시간 시세(웹소켓) — 조회 시세만. 수집기(stockon-collector) 안에서만 돈다.

- 받는 타입은 TYPES 세 가지뿐이다: 0B 주식체결(종목 현재가), 0J 업종지수(코스피·코스닥), 0U 업종등락(상승·하락·상한·하한 수).
  주문체결·잔고·조건검색 같은 다른 타입은 등록 메시지를 만들기 전에 막는다(register_message).
- 주소는 KIWOOM_MODE로만 고른다(모의/실전 웹소켓 하나씩). 토큰은 KiwoomClient가 발급한 것을 메모리로만 받는다.
- 연결 → LOGIN → REG. 서버의 PING은 그대로 돌려보낸다. 끊기면 1·2·5·10·30초 간격으로 다시 연결한다.
- 받은 값은 메모리(state)에 두고, 수집기가 5초마다 market_live.json으로 쓴다(화면은 이 파일만 읽는다 → 사람 수와 무관).
- 세션당 실시간 등록 한도(약 200종목) 안에서 MAX_ITEMS까지만 등록한다.
"""

import asyncio
import json
import logging
import threading
import time
from datetime import datetime

from services.stockon.kiwoom_client import num, price
from services.stockon.public_data import KST

log = logging.getLogger("stockon.realtime")

WS_URLS = {"mock": "wss://mockapi.kiwoom.com:10000/api/dostk/websocket", "real": "wss://api.kiwoom.com:10000/api/dostk/websocket"}
TYPES = {"0B": "주식체결", "0J": "업종지수", "0U": "업종등락"}  # 조회 시세만(주문체결·잔고 등은 없음)
INDEX_CODES = {"001": "KOSPI", "101": "KOSDAQ"}
MAX_ITEMS = 190            # 세션당 등록 한도 200 안에서(지수 2 + 종목)
BACKOFF = (1, 2, 5, 10, 30)
RECV_TIMEOUT = 30          # 이 시간 동안 아무 메시지(PING 포함)도 없으면 끊고 다시 연결


def register_message(stock_codes: list[str], grp: str = "1") -> dict:
    """REG 메시지. 지수 2개(0J·0U) + 종목(0B)만. 허용 타입 밖이면 만들지 않는다."""
    data = [{"item": list(INDEX_CODES), "type": ["0J", "0U"]}]
    stocks = [c for c in dict.fromkeys(stock_codes) if c and c.isalnum()][:MAX_ITEMS - len(INDEX_CODES)]
    if stocks:
        data.append({"item": stocks, "type": ["0B"]})
    for d in data:
        if set(d["type"]) - set(TYPES):
            raise ValueError("허용 밖 실시간 타입")
    return {"trnm": "REG", "grp_no": grp, "refresh": "1", "data": data}


class RealtimeFeed:
    """웹소켓 연결 하나를 스레드에서 유지한다. snapshot()으로 지금 값을 읽는다."""

    def __init__(self, mode: str, token_fn, connect=None, clock=time.time):
        if mode not in WS_URLS:
            raise ValueError("bad mode")
        self.url = WS_URLS[mode]
        self._token_fn = token_fn
        self._connect = connect
        self._clock = clock
        self._lock = threading.Lock()
        self._items: list[str] = []
        self._want_reconnect = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.state = self._empty()

    def _empty(self) -> dict:
        return {"indices": {}, "breadth": {}, "stocks": {}, "connected": False, "last_msg_ts": None, "connected_ts": None,
                "reconnects": 0, "error": None, "day": datetime.now(KST).strftime("%Y%m%d")}

    # ---- 등록 종목 ----
    def set_items(self, codes: list[str]) -> bool:
        """등록할 종목이 바뀌면 다시 연결해서 새로 등록한다. 바뀌었으면 True."""
        codes = [c for c in dict.fromkeys(codes) if c][:MAX_ITEMS - len(INDEX_CODES)]
        with self._lock:
            if codes == self._items:
                return False
            self._items = codes
            self._want_reconnect = True
            return True

    # ---- 메시지 처리 ----
    def handle(self, msg: dict) -> dict | None:
        """메시지 하나. PING이면 돌려보낼 메시지를, 아니면 None. REAL이면 state를 갱신한다."""
        tr = msg.get("trnm")
        if tr == "PING":
            return msg
        if tr in ("LOGIN", "REG") and str(msg.get("return_code")) not in ("0", "None"):
            raise ConnectionError(f"{tr} {msg.get('return_code')}")
        if tr != "REAL":
            return None
        now = self._clock()
        with self._lock:
            day = datetime.now(KST).strftime("%Y%m%d")
            if self.state["day"] != day:  # 날짜가 바뀌면 어제 값을 지운다
                self.state.update(indices={}, breadth={}, stocks={}, day=day)
            self.state["last_msg_ts"] = now
            for d in msg.get("data") or []:
                kind, item, v = d.get("type"), str(d.get("item") or ""), d.get("values") or {}
                if kind not in TYPES:
                    continue
                t = str(v.get("20") or "")
                if kind == "0B":
                    self.state["stocks"][item] = {"close": price(v.get("10")), "change": num(v.get("11")), "rate": num(v.get("12")),
                                                  "t": t, "ts": now}
                elif kind in ("0J", "0U") and item in INDEX_CODES:
                    market = INDEX_CODES[item]
                    if v.get("10") not in (None, ""):
                        self.state["indices"][market] = {"close": price(v.get("10")), "change": num(v.get("11")),
                                                         "rate": num(v.get("12")), "t": t, "ts": now}
                    if kind == "0U":
                        self.state["breadth"][market] = {k: int(num(v.get(f)) or 0) for k, f in
                                                         (("upper", "251"), ("up", "252"), ("flat", "253"), ("lower", "254"), ("down", "255"))}
                        self.state["breadth"][market]["t"] = t
        return None

    def snapshot(self) -> dict:
        with self._lock:
            s = self.state
            return {**{k: v for k, v in s.items() if k not in ("indices", "breadth", "stocks")},
                    "indices": dict(s["indices"]), "breadth": dict(s["breadth"]), "stocks": dict(s["stocks"]), "items": len(self._items)}

    # ---- 연결 ----
    async def _session(self):
        connect = self._connect
        if connect is None:
            import websockets  # 수집기 이미지에만 필요
            connect = websockets.connect
        with self._lock:
            items, self._want_reconnect = list(self._items), False
        async with connect(self.url, ping_interval=None, open_timeout=10, close_timeout=3) as ws:
            await ws.send(json.dumps({"trnm": "LOGIN", "token": self._token_fn()}))
            self.handle(json.loads(await asyncio.wait_for(ws.recv(), 10)))
            await ws.send(json.dumps(register_message(items)))
            with self._lock:
                self.state.update(connected=True, connected_ts=self._clock(), error=None)
            while not self._stop.is_set():
                if self._want_reconnect:
                    return  # 등록 종목이 바뀌었다 → 새로 연결해서 등록
                try:
                    raw = await asyncio.wait_for(ws.recv(), 1)
                except asyncio.TimeoutError:
                    last = self.state["last_msg_ts"] or self.state["connected_ts"] or self._clock()
                    if self._clock() - last > RECV_TIMEOUT:
                        raise ConnectionError("no_message")
                    continue
                reply = self.handle(json.loads(raw))
                if reply is not None:
                    await ws.send(json.dumps(reply))

    async def _run(self):
        fails = 0
        while not self._stop.is_set():
            try:
                await self._session()
                fails = 0
            except Exception as e:  # 끊김·로그인 실패·타임아웃 → 기다렸다가 다시
                with self._lock:
                    self.state.update(connected=False, error=type(e).__name__)
                    self.state["reconnects"] += 1
                log.warning("kiwoom realtime disconnected: %s", type(e).__name__)
                wait = BACKOFF[min(fails, len(BACKOFF) - 1)]
                fails += 1
                await asyncio.sleep(0)  # 기다림이 0이어도 다른 작업에 차례를 넘긴다
                for _ in range(wait * 10):
                    if self._stop.is_set():
                        break
                    await asyncio.sleep(0.1)
            finally:
                with self._lock:
                    self.state["connected"] = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=lambda: asyncio.run(self._run()), name="kiwoom-realtime", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())
