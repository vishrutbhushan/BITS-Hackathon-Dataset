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
import re
import sys
import time
import logging

logger = logging.getLogger("vishrut.pipeline")

# Matches explicit monetary unit language in question text.
# We only extract a threshold_rupees when this appears, to avoid
# mistaking cert IDs / pkg numbers for rupee amounts.
_MONETARY_MARKERS = re.compile(r'\b(crore|lakh|inr|rs\.?|₹)\b', re.IGNORECASE)

from db.schema import get_connection
from understanding.entity_match import Gazetteer
from understanding import local_llm
from shapes.dispatcher import REGISTRY
from format_answer import format_answer


def classify_shape(q_text):
    """Keyword-based shape fallback. Only called when the LLM returns unknown."""
    q = q_text.lower()
    if "lack" in q or "no client reference" in q or "no reference letter" in q:
        return "absence"
    # Require explicit percentage language; 'share' alone is too broad
    if "percent" in q or "percentage" in q or "collection figure" in q or "out of one hundred" in q or "out of 100" in q:
        return "referenced_share"
    if "days" in q or "interval" in q or "exact interval" in q:
        return "date_span"
    if "distinct" in q or "different categories" in q or "separate internal" in q:
        return "distinct_count"
    if "after" in q and ("completed" in q or "wrapped up" in q or "finished" in q or "issued" in q or "issuance" in q or "credential" in q):
        return "temporal_chain"
    # category_diff must be checked before exclusion_aggregate
    if "value difference between" in q or "difference between" in q and "scope" in q:
        return "category_diff"
    if "excluding" in q or "exclude" in q:
        return "exclusion_aggregate"
    if "additional work" in q or "credential target" in q:
        return "gap_to_threshold"
    if "second largest" in q or "second-largest" in q:
        return "rank_value"
    if "as prime" in q or "as subcontractor" in q or "as joint venture" in q:
        return "role_split"
    if "exceed" in q or "crossing" in q or "hitting" in q:
        return "threshold_aggregate"
    if "mean" in q or "average" in q:
        return "avg_work_size"
    if "grading" in q or "assessed as" in q:
        return "doc_filtered_aggregate"
    if "combined value" in q or "total value" in q or "aggregate value" in q:
        return "hop_aggregate"
    return "unknown"



def _resolve_client_from_project(con, project_name):
    if not project_name:
        return None
    row = con.execute(
        "SELECT c.name FROM projects p JOIN clients c ON p.client_id = c.client_id WHERE p.name = ?",
        (project_name,)
    ).fetchone()
    if row:
        return row[0]
    # Fallback to fuzzy match
    row_fuzzy = con.execute(
        "SELECT c.name FROM projects p JOIN clients c ON p.client_id = c.client_id WHERE p.name LIKE ?",
        (f"%{project_name}%",)
    ).fetchone()
    if row_fuzzy:
        return row_fuzzy[0]
    return None


def _resolve_engineer_from_project(con, project_name):
    if not project_name:
        return None
    row = con.execute(
        "SELECT e.name FROM projects p JOIN engineers e ON p.engineer_id = e.engineer_id WHERE p.name = ?",
        (project_name,)
    ).fetchone()
    if row:
        return row[0]
    row_fuzzy = con.execute(
        "SELECT e.name FROM projects p JOIN engineers e ON p.engineer_id = e.engineer_id WHERE p.name LIKE ?",
        (f"%{project_name}%",)
    ).fetchone()
    if row_fuzzy:
        return row_fuzzy[0]
    return None


