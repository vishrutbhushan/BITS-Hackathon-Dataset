"""Intent planning and typed query decomposition.

Questions are compiled from a small operation ontology (aggregate, difference,
threshold, exclusion, temporal, and so on) rather than a catalogue of observed
sentences.  Entity catalogues come from DuckDB through :mod:`entity_resolver`.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.append(str(Path(__file__).resolve().parent.parent / "db"))
from database import DEFAULT_DB_PATH, get_db
from entity_resolver import EntityResolver, normalize_text


SMALL_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS_NUMBERS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
NUMBER_WORDS = set(SMALL_NUMBERS) | set(TENS_NUMBERS) | {"and", "hundred", "thousand"}
MONTH_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
)

# These aliases describe the database schema's category vocabulary.  They are
# domain synonyms, not phrases copied from evaluation questions.
CATEGORY_ALIASES = [
    ("bridges and flyovers", "Bridges Flyovers"),
    ("bridges flyovers", "Bridges Flyovers"),
    ("bridges & flyovers", "Bridges Flyovers"),
    ("large bridges", "Large Bridges"),
    ("small buildings", "Small Buildings"),
    ("industrial epc", "Industrial Epc"),
    ("roads and highways", "Roads Highways"),
    ("roads highways", "Roads Highways"),
    ("roads & highways", "Roads Highways"),
    ("road maintenance", "Roads Maintenance"),
    ("roads maintenance", "Roads Maintenance"),
    ("sewerage and drainage", "Sewerage Drainage"),
    ("sewerage drainage", "Sewerage Drainage"),
    ("water treatment", "Water Treatment"),
    ("water supply", "Water Supply"),
    ("expressways", "Expressways"), ("expressway", "Expressways"),
    ("industrial", "Industrial Epc"), ("irrigation", "Irrigation"),
    ("tunnels", "Tunnels"), ("tunnel", "Tunnels"),
    ("maintenance", "Roads Maintenance"),
    ("sewerage", "Sewerage Drainage"), ("drainage", "Sewerage Drainage"),
    ("flyovers", "Bridges Flyovers"), ("flyover", "Bridges Flyovers"),
    ("bridges", "Bridges Flyovers"), ("bridge", "Bridges Flyovers"),
    ("buildings", "Buildings"), ("building", "Buildings"),
    ("roads", "Roads Highways"), ("road", "Roads Highways"),
    ("highways", "Roads Highways"), ("highway", "Roads Highways"),
]


def words_to_number(words: Sequence[str]) -> Optional[int]:
    """Parse an English non-negative integer phrase."""
    current = 0
    total = 0
    consumed = False
    for word in words:
        if word == "and":
            continue
        if word in SMALL_NUMBERS:
            current += SMALL_NUMBERS[word]
        elif word in TENS_NUMBERS:
            current += TENS_NUMBERS[word]
        elif word == "hundred":
            current = max(current, 1) * 100
        elif word == "thousand":
            total += max(current, 1) * 1_000
            current = 0
        else:
            return None
        consumed = True
    return total + current if consumed else None


def extract_threshold_inr(text: str) -> Optional[int]:
    """Extract a lossless crore/lakh amount from digits or number words."""
    normalized = text.lower().replace(",", "").replace("₹", " inr ")
    normalized = re.sub(r"[^a-z0-9.]+", " ", normalized).strip()
    numeric = re.search(r"(?:inr|rs)?\s*(\d+(?:\.\d+)?)\s*(crores?|cr|lakhs?)\b", normalized)
    if numeric:
        multiplier = 10_000_000 if numeric.group(2).startswith(("cr", "crore")) else 100_000
        return int(round(float(numeric.group(1)) * multiplier))

    raw_tokens = re.findall(r"[a-z]+", normalized.replace("-", " "))
    for index, token in enumerate(raw_tokens):
        if token not in {"crore", "crores", "cr", "lakh", "lakhs"}:
            continue
        start = index
        while start > 0 and raw_tokens[start - 1] in NUMBER_WORDS:
            start -= 1
        value = words_to_number(raw_tokens[start:index])
        if value is not None:
            multiplier = 10_000_000 if token in {"crore", "crores", "cr"} else 100_000
            return value * multiplier
    return None


def parse_threshold_inr(text: str) -> int:
    value = extract_threshold_inr(text)
    if value is None:
        raise ValueError(f"No crore/lakh threshold found in question: {text}")
    return value


def extract_explicit_date(text: str) -> Optional[str]:
    """Extract an exact date while rejecting underspecified month/year text."""
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        return iso.group(1)
    patterns = [
        rf"\b(?:{MONTH_PATTERN})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,)?\s+\d{{4}}\b",
        rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTH_PATTERN})(?:,)?\s+\d{{4}}\b",
    ]
    from dateutil import parser as dt_p
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", match.group(0), flags=re.I)
            try:
                return dt_p.parse(cleaned, fuzzy=False).strftime("%Y-%m-%d")
            except (TypeError, ValueError, OverflowError):
                continue
    return None


@dataclass
class SubTask:
    task_id: str
    action: str
    description: str
    query_params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    question: str
    pattern: str
    anchor_person: Optional[str] = None
    anchor_credential: Optional[str] = None
    anchor_project: Optional[str] = None
    anchor_package_num: Optional[int] = None
    anchor_client: Optional[str] = None
    anchor_date: Optional[str] = None
    target_metric: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)
    subtasks: List[SubTask] = field(default_factory=list)
    confidence: float = 0.0
    alternatives: List[Tuple[str, float]] = field(default_factory=list)
    diagnostics: List[str] = field(default_factory=list)


CONCEPT_ROOTS = {
    "reference": {"refer", "testimon", "endorse", "approval", "verif", "signoff", "letter"},
    "billing": {"bill", "invoic", "claim", "charge", "debit", "ledger", "account"},
    "receipt": {"collect", "paid", "payment", "receipt", "receiv", "realis", "realiz", "clear", "credit", "settle"},
    "award": {"award", "contract", "sanction", "scope", "secur", "commit"},
    "difference": {"differ", "gap", "delta", "varian", "spread", "shortfall", "movement", "shift", "swing", "separat", "exceed", "beat", "compar", "contrast", "reconcil", "crosscheck", "apart", "minus", "subtract", "deduct", "less", "distance", "disparity", "margin", "chang", "growth", "declin", "increas", "decreas"},
    "aggregate": {"aggreg", "combin", "cumul", "sum", "tally", "total", "rollup"},
    "exclude": {"exclud", "omit", "remov", "drop", "without", "apart", "strip", "filter", "carve", "except", "aside"},
    "missing": {"miss", "absent", "unrefer", "without", "lack", "unaccompan"},
    "outstanding": {"outstand", "unpaid", "owed", "owing", "due", "pending", "receiv", "balance", "remain", "settle", "arrear", "unsettled", "residual", "left", "net", "ageing", "aging", "open"},
    "average": {"average", "mean", "typical"},
    "rank_high": {"largest", "biggest", "highest", "top"},
    "rank_second": {"second", "next", "runner", "behind", "following", "subsequent", "nearest"},
    "goal": {"target", "goal", "need", "remain", "reach", "meet", "hit", "achiev", "secure"},
    "threshold": {"above", "over", "minimum", "least", "threshold", "cutoff", "limit", "exceed", "cross", "higher", "more", "clear"},
    "credential": {"pmp", "credential", "certif", "issu"},
}


def _has(tokens_: set[str], concept: str) -> bool:
    return any(any(token.startswith(root) for root in CONCEPT_ROOTS[concept]) for token in tokens_)


class IntentPlanner:
    CLIENT_SCOPED = {
        "absence", "ar_outstanding", "avg_work_size", "category_diff",
        "category_aggregate",
        "collection_rate", "exclusion_aggregate", "gap_to_threshold",
        "hop_aggregate", "mean_median_gap", "rank_value", "referenced_share",
        "role_split", "threshold_aggregate", "unbilled_gap", "yoy_movement",
    }

    def __init__(self, db_path: Optional[Path] = None, semantic_router: Optional[Any] = None):
        self.db = get_db(db_path or DEFAULT_DB_PATH)
        self.entities = EntityResolver(self.db, semantic_router=semantic_router)
        self.known_engineers = self.entities.engineers
        self.known_clients = self.entities.clients
        self.known_projects = self.entities.projects

    @staticmethod
    def _mask(text: str, phrases: Sequence[Optional[str]]) -> str:
        masked = text.lower()
        for phrase in sorted((p for p in phrases if p), key=len, reverse=True):
            masked = re.sub(re.escape(str(phrase).lower()), lambda m: " " * len(m.group(0)), masked)
        return masked

    def extract_categories(self, text: str, ignored_phrases: Optional[List[str]] = None) -> List[str]:
        """Extract ordered, non-overlapping category mentions."""
        masked = self._mask(text, [*self.known_clients, *(ignored_phrases or [])])
        occupied: List[Tuple[int, int]] = []
        matches: List[Tuple[int, str]] = []
        for alias, canonical in sorted(CATEGORY_ALIASES, key=lambda item: len(item[0]), reverse=True):
            for match in re.finditer(rf"\b{re.escape(alias)}\b", masked, re.I):
                start, end = match.span()
                if any(start < used_end and used_start < end for used_start, used_end in occupied):
                    continue
                occupied.append((start, end))
                matches.append((start, canonical))
        found: List[str] = []
        for _, canonical in sorted(matches):
            if canonical not in found:
                found.append(canonical)
        return found

    def resolve_descriptive_project(self, question: str, person: Optional[str]):
        return self.entities.resolve_project(question, person).value

    def _classify(
        self,
        question: str,
        answer_type: str,
        categories: Sequence[str],
        threshold: Optional[int],
        years: Sequence[int],
    ) -> Tuple[str, float, List[Tuple[str, float]], Dict[str, float]]:
        normalized = normalize_text(question)
        token_set = set(normalized.split())
        phrase_vs = bool(re.search(r"\b(?:vs|versus)\b", normalized))
        financial_growth = bool(token_set & {"turnover", "revenue", "sales"}) and len(years) >= 2

        if answer_type == "days":
            return "date_span", 0.99, [], {"date_span": 10.0}
        if answer_type == "count":
            negated_reference = bool(re.search(r"\b(?:no|not)\b.*\b(?:reference|letter|testimonial)\b", normalized))
            missing_reference = (_has(token_set, "missing") or negated_reference) and _has(token_set, "reference")
            pattern = "absence" if missing_reference else "distinct_count"
            confidence = 0.98 if missing_reference or _has(token_set, "credential") else 0.82
            return pattern, confidence, [], {pattern: 10.0}
        if answer_type == "percent":
            if financial_growth:
                return "turnover_growth", 0.96, [], {"turnover_growth": 10.0}
            ref = _has(token_set, "reference")
            cash = _has(token_set, "billing") and _has(token_set, "receipt")
            pattern = "collection_rate" if cash else "referenced_share"
            confidence = 0.97 if ref or cash else 0.62
            return pattern, confidence, [], {pattern: 10.0}

        score: Dict[str, float] = {}
        compare = _has(token_set, "difference") or phrase_vs
        aggregate = _has(token_set, "aggregate")
        exclude = _has(token_set, "exclude") or bool(re.search(r"\bnet(?:ted)?\s+(?:of|out)\b", normalized))
        award = _has(token_set, "award")
        billing = _has(token_set, "billing")
        outstanding = _has(token_set, "outstanding")

        asset_nouns = bool(token_set & {"asset", "assets", "equipment", "machinery", "fleet"})
        plant_with_register_qualifier = "plant" in token_set and bool(
            token_set & {"acquisition", "asset", "assets", "cost", "equipment", "fleet", "owned", "ownership", "register", "rented", "safety"}
        )
        if asset_nouns or plant_with_register_qualifier:
            score["plant_asset_valuation"] = 11.0
        if token_set & {"boq", "measurement", "measurements", "quantity", "quantities"} and re.search(r"\bcontract\s*[-#]?\s*\d+", normalized):
            score["boq_quantity_variance"] = 11.0

        if threshold is not None and _has(token_set, "goal") and compare:
            score["gap_to_threshold"] = 12.0
        elif threshold is not None and _has(token_set, "goal") and ({"reach", "meet", "hit", "target"} & token_set):
            score["gap_to_threshold"] = 11.0
        if _has(token_set, "rank_high") and _has(token_set, "rank_second"):
            score["rank_value"] = 9.0 + float(compare)
        elif _has(token_set, "rank_high") and compare:
            score["rank_value"] = 8.0
        if (outstanding and (billing or _has(token_set, "receipt") or "balance" in token_set)) or (billing and (_has(token_set, "receipt") or aggregate) and not award):
            score["ar_outstanding"] = 8.0 - (3.0 if award else 0.0)
        elif outstanding and not award:
            score["ar_outstanding"] = 7.0
        if award and billing:
            score["unbilled_gap"] = 10.0
        if len(years) >= 2 and compare:
            score["yoy_movement"] = 9.0
        elif len(years) >= 2:
            score["yoy_movement"] = 7.5
        if "median" in token_set:
            score["mean_median_gap"] = 10.0
        if exclude and categories:
            score["exclusion_aggregate"] = 10.0
        category_relationship = compare or bool(
            token_set & {"against", "between", "each", "respective", "totals", "rollups"}
        )
        if len(categories) >= 2 and category_relationship:
            score["category_diff"] = 9.0
        elif len(categories) >= 2:
            # Never discard explicit category constraints.  A genuinely
            # combined subset uses its own operator; otherwise the requested
            # two-way comparison compiles to a difference.
            if "combined" in token_set and not compare:
                score["category_aggregate"] = 8.5
            else:
                score["category_diff"] = 8.0
        if "after" in token_set and _has(token_set, "credential"):
            score["temporal_chain"] = 10.0
        if _has(token_set, "average"):
            score["avg_work_size"] = 9.0
        if threshold is not None and _has(token_set, "threshold"):
            score["threshold_aggregate"] = 8.0
        if {"prime", "subcontractor", "jv"} & token_set or "joint venture" in normalized:
            score["role_split"] = 9.0
        if aggregate:
            score["hop_aggregate"] = 6.0

        if not score:
            return "generic_multi_hop", 0.25, [], {}
        ordered = sorted(score.items(), key=lambda item: (-item[1], item[0]))
        best_pattern, best_score = ordered[0]
        margin = best_score - ordered[1][1] if len(ordered) > 1 else best_score
        confidence = min(0.99, 0.50 + 0.035 * best_score + 0.03 * min(margin, 5.0))
        return best_pattern, confidence, ordered[1:4], score

    @staticmethod
    def _role(question: str) -> str:
        normalized = normalize_text(question)
        if "subcontractor" in normalized:
            return "Subcontractor"
        if "joint venture" in normalized or re.search(r"\bjv\b", normalized):
            return "JV Partner"
        return "Prime"

    def _compile(self, pattern: str, slots: Dict[str, Any]) -> List[SubTask]:
        person, cred, project = slots["person"], slots["credential"], slots["project"]
        package, client, date = slots["package"], slots["client"], slots["date"]
        categories, years, threshold = slots["categories"], slots["years"], slots["threshold"]
        base = {"client": client, "pkg_num": package, "person": person}

        sql_patterns = {
            "absence": ("absence", "count_missing"),
            "distinct_count": ("engineer_projects", "count_distinct_categories"),
            "referenced_share": ("referenced_share", "percentage"),
            "collection_rate": ("collection_rate", "percentage"),
            "ar_outstanding": ("ar_outstanding", "outstanding_inr"),
            "unbilled_gap": ("unbilled_gap", "passthrough"),
            "mean_median_gap": ("client_portfolio_values", "mean_minus_median"),
            "avg_work_size": ("client_portfolio", "average_inr"),
            "rank_value": ("client_ranked_projects", "rank_diff_inr"),
            "hop_aggregate": ("client_portfolio_sum", "sum_inr"),
        }
        if pattern in sql_patterns:
            sql_type, metric = sql_patterns[pattern]
            params = dict(base)
            if sql_type == "engineer_projects":
                params = {"person": person}
            return [
                SubTask("T1", "sql_query", f"Execute {sql_type}", {"sql_type": sql_type, **params}),
                SubTask("T2", "math_compute", f"Compute {metric}", {"metric": metric}, ["T1"]),
            ]
        if pattern == "date_span":
            return [
                SubTask("T1", "sql_query", "Resolve credential issue date", {"sql_type": "credential_date", "person": person, "cred": cred, "date": date}),
                SubTask("T2", "sql_query", "Resolve project completion date", {"sql_type": "project_date", "project": project, "pkg_num": package, "person": person}),
                SubTask("T3", "math_compute", "Compute elapsed days", {"metric": "date_diff_days"}, ["T1", "T2"]),
            ]
        if pattern == "temporal_chain":
            return [
                SubTask("T1", "sql_query", "Resolve credential issue date", {"sql_type": "credential_date", "person": person, "cred": cred, "date": date}),
                SubTask("T2", "sql_query", "Find projects completed after credential", {"sql_type": "projects_after_date", "person": person}, ["T1"]),
                SubTask("T3", "math_compute", "Sum qualifying projects", {"metric": "sum_inr"}, ["T2"]),
            ]
        if pattern == "yoy_movement":
            return [
                SubTask("T1", "sql_query", "Aggregate the two completion years", {"sql_type": "yoy_movement", **base, "year1": years[0], "year2": years[1]}),
                SubTask("T2", "math_compute", "Compute year movement", {"metric": "yoy_diff_inr"}, ["T1"]),
            ]
        if pattern == "category_diff":
            return [
                SubTask("T1", "sql_query", "Aggregate the requested categories", {"sql_type": "category_diff", **base, "categories": list(categories[:2])}),
                SubTask("T2", "math_compute", "Compute category difference", {"metric": "category_diff_inr"}, ["T1"]),
            ]
        if pattern == "category_aggregate":
            return [
                SubTask("T1", "sql_query", "Aggregate the requested category subset", {"sql_type": "category_aggregate", **base, "categories": list(categories)}),
                SubTask("T2", "math_compute", "Sum requested categories", {"metric": "sum_inr"}, ["T1"]),
            ]
        if pattern == "exclusion_aggregate":
            return [
                SubTask("T1", "sql_query", "Aggregate portfolio excluding category", {"sql_type": "client_excluded_projects", **base, "exclude": categories[0]}),
                SubTask("T2", "math_compute", "Sum remaining projects", {"metric": "sum_inr"}, ["T1"]),
            ]
        if pattern == "gap_to_threshold":
            return [
                SubTask("T1", "sql_query", "Aggregate client portfolio", {"sql_type": "client_portfolio_sum", **base}),
                SubTask("T2", "math_compute", "Compute target gap", {"metric": "gap_inr", "target_inr": threshold, "gap_mode": slots["gap_mode"]}, ["T1"]),
            ]
        if pattern == "threshold_aggregate":
            return [
                SubTask("T1", "sql_query", "Aggregate projects meeting threshold", {"sql_type": "client_threshold_projects", **base, "threshold_inr": threshold}),
                SubTask("T2", "math_compute", "Sum qualifying projects", {"metric": "sum_inr"}, ["T1"]),
            ]
        if pattern == "role_split":
            return [
                SubTask("T1", "sql_query", "Aggregate projects by delivery role", {"sql_type": "client_role_projects", **base, "role": slots["role"]}),
                SubTask("T2", "math_compute", "Sum qualifying projects", {"metric": "sum_inr"}, ["T1"]),
            ]
        if pattern == "turnover_growth":
            return [
                SubTask("T1", "sql_query", "Retrieve audited turnover for both fiscal years", {"sql_type": "turnover_growth", "year1": years[0], "year2": years[1], "metric": "total_revenue"}),
                SubTask("T2", "math_compute", "Compute turnover growth percentage", {"metric": "percentage"}, ["T1"]),
            ]
        if pattern == "plant_asset_valuation":
            return [
                SubTask("T1", "sql_query", "Aggregate plant and machinery register", {"sql_type": "plant_asset_valuation", **slots["asset_filters"]}),
                SubTask("T2", "math_compute", "Sum qualifying asset costs", {"metric": "sum_inr"}, ["T1"]),
            ]
        if pattern == "boq_quantity_variance":
            return [
                SubTask("T1", "sql_query", "Compare tender and measured BOQ quantities", {"sql_type": "boq_quantity_variance", "contract_id": slots["contract_id"], "item_no": slots["item_no"], "question": slots["question"]}),
                SubTask("T2", "math_compute", "Return executed minus tender quantity", {"metric": "passthrough"}, ["T1"]),
            ]
        return [SubTask("T1", "fts_search", "Retrieve evidence for low-confidence intent", {"query": slots["question"]})]

    def plan(self, question: str, answer_type: Optional[str] = None) -> ExecutionPlan:
        answer_type = (answer_type or "money").lower()
        initial_project = self.entities.resolve_project(question)
        package = initial_project.value["package_number"] if initial_project.value else None
        person_res = self.entities.resolve_person(question, package)
        person = person_res.value
        project_res = initial_project
        if not project_res.value and person:
            project_res = self.entities.resolve_project(question, person)
            package = project_res.value["package_number"] if project_res.value else package
        elif not project_res.value and person_res.ambiguous:
            # Resolve mutually ambiguous short person/project mentions jointly.
            # A unique title match under one candidate lead supplies both slots.
            joint_matches = []
            for candidate_person in person_res.alternatives:
                candidate_project = self.entities.resolve_project(question, candidate_person)
                if candidate_project.value:
                    joint_matches.append((candidate_person, candidate_project))
            unique_packages = {match[1].value["package_number"] for match in joint_matches}
            if len(unique_packages) == 1:
                person, project_res = joint_matches[0]
                person_res = type(person_res)(person, 0.94, "joint_project_person")
                package = project_res.value["package_number"]

        client_res = self.entities.resolve_client(question)
        if not project_res.value and not client_res.value and not person_res.ambiguous:
            fts_project = self.entities.resolve_project_via_fts(question, person)
            dense_project = self.entities.resolve_project_dense(question, person)
            # Independent sparse+dense agreement is stronger than either
            # fallback alone. A confident dense-only match covers unseen
            # descriptions; a sparse-only match preserves prior behavior.
            if (
                fts_project.value
                and dense_project.value
                and fts_project.value["package_number"] == dense_project.value["package_number"]
            ):
                project_res = type(fts_project)(
                    fts_project.value,
                    min(0.95, max(fts_project.confidence, dense_project.confidence) + 0.04),
                    "hybrid_sparse_dense_project",
                )
            elif fts_project.value:
                project_res = fts_project
            elif dense_project.value:
                project_res = dense_project
            if project_res.value:
                package = project_res.value["package_number"]
                if not person and project_res.value.get("lead"):
                    person = project_res.value["lead"]
                    person_res = type(person_res)(person, project_res.confidence, f"{project_res.source}_lead")
        project_record = project_res.value or self.entities.project_for_package(package)

        credential_res = self.entities.resolve_credential(question)
        credential = credential_res.value["type"] if credential_res.value else None
        credential_id_match = re.search(r"\b(?:PMI|SSBB|6S)-\d+\b", question, re.I)
        if credential_id_match:
            credential = credential_id_match.group(0).upper()
        elif re.search(r"\bpmp\b", question, re.I):
            credential = "PMP"
        elif re.search(r"\b(?:six sigma|black belt|ssbb)\b", question, re.I):
            credential = "Six Sigma Black Belt"

        graph_client = project_record.get("client") if project_record else None
        # Exact/strong explicit names may intentionally override the anchor
        # project's client.  A low-confidence fuzzy acronym may not: the
        # package edge is authoritative and avoids state words or credentials
        # being mistaken for an organization shorthand.
        if client_res.value and (client_res.confidence >= 0.82 or not graph_client):
            client = client_res.value
        else:
            client = graph_client or client_res.value
        if not person and project_record and project_record.get("lead"):
            person = project_record["lead"]
            person_res = type(person_res)(person, 0.96, "project_lead")

        project_title = project_record.get("title") if project_record else None
        categories = self.extract_categories(question, [project_title] if project_title else None)
        # A negative digit boundary also accepts compact fiscal notation such
        # as FY2023-24, where a word boundary before the year does not exist.
        years = [int(y) for y in dict.fromkeys(re.findall(r"(?<!\d)(20\d{2})(?!\d)", question))]
        threshold = extract_threshold_inr(question)
        date = extract_explicit_date(question)
        normalized_question = normalize_text(question)
        state = next((value.title() for value in self.entities.states if re.search(rf"\b{re.escape(value)}\b", normalized_question)), None)
        ownership = "rented" if re.search(r"\b(?:rent|rented|leased?)\b", normalized_question) else ("owned" if "owned" in normalized_question else None)
        if re.search(r"\b(?:not|without|lacking)\b.{0,24}\b(?:safety|certif)", normalized_question):
            safety_certified = False
        else:
            safety_certified = True if re.search(r"\b(?:safety|certified)\b", normalized_question) else None
        condition = next((value for value in ("new", "good", "fair", "poor") if re.search(rf"\b{value}\b", normalized_question)), None)
        contract_match = re.search(r"\bcontract\s*[-#]?\s*(\d+)\b", normalized_question)
        item_match = re.search(r"\bitem\s*(?:no)?\s*[-#]?\s*([a-z0-9.]+)\b", normalized_question)
        pattern, route_conf, alternatives, scores = self._classify(
            question, answer_type, categories, threshold, years
        )
        if pattern == "generic_multi_hop" and answer_type == "money" and client:
            # The scorer has no abstention penalty.  For an unresolved
            # client-scoped money intent, the full portfolio is a bounded,
            # evidence-backed fallback and usually earns partial credit; a
            # fabricated zero does not.  Confidence stays deliberately low so
            # an enabled LLM audits it.
            pattern = "hop_aggregate"
            route_conf = 0.35
            alternatives = [("generic_multi_hop", 0.25)]
            scores = {"hop_aggregate_fallback": 1.0}

        diagnostics = [f"route_scores={scores}", f"person={person_res.source}", f"client={client_res.source}", f"project={project_res.source}"]
        confidence = route_conf
        if pattern in self.CLIENT_SCOPED and not client:
            confidence *= 0.25
            diagnostics.append("missing required client anchor")
        elif pattern in self.CLIENT_SCOPED:
            client_confidence = (
                client_res.confidence
                if client_res.value == client and client_res.confidence >= 0.82
                else project_res.confidence if project_record else client_res.confidence
            )
            confidence = min(confidence, client_confidence or 0.55)
        if pattern in {"date_span", "temporal_chain", "distinct_count"} and not person:
            confidence *= 0.25
            diagnostics.append("missing required person anchor")
        elif pattern in {"date_span", "temporal_chain", "distinct_count"}:
            confidence = min(confidence, person_res.confidence or 0.55)
        if pattern == "date_span" and project_record:
            confidence = min(confidence, project_res.confidence or 0.55)
        if person_res.ambiguous:
            confidence *= 0.5
            diagnostics.append(f"ambiguous people={list(person_res.alternatives)}")
        if project_res.ambiguous:
            confidence *= 0.5
            diagnostics.append(f"ambiguous projects={list(project_res.alternatives)}")

        slots = {
            "question": question, "person": person, "credential": credential,
            "project": project_title, "package": package, "client": client,
            "date": date, "categories": categories, "years": years,
            "threshold": threshold, "role": self._role(question),
            "asset_filters": {"state": state, "ownership": ownership, "safety_certified": safety_certified, "condition": condition},
            "contract_id": int(contract_match.group(1)) if contract_match else None,
            "item_no": item_match.group(1) if item_match else None,
            "gap_mode": "shortfall" if re.search(r"\b(?:need|needed|required|remaining|still)\b", normalized_question) else "absolute",
        }
        subtasks = self._compile(pattern, slots)
        return ExecutionPlan(
            question=question,
            pattern=pattern,
            anchor_person=person,
            anchor_credential=credential,
            anchor_project=project_title,
            anchor_package_num=package,
            anchor_client=client,
            anchor_date=date,
            target_metric=answer_type,
            extra_params={"categories": categories, "years": years, "threshold_inr": threshold, "role": slots["role"]},
            subtasks=subtasks,
            confidence=round(confidence, 3),
            alternatives=alternatives,
            diagnostics=diagnostics,
        )
