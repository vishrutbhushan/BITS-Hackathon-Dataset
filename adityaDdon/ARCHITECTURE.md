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
4. `legacy/` preserves the last stable typed planner/retriever as an independent
   incumbent. `AgreementEnsemble` executes both architectures. Equal numeric
   results are accepted without model compute; only genuine disagreements are
   sent to the semantic arbiter.
5. The arbiter sees the question and two typed plan descriptions, never their
   numeric answers. Candidate A/B order is stable-randomized per question. A
   challenger switch needs confidence at or above the configured threshold in
   both an arbitration pass and a position-reversed verification pass. Any
   timeout, malformed JSON, omitted item, or inconsistent vote keeps the stable
   incumbent.
6. `ReasonerNode` only returns a typed execution result. The language model is
   a bounded control plane and cannot calculate, copy, or directly modify an
   answer.
7. `BidIntelligencePipeline` applies type-aware formatting. A failure in one
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

Start the local Qwen control plane in one terminal:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-local-mlx.txt
.venv/bin/hf download mlx-community/Qwen3.5-9B-4bit \
  --local-dir models/Qwen3.5-9B-4bit
./run_local_agent.sh
```

The configuration uses Qwen3.5-9B 4-bit through the loopback MLX-VLM
OpenAI-compatible endpoint. The model arbitrates only the small disagreement
set; the two relational engines remain the answer authorities.
`local_mlx_server.py` disables long reasoning traces because routing requires
constrained JSON, not open-ended deliberation.

```bash
python -m unittest -v test_architecture.py test_regressions.py
python db/validator.py
python pipeline.py --questions ../sample_questions.json \
  --output /tmp/sample.csv --no-llm
python ../evaluate.py --submission /tmp/sample.csv \
  --questions ../sample_questions.json
python pipeline.py --questions ../questions.json \
  --output submission_ensemble.csv
```

`test_architecture.py` uses synthetic/metamorphic questions and SQL-derived
expectations, including model-outage fallback, zero-call agreement, and
position-bias reversal. `validator.py` checks 14 extraction and cross-table
invariants.
