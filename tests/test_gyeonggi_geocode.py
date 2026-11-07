"""경기 주소 지오코딩 회귀 테스트. 실제 실패 주소 6건(운영 시범 실행)과 검증 조건·실패 캐시 재시도 규칙.

provider 응답은 NAVER addressElements 모양을 흉내 낸 합성 값이다(외부 호출 없음).
"""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import gyeonggi_projects as gg

REAL = {
    "경기도 고양시 덕양구 관산동 178-57번지 일원": ("경기도 고양시 덕양구 관산동 178-57", "고양시", "덕양구", "관산동", "178-57"),
    "경기도 고양시 덕양구 행신동 222번지 일원": ("경기도 고양시 덕양구 행신동 222", "고양시", "덕양구", "행신동", "222"),
    "경기도 고양시 일산동 960-16번지 일원": ("경기도 고양시 일산동 960-16", "고양시", None, "일산동", "960-16"),
    "경기도 고양시 덕양구 고양동 22-2번지 일원(제일복지회관 주변)": ("경기도 고양시 덕양구 고양동 22-2", "고양시", "덕양구", "고양동", "22-2"),
    "경기도 고양시 행신동 173-1번지일원(행신지구 재건축 주변)": ("경기도 고양시 행신동 173-1", "고양시", None, "행신동", "173-1"),
    "경기도 고양시 덕양구 토당동 251-12번지 일원": ("경기도 고양시 덕양구 토당동 251-12", "고양시", "덕양구", "토당동", "251-12"),
}
NAVER_GU = {"관산동": "덕양구", "행신동": "덕양구", "일산동": "일산동구", "고양동": "덕양구", "토당동": "덕양구"}


def cand(dong, lot, *, sigungu=None, sido="경기도", ri="", acc="PARCEL", lon=126.85, lat=37.65, jibun=None):
    sigungu = sigungu or f"고양시 {NAVER_GU.get(dong, '덕양구')}"
    return {"longitude": lon, "latitude": lat, "accuracy": acc,
            "matched_address": jibun or f"{sido} {sigungu} {dong} {lot}", "jibun_address": jibun or f"{sido} {sigungu} {dong} {lot}",
            "address_elements": {"SIDO": sido, "SIGUGUN": sigungu, "DONGMYUN": dong, "RI": ri, "LAND_NUMBER": lot}}


def resp(*cands):
    return {"result_status": "MATCHED", "provider": "naver:geocode", "candidates": list(cands)}


class ParseTests(unittest.TestCase):
    def test_real_failed_addresses_now_parse(self):
        for address, (query, si, gu, dong, lot) in REAL.items():
            t = gg.geocode_target(address)
            self.assertIsNone(t["reason"], address)
            self.assertEqual((t["query"], t["si"], t["gu"], t["dong"], t["lot"]), (query, si, gu, dong, lot), address)
            self.assertNotIn("일원", t["query"])
            self.assertNotIn("(", t["query"])

    def test_mountain_lot_and_ri(self):
        t = gg.geocode_target("경기도 양평군 양평읍 양근리 산 12-3번지 일원")
        self.assertEqual((t["query"], t["dong"], t["ri"], t["lot"], t["mountain"]), ("경기도 양평군 양평읍 양근리 산 12-3", "양평읍", "양근리", "12-3", True))
        self.assertTrue(gg.geocode_target("경기도 가평군 가평읍 읍내리 산12")["mountain"])

    def test_incomplete_addresses_are_not_guessed(self):
        cases = {
            "경기도 고양시 덕양구 관산동 일원": "NO_LOT",
            "경기도 덕양구 관산동 178-57": "NO_SIGUN",
            "경기도 고양시 178-57번지": "NO_DONG",
            "경기도 고양시 덕양구 관산동 178-57, 178-58번지 일원": "MULTIPLE_LOTS",
            "인천광역시 중구 신포동 1": "NO_SIGUN",
            "": "NO_SIGUN",
        }
        for address, reason in cases.items():
            t = gg.geocode_target(address)
            self.assertEqual((t["reason"], t["query"]), (reason, None), address)

    def test_original_address_is_not_changed(self):
        fetched = {"rows": [{"SIGUN_NM": "고양시", "IMPRV_ZONE_NM": "관산", "LOCPLC_ADDR": "경기도 고양시 덕양구 관산동 178-57번지 일원",
                             "BIZ_TYPE_NM": "재개발", "BIZ_STEP_NM": "예정구역"}],
                   "fetched_at": "2026-11-08T00:00:00+00:00", "total": 1, "received": 1, "pages": 1, "result_code": "INFO-000",
                   "complete": True, "service": "GenrlimprvBizpropls"}
        r = gg.normalize("general", fetched)[0][0]
        self.assertEqual(r["address"], "경기도 고양시 덕양구 관산동 178-57번지 일원")
        self.assertEqual(r["raw"]["LOCPLC_ADDR"], "경기도 고양시 덕양구 관산동 178-57번지 일원")


