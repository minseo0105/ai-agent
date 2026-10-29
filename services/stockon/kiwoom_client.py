"""키움 REST API — 조회 전용 클라이언트 (docs/STOCKON_PLAN.md 3-6절).

- 이 파일에는 허용 목록(ALLOWED)에 있는 조회 TR만 있다. 주문·계좌 API는 코드에 없다.
  실시간 시세(웹소켓)는 kiwoom_realtime.py가 시세 타입 세 가지(0B·0J·0U)만 받는다(이 클라이언트의 토큰을 메모리로 넘김).
- 공개 함수는 query(api_id, body) 하나. 허용 목록 밖이면 네트워크 호출 전에 예외.
- 키·토큰은 이 객체(수집기 프로세스 메모리)에만 있다. 로그·예외·파일에 남기지 않는다.
- 도메인은 KIWOOM_MODE(mock/real)로만 고른다. 모의 서버는 KRX만. 호출 간격은 TR 종류와 관계없이 전체 1.1초(모의, 초당 1회 이하).
- 토큰은 만료 10분 전(KST 기준 — 컨테이너 시계가 UTC여도)에 다시 받고, 키움이 토큰 무효를 알리면 버리고 한 번 다시 받는다.
"""

import threading
import time
from datetime import datetime, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo

import requests

HOSTS = MappingProxyType({"mock": "https://mockapi.kiwoom.com", "real": "https://api.kiwoom.com"})

# api-id ↔ URL 쌍(키움 공식 스펙 kiwoom_api_spec.json 기준). 이 밖의 조합은 보내지 않는다.
ALLOWED = MappingProxyType({
    "au10001": "/oauth2/token",          # 접근토큰 발급
    "au10002": "/oauth2/revoke",         # 접근토큰 폐기
    "ka20001": "/api/dostk/sect",        # 업종현재가(지수)
    "ka20009": "/api/dostk/sect",        # 업종현재가일별
    "ka20003": "/api/dostk/sect",        # 전업종지수(업종별 등락 순위·상한/하한 수)
    "ka20005": "/api/dostk/chart",       # 업종분봉(지수 장중 5분봉)
    "ka10051": "/api/dostk/sect",        # 업종별투자자순매수
    "ka10027": "/api/dostk/rkinfo",      # 전일대비등락률상위
    "ka10032": "/api/dostk/rkinfo",      # 거래대금상위
    "ka10030": "/api/dostk/rkinfo",      # 당일거래량상위
    "ka90009": "/api/dostk/rkinfo",      # 외국인기관매매상위
    "ka10001": "/api/dostk/stkinfo",     # 주식기본정보
    "ka10095": "/api/dostk/stkinfo",     # 지정종목 정보(여러 종목 | 로 연결)
    "ka10099": "/api/dostk/stkinfo",     # 종목정보 리스트
    "ka10101": "/api/dostk/stkinfo",     # 업종코드 리스트
    "ka10008": "/api/dostk/frgnistt",    # 주식외국인종목별매매동향
    "ka10131": "/api/dostk/frgnistt",    # 기관외국인연속매매현황
})

# 호출 최소 간격(초, 모든 TR 합쳐서). 모의: 초당 1회 이하, 실전: 조회 1초 5회.
MIN_INTERVAL = MappingProxyType({"mock": 1.1, "real": 0.3})
SEOUL = ZoneInfo("Asia/Seoul")
TOKEN_INVALID = {"8005", "http_401"}  # 토큰이 유효하지 않음 → 버리고 다시 발급


