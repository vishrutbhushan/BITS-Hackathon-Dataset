#!/usr/bin/env python3
"""
End-to-end pipeline: question in → answer out.

Architecture (v2 — Text-to-SQL):
  For each question the LLM generates a SQL SELECT that is executed against
  the pre-built graph.sqlite. This replaces the old shape-dispatch system
  entirely: no hardcoded shapes, no keyword classifiers, no entity matching
  heuristics. The LLM sees the full schema and all entity names, so it can
  write correct SQL for any reasoning pattern.

  Fallback: if the SQL is invalid / returns None, we escalate to a RAG prompt
  that asks the LLM to answer directly from retrieved document text.

Usage:
    python pipeline.py --db ../graph.sqlite \\
                       --questions output/questions.jsonl \\
                       --out output/submission.jsonl \\
                       --log logs/run_log.json
"""
import argparse
import json
import logging
import re
import sys
import time

logger = logging.getLogger("vishrut.pipeline")

from db.schema import get_connection
from understanding import local_llm
from format_answer import format_answer


# ── Answer-question entry point ────────────────────────────────────────────────

def answer_question(con, question_text: str, answer_type: str = "money", log=None):
    """Text-to-SQL pipeline for a single question.

    Steps:
      1. Ask LLM to write a SQL query.
      2. Execute the query against the graph DB.
      3. Format the result using the known answer_type.
      4. On any failure → RAG fallback.

    Returns (answer, meta).
    """
    # ── Stage 1: Generate SQL ─────────────────────────────────────────────────
    sql = None
    try:
        sql = local_llm.text_to_sql(question_text, con)
        logger.debug(f"Generated SQL: {sql}")
    except Exception as e:
        logger.warning(f"text_to_sql failed: {e} — falling back to RAG")
        return _rag_fallback(question_text, answer_type, log)

    # ── Stage 2: Execute SQL ──────────────────────────────────────────────────
    try:
        raw = local_llm.execute_sql(con, sql)
        logger.debug(f"SQL result: {raw}")
    except Exception as e:
        logger.warning(f"SQL execution failed ({e}) for: {sql!r} — falling back to RAG")
        return _rag_fallback(question_text, answer_type, log)

    if raw is None:
        logger.warning(f"SQL returned no rows for: {sql!r} — falling back to RAG")
        return _rag_fallback(question_text, answer_type, log)

    # ── Stage 3: Format ───────────────────────────────────────────────────────
    try:
        final_answer = format_answer(raw, answer_type)
    except Exception as e:
        logger.warning(f"format_answer failed ({e}), returning raw value")
        final_answer = raw

    meta = {"shape": "text_to_sql", "path": "llm_sql", "sql": sql, "raw": raw}
    if log is not None:
        log.append({"question": question_text, **meta, "answer": final_answer})

    return final_answer, meta


# ── RAG fallback ───────────────────────────────────────────────────────────────

_cached_documents = []


def _rag_fallback(question_text: str, answer_type: str, log=None):
    """Last-resort: retrieve relevant document text and ask LLM to answer."""
    global _cached_documents
    import csv
    from pathlib import Path

    workspace_root = Path(__file__).resolve().parent.parent

    # Load document corpus once
    if not _cached_documents:
        index_csv = workspace_root / "document_index.csv"
        extracted_text_root = workspace_root / "extracted_text"
        if index_csv.exists() and extracted_text_root.exists():
            with open(index_csv, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    txt_path = extracted_text_root / row["doc_type"] / f"{row['doc_id']}.txt"
                    if txt_path.exists():
                        _cached_documents.append({
                            "doc_id": row["doc_id"],
                            "doc_type": row["doc_type"],
                            "text": txt_path.read_text(encoding="utf-8"),
                            "filename": row["filename"],
                        })

    # Score documents by keyword overlap with the question
    words = re.findall(r'\b[A-Za-z0-9]{3,}\b', question_text)
    entities = re.findall(r'\b[A-Z][a-z0-9]+\b', question_text)
    scored = []
    for doc in _cached_documents:
        doc_low = doc["text"].lower()
        score = sum(1 for w in words if w.lower() in doc_low)
        score += sum(3 for ent in entities if ent in doc["text"])
        scored.append((doc, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    top_docs = [d for d, _ in scored[:5]]

    context = "\n\n".join(
        f"--- {d['doc_id']} ({d['doc_type']}) ---\n{d['text'][:2000]}"
        for d in top_docs
    )

    type_hint = {
        "money": "Return the answer as a plain integer number of rupees.",
        "percent": "Return the answer as a decimal number out of 100 (e.g. 66.67).",
        "days": "Return the answer as an integer number of days.",
        "count": "Return the answer as an integer count.",
    }.get(answer_type, "Return the answer as a plain number.")

    prompt = f"""You are an expert financial auditor. Answer the question below using ONLY the documents provided.
{type_hint}
Return ONLY a JSON object: {{"answer": <number>}}

QUESTION: {question_text}

DOCUMENTS:
{context}
"""

    try:
        response_text = local_llm.query_llm_direct(prompt)
        m = re.search(r'\{"answer"\s*:\s*([-\d.]+)\}', response_text)
        if m:
            val = float(m.group(1))
            ans = int(val) if val == int(val) else round(val, 2)
        else:
            m2 = re.search(r'([-\d]+(?:\.\d+)?)', response_text)
            ans = float(m2.group(1)) if m2 else 0
            if isinstance(ans, float) and ans == int(ans):
                ans = int(ans)
    except Exception as e:
        logger.error(f"RAG fallback failed: {e}", exc_info=True)
        ans = 0

    meta = {"shape": "rag_fallback", "path": "rag", "top_docs": [d["doc_id"] for d in top_docs]}
    if log is not None:
        log.append({"question": question_text, **meta, "answer": ans})

    return ans, meta


# ── Main run loop ──────────────────────────────────────────────────────────────

def run(db_path: str, questions_path: str, out_path: str,
        log_path: str = None, delay: float = 0.0):
    con = get_connection(db_path)
    log = [] if log_path else None

    with open(questions_path, encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]

    total = len(questions)
    logger.info(f"Loaded {total} questions from {questions_path}")

    with open(out_path, "w", encoding="utf-8") as out:
        for idx, item in enumerate(questions, 1):
            qid = item["qid"]
            question = item["question"]
            answer_type = item.get("answer_type", "money")
            logger.info(f"[{idx}/{total}] {qid}: processing...")
            try:
                answer, meta = answer_question(con, question, answer_type=answer_type, log=log)
                logger.info(f"[{idx}/{total}] {qid}: {meta['shape']} → {answer}")
            except Exception as e:
                logger.error(f"[{idx}/{total}] {qid}: unhandled error: {e}", exc_info=True)
                answer = 0
            out.write(json.dumps({"qid": qid, "answer": answer}) + "\n")
            out.flush()
            if delay > 0 and idx < total:
                time.sleep(delay)

    if log_path:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, default=str)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", default=None)
    ap.add_argument("--delay", type=float, default=0.0)
    args = ap.parse_args()

    run(args.db, args.questions, args.out, args.log, args.delay)