def answer_question(con, gazetteer, question_text: str, log=None):
    """Run Stage 4 (understand) -> Stage 5 (execute) -> Stage 6 (format)
    for a single question. Returns (answer, meta) where meta records
    which path was used and the execution trace, for debugging.
    """
    parsed = local_llm.parse_question(question_text, gazetteer)
    used = "local"

    # 1. Rule-based shape classification: only kicks in when the LLM returns
    #    unknown or null, so the LLM is always the primary signal.
    if parsed.get("shape") in (None, "unknown"):
        pred_shape = classify_shape(question_text)
        if pred_shape != "unknown":
            parsed["shape"] = pred_shape
            used = "keyword_fallback"

    # 2. Multi-hop Entity Resolution from Project Name (Unconditionally overwrite if project_name is present)
    if parsed.get("project_name"):
        resolved_client = _resolve_client_from_project(con, parsed["project_name"])
        if resolved_client:
            parsed["client_name"] = resolved_client
        resolved_eng = _resolve_engineer_from_project(con, parsed["project_name"])
        if resolved_eng:
            parsed["engineer_name"] = resolved_eng

    # 3. Rule-Based Threshold Money Extraction: only override when the question
    #    contains explicit monetary unit language. Bare numbers in questions are
    #    usually cert IDs or pkg numbers, NOT rupee thresholds.
    if _MONETARY_MARKERS.search(question_text):
        from parsers.money import parse_spoken_amount
        extracted_money = parse_spoken_amount(question_text)
        if extracted_money is not None:
            parsed["threshold_rupees"] = extracted_money

    # 4. Entity Validation (Warn rather than crash, fall back to RAG if invalid)
    if not local_llm.validate(parsed, gazetteer):
        logger.warning(f"Validation failed for {parsed}, falling back to RAG...")
        return run_rag_fallback(question_text, log)

    shape = parsed["shape"]
    if shape == "unknown" or shape not in REGISTRY:
        return run_rag_fallback(question_text, log)

    fn = REGISTRY[shape]

    # Map the parsed fields onto each shape function's actual kwargs.
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
        # category_diff: absolute value difference between two category totals for a client.
        # The LLM should populate category_a and category_b from the question.
        "category_diff": {
            "client_name": parsed["client_name"],
            "category_a": parsed.get("category_a"),
            "category_b": parsed.get("category_to_exclude"),  # reuse slot for cat_b if LLM fills it
        },
    }
    kwargs = kwargs_by_shape.get(shape)
    if kwargs is None:
        raise ValueError(f"no kwargs mapping for shape {shape!r} -- add one as you add shapes")

    try:
        raw_answer, trace = fn(con, **kwargs)
    except Exception as e:
        logger.warning(f"Dispatcher failed for shape {shape}: {e}, falling back to RAG...")
        return run_rag_fallback(question_text, log)

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


cached_documents = []