class KiwoomError(Exception):
    """code만 담는다(키움 return_code / HTTP 상태 / 내부 사유). 키·토큰·요청 본문은 담지 않는다."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code} {message}".strip())
        self.code, self.message = code, message[:80]


class KiwoomClient:
    def __init__(self, mode: str, appkey: str, secretkey: str, http=requests.post, clock=time.monotonic, sleep=time.sleep,
                 now=None):
        if mode not in HOSTS:
            raise KiwoomError("bad_mode", "KIWOOM_MODE는 mock 또는 real")
        if not appkey or not secretkey:
            raise KiwoomError("not_configured", "키움 App Key/Secret 없음")
        self.mode, self._appkey, self._secret = mode, appkey, secretkey
        self._http, self._clock, self._sleep = http, clock, sleep
        self._now = now or (lambda: datetime.now(SEOUL).replace(tzinfo=None))  # expires_dt가 KST라 KST로 비교
        self._token, self._token_exp = None, None
        self._last = -1e9
        self._lock = threading.Lock()       # 토큰 발급
        self._call_lock = threading.Lock()  # 호출 하나씩(수집 루프·뉴스 속 숨은 종목 스레드가 같이 써도 간격 유지)
        self.token_issued = 0               # 토큰 발급 횟수(상태 확인용)

    def __repr__(self):  # 실수로 로그에 찍혀도 키가 나가지 않게
        return f"KiwoomClient(mode={self.mode})"

    # ---- 내부 ----
    def _post(self, api_id: str, body: dict, headers: dict) -> tuple[dict, dict]:
        path = ALLOWED.get(api_id)
        if path is None:
            raise KiwoomError("not_allowed", f"허용 목록 밖 TR: {api_id[:12]}")
        with self._call_lock:
            wait = MIN_INTERVAL[self.mode] - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = self._clock()
            try:
                r = self._http(HOSTS[self.mode] + path, json=body, timeout=15,
                               headers={"Content-Type": "application/json;charset=UTF-8", "api-id": api_id, **headers})
            except requests.RequestException as e:
                raise KiwoomError("network", type(e).__name__)
        try:
            data = r.json()
        except ValueError:
            raise KiwoomError(f"http_{r.status_code}")
        code = data.get("return_code")
        if r.status_code == 429 or str(code) == "5":
            raise KiwoomError("rate_limited", "허용된 요청 개수 초과")
        if r.status_code != 200 or (code not in (None, 0, "0")):
            raise KiwoomError(str(code if code not in (None, "") else f"http_{r.status_code}"), str(data.get("return_msg") or ""))
        return data, dict(r.headers or {})

    def _ensure_token(self):
        with self._lock:
            if self._token and self._token_exp and self._now() < self._token_exp - timedelta(minutes=10):
                return self._token
            data, _ = self._post("au10001", {"grant_type": "client_credentials", "appkey": self._appkey,
                                             "secretkey": self._secret}, {})
            token = data.get("token")
            if not token:
                raise KiwoomError("no_token")
            try:
                exp = datetime.strptime(str(data.get("expires_dt")), "%Y%m%d%H%M%S")
            except ValueError:
                exp = self._now() + timedelta(hours=23)
            self._token, self._token_exp = token, exp
            self.token_issued += 1
            return token

    # ---- 공개 ----
    def query(self, api_id: str, body: dict) -> dict:
        """허용 목록의 조회 TR 하나를 부른다. 토큰은 필요할 때 발급(24시간)."""
        if api_id not in ALLOWED or api_id.startswith("au"):
            raise KiwoomError("not_allowed", f"허용 목록 밖 TR: {api_id[:12]}")
        for attempt in range(2):
            token = self._ensure_token()
            try:
                data, _ = self._post(api_id, body, {"authorization": f"Bearer {token}"})
                return data
            except KiwoomError as e:
                if e.code not in TOKEN_INVALID or attempt:
                    raise
                with self._lock:
                    self._token = self._token_exp = None  # 무효 토큰은 버리고 한 번만 다시 받는다

    def access_token(self) -> str:
        """실시간 시세 웹소켓 LOGIN용. 같은 프로세스 메모리 안에서만 넘긴다(로그·파일에 남기지 않음)."""
        return self._ensure_token()

    def check_token(self) -> str:
        """토큰 발급만 해 본다(시세 조회 없음). 성공하면 'ok', 실패하면 KiwoomError(code)."""
        self._ensure_token()
        return "ok"

    def revoke(self) -> None:
        """종료할 때 토큰을 폐기한다. 실패해도 조용히 넘어간다(24시간 뒤 자동 만료)."""
        if not self._token:
            return
        try:
            self._post("au10002", {"appkey": self._appkey, "secretkey": self._secret, "token": self._token}, {})
        except KiwoomError:
            pass
        self._token = self._token_exp = None


def num(v, cast=float):
    """키움 숫자 문자열: 앞의 +/- 는 전일 대비 방향 표시다. '+156600' → 156600."""
    if v in (None, ""):
        return None
    try:
        return cast(str(v).replace(",", "").strip())
    except ValueError:
        return None


def price(v):
    """가격은 부호를 떼고 절대값으로."""
    n = num(v)
    return abs(n) if n is not None else None
