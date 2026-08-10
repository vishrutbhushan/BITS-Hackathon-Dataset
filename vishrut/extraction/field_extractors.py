"""
Per-doc-type field extraction from raw text (output of Stage 0).

These are heuristic, regex/positional extractors -- they will need
tuning once you're reading real documents, since layout varies across
the 62 issuing bodies (per BRIEFING.md section 1). Treat every function
here as a first draft: run it against a handful of real extracted text
files, see what it misses, and tighten the pattern.

Each extractor returns a dict of raw strings (not yet canonicalized --
that's parsers/*.py's job) plus None for anything not found, so a
missing field is visible rather than silently absorbed into a wrong
default.
"""
import re
from parsers.money import parse_money
from parsers.dates import parse_date
from parsers.grading import normalize_grading
from parsers.category import categorize

# --- generic helpers ------------------------------------------------------

_PROJECT_NAME_RE = re.compile(
    r"([A-Z][A-Za-z /\-]+ \u2014 [A-Za-z ]+ Pkg-\d+)"
)
_CLIENT_LINE_RE = re.compile(
    r"(?:Client|Employer|Department|Issued by)\s*:\s*(.+)", re.IGNORECASE
)
_ROLE_RE = re.compile(r"\b(Prime|Sub-?contractor|Joint Venture|JV)\b", re.IGNORECASE)
_REF_NO_RE = re.compile(r"Ref(?:erence)?\.?\s*No\.?\s*[:\-]?\s*([A-Za-z0-9/\-]+)")


def extract_completion_certificate(text: str) -> dict:
    """completion_certificate: value, dates, client, written grading."""
    project_name_match = _PROJECT_NAME_RE.search(text)
    client_match = _CLIENT_LINE_RE.search(text)
    role_match = _ROLE_RE.search(text)

    return {
        "project_name": project_name_match.group(1) if project_name_match else None,
        "client_raw": client_match.group(1).strip() if client_match else None,
        "value_rupees": parse_money(text),
        "completion_date": parse_date(text),  # NOTE: tighten with a label-anchored
                                               # search (e.g. text after "Completion Date:")
                                               # once you see real layouts -- a bare
                                               # parse_date(text) will grab the FIRST
                                               # date-like substring, which may not be
                                               # the completion date on a dense certificate.
        "grading": normalize_grading(text),
        "role": role_match.group(1) if role_match else None,
        "category": categorize(project_name_match.group(1)) if project_name_match else "other",
    }


def extract_reference_letter(text: str) -> dict:
    """reference_letter: existence is itself the signal (see graph/build_graph.py) --
    this just pulls the project it refers to, for linking."""
    project_name_match = _PROJECT_NAME_RE.search(text)
    return {
        "project_name": project_name_match.group(1) if project_name_match else None,
    }


def extract_personnel_certificate(text: str) -> dict:
    """personnel_certificate: engineer name, cert type, issue date."""
    # NOTE: placeholder patterns -- tune against real documents. Certs
    # likely have "Awarded to: <name>" and "Certification: PMP" style
    # lines; without real samples these are best-guess anchors.
    name_match = re.search(r"(?:Awarded to|Name)\s*:\s*([A-Z][a-zA-Z\. ]+)", text)
    cert_type_match = re.search(
        r"\b(PMP|Six Sigma (?:Black|Green) Belt|PRINCE2|ISO \d+ Lead Auditor)\b",
        text,
    )
    cert_number_match = re.search(r"(?:Cert(?:ificate)?\.?\s*No\.?|PMI-\d+)", text)
    return {
        "engineer_name": name_match.group(1).strip() if name_match else None,
        "cert_type": cert_type_match.group(1) if cert_type_match else None,
        "issue_date": parse_date(text),
    }


def extract_cv(text: str) -> dict:
    """cv: which works this engineer led."""
    name_match = re.search(r"(?:Name|Engineer)\s*:\s*([A-Z][a-zA-Z\. ]+)", text)
    project_names = _PROJECT_NAME_RE.findall(text)
    return {
        "engineer_name": name_match.group(1).strip() if name_match else None,
        "projects_led": project_names,
    }


# Registry so the extraction driver can dispatch by doc_type without a
# long if/elif chain. Extend as you add extractors for the remaining
# doc types (performance_bond, ra_bill, financial_statement, ...).
EXTRACTORS = {
    "completion_certificate": extract_completion_certificate,
    "reference_letter": extract_reference_letter,
    "personnel_certificate": extract_personnel_certificate,
    "cv": extract_cv,
}


def extract(doc_type: str, text: str) -> dict:
    fn = EXTRACTORS.get(doc_type)
    if fn is None:
        return {}
    return fn(text)
