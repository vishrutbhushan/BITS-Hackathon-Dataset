#!/usr/bin/env python3
"""
run_submission.py — Generates the complete official submission CSV for all evaluation questions.
Strictly operates inside adityaDdon/ folder.
"""

import sys
import os
from pathlib import Path

# Add current dir and submodules to path
CURRENT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = CURRENT_DIR.parent
sys.path.append(str(CURRENT_DIR))
sys.path.append(str(CURRENT_DIR / "agent"))
sys.path.append(str(CURRENT_DIR / "db"))

from pipeline import BidIntelligencePipeline

def main():
    questions_file = WORKSPACE_ROOT / "questions.json"
    output_csv = CURRENT_DIR / "submission.csv"

    print("=" * 70)
    print("STARTING FULL EVALUATION RUN ON", questions_file)
    print("OUTPUT DESTINATION:", output_csv)
    print("=" * 70)

    # Both typed architectures execute every question. Equal results skip the
    # model; only disagreements are arbitrated. Any API or schema failure keeps
    # the last stable incumbent's DuckDB result.
    pipeline = BidIntelligencePipeline(use_agentic=True)
    results = pipeline.process_file(questions_file, output_csv)

    print("\n" + "=" * 70)
    print(f"COMPLETED ALL {len(results)} QUESTIONS!")
    print(f"Official submission CSV generated at: {output_csv}")
    print("=" * 70)

if __name__ == "__main__":
    main()
