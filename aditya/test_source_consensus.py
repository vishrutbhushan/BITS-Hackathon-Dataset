import sys
import unittest
from collections import defaultdict
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "db"))
sys.path.insert(0, str(ROOT / "agent"))

from database import DEFAULT_DB_PATH, get_db
from entity_resolver import EntityResolver
from exact_math import mean_median_gap, percentage, round_fraction
from intent_planner import (
    IntentPlanner,
    extract_mean_median_mode,
    extract_performance_filter,
    extract_threshold_comparison,
)
from retriever import SubtaskRetriever
from source_consensus import (
    SourceFact,
    normalize_date,
    parse_performance_grade,
    parse_portfolio,
    reconcile_project,
    select_consensus,
)
from promote_candidate import promote


class SourceConsensusUnitTests(unittest.TestCase):
    def test_indian_numeric_dates_are_day_first_and_iso_is_year_first(self):
        self.assertEqual(normalize_date("06/02/2011"), "2011-02-06")
        self.assertEqual(normalize_date("2011-02-06"), "2011-02-06")
        self.assertEqual(normalize_date("February 6, 2011"), "2011-02-06")

    def test_portfolio_parser_preserves_wrapped_jv_role(self):
        text = """1. Material Handling Plant — Example Pkg-999
Client
Example Authority (JV
Partner)
Category
Industrial Epc
Executed Value
INR 12.33 Cr
Completed
July 16, 2025 · Certificate CC/1/2025/999
Industrial Epc works for Example Authority completed 2025.
"""
        record = parse_portfolio(text)[999]
        self.assertEqual(record["role"], "JV Partner")
        self.assertEqual(record["client"], "Example Authority")

    def test_portfolio_record_boundary_does_not_start_at_prose_year(self):
        text = """1. First Work — Example Pkg-1
Client
Example Authority (Prime)
Category
Roads
Executed Value
INR 1.00 Cr
Completed
January 1, 2015 · Certificate CC/1/2015/001
Roads works for Example Authority completed 2015.
2. Second Work — Example Pkg-2
Client
Example Authority (Prime)
Category
Roads
Executed Value
INR 2.00 Cr
Completed
February 2, 2016 · Certificate CC/2/2016/002
"""
        records = parse_portfolio(text)
        self.assertEqual(set(records), {1, 2})
        self.assertEqual(records[2]["work_no"], 2)

    def test_two_source_agreement_outvotes_lower_priority_conflict(self):
        facts = [
            SourceFact("primary", "A", "completion_date", "2020-02-01"),
            SourceFact("secondary", "B", "completion_date", "2020-01-02"),
            SourceFact("tertiary", "C", "completion_date", "2020-01-02"),
        ]
        selected = select_consensus(facts, ("primary", "secondary", "tertiary"))
        self.assertEqual(selected.value, "2020-01-02")
        self.assertEqual(selected.status, "majority")

    def test_exact_grouped_client_amount_has_precision_authority(self):
        sources = {
            "client_certificate": {
                "doc_id": "CC",
                "value_inr": 123_456_789,
                "raw_value": "12,34,56,789",
            },
            "company_certificate": {
                "doc_id": "CCC",
                "value_inr": 123_500_000,
                "raw_value": "INR 12.35 Cr",
            },
            "portfolio": {
                "doc_id": "PPP",
                "value_inr": 123_500_000,
                "raw_value": "INR 12.35 Cr",
            },
        }
        selected = reconcile_project(sources)["value_inr"]
        self.assertEqual(selected.value, 123_456_789)
        self.assertEqual(selected.status, "precision_authority")

    def test_performance_grade_requires_an_evidenced_assessment_phrase(self):
        satisfactory, _ = parse_performance_grade(
            "The quality of work has been found\n satisfactory during final inspection."
        )
        conforming, _ = parse_performance_grade(
            "The workmanship conforming to the\n technical specifications was accepted."
        )
        missing, _ = parse_performance_grade("The project reached completion on schedule.")
        self.assertEqual(satisfactory, "Satisfactory")
        self.assertEqual(conforming, "Good")
        self.assertEqual(missing, "")

    def test_exact_math_has_explicit_rounding_and_difference_direction(self):
        self.assertEqual(round_fraction(Fraction(1, 2)), 1)
        self.assertEqual(round_fraction(Fraction(-1, 2)), -1)
        self.assertEqual(percentage(1, 6), 16.67)
        values = [1, 100, 101]
        self.assertEqual(mean_median_gap(values), 33)
        self.assertEqual(mean_median_gap(values, "left_minus_right"), -33)
        self.assertEqual(extract_mean_median_mode("median minus mean"), "right_minus_left")
        self.assertEqual(extract_mean_median_mode("gap between mean and median"), "absolute")

    def test_threshold_boundaries_distinguish_strict_and_inclusive_language(self):
        self.assertEqual(extract_threshold_comparison("strictly above 12 crore"), "gt")
        self.assertEqual(extract_threshold_comparison("at least 12 crore"), "gte")

    def test_common_adjective_does_not_become_a_performance_filter(self):
        self.assertEqual(extract_performance_filter("assets in Good condition"), (None, "exact"))
        self.assertEqual(
            extract_performance_filter("sum the outstanding invoice balance"),
            (None, "exact"),
        )
        self.assertEqual(
            extract_performance_filter("works assessed as Good"),
            ("Good", "exact"),
        )
        self.assertEqual(
            extract_performance_filter("projects with Outstanding performance ratings"),
            ("Outstanding", "exact"),
        )


