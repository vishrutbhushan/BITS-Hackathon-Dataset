#!/usr/bin/env python3
"""Regression coverage for previously silent high-impact answer failures."""

import json
import sys
import unittest
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = CURRENT_DIR.parent
sys.path[:0] = [str(CURRENT_DIR), str(CURRENT_DIR / "agent"), str(CURRENT_DIR / "db")]

from intent_planner import IntentPlanner, extract_explicit_date, parse_threshold_inr
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
            "HV-IC-0036": "Water Treatment",
            "HV-IC-0292": "Roads Highways",
            "HV-IC-0319": "Sewerage Drainage",
        }
        for qid, category in expected.items():
            with self.subTest(qid=qid):
                plan = self.plan(qid)
                self.assertEqual(plan.pattern, "exclusion_aggregate")
                self.assertEqual(plan.subtasks[0].query_params["exclude"], category)

    def test_package_less_project_descriptions_resolve_semantically(self):
        expected = {
            "HV-IC-0014": 23,
            "HV-IC-0118": 117,
            "HV-IC-0222": 100,
            "HV-IC-0244": 60,
            "HV-IC-0335": 4,
            "HV-IC-0349": 25,
        }
        for qid, package_number in expected.items():
            with self.subTest(qid=qid):
                self.assertEqual(self.plan(qid).anchor_package_num, package_number)

    def test_semantic_project_resolution_changes_downstream_answer(self):
        expected = {
            "HV-IC-0014": 536,
            "HV-IC-0118": 374,
            "HV-IC-0222": 326_300_000,
            "HV-IC-0335": 798,
            "HV-IC-0349": 240_294_737,
        }
        for qid, answer in expected.items():
            with self.subTest(qid=qid):
                self.assertEqual(self.answer(qid), answer)

    def test_month_and_year_do_not_invent_a_day_of_month(self):
        self.assertIsNone(self.plan("HV-IC-0014").anchor_date)

    def test_variance_between_scope_and_claims_is_unbilled_gap(self):
        self.assertEqual(self.plan("HV-IC-0285").pattern, "unbilled_gap")

    def test_endorsement_share_is_not_collection_rate(self):
        self.assertEqual(self.plan("HV-IC-0389").pattern, "referenced_share")

    def test_spaced_compound_number_does_not_collapse_to_suffix(self):
        question = self.questions["HV-IC-0377"]["question"]
        self.assertEqual(parse_threshold_inr(question), 260_000_000)
        self.assertEqual(self.answer("HV-IC-0377"), 1_350_500_000)

    def test_general_number_and_date_parsers_are_not_dataset_enumerations(self):
        self.assertEqual(
            parse_threshold_inr("only engagements above one hundred and thirty four crore"),
            1_340_000_000,
        )
        self.assertEqual(parse_threshold_inr("minimum INR 12.75 lakh"), 1_275_000)
        self.assertEqual(extract_explicit_date("issued November 7th, 2022"), "2022-11-07")
        self.assertEqual(extract_explicit_date("issued 14 February 2020"), "2020-02-14")
        self.assertIsNone(extract_explicit_date("issued in November 2022"))

    def test_unseen_paraphrases_map_through_operation_ontology(self):
        cases = [
            (
                "For Trishakti, omit tunnels and return the remainder of its portfolio.",
                "money",
                "exclusion_aggregate",
            ),
            (
                "What receivable balance is due on Suvarna's invoices?",
                "money",
                "ar_outstanding",
            ),
            (
                "Show the spread between Mahanadi Steel's top and runner-up contracts.",
                "money",
                "rank_value",
            ),
            (
                "What is the difference between Suvarna's sanctioned contracts and invoices?",
                "money",
                "unbilled_gap",
            ),
            (
                "What percentage of Trishakti assignments have endorsements?",
                "percent",
                "referenced_share",
            ),
            (
                "Add Mahanadi Steel jobs worth at least ninety four crore.",
                "money",
                "threshold_aggregate",
            ),
        ]
        for question, answer_type, expected_pattern in cases:
            with self.subTest(question=question):
                self.assertEqual(
                    self.planner.plan(question, answer_type).pattern,
                    expected_pattern,
                )

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
