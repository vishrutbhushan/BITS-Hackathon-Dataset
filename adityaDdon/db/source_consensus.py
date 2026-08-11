"""Source-level reconciliation for the closed project document graph.

The corpus contains three independent descriptions of each completed work:
the client completion certificate, the company's completion certificate, and
the consolidated past-performance portfolio.  This module parses those
descriptions independently and selects facts by agreement before applying a
document-authority fallback.  It deliberately has no knowledge of questions,
question IDs, submissions, or expected answers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from dateutil import parser as date_parser


PROJECT_NUMBER_RE = re.compile(r"\bPkg-(\d{1,3})\b", re.I)
MONEY_RE = re.compile(
    r"(?:INR|Rs\.?|₹)?\s*"
    r"(-?[\d,]+(?:\.\d+)?)\s*"
    r"(crores?|Cr|lakhs?|Lakh)?\b",
    re.I,
)


@dataclass(frozen=True)
class SourceFact:
    """One normalized field value with its document provenance."""

    source: str
    doc_id: str
    field: str
    value: Any
    raw_value: str = ""


@dataclass(frozen=True)
class ConsensusFact:
    """Selected value plus agreement metadata for auditing."""

    value: Any
    source: str
    doc_id: str
    agreement_count: int
    evidence_count: int
    status: str


def normalize_inr(raw: Any) -> int:
    """Convert lossless Indian money renderings into integer rupees."""
    if raw is None or isinstance(raw, bool):
        return 0
    text = str(raw).strip()
    match = MONEY_RE.search(text)
    if not match:
        return 0
    try:
        amount = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return 0
    unit = (match.group(2) or "").lower()
    if unit.startswith("cr") or unit.startswith("crore"):
        amount *= 10_000_000
    elif unit.startswith("lakh"):
        amount *= 100_000
    return int(amount.quantize(Decimal("1")))


def normalize_date(raw: Any) -> Optional[str]:
    if raw in (None, ""):
        return None
    text = str(raw).strip().split("·", 1)[0].strip()
    try:
        # The estate is Indian: numeric dates beginning with a day are
        # DD/MM/YYYY (or DD-MM-YYYY), while an initial four-digit component is
        # ISO year-first.  dateutil's month-first default silently transposed
        # every ambiguous day/month pair.
        year_first = bool(re.match(r"^\d{4}[-/]", text))
        day_first = bool(re.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}$", text))
        return date_parser.parse(
            text,
            yearfirst=year_first,
            dayfirst=day_first,
        ).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_name(raw: Any) -> str:
    """Remove only role/legal qualifiers; retain the organization identity."""
    if raw is None:
        return ""
    text = re.sub(r"\s+", " ", str(raw)).strip(" ,.")
    text = re.sub(
        r"\s*\((?:government|private|prime|subcontractor|jv\s+partner|joint\s+venture)\)\s*$",
        "",
        text,
        flags=re.I,
    )
    return text.strip(" ,.")


def _identity(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return value


def select_consensus(
    facts: Iterable[SourceFact],
    source_priority: Sequence[str],
) -> ConsensusFact:
    """Select a modal non-empty value, then use explicit source authority.

    Agreement always outranks source priority.  Priority is needed only for a
    single readable source or a true conflict.  Empty strings, ``None``, and
    non-positive monetary values are treated as missing evidence.
    """
    usable = [
        fact
        for fact in facts
        if fact.value not in (None, "")
        and not (fact.field.endswith("_inr") and int(fact.value) <= 0)
    ]
    if not usable:
        return ConsensusFact(None, "", "", 0, 0, "missing")

    identities = [_identity(fact.value) for fact in usable]
    counts = Counter(identities)
    modal_identity, modal_count = counts.most_common(1)[0]
    modal = [fact for fact in usable if _identity(fact.value) == modal_identity]
    priority = {source: index for index, source in enumerate(source_priority)}
    selected_pool = modal if modal_count >= 2 else usable
    selected = min(
        selected_pool,
        key=lambda fact: (priority.get(fact.source, len(priority)), fact.doc_id),
    )
    if modal_count == len(usable):
        status = "unanimous" if len(usable) > 1 else "single_source"
    elif modal_count >= 2:
        status = "majority"
    else:
        status = "authority_fallback"
    return ConsensusFact(
        selected.value,
        selected.source,
        selected.doc_id,
        modal_count,
        len(usable),
        status,
    )


def _match_after_label(text: str, labels: Sequence[str]) -> str:
    label = "|".join(labels)
    match = re.search(rf"(?:{label})\s*\n\s*([^\n]+)", text, re.I)
    return match.group(1).strip() if match else ""


def _project_number(text: str) -> Optional[int]:
    match = PROJECT_NUMBER_RE.search(text)
    return int(match.group(1)) if match else None


def _labeled_money(text: str) -> Tuple[int, str]:
    labels = (
        r"gross\s+executed\s+value",
        r"final\s+executed\s+amount",
        r"executed\s+value",
        r"contract\s+value(?:\s*\(original\))?",
        r"awarded\s+value",
    )
    for match in re.finditer("|".join(labels), text, re.I):
        window = text[match.end() : match.end() + 180]
        # Prefer an exact Indian-grouped integer when both an exact amount and
        # a rounded verbal rendering are present in the same field.
        grouped = re.search(r"(?:INR|Rs\.?|₹)?\s*(\d{1,3}(?:,\d{2,3}){2,})", window, re.I)
        if grouped:
            raw = grouped.group(0).strip()
            return int(grouped.group(1).replace(",", "")), raw
        unit = re.search(
            r"(?:INR|Rs\.?|₹)?\s*[\d,]+(?:\.\d+)?\s*(?:crores?|Cr|lakhs?|Lakh)\b",
            window,
            re.I,
        )
        if unit:
            raw = unit.group(0).strip()
            return normalize_inr(raw), raw
        raw_inr = re.search(r"(?:INR|Rs\.?|₹)\s*(\d{6,})\b", window, re.I)
        if raw_inr:
            return int(raw_inr.group(1)), raw_inr.group(0).strip()
    return 0, ""


def parse_company_certificate(text: str, doc_id: str) -> Dict[str, Any]:
    package = _project_number(text)
    value, raw_value = _labeled_money(text)
    title = _match_after_label(text, (r"Project\s+Name", r"Work"))
    client = _match_after_label(text, (r"Client",))
    category = _match_after_label(text, (r"Work\s+Category", r"Category"))
    completion = _match_after_label(text, (r"Completion\s+Date", r"Completion"))
    lead = _match_after_label(text, (r"Project\s+Manager", r"Project\s+Lead"))
    return {
        "package_number": package,
        "source": "company_certificate",
        "doc_id": doc_id,
        "title": title,
        "client": normalize_name(client),
        "category": category.strip(),
        "value_inr": value,
        "raw_value": raw_value,
        "completion_date": normalize_date(completion),
        "project_lead": lead.strip(),
        "role": "",
    }


def parse_client_certificate(text: str, doc_id: str) -> Dict[str, Any]:
    package = _project_number(text)
    value, raw_value = _labeled_money(text)
    title = _match_after_label(text, (r"Name\s+of\s+Work",))
    if not title:
        prose_title = re.search(r"work\s+of\s+[“\"]([^”\"]+Pkg-\d+)[”\"]", text, re.I)
        title = prose_title.group(1).strip() if prose_title else ""
    completion = _match_after_label(text, (r"Completion\s+Date",))
    if not completion:
        prose_date = re.search(
            r"completed\s+in\s+all\s+respects\s+on\s+(.{6,24}?)\s+at\s+a\s+gross",
            text,
            re.I | re.S,
        )
        completion = re.sub(r"\s+", " ", prose_date.group(1)).strip() if prose_date else ""
    lead = _match_after_label(text, (r"Contractor'?s\s+Project\s+Manager",))
    if not lead:
        prose_lead = re.search(r"supervised\s+on\s+the\s+contractor'?s\s+side\s+by\s+([^\.\n]+)", text, re.I)
        lead = prose_lead.group(1).strip() if prose_lead else ""
    category = _match_after_label(text, (r"Nature\s*/\s*Category",))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    client = lines[0] if lines else ""
    return {
        "package_number": package,
        "source": "client_certificate",
        "doc_id": doc_id,
        "title": title,
        "client": normalize_name(client),
        "category": category.strip(),
        "value_inr": value,
        "raw_value": raw_value,
        "completion_date": normalize_date(completion),
        "project_lead": lead.strip(),
        "role": "",
    }


PORTFOLIO_RECORD_RE = re.compile(
    r"(?ms)^\s*(\d{1,3})\.\s*([^\n]+)\n"
    r"Client\s*\n(.*?)\n"
    r"Category\s*\n(.*?)\n"
    r"Executed\s+Value\s*\n(.*?)\n"
    r"Completed\s*\n([^\n]+)"
)


def parse_portfolio(text: str, doc_id: str = "DOC-PPP-001") -> Dict[int, Dict[str, Any]]:
    r"""Parse each detailed portfolio record without consuming the next one.

    The prior broad ``\s*`` expression could start a match at the year in a
    prose sentence (``completed 2015.``), and it rejected a client whose
    ``(JV Partner)`` qualifier wrapped across lines.  Explicit line-anchored
    section boundaries prevent both failures.
    """
    records: Dict[int, Dict[str, Any]] = {}
    for ordinal, title, client_raw, category, raw_value, completion in PORTFOLIO_RECORD_RE.findall(text):
        package = _project_number(title)
        if package is None:
            continue
        role_match = re.search(
            r"\((Prime|Subcontractor|JV\s+Partner|Joint\s+Venture)\)",
            client_raw,
            re.I,
        )
        role_text = re.sub(r"\s+", " ", role_match.group(1)).lower() if role_match else ""
        if role_text == "prime":
            role = "Prime"
        elif role_text == "subcontractor":
            role = "Subcontractor"
        elif role_text:
            role = "JV Partner"
        else:
            role = ""
        records[package] = {
            "package_number": package,
            "source": "portfolio",
            "doc_id": doc_id,
            "work_no": int(ordinal),
            "title": title.strip(),
            "client": normalize_name(client_raw),
            "category": re.sub(r"\s+", " ", category).strip(),
            "value_inr": normalize_inr(raw_value),
            "raw_value": raw_value.strip(),
            "completion_date": normalize_date(completion),
            "project_lead": "",
            "role": role,
        }
    return records


def reconcile_project(
    sources: Mapping[str, Mapping[str, Any]],
) -> Dict[str, ConsensusFact]:
    """Reconcile the fields used by online arithmetic and entity routing."""
    priorities = {
        "title": ("company_certificate", "client_certificate", "portfolio"),
        # Company/portfolio spellings match the workbook identity keys; client
        # headers sometimes use all caps for presentation only.
        "client": ("company_certificate", "portfolio", "client_certificate"),
        "category": ("company_certificate", "portfolio", "client_certificate"),
        "value_inr": ("client_certificate", "company_certificate", "portfolio"),
        "completion_date": ("client_certificate", "company_certificate", "portfolio"),
        "project_lead": ("client_certificate", "company_certificate"),
        "role": ("portfolio",),
    }
    reconciled: Dict[str, ConsensusFact] = {}
    for field, priority in priorities.items():
        facts = [
            SourceFact(
                source=source_name,
                doc_id=str(record.get("doc_id", "")),
                field=field,
                value=record.get(field),
                raw_value=str(record.get("raw_value", "")) if field == "value_inr" else str(record.get(field, "")),
            )
            for source_name, record in sources.items()
        ]
        reconciled[field] = select_consensus(facts, priority)

    # An exact Indian-grouped client-certificate amount is more precise than
    # a rounded crore rendering in two secondary summaries.  Preserve that
    # lossless representation even when the rounded renderings agree.
    client_value = sources.get("client_certificate", {})
    client_raw = str(client_value.get("raw_value", ""))
    exact_grouped = re.fullmatch(r"(?:INR|Rs\.?|₹)?\s*\d{1,3}(?:,\d{2,3}){2,}", client_raw, re.I)
    if exact_grouped and int(client_value.get("value_inr") or 0) > 0:
        reconciled["value_inr"] = ConsensusFact(
            int(client_value["value_inr"]),
            "client_certificate",
            str(client_value.get("doc_id", "")),
            1,
            reconciled["value_inr"].evidence_count,
            "precision_authority",
        )
    return reconciled


def evidence_rows(
    package_number: int,
    sources: Mapping[str, Mapping[str, Any]],
    reconciled: Mapping[str, ConsensusFact],
) -> Iterable[Tuple[Any, ...]]:
    """Yield normalized rows suitable for ``project_fact_evidence``."""
    for source_name, record in sorted(sources.items()):
        for field in reconciled:
            value = record.get(field)
            if value in (None, ""):
                continue
            chosen = reconciled[field]
            yield (
                package_number,
                field,
                source_name,
                record.get("doc_id", ""),
                str(record.get("raw_value", "")) if field == "value_inr" else str(value),
                str(value),
                _identity(value) == _identity(chosen.value),
                chosen.status,
            )