class VerifyTests(unittest.TestCase):
    def test_real_addresses_verify_with_exact_naver_candidate(self):
        for address, (_, _, _, dong, lot) in REAL.items():
            r = gg.verify_coordinate(address, resp(cand(dong, lot)))
            self.assertTrue(r["coordinate_verified"], (address, r))
            self.assertEqual(r["parser_version"], gg.PARSER_VERSION)

    def test_failures_report_which_check_failed(self):
        a = "경기도 고양시 덕양구 관산동 178-57번지 일원"
        cases = {
            "lot": cand("관산동", "178-5"),
            "dong": cand("행신동", "178-57"),
            "gu": cand("관산동", "178-57", sigungu="고양시 일산서구"),
            "sigun": cand("관산동", "178-57", sigungu="파주시"),
            "sido": cand("관산동", "178-57", sido="서울특별시"),
            "accuracy": cand("관산동", "178-57", acc="REGION"),
            "bounds": cand("관산동", "178-57", lat=35.1),
        }
        for check, c in cases.items():
            r = gg.verify_coordinate(a, resp(c))
            self.assertFalse(r["coordinate_verified"], check)
            self.assertEqual(r["reason"], "NO_CANDIDATE_PASSED")
            self.assertIn(check, r["failed_checks"], check)
            self.assertEqual(r["diagnostics"][0]["failed_checks"], ["gu", "sigun"] if check == "sigun" else [check])  # 다른 시면 구도 함께 틀린다
            self.assertNotIn("latitude", r)

    def test_two_exact_candidates_are_not_adopted(self):
        r = gg.verify_coordinate("경기도 고양시 덕양구 토당동 251-12번지 일원", resp(cand("토당동", "251-12"), cand("토당동", "251-12", lon=126.86)))
        self.assertEqual((r["coordinate_verified"], r["reason"]), (False, "MULTIPLE_CANDIDATES"))

    def test_every_candidate_is_checked_not_only_the_first_ten(self):
        a = "경기도 고양시 덕양구 토당동 251-12번지 일원"
        noise = [cand("토당동", f"251-{n}") for n in range(20, 30)]  # 10건, 모두 지번 불일치
        # 1번째와 12번째가 모두 정확히 맞으면 하나로 확정하지 않는다.
        r = gg.verify_coordinate(a, resp(cand("토당동", "251-12"), *noise, cand("토당동", "251-12", lon=126.86)))
        self.assertEqual((r["coordinate_verified"], r["reason"], r["candidate_count"], r["passing_count"]), (False, "MULTIPLE_CANDIDATES", 12, 2))
        self.assertEqual(len(r["diagnostics"]), gg.MAX_DIAGNOSTICS)
        self.assertTrue(r["diagnostics_truncated"])
        # 유일한 일치 후보가 12번째에 있어도 찾는다.
        only_last = gg.verify_coordinate(a, resp(*noise, cand("토당동", "251-1"), cand("토당동", "251-12")))
        self.assertTrue(only_last["coordinate_verified"])
        self.assertEqual(only_last["candidate_count"], 12)

    def test_mountain_lot_must_match_mountain(self):
        a = "경기도 양평군 양평읍 양근리 산 12-3번지 일원"
        plain = cand("양평읍", "12-3", sigungu="양평군", ri="양근리", lon=127.5, lat=37.49, jibun="경기도 양평군 양평읍 양근리 12-3")
        hill = cand("양평읍", "12-3", sigungu="양평군", ri="양근리", lon=127.5, lat=37.49, jibun="경기도 양평군 양평읍 양근리 산 12-3")
        self.assertIn("mountain", gg.verify_coordinate(a, resp(plain))["failed_checks"])
        self.assertTrue(gg.verify_coordinate(a, resp(hill))["coordinate_verified"])

    def test_unparseable_address_never_calls_for_a_match(self):
        r = gg.verify_coordinate("경기도 고양시 덕양구 관산동 일원", resp(cand("관산동", "1")))
        self.assertEqual((r["coordinate_verified"], r["reason"], r["parse_reason"]), (False, "ADDRESS_HAS_NO_LOT_OR_SIGUN", "NO_LOT"))

    def test_failed_cache_entries_are_never_used_as_coordinates(self):
        records = [{"address": "a", "latitude": None, "longitude": None, "mappable": False, "has_location": False,
                    "coordinate_verified": False, "location_notice": "x"}]
        gg.attach_coordinates(records, lambda a: {"coordinate_verified": False, "latitude": 37.6, "longitude": 126.8, "status": "FAILED"})
        self.assertFalse(records[0]["mappable"])
        self.assertIsNone(records[0]["latitude"])