def run_rag_fallback(question_text, log=None):
    global cached_documents
    import os
    import csv
    import re
    from pathlib import Path
    
    workspace_root = Path("c:/Code/BITS-Hackathon-Dataset")
    
    # 1. Load documents if not cached
    if not cached_documents:
        index_csv = workspace_root / "document_index.csv"
        extracted_text_root = workspace_root / "extracted_text"
        if index_csv.exists() and extracted_text_root.exists():
            with open(index_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    doc_id = row["doc_id"]
                    doc_type = row["doc_type"]
                    txt_path = extracted_text_root / doc_type / f"{doc_id}.txt"
                    if txt_path.exists():
                        cached_documents.append({
                            "doc_id": doc_id,
                            "doc_type": doc_type,
                            "text": txt_path.read_text(encoding="utf-8"),
                            "filename": row["filename"]
                        })

    # 2. Retrieve top matching documents
    words = re.findall(r'\b[A-Za-z0-9]{3,}\b', question_text)
    entities = re.findall(r'\b[A-Z][a-z0-9]+\b', question_text)
    
    scored = []
    for doc in cached_documents:
        score = 0
        doc_text_lower = doc["text"].lower()
        for w in words:
            if w.lower() in doc_text_lower:
                score += 1
        for ent in entities:
            if ent in doc["text"]:
                score += 3
                
        # Boost specific document types based on question content
        q_low = question_text.lower()
        if "bill" in q_low and "bill" in doc["doc_type"]:
            score += 8
        if "ledger" in q_low and ("ledger" in doc["doc_type"] or "workbook" in doc["doc_type"]):
            score += 8
        if "invoice" in q_low and "invoice" in doc["doc_type"]:
            score += 8
        if "bank" in q_low and "bank" in doc["doc_type"]:
            score += 8
        if "annual" in q_low and "annual" in doc["doc_type"]:
            score += 8
            
        scored.append((doc, score))
        
    scored.sort(key=lambda x: x[1], reverse=True)
    top_docs = [x[0] for x in scored[:4]] # Get top 4 documents
    
    # 3. Build context
    context_parts = []
    for doc in top_docs:
        context_parts.append(f"--- Document ID: {doc['doc_id']} | Type: {doc['doc_type']} | Filename: {doc['filename']} ---\n{doc['text']}")
    context_text = "\n\n".join(context_parts)
    
    # 4. Prompt the LLM
    prompt = f"""You are an expert financial auditor answering questions on a construction document estate.

QUESTION:
{question_text}

RETRIEVED RELEVANT DOCUMENTS:
{context_text}

INSTRUCTIONS:
1. Analyze the retrieved documents and identify the values needed to answer the question.
2. Carry out any required calculations/arithmetic precisely.
3. Return ONLY a valid JSON object with key "answer" containing the single plain number answer (no units, no commas, no formatting).
   - If money, output plain integer rupees (e.g. 537933333, not 53.79 Cr).
   - If percentage, output number out of 100 (e.g. 33.33, not 0.3333).
   - If days, output integer number of days.
   - If count, output integer count.
   
Example: {{"answer": 537933333}}
"""
    try:
        from understanding.local_llm import query_llm_direct
        response_text = query_llm_direct(prompt)
        
        # Parse answer
        m_json = re.search(r'\{.*?"answer"\s*:\s*([-\d.]+).*?\}', response_text, re.S)
        if m_json:
            ans_val = float(m_json.group(1))
            final_answer = int(ans_val) if ans_val.is_integer() else round(ans_val, 2)
        else:
            m_num = re.search(r'([-\d]+(?:\.\d+)?)', response_text)
            if m_num:
                ans_val = float(m_num.group(1))
                final_answer = int(ans_val) if ans_val.is_integer() else round(ans_val, 2)
            else:
                final_answer = 0
    except Exception as e:
        logger.error(f"[RAG Fallback] Error: {e}", exc_info=True)
        final_answer = 0
        
    meta = {"shape": "rag_fallback", "path": "rag_fallback", "top_docs": [d["doc_id"] for d in top_docs]}
    if log is not None:
        log.append({"question": question_text, **meta, "answer": final_answer})
        
    return final_answer, meta


def run(db_path: str, questions_path: str, out_path: str, log_path: str = None, delay: float = 2.0):
    con = get_connection(db_path)
    gazetteer = Gazetteer(con)
    log = [] if log_path else None

    # Load all questions to get total count
    with open(questions_path, encoding="utf-8") as f:
        questions = [json.loads(line.strip()) for line in f if line.strip()]
        
    total_questions = len(questions)
    logger.info(f"Loaded {total_questions} questions from {questions_path}")

    with open(out_path, "w", encoding="utf-8") as out:
        for index, item in enumerate(questions, 1):
            qid, question = item["qid"], item["question"]
            logger.info(f"[{index}/{total_questions}] {qid}: Processing...")
            try:
                answer, meta = answer_question(con, gazetteer, question, log=log)
                logger.info(f"[{index}/{total_questions}] {qid}: Success! Shape: {meta['shape']} -> Answer: {answer}")
            except Exception as e:
                logger.error(f"[{index}/{total_questions}] {qid}: Failed! Error: {e}", exc_info=True)
                answer = 0
            out.write(json.dumps({"qid": qid, "answer": answer}) + "\n")
            out.flush()
            if delay > 0 and index < total_questions:
                time.sleep(delay)

    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, default=str)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to the sqlite graph DB built by graph/build_graph.py")
    ap.add_argument("--questions", required=True, help="questions.jsonl, one {qid, question} per line")
    ap.add_argument("--out", default="submission.jsonl")
    ap.add_argument("--log", default="run_log.json", help="per-question trace for debugging")
    ap.add_argument("--delay", type=float, default=2.0, help="delay in seconds between queries to avoid rate limiting")
    args = ap.parse_args()
    run(args.db, args.questions, args.out, args.log, args.delay)
    logger.info(f"Wrote {args.out}")
