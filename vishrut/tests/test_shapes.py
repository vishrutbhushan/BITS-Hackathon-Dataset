"""
Shape dispatcher tests, validated against real answers from
sample_questions.json. Each test seeds a minimal sqlite DB with the exact
values named in that sample's reasoning_steps, then checks the shape
function reproduces the published answer exactly.

This is the check described in the architecture doc: prove the shape
library is correct with hand-typed entity bindings, BEFORE any question-
understanding / LLM layer is wired in. If these pass, any error later is
isolated to extraction or entity resolution, not the math.
"""
import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.schema import get_connection, upsert_client, upsert_engineer
from shapes import dispatcher as D


def seed_project(con, client_id, value, category="other", completion_date=None,
                  grading=None, role=None, has_ref=0, engineer_id=None, name=None):
    con.execute(
        """INSERT INTO projects
           (name, client_id, engineer_id, category, value_rupees,
            completion_date, grading, role, has_reference_letter, source_doc_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name or f"project-{value}", client_id, engineer_id, category, value,
         completion_date, grading, role, has_ref, "test"),
    )


class TestAbsenceAndReferencedShare(unittest.TestCase):
    """HS-IC-0002 / HS-IC-0020: Jal Nigam, Jharkhand -- 3 works, 1 referenced."""

    def setUp(self):
        self.con = get_connection()
        cid = upsert_client(self.con, "Jal Nigam, Jharkhand")
        seed_project(self.con, cid, 730200000, has_ref=1)   # the one WITH a reference letter
        seed_project(self.con, cid, 814400000, has_ref=0)
        seed_project(self.con, cid, 69200000, has_ref=0)
        self.con.commit()

    def test_absence_count(self):
        answer, _ = D.shape_absence(self.con, "Jal Nigam, Jharkhand")
        self.assertEqual(answer, 2)  # HS-IC-0002

    def test_referenced_share(self):
        answer, _ = D.shape_referenced_share(self.con, "Jal Nigam, Jharkhand")
        self.assertEqual(answer, 33.33)  # HS-IC-0020


class TestRankAndThreshold(unittest.TestCase):
    """HS-IC-0018 / HS-IC-0024: same Jal Nigam client, different shapes."""

    def setUp(self):
        self.con = get_connection()
        cid = upsert_client(self.con, "Jal Nigam, Jharkhand")
        seed_project(self.con, cid, 730200000)
        seed_project(self.con, cid, 814400000)
        seed_project(self.con, cid, 69200000)
        self.con.commit()

    def test_rank_value_gap(self):
        answer, _ = D.shape_rank_value(self.con, "Jal Nigam, Jharkhand")
        self.assertEqual(answer, 84200000)  # HS-IC-0018

    def test_threshold_aggregate(self):
        # HS-IC-0024: "crossing the seventy-three crore mark" -> > 730,000,000
        answer, _ = D.shape_threshold_aggregate(self.con, "Jal Nigam, Jharkhand", 730000000)
        self.assertEqual(answer, 1544600000)

    def test_avg_work_size(self):
        # HS-IC-0011: average across the same 3-work portfolio
        answer, _ = D.shape_avg_work_size(self.con, "Jal Nigam, Jharkhand")
        self.assertEqual(answer, 537933333)


class TestJharkhandMunicipalCorporation(unittest.TestCase):
    """HS-IC-0019 / HS-IC-0021 / HS-IC-0023 / HS-IC-0016: one client, four shapes."""

    def setUp(self):
        self.con = get_connection()
        cid = upsert_client(self.con, "Jharkhand Municipal Corporation")
        seed_project(self.con, cid, 87400000, category="road",
                     role="Subcontractor", has_ref=1)
        seed_project(self.con, cid, 314600000, category="building", role="Prime", has_ref=1)
        seed_project(self.con, cid, 69500000, category="roads_maintenance", role="Prime", has_ref=0)
        self.con.commit()

    def test_rank_value_gap(self):
        answer, _ = D.shape_rank_value(self.con, "Jharkhand Municipal Corporation")
        self.assertEqual(answer, 227200000)  # HS-IC-0019

    def test_referenced_share(self):
        answer, _ = D.shape_referenced_share(self.con, "Jharkhand Municipal Corporation")
        self.assertEqual(answer, 66.67)  # HS-IC-0021

    def test_role_split(self):
        answer, _ = D.shape_role_split(self.con, "Jharkhand Municipal Corporation", "Prime")
        self.assertEqual(answer, 384100000)  # HS-IC-0023

    def test_exclusion_aggregate(self):
        answer, _ = D.shape_exclusion_aggregate(
            self.con, "Jharkhand Municipal Corporation", "roads_maintenance"
        )
        self.assertEqual(answer, 402000000)  # HS-IC-0016


class TestGapToThreshold(unittest.TestCase):
    """HS-IC-0017: Irrigation & Waterways Dept, Govt of Uttar Pradesh."""

    def setUp(self):
        self.con = get_connection()
        cid = upsert_client(self.con, "Irrigation & Waterways Dept, Govt of Uttar Pradesh")
        seed_project(self.con, cid, 123300000, grading="Excellent")
        seed_project(self.con, cid, 48000000, grading="Excellent")
        self.con.commit()

    def test_gap_to_threshold(self):
        # target INR 20 Cr = 200,000,000
        answer, _ = D.shape_gap_to_threshold(
            self.con, "Irrigation & Waterways Dept, Govt of Uttar Pradesh", 200000000
        )
        self.assertEqual(answer, 28700000)  # HS-IC-0017

    def test_doc_filtered_aggregate(self):
        # HS-IC-0013: both works graded Excellent -> sum of both
        answer, _ = D.shape_doc_filtered_aggregate(
            self.con, "Irrigation & Waterways Dept, Govt of Uttar Pradesh", "Excellent"
        )
        self.assertEqual(answer, 171300000)


class TestEngineerPortfolioShapes(unittest.TestCase):
    """HS-IC-0006 / HS-IC-0010: Asha Nair's 4 led works (distinct_count, temporal_chain)."""

    def setUp(self):
        self.con = get_connection()
        eid = upsert_engineer(self.con, "Asha Nair")
        client_a = upsert_client(self.con, "Client A")
        client_b = upsert_client(self.con, "Jal Nigam, Jharkhand")

        self.con.execute(
            "INSERT INTO engineer_certs(engineer_id, cert_type, issue_date) VALUES (?, ?, ?)",
            (eid, "PMP", "2021-03-10"),
        )
        # Exactly 4 works led, matching HS-IC-0006's reasoning_steps values,
        # 4 distinct categories, 2 completed after the PMP issue date
        # (summing to 244,200,000 per HS-IC-0010).
        seed_project(self.con, client_a, 321400000, category="building",
                     completion_date="2021-01-15", engineer_id=eid,
                     name="Project A (before)")
        seed_project(self.con, client_a, 214200000, category="water_treatment",
                     completion_date="2021-06-01", engineer_id=eid,
                     name="Project B (after)")
        seed_project(self.con, client_b, 814400000, category="bridge",
                     completion_date="2021-02-01", engineer_id=eid,
                     name="Cable Stayed Bridge \u2014 Jharkhand Pkg-115")
        seed_project(self.con, client_a, 30000000, category="power",
                     completion_date="2021-04-01", engineer_id=eid,
                     name="Project D (after)")
        self.con.commit()

    def test_distinct_count(self):
        answer, _ = D.shape_distinct_count(self.con, "Asha Nair")
        self.assertEqual(answer, 4)  # HS-IC-0006

    def test_temporal_chain(self):
        answer, _ = D.shape_temporal_chain(self.con, "Asha Nair", "2021-03-10")
        # Projects B (214.2M) and D (30M) completed after 2021-03-10
        self.assertEqual(answer, 244200000)  # HS-IC-0010

    def test_avg_work_size_for_bridge_client(self):
        # HS-IC-0011: her Cable Stayed Bridge project's client, averaged
        # over that client's full (separately seeded) portfolio
        cid = upsert_client(self.con, "Jal Nigam, Jharkhand")
        seed_project(self.con, cid, 730200000)
        seed_project(self.con, cid, 69200000)
        self.con.commit()
        answer, _ = D.shape_avg_work_size(self.con, "Jal Nigam, Jharkhand")
        self.assertEqual(answer, 537933333)


class TestDateSpan(unittest.TestCase):
    """HS-IC-0003: isolated fixture, since the date_span shape only needs
    one cert and one named project, unrelated to the portfolio-count
    tests above."""

    def setUp(self):
        self.con = get_connection()
        eid = upsert_engineer(self.con, "Asha Nair")
        client_a = upsert_client(self.con, "Client A")
        self.con.execute(
            "INSERT INTO engineer_certs(engineer_id, cert_type, issue_date) VALUES (?, ?, ?)",
            (eid, "PMP", "2021-03-10"),
        )
        # 2021-03-10 + 1569 days = 2025-06-26 (verified via datetime.timedelta)
        seed_project(self.con, client_a, 999999999, category="building",
                     completion_date="2025-06-26", engineer_id=eid,
                     name="School Building \u2014 Madhya Pradesh Pkg-145")
        self.con.commit()

    def test_date_span(self):
        answer, _ = D.shape_date_span(
            self.con, "Asha Nair", "PMP", "2021-03-10",
            "School Building \u2014 Madhya Pradesh Pkg-145",
        )
        self.assertEqual(answer, 1569)  # HS-IC-0003


class TestHopAggregate(unittest.TestCase):
    """HS-IC-0007-style: engineer's works restricted to one client."""

    def setUp(self):
        self.con = get_connection()
        eid = upsert_engineer(self.con, "Rahul Menon")
        pwd = upsert_client(self.con, "Public Works Department, Govt of Maharashtra")
        other = upsert_client(self.con, "Some Other Client")

        for v in [193299999, 176600000, 214200000, 307300000, 586900000, 529900000]:
            seed_project(self.con, pwd, v, engineer_id=eid)
        seed_project(self.con, other, 999999999, engineer_id=eid)  # should be excluded
        self.con.commit()

    def test_hop_aggregate(self):
        answer, _ = D.shape_hop_aggregate(
            self.con, "Rahul Menon", "Public Works Department, Govt of Maharashtra"
        )
        self.assertEqual(answer, 2008199999)  # HS-IC-0007


if __name__ == "__main__":
    unittest.main()
