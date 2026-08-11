# Bid-intelligence architecture

## Online path

1. `EntityResolver` loads people, projects, credentials, states, and the union
   of project and receivables clients from DuckDB. It resolves exact IDs and
   graph edges first, generated aliases second, conservative token/FTS matches
   last. Ambiguous short names are not silently assigned.
2. `IntentPlanner` maps operation concepts to a typed `ExecutionPlan`. The
   classifier is constrained by `answer_type` and records route confidence,
   alternatives, and diagnostics. It does not enumerate question IDs or
   observed question sentences.
3. `SubtaskRetriever` executes the declared DAG in dependency order. Exact
   canonical keys scope SQL; arithmetic uses dependency outputs rather than
   global mutable state or implicit dates.
4. The protected production route executes the current and legacy typed
   architectures. `DenseSemanticRouter` and Qwen3-Reranker remain available
   for shadow experiments, but semantic answer overrides are disabled by
   default (`SEMANTIC_OVERRIDES_ENABLED=0`) because their blind submission
   regressed. Package IDs, graph edges, and exact names retain precedence.
5. `legacy/` preserves the last stable typed planner/retriever as an independent
   incumbent. `AgreementEnsemble` executes both relational architectures. In
   opt-in semantic experiments, a dense alternate must still pass operator
   preconditions and compile into the same typed DuckDB tool boundary.
6. The optional Qwen3 embedding/reranker models are loaded sequentially and
   released before the 9B controller, keeping peak memory bounded on a 16 GB
   Mac. They are diagnostics/challengers rather than default answer authority.
7. The arbiter sees the question, typed plan descriptions, and semantic scores,
   never numeric answers. Candidate order is deterministically shifted between
   passes. A challenger must be selected in both passes. Any timeout, malformed
   JSON, omitted item, inconsistent vote, or failed compiler precondition keeps
   the stable incumbent.
8. `ReasonerNode` only returns a typed execution result. The language model is
   a bounded control plane and cannot calculate, copy, or directly modify an
   answer.
9. `BidIntelligencePipeline` applies type-aware formatting. A failure in one
   question is isolated, enriched with BM25 evidence, and cannot abort the
   batch.

Evidence precedence is: explicit stable ID / package edge, exact canonical
name, unique generated alias, conservative descriptive match, BM25 fallback.
A lower-confidence text match cannot override an exact package-to-client edge.

## Structured facts

Before online reasoning, `source_consensus.py` independently parses the client
certificate, company certificate, and portfolio description for every work.
Facts are selected by source agreement, with explicit precision/authority
fallbacks, and written to `project_fact_evidence`. Numeric Indian dates are
parsed day-first unless they are ISO year-first; this prevents silent
month/day transposition. A project fact is therefore auditable back to the
documents that agree with it.

Performance grades are parsed only from explicit assessment language in the
client certificate. All 155 grades retain their supporting phrase in the
evidence table; there is no default grade. The `doc_filtered_aggregate`
operator can therefore prove both the selected boundary and an empty result
without relying on retrieval silence.

The database builder extracts and validates:

- documents and BM25 index;
- 155 projects, client portfolios, credentials, engineers, reference-letter
  presence, and performance bonds;
- receivables, assets, trial balances, tender BOQ rows, and all measurement
  rows;
- audited contract and total revenue for seven fiscal years.

The core deterministic operations cover absence, date spans, distinct counts,
portfolio sum/average/exclusion/threshold/category/role/rank/year operations,
performance-grade filtering, receivables and collection,
credential-relative temporal sums, assets, audited turnover growth, and BOQ
quantity variance. Mean/median comparisons and percentages use exact rational
or decimal arithmetic; strict `above` and inclusive `at least` boundaries are
compiled separately. Output precision is operator-specific.

## Verification

Start the local Qwen control plane in one terminal:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-local-mlx.txt
.venv/bin/hf download mlx-community/Qwen3.5-9B-4bit \
  --local-dir models/Qwen3.5-9B-4bit
.venv/bin/hf download Qwen/Qwen3-Embedding-0.6B \
  --local-dir models/Qwen3-Embedding-0.6B
.venv/bin/hf download Qwen/Qwen3-Reranker-0.6B \
  --local-dir models/Qwen3-Reranker-0.6B
./run_local_agent.sh
```

The configuration uses Qwen3.5-9B 4-bit through the loopback MLX-VLM
OpenAI-compatible endpoint. The model arbitrates only the small disagreement
set; the two relational engines remain the answer authorities.
`local_mlx_server.py` disables long reasoning traces because routing requires
constrained JSON, not open-ended deliberation.

```bash
python -m unittest -v test_source_consensus.py test_architecture.py \
  test_pipeline.py test_regressions.py
python db/validator.py
python pipeline.py --questions ../sample_questions.json \
  --output /tmp/sample.csv --no-llm
python ../evaluate.py --submission /tmp/sample.csv \
  --questions ../sample_questions.json
python pipeline.py --questions ../questions.json \
  --output submission_safe_consensus.csv
```

`test_architecture.py` uses synthetic/metamorphic questions and SQL-derived
expectations, including model-outage fallback, zero-call agreement,
position-bias reversal, dense paraphrase routing, adversarial cross-encoder
pairs, and asset/project polysemy. `test_source_consensus.py` covers source
agreement, wrapped fields, day-first dates, precision precedence,
performance-grade evidence, exact arithmetic, aggregation boundaries, entity
ambiguity, and live provenance coverage. `validator.py` checks 19 extraction
and cross-table invariants.

For a conservative deployment migration, `promote_candidate.py` can retain a
previously accepted output everywhere except typed operators explicitly
authorized by the current architectural change. It never reads labels or
scores; its purpose is to prevent unrelated model variance from being bundled
with a source/parser correction.
