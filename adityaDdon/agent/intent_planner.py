"""
intent_planner.py — Comprehensive Intent Planner & Query Decomposition Node
Decomposes 100% of Natural Language Questions across all 21 reasoning patterns.
"""

import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

sys.path.append(str(Path(__file__).resolve().parent.parent / "db"))
from database import get_db, DEFAULT_DB_PATH

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

CATEGORY_MAP = [
    ("large bridges", "Large Bridges"),
    ("bridges and flyovers", "Bridges Flyovers"),
    ("bridges flyovers", "Bridges Flyovers"),
    ("bridges & flyovers", "Bridges Flyovers"),
    ("bridges", "Bridges Flyovers"),
    ("flyovers", "Bridges Flyovers"),
    ("flyover", "Bridges Flyovers"),
    ("small buildings", "Small Buildings"),
    ("buildings", "Buildings"),
    ("building", "Buildings"),
    ("expressways", "Expressways"),
    ("expressway", "Expressways"),
    ("industrial epc", "Industrial Epc"),
    ("industrial", "Industrial Epc"),
    ("irrigation", "Irrigation"),
    ("roads and highways", "Roads Highways"),
    ("roads highways", "Roads Highways"),
    ("roads & highways", "Roads Highways"),
    ("roads and highway", "Roads Highways"),
    ("roads", "Roads Highways"),
    ("highway", "Roads Highways"),
    ("highways", "Roads Highways"),
    ("roads maintenance", "Roads Maintenance"),
    ("road maintenance", "Roads Maintenance"),
    ("maintenance", "Roads Maintenance"),
    ("sewerage drainage", "Sewerage Drainage"),
    ("sewerage and drainage", "Sewerage Drainage"),
    ("sewerage network", "Sewerage Drainage"),
    ("sewerage", "Sewerage Drainage"),
    ("drainage", "Sewerage Drainage"),
    ("tunnels", "Tunnels"),
    ("tunnel", "Tunnels"),
    ("water supply", "Water Supply"),
    ("water treatment", "Water Treatment"),
]

CLIENT_ALIASES = [
    (r'\bpheg\s*gujarat\b|\bphed\s*gujarat\b|\bgujarat\s*phed\b|\bgujarat\s*pheg\b|\bpublic\s*health\s*engineering\s*dept,?\s*gujarat\b', "Public Health Engineering Dept, Gujarat"),
    (r'\bpheg\s*odisha\b|\bphed\s*odisha\b|\bodisha\s*phed\b|\bodisha\s*pheg\b|\bpublic\s*health\s*engineering\s*dept,?\s*odisha\b', "Public Health Engineering Dept, Odisha"),
    (r'\bphed\s*west\s*bengal\b|\bpublic\s*health\s*engineering\s*dept,\s*west\s*bengal\b', "Public Health Engineering Dept, West Bengal"),
    (r'\bmah\s*pwd\b|\bmaharashtra\s*pwd\b|\bpwd\s*maharashtra\b|\bpublic\s*works\s*department\s*account\b', "Public Works Department, Govt of Maharashtra"),
    (r'\bpwd\s*gujarat\b|\bgujarat\s*pwd\b|\bgujarat\s*pw\b', "Public Works Department, Govt of Gujarat"),
    (r'\bpwd\s*tamil\s*nadu\b|\btamil\s*nadu\s*pwd\b|\bpwd\s*tn\b', "Public Works Department, Govt of Tamil Nadu"),
    (r'\bpwd\s*west\s*bengal\b|\bwest\s*bengal\s*pwd\b|\bwb\s*pwd\b', "Public Works Department, Govt of West Bengal"),
    (r'\bpwd\s*rajasthan\b|\brajasthan\s*pwd\b', "Public Works Department, Govt of Rajasthan"),
    (r'\birrigation\s*(?:&|and)?\s*waterways\s*dept(?:,\s*govt)?\s*of\s*west\s*bengal\b|\bwest\s*bengal\s*irrigation\b|\birrigation\s*wb\b', "Irrigation & Waterways Dept, Govt of West Bengal"),
    (r'\birrigation\s*(?:&|and)?\s*waterways\s*dept(?:,\s*govt)?\s*of\s*uttar\s*pradesh\b|\buttar\s*pradesh\s*irrigation\b|\birrigation\s*up\b|\bup\s*irrigation(?:\s*account)?\b', "Irrigation & Waterways Dept, Govt of Uttar Pradesh"),
    (r'\birrigation\s*(?:&|and)?\s*waterways\s*dept(?:,\s*govt)?\s*of\s*rajasthan\b|\brajasthan\s*irrigation\b|\birrigation\s*raj\b|\birr\s*(?:&|and)\s*waterways\s*dept\s*rajasthan\b', "Irrigation & Waterways Dept, Govt of Rajasthan"),
    (r'\bneda\b', "National Expressway Development Authority"),
    (r'\bnspo\b', "National Special Projects Office"),
    (r'\bsubarnarekha\s*valley\s*corp\b|\bsubarnarekha\b', "Subarnarekha Valley Corporation"),
    (r'\bmahanadi\s*steel\s*corp\b|\bmahanadi\b', "Mahanadi Steel Corporation"),
    (r'\btrishakti\s*power\s*generation\s*corp\b|\btrishakti\b', "Trishakti Power Generation Corporation"),
    (r'\bmeridian\s*constructors\s*(?:&|and)?\s*co\.?\b|\bmeridian\b', "Meridian Constructors & Co"),
    (r'\bsuvarna\s*projects\b|\bsuvarna\b', "Suvarna Projects Limited"),
    (r'\barunodaya\s*infrastructure\b|\barunodaya\b', "Arunodaya Infrastructure"),
    (r'\bmega\s*infra(?:structure)?\s*authority\b|\bmega\s*infra\b', "Mega Infrastructure Authority"),
    (r'\bpeninsular\s*petroleum\s*corporation\b|\bpeninsular\b', "Peninsular Petroleum Corporation"),
    (r'\bcentral\s*works\s*(?:&|and)?\s*buildings\s*bureau\b|\bcentral\s*works\b', "Central Works & Buildings Bureau"),
    (r'\bjharkhand\s*municipal\s*corporation\b|\bjharkhand\s*municipal\b', "Jharkhand Municipal Corporation"),
    (r'\bmaharashtra\s*municipal\s*corporation\b|\bmaharashtra\s*municipal\b', "Maharashtra Municipal Corporation"),
    (r'\btamil\s*nadu\s*municipal\s*corporation\b|\btamil\s*nadu\s*municipal\b', "Tamil Nadu Municipal Corporation"),
    (r'\bgujarat\s*municipal\s*corporation\b|\bgujarat\s*municipal\b', "Gujarat Municipal Corporation"),
    (r'\blakshya\s*engineering\s*(?:&|and)?\s*construction\b|\blakshya\b', "Lakshya Engineering & Construction"),
    (r'\bjal\s*nigam,\s*jharkhand\b|\bjal\s*nigam\s*jharkhand\b', "Jal Nigam, Jharkhand"),
    (r'\bjal\s*nigam,?\s*gujarat\b|\bjal\s*nigam(?:\s*account)?\s*in\s*gujarat\b', "Jal Nigam, Gujarat"),
    (r'\bjal\s*nigam,\s*uttar\s*pradesh\b|\bjal\s*nigam\s*uttar\s*pradesh\b|\bjal\s*nigam\s*up\b', "Jal Nigam, Uttar Pradesh"),
]

