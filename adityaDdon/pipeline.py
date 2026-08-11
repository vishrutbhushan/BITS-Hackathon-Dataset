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
from pathlib import Path
from typing import Dict, Any, List, Union

# Add agent and db directories to path
CURRENT_DIR = Path(__file__).resolve().parent
sys.path.append(str(CURRENT_DIR / "agent"))
sys.path.append(str(CURRENT_DIR / "db"))

from intent_planner import IntentPlanner, ExecutionPlan
from retriever import SubtaskRetriever, RetrievalContext
from reasoner import ReasonerNode

class BidIntelligencePipeline:
    def __init__(self, use_llm: bool = True):
        self.planner = IntentPlanner()
        self.retriever = SubtaskRetriever()
        self.reasoner = ReasonerNode(use_llm=use_llm)

    def answer_question(self, question: str, answer_type: str = "money") -> Dict[str, Any]:
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
            plan = locals().get("plan") or ExecutionPlan(
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

        # Step 3: LLM & Deterministic Reasoning / Computation
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
        }

    def process_file(self, questions_file: Path, output_file: Path) -> List[Dict[str, Any]]:
        with open(questions_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        questions = data.get("questions", data)
        print(f"Processing {len(questions)} questions from {questions_file}...")

        submissions = []
        detailed_results = []

        for i, q in enumerate(questions, 1):
            qid = q.get("qid") or q.get("question_id") or f"Q-{i:04d}"
            q_text = q.get("question", "")
            ans_type = q.get("answer_type", "money")
            gold = q.get("answer", q.get("answer_gold"))

            res = self.answer_question(q_text, answer_type=ans_type)
            ans = res["answer"]

            submissions.append({"question_id": qid, "answer": ans})
            detailed_results.append({
                "qid": qid,
                "question": q_text,
                "gold": gold,
                "answer": ans,
                "pattern": res["pattern"]
            })

            gold_str = f" (Gold: {gold})" if gold is not None else ""
            print(f"  [{i:03d}/{len(questions):03d}] {qid:12s} Pattern: {res['pattern']:22s} Answer: {ans}{gold_str}")

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
    parser.add_argument("--no-llm", action="store_true", help="Run in deterministic math mode without LLM calls")
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
