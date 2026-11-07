"""경기도 정비사업 수집기 테스트. 외부 호출 없이 경기데이터드림 응답 형식을 흉내 낸 합성 데이터만 쓴다.

픽스처의 필드명(IMPRV_ZONE_NM 등)은 실제 응답 필드가 아니라 탐지 규칙을 시험하기 위한 합성 이름이다.
"""
import asyncio
import json
import unittest
from unittest import mock

from services import gyeonggi_projects as gg

SECRET = "SECRET-KEY-123"


def secret(name, default=None):
    return SECRET if name == gg.KEY_NAME else default


class Resp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


def page(service, rows, total, code="INFO-000"):
    return {service: [{"head": [{"list_total_count": total}, {"RESULT": {"CODE": code, "MESSAGE": "정상 처리되었습니다."}}]},
                      {"row": rows}]}


def row(i, sigun="수원시", name=None, addr=None, **extra):
    base = {"SIGUN_NM": sigun, "IMPRV_ZONE_NM": name or f"테스트{i}구역", "IMPRV_BIZ_TYPE": "재개발",
            "PROGRS_STTUS": "조합설립인가", "REFINE_LOTNO_ADDR": addr or f"경기도 {sigun} 팔달구 매산동 {i}",
            "ZONE_AR": "12,345.6", "ASSOCTN_APPRV_DE": "2021-05-03"}
    base.update(extra)
    return base


