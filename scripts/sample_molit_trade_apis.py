"""국토교통부 실거래 API 샘플 조사(읽기 전용). DB·파일 쓰기 없음, 집계만 출력한다.

키는 환경변수 PUBLIC_DATA_API_KEY 에서만 읽고(없으면 .streamlit/secrets.toml [realestate]),
출력·로그·예외 문구 어디에도 싣지 않는다. 원자료 행은 저장하지 않고 필드별 채움률만 낸다.

  PUBLIC_DATA_API_KEY=... python scripts/sample_molit_trade_apis.py --lawd 11710 --ymd 202610 --out report.json
  python scripts/sample_molit_trade_apis.py --check-config      # 키 존재 여부만(값 출력 안 함)
"""
import argparse, json, os, re, sys, xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "https://apis.data.go.kr/1613000/"
APIS = {  # 앞 4개는 현재 코드(TRADE_APIS)와 동일. 마지막은 분양권·입주권 후보로 응답 필드를 확인한다.
    "아파트": "RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "연립·다세대": "RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    "단독·다가구": "RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade",
    "오피스텔": "RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade",
    "분양권전매(후보)": "RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade",
}
KEY_RE = re.compile(r"(?i)(servicekey|api_?key)=[^&\s'\"]+")


def load_key():
    key = os.environ.get("PUBLIC_DATA_API_KEY")
    if not key:
        try:
            from services.realestate_monitor import _secret
            key = _secret("PUBLIC_DATA_API_KEY")
        except Exception:
            key = None
    return unquote(key) if key else None


def mask(text, key=None):
    text = KEY_RE.sub(r"\1=***", str(text))
    return text.replace(key, "***") if key else text


def summarize(xml_text):
    """한 응답 → {result_code, total, items, field_fill{필드:채움률}, 값 분포}. 행 자체는 반환하지 않는다."""
    root = ET.fromstring(xml_text)
    code = (root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or "").strip()
    msg = (root.findtext(".//resultMsg") or root.findtext(".//errMsg") or "").strip()
    items = root.findall(".//item")
    fields = Counter(); filled = Counter(); dist = {}
    for it in items:
        for child in it:
            tag = child.tag; text = (child.text or "").strip()
            fields[tag] += 1
            if text and text != "-":
                filled[tag] += 1
            if tag in ("cdealType", "dealingGbn", "ownershipGbn", "buyerGbn", "slerGbn", "houseType", "rgstDate"):
                dist.setdefault(tag, Counter())[("있음" if tag == "rgstDate" and text else text) or "(빈값)"] += 1
    n = len(items)
    return {"result_code": code, "result_msg": msg, "total_count": (root.findtext(".//totalCount") or "").strip(),
            "items": n, "fields": sorted(fields),
            "field_fill_rate": {t: round(filled[t] / n, 3) for t in sorted(fields)} if n else {},
            "value_distribution": {t: dict(c.most_common(8)) for t, c in dist.items()}}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lawd", action="append", help="시군구 코드 5자리(여러 번 지정 가능)")
    ap.add_argument("--ymd", default="202610")
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--out")
    ap.add_argument("--check-config", action="store_true")
    args = ap.parse_args(argv)
    key = load_key()
    if args.check_config:
        print(json.dumps({"public_data_key_present": bool(key)}))
        return 0
    if not key:
        print("PUBLIC_DATA_API_KEY 가 없습니다.", file=sys.stderr)
        return 2
    import requests
    report = {"ymd": args.ymd, "db_write": False, "results": {}}
    for lawd in args.lawd or ["11710"]:
        for name, path in APIS.items():
            try:
                r = requests.get(BASE + path, params={"serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": args.ymd,
                                                      "pageNo": 1, "numOfRows": args.rows}, timeout=30)
                entry = {"http": r.status_code, **summarize(r.text)} if r.ok else {"http": r.status_code}
            except Exception as exc:  # 요청 URL(키 포함)이 예외 문구에 섞일 수 있어 가린다
                entry = {"error": mask(exc, key)[:200]}
            report["results"][f"{lawd}/{name}"] = entry
    text = json.dumps(report, ensure_ascii=False, indent=2)
    assert key not in text
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
