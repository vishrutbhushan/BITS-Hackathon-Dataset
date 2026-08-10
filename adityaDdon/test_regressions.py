#!/usr/bin/env python3
"""Regression coverage for previously silent high-impact answer failures."""

import json
import sys
import unittest
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = CURRENT_DIR.parent
sys.path[:0] = [str(CURRENT_DIR), str(CURRENT_DIR / "agent"), str(CURRENT_DIR / "db")]

from intent_planner import IntentPlanner
from pipeline import BidIntelligencePipeline
from db.build_database import extract_labeled_inr, normalize_inr


CLIENT_SCOPED_PATTERNS = {
    "absence",
    "ar_outstanding",
    "avg_work_size",
    "category_diff",
    "collection_rate",
    "exclusion_aggregate",
    "gap_to_threshold",
    "hop_aggregate",
    "mean_median_gap",
    "rank_value",
    "referenced_share",
    "threshold_aggregate",
    "unbilled_gap",
    "yoy_movement",
}


class PipelineRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads((WORKSPACE_ROOT / "questions.json").read_text(encoding="utf-8"))
        cls.questions = {q["qid"]: q for q in payload["questions"]}
        cls.planner = IntentPlanner()
        cls.pipeline = BidIntelligencePipeline(use_llm=False)

    def plan(self, qid):
        question = self.questions[qid]
        return self.planner.plan(question["question"], question["answer_type"])

    def answer(self, qid):
        question = self.questions[qid]
        return self.pipeline.answer_question(question["question"], question["answer_type"])["answer"]

    def test_unbilled_gap_is_not_subtracted_from_default_threshold(self):
        self.assertEqual(self.answer("HV-IC-0371"), 629_771_836)

    def test_exact_grouped_inr_wins_over_rounded_crore_rendering(self):
        text = "gross executed value of INR 19,32,99,999/- (Rupees 19.33 Crore Only)"
        self.assertEqual(extract_labeled_inr(text), 193_299_999)
        self.assertEqual(normalize_inr("3,338.00 Lakh"), 333_800_000)

    def test_client_aliases_resolve_to_canonical_entities(self):
        expected = {
            "HV-IC-0041": "Irrigation & Waterways Dept, Govt of Uttar Pradesh",
            "HV-IC-0196": "Public Works Department, Govt of Gujarat",
            "HV-IC-0338": "Public Health Engineering Dept, Odisha",
            "HV-IC-0377": "Irrigation & Waterways Dept, Govt of Rajasthan",
            "HV-IC-0453": "Jal Nigam, Gujarat",
        }
        for qid, client in expected.items():
            with self.subTest(qid=qid):
                self.assertEqual(self.plan(qid).anchor_client, client)

    def test_overlapping_category_aliases_use_longest_non_overlapping_span(self):
        expected = {
            "HV-IC-0428": ["Roads Maintenance", "Water Supply"],
            "HV-IC-0438": ["Large Bridges", "Water Treatment"],
            "HV-IC-0468": ["Large Bridges", "Water Supply"],
        }
        for qid, categories in expected.items():
            with self.subTest(qid=qid):
                self.assertEqual(self.plan(qid).extra_params["categories"], categories)

    def test_project_title_categories_do_not_override_average_intent(self):
        plan = self.plan("HV-IC-0337")
        self.assertEqual(plan.pattern, "avg_work_size")

    def test_exclusion_categories_are_exact(self):
        expected = {
            "HV-IC-0292": "Roads Highways",
            "HV-IC-0319": "Sewerage Drainage",
        }
        for qid, category in expected.items():
            with self.subTest(qid=qid):
                plan = self.plan(qid)
                self.assertEqual(plan.pattern, "exclusion_aggregate")
                self.assertEqual(plan.subtasks[0].query_params["exclude"], category)

    def test_receivable_language_maps_to_outstanding_balance(self):
        for qid in [
            "HV-IC-0390",
            "HV-IC-0393",
            "HV-IC-0407",
            "HV-IC-0411",
            "HV-IC-0412",
            "HV-IC-0413",
        ]:
            with self.subTest(qid=qid):
                self.assertEqual(self.plan(qid).pattern, "ar_outstanding")

    def test_two_category_requests_compile_to_category_difference(self):
        for qid in ["HV-IC-0460", "HV-IC-0468", "HV-IC-0473"]:
            with self.subTest(qid=qid):
                plan = self.plan(qid)
                self.assertEqual(plan.pattern, "category_diff")
                self.assertEqual(len(plan.extra_params["categories"]), 2)

    def test_all_client_scoped_questions_resolve_a_client(self):
        for qid, question in self.questions.items():
            plan = self.planner.plan(question["question"], question["answer_type"])
            if plan.pattern in CLIENT_SCOPED_PATTERNS:
                with self.subTest(qid=qid, pattern=plan.pattern):
                    self.assertTrue(plan.anchor_client, "client-scoped query has no resolved client")

    def test_every_category_difference_has_exactly_two_categories(self):
        for qid, question in self.questions.items():
            plan = self.planner.plan(question["question"], question["answer_type"])
            if plan.pattern == "category_diff":
                with self.subTest(qid=qid):
                    self.assertEqual(len(plan.extra_params.get("categories", [])), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
