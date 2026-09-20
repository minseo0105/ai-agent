import copy
from datetime import date
import json
from pathlib import Path
import unittest

from services.golf_master_builder_v2 import (
    TEST_IDS, build_club, build_report, claim_reason, field_result, identity_valid, kga_audit,
)

AS_OF = date(2026, 9, 20)


def source(sid="s", kind="official", published=None):
    return {"id": sid, "club_id": "test", "kind": kind, "url": "https://example.org/branch/",
            "source_date": published, "checked_at": "2026-09-20", "reviewed_by": "test reviewer",
            "authorized_urls": ["https://example.org/branch/"],
            "identity": {"method": "operator_legal_review", "publisher": "operator",
                         "branch": "test", "basis": "legal/contact review",
                         "evidence_url": "https://example.org/branch/",
                         "address_or_phone_match": True}}


def claim(field="holes", value=36, **kw):
    return {"field": field, "value": value, "source_id": "s", "quote": "전체 규모 총 36홀",
            "locator": "overview", "review_note": "reviewed exact context", "scope": "club",
            "temporal": "undated", "assertion": "explicit_club_total", **kw}


class Builder2Tests(unittest.TestCase):
    def test_search_name_and_contact_do_not_establish_identity(self):
        s = source()
        s["identity"] = {"name_match": True, "phone_match": True, "address_match": True}
        for url in ("https://hanjingolf.com/", "https://kakao.golf/",
                    "https://yeoksamgolf.com/", "https://unknown-new-domain.example/"):
            s["url"] = url
            self.assertFalse(identity_valid(s, "test"))
            self.assertIsNotNone(claim_reason(claim(), s, "test", AS_OF))

    def test_booking_is_not_homepage_without_authorized_exact_url(self):
        self.assertIsNotNone(claim_reason(claim("official_url", "https://kakao.golf/"), source(), "test", AS_OF))
        self.assertIsNotNone(claim_reason(claim("official_url", "https://example.org/"), source(), "test", AS_OF))
        self.assertIsNone(claim_reason(claim("official_url", "https://example.org/branch/"), source(), "test", AS_OF))

    def test_foreign_branch_not_accepted(self):
        s = source(); s["club_id"] = "jeju"
        self.assertIsNotNone(claim_reason(claim(), s, "test", AS_OF))

    def test_round_holes_and_course_combos_are_not_total(self):
        c = claim(value=18, quote="18홀 라운드 요금", assertion="round_fee")
        self.assertIsNotNone(claim_reason(c, source(), "test", AS_OF))
        c = claim("courses", [{"name": "동+서", "holes": 18}], assertion="kga_combinations")
        self.assertIsNotNone(claim_reason(c, source(), "test", AS_OF))

    def test_complete_course_sum_and_conflict(self):
        rows = [{"name": "올드", "holes": 18, "holes_evidence": "올드18홀"},
                {"name": "듄스", "holes": 18, "holes_evidence": "듄스18홀"}]
        c = claim("courses", rows, assertion="physical_courses", complete_course_inventory=True)
        d = {"sources": [source()], "claims": [c]}
        result = build_club({"id": "test", "name": "test"}, d, AS_OF)
        self.assertEqual(result["facts"]["holes"]["value"], 36)
        d["claims"].append(claim(value=18, quote="총18홀"))
        self.assertIsNone(build_club({"id": "test", "name": "test"}, d, AS_OF)["facts"]["holes"]["value"])

    def test_partial_inventory_not_summed(self):
        c = claim("courses", [{"name": "하늘", "holes": 18, "holes_evidence": "18홀"}],
                  assertion="physical_courses", complete_course_inventory=False)
        r = build_club({"id": "test", "name": "test"}, {"sources": [source()], "claims": [c]}, AS_OF)
        self.assertIsNone(r["facts"]["holes"]["value"])

    def test_missing_hole_proof_and_duplicate_courses_rejected(self):
        c = claim("courses", [{"name": "동", "holes": 9}], assertion="physical_courses")
        self.assertIsNotNone(claim_reason(c, source(), "test", AS_OF))
        c["value"] = [{"name": "동", "holes": None}, {"name": "동", "holes": None}]
        self.assertIsNotNone(claim_reason(c, source(), "test", AS_OF))

    def test_historical_and_current_do_not_make_mixed(self):
        old = claim("operation_type", "회원제", assertion="explicit_current_operation", temporal="historical")
        new = claim("operation_type", "대중제", source_id="new", assertion="explicit_current_operation", temporal="current")
        r = field_result([old, new], {"s": source(published="2018-01-01"),
                         "new": source("new", published="2026-05-01")}, "operation_type", "test", AS_OF)
        self.assertEqual(r["value"], "대중제")
        self.assertEqual(len(r["reference"]), 1)

    def test_undated_and_old_current_operation_are_reference(self):
        c = claim("operation_type", "대중제", assertion="explicit_current_operation", temporal="current")
        for published in (None, "2022-01-01", "2027-01-01"):
            self.assertIsNotNone(claim_reason(c, source(published=published), "test", AS_OF))

    def test_mixed_requires_simultaneous_evidence(self):
        c = claim("operation_type", "혼합", assertion="explicit_current_operation", temporal="current")
        self.assertIsNotNone(claim_reason(c, source(published="2026-01-01"), "test", AS_OF))
        c["simultaneous_operation_evidence"] = "현재회원제18+대중제9"
        self.assertIsNone(claim_reason(c, source(published="2026-01-01"), "test", AS_OF))

    def test_priority_and_same_priority_conflict(self):
        a, b = claim(), claim(value=18, quote="총18홀", source_id="b")
        r = field_result([a,b], {"s":source(), "b":source("b", "government")}, "holes", "test", AS_OF)
        self.assertEqual(r["value"],36)
        r = field_result([a,b], {"s":source(), "b":source("b")}, "holes", "test", AS_OF)
        self.assertIsNone(r["value"])

    def test_secondary_domains_alone_not_independent(self):
        a, b = source(kind="secondary"), source("b", "secondary")
        b["url"] = "https://another.example/"
        claims = [claim(),claim(source_id="b")]
        self.assertIsNone(field_result(claims, {"s":a,"b":b}, "holes", "test", AS_OF)["value"])
        a["independence_group"]="original-a"; b["independence_group"]="original-b"
        self.assertEqual(field_result(claims, {"s":a,"b":b}, "holes", "test", AS_OF)["value"],36)

    def test_kga_unassigned_never_inferred(self):
        k = {"matched":True,"match_type":"exact","course_combinations":["동+서"],
             "ratings_source_date":"2024-07-15", "checked_at":"2026-09-20",
             "ratings":[{"course":"","tee":"BLACK","gender":"남자","course_rating":74.1,"slope_rating":142}]}
        r=kga_audit({"kga":k},AS_OF)
        self.assertEqual(len(r["ratings_quarantined"]),1)
        self.assertEqual(r["ratings_structurally_valid"],[])
        self.assertTrue(r["older_than_730_days_or_undated"])

    def test_checked_at_does_not_become_source_date(self):
        r=field_result([claim()],{"s":source()},"holes","test",AS_OF)
        self.assertIsNone(r["source_date"])
        self.assertEqual(r["checked_at"],"2026-09-20")

    def test_duplicate_rating_conflict_quarantines_both(self):
        row = {"course":"동+서", "tee":"BLACK", "gender":"남자", "course_rating":74.1,"slope_rating":142}
        other = {**row, "course_rating":77.0}
        r=kga_audit({"kga":{"matched":True,"match_type":"exact","course_combinations":["동+서"],"ratings":[row,other]}},AS_OF)
        self.assertEqual(len(r["ratings_quarantined"]),2)
        self.assertEqual(r["ratings_structurally_valid"],[])

    def test_duplicate_source_ids_fail_closed(self):
        with self.assertRaises(ValueError):
            build_club({"id":"test","name":"test"},{"sources":[source(),source()]},AS_OF)

    def test_real_ten_review_does_not_mutate_input(self):
        root=Path(__file__).resolve().parents[1]
        raw=(root/'data/golf/catalog.json').read_bytes()
        catalog=json.loads(raw.decode('utf-8-sig'))
        dossier=json.loads((root/'data/golf/builder2/test10_sources.json').read_text(encoding='utf-8'))
        before=copy.deepcopy((catalog,dossier))
        r=build_report(catalog,dossier,AS_OF)
        self.assertEqual((catalog,dossier),before)
        self.assertEqual((root/'data/golf/catalog.json').read_bytes(),raw)
        self.assertEqual(tuple(c['id'] for c in r['clubs']),TEST_IDS)
        self.assertTrue(all(c['apply_allowed'] is False for c in r['clubs']))
        by_id={c['id']:c for c in r['clubs']}
        self.assertEqual(by_id['blackstone']['facts']['holes']['value'],27)
        self.assertIsNone(by_id['blackstone']['facts']['operation_type']['value'])
        self.assertEqual(by_id['club72']['facts']['holes']['value'],72)
        self.assertEqual(by_id['club72']['facts']['operation_type']['value'],'대중제')
        self.assertTrue(all(c['holes'] is None for c in by_id['club72']['facts']['courses']['value']))


if __name__ == '__main__':
    unittest.main()
