import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "db"))
sys.path.insert(0, str(ROOT / "agent"))

from database import DEFAULT_DB_PATH, get_db
from entity_resolver import EntityResolver
from retriever import SubtaskRetriever
from source_consensus import (
    SourceFact,
    normalize_date,
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
