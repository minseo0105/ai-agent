"""뉴스 속 숨은 종목 — 기업 연관성 검증 오프라인 테스트. 외부 API·AI를 부르지 않는다.

고정 사례(tests/fixtures/stockon_verify_cases.json): 2026-10-30 서버 복사본에서 실제 기사·근거 자료·검증 AI 답을 기록한 것.
코드 대조(근거 문장·회사 이름·사건 연결·기준 시각)와 분류는 여기서 다시 돌린다.

실행: python -B -m unittest tests.test_stockon_verify -v
"""

import io
import json
import time
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from services.stockon import lifemap, store, verify
from services.stockon.public_data import KST
from tests.test_stockon_lifemap import LifemapBase, STOCKS

CASES = json.loads((Path(__file__).parent / "fixtures" / "stockon_verify_cases.json").read_text(encoding="utf-8"))
MORE = {
    "047810": {"name": "한국항공우주", "market": "KOSPI", "close": 1, "rate": 0.1, "cap": 1e13},
    "003490": {"name": "대한항공", "market": "KOSPI", "close": 1, "rate": -0.5, "cap": 1e13},
    "020560": {"name": "아시아나항공", "market": "KOSPI", "close": 1, "rate": -0.3, "cap": 1e12},
    "180640": {"name": "한진칼", "market": "KOSPI", "close": 1, "rate": 0.2, "cap": 1e12},
    "259960": {"name": "크래프톤", "market": "KOSPI", "close": 1, "rate": 1.0, "cap": 1e13},
    "251270": {"name": "넷마블", "market": "KOSPI", "close": 1, "rate": 0.4, "cap": 1e12},
    "263750": {"name": "펄어비스", "market": "KOSDAQ", "close": 1, "rate": -1.0, "cap": 1e12},
    "105560": {"name": "KB금융", "market": "KOSPI", "close": 1, "rate": 0.0, "cap": 3e13},
    "018260": {"name": "삼성에스디에스", "market": "KOSPI", "close": 1, "rate": 0.0, "cap": 1e13},
}
REF = datetime(2026, 10, 30, 17, 0, tzinfo=KST)


def _replay(case: dict):
    """기록한 근거 자료로 Corpus를 다시 만든다(번호·시각 그대로)."""
    corpus = verify.Corpus(datetime.fromisoformat(case["ref"]), case["checked"])
    corpus.items = case["corpus"]
    corpus.after_ref = case["after_ref"]
    return corpus, [tuple(p) for p in case["pre_parties"]], case["article_text"]


def on_map(m: dict) -> list[str]:
    """지도(동그라미)에 올라가는 회사: 직접 당사자·검증된 간접 영향(검증 전이면 예전처럼 모두)."""
    return [c["name"] for st in m["stages"] for c in st["companies"] if c.get("tier", "indirect") in ("party", "indirect")]


class VerifyBase(LifemapBase):
    def setUp(self):
        super().setUp()
        store.write("stocks", {"as_of": "20261030", "stocks": {**STOCKS, **MORE}})
        lifemap._dir_cache.update(mtime=None)
        p = mock.patch.dict("os.environ", {"LIFEMAP_VERIFY": "1"})
        p.start()
        self.patches.append(p)

    def run_case(self, key: str) -> tuple[dict, dict]:
        case = CASES[key]
        with mock.patch.object(verify, "collect", return_value=_replay(case)), \
                mock.patch.object(verify, "ask", return_value=case["raw"]):
            m = verify.verify_map(case["topic"], case["old_map"], case["context"], datetime.fromisoformat(case["ref"]))
        return case, m


