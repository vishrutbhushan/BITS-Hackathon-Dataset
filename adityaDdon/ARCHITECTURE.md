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
4. `DenseSemanticRouter` uses instruction-aware Qwen3-Embedding-0.6B vectors
   for typed-operator recall and descriptive-project retrieval. Package IDs,
   graph edges, and exact names retain precedence. Corpus embeddings are cached
   by content fingerprint; question vectors remain ephemeral.
5. `legacy/` preserves the last stable typed planner/retriever as an independent
   incumbent. `AgreementEnsemble` executes both relational architectures. A
   dense alternate must pass operator preconditions and compile into the same
   typed DuckDB tool boundary before it becomes a candidate.
6. Qwen3-Reranker-0.6B cross-encodes question/plan pairs. It filters weak dense
   recalls and may lower the generator confidence gate only when its relevance
   score and margin are both strong. Encoder and reranker weights are released
   before the 9B control model runs, keeping peak memory bounded on a 16 GB Mac.
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
python -m unittest -v test_architecture.py test_regressions.py
python db/validator.py
python pipeline.py --questions ../sample_questions.json \
  --output /tmp/sample.csv --no-llm
python ../evaluate.py --submission /tmp/sample.csv \
  --questions ../sample_questions.json
python pipeline.py --questions ../questions.json \
  --output submission_sota_hybrid.csv
```

`test_architecture.py` uses synthetic/metamorphic questions and SQL-derived
expectations, including model-outage fallback, zero-call agreement,
position-bias reversal, dense paraphrase routing, adversarial cross-encoder
pairs, and asset/project polysemy. `validator.py` checks 14 extraction and
cross-table invariants.