class SourceConsensusDatabaseTests(unittest.TestCase):
    def test_all_projects_have_provenance_and_unanimous_dates(self):
        db = get_db(DEFAULT_DB_PATH)
        covered = db.fetchall(
            """
            SELECT COUNT(*) FROM (
                SELECT package_number FROM project_fact_evidence
                GROUP BY package_number
                HAVING COUNT(DISTINCT source_type) = 3
            )
            """
        )[0][0]
        conflicts = db.fetchall(
            """
            SELECT COUNT(DISTINCT package_number)
            FROM project_fact_evidence
            WHERE field_name='completion_date' AND consensus_status <> 'unanimous'
            """
        )[0][0]
        self.assertEqual(covered, 155)
        self.assertEqual(conflicts, 0)

    def test_every_receivables_client_is_resolvable_without_a_project(self):
        db = get_db(DEFAULT_DB_PATH)
        resolver = EntityResolver(db)
        retriever = SubtaskRetriever()
        receivables_clients = {
            row[0]
            for row in db.fetchall(
                "SELECT DISTINCT canonical_client FROM workbooks_receivables"
            )
        }
        self.assertTrue(receivables_clients <= set(resolver.clients))
        for client in receivables_clients:
            self.assertEqual(retriever._resolve_client(client, None, None), client)

    def test_all_performance_grades_have_client_certificate_evidence(self):
        db = get_db(DEFAULT_DB_PATH)
        coverage = db.fetchall(
            """
            SELECT COUNT(DISTINCT package_number)
            FROM project_fact_evidence
            WHERE field_name = 'performance_grading'
              AND source_type = 'client_certificate'
              AND agrees_with_selected
            """
        )[0][0]
        self.assertEqual(coverage, 155)

    def test_grade_filtered_aggregate_matches_structured_source_facts(self):
        db = get_db(DEFAULT_DB_PATH)
        client = db.fetchall(
            """
            SELECT canonical_client FROM projects
            WHERE performance_grading = 'Good'
            GROUP BY canonical_client ORDER BY COUNT(*) DESC LIMIT 1
            """
        )[0][0]
        planner = IntentPlanner()
        retriever = SubtaskRetriever()
        plan = planner.plan(
            f"Total the completed works for {client} assessed as Good.",
            "money",
        )
        self.assertEqual(plan.pattern, "doc_filtered_aggregate")
        result = retriever.execute_plan(plan).candidate_answer
        expected = db.fetchall(
            """
            SELECT SUM(contract_value_inr) FROM projects
            WHERE canonical_client = ? AND performance_grading = 'Good'
            """,
            [client],
        )[0][0]
        self.assertEqual(result, expected)

    def test_strict_threshold_excludes_the_boundary_value(self):
        db = get_db(DEFAULT_DB_PATH)
        client, threshold = db.fetchall(
            """
            SELECT canonical_client, contract_value_inr
            FROM projects ORDER BY package_number LIMIT 1
            """
        )[0]
        lakh = threshold / 100_000
        planner = IntentPlanner()
        retriever = SubtaskRetriever()
        strict = planner.plan(
            f"Total {client} projects above {lakh:g} lakh.", "money"
        )
        inclusive = planner.plan(
            f"Total {client} projects worth at least {lakh:g} lakh.", "money"
        )
        self.assertEqual(strict.extra_params["threshold_comparison"], "gt")
        self.assertEqual(inclusive.extra_params["threshold_comparison"], "gte")
        strict_value = retriever.execute_plan(strict).candidate_answer
        inclusive_value = retriever.execute_plan(inclusive).candidate_answer
        boundary_total = db.fetchall(
            """
            SELECT COALESCE(SUM(contract_value_inr), 0) FROM projects
            WHERE canonical_client = ? AND contract_value_inr = ?
            """,
            [client, threshold],
        )[0][0]
        self.assertEqual(inclusive_value - strict_value, boundary_total)

    def test_explicit_client_disambiguates_repeated_project_descriptions(self):
        db = get_db(DEFAULT_DB_PATH)
        resolver = EntityResolver(db)
        groups = defaultdict(list)
        for project in resolver.projects:
            groups[project["title"].split("—", 1)[0].strip()].append(project)
        verified = 0
        for core, projects in groups.items():
            if len(projects) < 2 or not resolver.resolve_project(core).ambiguous:
                continue
            for project in projects:
                resolved = resolver.resolve_project(core, client=project["client"])
                if resolved.value and resolved.value["package_number"] == project["package_number"]:
                    verified += 1
        self.assertGreater(verified, 0)

    def test_candidate_guard_promotes_only_declared_operator_scope(self):
        questions = [
            {"qid": "SYN-DATE", "question": "How many days separate the credential and project completion?", "answer_type": "days"},
            {"qid": "SYN-AVG", "question": "What is the average completed work size?", "answer_type": "money"},
        ]
        rows, stats = promote(
            questions,
            {"SYN-DATE": "10", "SYN-AVG": "100"},
            {"SYN-DATE": "20", "SYN-AVG": "200"},
            {"date_span"},
        )
        self.assertEqual(rows, [("SYN-DATE", "20"), ("SYN-AVG", "100")])
        self.assertEqual(stats, {"unchanged": 0, "promoted": 1, "guarded": 1})


if __name__ == "__main__":
    unittest.main()
