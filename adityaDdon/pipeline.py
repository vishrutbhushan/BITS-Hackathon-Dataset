#!/usr/bin/env python3
"""
pipeline.py — End-to-End Bid Intelligence Pipeline in adityaDdon/
Coordinates Intent Planner Node (DAG) -> Subtask Retriever Node (DuckDB FTS & SQL) -> Reasoner Node (LLM/Math).
Produces official submission CSV format:
    question_id,answer
    HV-IC-0001,2942400000
    HV-IC-0002,1516600000
    HV-IC-0003,90.19
"""

import sys
import csv
import json
import argparse
from collections import Counter
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

# Add agent and db directories to path
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.append(str(CURRENT_DIR / "agent"))
sys.path.append(str(CURRENT_DIR / "db"))

from intent_planner import IntentPlanner, ExecutionPlan
from retriever import SubtaskRetriever, RetrievalContext
from reasoner import ReasonerNode
from agentic_controller import AgenticController
from ensemble_controller import AgreementEnsemble

class BidIntelligencePipeline:
    def __init__(
        self,
        use_llm: bool = True,
        use_agentic: Optional[bool] = None,
        agentic_client: Optional[Any] = None,
    ):
        self.planner = IntentPlanner()
        self.retriever = SubtaskRetriever()
        # ``use_llm`` remains a compatibility argument, but model compute now
        # lives entirely in the control plane.  The final answer is always a
        # typed DuckDB/arithmetic result, never free-form model output.
        agentic_enabled = use_llm if use_agentic is None else use_agentic
        self.controller = AgenticController(
            self.planner,
            self.retriever,
            enabled=agentic_enabled,
            client=agentic_client,
        )
        self.ensemble = (
            AgreementEnsemble(self.controller) if agentic_enabled else None
        )
        self.reasoner = ReasonerNode(use_llm=False)

    def _seed_execution(
        self, question: str, answer_type: str
    ) -> tuple[ExecutionPlan, RetrievalContext]:
        """Create and execute the deterministic seed without aborting a batch."""
        plan = None
        # Step 1: Intent Planning & DAG Decomposition with answer_type hard constraint
        try:
            plan = self.planner.plan(question, answer_type=answer_type)

            # Step 2: Subtask Execution via DuckDB FTS & Relational SQL
            context = self.retriever.execute_plan(plan)
        except Exception as exc:
            # One malformed or genuinely ambiguous question must not abort the
            # whole submission.  Preserve the failure as low-confidence
            # evidence so an enabled LLM can recover; deterministic batch mode
            # still emits a numeric fallback and continues.
            plan = plan or ExecutionPlan(
                question=question,
                pattern="generic_multi_hop",
                target_metric=answer_type,
                confidence=0.0,
                diagnostics=[f"planning failure: {exc}"],
            )
            fallback_lines = [f"Deterministic execution failed: {exc}"]
            try:
                for hit in self.retriever.db.search_fts(question, limit=5):
                    fallback_lines.append(
                        f"FTS [{hit['doc_id']} / {hit['doc_type']}]: {hit['content'][:500]}"
                    )
            except Exception as retrieval_exc:
                fallback_lines.append(f"Fallback retrieval also failed: {retrieval_exc}")
            context = RetrievalContext(
                plan=plan,
                evidence_text="\n".join(fallback_lines),
                confidence=0.0,
                is_complete=False,
                warnings=[str(exc)],
            )
        return plan, context

    def answer_question(self, question: str, answer_type: str = "money") -> Dict[str, Any]:
        plan, context = self._seed_execution(question, answer_type)
        return self._answer_from_seed(question, answer_type, plan, context)

    def _answer_from_seed(
        self,
        question: str,
        answer_type: str,
        plan: ExecutionPlan,
        context: RetrievalContext,
    ) -> Dict[str, Any]:

        # Step 3: preserve independent deterministic agreement and spend model
        # compute only on real architecture disagreements. Any agent failure
        # defaults to the stable incumbent plan, never a free-form answer.
        ensemble = getattr(self, "ensemble", None)
        if ensemble is not None:
            outcome = ensemble.resolve(plan, context)
            plan, context = outcome.plan, outcome.context
            control_source = outcome.source
            control_diagnostics = outcome.diagnostics
        else:
            control_source = "deterministic"
            control_diagnostics = []

        # Step 4: deterministic result selection and type formatting.
        final_answer = self.reasoner.reason(context)

        # Format answer cleanly
        if answer_type == "percent" or plan.pattern in ["referenced_share", "collection_rate"]:
            if isinstance(final_answer, (int, float)):
                # Every percentage-producing executor and the LLM contract use
                # the public 0..100 scale.  Magnitude-based conversion corrupts
                # legitimate small percentages (0.5% became 50%).
                final_answer = round(float(final_answer), 2)
        elif isinstance(final_answer, float) and final_answer.is_integer():
            final_answer = int(final_answer)
        elif isinstance(final_answer, (int, float)) and answer_type in ["money", "days", "count"]:
            final_answer = int(round(final_answer))

        return {
            "question": question,
            "pattern": plan.pattern,
            "answer": final_answer,
            "candidate": context.candidate_answer,
            "subtasks_count": len(plan.subtasks),
            "evidence": context.evidence_text,
            "confidence": context.confidence,
            "complete": context.is_complete,
            "warnings": context.warnings,
            "control_source": control_source,
            "control_diagnostics": control_diagnostics,
        }

    def process_file(self, questions_file: Path, output_file: Path) -> List[Dict[str, Any]]:
        with open(questions_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        questions = data.get("questions", data)
        print(f"Processing {len(questions)} questions from {questions_file}...")

        submissions = []
        detailed_results = []

        # Pre-execute relational candidates serially, then batch only the
        # model control decisions.  This cuts network round trips without
        # sharing a DuckDB connection across worker threads.
        seeded = []
        for q in questions:
            q_text = q.get("question", "")
            ans_type = q.get("answer_type", "money")
            plan, context = self._seed_execution(q_text, ans_type)
            seeded.append((plan, context))
        ensemble = getattr(self, "ensemble", None)
        if ensemble is not None:
            batch_stats = ensemble.prepare_batch(seeded)
            if batch_stats["disagreements"]:
                print(
                    "Ensemble routing: "
                    f"{batch_stats['agreements']} agreements, "
                    f"{batch_stats['disagreements']} disagreements / "
                    f"{batch_stats['total']} total, "
                    f"{batch_stats['arbitration_batches']} arbitration batches, "
                    f"{batch_stats['verification_batches']} verification batches, "
                    f"{batch_stats['current_switches']} two-pass challenger switches."
                )

        for i, (q, seed) in enumerate(zip(questions, seeded), 1):
            qid = q.get("qid") or q.get("question_id") or f"Q-{i:04d}"
            q_text = q.get("question", "")
            ans_type = q.get("answer_type", "money")
            gold = q.get("answer", q.get("answer_gold"))

            res = self._answer_from_seed(q_text, ans_type, *seed)
            ans = res["answer"]

            submissions.append({"question_id": qid, "answer": ans})
            detailed_results.append({
                "qid": qid,
                "question": q_text,
                "gold": gold,
                "answer": ans,
                "pattern": res["pattern"],
                "control_source": res["control_source"],
                "control_diagnostics": res["control_diagnostics"],
            })

            gold_str = f" (Gold: {gold})" if gold is not None else ""
            print(
                f"  [{i:03d}/{len(questions):03d}] {qid:12s} "
                f"Pattern: {res['pattern']:22s} Answer: {ans}{gold_str} "
                f"[{res['control_source']}]"
            )

        control_counts = Counter(item["control_source"] for item in detailed_results)
        print("Control outcomes:", dict(sorted(control_counts.items())))

        # Write output based on extension (.csv vs .jsonl)
        if str(output_file).endswith(".csv"):
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, lineterminator="\n")
                writer.writerow(["question_id", "answer"])
                for item in submissions:
                    writer.writerow([item["question_id"], item["answer"]])
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                for item in submissions:
                    f.write(json.dumps({"qid": item["question_id"], "answer": item["answer"]}) + "\n")

        print(f"\nWritten {len(submissions)} predictions to {output_file}")
        return detailed_results

def main():
    parser = argparse.ArgumentParser(description="Bid Intelligence Pipeline")
    parser.add_argument("--questions", default="../questions.json", help="Path to input questions JSON")
    parser.add_argument("--output", default="submission.csv", help="Path to output submission CSV/JSONL")
    parser.add_argument("--question", help="Single natural language question string")
    parser.add_argument(
        "--no-llm", "--deterministic", dest="no_llm", action="store_true",
        help="Disable the agreement ensemble and run only the current deterministic architecture",
    )
    args = parser.parse_args()

    pipeline = BidIntelligencePipeline(use_llm=not args.no_llm)

    if args.question:
        result = pipeline.answer_question(args.question)
        print("\n" + "=" * 60)
        print("QUESTION:", result["question"])
        print("PATTERN :", result["pattern"])
        print("ANSWER  :", result["answer"])
        print("=" * 60)
    else:
        q_path = Path(args.questions)
        out_path = Path(args.output)
        pipeline.process_file(q_path, out_path)

if __name__ == "__main__":
    main()
