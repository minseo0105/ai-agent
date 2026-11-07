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
    """일반 정비사업 행(필드명은 실제 응답에서 확인된 이름, 값은 합성)."""
    base = {"SIGUN_NM": sigun, "IMPRV_ZONE_NM": name or f"테스트{i}구역", "LOCPLC_ADDR": addr or f"{sigun} 팔달구 매산동 {i}",
            "BIZ_TYPE_NM": "재개발", "BIZ_STEP_NM": "조합설립", "ZONE_AR": "12345.6", "EXISTNG_HOUSNG_HSHLD_CNT": "300",
            "BIZ_IMPLMTN_HSHLD_CNT_TOTSUM": "520", "BIZ_IMPLMNTR_NM": "테스트조합",
            "ASSOCTN_FOUND_CONFMTN_DE": "2021-05-03", "BIZ_IMPLMTN_CONFMTN_DE": "", "MANAGE_DISPOSIT_CONFMTN_DE": None}
    base.update(extra)
    return base


def small_row(i, signgu="부천시 원미구", name=None, addr=None, **extra):
    base = {"SIGNGU_NM": signgu, "BIZ_NM": name or f"소규모{i}", "DETAIL_ADDR": addr or f"부천시 원미구 원미동 {i}",
            "PROPLSN_STEP": "건축심의", "BIZ_IMPLMTN_AR": "3,210", "BIZ_DIV": "1",
            "ASSOCTN_FOUND_CONFMTN_LPERD": "2022.03", "BIZ_IMPLMTN_PLAN_CONFMTN_LPERD": "", "STRCONTR_LPERD": "", "COMPLTN_LPERD": ""}
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

    def test_verified_field_names_and_missing_fields(self):
        self.assertEqual(gg.detect_mapping([row(1)], "general")["status"], "VERIFIED_NAMES")
        broken = row(1)
        del broken["BIZ_STEP_NM"]
        d = gg.detect_mapping([broken], "general")
        self.assertEqual(d["status"], "FIELDS_MISSING")
        self.assertIn("BIZ_STEP_NM", d["missing_fields"])
        self.assertNotIn("stage", d["mapping"])  # 다른 필드로 대신 채우지 않는다

    def test_general_record_keeps_raw_values_and_does_not_invent(self):
        records, _ = gg.normalize("general", self.fetched([row(7)]))
        r = records[0]
        self.assertEqual(r["raw"]["IMPRV_ZONE_NM"], "테스트7구역")
        self.assertEqual((r["sigun"], r["district"], r["dong"], r["type_label"]), ("수원시", "수원시 팔달구", "매산동", "재개발"))
        vals = {v["key"]: v["value"] for v in r["values"]}
        self.assertEqual(vals, {"area": "12345.6", "existing_households": "300", "planned_households": "520", "implementer": "테스트조합"})
        self.assertEqual([d["value"] for d in r["stage_dates"]], ["2021-05-03", None, None])
        self.assertIsNone(r["source_base_date"])
        self.assertTrue(r["needs_refresh"])
        self.assertFalse(r["mappable"])
        for banned in ("investment", "roi", "profit", "contribution", "price"):
            self.assertFalse(any(banned in k for k in r), banned)

    def test_small_record_does_not_convert_biz_div(self):
        records, _ = gg.normalize("small", self.fetched([small_row(1, BIZ_DIV="3")], "small"))
        r = records[0]
        self.assertEqual((r["type_label"], r["program_label"], r["biz_div"]), ("소규모주택정비", "소규모주택정비", "3"))
        self.assertEqual((r["sigun"], r["district"]), ("부천시", "부천시 원미구"))
        self.assertEqual(r["stage_dates"][0], {"label": "조합설립인가", "value": "2022.03", "source_field": "ASSOCTN_FOUND_CONFMTN_LPERD"})

    def test_stage_standardization_covers_all_reported_values(self):
        general = {"예정구역": "CANDIDATE", "정비구역": "DESIGNATED", "추진위원회": "COMMITTEE", "조합설립": "ASSOCIATION_APPROVED",
                   "사업시행": "IMPLEMENTATION_APPROVED", "관리처분": "MANAGEMENT_DISPOSITION", "착공": "CONSTRUCTION",
                   "준공": "COMPLETED", "청산": "CLOSED"}
        small = {"조합설립인가": "ASSOCIATION_APPROVED", "건축심의": "PLAN_DELIBERATION", "사업시행계획인가": "IMPLEMENTATION_APPROVED",
                 "준공": "COMPLETED", "착공": "CONSTRUCTION", "사업시행인가": "IMPLEMENTATION_APPROVED", "이전고시": "TRANSFER_NOTICE",
                 "주민합의체 구성": "COMMITTEE"}
        for raw, code in general.items():
            self.assertEqual(gg.standard_stage("general", raw), code, raw)
        for raw, code in small.items():
            self.assertEqual(gg.standard_stage("small", raw), code, raw)
        for raw in ("", None, "미입력", "알수없음"):
            self.assertEqual(gg.standard_stage("small", raw), "UNKNOWN")

    def test_original_and_standard_stage_kept_separately_and_completed_flag(self):
        rows = [row(1, BIZ_STEP_NM="준공"), row(2, BIZ_STEP_NM="청산"), row(3, BIZ_STEP_NM="관리처분"), row(4, BIZ_STEP_NM="")]
        records, _ = gg.normalize("general", self.fetched(rows))
        self.assertEqual([(r["stage_raw"], r["stage_std"], r["completed"]) for r in records],
                         [("준공", "COMPLETED", True), ("청산", "CLOSED", True), ("관리처분", "MANAGEMENT_DISPOSITION", False), (None, "UNKNOWN", False)])
        self.assertIn("stage", records[3]["missing"])

    def test_missing_fields_and_invalid_sigun_are_reported(self):
        rows = [row(1, sigun="인천광역시", addr="인천광역시 중구 1"), {"SIGUN_NM": "광명시"}]
        records, _ = gg.normalize("general", self.fetched(rows))
        self.assertFalse(records[0]["sigun_valid"])
        self.assertTrue(records[1]["sigun_valid"])
        self.assertEqual(set(records[1]["missing"]), {"name", "type_label", "address", "stage"})

    def test_duplicates_are_flagged_not_removed(self):
        a, _ = gg.normalize("general", self.fetched([row(1, sigun="부천시", name="원미1-1구역 주택재개발", addr="부천시 원미구 원미동 1")]))
        b, _ = gg.normalize("small", self.fetched([small_row(2, name="원미 1-1 구역", addr="부천시 원미구 원미동 99")], "small"))
        c, _ = gg.normalize("general", self.fetched([row(3, sigun="광명시", name="원미1-1구역", addr="광명시 철산동 3")]))
        d, _ = gg.normalize("general", self.fetched([row(4, sigun="광명시", name="다른사업", addr="광명시 철산동 3")]))
        records = a + b + c + d
        self.assertEqual(gg.mark_duplicates(records), 2)  # 이름 1쌍(부천), 주소 1쌍(광명)
        self.assertEqual(records[0]["duplicate_of"], [records[1]["project_id"]])
        self.assertEqual(records[2]["duplicate_basis"], ["addr"])
        self.assertEqual(len(records), 4)

    def test_to_project_has_screen_fields_and_unknowns(self):
        records, _ = gg.normalize("general", self.fetched([row(1, BIZ_STEP_NM="관리처분")]))
        p = gg.to_project(records[0])
        for key in ("project_id", "name", "type_label", "program_label", "stage", "stage_timeline", "location_accuracy", "trust",
                    "official_source", "stage_display", "spatial", "mappable", "has_location", "gyeonggi"):
            self.assertIn(key, p)
        self.assertTrue(p["project_id"].startswith("gg-general-"))
        self.assertEqual(p["stage"]["label"], "관리처분")
        self.assertEqual(p["stage_timeline"]["current_label"], "관리처분인가")
        self.assertFalse(p["stage_display"]["legal_stage_confirmed"])
        self.assertIsNone(p["naver_real_estate"])
        self.assertIsNone(p["stage_guide"])
        detail = gg.detail_for(p, {"trades": {}})
        self.assertFalse(detail["project"]["boundary"]["verified"])
        self.assertIsNone(detail["project"]["facts"]["area_m2"])  # 단위 미검증이라 숫자로 해석하지 않는다

    def test_quality_report_and_31_regions(self):
        records, _ = gg.normalize("general", self.fetched([row(1), row(2, sigun="광명시", addr="광명시 철산동 2"), row(3, sigun="인천광역시", addr="인천광역시 중구 3")]))
        gg.mark_duplicates(records)
        q = gg.quality_report(records, {})
        self.assertEqual(len(q["by_sigun"]), 31)
        self.assertEqual(q["by_sigun"]["수원시"], 1)
        self.assertEqual(q["unknown_sigun"], {"(없음)": 1})
        self.assertIn("general / 조합설립 / ASSOCIATION_APPROVED", q["stage_mapping"])
        self.assertEqual(len(gg.region_summary(records)), 31)


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
                return Resp(page(svc, [row(1), row(2, sigun="광명시", addr="광명시 철산동 2", BIZ_TYPE_NM="재건축"),
                                       row(3, BIZ_STEP_NM="준공")], 3))
            return Resp(page(gg.DATASETS["small"]["service"], [small_row(9)], 1))
        with mock.patch.object(api, "_gg_http_get", http_get), mock.patch.object(api.rm, "_secret", secret):
            out = self.run_route(api.gyeonggi_projects(sigun="광명시"))
            regions = self.run_route(api.gyeonggi_regions())
            rebuild = self.run_route(api.gyeonggi_projects(type="재건축"))
            small = self.run_route(api.gyeonggi_projects(type="소규모정비"))
            active = self.run_route(api.gyeonggi_projects(include_completed=False))
            everything = self.run_route(api.gyeonggi_projects())
            pid = small["items"][0]["project_id"]
            with mock.patch.object(api.detail, "_coordinate_provider_configured", lambda: False):
                d = self.run_route(api.gyeonggi_project_detail(pid))
        self.assertEqual((rebuild["total"], small["total"], everything["total"], active["total"], everything["completed"]), (1, 1, 4, 3, 1))
        self.assertEqual(d["project"]["project_id"], pid)
        self.assertIn("trades", d["connections"])
        self.assertEqual(out["total"], 1)
        self.assertEqual(out["items"][0]["district"], "광명시")
        self.assertNotIn("raw", out["items"][0])
        self.assertEqual(out["items"][0]["gyeonggi"]["format_note"][:2], "면적")
        self.assertNotIn(SECRET, json.dumps(out, ensure_ascii=False))
        self.assertEqual(len(regions["regions"]), 31)

    def test_detail_rejects_unknown_ids(self):
        import api.realestate as api
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            self.run_route(api.gyeonggi_project_detail("8ce0fcab-579e-54f3-ab09-df384230e52a"))
        self.assertEqual(ctx.exception.status_code, 422)

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