class FixtureCasesTest(VerifyBase):
    """6단계 고정 사례: 지금 방식 대비 지도에 올라가는 회사·오탐."""

    def test_incheon_airport_ticketing_outage(self):
        case, m = self.run_case("airport")
        self.assertEqual(on_map(case["old_map"]), ["한국항공우주", "대한항공", "아시아나항공", "한진칼"])  # 지금 방식: 4곳
        self.assertEqual(on_map(m), [])  # 공급사가 공시·보도로 확인되지 않음 → 지도에 0곳
        self.assertEqual(m["verify"]["listed"], 0)  # '검증된 국내 상장기업 없음'
        self.assertEqual([(p["name"], p["kind"]) for p in m["parties"]], [("인천국제공항공사", "국내 비상장")])  # '인천공항'과 합침
        ref_only = {c["name"]: c for st in m["stages"] for c in st["companies"] if c["tier"] == "industry"}
        self.assertEqual(set(ref_only), {"한국항공우주", "대한항공", "아시아나항공"})  # 항공사는 업종 참고만
        self.assertEqual(ref_only["대한항공"]["note"], "보도상 영향 없음")  # '국적기는 정상 수속' 기사는 연결 근거가 아니다
        self.assertTrue(all(c["direction"] == "unk" for c in ref_only.values()))
        self.assertEqual([(d["name"], d["why"]) for d in m["verify"]["dropped"]], [("한진칼", "기사에 이름 없음")])
        self.assertTrue(m["interpretation"])  # 근거 없는 회사를 말하는 해석 문장은 빠지고, 다 빠지면 안내 한 줄
        for line in m["interpretation"]:
            self.assertFalse(any(n in line for n in ("한국항공우주", "대한항공", "아시아나항공", "한진칼")), line)

    def test_call_of_duty_video_controversy(self):
        case, m = self.run_case("cod")
        self.assertEqual(on_map(case["old_map"]), ["크래프톤", "넷마블", "펄어비스"])  # 지금 방식: 3곳
        self.assertEqual(on_map(m), [])
        self.assertEqual([(p["name"], p["kind"]) for p in m["parties"]], [("액티비전", "해외")])
        self.assertEqual({c["name"] for st in m["stages"] for c in st["companies"]}, {"크래프톤", "넷마블"})  # 업종 참고만
        self.assertEqual([d["name"] for d in m["verify"]["dropped"]], ["펄어비스"])  # '규제 대상' 주장, 근거 없음

    def test_issue_without_verified_company_is_marked_and_logged(self):
        case = CASES["airport"]
        t = {**case["topic"], "_context": case["context"], "articles": [{"url": "u1", "title": "x", "rep": True}]}
        with mock.patch.object(lifemap, "interpret", return_value=json.loads(json.dumps(case["old_map"]))), \
                mock.patch.object(verify, "collect", return_value=_replay(case)), \
                mock.patch.object(verify, "ask", return_value=case["raw"]), \
                mock.patch.object(lifemap, "ensure_intros", return_value=0):
            done = lifemap._finish(t, self.basis())
        self.assertTrue(done["no_verified"])
        log = store.read("lifemap_verify_log")
        self.assertEqual(log[-1]["dropped"][0]["name"], "한진칼")  # 근거 부족은 로그에만
        store.write("lifemap", {"basis": {"key": self.basis()["key"]}, "topics": [done]})
        view = lifemap.overview()["topics"][0]["map"]
        self.assertNotIn("dropped", view["verify"])  # 화면에는 내보내지 않는다
        self.assertEqual(view["verify"]["listed"], 0)


def _item(n, kind, title, text, press="연합뉴스", hours=2, **extra):
    return {"n": n, "kind": kind, "title": title, "text": text, "url": f"https://x/{n}", "press": press,
            "pub": (REF - timedelta(hours=hours)).isoformat(), "checked": REF.isoformat(), **extra}


def _corpus(items):
    c = verify.Corpus(REF, REF.isoformat())
    c.items = items
    return c


def _claim(name, relation, ev, impact="영향 있음", path="", direction="불확실"):
    return {"name": name, "relation": relation, "evidence": [{"n": n, "quote": q} for n, q in ev], "impact": impact, "path": path,
            "direction": direction}


TOPIC = {"name": "인천공항 발권 장애", "query": "인천공항 체크인 발권 장애", "title": "인천공항 발권 시스템 먹통"}
ART = "인천공항 체크인 발권 시스템 장애 인천국제공항공사 측은 복구 중"


def _map(*companies):
    return {"stages": [{"key": "p0", "label": "시스템 복구", "detail": "", "companies": [
        {"code": code, "name": MORE.get(code, STOCKS.get(code))["name"], "relevance": "중", "reason": "r", "direction": "pos",
         "relation": rel, "hop": 1, "party": False} for code, rel in companies]}]}


