#!/usr/bin/env python3
"""
pipeline.py — End-to-End Bid Intelligence Pipeline in adityaDdon/
Coordinates Intent Planner Node (DAG) -> Subtask Retriever Node (DuckDB FTS & SQL) -> Reasoner Node (LLM/Math).
"""

import sys
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

    def answer_question(self, question: str) -> Dict[str, Any]:
        # Step 1: Intent Planning & DAG Decomposition
        plan = self.planner.plan(question)

        # Step 2: Subtask Execution via DuckDB FTS & Relational SQL
        context = self.retriever.execute_plan(plan)

        # Step 3: LLM & Deterministic Reasoning / Computation
        final_answer = self.reasoner.reason(context)

        return {
            "question": question,
            "pattern": plan.pattern,
            "answer": final_answer,
            "candidate": context.candidate_answer,
            "subtasks_count": len(plan.subtasks),
            "evidence": context.evidence_text
        }

    def process_file(self, questions_file: Path, output_file: Path) -> List[Dict[str, Any]]:
        with open(questions_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        questions = data.get("questions", data)
        print(f"Processing {len(questions)} questions from {questions_file}...")

        submissions = []
        detailed_results = []

        for i, q in enumerate(questions, 1):
            qid = q.get("qid", f"Q-{i:04d}")
            q_text = q.get("question", "")
            gold = q.get("answer", q.get("answer_gold"))

            res = self.answer_question(q_text)
            ans = res["answer"]

            submissions.append({"qid": qid, "answer": ans})
            detailed_results.append({
                "qid": qid,
                "question": q_text,
                "gold": gold,
                "answer": ans,
                "pattern": res["pattern"]
            })

            print(f"  [{i:02d}/{len(questions):02d}] {qid:12s} Pattern: {res['pattern']:22s} Answer: {ans} (Gold: {gold})")

        # Write submission JSONL
        with open(output_file, "w", encoding="utf-8") as f:
            for item in submissions:
                f.write(json.dumps(item) + "\n")

        print(f"\nWritten predictions to {output_file}")
        return detailed_results

def main():
    parser = argparse.ArgumentParser(description="Bid Intelligence Pipeline")
    parser.add_argument("--questions", default="../sample_questions.json", help="Path to input questions JSON")
    parser.add_argument("--output", default="sample_submission.jsonl", help="Path to output submission JSONL")
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
