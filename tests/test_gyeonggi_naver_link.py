"""경기 사업 네이버부동산 지도 링크: 검증된 좌표가 있을 때만, 서울과 같은 함수·URL 형식으로."""
import asyncio
import re
import unittest
from pathlib import Path
from unittest import mock

from services import development_presentation as pr
from services import gyeonggi_projects as gg

ROOT = Path(__file__).resolve().parents[1]
ADDR_OK = "경기도 고양시 덕양구 관산동 178-57번지 일원"
ADDR_NO = "경기도 고양시 덕양구 행신동 222번지 일원"


def records():
    rows = [{"SIGUN_NM": "고양시", "IMPRV_ZONE_NM": "관산(합성)", "LOCPLC_ADDR": ADDR_OK, "BIZ_TYPE_NM": "재개발", "BIZ_STEP_NM": "예정구역"},
            {"SIGUN_NM": "고양시", "IMPRV_ZONE_NM": "행신(합성)", "LOCPLC_ADDR": ADDR_NO, "BIZ_TYPE_NM": "재건축", "BIZ_STEP_NM": "조합설립"}]
    fetched = {"rows": rows, "fetched_at": "2026-11-08T00:00:00+00:00", "total": 2, "received": 2, "pages": 1,
               "result_code": "INFO-000", "complete": True, "service": "GenrlimprvBizpropls"}
    return gg.normalize("general", fetched)[0]


CACHE = {ADDR_OK: {"coordinate_verified": True, "latitude": 37.6512, "longitude": 126.8443, "status": "VERIFIED"},
         ADDR_NO: {"coordinate_verified": False, "latitude": 37.6, "longitude": 126.8, "status": "FAILED"}}


class LinkTests(unittest.TestCase):
    def test_verified_coordinate_gets_the_seoul_link_format(self):
        recs = gg.attach_coordinates(records(), CACHE.get)
        link = gg.to_project(recs[0])["naver_real_estate"]
        seoul = pr.naver_real_estate_link({"latitude": 37.6512, "longitude": 126.8443})
        self.assertEqual(link["url"], seoul["url"])
        self.assertRegex(link["url"], r"^https://fin\.land\.naver\.com/map\?center=[0-9A-Za-z]+-[0-9A-Za-z]+&zoom=17$")
        self.assertEqual(set(link), set(seoul))
        self.assertEqual((link["basis"], link["destination"], link["label"]), (seoul["basis"], "NPAY_MAP", seoul["label"]))
        self.assertIn("특정 단지·매물이 아니에요", link["note"])

    def test_no_link_without_verified_coordinate(self):
        recs = gg.attach_coordinates(records(), CACHE.get)
        self.assertIsNone(gg.to_project(recs[1])["naver_real_estate"])  # 실패 캐시(좌표 값이 있어도) → 링크 없음
        base = records()[0]
        self.assertIsNone(gg.to_project(base)["naver_real_estate"])  # 좌표 없음
        tampered = dict(base, latitude=37.6, longitude=126.8, mappable=True, coordinate_verified=False)
        self.assertIsNone(gg.naver_link(tampered))
        unmappable = dict(base, latitude=37.6, longitude=126.8, mappable=False, coordinate_verified=True)
        self.assertIsNone(gg.naver_link(unmappable))
        broken = dict(base, latitude=float("nan"), longitude=126.8, mappable=True, coordinate_verified=True)
        self.assertIsNone(gg.naver_link(broken))

    def test_link_matches_frontend_type(self):
        ts = (ROOT / "web/src/lib/realestate.ts").read_text(encoding="utf-8")
        block = ts[ts.index("  naver_real_estate: {"):]
        block = block[:block.index("} | null;")]
        fields = set(re.findall(r"^\s+(\w+): string;", block, re.M))
        recs = gg.attach_coordinates(records(), CACHE.get)
        self.assertEqual(set(gg.to_project(recs[0])["naver_real_estate"]), fields)

    def test_seoul_link_is_unchanged(self):
        link = pr.naver_real_estate_link({"latitude": 37.5, "longitude": 127.0})
        self.assertEqual(link["note"], "저장된 사업 대표좌표 위치의 Npay 부동산 지도를 새 탭에서 엽니다.")
        self.assertIsNone(pr.naver_real_estate_link({"latitude": None, "longitude": 127.0}))


class RouteTests(unittest.TestCase):
    def test_list_and_detail_routes_attach_coordinates_before_building_links(self):
        import api.realestate as api
        with mock.patch.object(api.gg, "collect", lambda *a, **k: (records(), {"general": {"status": "OK"}})), \
                mock.patch.object(api, "_gg_coordinate_lookup", lambda: CACHE.get), \
                mock.patch.object(api.detail, "_coordinate_provider_configured", lambda: False):
            listing = asyncio.run(api.gyeonggi_projects())
            by_name = {p["name"]: p for p in listing["items"]}
            ok, no = by_name["관산(합성)"], by_name["행신(합성)"]
            self.assertTrue(ok["mappable"])
            self.assertTrue(ok["naver_real_estate"]["url"].startswith("https://fin.land.naver.com/map?center="))
            self.assertFalse(no["mappable"])
            self.assertIsNone(no["naver_real_estate"])
            d_ok = asyncio.run(api.gyeonggi_project_detail(ok["project_id"]))
            d_no = asyncio.run(api.gyeonggi_project_detail(no["project_id"]))
        self.assertEqual(d_ok["project"]["naver_real_estate"]["url"], ok["naver_real_estate"]["url"])
        self.assertIsNone(d_no["project"]["naver_real_estate"])


if __name__ == "__main__":
    unittest.main()