class RulesTest(VerifyBase):
    def classify(self, m, items, raw, pre=(("인천국제공항공사", ""),), text=ART):
        return verify.classify(TOPIC, m, _corpus(items), raw, list(pre), text)

    def test_fabricated_or_untied_quote_is_not_evidence(self):
        items = [_item(1, "news", "삼성SDS, 인천공항 발권 시스템 구축", "삼성SDS가 인천공항 체크인 발권 시스템을 구축했다"),
                 _item(2, "news", "삼성SDS 클라우드 사업 확대", "삼성SDS가 공공 클라우드 사업을 늘린다")]
        m = _map(("018260", "공급사"))
        made_up = {"parties": [], "companies": [_claim("삼성에스디에스", "공급망", [(1, "삼성SDS가 인천공항 발권 시스템을 운영·보수한다고 밝혔다")])]}
        out = self.classify(m, items, made_up)
        self.assertEqual(out["stages"], [])  # 자료에 없는 문장 → 근거 부족(공급사 주장이라 업종 참고도 아님)
        self.assertEqual(out["verify"]["dropped"][0]["why"], "근거 문장이 자료에 없음")
        untied = {"parties": [], "companies": [_claim("삼성에스디에스", "공급망", [(2, "삼성SDS가 공공 클라우드 사업을 늘린다")])]}
        self.assertEqual(self.classify(m, items, untied)["stages"], [])  # 문장은 있지만 이 사건 이야기가 아님
        real = {"parties": [], "companies": [_claim("삼성에스디에스", "공급망", [(1, "삼성SDS가 인천공항 체크인 발권 시스템을 구축했다")],
                                                     path="발권 시스템을 구축해 복구 책임이 생길 수 있다", direction="부정")]}
        c = self.classify(m, items, real)["stages"][0]["companies"][0]
        self.assertEqual((c["tier"], c["grade"], c["rel_kind"], c["direction"]), ("indirect", "단일 보도", "공급망", "neg"))
        self.assertEqual(c["sources"][0]["kind"], "뉴스")
        self.assertEqual(set(c["sources"][0]), {"kind", "title", "url", "press", "pub", "checked", "quote"})

    def test_grades_dart_confirmed_two_presses_reported(self):
        items = [_item(1, "news", "삼성SDS 인천공항 발권 시스템 공급", "삼성SDS가 인천공항 발권 시스템을 공급했다"),
                 _item(2, "news", "인천공항 발권 장애, 삼성SDS 시스템", "인천공항 발권 장애는 삼성SDS 시스템에서", press="SBS"),
                 _item(3, "dart", "삼성에스디에스 단일판매ㆍ공급계약체결", "계약상대 인천국제공항공사 발권 시스템 구축", press="DART 전자공시",
                       filer="018260")]
        m = _map(("018260", "공급사"))

        def grade(ev):
            raw = {"parties": [], "companies": [_claim("삼성에스디에스", "공급망", ev)]}
            return self.classify(m, items, raw)["stages"][0]["companies"][0]["grade"]
        self.assertEqual(grade([(1, "삼성SDS가 인천공항 발권 시스템을 공급했다")]), "단일 보도")
        self.assertEqual(grade([(1, "삼성SDS가 인천공항 발권 시스템을 공급했다"), (2, "인천공항 발권 장애는 삼성SDS 시스템에서")]), "보도 확인")
        self.assertEqual(grade([(3, "계약상대 인천국제공항공사 발권 시스템 구축")]), "확인됨")  # 공시는 그 회사가 낸 것

    def test_direction_needs_path_and_no_impact_goes_to_industry(self):
        items = [_item(1, "news", "인천공항 발권 장애에 대한항공 수속 지연", "인천공항 발권 장애로 대한항공 수속이 지연됐다"),
                 _item(2, "news", "인천공항 발권 장애, 대한항공은 정상 수속", "인천공항 발권 장애에도 대한항공은 정상적으로 수속했다")]
        m = _map(("003490", "경쟁사"))
        ev = [(1, "인천공항 발권 장애로 대한항공 수속이 지연됐다")]
        no_path = self.classify(m, items, {"parties": [], "companies": [_claim("대한항공", "사업", ev, direction="부정")]})
        self.assertEqual(no_path["stages"][0]["companies"][0]["direction"], "unk")  # 경로 설명이 없으면 방향 불확실
        banned = self.classify(m, items, {"parties": [], "companies": [_claim("대한항공", "사업", ev, path="경쟁사 수혜", direction="긍정")]})
        self.assertEqual(banned["stages"][0]["companies"][0]["direction"], "unk")
        none = self.classify(m, items, {"parties": [], "companies": [
            _claim("대한항공", "사업", [(2, "인천공항 발권 장애에도 대한항공은 정상적으로 수속했다")], impact="영향 없음", path="정상 수속", direction="중립")]})
        c = none["stages"][0]["companies"][0]
        self.assertEqual((c["tier"], c["note"], c["direction"]), ("industry", "보도상 영향 없음", "unk"))

    def test_party_alias_parent_needs_source_and_unlisted_marked(self):
        text = "국민은행 전산 장애로 모바일 뱅킹 먹통"
        m = {"stages": []}
        out = verify.classify({"name": "국민은행 전산 장애", "query": "국민은행 전산 장애"}, m,
                              _corpus([_item(1, "rss", "국민은행 전산 장애", text)]), {"parties": [{"name": "국민은행", "kind": "국내 비상장"}],
                                                                                      "companies": []}, [], text)
        party = out["stages"][0]["companies"][0]
        self.assertEqual((party["name"], party["tier"], party["grade"], party["rel_kind"]), ("KB금융", "party", "확인됨", "지분"))
        self.assertIn("100% 자회사", party["sources"][0]["title"])
        self.assertIn({"name": "국민은행", "kind": "국내 비상장", "note": "KB금융 자회사"}, out["parties"])
        # 기사에 나오지 않은 이름은 AI가 당사자라 해도 넣지 않는다
        out = verify.classify(TOPIC, {"stages": []}, _corpus([]), {"parties": [{"name": "마이크로소프트", "kind": "해외"}], "companies": []}, [], ART)
        self.assertEqual(out["parties"], [])
        # 정부·언론은 당사자 회사가 아니고, 같은 기관의 줄임말은 하나로
        text = "인천국제공항공사(인천공항공사)는 국토교통부와 함께 에어링크 장애를 조사했다고 뉴욕타임스가 전했다"
        _, others = verify.find_parties([("인천공항공사", ""), ("인천국제공항공사", ""), ("국토교통부", "국내 비상장"),
                                         ("뉴욕타임스", "해외"), ("에어링크", "해외")], text, {}, {})
        self.assertEqual([o["name"] for o in others], ["인천국제공항공사", "에어링크"])

    def test_ai_found_supplier_is_added_only_when_verified(self):
        items = [_item(1, "news", "인천공항 발권 시스템, 삼성SDS가 운영", "인천공항 발권 시스템은 삼성SDS가 운영한다")]
        raw = {"parties": [], "companies": [_claim("삼성에스디에스", "공급망", [(1, "인천공항 발권 시스템은 삼성SDS가 운영한다")], path="시스템 운영사로 복구를 맡을 수 있다",
                                                   direction="중립"),
                                            _claim("KT", "공급망", [(1, "KT가 회선을 댄다")])]}
        out = self.classify(_map(("003490", "경쟁사")), items, raw)
        found = [c for st in out["stages"] for c in st["companies"] if c.get("found")]
        self.assertEqual([(c["name"], c["tier"], c["direction"]) for c in found], [("삼성에스디에스", "indirect", "neu")])
        self.assertEqual(out["verify"]["listed"], 1)

    def test_evidence_after_reference_time_is_not_used(self):
        c = verify.Corpus(REF, REF.isoformat())
        self.assertIsNotNone(c.add("news", "t", "x", "https://a/1", "연합뉴스", (REF - timedelta(minutes=1)).isoformat()))
        self.assertIsNone(c.add("news", "t", "x", "https://a/2", "연합뉴스", (REF + timedelta(minutes=1)).isoformat()))
        self.assertIsNone(c.add("news", "t", "x", "https://a/1", "연합뉴스", REF.isoformat()))  # 같은 주소
        self.assertEqual((len(c.items), c.after_ref), (1, 1))

    def test_dart_same_day_excluded_and_excerpt_cached(self):
        listing = {"status": "000", "list": [
            {"rcept_no": "1", "rcept_dt": "20261030", "report_nm": "단일판매ㆍ공급계약체결"},  # 기준일 당일 → 접수 시각을 몰라 뺀다
            {"rcept_no": "2", "rcept_dt": "20261020", "report_nm": "단일판매ㆍ공급계약체결"},
            {"rcept_no": "3", "rcept_dt": "20260310", "report_nm": "사업보고서 (2025.12)"}]}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("a.xml", "<P>계약상대방: 인천국제공항공사</P><P>계약내용: 체크인 발권 시스템 구축</P>")
        calls = []

        class R:
            def __init__(self, body=None, content=b""):
                self.body, self.content, self.status_code = body, content, 200

            def json(self):
                return self.body

        def http(url, params=None, timeout=None):
            calls.append(url)
            return R(listing) if url.endswith("list.json") else R(content=buf.getvalue())
        with mock.patch.object(verify, "get_secret", return_value="k"), mock.patch.object(verify.disclosures, "corp_codes_for", return_value=["c"]):
            c = verify.Corpus(REF, REF.isoformat())
            n = verify.dart_evidence(c, {"code": "018260", "name": "삼성에스디에스"}, ["인천국제공항공사"], True, [3], http)
            self.assertEqual(n, 2)  # 공급계약 공시 1 + 사업보고서 1(같은 날 공시는 없음)
            self.assertEqual([i["url"][-1] for i in c.items], ["2", "3"])
            self.assertIn("인천국제공항공사", c.items[0]["text"])
            self.assertEqual((c.items[0]["kind"], c.items[0]["filer"]), ("dart", "018260"))
            verify.dart_text("2", http)
        self.assertEqual(sum(u.endswith("document.xml") for u in calls), 2)  # 같은 원문은 캐시에서

    def test_off_error_and_timeout_keep_current_result_as_unverified(self):
        m = _map(("003490", "경쟁사"))
        with mock.patch.dict("os.environ", {"LIFEMAP_VERIFY": "0"}):
            off = verify.verify_map(TOPIC, m, [], REF)
        self.assertEqual((off["verify"]["status"], off["stages"]), ("off", m["stages"]))
        with mock.patch.object(verify, "collect", side_effect=RuntimeError("down")):
            err = verify.verify_map(TOPIC, m, [], REF)
        self.assertEqual((err["verify"]["status"], err["stages"]), ("unverified", m["stages"]))
        self.assertIn("down", err["verify"]["error"])
        with mock.patch.object(verify, "VERIFY_TIMEOUT", 0.05), mock.patch.object(verify, "collect", side_effect=lambda *a, **k: time.sleep(0.3)):
            slow = verify.verify_map(TOPIC, m, [], REF)
        self.assertEqual((slow["verify"]["status"], slow["verify"]["error"], slow["stages"]), ("unverified", "timeout", m["stages"]))
        self.assertEqual([r["status"] for r in store.read("lifemap_verify_log")], ["unverified", "unverified"])

    def test_names_and_quotes(self):
        for text, name, hit in [("KTX 운행 중단", "KT", False), ("KT는 복구", "KT", True), ("애플리케이션", "애플", False),
                                ("GS건설 해킹", "GS", False), ("인천국제공항공사 측은", "인천국제공항공사", True)]:
            self.assertEqual(verify.mentions(text, name), hit, (text, name))
        self.assertTrue(verify.quote_found("체크인 시스템 장애로 발권이 지연", "어제 체크인 시스템 장애로 발권이 5시간 지연됐다"))
        self.assertFalse(verify.quote_found("A사가 시스템을 공급했다", "인천공항 시스템 장애"))
        self.assertTrue(verify.tied("인천공항 발권 장애 대한항공", [], ["인천공항", "발권", "장애"]))
        self.assertFalse(verify.tied("게임 신작 크래프톤", [], ["콜", "오브", "듀티", "게임"]))  # 업종 말 하나로는 사건과 이어지지 않는다


class SelectionTest(VerifyBase):
    """4단계: 검증된 국내 상장기업이 있는 이슈 먼저, 없는 이슈는 최대 1개."""

    def test_no_verified_issues_capped_at_one_and_sorted_last(self):
        def made(name, no_verified, url):
            return {"name": name, "title": f"{name} 제목", "query": name, "no_verified": no_verified,
                    "articles": [{"url": url, "title": f"{name} 기사", "rep": True}], "map": {"stages": []}}
        picked = [made("공항 장애", True, "u1"), made("게임 논란", True, "u2"), made("배터리 리콜", False, "u3"), made("폭우 피해", False, "u4")]
        with mock.patch.object(lifemap, "rss_issues", return_value=picked), \
                mock.patch.object(lifemap, "_finish", side_effect=lambda t, *a, **k: t), \
                mock.patch.object(lifemap, "naver_general_issues", return_value=[]):
            data = lifemap.run_topics(self.basis())
        self.assertEqual([t["name"] for t in data["topics"]], ["배터리 리콜", "폭우 피해", "공항 장애"])
        self.assertEqual(store.read("lifemap_status")["rejects"]["no_verified"], 1)


if __name__ == "__main__":
    unittest.main()
