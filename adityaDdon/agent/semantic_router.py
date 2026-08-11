"""Instruction-aware dense retrieval for typed plans and project records.

Exact identifiers and graph edges remain authoritative.  This module supplies
an independent semantic signal only when lexical routing is ambiguous.  It
uses the local Qwen3 embedding checkpoint, batches all evaluation questions,
and releases the model before the larger control-plane model is invoked.
Numeric candidates and labels are never embedded.
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np


OPERATOR_PROTOTYPES: Dict[str, Tuple[str, ...]] = {
    "absence": (
        "Count projects missing a reference letter or completion endorsement.",
        "Number of records where client reference evidence is absent; not a percentage.",
    ),
    "distinct_count": (
        "Count unique construction categories associated with one engineer.",
        "Set cardinality of work types led by a person, not number of projects.",
    ),
    "date_span": (
        "Elapsed calendar days between credential issue and one project completion date.",
        "Project completion date minus professional certificate issue date in days.",
    ),
    "referenced_share": (
        "Percentage of a client's projects having reference letters: referenced count divided by all project count.",
        "Share of completed works supported by client testimonials, on a zero to one hundred scale.",
    ),
    "collection_rate": (
        "Percentage of invoiced receivables collected: received cash divided by invoice amount.",
        "Cash realization rate for claims already billed, on a zero to one hundred scale.",
    ),
    "turnover_growth": (
        "Percentage change in audited total revenue between two fiscal years: new minus old divided by old.",
        "Growth rate of financial-statement turnover across two fiscal periods, not project-value movement.",
    ),
    "ar_outstanding": (
        "Money still due on invoices: sum explicit outstanding receivable ledger balances.",
        "Invoice amount minus cash received, aggregated for a client; not awarded contract value.",
    ),
    "unbilled_gap": (
        "Money difference between awarded portfolio scope and invoiced or claimed amount.",
        "Reconcile contract awards against billing raised; not unpaid receivable balance.",
    ),
    "mean_median_gap": (
        "Money difference between arithmetic mean project value and median project value.",
        "Subtract the median contract size from the average contract size.",
    ),
    "avg_work_size": (
        "Arithmetic mean money value per project: portfolio sum divided by project count.",
        "Average or typical contract size, with no cutoff and no comparison.",
    ),
    "rank_value": (
        "Largest-versus-second rank gap: highest individual project value minus the second highest.",
        "Difference between the biggest job and its runner-up, not mean versus median.",
    ),
    "category_diff": (
        "Money difference between totals for two explicitly named construction categories.",
        "Contrast category A versus category B; subtract their aggregates rather than adding them.",
    ),
    "category_aggregate": (
        "Money sum across only the explicitly selected construction categories.",
        "Combine category A and category B totals; add them rather than compare them.",
    ),
    "exclusion_aggregate": (
        "Money sum of the client portfolio after omitting an explicitly named category.",
        "All project value except the excluded work type.",
    ),
    "gap_to_threshold": (
        "Money remaining to reach an explicit target: target minus current total, bounded at zero when requested.",
        "The threshold is a portfolio goal, not a filter applied to each project.",
    ),
    "threshold_aggregate": (
        "Money sum of individual projects whose value meets an explicit minimum cutoff.",
        "Filter every project by the threshold and add qualifying values; not distance to a target.",
    ),
    "role_split": (
        "Money sum of projects delivered in one contractual role: prime, JV partner, or subcontractor.",
        "Portfolio aggregate restricted by delivery role.",
    ),
    "temporal_chain": (
        "Money sum of projects completed after an engineer's credential issue date.",
        "Date-filtered portfolio aggregation anchored to professional certification.",
    ),
    "yoy_movement": (
        "Absolute money change between client project totals completed in two calendar years.",
        "Compare annual completed-work value, not percentage financial-statement revenue growth.",
    ),
    "hop_aggregate": (
        "Full portfolio sum: add awarded contract values of every job for the client without a filter.",
        "Cumulative client project value; no average, comparison, cutoff, invoice, category, or role restriction.",
    ),
    "plant_asset_valuation": (
        "Money sum of acquisition costs from the plant and equipment asset register after attribute filters.",
        "Value owned or rented machinery by location, safety certification, ownership, or condition.",
    ),
    "boq_quantity_variance": (
        "Quantity difference between measured executed BOQ quantity and tender BOQ quantity for a contract item.",
        "Executed measurement minus tender quantity, not a money portfolio calculation.",
    ),
}


@dataclass(frozen=True)
class SemanticSignal:
    rankings: Tuple[Tuple[str, float], ...]

    @property
    def operator(self) -> Optional[str]:
        return self.rankings[0][0] if self.rankings else None

    @property
    def score(self) -> float:
        return self.rankings[0][1] if self.rankings else 0.0

    @property
    def margin(self) -> float:
        if not self.rankings:
            return 0.0
        second = self.rankings[1][1] if len(self.rankings) > 1 else 0.0
        return self.rankings[0][1] - second


@dataclass(frozen=True)
class ProjectSignal:
    project: Optional[Mapping[str, Any]]
    score: float
    margin: float
    alternatives: Tuple[int, ...] = ()


class DenseSemanticRouter:
    """Lazy local encoder with corpus-index and question-vector caching."""

    OPERATOR_INSTRUCTION = (
        "Given a bid-intelligence question, retrieve the typed operation whose "
        "mathematical formula and entity scope exactly match it. Distinguish "
        "summing, averaging, comparing, filtering, target gaps, billing, and cash collection."
    )
    PROJECT_INSTRUCTION = (
        "Given a bid-intelligence question, retrieve the exact project record "
        "described by its title, infrastructure type, location, client, or engineer. "
        "Ignore the requested calculation."
    )

    def __init__(
        self,
        operator_specs: Mapping[str, Mapping[str, Any]],
        model_path: Optional[Path] = None,
        enabled: bool = True,
    ) -> None:
        default_path = Path(__file__).resolve().parent.parent / "models" / "Qwen3-Embedding-0.6B"
        configured = Path(os.getenv("EMBEDDING_MODEL_PATH", str(model_path or default_path)))
        env_enabled = os.getenv("EMBEDDING_ENABLED", "1").strip().lower() not in {
            "0", "false", "no", "off",
        }
        self.model_path = configured
        self.enabled = bool(enabled and env_enabled and (configured / "config.json").exists())
        self.operator_specs = dict(operator_specs)
        self.dimensions = max(32, min(1024, int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))))
        self.batch_size = max(1, min(128, int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))))
        self.max_length = max(64, min(2048, int(os.getenv("EMBEDDING_MAX_LENGTH", "384"))))
        self.challenge_min_score = float(os.getenv("EMBEDDING_CHALLENGE_MIN_SCORE", "0.64"))
        self.challenge_min_margin = float(os.getenv("EMBEDDING_CHALLENGE_MIN_MARGIN", "0.08"))
        self.recall_min_score = float(os.getenv("EMBEDDING_RECALL_MIN_SCORE", "0.55"))
        self.project_min_score = float(os.getenv("EMBEDDING_PROJECT_MIN_SCORE", "0.66"))
        self.project_min_margin = float(os.getenv("EMBEDDING_PROJECT_MIN_MARGIN", "0.05"))
        self._tokenizer: Any = None
        self._model: Any = None
        self._torch: Any = None
        self._device = "cpu"
        self._operator_rows: List[str] = []
        self._operator_names: List[str] = []
        self._operator_vectors: Optional[np.ndarray] = None
        self._projects: List[Mapping[str, Any]] = []
        self._project_vectors: Optional[np.ndarray] = None
        self._operator_queries: Dict[str, np.ndarray] = {}
        self._project_queries: Dict[str, np.ndarray] = {}

    def register_projects(self, projects: Sequence[Mapping[str, Any]]) -> None:
        self._projects = list(projects)
        self._project_vectors = None

    def _load(self) -> None:
        if not self.enabled or self._model is not None:
            return
        import torch
        from transformers import AutoModel, AutoTokenizer
        from transformers.utils import logging as transformers_logging

        transformers_logging.set_verbosity_error()
        self._torch = torch
        self._device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if self._device == "mps" else torch.float32
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, padding_side="left", local_files_only=True
        )
        self._model = AutoModel.from_pretrained(
            self.model_path, local_files_only=True, dtype=dtype
        ).to(self._device).eval()

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimensions), dtype=np.float32)
        self._load()
        if self._model is None:
            raise RuntimeError("dense embedding model is unavailable")
        rows: List[np.ndarray] = []
        torch = self._torch
        for offset in range(0, len(texts), self.batch_size):
            batch_text = list(texts[offset : offset + self.batch_size])
            batch = self._tokenizer(
                batch_text,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            ).to(self._device)
            with torch.inference_mode():
                vectors = self._model(**batch).last_hidden_state[:, -1, : self.dimensions]
                vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
            rows.append(vectors.detach().float().cpu().numpy())
        return np.concatenate(rows, axis=0)

    @staticmethod
    def _instruct(instruction: str, question: str) -> str:
        return f"Instruct: {instruction}\nQuery: {question}"

    def _cache_path(self, namespace: str, texts: Sequence[str]) -> Path:
        payload = json.dumps(
            {"namespace": namespace, "dimensions": self.dimensions, "texts": list(texts)},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()[:20]
        return self.model_path / ".dense_cache" / f"{namespace}-{digest}.npy"

    def _corpus_vectors(self, namespace: str, texts: Sequence[str]) -> np.ndarray:
        path = self._cache_path(namespace, texts)
        try:
            values = np.load(path, allow_pickle=False)
            if values.shape == (len(texts), self.dimensions):
                return values
        except (OSError, ValueError):
            pass
        values = self._encode(texts)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, values, allow_pickle=False)
        except OSError:
            pass
        return values

    def _prepare_operator_index(self) -> None:
        if self._operator_vectors is not None:
            return
        rows: List[str] = []
        names: List[str] = []
        for name, spec in self.operator_specs.items():
            prototypes = OPERATOR_PROTOTYPES.get(name) or (str(spec.get("meaning", name)),)
            for prototype in prototypes:
                rows.append(f"Typed operation {name.replace('_', ' ')}: {prototype}")
                names.append(name)
        self._operator_rows = rows
        self._operator_names = names
        self._operator_vectors = self._corpus_vectors("operators", rows)

    def _project_documents(self) -> List[str]:
        return [
            "Project record: "
            f"title {item.get('title')}; category {item.get('category') or 'unknown'}; "
            f"state {item.get('state') or 'unknown'}; client {item.get('client') or 'unknown'}; "
            f"engineer {item.get('lead') or 'unknown'}."
            for item in self._projects
        ]

    def _prepare_project_index(self) -> None:
        if self._project_vectors is not None or not self._projects:
            return
        documents = self._project_documents()
        self._project_vectors = self._corpus_vectors("projects", documents)

    def prepare_questions(self, questions: Iterable[str]) -> Dict[str, int]:
        """Batch both query tasks, then release model weights before Qwen runs."""
        unique = list(dict.fromkeys(str(value) for value in questions if value))
        if not self.enabled or not unique:
            return {"questions": len(unique), "embedded": 0}
        try:
            self._prepare_operator_index()
            self._prepare_project_index()
            missing_operator = [q for q in unique if q not in self._operator_queries]
            missing_project = [q for q in unique if q not in self._project_queries]
            if missing_operator:
                vectors = self._encode([
                    self._instruct(self.OPERATOR_INSTRUCTION, q) for q in missing_operator
                ])
                self._operator_queries.update(zip(missing_operator, vectors))
            if missing_project and self._projects:
                vectors = self._encode([
                    self._instruct(self.PROJECT_INSTRUCTION, q) for q in missing_project
                ])
                self._project_queries.update(zip(missing_project, vectors))
            return {"questions": len(unique), "embedded": len(missing_operator)}
        except Exception:
            # Dense retrieval is an optional signal. Its failure must not
            # disturb either typed architecture.
            self.enabled = False
            return {"questions": len(unique), "embedded": 0}
        finally:
            self.release_model()

    def release_model(self) -> None:
        self._model = None
        self._tokenizer = None
        if self._torch is not None and self._device == "mps":
            try:
                self._torch.mps.empty_cache()
            except Exception:
                pass
        gc.collect()

    def rank_operators(self, question: str, answer_type: str, limit: int = 3) -> SemanticSignal:
        if not self.enabled:
            return SemanticSignal(())
        if question not in self._operator_queries:
            self.prepare_questions([question])
        query = self._operator_queries.get(question)
        if query is None or self._operator_vectors is None:
            return SemanticSignal(())
        allowed = {
            name for name, spec in self.operator_specs.items()
            if answer_type in set(spec.get("types", ()))
        }
        best: Dict[str, float] = {}
        scores = self._operator_vectors @ query
        for name, score in zip(self._operator_names, scores):
            if name in allowed:
                best[name] = max(best.get(name, -1.0), float(score))
        ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return SemanticSignal(tuple(ranked))

    def is_strong(self, signal: SemanticSignal) -> bool:
        return bool(
            signal.operator
            and signal.score >= self.challenge_min_score
            and signal.margin >= self.challenge_min_margin
        )

    def can_retrieve(self, signal: SemanticSignal) -> bool:
        """High-recall gate; downstream cross-encoding supplies precision."""
        return bool(signal.operator and signal.score >= self.recall_min_score)

    def rank_projects(self, question: str, person: Optional[str] = None) -> ProjectSignal:
        if not self.enabled or not self._projects:
            return ProjectSignal(None, 0.0, 0.0)
        if question not in self._project_queries:
            self.prepare_questions([question])
        query = self._project_queries.get(question)
        if query is None or self._project_vectors is None:
            return ProjectSignal(None, 0.0, 0.0)
        scores = self._project_vectors @ query
        candidates = []
        for index, (project, score) in enumerate(zip(self._projects, scores)):
            if person and str(project.get("lead") or "").casefold() != person.casefold():
                continue
            candidates.append((float(score), index, project))
        candidates.sort(key=lambda item: (-item[0], int(item[2]["package_number"])))
        if not candidates:
            return ProjectSignal(None, 0.0, 0.0)
        top_score, _index, top = candidates[0]
        second = candidates[1][0] if len(candidates) > 1 else 0.0
        margin = top_score - second
        alternatives = tuple(int(item[2]["package_number"]) for item in candidates[1:4])
        accepted = top if top_score >= self.project_min_score and margin >= self.project_min_margin else None
        return ProjectSignal(accepted, top_score, margin, alternatives)


class PlanReranker:
    """Cross-encode question/typed-plan pairs with Qwen3-Reranker-0.6B."""

    INSTRUCTION = (
        "Determine whether the typed bid-intelligence plan exactly matches the "
        "question's requested mathematical operation, entity scope, filters, dates, "
        "and output type. Reject plans that add an unstated concept or omit a stated constraint."
    )
    PREFIX = (
        '<|im_start|>system\nJudge whether the Document meets the requirements based on '
        'the Query and the Instruct provided. Note that the answer can only be "yes" or '
        '"no".<|im_end|>\n<|im_start|>user\n'
    )
    SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def __init__(self, model_path: Optional[Path] = None, enabled: bool = True) -> None:
        default_path = Path(__file__).resolve().parent.parent / "models" / "Qwen3-Reranker-0.6B"
        configured = Path(os.getenv("RERANKER_MODEL_PATH", str(model_path or default_path)))
        env_enabled = os.getenv("RERANKER_ENABLED", "1").strip().lower() not in {
            "0", "false", "no", "off",
        }
        self.model_path = configured
        self.enabled = bool(enabled and env_enabled and (configured / "config.json").exists())
        self.batch_size = max(1, min(64, int(os.getenv("RERANKER_BATCH_SIZE", "16"))))
        self.max_length = max(128, min(2048, int(os.getenv("RERANKER_MAX_LENGTH", "512"))))

    def score(self, pairs: Sequence[Tuple[str, str]]) -> List[float]:
        if not self.enabled or not pairs:
            return []
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from transformers.utils import logging as transformers_logging

        transformers_logging.set_verbosity_error()
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if device == "mps" else torch.float32
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, padding_side="left", local_files_only=True
        )
        model = AutoModelForCausalLM.from_pretrained(
            self.model_path, local_files_only=True, dtype=dtype
        ).to(device).eval()
        false_id = tokenizer.convert_tokens_to_ids("no")
        true_id = tokenizer.convert_tokens_to_ids("yes")
        prefix_tokens = tokenizer.encode(self.PREFIX, add_special_tokens=False)
        suffix_tokens = tokenizer.encode(self.SUFFIX, add_special_tokens=False)
        formatted = [
            f"<Instruct>: {self.INSTRUCTION}\n<Query>: {query}\n<Document>: {document}"
            for query, document in pairs
        ]
        results: List[float] = []
        try:
            for offset in range(0, len(formatted), self.batch_size):
                texts = formatted[offset : offset + self.batch_size]
                inputs = tokenizer(
                    texts,
                    padding=False,
                    truncation=True,
                    return_attention_mask=False,
                    max_length=self.max_length - len(prefix_tokens) - len(suffix_tokens),
                )
                for index, token_ids in enumerate(inputs["input_ids"]):
                    inputs["input_ids"][index] = prefix_tokens + token_ids + suffix_tokens
                padded = tokenizer.pad(inputs, padding=True, return_tensors="pt").to(device)
                with torch.inference_mode():
                    logits = model(**padded).logits[:, -1, :]
                    binary = torch.stack([logits[:, false_id], logits[:, true_id]], dim=1)
                    probabilities = torch.softmax(binary.float(), dim=1)[:, 1]
                results.extend(probabilities.detach().cpu().tolist())
        finally:
            del model
            del tokenizer
            if device == "mps":
                try:
                    torch.mps.empty_cache()
                except Exception:
                    pass
            gc.collect()
        return [float(value) for value in results]
