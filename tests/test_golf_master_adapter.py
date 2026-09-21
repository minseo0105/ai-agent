import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path
from collections import Counter
from services.golf_master import (attach_master, get_objective_detail, get_objective_status,
    matches_objective_conditions, is_round_eligible, normalize_operation_type, FEATURES)
from services.golf_catalog import load_service_catalog, estimate_per_person


class AdapterTests(unittest.TestCase):
    def overlay(self, status, classification, **club):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "master.json"
            p.write_text(json.dumps({"schema_version":"final-1.0", "clubs":[{
                "id":"a", "play_facility":{"nine_hole_twice":{
                    "status":status, "verification_class":classification}}}]}))
            source = [dict(id="a", name="시험", **club)]
            before = copy.deepcopy(source)
            result = attach_master(source, p)[0]
            self.assertEqual(source, before)
            return result

    def test_statuses_and_rounds(self):
        for status, cls, expected in [
            ("confirmed","SUPPORTED_B","confirmed"),
            ("conditional","CONDITIONAL","conditional"),
            ("unavailable","NEGATIVE_CANDIDATE","needs_check"),
            ("unavailable","VERIFIED_NEGATIVE","needs_check"),
            ("confirmed","CONTAMINATED_HOLD","needs_check"),
            ("needs_check","REFERENCE_ONLY","needs_check"),
            ("unknown","UNKNOWN","needs_check"),
            ("confirmed","UNRECOGNIZED","needs_check")]:
            c = self.overlay(status, cls, holes=9)
            self.assertEqual(get_objective_status(c,"nine_hole_twice"),expected)
            self.assertEqual(is_round_eligible(c),expected == "confirmed")
            self.assertTrue(matches_objective_conditions(c, list(FEATURES)))
        for holes, expected in [(18,True),(27,True),(9,False),(12,False),(None,True),("확인 필요",True)]:
            self.assertEqual(is_round_eligible({"holes":holes}),expected)

    def test_conflict(self):
        c = self.overlay("confirmed","SUPPORTED_B",play={"nine_hole_twice":False})
        self.assertTrue(get_objective_detail(c,"nine_hole_twice")["conflict"])
        self.assertEqual(get_objective_status(c,"nine_hole_twice"),"needs_check")

    def test_fallback_and_duplicate(self):
        rows=[{"id":"a","holes":18,"play":{"three_person":False}}]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"m.json"
            for content in [None,"{",json.dumps({"schema_version":"other"}),json.dumps({"schema_version":"final-1.0","clubs":[{"id":"a"},{"id":"a"}]})]:
                if content is not None:p.write_text(content)
                result=attach_master(rows,p)
                self.assertFalse(result[0]["_golf_runtime"]["matched"])
                self.assertTrue(matches_objective_conditions(result[0],["3인 플레이"]))
        self.assertEqual(attach_master(rows,enabled=False)[0]["_golf_runtime"]["diagnostic"],"disabled")

    def test_real_data(self):
        raw=json.loads(Path("data/golf/catalog.json").read_text(encoding="utf-8"))
        master=json.loads(Path("data/golf/master/golf_master.json").read_text(encoding="utf-8"))["clubs"]
        loaded=load_service_catalog()
        self.assertEqual((len(raw),len(master),len(loaded)),(553,553,553))
        self.assertEqual({c["id"] for c in raw},{c["id"] for c in master})
        self.assertEqual(sum(c["_golf_runtime"]["matched"] for c in loaded),553)
        by_id={c["id"]:c for c in loaded}
        negatives=0
        for c in master:
            for k,v in c["play_facility"].items():
                if v["status"]=="unavailable":
                    negatives+=1
                    self.assertEqual(get_objective_status(by_id[c["id"]],k),"needs_check")
                    self.assertTrue(matches_objective_conditions(by_id[c["id"]],[k]))
        self.assertEqual(negatives,48)
        for c in raw:
            after=by_id[c["id"]]
            for k in ("kga","fee","play","holes","official_url","booking_url","evidence","vworld_x","vworld_y"):
                self.assertEqual(c.get(k),after.get(k))
            for weekend in (False,True):
                self.assertEqual(estimate_per_person(c,weekend,4),estimate_per_person(after,weekend,4))

    def test_operation_and_page_routes(self):
        self.assertEqual(normalize_operation_type("비회원제"),"대중제(퍼블릭)")
        self.assertEqual(normalize_operation_type("회원제"),"회원제")
        s=Path("pages/6_골프장_추천.py").read_text(encoding="utf-8")
        ast.parse(s)
        self.assertEqual(s.count('matches_objective_conditions(club, cond.get("objective_features", []))'),2)
        self.assertIn('cond["objective_features"] = ["3인 플레이"] if cond["players"] == 3 else []',s)
        for call in ("render_kga_course_intelligence(club)","search_golf_review_bundle(","analyze_reviews_with_gpt(","save_runtime_summary(","refresh_pool_dual(","_skill_fit(","naver.maps.LatLng"):
            self.assertIn(call,s)
