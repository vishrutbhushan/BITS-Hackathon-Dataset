# Bid-intelligence architecture

## Online path

1. `EntityResolver` loads people, clients, projects, credentials, and state
   names from DuckDB. It resolves exact IDs and graph edges first, generated
   aliases second, conservative token/FTS matches last. Ambiguous short names
   are not silently assigned.
2. `IntentPlanner` maps operation concepts to a typed `ExecutionPlan`. The
   classifier is constrained by `answer_type` and records route confidence,
   alternatives, and diagnostics. It does not enumerate question IDs or
   observed question sentences.
3. `SubtaskRetriever` executes the declared DAG in dependency order. Exact
   canonical keys scope SQL; arithmetic uses dependency outputs rather than
   global mutable state or implicit dates.
4. `ReasonerNode` returns high-confidence deterministic results immediately.
   Low-confidence or incomplete results can spend an LLM call when enabled.
   Submission mode remains deterministic and API-free.
5. `BidIntelligencePipeline` applies type-aware formatting. A failure in one
   question is isolated, enriched with BM25 evidence, and cannot abort the
   batch.

Evidence precedence is: explicit stable ID / package edge, exact canonical
name, unique generated alias, conservative descriptive match, BM25 fallback.
A lower-confidence text match cannot override an exact package-to-client edge.

## Structured facts

The database builder extracts and validates:

- documents and BM25 index;
- 155 projects, client portfolios, credentials, engineers, reference-letter
  presence, and performance bonds;
- receivables, assets, trial balances, tender BOQ rows, and all measurement
  rows;
- audited contract and total revenue for seven fiscal years.

The core deterministic operations cover absence, date spans, distinct counts,
portfolio sum/average/exclusion/threshold/category/role/rank/year operations,
receivables and collection, credential-relative temporal sums, assets, audited
turnover growth, and BOQ quantity variance.

## Verification

```bash
python -m unittest -v test_architecture.py test_regressions.py
python db/validator.py
python pipeline.py --questions ../sample_questions.json \
  --output /tmp/sample.csv --no-llm
python ../evaluate.py --submission /tmp/sample.csv \
  --questions ../sample_questions.json
python run_submission.py
```

`test_architecture.py` uses synthetic/metamorphic questions and SQL-derived
expectations. `validator.py` checks 14 extraction and cross-table invariants.

