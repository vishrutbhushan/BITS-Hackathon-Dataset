#!/usr/bin/env python3
"""Promote only behavior changes authorized by an architectural migration.

This is a deployment safety gate, not an answer selector.  It never sees gold
answers or scores.  Given the last accepted output and a newly generated
candidate, it retains the accepted answer unless the candidate's typed
operator belongs to an explicitly declared migration scope.  The same policy
can be used for any question set and prevents unrelated model nondeterminism
from hitchhiking on a source/parser change.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

from pipeline import BidIntelligencePipeline


def read_answers(path: Path) -> Dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    answers = {row["question_id"]: row["answer"] for row in rows}
    if len(answers) != len(rows):
        raise ValueError(f"Duplicate question_id in {path}")
    for question_id, answer in answers.items():
        try:
            numeric = float(answer)
        except ValueError as exc:
            raise ValueError(f"Non-numeric answer for {question_id} in {path}") from exc
        if not math.isfinite(numeric):
            raise ValueError(f"Non-finite answer for {question_id} in {path}")
    return answers


def promote(
    questions: Sequence[Mapping[str, object]],
    accepted: Mapping[str, str],
    proposed: Mapping[str, str],
    allowed_patterns: Iterable[str],
) -> tuple[list[tuple[str, str]], Dict[str, int]]:
    allowed = set(allowed_patterns)
    pipeline = BidIntelligencePipeline(use_agentic=False)
    promoted = []
    stats = {"unchanged": 0, "promoted": 0, "guarded": 0}
    seen = set()
    for index, question in enumerate(questions, 1):
        question_id = str(question.get("qid") or question.get("question_id") or f"Q-{index:04d}")
        seen.add(question_id)
        if question_id not in accepted or question_id not in proposed:
            raise ValueError(f"Missing question_id {question_id} in accepted/proposed output")
        old_answer = accepted[question_id]
        new_answer = proposed[question_id]
        if old_answer == new_answer:
            selected = old_answer
            stats["unchanged"] += 1
        else:
            answer_type = str(question.get("answer_type") or "money")
            plan = pipeline.planner.plan(str(question.get("question") or ""), answer_type)
            if plan.pattern in allowed:
                selected = new_answer
                stats["promoted"] += 1
            else:
                selected = old_answer
                stats["guarded"] += 1
        promoted.append((question_id, selected))
    if set(accepted) != seen or set(proposed) != seen:
        raise ValueError("Question IDs in CSVs do not exactly match the question set")
    return promoted, stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--accepted", type=Path, required=True)
    parser.add_argument("--proposed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-pattern", action="append", default=[])
    args = parser.parse_args()

    payload = json.loads(args.questions.read_text(encoding="utf-8"))
    questions = payload.get("questions", payload)
    rows, stats = promote(
        questions,
        read_answers(args.accepted),
        read_answers(args.proposed),
        args.allow_pattern,
    )
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("question_id", "answer"))
        writer.writerows(rows)
    print(f"Promotion summary: {stats}; wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