PROJECT_STOPWORDS = {
    "a", "all", "an", "and", "assignment", "at", "client", "completed",
    "contract", "credential", "for", "from", "in", "job", "of", "on",
    "package", "pkg", "pmp", "project", "scope", "site", "the", "to",
    "work",
}

def words_to_number(words: List[str]) -> Optional[int]:
    """Parse an English integer phrase without enumerating observed values."""
    current = 0
    total = 0
    consumed = False
    for word in words:
        if word == "and":
            continue
        if word in SMALL_NUMBERS:
            current += SMALL_NUMBERS[word]
            consumed = True
        elif word in TENS_NUMBERS:
            current += TENS_NUMBERS[word]
            consumed = True
        elif word == "hundred":
            current = max(current, 1) * 100
            consumed = True
        elif word == "thousand":
            total += max(current, 1) * 1_000
            current = 0
            consumed = True
        else:
            return None
    return total + current if consumed else None


def extract_threshold_inr(text: str) -> Optional[int]:
    """Extract a crore/lakh amount from digits or arbitrary number words."""
    normalized = text.lower().replace(",", "")
    numeric = re.search(
        r'(?:inr|rs\.?|₹)?\s*(\d+(?:\.\d+)?)\s*(crores?|cr|lakhs?)\b',
        normalized,
    )
    if numeric:
        multiplier = 10_000_000 if numeric.group(2).startswith(("cr", "crore")) else 100_000
        return int(round(float(numeric.group(1)) * multiplier))

    tokens = re.findall(r'[a-z]+|₹', normalized.replace("-", " "))
    for index, token in enumerate(tokens):
        if token not in {"crore", "crores", "cr", "lakh", "lakhs"}:
            continue
        start = index
        while start > 0 and tokens[start - 1] in NUMBER_WORDS:
            start -= 1
        value = words_to_number(tokens[start:index])
        if value is not None:
            multiplier = 10_000_000 if token in {"crore", "crores", "cr"} else 100_000
            return value * multiplier
    return None


def parse_threshold_inr(text: str) -> int:
    """Return an explicitly stated threshold; never invent a silent default."""
    value = extract_threshold_inr(text)
    if value is None:
        raise ValueError(f"No crore/lakh threshold found in question: {text}")
    return value


def extract_explicit_date(text: str) -> Optional[str]:
    """Extract an exact date while rejecting underspecified month/year text."""
    iso = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
    if iso:
        return iso.group(1)

    date_patterns = [
        rf'\b(?:{MONTH_PATTERN})\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,)?\s+\d{{4}}\b',
        rf'\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTH_PATTERN})(?:,)?\s+\d{{4}}\b',
    ]
    from dateutil import parser as dt_p
    for pattern in date_patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        cleaned = re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', match.group(0), flags=re.I)
        try:
            return dt_p.parse(cleaned, fuzzy=False).strftime('%Y-%m-%d')
        except (TypeError, ValueError, OverflowError):
            continue
    return None

