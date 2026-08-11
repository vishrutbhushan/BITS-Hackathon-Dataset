"""Data-driven entity resolution for bid-intelligence questions.

The resolver derives its catalogue from DuckDB instead of enumerating people,
clients, projects, or question examples in source code.  It returns confidence
and ambiguity information so the planner can avoid silently selecting an
unrelated entity when a short name is shared by multiple records.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ORGANISATION_WORDS = {
    "and", "co", "company", "corp", "corporation", "dept", "department",
    "government", "govt", "limited", "ltd", "of", "office", "the",
}
INITIALISM_STOPWORDS = {
    "and", "co", "company", "corp", "corporation", "government", "govt",
    "limited", "ltd", "of", "the",
}

PROJECT_STOPWORDS = {
    "a", "all", "an", "and", "assignment", "at", "client", "completed",
    "contract", "credential", "for", "from", "in", "job", "of", "on",
    "package", "pkg", "pmp", "project", "scope", "site", "the", "to",
    "work",
}


def normalize_text(value: str) -> str:
    """Normalize punctuation and possessives while preserving word order."""
    value = unicodedata.normalize("NFKD", value or "")
    value = value.replace("’", "'").replace("‘", "'")
    value = re.sub(r"\b([a-z]+)'s\b", r"\1", value.lower())
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def tokens(value: str) -> List[str]:
    return normalize_text(value).split()


def contains_phrase(haystack: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {haystack} "


@dataclass(frozen=True)
class Resolution:
    value: Optional[Any]
    confidence: float
    source: str
    alternatives: Tuple[Any, ...] = field(default_factory=tuple)

    @property
    def ambiguous(self) -> bool:
        return self.value is None and len(self.alternatives) > 1


class EntityResolver:
    """Resolve corpus entities with exact, alias, and conservative fuzzy passes."""

    def __init__(self, db, semantic_router: Optional[Any] = None):
        self.db = db
        self.semantic_router = semantic_router
        self.engineers = sorted(
            {row[0].strip() for row in db.fetchall("SELECT full_name FROM engineers") if row[0]},
            key=len,
            reverse=True,
        )
        self.clients = sorted(
            {
                row[0].strip(" ,.")
                for row in db.fetchall(
                    """
                    SELECT canonical_client FROM clients
                    UNION
                    SELECT canonical_client FROM workbooks_receivables
                    """
                )
                if row[0]
            },
            key=len,
            reverse=True,
        )
        self.projects = [
            {
                "title": row[0],
                "package_number": int(row[1]),
                "client": row[2],
                "lead": row[3],
                "state": row[4],
                "category": row[5],
                "document_ids": tuple(doc for doc in row[6:9] if doc),
            }
            for row in db.fetchall(
                """
                SELECT title, package_number, canonical_client, project_lead, state, category,
                       ccc_doc_id, cc_doc_id, ref_doc_id
                FROM projects
                WHERE title IS NOT NULL AND package_number IS NOT NULL
                """
            )
        ]
        self.projects_by_package = {p["package_number"]: p for p in self.projects}
        self.projects_by_document = {
            doc_id: project
            for project in self.projects
            for doc_id in project["document_ids"]
        }
        self.credentials = {
            str(row[0]).upper(): {
                "person": row[1], "type": row[2], "issue_date": row[3]
            }
            for row in db.fetchall(
                "SELECT credential_id, engineer_name, credential_type, issue_date FROM credentials"
            )
            if row[0]
        }
        self.states = sorted(
            {normalize_text(p["state"]) for p in self.projects if p.get("state")},
            key=len,
            reverse=True,
        )
        self._people_by_first = self._index_first_names(self.engineers)
        self._client_aliases = self._build_client_aliases()
        if self.semantic_router is not None:
            self.semantic_router.register_projects(self.projects)

    @staticmethod
    def _index_first_names(names: Iterable[str]) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = defaultdict(list)
        for name in names:
            parts = tokens(name)
            if parts:
                result[parts[0]].append(name)
        return result

    def _state_in(self, normalized_name: str) -> Optional[str]:
        return next((state for state in self.states if contains_phrase(normalized_name, state)), None)

    def _build_client_aliases(self) -> Dict[str, set[str]]:
        aliases: Dict[str, set[str]] = {}
        first_counts = Counter(tokens(client)[0] for client in self.clients if tokens(client))

        for client in self.clients:
            normalized = normalize_text(client)
            client_tokens = normalized.split()
            generated = {normalized}

            # Initialisms are corpus-derived (NEDA, NSPO, PWD, PHED, ...),
            # not a maintained list of client-specific spellings.
            significant = [t for t in client_tokens if t not in INITIALISM_STOPWORDS]
            if len(significant) >= 3:
                generated.add("".join(t[0] for t in significant))

            state = self._state_in(normalized)
            if state:
                state_tokens = set(state.split())
                state_abbreviation = "".join(part[0] for part in state.split())
                core = [t for t in client_tokens if t not in INITIALISM_STOPWORDS and t not in state_tokens]
                if len(core) >= 2:
                    abbreviation = "".join(t[0] for t in core)
                    abbreviations = {abbreviation}
                    # Departmental shorthand often omits the final generic
                    # word (e.g. two-letter prefix rather than three letters).
                    for prefix_len in range(2, len(core)):
                        abbreviations.add("".join(t[0] for t in core[:prefix_len]))
                    for short in abbreviations:
                        generated.update({
                            f"{short} {state}", f"{state} {short}",
                            f"{short} {state_abbreviation}", f"{state_abbreviation} {short}",
                        })
                    generated.update({
                        f"{abbreviation} {state}", f"{state} {abbreviation}",
                        f"{abbreviation} {state_abbreviation}", f"{state_abbreviation} {abbreviation}",
                    })
                if core and core[0] not in {"public", "national"}:
                    generated.update({
                        f"{core[0]} {state}", f"{state} {core[0]}",
                        f"{core[0]} {state_abbreviation}", f"{state_abbreviation} {core[0]}",
                    })

            first = client_tokens[0] if client_tokens else ""
            state_first_tokens = {state.split()[0] for state in self.states}
            if len(first) >= 4 and first_counts[first] == 1 and first not in {"public", "national"} | state_first_tokens:
                generated.add(first)

            # Remove a trailing legal form to cover ordinary short names such
            # as "Mahanadi Steel" without encoding any estate-specific alias.
            shortened = list(client_tokens)
            while shortened and shortened[-1] in ORGANISATION_WORDS:
                shortened.pop()
            if len(shortened) >= 2:
                generated.add(" ".join(shortened))

            aliases[client] = {a for a in generated if len(a) >= 3}
        return aliases

    def resolve_credential(self, question: str) -> Resolution:
        matches = [key for key in self.credentials if re.search(rf"\b{re.escape(key)}\b", question, re.I)]
        if len(matches) == 1:
            return Resolution(self.credentials[matches[0]], 1.0, "credential_id")
        if len(matches) > 1:
            return Resolution(None, 0.0, "ambiguous_credential", tuple(matches))
        return Resolution(None, 0.0, "not_found")

    def resolve_person(self, question: str, package_number: Optional[int] = None) -> Resolution:
        credential = self.resolve_credential(question)
        if credential.value:
            return Resolution(credential.value["person"], 1.0, "credential_id")

        normalized_question = normalize_text(question)
        exact = [name for name in self.engineers if contains_phrase(normalized_question, normalize_text(name))]
        if len(exact) == 1:
            return Resolution(exact[0], 1.0, "full_name")
        if len(exact) > 1:
            return Resolution(None, 0.0, "ambiguous_full_name", tuple(exact))

        mentioned_first = []
        q_tokens = set(normalized_question.split())
        for first, names in self._people_by_first.items():
            # Also accept an unpunctuated possessive ("Pritis") generically;
            # OCR and hurried prompts frequently drop apostrophes.
            if len(first) > 3 and (first in q_tokens or f"{first}s" in q_tokens):
                mentioned_first.extend(names)
        mentioned_first = list(dict.fromkeys(mentioned_first))
        if len(mentioned_first) == 1:
            return Resolution(mentioned_first[0], 0.88, "unique_first_name")

        if package_number in self.projects_by_package:
            lead = self.projects_by_package[package_number].get("lead")
            if lead and (not mentioned_first or lead in mentioned_first):
                return Resolution(lead, 0.96, "package_lead")

        if mentioned_first:
            return Resolution(None, 0.0, "ambiguous_first_name", tuple(mentioned_first))
        return Resolution(None, 0.0, "not_found")

    def resolve_client(self, question: str) -> Resolution:
        normalized_question = normalize_text(question)
        hits: List[Tuple[int, str, str]] = []
        question_tokens = set(normalized_question.split())
        for client, aliases in self._client_aliases.items():
            for alias in aliases:
                alias_tokens = alias.split()
                if contains_phrase(normalized_question, alias) or (
                    len(alias_tokens) >= 2 and set(alias_tokens) <= question_tokens
                ):
                    hits.append((len(alias.split()), client, alias))

        if hits:
            best_length = max(hit[0] for hit in hits)
            best = {(client, alias) for length, client, alias in hits if length == best_length}
            clients = sorted({client for client, _ in best})
            if len(clients) == 1:
                alias = max((alias for client, alias in best if client == clients[0]), key=len)
                confidence = 1.0 if normalize_text(clients[0]) == alias else min(0.98, 0.82 + 0.04 * best_length)
                return Resolution(clients[0], confidence, f"client_alias:{alias}")
            return Resolution(None, 0.0, "ambiguous_client_alias", tuple(clients))

        # Tolerate a one-character OCR/acronym error only when a state or other
        # qualifier also matches.  This covers noisy short forms without fuzzy
        # matching full organization names.
        def edit_distance_at_most_one(left: str, right: str) -> bool:
            if abs(len(left) - len(right)) > 1:
                return False
            if len(left) == len(right):
                return sum(a != b for a, b in zip(left, right)) <= 1
            short, long = (left, right) if len(left) < len(right) else (right, left)
            for index in range(len(long)):
                if long[:index] + long[index + 1:] == short:
                    return True
            return False

        fuzzy_hits = []
        for client, aliases in self._client_aliases.items():
            for alias in aliases:
                alias_parts = alias.split()
                if len(alias_parts) < 2 or not (2 < len(alias_parts[0]) <= 5):
                    continue
                qualifiers = set(alias_parts[1:])
                if not qualifiers <= question_tokens:
                    continue
                if any(
                    2 < len(token) <= 5 and edit_distance_at_most_one(token, alias_parts[0])
                    for token in question_tokens
                ):
                    fuzzy_hits.append(client)
        fuzzy_clients = sorted(set(fuzzy_hits))
        if len(fuzzy_clients) == 1:
            return Resolution(fuzzy_clients[0], 0.74, "fuzzy_acronym")
        if len(fuzzy_clients) > 1:
            return Resolution(None, 0.0, "ambiguous_fuzzy_acronym", tuple(fuzzy_clients))

        # Conservative token fallback.  It is only accepted when the best
        # candidate has at least two distinguishing tokens and a clear margin.
        q_tokens = set(normalized_question.split())
        scored = []
        for client in self.clients:
            c_tokens = {t for t in tokens(client) if t not in ORGANISATION_WORDS}
            overlap = c_tokens & q_tokens
            if len(overlap) >= 2:
                scored.append((len(overlap) / len(c_tokens), len(overlap), client))
        scored.sort(reverse=True)
        if scored and (len(scored) == 1 or scored[0][:2] > scored[1][:2]):
            return Resolution(scored[0][2], min(0.9, scored[0][0]), "client_token_overlap")
        if scored:
            return Resolution(None, 0.0, "ambiguous_client_tokens", tuple(x[2] for x in scored[:3]))
        return Resolution(None, 0.0, "not_found")

    @staticmethod
    def _project_tokens(value: str) -> set[str]:
        normalized = normalize_text(value)
        expansions = {
            "wtp": "water treatment plant",
            "stp": "sewerage treatment plant",
            "rob": "road over bridge",
        }
        normalized = " ".join(expansions.get(token, token) for token in normalized.split())
        normalized = re.sub(r"\b(?:pkg|package)\s*\d+\b", " ", normalized)
        return {
            token for token in normalized.split()
            if token not in PROJECT_STOPWORDS and len(token) > 1
        }

    def resolve_project(self, question: str, person: Optional[str] = None) -> Resolution:
        package = re.search(r"\b(?:pkg|package)\s*-?\s*(\d+)\b", question, re.I)
        if package:
            number = int(package.group(1))
            project = self.projects_by_package.get(number)
            return Resolution(project, 1.0 if project else 0.0, "package_number")

        question_tokens = self._project_tokens(question)
        candidates: List[Tuple[float, int, Dict[str, Any]]] = []
        for project in self.projects:
            lead = normalize_text(project.get("lead") or "")
            if person and normalize_text(person) != lead:
                continue
            title_tokens = self._project_tokens(project["title"])
            overlap = title_tokens & question_tokens
            coverage = len(overlap) / len(title_tokens) if title_tokens else 0.0
            enough_context = (len(overlap) >= 1 if person else len(overlap) >= 2)
            minimum_coverage = 0.2 if person else 0.6
            if enough_context and coverage >= minimum_coverage:
                candidates.append((coverage, len(overlap), project))

        candidates.sort(key=lambda item: (item[1], item[0]), reverse=True)
        if not candidates:
            return Resolution(None, 0.0, "not_found")
        if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
            return Resolution(
                None,
                0.0,
                "ambiguous_project_description",
                tuple(x[2]["package_number"] for x in candidates[:4]),
            )
        best = candidates[0]
        confidence = min(0.95, 0.65 + 0.25 * best[0] + 0.03 * best[1])
        return Resolution(best[2], confidence, "project_description")

    def project_for_package(self, package_number: Optional[int]) -> Optional[Dict[str, Any]]:
        return self.projects_by_package.get(package_number) if package_number is not None else None

    def resolve_project_via_fts(self, question: str, person: Optional[str] = None) -> Resolution:
        """Use BM25 only after deterministic project matching is inconclusive."""
        hits = self.db.search_fts(question, limit=12, doc_type="company_completion_certificate")
        candidates = []
        for hit in hits:
            project = self.projects_by_document.get(hit["doc_id"])
            if not project:
                continue
            if person and normalize_text(project.get("lead") or "") != normalize_text(person):
                continue
            candidates.append((float(hit["score"]), project))
        if not candidates:
            return Resolution(None, 0.0, "fts_not_found")
        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_project = candidates[0]
        second_score = candidates[1][0] if len(candidates) > 1 else 0.0
        relative_margin = max(0.0, (best_score - second_score) / max(abs(best_score), 1.0))
        confidence = min(0.88, 0.58 + 0.6 * relative_margin + (0.08 if person else 0.0))
        return Resolution(
            best_project,
            confidence,
            "fts_project",
            tuple(item[1]["package_number"] for item in candidates[1:4]),
        )

    def resolve_project_dense(self, question: str, person: Optional[str] = None) -> Resolution:
        """Resolve a descriptive project only on a high-margin dense match.

        Package IDs and lexical title matches are evaluated first.  Dense
        retrieval exists for unseen paraphrases and never overrides those
        stronger graph-backed signals.
        """
        if self.semantic_router is None or not self.semantic_router.enabled:
            return Resolution(None, 0.0, "dense_disabled")
        signal = self.semantic_router.rank_projects(question, person)
        if signal.project is None:
            return Resolution(
                None,
                0.0,
                "dense_project_inconclusive",
                signal.alternatives,
            )
        confidence = min(0.91, 0.66 + signal.margin * 2.0)
        return Resolution(
            signal.project,
            confidence,
            "dense_project",
            signal.alternatives,
        )
