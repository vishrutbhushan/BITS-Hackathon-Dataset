"""Synthetic and architecture-level tests independent of evaluation examples."""

import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace


CURRENT_DIR = Path(__file__).resolve().parent
sys.path[:0] = [str(CURRENT_DIR), str(CURRENT_DIR / "agent"), str(CURRENT_DIR / "db")]

from entity_resolver import EntityResolver
from agentic_controller import AgenticController
from intent_planner import ExecutionPlan, IntentPlanner
from pipeline import BidIntelligencePipeline
from reasoner import ReasonerNode
from retriever import RetrievalContext, SubtaskRetriever
from database import get_db
from db.build_database import normalize_inr


class ArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = get_db()
        cls.entities = EntityResolver(cls.db)
        cls.planner = IntentPlanner()
        cls.retriever = SubtaskRetriever()

    def test_client_aliases_are_derived_and_specific(self):
        cases = {
            "PWD Gujarat": "Public Works Department, Govt of Gujarat",
            "Gujarat PWD account": "Public Works Department, Govt of Gujarat",
            "PHEG Odisha": "Public Health Engineering Dept, Odisha",
            "Jal Nigam account in Gujarat": "Jal Nigam, Gujarat",
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(self.entities.resolve_client(phrase).value, expected)

    def test_ambiguous_first_name_is_not_selected_arbitrarily(self):
        plan = self.planner.plan("How many work categories has Meera led?", "count")
        self.assertIsNone(plan.anchor_person)
        self.assertLess(plan.confidence, 0.5)
        self.assertTrue(any("ambiguous people" in item for item in plan.diagnostics))

    def test_package_edge_disambiguates_a_shared_first_name(self):
        package, lead = self.db.fetchall(
            """
            SELECT package_number, project_lead
            FROM projects
            WHERE split_part(project_lead, ' ', 1) IN (
                SELECT split_part(full_name, ' ', 1)
                FROM engineers GROUP BY 1 HAVING COUNT(*) > 1
            )
            ORDER BY package_number LIMIT 1
            """
        )[0]
        first = lead.split()[0]
        plan = self.planner.plan(
            f"How many days from {first}'s PMP issue to completion of Pkg-{package}?",
            "days",
        )
        self.assertEqual(plan.anchor_person, lead)
        self.assertEqual(plan.anchor_package_num, package)

    def test_credential_id_resolves_holder_without_name(self):
        credential_id, person = self.db.fetchall(
            "SELECT credential_id, engineer_name FROM credentials ORDER BY credential_id LIMIT 1"
        )[0]
        resolution = self.entities.resolve_person(f"Use credential {credential_id} for this audit")
        self.assertEqual(resolution.value, person)
        self.assertEqual(resolution.confidence, 1.0)

    def test_temporal_dag_uses_selected_credential_dependency(self):
        person, issue_date = self.db.fetchall(
            """
            SELECT engineer_name, issue_date FROM credentials
            WHERE credential_type = 'Six Sigma Black Belt'
            ORDER BY engineer_name LIMIT 1
            """
        )[0]
        question = f"Sum the work completed by {person} after the Six Sigma certification was issued."
        plan = self.planner.plan(question, "money")
        self.assertEqual(plan.pattern, "temporal_chain")
        self.assertEqual(plan.subtasks[1].depends_on, ["T1"])
        context = self.retriever.execute_plan(plan)
        expected = self.db.fetchall(
            """
            SELECT COALESCE(SUM(contract_value_inr), 0) FROM projects
            WHERE lower(project_lead) = lower(?) AND completion_date > ?
            """,
            [person, issue_date],
        )[0][0]
        self.assertEqual(context.candidate_answer, expected)

    def test_target_gap_is_directional_and_never_reports_overshoot(self):
        client = self.db.fetchall(
            "SELECT canonical_client FROM clients ORDER BY total_value_inr DESC LIMIT 1"
        )[0][0]
        plan = self.planner.plan(
            f"How much more is needed for {client} to reach the target of INR 1 Cr?",
            "money",
        )
        self.assertEqual(plan.pattern, "gap_to_threshold")
        self.assertEqual(self.retriever.execute_plan(plan).candidate_answer, 0)

    def test_explicit_category_subset_is_not_discarded(self):
        client = self.db.fetchall(
            """
            SELECT canonical_client FROM projects
            WHERE category IN ('Tunnels', 'Irrigation')
            GROUP BY canonical_client HAVING COUNT(DISTINCT category) = 2
            LIMIT 1
            """
        )[0][0]
        plan = self.planner.plan(
            f"Give the combined value of tunnels and irrigation for {client}.",
            "money",
        )
        self.assertEqual(plan.pattern, "category_aggregate")
        expected = self.db.fetchall(
            """
            SELECT SUM(contract_value_inr) FROM projects
            WHERE canonical_client = ? AND category IN ('Tunnels', 'Irrigation')
            """,
            [client],
        )[0][0]
        self.assertEqual(self.retriever.execute_plan(plan).candidate_answer, expected)

    def test_percentage_formatter_keeps_small_public_scale_value(self):
        plan = ExecutionPlan("synthetic", "collection_rate", target_metric="percent", confidence=1.0)
        context = RetrievalContext(
            plan=plan,
            candidate_answer=0.5,
            confidence=1.0,
            is_complete=True,
        )

        class PlannerStub:
            def plan(self, *_args, **_kwargs):
                return plan

        class RetrieverStub:
            def execute_plan(self, _plan):
                return context

        pipeline = BidIntelligencePipeline.__new__(BidIntelligencePipeline)
        pipeline.planner = PlannerStub()
        pipeline.retriever = RetrieverStub()
        pipeline.reasoner = ReasonerNode(use_llm=False)
        self.assertEqual(pipeline.answer_question("synthetic", "percent")["answer"], 0.5)

    def test_agent_controls_plan_but_cannot_supply_the_answer(self):
        client = self.db.fetchall(
            "SELECT canonical_client FROM clients ORDER BY total_value_inr DESC LIMIT 1"
        )[0][0]
        question = f"Return the average project value for {client}."
        seed = self.planner.plan(question, "money")
        seed.confidence = 0.1
        seed_context = self.retriever.execute_plan(seed)

        class FakeCompletions:
            def __init__(self):
                self.responses = [
                    {
                        "action": "replan",
                        "pattern": "hop_aggregate",
                        "confidence": 0.91,
                        "slots": {"client": client},
                        # This field is outside the schema and must be ignored.
                        "answer": 999,
                    },
                    {"choice": "agent", "confidence": 0.9},
                ]

            def create(self, **_kwargs):
                content = __import__("json").dumps(self.responses.pop(0))
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
                )

        fake = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
        controller = AgenticController(
            self.planner, self.retriever, enabled=True, client=fake, max_steps=1
        )
        outcome = controller.refine(seed, seed_context)
        expected = self.db.fetchall(
            "SELECT SUM(contract_value_inr) FROM projects WHERE canonical_client = ?",
            [client],
        )[0][0]
        self.assertEqual(outcome.context.candidate_answer, expected)
        self.assertNotEqual(outcome.context.candidate_answer, 999)
        self.assertEqual(outcome.source, "agent_replanned")

    def test_malformed_agent_output_falls_back_to_seed(self):
        plan = ExecutionPlan("synthetic", "hop_aggregate", confidence=0.1)
        context = RetrievalContext(
            plan=plan,
            candidate_answer=11,
            confidence=0.1,
            is_complete=True,
        )

        class BrokenCompletions:
            def create(self, **_kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))]
                )

        fake = SimpleNamespace(chat=SimpleNamespace(completions=BrokenCompletions()))
        controller = AgenticController(
            self.planner, self.retriever, enabled=True, client=fake, max_steps=2
        )
        outcome = controller.refine(plan, context)
        self.assertIs(outcome.context, context)
        self.assertEqual(outcome.source, "agent_fallback_seed")

    def test_agent_ignores_reasoning_trace_before_json(self):
        plan = ExecutionPlan("synthetic", "hop_aggregate", confidence=0.1)
        context = RetrievalContext(
            plan=plan,
            candidate_answer=11,
            confidence=0.1,
            is_complete=True,
        )

        class ThinkingCompletions:
            def create(self, **_kwargs):
                content = '<think>consider {"action":"replan"}</think>\n{"action":"keep"}'
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
                )

        fake = SimpleNamespace(chat=SimpleNamespace(completions=ThinkingCompletions()))
        controller = AgenticController(
            self.planner, self.retriever, enabled=True, client=fake, max_steps=1
        )
        outcome = controller.refine(plan, context)
        self.assertEqual(outcome.source, "agent_confirmed_seed")
        self.assertEqual(outcome.context.candidate_answer, 11)

    def test_high_confidence_execution_spends_no_model_call(self):
        plan = ExecutionPlan("synthetic", "hop_aggregate", confidence=0.99)
        context = RetrievalContext(
            plan=plan,
            candidate_answer=11,
            confidence=0.99,
            is_complete=True,
        )

        class NeverCompletions:
            def create(self, **_kwargs):
                raise AssertionError("high-confidence path should not call the model")

        fake = SimpleNamespace(chat=SimpleNamespace(completions=NeverCompletions()))
        controller = AgenticController(
            self.planner, self.retriever, enabled=True, client=fake
        )
        outcome = controller.refine(plan, context)
        self.assertFalse(outcome.escalated)
        self.assertEqual(outcome.context.candidate_answer, 11)

    def test_operator_confusion_at_old_cutoff_is_escalated(self):
        """A plausible 0.90 route is not sufficiently calibrated to skip review."""
        plan = ExecutionPlan(
            "Add only category alpha plus category beta.",
            "category_diff",
            target_metric="money",
            confidence=0.90,
        )
        context = RetrievalContext(
            plan=plan,
            candidate_answer=0,
            confidence=0.90,
            is_complete=True,
        )
        fake = SimpleNamespace(chat=SimpleNamespace(completions=object()))
        controller = AgenticController(
            self.planner, self.retriever, enabled=True, client=fake
        )
        escalate, reason = controller.should_escalate(plan, context)
        self.assertTrue(escalate)
        self.assertEqual(reason, "low_confidence")

    def test_loopback_agent_needs_no_remote_api_key(self):
        with patch.dict(
            "os.environ",
            {
                "AGENTIC_BASE_URL": "http://127.0.0.1:8080",
                "AGENTIC_API_KEY": "",
                "OPENROUTER_API_KEY": "",
            },
            clear=False,
        ):
            controller = AgenticController(
                self.planner, self.retriever, enabled=True
            )
        self.assertTrue(controller.enabled)
        self.assertEqual(controller.base_url, "http://127.0.0.1:8080")

    def test_batch_control_uses_one_call_and_populates_safe_cache(self):
        plans = [
            ExecutionPlan(f"synthetic {index}", "hop_aggregate", target_metric="money", confidence=0.2)
            for index in range(2)
        ]
        contexts = [
            RetrievalContext(
                plan=plan,
                candidate_answer=index + 1,
                confidence=0.2,
                is_complete=True,
            )
            for index, plan in enumerate(plans)
        ]

        class BatchCompletions:
            def __init__(self):
                self.calls = 0

            def create(self, **_kwargs):
                self.calls += 1
                content = __import__("json").dumps({
                    "decisions": [
                        {"id": "0", "action": "keep"},
                        {"id": "1", "action": "keep"},
                    ]
                })
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
                )

        completions = BatchCompletions()
        fake = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        controller = AgenticController(
            self.planner, self.retriever, enabled=True, client=fake
        )
        stats = controller.prepare_batch(list(zip(plans, contexts)))
        self.assertEqual(stats["model_batches"], 1)
        self.assertEqual(completions.calls, 1)
        for plan, context in zip(plans, contexts):
            outcome = controller.refine(plan, context)
            self.assertEqual(outcome.context.candidate_answer, context.candidate_answer)
            self.assertEqual(outcome.source, "agent_confirmed_seed_cache")
        self.assertEqual(completions.calls, 1)

    def test_one_omitted_batch_item_is_repaired_without_discarding_siblings(self):
        plans = [
            ExecutionPlan(f"partial {index}", "hop_aggregate", confidence=0.2)
            for index in range(2)
        ]
        contexts = [
            RetrievalContext(
                plan=plan,
                candidate_answer=index + 1,
                confidence=0.2,
                is_complete=True,
            )
            for index, plan in enumerate(plans)
        ]

        class PartialCompletions:
            def __init__(self):
                self.calls = 0

            def create(self, **_kwargs):
                self.calls += 1
                decisions = (
                    [{"id": "0", "action": "keep"}]
                    if self.calls == 1
                    else [{"id": "0", "action": "keep"}]
                )
                content = __import__("json").dumps({"decisions": decisions})
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
                )

        completions = PartialCompletions()
        fake = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )
        controller = AgenticController(
            self.planner, self.retriever, enabled=True, client=fake
        )
        stats = controller.prepare_batch(list(zip(plans, contexts)))
        first = controller.refine(plans[0], contexts[0])
        second = controller.refine(plans[1], contexts[1])
        self.assertEqual(first.source, "agent_confirmed_seed_cache")
        self.assertEqual(second.source, "agent_confirmed_seed_cache")
        self.assertEqual(stats["repair_batches"], 1)
        self.assertEqual(stats["fallbacks"], 0)
        self.assertEqual(completions.calls, 2)

    def test_turnover_growth_uses_audited_structured_facts(self):
        rows = self.db.fetchall(
            """
            SELECT fiscal_year_start, amount_inr FROM financial_metrics
            WHERE metric = 'total_revenue' ORDER BY fiscal_year_start LIMIT 2
            """
        )
        year1, value1 = rows[0]
        year2, value2 = rows[1]
        plan = self.planner.plan(
            f"What was total revenue growth from FY{year1}-{str(year1 + 1)[-2:]} to FY{year2}-{str(year2 + 1)[-2:]}?",
            "percent",
        )
        self.assertEqual(plan.pattern, "turnover_growth")
        expected = round(((value2 - value1) / value1) * 100, 2)
        self.assertEqual(self.retriever.execute_plan(plan).candidate_answer, expected)

    def test_asset_filters_compile_to_exact_register_query(self):
        plan = self.planner.plan(
            "Total acquisition cost of owned safety-certified plant in Odisha.",
            "money",
        )
        self.assertEqual(plan.pattern, "plant_asset_valuation")
        expected = self.db.fetchall(
            """
            SELECT SUM(cost_inr) FROM workbooks_assets
            WHERE lower(location_state) = 'odisha'
              AND lower(ownership) = 'owned' AND safety_certified = true
            """
        )[0][0]
        self.assertEqual(self.retriever.execute_plan(plan).candidate_answer, expected)

    def test_boq_variance_uses_all_measurement_rows(self):
        contract_id, item_no, tender = self.db.fetchall(
            "SELECT contract_id, item_no, quantity FROM workbooks_boq ORDER BY contract_id, item_no LIMIT 1"
        )[0]
        plan = self.planner.plan(
            f"What is the measured quantity variance for item {item_no} in contract {contract_id}?",
            "money",
        )
        self.assertEqual(plan.pattern, "boq_quantity_variance")
        measured = self.db.fetchall(
            """
            SELECT SUM(quantity_measured) FROM workbooks_boq_measurements
            WHERE contract_id = ? AND item_no = ?
            """,
            [contract_id, item_no],
        )[0][0]
        self.assertEqual(
            self.retriever.execute_plan(plan).candidate_answer,
            round(float(measured) - float(tender), 3),
        )

    def test_money_normalizer_preserves_decimals_and_sign(self):
        self.assertEqual(normalize_inr("INR 1.73 Cr"), 17_300_000)
        self.assertEqual(normalize_inr("58.84 Lakh"), 5_884_000)
        self.assertEqual(normalize_inr("-2,211,907"), -2_211_907)

    def test_routing_is_stable_under_surface_perturbations(self):
        client = self.db.fetchall(
            "SELECT canonical_client FROM clients ORDER BY total_works DESC LIMIT 1"
        )[0][0]
        cases = {
            "ar_outstanding": f"What receivable balance remains unpaid for {client}?",
            "unbilled_gap": f"Compare awarded contract scope with invoiced claims for {client}.",
            "rank_value": f"How much does {client}'s largest project exceed the runner-up?",
            "exclusion_aggregate": f"For {client}, omit tunnels and total the rest.",
            "category_diff": f"Compare tunnel and irrigation totals for {client}.",
            "referenced_share": f"What percentage of {client}'s jobs have testimonial letters?",
        }
        wrappers = [
            lambda value: value,
            lambda value: f"Please confirm — {value}",
            lambda value: value.upper().replace(",", " ; "),
        ]
        for expected, question in cases.items():
            for wrapper in wrappers:
                perturbed = wrapper(question)
                with self.subTest(pattern=expected, question=perturbed):
                    plan = self.planner.plan(
                        perturbed,
                        "percent" if expected == "referenced_share" else "money",
                    )
                    self.assertEqual(plan.pattern, expected)
                    self.assertGreaterEqual(plan.confidence, 0.7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
