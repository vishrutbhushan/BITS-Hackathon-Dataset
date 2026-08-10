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
    r"([A-Z][A-Za-z0-9 /\-&',]+\s*(?:[\u2013\u2014-]|--)\s*[A-Za-z0-9 /\-&',]+\s+Pkg-\d+)"
)
_CLIENT_LINE_RE = re.compile(
    r"(?:Client|Employer|Department|Issued by)\s*:\s*(.+)", re.IGNORECASE
)
_ROLE_RE = re.compile(r"\b(Prime|Sub-?contractor|Joint Venture|JV)\b", re.IGNORECASE)
_REF_NO_RE = re.compile(r"Ref(?:erence)?\.?\s*No\.?\s*[:\-]?\s*([A-Za-z0-9/\-]+)")

def extract_project_name(text: str) -> str:
    # 1. Try regex with flexible dashes
    match = _PROJECT_NAME_RE.search(text)
    if match:
        return match.group(1).strip()
    # 2. Try looking for line after Name of Work
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if "Name of Work" in line and i + 1 < len(lines):
            val = lines[i+1].strip()
            if val:
                return val
    return None

def extract_client_name(text: str) -> str:
    match = _CLIENT_LINE_RE.search(text)
    if match:
        return match.group(1).strip()
    # First non-empty line that isn't a page/doc boundary
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    for line in lines:
        if line.startswith("--- page") or line.startswith("--- Page") or "CONFIDENTIAL" in line:
            continue
        return line
    return None

def extract_engineer_name(text: str) -> str:
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if "Contractor's Project Manager" in line and i + 1 < len(lines):
            val = lines[i+1].strip()
            if val:
                return val
    match = re.search(r"supervised on the contractor's side by\s+([A-Z][a-zA-Z\. ]+)", text, re.I)
    if match:
        return match.group(1).strip()
    return None

def extract_completion_certificate(text: str) -> dict:
    """completion_certificate: value, dates, client, written grading."""
    proj_name = extract_project_name(text)
    client_name = extract_client_name(text)
    engineer_name = extract_engineer_name(text)
    role_match = _ROLE_RE.search(text)

    return {
        "project_name": proj_name,
        "client_raw": client_name,
        "engineer_name": engineer_name,
        "value_rupees": parse_money(text),
        "completion_date": parse_date(text),
        "grading": normalize_grading(text),
        "role": role_match.group(1) if role_match else None,
        "category": categorize(proj_name) if proj_name else "other",
    }


def extract_reference_letter(text: str) -> dict:
    """reference_letter: existence is itself the signal (see graph/build_graph.py) --
    this just pulls the project it refers to, for linking."""
    proj_name = extract_project_name(text)
    return {
        "project_name": proj_name,
    }


def extract_personnel_certificate(text: str) -> dict:
    """personnel_certificate: engineer name, cert type, issue date."""
    lines = text.split('\n')
    engineer_name = None
    for i, line in enumerate(lines):
        if ("This is to certify that" in line or "conferred upon" in line or "conferred on" in line) and i + 1 < len(lines):
            val = lines[i+1].strip()
            if val:
                engineer_name = val
                break
    if not engineer_name:
        name_match = re.search(r"(?:Awarded to|Name)\s*:\s*([A-Z][a-zA-Z\. ]+)", text)
        if name_match:
            engineer_name = name_match.group(1).strip()
            
    cert_type_match = re.search(
        r"\b(PMP|Six Sigma (?:Black|Green) Belt|PRINCE2|ISO \d+ Lead Auditor)\b",
        text,
    )
    cert_number_match = re.search(r"(?:Cert(?:ificate)?\.?\s*No\.?|PMI-\d+)", text)
    return {
        "engineer_name": engineer_name,
        "cert_type": cert_type_match.group(1) if cert_type_match else None,
        "issue_date": parse_date(text),
    }


def extract_cv(text: str) -> dict:
    """cv: which works this engineer led."""
    lines = text.split('\n')
    engineer_name = None
    for i, line in enumerate(lines):
        if "Name" in line and i + 1 < len(lines):
            val = lines[i+1].strip()
            if val and not val.startswith("Curriculum") and not val.startswith("Employee"):
                engineer_name = val
                break
    if not engineer_name:
        name_match = re.search(r"(?:Name|Engineer)\s*:\s*([A-Z][a-zA-Z\. ]+)", text)
        if name_match:
            engineer_name = name_match.group(1).strip()
            
    project_names = _PROJECT_NAME_RE.findall(text)
    return {
        "engineer_name": engineer_name,
        "projects_led": project_names,
    }


def extract_company_completion_certificate(text: str) -> dict:
    """company_completion_certificate: perfectly formatted company record."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    project_name = None
    client_raw = None
    category_raw = None
    value_raw = None
    completion_date_raw = None
    engineer_name = None
    
    for i, line in enumerate(lines):
        if line.lower() in ("work", "project name") and i + 1 < len(lines):
            project_name = lines[i+1]
            break
            
    for i, line in enumerate(lines):
        if line.lower() == "client" and i + 1 < len(lines):
            client_raw = lines[i+1]
            break
            
    for i, line in enumerate(lines):
        if line.lower() in ("category", "work category") and i + 1 < len(lines):
            category_raw = lines[i+1]
            break
            
    for i, line in enumerate(lines):
        if line.lower() in ("executed value", "value", "contract value") and i + 1 < len(lines):
            value_raw = lines[i+1]
            break
            
    for i, line in enumerate(lines):
        if line.lower() in ("completion", "completion date") and i + 1 < len(lines):
            completion_date_raw = lines[i+1]
            break
            
    for i, line in enumerate(lines):
        if line.lower() in ("project lead", "project manager") and i + 1 < len(lines):
            engineer_name = lines[i+1]
            break
            
    # Clean the fields
    client_name = re.sub(r'\s*\((government|private|psu)\)\s*$', '', client_raw, flags=re.I).strip() if client_raw else None
    
    # Clean engineer name (stop at period or "This certificate")
    if engineer_name:
        engineer_name = re.split(r'\.|\bThis certificate\b', engineer_name, flags=re.I)[0].strip()
        
    return {
        "project_name": project_name,
        "client_name": client_name,
        "client_raw": client_raw,
        "category": categorize(category_raw) if category_raw else "other",
        "value_rupees": parse_money(value_raw) if value_raw else parse_money(text),
        "completion_date": parse_date(completion_date_raw) if completion_date_raw else parse_date(text),
        "engineer_name": engineer_name,
    }


# Registry so the extraction driver can dispatch by doc_type without a
# long if/elif chain. Extend as you add extractors for the remaining
# doc types (performance_bond, ra_bill, financial_statement, ...).
EXTRACTORS = {
    "completion_certificate": extract_completion_certificate,
    "company_completion_certificate": extract_company_completion_certificate,
    "reference_letter": extract_reference_letter,
    "personnel_certificate": extract_personnel_certificate,
    "cv": extract_cv,
}


def extract(doc_type: str, text: str) -> dict:
    fn = EXTRACTORS.get(doc_type)
    if fn is None:
        return {}
    return fn(text)
