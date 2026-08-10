# Bid Intelligence pipeline -- reference implementation

Companion code to the architecture doc from this conversation. Everything
that can run without the real document corpus (parsers, shape dispatcher,
pipeline wiring) is implemented AND TESTED here -- 44 tests, all passing,
validated against the actual answers in `sample_questions.json`. Stages
that need the real `documents/` folder (extraction, graph build) are
implemented with working code but need to be pointed at your corpus and
tuned against what you actually see, per BRIEFING.md's warning that
layout varies across issuers.

## What's proven vs. what needs your corpus

| Component | Status |
|---|---|
| `parsers/money.py`, `dates.py`, `category.py`, `grading.py` | Fully tested against real sample answers (25 tests) |
| `shapes/dispatcher.py` (13 reasoning shapes) | Fully tested against real sample answers (16 tests) |
| `pipeline.py` wiring (understanding -> dispatch -> format) | Integration-tested with a mocked LLM (3 tests) |
| `extraction/field_extractors.py` | Working regex-based extractors, **untuned** -- needs real documents to validate/tighten |
| `graph/build_graph.py` | Working batch-build logic, untested against real data |
| `understanding/local_llm.py`, `fallback.py` | Complete, ready-to-run clients -- **not runnable in this environment**, needs your Ollama install / OpenRouter key |
| `scripts/*.py` | Extraction scripts from earlier in this build -- run these first against your `documents/` folder |

## Run order on your machine

```bash
pip install -r requirements.txt

# 1. Triage: how many pages actually need OCR (you said none, for now)
python scripts/triage_pdfs.py --index document_index.csv --root /path/to/parent/of/documents

# 2. Extract raw text (Stage 0)
python scripts/extract_text.py --index document_index.csv --root /path/to/parent/of/documents --out extracted_text

# 3. Extract workbook data (Stage 0b)
python scripts/extract_workbooks.py --index document_index.csv --root /path/to/parent/of/documents --out workbooks_raw

# 4. Run field extraction over extracted_text/ using extraction/field_extractors.py,
#    feed the results into graph/build_graph.py to populate a sqlite DB.
#    (This glue script isn't written yet -- it depends on how your real
#    doc_id -> doc_type -> text files are laid out. Once you've run steps
#    1-3 and can see the real files, this is a quick script to write:
#    walk extracted_text/<doc_type>/*.txt, call extraction.extract(doc_type, text),
#    collect into the lists graph.build_graph.build_graph() expects.)

# 5. Install Ollama, pull the model:
ollama pull qwen2.5:3b

# 6. Run the full pipeline against your questions:
python pipeline.py --db graph.sqlite --questions questions.jsonl --out submission.jsonl

# 7. Score it:
python evaluate.py --submission submission.jsonl --per-question
```

## Run the test suite (no corpus needed)

```bash
python -m unittest discover -s tests -v
```

All 44 tests should pass -- this proves the money/date/category/grading
parsers and all 13 shape functions are correct against real sample
answers, and that the pipeline wiring (including the OpenRouter
escalation path) is correct, all without touching a single real
document. When you plug in real extraction next, any new failure is
isolated to extraction/graph-building, not this layer.

## Project layout

```
project/
├── parsers/          money.py, dates.py, category.py, grading.py -- canonicalizers, fully tested
├── db/                schema.py -- sqlite schema + upsert helpers
├── extraction/        field_extractors.py -- per-doc-type regex extraction (untuned, needs real docs)
├── graph/              build_graph.py -- Stage 2 batch graph builder
├── shapes/            dispatcher.py -- 13 reasoning-shape functions + registry, fully tested
├── understanding/     entity_match.py (gazetteer/fuzzy match), local_llm.py (Ollama), fallback.py (OpenRouter)
├── scripts/           triage_pdfs.py, extract_text.py, extract_workbooks.py -- Stage 0 batch jobs
├── tests/             44 tests total, all passing
├── pipeline.py        Stage 4->5->6 orchestration, CLI entry point
├── format_answer.py   Stage 6 formatting rules
├── sample_questions.json, document_index.csv  (copied in for convenience)
└── requirements.txt
```

## Extending the shape library

You've got 13 of the ~21 hidden-set shapes covered (everything the
sample questions demonstrate). The remaining ones will very likely
recombine the same primitives already in `shapes/dispatcher.py`
(`_portfolio`, `_works_led`, filter, sum/mean/count/rank) -- some are
probably workbook-driven (BOQ line-item aggregates, ageing-bucket
filters, asset-register lookups), which will need a small extension to
`db/schema.py` to hold workbook rows, plus new shape functions following
the same pattern as the existing ones.

## A note on determinism

Every shape function in `shapes/dispatcher.py` is pure -- same DB state
and same arguments always produce the same answer. The only
non-deterministic step is `understanding/local_llm.py` (and its
fallback), which is why `pipeline.answer_question()` validates the
model's output against the gazetteer before ever calling a shape
function. If a submission ever produces a wrong answer, the trace in
`run_log.json` (written by `pipeline.run()`) tells you immediately
whether the fault was in question-understanding (wrong shape/entities)
or upstream in extraction (right shape/entities, wrong data) -- keep
using that log as you iterate.
