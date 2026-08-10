#!/usr/bin/env python3
"""
End-to-end orchestration: question(s) in -> submission.jsonl out.

This ties Stages 4-6 together (question understanding -> shape dispatch
-> formatting). Stages 0-2 (raw extraction, field extraction, graph
build) are separate batch jobs you run ONCE against the real corpus --
see scripts/ and the README -- because they don't depend on the
questions at all and shouldn't be redone per-question.

Usage:
    python pipeline.py --db graph.sqlite --questions questions.jsonl --out submission.jsonl

Each line of `questions.jsonl` should look like:
    {"qid": "HV-IC-0001", "question": "..."}
"""
import argparse
import json
import sys
import time

from db.schema import get_connection
from understanding.entity_match import Gazetteer
from understanding import local_llm
from shapes.dispatcher import REGISTRY
from format_answer import format_answer


def answer_question(con, gazetteer, question_text: str, log=None):
    """Run Stage 4 (understand) -> Stage 5 (execute) -> Stage 6 (format)
    for a single question. Returns (answer, meta) where meta records
    which path was used and the execution trace, for debugging.
    """
    parsed = local_llm.parse_question(question_text, gazetteer)
    used = "openrouter"

    if not local_llm.validate(parsed, gazetteer):
        raise ValueError(f"OpenRouter model output failed validation: {parsed}")


    shape = parsed["shape"]
    fn = REGISTRY[shape]

    # Map the parsed fields onto each shape function's actual kwargs.
    # This mapping is the one place that has to know each shape's
    # signature -- kept centralized here rather than scattered.
    kwargs_by_shape = {
        "absence": {"client_name": parsed["client_name"]},
        "referenced_share": {"client_name": parsed["client_name"]},
        "avg_work_size": {"client_name": parsed["client_name"]},
        "rank_value": {"client_name": parsed["client_name"]},
        "gap_to_threshold": {"client_name": parsed["client_name"], "threshold_rupees": parsed["threshold_rupees"]},
        "threshold_aggregate": {"client_name": parsed["client_name"], "threshold_rupees": parsed["threshold_rupees"]},
        "doc_filtered_aggregate": {"client_name": parsed["client_name"], "grading": parsed["grading"]},
        "exclusion_aggregate": {"client_name": parsed["client_name"], "exclude_category": parsed["category_to_exclude"]},
        "role_split": {"client_name": parsed["client_name"], "role": parsed["role"]},
        "distinct_count": {"engineer_name": parsed["engineer_name"]},
        "hop_aggregate": {"engineer_name": parsed["engineer_name"], "client_name": parsed["client_name"]},
        "temporal_chain": {"engineer_name": parsed["engineer_name"], "issue_date": parsed.get("issue_date")},
        "date_span": {
            "engineer_name": parsed["engineer_name"],
            "cert_type": parsed.get("cert_type", "PMP"),
            "issue_date": parsed.get("issue_date"),
            "project_name": parsed["project_name"],
        },
    }
    kwargs = kwargs_by_shape.get(shape)
    if kwargs is None:
        raise ValueError(f"no kwargs mapping for shape {shape!r} -- add one as you add shapes")

    raw_answer, trace = fn(con, **kwargs)

    answer_type_by_shape = {
        "absence": "count", "distinct_count": "count",
        "referenced_share": "percent",
        "date_span": "days",
    }
    answer_type = answer_type_by_shape.get(shape, "money")
    final_answer = format_answer(raw_answer, answer_type)

    meta = {"shape": shape, "path": used, "parsed": parsed, "trace": trace}
    if log is not None:
        log.append({"question": question_text, **meta, "answer": final_answer})

    return final_answer, meta


def run(db_path: str, questions_path: str, out_path: str, log_path: str = None, delay: float = 2.0):
    con = get_connection(db_path)
    gazetteer = Gazetteer(con)
    log = [] if log_path else None

    with open(questions_path, encoding="utf-8") as f, open(out_path, "w", encoding="utf-8") as out:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            qid, question = item["qid"], item["question"]
            try:
                answer, meta = answer_question(con, gazetteer, question, log=log)
            except Exception as e:
                # Per the README: an unanswered question scores zero, and a
                # wrong one costs nothing extra -- so on failure, still emit
                # SOMETHING rather than skip the line. 0 is a safe default
                # for counts; adjust if you'd rather guess a typical value.
                print(f"[warn] {qid} failed: {e}", file=sys.stderr)
                answer = 0
            out.write(json.dumps({"qid": qid, "answer": answer}) + "\n")
            if delay > 0:
                time.sleep(delay)

    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, default=str)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to the sqlite graph DB built by graph/build_graph.py")
    ap.add_argument("--questions", required=True, help="questions.jsonl, one {qid, question} per line")
    ap.add_argument("--out", default="submission.jsonl")
    ap.add_argument("--log", default="run_log.json", help="per-question trace for debugging")
    ap.add_argument("--delay", type=float, default=2.0, help="delay in seconds between queries to avoid rate limiting")
    args = ap.parse_args()
    run(args.db, args.questions, args.out, args.log, args.delay)
    print(f"Wrote {args.out}")