class RetryPolicyTests(unittest.TestCase):
    def test_needs_geocode(self):
        self.assertTrue(gg.needs_geocode(None))
        self.assertFalse(gg.needs_geocode({"coordinate_verified": True, "parser_version": 1}))
        self.assertTrue(gg.needs_geocode({"coordinate_verified": False, "reason": "NO_CANDIDATE_PASSED"}))  # 버전 없는 예전 실패
        self.assertFalse(gg.needs_geocode({"coordinate_verified": False, "parser_version": gg.PARSER_VERSION}))
        self.assertTrue(gg.needs_geocode({"coordinate_verified": False, "parser_version": gg.PARSER_VERSION}, retry_failed=True))


class RouteTests(unittest.TestCase):
    ADDRS = ["경기도 고양시 덕양구 관산동 178-57번지 일원",          # 이미 성공 → 건너뜀
             "경기도 고양시 덕양구 행신동 222번지 일원",            # 예전(버전 없는) 실패 → 다시 시도
             "경기도 고양시 덕양구 토당동 251-12번지 일원",          # 현재 버전 실패 → retry_failed일 때만
             "경기도 고양시 덕양구 고양동 22-2번지 일원(제일복지회관 주변)",  # 처음
             "경기도 고양시 덕양구 관산동 일원"]                    # 지번 없음 → provider 호출 없음

    def run_route(self, cache, **kw):
        import api.realestate as api
        calls = []

        def provider(query):
            calls.append(query)
            dong, lot = query.split()[-2], query.split()[-1]
            return resp(cand(dong, lot))
        records = [{"address": a} for a in self.ADDRS]
        with mock.patch.object(api, "GG_GEOCODE_CACHE", cache), \
                mock.patch.object(api.gg, "collect", lambda *a, **k: (records, {})), \
                mock.patch.object(api.geocode, "select_provider", lambda *a, **k: {"provider": provider, "name": "naver", "blocker": None}):
            out = asyncio.run(api.gyeonggi_geocode(**kw))
        return out, calls

    def seed(self, cache):
        import services.development_geocode as geo
        cache.mkdir(parents=True, exist_ok=True)
        write = lambda a, e: (cache / (geo.cache_key(a) + ".json")).write_text(json.dumps(dict(e, address=a), ensure_ascii=False), encoding="utf-8")
        write(self.ADDRS[0], {"coordinate_verified": True, "latitude": 37.65, "longitude": 126.85, "parser_version": 1})
        write(self.ADDRS[1], {"coordinate_verified": False, "reason": "ADDRESS_HAS_NO_LOT_OR_SIGUN"})
        write(self.ADDRS[2], {"coordinate_verified": False, "reason": "NO_CANDIDATE_PASSED", "parser_version": gg.PARSER_VERSION})

    def test_dry_run_calls_no_provider(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "c"
            self.seed(cache)
            out, calls = self.run_route(cache, dry_run=True)
        self.assertEqual(calls, [])
        self.assertEqual(out["status"], "DRY_RUN")
        self.assertEqual(out["pending"], 3)  # 예전 실패 1 + 처음 1 + 지번 없음 1
        self.assertEqual(out["parse_results"], {"QUERY_READY": 2, "NO_LOT": 1})
        self.assertEqual((out["expected_api_calls"], out["unparseable_recorded"], out["deferred"]), (2, 1, 0))

    def test_old_failures_are_retried_with_clean_queries_and_successes_kept(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "c"
            self.seed(cache)
            out, calls = self.run_route(cache, limit=10)
            self.assertEqual(calls, ["경기도 고양시 덕양구 행신동 222", "경기도 고양시 덕양구 고양동 22-2"])
            self.assertEqual((out["api_calls"], out["verified"], out["unparseable_recorded"]), (2, 2, 1))
            import services.development_geocode as geo
            saved = json.loads((cache / (geo.cache_key(self.ADDRS[1]) + ".json")).read_text(encoding="utf-8"))
            self.assertEqual((saved["status"], saved["parser_version"], saved["address"]), ("VERIFIED", gg.PARSER_VERSION, self.ADDRS[1]))
            kept = json.loads((cache / (geo.cache_key(self.ADDRS[0]) + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(kept["parser_version"], 1)  # 성공 캐시는 다시 쓰지 않는다
            again, calls2 = self.run_route(cache, limit=10)
            self.assertEqual(calls2, [])
            forced, calls3 = self.run_route(cache, limit=10, retry_failed=True)
            self.assertEqual(calls3, ["경기도 고양시 덕양구 토당동 251-12"])

    def test_plan_order_matches_limit(self):
        ok = lambda n: f"경기도 고양시 덕양구 관산동 {n}번지 일원"
        bad = lambda n: f"경기도 고양시 덕양구 관산{n}동 일원"
        plan = gg.plan_geocode([ok(1), bad(1), ok(2), bad(2), ok(3)], 2)
        self.assertEqual([action for _, action, _ in plan], ["CALL", "SKIP_UNPARSEABLE", "CALL", "DEFER", "DEFER"])

    def test_dry_run_counts_match_the_real_run(self):
        order = [self.ADDRS[4], self.ADDRS[1], self.ADDRS[3]]  # 지번 없음, 예전 실패, 처음
        for limit in (1, 2, 10):
            with tempfile.TemporaryDirectory() as d:
                cache = Path(d) / "c"
                with mock.patch.object(self, "ADDRS", order):
                    dry, calls = self.run_route(cache, limit=limit, dry_run=True)
                    self.assertEqual(calls, [])
                    real, calls = self.run_route(cache, limit=limit)
                self.assertEqual(dry["expected_api_calls"], len(calls), limit)
                self.assertEqual(dry["expected_api_calls"], real["api_calls"], limit)
                self.assertEqual(dry["unparseable_recorded"], real["unparseable_recorded"], limit)
                self.assertEqual(dry["deferred"], real["deferred"], limit)
                self.assertEqual(dry["expected_api_calls"] + dry["unparseable_recorded"] + dry["deferred"], dry["pending"])

    def test_limit_caps_provider_calls(self):
        with tempfile.TemporaryDirectory() as d:
            out, calls = self.run_route(Path(d) / "c", limit=1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(out["api_calls"], 1)


if __name__ == "__main__":
    unittest.main()