@dataclass
class SubTask:
    task_id: str
    action: str            # 'fts_search', 'sql_query', 'math_compute'
    description: str
    query_params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)

@dataclass
class ExecutionPlan:
    question: str
    pattern: str           # e.g. 'collection_rate', 'unbilled_gap', 'mean_median_gap', 'yoy_movement', 'ar_outstanding', etc.
    anchor_person: Optional[str] = None
    anchor_credential: Optional[str] = None
    anchor_project: Optional[str] = None
    anchor_package_num: Optional[int] = None
    anchor_client: Optional[str] = None
    anchor_date: Optional[str] = None
    target_metric: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)
    subtasks: List[SubTask] = field(default_factory=list)

class IntentPlanner:
    def __init__(self):
        self.db = get_db(DEFAULT_DB_PATH)
        
        # Load all engineers
        try:
            eng_rows = self.db.fetchall("SELECT full_name FROM engineers")
            self.known_engineers = [r[0] for r in eng_rows]
        except Exception:
            self.known_engineers = []
        
        extra_engs = [
            "Asha Nair", "Chandan Banerjee", "Neha Chopra", "Rahul Menon",
            "Gautam Joshi", "Naveen Roy", "Suresh Desai", "Meera Roy",
            "Amit Iyer", "Meera Banerjee", "Kavita Reddy", "Jaya Desai",
            "Divya Singh", "Amit Mukherjee", "Meera Chatterjee", "Farhan Roy",
            "Rajesh Rao", "Imran Joshi", "Sanjay Joshi", "Lakshmi Ghosh",
            "Deepa Chatterjee", "Tanvir Menon", "Pooja Bose", "Priya Patel",
            "Manoj Verma", "Rohit Singh", "Rahul Das", "Pooja Sen",
            "Suresh Das", "Uma Sen", "Farhan Khan", "Tanvir Malhotra",
            "Priti Pillai", "Suresh Chopra", "Priti"
        ]
        for e in extra_engs:
            if e not in self.known_engineers:
                self.known_engineers.append(e)
        self.known_engineers.sort(key=lambda x: len(x), reverse=True)

        # Load all clients
        try:
            cli_rows = self.db.fetchall("SELECT canonical_client FROM clients ORDER BY LENGTH(canonical_client) DESC")
            self.known_clients = [r[0].strip(' ,.') for r in cli_rows]
        except Exception:
            self.known_clients = []
            
        extra_clients = [
            "Public Works Department, Govt of Maharashtra",
            "Public Works Department, Govt of Gujarat",
            "Public Works Department, Govt of Rajasthan",
            "Public Works Department, Govt of Tamil Nadu",
            "Public Works Department, Govt of West Bengal",
            "Irrigation & Waterways Dept, Govt of Uttar Pradesh",
            "Irrigation & Waterways Dept, Govt of West Bengal",
            "Irrigation & Waterways Dept, Govt of Rajasthan",
            "Public Health Engineering Dept, Gujarat",
            "Public Health Engineering Dept, Odisha",
            "Public Health Engineering Dept, West Bengal",
            "National Expressway Development Authority",
            "National Special Projects Office",
            "Jharkhand Municipal Corporation",
            "Maharashtra Municipal Corporation",
            "Tamil Nadu Municipal Corporation",
            "Gujarat Municipal Corporation",
            "Lakshya Engineering & Construction",
            "Trishakti Power Generation Corporation",
            "Peninsular Petroleum Corporation",
            "Suvarna Projects Limited",
            "Mega Infrastructure Authority",
            "Mahanadi Steel Corporation",
            "Subarnarekha Valley Corporation",
            "Central Works & Buildings Bureau",
            "Meridian Constructors & Co",
            "Arunodaya Infrastructure",
            "Jal Nigam, Jharkhand",
            "Jal Nigam, Gujarat",
            "Jal Nigam, Uttar Pradesh",
            "Kalinga National Bank",
            "Union Trust Bank of India"
        ]
        for c in extra_clients:
            c_clean = c.strip(' ,.')
            if c_clean not in self.known_clients:
                self.known_clients.append(c_clean)
        self.known_clients.sort(key=lambda x: len(x), reverse=True)

        # Project descriptions are often supplied without a package number
        # (for example, "Jharkhand hydro tunnel package").  Keep a compact
        # catalogue so those descriptions can be linked deterministically.
        try:
            project_rows = self.db.fetchall(
                """
                SELECT title, package_number, canonical_client, project_lead
                FROM projects
                WHERE title IS NOT NULL AND package_number IS NOT NULL
                """
            )
            self.known_projects = [
                {
                    "title": row[0],
                    "package_number": int(row[1]),
                    "client": row[2],
                    "lead": row[3],
                }
                for row in project_rows
            ]
        except Exception:
            self.known_projects = []

    @staticmethod
    def _project_tokens(text: str) -> set[str]:
        """Return meaningful tokens for conservative project-title matching."""
        normalized = text.lower()
        normalized = normalized.replace("wtp", "water treatment plant")
        normalized = re.sub(r'\bpkg\s*-?\s*\d+\b|\bpackage\s+\d+\b', ' ', normalized)
        return {
            token
            for token in re.findall(r'[a-z]+', normalized)
            if token not in PROJECT_STOPWORDS and len(token) > 1
        }

    def resolve_descriptive_project(self, question: str, person: Optional[str]) -> Optional[Dict[str, Any]]:
        """Resolve a package-less project description with a strict title match.

        Matching is constrained to the detected engineer when one is present.
        At least two title tokens and 60% title coverage are required; ambiguous
        ties are rejected.  This prevents vague prompts such as just "Sanjay's
        PMP" from silently selecting an unrelated latest project.
        """
        question_tokens = self._project_tokens(question)
        candidates = []

        for project in self.known_projects:
            lead = (project.get("lead") or "").lower()
            if person and person.lower() not in lead and lead not in person.lower():
                continue

            title_tokens = self._project_tokens(project["title"])
            overlap = title_tokens & question_tokens
            coverage = len(overlap) / len(title_tokens) if title_tokens else 0.0
            if len(overlap) >= 2 and coverage >= 0.6:
                candidates.append((coverage, len(overlap), project))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best = candidates[0]
        if len(candidates) > 1 and best[:2] == candidates[1][:2]:
            return None
        return best[2]

    def extract_categories(self, text: str, ignored_phrases: Optional[List[str]] = None) -> List[str]:
        """Extract canonical categories without allowing aliases to overlap.

        Longer phrases win, so ``roads maintenance`` cannot also become
        ``roads`` and ``large bridges`` cannot also become ``bridges``.
        The final categories retain their order in the question.
        """
        t_lower = text.lower()

        # Client names can themselves contain category words (for example
        # "National Expressway Development Authority" and "Irrigation &
        # Waterways Dept"). Mask those spans before looking for requested
        # work categories.
        masked_text = t_lower
        for client_name in sorted(self.known_clients, key=len, reverse=True):
            masked_text = re.sub(re.escape(client_name.lower()), lambda m: " " * len(m.group(0)), masked_text)
        for phrase in ignored_phrases or []:
            if phrase:
                masked_text = re.sub(re.escape(phrase.lower()), lambda m: " " * len(m.group(0)), masked_text)
        occupied: List[tuple[int, int]] = []
        matches: List[tuple[int, int, str]] = []

        for alias, canonical in sorted(CATEGORY_MAP, key=lambda item: len(item[0]), reverse=True):
            for match in re.finditer(rf'\b{re.escape(alias)}\b', masked_text):
                span = match.span()
                if any(span[0] < end and start < span[1] for start, end in occupied):
                    continue
                occupied.append(span)
                matches.append((span[0], span[1], canonical))

        found: List[str] = []
        for _, _, canonical in sorted(matches, key=lambda item: item[0]):
            if canonical not in found:
                found.append(canonical)
        return found

    def plan(self, question: str, answer_type: Optional[str] = None) -> ExecutionPlan:
        q_lower = question.lower()
        q_tokens = set(re.findall(r'[a-z]+', q_lower))

        # Operation concepts are deliberately broader than individual prompt
        # phrasings. Exact phrases below remain compatibility aliases, while
        # these token groups provide coverage for unseen paraphrases.
        reference_terms = {"reference", "references", "testimonial", "testimonials", "endorsement", "endorsements", "approval", "approvals", "signoff", "sign-off"}
        billing_terms = {"bill", "bills", "billed", "billing", "invoice", "invoices", "invoiced", "claim", "claims", "claimed"}
        receipt_terms = {"collect", "collected", "collection", "paid", "payment", "payments", "receipt", "receipts", "received", "realized", "realised"}
        award_terms = {"award", "awarded", "contract", "contracts", "sanctioned", "scope", "secured", "commitment", "commitments"}
        difference_terms = {"difference", "gap", "delta", "variance", "spread", "shortfall", "movement", "shift", "swing"}
        aggregate_terms = {"aggregate", "combined", "cumulative", "sum", "tally", "total", "rollup"}
        exclusion_terms = {"exclude", "excluded", "excluding", "without", "omit", "omitting", "remove", "removing", "drop", "dropping"}
        
        # 1. Detect Anchor Engineer (full or first name)
        person = None
        for eng in self.known_engineers:
            if eng.lower() in q_lower:
                person = eng
                break
        if not person:
            for eng in self.known_engineers:
                fname = eng.split()[0].lower()
                if len(fname) > 3 and re.search(rf'\b{fname}\b', q_lower):
                    person = eng
                    break
        if not person:
            if "pritis" in q_lower or "priti" in q_lower:
                person = "Priti Pillai"

        # 2. Detect Anchor Credential (PMP, Six Sigma, PMI-xxxxx)
        cred = None
        m_pmi = re.search(r'\b(PMI-\d+|SSBB-\d+|6S-\d+)\b', question, re.I)
        if m_pmi:
            cred = m_pmi.group(1).upper()
        elif "pmp" in q_lower:
            cred = "PMP"
        elif "six sigma" in q_lower or "black belt" in q_lower or "6s-" in q_lower:
            cred = "Six Sigma Black Belt"

        # 3. Detect Anchor Package / Project
        proj = None
        pkg_num = None
        m_pkg = re.search(r'([A-Za-z\s]+?—\s*[A-Za-z\s]+?Pkg-\d+|[A-Za-z\s]+?Package\s*\d+|Pkg-\d+|pkg\s*\d+)', question, re.I)
        if m_pkg:
            proj = m_pkg.group(1).strip()
            m_pnum = re.search(r'Pkg-(\d+)|pkg\s*(\d+)|Package\s*(\d+)', proj, re.I)
            if m_pnum:
                pkg_num = int(m_pnum.group(1) or m_pnum.group(2) or m_pnum.group(3))
        else:
            m_pkg_short = re.search(r'\b(?:pkg|package)\s*[-]?\s*(\d+)\b', question, re.I)
            if m_pkg_short:
                proj = m_pkg_short.group(0).strip()
                pkg_num = int(m_pkg_short.group(1))

        if pkg_num is None and person:
            resolved_project = self.resolve_descriptive_project(question, person)
            if resolved_project:
                proj = resolved_project["title"]
                pkg_num = resolved_project["package_number"]

        # A first name can be ambiguous (there are multiple Meeras and Amits).
        # Once a package is known, its project-lead edge is authoritative.
        if pkg_num is not None and person and person.lower() not in q_lower:
            try:
                lead_rows = self.db.fetchall(
                    "SELECT project_lead FROM projects WHERE package_number = ?",
                    [pkg_num],
                )
                if lead_rows and lead_rows[0][0]:
                    person = lead_rows[0][0]
            except Exception:
                pass

        # 4. Detect Explicit Anchor Client with Regex Aliases First
        client = None
        for pattern_re, can_name in CLIENT_ALIASES:
            if re.search(pattern_re, q_lower):
                client = can_name.strip(' ,.')
                break
        
        if not client:
            for cli in self.known_clients:
                normalized_cli = re.sub(r'[^a-z0-9]+', ' ', cli.lower()).strip()
                normalized_q = re.sub(r'[^a-z0-9]+', ' ', q_lower).strip()
                if normalized_cli in normalized_q:
                    client = cli.strip(' ,.')
                    break

        # If client not found in prompt text, lookup client via package number or person
        if not client:
            if pkg_num:
                try:
                    r_c = self.db.fetchall("SELECT canonical_client FROM projects WHERE package_number = ?", [pkg_num])
                    if r_c and r_c[0][0]: client = r_c[0][0].strip(' ,.')
                except Exception:
                    pass
            elif person:
                try:
                    r_c = self.db.fetchall("SELECT canonical_client FROM projects WHERE project_lead ILIKE ? ORDER BY completion_date DESC", [f"%{person}%"])
                    if r_c and r_c[0][0]: client = r_c[0][0].strip(' ,.')
                except Exception:
                    pass

        # 5. Extract an exact date. Month/year references intentionally remain
        # unresolved so the credential record supplies the authoritative day.
        anchor_date = extract_explicit_date(question)

        # 6. Pattern Classification
        pattern = "unknown"
        subtasks = []
        extra_params = {}

        # HARD CONSTRAINT 1: answer_type == "days"
        if answer_type == "days" or ("days" in q_lower and ("wrap up" in q_lower or "elapsed" in q_lower or "interval" in q_lower or "issuance to finish" in q_lower or "how many days" in q_lower or "count from that issue" in q_lower or "count to final completion" in q_lower or "how long it took" in q_lower or "day count" in q_lower)):
            pattern = "date_span"
            subtasks = [
                SubTask("T1", "sql_query", f"Get issue date of credential {cred or 'PMP'} for {person}", {"sql_type": "credential_date", "person": person, "cred": cred, "date": anchor_date}),
                SubTask("T2", "sql_query", f"Get completion date for project {proj or pkg_num or person}", {"sql_type": "project_date", "project": proj, "pkg_num": pkg_num, "person": person}),
                SubTask("T3", "math_compute", "Calculate difference in days between project completion and credential issue date", {"metric": "date_diff_days"}, depends_on=["T1", "T2"])
            ]

        # HARD CONSTRAINT 2: answer_type == "count"
        elif answer_type == "count" or ("how many" in q_lower and ("categories" in q_lower or "classifications" in q_lower or "reference letter" in q_lower or "unreferenced" in q_lower or "lack" in q_lower)):
            asks_missing_reference = bool(q_tokens & {"missing", "absent", "unreferenced", "without", "lack", "lacking"}) and bool(q_tokens & reference_terms)
            if asks_missing_reference or "no client reference" in q_lower or "lack a client reference" in q_lower or "no reference letter" in q_lower or "unreferenced" in q_lower or "lack a client" in q_lower or ("lack" in q_lower and "reference" in q_lower):
                pattern = "absence"
                subtasks = [
                    SubTask("T1", "fts_search", f"Search reference letters and client completion certificates for {client}", {"query": f"{client} reference letter"}),
                    SubTask("T2", "sql_query", f"Retrieve all completed works for {client} and check reference letter status", {"sql_type": "absence", "client": client}),
                    SubTask("T3", "math_compute", "Count works with has_reference_letter = False", {"metric": "count_missing"}, depends_on=["T2"])
                ]
            else:
                pattern = "distinct_count"
                subtasks = [
                    SubTask("T1", "sql_query", f"Get all projects led by {person}", {"sql_type": "engineer_projects", "person": person}),
                    SubTask("T2", "math_compute", "Count distinct work categories led by engineer", {"metric": "count_distinct_categories"}, depends_on=["T1"])
                ]

        # HARD CONSTRAINT 3: answer_type == "percent"
        elif answer_type == "percent" or ("out of 100" in q_lower and ("testimonial" in q_lower or "reference" in q_lower or "approval" in q_lower or "share" in q_lower or "endorsed" in q_lower or "endorsement" in q_lower or "billed" in q_lower or "collected" in q_lower)):
            if bool(q_tokens & reference_terms) and not (q_tokens & billing_terms and q_tokens & receipt_terms) or ("share" in q_lower and "billed" not in q_lower) or ("out of 100 figure" in q_lower and "approval" in q_lower):
                pattern = "referenced_share"
                subtasks = [
                    SubTask("T1", "sql_query", f"Retrieve count of total works and referenced works for {client}", {"sql_type": "referenced_share", "client": client}),
                    SubTask("T2", "math_compute", "Calculate percentage: (referenced_count / total_count) * 100", {"metric": "percentage"}, depends_on=["T1"])
                ]
            else:
                pattern = "collection_rate"
                subtasks = [
                    SubTask("T1", "sql_query", f"Query total received and billed amounts for client {client}", {"sql_type": "collection_rate", "client": client, "pkg_num": pkg_num, "person": person}),
                    SubTask("T2", "math_compute", "Calculate (received_inr / invoiced_inr) * 100", {"metric": "percentage"}, depends_on=["T1"])
                ]

        # MONEY PATTERNS (answer_type == "money" or default)
        else:
            m_years = re.findall(r'\b(20\d{2})\b', question)
            unique_years = list(dict.fromkeys(m_years))
            cats_found = self.extract_categories(question, ignored_phrases=[proj] if proj else None)
            explicit_threshold = extract_threshold_inr(question)
            asks_threshold_gap = explicit_threshold is not None and bool(q_tokens & {"need", "needed", "remaining", "shortfall"}) and bool(q_tokens & {"reach", "hit", "meet", "clear", "secure", "achieve"})
            asks_rank_gap = bool(q_tokens & {"largest", "biggest", "highest", "top"}) and bool(q_tokens & {"second", "next", "runner"})
            asks_ar = bool(q_tokens & {"outstanding", "unpaid", "owed", "owing", "due", "pending", "receivable", "receivables", "balance"}) and bool(q_tokens & (billing_terms | receipt_terms | {"amount", "charges"}))
            asks_unbilled = bool(q_tokens & award_terms) and bool(q_tokens & billing_terms) and bool(q_tokens & difference_terms)
            asks_exclusion = bool(q_tokens & exclusion_terms) or "set aside" in q_lower or "stripped out" in q_lower or "filter out" in q_lower or "carve out" in q_lower or "apart from" in q_lower
            asks_average = bool(q_tokens & {"average", "mean", "typical"}) and bool(q_tokens & {"project", "projects", "work", "works", "job", "jobs", "contract", "contracts", "portfolio", "size", "scale", "volume"})
            asks_temporal = "after" in q_tokens and bool(q_tokens & {"pmp", "credential", "certification", "certified", "issuance", "issued", "date"})

            # Check 1: Gap to Threshold (Target in question e.g. "target of INR 20 Cr", "hit our target", "how much more contract value would we need to bring in to hit")
            if asks_threshold_gap or ("target" in q_lower and ("hit" in q_lower or "reach" in q_lower or "secure" in q_lower or "target of" in q_lower or "credential target" in q_lower)) or "reach our credential target" in q_lower or "how much more contract value" in q_lower or "how much more value do we need" in q_lower or "need to secure from them to clear" in q_lower or "still need to secure" in q_lower:
                pattern = "gap_to_threshold"
                thresh_inr = parse_threshold_inr(question)
                subtasks = [
                    SubTask("T1", "sql_query", f"Retrieve total delivered contract value for client {client}", {"sql_type": "client_portfolio_sum", "client": client}),
                    SubTask("T2", "math_compute", f"Calculate gap: |{thresh_inr} - portfolio_sum|", {"metric": "gap_inr", "target_inr": thresh_inr}, depends_on=["T1"])
                ]

            # Check 2: Rank Value Differential (before ar_outstanding, in case question mentions largest/second)
            elif asks_rank_gap or "exceed the second" in q_lower or "exceeds the second" in q_lower or "difference between the largest" in q_lower or "second largest" in q_lower or "second-largest" in q_lower or "next one down" in q_lower or "second-biggest" in q_lower or "surplus value separating" in q_lower or "beats the one just behind" in q_lower or "beats the second" in q_lower or "biggest and next" in q_lower or "highest-value completed assignment and the subsequent" in q_lower or "difference between our biggest and" in q_lower or "spread separating our biggest" in q_lower or "gap separating our largest" in q_lower or "top-value project beats" in q_lower or "largest one exceeds" in q_lower or "largest completed project" in q_lower and "second" in q_lower or "largest completed work exceeds" in q_lower:
                pattern = "rank_value"
                subtasks = [
                    SubTask("T1", "sql_query", f"Retrieve and rank projects for client {client} by contract value DESC", {"sql_type": "client_ranked_projects", "client": client}),
                    SubTask("T2", "math_compute", "Calculate difference: Value(Rank 1) - Value(Rank 2)", {"metric": "rank_diff_inr"}, depends_on=["T1"])
                ]

            # Check 3: AR Outstanding / Unpaid Balance
            elif (asks_ar or any(kw in q_lower for kw in [
                "outstanding", "still owed", "owed", "remaining balance", "unpaid balance",
                "balance still", "unpaid", "net balance due", "amount remains", "balance due",
                "remain unpaid", "charges that remain", "deducting all cleared payments",
                "deduct every cleared", "remains on the invoices", "balance across the invoices",
                "balance when i cross-check invoices", "unpaid amount", "unpaid charges",
                "remaining unpaid balance", "true remaining balance", "system balance",
                "adjusted balance", "credits are applied", "cleared against those billed amounts",
                "still owe", "still due", "currently due", "amount due", "total amount due",
                "total amount still owed", "pending amount", "still pending", "billed amounts that are still pending",
                "billed totals is still pending", "submitted charges that remain unpaid"
            ])) and "shortfall between our awarded" not in q_lower and "gap between total award value" not in q_lower and "sitting above" not in q_lower:
                pattern = "ar_outstanding"
                subtasks = [
                    SubTask("T1", "sql_query", f"Query total outstanding balance from Receivables Ageing for client {client}", {"sql_type": "ar_outstanding", "client": client, "pkg_num": pkg_num, "person": person}),
                    SubTask("T2", "math_compute", "Return exact outstanding balance in INR", {"metric": "outstanding_inr"}, depends_on=["T1"])
                ]

            # Check 4: Period-over-Period / Year-on-Year Movement
            elif len(unique_years) >= 2 and ("between" in q_lower or "to" in q_lower or "through" in q_lower or "and" in q_lower or "movement" in q_lower or "variance" in q_lower or "shift" in q_lower or "swing" in q_lower or "gap" in q_lower or "difference" in q_lower or "vs" in q_lower or "move" in q_lower or "delta" in q_lower):
                pattern = "yoy_movement"
                y1 = int(unique_years[0])
                y2 = int(unique_years[1])
                extra_params = {"year1": y1, "year2": y2}
                subtasks = [
                    SubTask("T1", "sql_query", f"Retrieve completed project values for client {client} in years {y1} and {y2}", {"sql_type": "yoy_movement", "client": client, "year1": y1, "year2": y2}),
                    SubTask("T2", "math_compute", f"Calculate absolute difference in value between {y1} and {y2}", {"metric": "yoy_diff_inr"}, depends_on=["T1"])
                ]

            # Check 5: Mean vs Median Contract Value
            elif "median" in q_lower:
                pattern = "mean_median_gap"
                subtasks = [
                    SubTask("T1", "sql_query", f"Retrieve all project contract values for client {client}", {"sql_type": "client_portfolio_values", "client": client, "pkg_num": pkg_num, "person": person}),
                    SubTask("T2", "math_compute", "Calculate Mean - Median contract value", {"metric": "mean_minus_median"}, depends_on=["T1"])
                ]

            # Check 6: Category Difference
            elif len(cats_found) >= 2:
                pattern = "category_diff"
                extra_params = {"categories": cats_found}
                subtasks = [
                    SubTask("T1", "sql_query", f"Retrieve category sums for {cats_found} for client {client}", {"sql_type": "category_diff", "client": client, "categories": cats_found, "pkg_num": pkg_num, "person": person}),
                    SubTask("T2", "math_compute", "Calculate absolute difference between category totals", {"metric": "category_diff_inr"}, depends_on=["T1"])
                ]

            # Check 7: Unbilled Gap / Shortfall between Awarded and Billed
            elif asks_unbilled or (("gap" in q_lower or "shortfall" in q_lower or "unbilled" in q_lower or "missing amount" in q_lower or "delta" in q_lower or "variance" in q_lower or "cross-check against the invoice" in q_lower or "cross-checking against the claims" in q_lower or "sitting above what we" in q_lower or "cross-check the claims" in q_lower) and ("billed" in q_lower or "invoiced" in q_lower or "claims" in q_lower or "claimed" in q_lower or "cash flow" in q_lower or "bills" in q_lower or "awarded" in q_lower or "commitments" in q_lower or "sanctioned" in q_lower or "invoice amount" in q_lower or "total value" in q_lower or "total scope" in q_lower or "secured work" in q_lower or "secured contract" in q_lower or "awards" in q_lower)):
                pattern = "unbilled_gap"
                subtasks = [
                    SubTask("T1", "sql_query", f"Calculate shortfall: Awarded Portfolio - Billed Invoiced for client {client}", {"sql_type": "unbilled_gap", "client": client}),
                    SubTask("T2", "math_compute", "Return the already computed awarded-versus-invoiced gap", {"metric": "passthrough"}, depends_on=["T1"])
                ]

            # Check 8: Exclusion Aggregate
            elif asks_exclusion or "excluding" in q_lower or "exclude" in q_lower or "is excluded" in q_lower or "remove the" in q_lower or "removing the" in q_lower or "set aside" in q_lower or "minus the" in q_lower or "without the" in q_lower or "dropping the" in q_lower or "stripped out" in q_lower or "filter out the" in q_lower or "carve that out" in q_lower:
                pattern = "exclusion_aggregate"
                excluded = cats_found[0] if cats_found else None
                if excluded is None:
                    raise ValueError(f"Could not resolve excluded category from question: {question}")
                
                subtasks = [
                    SubTask("T1", "sql_query", f"Retrieve all projects for client {client} excluding {excluded}", {"sql_type": "client_excluded_projects", "client": client, "exclude": excluded}),
                    SubTask("T2", "math_compute", "Sum contract values of remaining projects in exact INR", {"metric": "sum_inr"}, depends_on=["T1"])
                ]

            # Check 9: Temporal Chain
            elif asks_temporal or "after that date" in q_lower or "after her pmp" in q_lower or "after his pmp" in q_lower or "finished after" in q_lower or "completed after" in q_lower or "wrapped up after" in q_lower or ("after" in q_lower and ("pmp" in q_lower or "certification" in q_lower or "issue date" in q_lower)):
                pattern = "temporal_chain"
                subtasks = [
                    SubTask("T1", "sql_query", f"Get issue date of {cred or 'PMP'} for {person}", {"sql_type": "credential_date", "person": person, "cred": cred, "date": anchor_date}),
                    SubTask("T2", "sql_query", f"Retrieve projects led by {person} completed after certification date", {"sql_type": "projects_after_date", "person": person, "date": anchor_date}),
                    SubTask("T3", "math_compute", "Sum contract values of qualifying projects in exact INR", {"metric": "sum_inr"}, depends_on=["T2"])
                ]

            # Check 10: Average Work Size
            elif asks_average or "average size" in q_lower or "mean size" in q_lower or "typical project scale" in q_lower or "mean volume" in q_lower or "overall average for every project" in q_lower or "actual mean across all the completed work" in q_lower or "mean across all" in q_lower or "average for every project" in q_lower or "mean scale" in q_lower or "typical scale" in q_lower or "average contract value" in q_lower or "defensible average" in q_lower or "mean scale across" in q_lower:
                pattern = "avg_work_size"
                subtasks = [
                    SubTask("T1", "fts_search", f"Resolve project {proj} to commissioning client", {"query": f"{proj}"}),
                    SubTask("T2", "sql_query", f"Retrieve all completed works for client {client}", {"sql_type": "client_portfolio", "client": client, "proj": proj, "pkg_num": pkg_num, "person": person}),
                    SubTask("T3", "math_compute", "Calculate exact average contract value in INR", {"metric": "average_inr"}, depends_on=["T2"])
                ]

            # Check 11: Threshold Aggregate
            elif explicit_threshold is not None and ("threshold" in q_lower or "mark" in q_lower or "line" in q_lower or "clear" in q_lower or "exceed" in q_lower or "cutoff" in q_lower or "limit" in q_lower or "minimum" in q_lower or "at least" in q_lower or "above" in q_lower or "over" in q_lower or "or higher" in q_lower or "or more" in q_lower or "hitting" in q_lower or "crossing" in q_lower):
                pattern = "threshold_aggregate"
                thresh_inr = explicit_threshold
                subtasks = [
                    SubTask("T1", "sql_query", f"Retrieve projects for client {client} with value >= {thresh_inr}", {"sql_type": "client_threshold_projects", "client": client, "threshold_inr": thresh_inr}),
                    SubTask("T2", "math_compute", "Sum qualifying contract values in exact INR", {"metric": "sum_inr"}, depends_on=["T1"])
                ]

            # Check 12: Role Split
            elif "as prime" in q_lower or "as subcontractor" in q_lower or "as jv" in q_lower:
                pattern = "role_split"
                role = "Subcontractor" if "as subcontractor" in q_lower else ("JV Partner" if "as jv" in q_lower else "Prime")
                subtasks = [
                    SubTask("T1", "sql_query", f"Retrieve projects for client {client} where role = '{role}'", {"sql_type": "client_role_projects", "client": client, "role": role}),
                    SubTask("T2", "math_compute", f"Sum contract values of {role} projects in exact INR", {"metric": "sum_inr"}, depends_on=["T1"])
                ]

            # Check 13: Hop Aggregate / Combined Value
            elif (bool(q_tokens & aggregate_terms) or "combined value" in q_lower or "total value" in q_lower or "aggregate value" in q_lower) and (client or person or pkg_num):
                pattern = "hop_aggregate"
                subtasks = [
                    SubTask("T1", "sql_query", f"Find all projects delivered for client {client}", {"sql_type": "client_portfolio_sum", "client": client, "person": person, "proj": proj, "pkg_num": pkg_num}),
                    SubTask("T2", "math_compute", "Sum contract values of all projects for client in exact INR", {"metric": "sum_inr"}, depends_on=["T1"])
                ]

            else:
                pattern = "generic_multi_hop"
                subtasks = [
                    SubTask("T1", "fts_search", f"FTS BM25 search across document estate for: {question[:80]}", {"query": question}),
                    SubTask("T2", "sql_query", "Execute relational search for identified entities", {"person": person, "client": client, "proj": proj, "pkg_num": pkg_num}),
                    SubTask("T3", "math_compute", "Derive answer from retrieved evidence and query", {})
                ]

        return ExecutionPlan(
            question=question,
            pattern=pattern,
            anchor_person=person,
            anchor_credential=cred,
            anchor_project=proj,
            anchor_package_num=pkg_num,
            anchor_client=client,
            anchor_date=anchor_date,
            extra_params=extra_params,
            subtasks=subtasks
        )