class FetchTests(unittest.TestCase):
    def setUp(self):
        gg._cache.clear()

    def test_pages_until_total_and_marks_complete(self):
        svc = gg.DATASETS["general"]["service"]
        calls = []

        def http_get(url, params=None, timeout=None):
            calls.append(params["pIndex"])
            n = 2 if params["pIndex"] == 1 else 1
            start = (params["pIndex"] - 1) * 2
            return Resp(page(svc, [row(start + k) for k in range(n)], 3))

        out = gg.fetch_dataset("general", http_get, secret, page_size=2, sleep=lambda s: None)
        self.assertEqual(calls, [1, 2])
        self.assertEqual((out["total"], out["received"], out["complete"]), (3, 3, True))

    def test_incomplete_when_fewer_rows_than_total(self):
        svc = gg.DATASETS["small"]["service"]
        out = gg.fetch_dataset("small", lambda *a, **k: Resp(page(svc, [row(1)], 5)), secret, page_size=10, sleep=lambda s: None)
        self.assertFalse(out["complete"])

    def test_retries_timeouts_then_succeeds(self):
        svc = gg.DATASETS["general"]["service"]
        attempts, sleeps = [], []

        def http_get(url, params=None, timeout=None):
            attempts.append(1)
            if len(attempts) < 3:
                raise TimeoutError(f"timed out {url}?KEY={params['KEY']}")
            return Resp(page(svc, [row(1)], 1))

        out = gg.fetch_dataset("general", http_get, secret, sleep=sleeps.append)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleeps, [1, 2])
        self.assertEqual(out["received"], 1)

    def test_timeout_exhausted_raises_without_key(self):
        def http_get(url, params=None, timeout=None):
            raise TimeoutError(f"timed out {url}?KEY={params['KEY']}&pIndex=1")
        with self.assertRaises(gg.GyeonggiError) as ctx:
            gg.fetch_dataset("general", http_get, secret, retries=2, sleep=lambda s: None)
        self.assertEqual(ctx.exception.code, "TIMEOUT")
        self.assertNotIn(SECRET, str(ctx.exception))

    def test_http_500_and_429_are_retried(self):
        svc = gg.DATASETS["general"]["service"]
        seq = [Resp({}, 500), Resp({}, 429), Resp(page(svc, [row(1)], 1))]
        out = gg.fetch_dataset("general", lambda *a, **k: seq.pop(0), secret, sleep=lambda s: None)
        self.assertEqual(out["received"], 1)
        with self.assertRaises(gg.GyeonggiError) as ctx:
            gg.fetch_dataset("general", lambda *a, **k: Resp({}, 500), secret, retries=1, sleep=lambda s: None)
        self.assertEqual(ctx.exception.code, "HTTP_500")

    def test_invalid_key_is_not_retried(self):
        calls = []

        def http_get(*a, **k):
            calls.append(1)
            return Resp({"RESULT": {"CODE": "ERROR-290", "MESSAGE": "인증키가 유효하지 않습니다."}})
        with self.assertRaises(gg.GyeonggiError) as ctx:
            gg.fetch_dataset("general", http_get, secret, sleep=lambda s: None)
        self.assertEqual((ctx.exception.code, len(calls)), ("ERROR-290", 1))

    def test_no_data_is_empty_not_error(self):
        out = gg.fetch_dataset("small", lambda *a, **k: Resp({"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}}), secret)
        self.assertEqual((out["received"], out["complete"]), (0, True))

    def test_missing_key_makes_no_request(self):
        called = []
        with self.assertRaises(gg.GyeonggiError) as ctx:
            gg.fetch_dataset("general", lambda *a, **k: called.append(1), lambda n, d=None: None)
        self.assertEqual(ctx.exception.code, "NOT_CONFIGURED")
        self.assertEqual(called, [])


class NormalizeTests(unittest.TestCase):
    def fetched(self, rows, dataset="general"):
        return {"rows": rows, "fetched_at": "2026-11-07T00:00:00+00:00", "total": len(rows), "received": len(rows),
                "pages": 1, "result_code": "INFO-000", "complete": True, "service": gg.DATASETS[dataset]["service"]}

    def test_mapping_is_detected_and_marked_unverified(self):
        d = gg.detect_mapping([row(1, UNKNOWN_COL="x")])
        self.assertEqual(d["status"], "UNVERIFIED")
        self.assertEqual(d["mapping"]["sigun"], "SIGUN_NM")
        self.assertEqual(d["mapping"]["name"], "IMPRV_ZONE_NM")
        self.assertEqual(d["mapping"]["address"], "REFINE_LOTNO_ADDR")
        self.assertIn("ASSOCTN_APPRV_DE", d["date_fields"])
        self.assertIn("UNKNOWN_COL", d["unmapped"])

    def test_record_keeps_raw_and_does_not_invent_values(self):
        records, _ = gg.normalize("general", self.fetched([row(7)]))
        r = records[0]
        self.assertEqual(r["raw"]["IMPRV_ZONE_NM"], "테스트7구역")
        self.assertEqual((r["sido"], r["sigun"], r["district"], r["dong"]), ("경기도", "수원시", "수원시 팔달구", "매산동"))
        self.assertEqual(r["area_m2"], 12345.6)
        self.assertEqual(r["stage_dates"], {"ASSOCTN_APPRV_DE": "2021-05-03"})
        self.assertEqual(r["collected_at"], "2026-11-07T00:00:00+00:00")
        self.assertIsNone(r["source_base_date"])
        self.assertTrue(r["needs_refresh"])
        self.assertFalse(r["mappable"])
        self.assertIsNone(r["latitude"])
        for banned in ("investment", "roi", "profit", "contribution", "price"):
            self.assertFalse(any(banned in k for k in r), banned)

    def test_missing_fields_and_invalid_sigun_are_reported(self):
        rows = [row(1, sigun="인천광역시"), {"SIGUN_NM": "광명시"}]
        records, _ = gg.normalize("general", self.fetched(rows))
        self.assertFalse(records[0]["sigun_valid"])
        self.assertTrue(records[1]["sigun_valid"])
        self.assertEqual(set(records[1]["missing"]), {"name", "type_label", "address", "stage"})

    def test_small_dataset_gets_policy_type(self):
        records, _ = gg.normalize("small", self.fetched([row(1)], "small"))
        self.assertEqual(records[0]["program_label"], "소규모주택정비")

    def test_duplicates_are_flagged_not_removed(self):
        a, _ = gg.normalize("general", self.fetched([row(1, sigun="부천시", name="원미1-1구역 주택재개발", addr="경기도 부천시 원미구 원미동 1")]))
        b, _ = gg.normalize("small", self.fetched([row(2, sigun="부천시", name="원미 1-1 구역", addr="경기도 부천시 원미구 원미동 99")], "small"))
        c, _ = gg.normalize("general", self.fetched([row(3, sigun="광명시", name="원미1-1구역")]))
        records = a + b + c
        self.assertEqual(gg.mark_duplicates(records), 1)
        self.assertEqual(records[0]["duplicate_of"], [records[1]["project_id"]])
        self.assertEqual(records[2]["duplicate_of"], [])
        self.assertEqual(len(records), 3)

    def test_quality_report_and_31_regions(self):
        records, _ = gg.normalize("general", self.fetched([row(1), row(2, sigun="광명시"), row(3, sigun="인천광역시")]))
        gg.mark_duplicates(records)
        q = gg.quality_report(records, {})
        self.assertEqual(len(q["by_sigun"]), 31)
        self.assertEqual(q["by_sigun"]["수원시"], 1)
        self.assertEqual(q["unknown_sigun"], {"인천광역시": 1})
        regions = gg.region_summary(records)
        self.assertEqual(len(regions), 31)
        self.assertNotIn("인천광역시", [r["sigun"] for r in regions])


class CacheTests(unittest.TestCase):
    def setUp(self):
        gg._cache.clear()

    def test_hit_within_ttl_and_stale_on_failure(self):
        svc = gg.DATASETS["general"]["service"]
        now = [0.0]
        calls = []

        def ok(*a, **k):
            calls.append(1)
            return Resp(page(svc, [row(1)], 1))
        first = gg.load("general", ok, secret, ttl=100, clock=lambda: now[0])
        second = gg.load("general", ok, secret, ttl=100, clock=lambda: now[0])
        self.assertEqual((first["cache"], second["cache"], len(calls)), ("MISS", "HIT", 1))
        now[0] = 500
        bad = lambda *a, **k: Resp({"RESULT": {"CODE": "ERROR-290", "MESSAGE": "x"}})
        stale = gg.load("general", bad, secret, ttl=100, clock=lambda: now[0])
        self.assertEqual(stale["cache"], "STALE")
        self.assertEqual(stale["received"], 1)
        self.assertEqual(stale["error"]["code"], "ERROR-290")

    def test_collect_returns_other_dataset_when_one_fails(self):
        def http_get(url, params=None, timeout=None):
            if url.endswith(gg.DATASETS["small"]["service"]):
                return Resp({"RESULT": {"CODE": "ERROR-310", "MESSAGE": "해당하는 서비스를 찾을 수 없습니다."}})
            return Resp(page(gg.DATASETS["general"]["service"], [row(1)], 1))
        records, meta = gg.collect(http_get, secret, sleep=lambda s: None)
        self.assertEqual(len(records), 1)
        self.assertEqual((meta["general"]["status"], meta["small"]["status"], meta["small"]["code"]), ("OK", "ERROR", "ERROR-310"))


class CoordinateTests(unittest.TestCase):
    ADDR = "경기도 수원시 팔달구 매산동 3"

    def cand(self, lot="3", sigungu="수원시 팔달구", sido="경기도", lon=127.0, lat=37.27, acc="PARCEL"):
        return {"longitude": lon, "latitude": lat, "accuracy": acc,
                "address_elements": {"SIDO": sido, "SIGUGUN": sigungu, "DONGMYUN": "매산동", "LAND_NUMBER": lot}}

    def resp(self, *cands):
        return {"result_status": "MATCHED", "provider": "naver", "candidates": list(cands)}

    def test_single_exact_candidate_is_verified(self):
        r = gg.verify_coordinate(self.ADDR, self.resp(self.cand()))
        self.assertTrue(r["coordinate_verified"])
        self.assertEqual((r["latitude"], r["longitude"]), (37.27, 127.0))

    def test_rejections(self):
        cases = {
            "lot 30 vs 3": self.resp(self.cand(lot="30")),
            "other city": self.resp(self.cand(sigungu="성남시 수정구")),
            "seoul": self.resp(self.cand(sido="서울특별시")),
            "out of bounds": self.resp(self.cand(lat=35.1)),
            "coarse accuracy": self.resp(self.cand(acc="DONG")),
            "two candidates": self.resp(self.cand(), self.cand(lon=127.001)),
            "no match": {"result_status": "NO_MATCH", "candidates": []},
        }
        for label, response in cases.items():
            self.assertFalse(gg.verify_coordinate(self.ADDR, response)["coordinate_verified"], label)
        self.assertFalse(gg.verify_coordinate("경기도 수원시 팔달구 매산동", self.resp(self.cand()))["coordinate_verified"])

    def test_attach_only_verified(self):
        records = [{"address": "a", "latitude": None, "longitude": None, "mappable": False, "has_location": False,
                    "coordinate_verified": False, "location_notice": "x"},
                   {"address": "b", "latitude": None, "longitude": None, "mappable": False, "has_location": False,
                    "coordinate_verified": False, "location_notice": "x"}]
        lookup = {"a": {"coordinate_verified": True, "latitude": 37.3, "longitude": 127.0},
                  "b": {"coordinate_verified": False, "reason": "NO_MATCH"}}.get
        gg.attach_coordinates(records, lookup)
        self.assertEqual([r["mappable"] for r in records], [True, False])


class ApiTests(unittest.TestCase):
    def setUp(self):
        gg._cache.clear()

    def run_route(self, coro):
        return asyncio.run(coro)

    def test_projects_route_filters_and_hides_raw_and_key(self):
        import api.realestate as api
        svc = gg.DATASETS["general"]["service"]

        def http_get(url, params=None, timeout=None):
            if url.endswith(svc):
                return Resp(page(svc, [row(1), row(2, sigun="광명시", addr="경기도 광명시 철산동 2")], 2))
            return Resp({"RESULT": {"CODE": "INFO-200", "MESSAGE": "없음"}})
        with mock.patch.object(api, "_gg_http_get", http_get), mock.patch.object(api.rm, "_secret", secret):
            out = self.run_route(api.gyeonggi_projects(sigun="광명시"))
            regions = self.run_route(api.gyeonggi_regions())
        self.assertEqual(out["total"], 1)
        self.assertEqual(out["items"][0]["district"], "광명시")
        self.assertNotIn("raw", out["items"][0])
        self.assertEqual(out["mapping_status"], "UNVERIFIED")
        self.assertNotIn(SECRET, json.dumps(out, ensure_ascii=False))
        self.assertEqual(len(regions["regions"]), 31)

    def test_rejects_non_gyeonggi_sigun(self):
        import api.realestate as api
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.run_route(api.gyeonggi_projects(sigun="인천광역시"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_missing_key_is_503(self):
        import api.realestate as api
        from fastapi import HTTPException
        with mock.patch.object(api.rm, "_secret", lambda n, d=None: None):
            with self.assertRaises(HTTPException) as ctx:
                self.run_route(api.gyeonggi_projects())
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
