#!/usr/bin/env python3
"""
test_pipeline.py — Comprehensive test runner for the DuckDB DAG Bid Intelligence Architecture in adityaDdon/
Runs sample questions through the pipeline and scores with evaluate.py.
"""

import sys
import subprocess
from pathlib import Path
from pipeline import BidIntelligencePipeline

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_JSON = WORKSPACE_ROOT / "sample_questions.json"
SUBMISSION_CSV = Path(__file__).resolve().parent / "sample_submission.csv"
EVALUATE_PY = WORKSPACE_ROOT / "evaluate.py"

def run_test():
    print("=" * 70)
    print("RUNNING END-TO-END PIPELINE EVALUATION ON SAMPLE QUESTIONS")
    print("=" * 70)

    pipeline = BidIntelligencePipeline(use_llm=True)
    results = pipeline.process_file(QUESTIONS_JSON, SUBMISSION_CSV)

    print("\n" + "=" * 70)
    print("RUNNING OFFICIAL SCORER (evaluate.py)")
    print("=" * 70)

    cmd = [
        sys.executable,
        str(EVALUATE_PY),
        "--submission", str(SUBMISSION_CSV),
        "--questions", str(QUESTIONS_JSON),
        "--per-question"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout)
    if res.stderr:
        print("STDERR:", res.stderr)

if __name__ == "__main__":
    run_test()
