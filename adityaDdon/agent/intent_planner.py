"""
intent_planner.py — Intent Planner & Query Decomposition Node
Decomposes natural language questions into a directed acyclic graph (DAG) of retrieval & reasoning subtasks.
"""

import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

sys.path.append(str(Path(__file__).resolve().parent.parent / "db"))
from database import get_db, DEFAULT_DB_PATH

@dataclass
class SubTask:
    task_id: str
    action: str            # 'fts_search', 'sql_query', 'graph_hop', 'math_compute'
    description: str
    query_params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)

@dataclass
class ExecutionPlan:
    question: str
    pattern: str           # P1..P21 e.g. 'absence', 'date_span', 'hop_aggregate', etc.
    anchor_person: Optional[str] = None
    anchor_credential: Optional[str] = None
    anchor_project: Optional[str] = None
    anchor_package_num: Optional[int] = None
    anchor_client: Optional[str] = None
    anchor_date: Optional[str] = None
    target_metric: Optional[str] = None
    subtasks: List[SubTask] = field(default_factory=list)

class IntentPlanner:
    def __init__(self):
        self.db = get_db(DEFAULT_DB_PATH)
        
        # Load known engineers and clients from database
        self.known_engineers = [
            "Asha Nair", "Chandan Banerjee", "Neha Chopra", "Rahul Menon",
            "Gautam Joshi", "Naveen Roy", "Suresh Desai", "Meera Roy",
            "Amit Iyer", "Meera Banerjee", "Kavita Reddy", "Jaya Desai",
            "Divya Singh", "Amit Mukherjee", "Meera Chatterjee", "Farhan Roy",
            "Rajesh Rao", "Imran Joshi", "Sanjay Joshi", "Lakshmi Ghosh"
        ]
        
        # Fetch canonical clients from DB sorted by length descending
        try:
            client_rows = self.db.fetchall("SELECT canonical_client FROM clients ORDER BY LENGTH(canonical_client) DESC")
            self.known_clients = [r[0] for r in client_rows]
        except Exception:
            self.known_clients = [
                "Public Works Department, Govt of Maharashtra",
                "Public Works Department, Govt of Gujarat",
                "Irrigation & Waterways Dept, Govt of Uttar Pradesh",
                "Irrigation & Waterways Dept, Govt of West Bengal",
                "Public Health Engineering Dept, Gujarat",
                "Public Health Engineering Dept, Odisha",
                "National Expressway Development Authority",
                "National Special Projects Office",
                "Jharkhand Municipal Corporation",
                "Maharashtra Municipal Corporation",
                "Lakshya Engineering & Construction",
                "Trishakti Power Generation Corporation",
                "Peninsular Petroleum Corporation",
                "Suvarna Projects Limited",
                "Mega Infrastructure Authority",
                "Mahanadi Steel Corporation",
                "Jal Nigam, Jharkhand",
                "Jal Nigam, Gujarat",
                "Jal Nigam, Uttar Pradesh",
                "Kalinga National Bank",
                "Union Trust Bank of India"
            ]

    def plan(self, question: str) -> ExecutionPlan:
        q_lower = question.lower()
        
        # 1. Detect Anchor Engineer
        person = None
        for eng in self.known_engineers:
            if eng.lower() in q_lower:
                person = eng
                break

        # 2. Detect Anchor Credential (PMP, Six Sigma, PMI-xxxxx)
        cred = None
        m_pmi = re.search(r'\b(PMI-\d+|SSBB-\d+|6S-\d+)\b', question, re.I)
        if m_pmi:
            cred = m_pmi.group(1).upper()
        elif "pmp" in q_lower:
            cred = "PMP"
        elif "six sigma" in q_lower or "black belt" in q_lower:
            cred = "Six Sigma Black Belt"

        # 3. Detect Anchor Package / Project
        proj = None
        pkg_num = None
        m_pkg = re.search(r'([A-Za-z\s]+?—\s*[A-Za-z\s]+?Pkg-\d+|[A-Za-z\s]+?Package\s*\d+|Pkg-\d+)', question, re.I)
        if m_pkg:
            proj = m_pkg.group(1).strip()
            m_pnum = re.search(r'Pkg-(\d+)|Package\s*(\d+)', proj, re.I)
            if m_pnum:
                pkg_num = int(m_pnum.group(1) or m_pnum.group(2))
        else:
            m_pkg_short = re.search(r'\bPkg-(\d+)\b', question, re.I)
            if m_pkg_short:
                proj = m_pkg_short.group(0).strip()
                pkg_num = int(m_pkg_short.group(1))

        # 4. Detect Explicit Anchor Client
        client = None
        for cli in self.known_clients:
            if cli.lower() in q_lower:
                client = cli
                break
        
        # Fallback partial client matching
        if not client:
            if "jal nigam, jharkhand" in q_lower or ("jal nigam" in q_lower and "jharkhand" in q_lower):
                client = "Jal Nigam, Jharkhand"
            elif "public health engineering" in q_lower and "gujarat" in q_lower:
                client = "Public Health Engineering Dept, Gujarat"
            elif "irrigation" in q_lower and "west bengal" in q_lower:
                client = "Irrigation & Waterways Dept, Govt of West Bengal"
            elif "irrigation" in q_lower and "uttar pradesh" in q_lower:
                client = "Irrigation & Waterways Dept, Govt of Uttar Pradesh"
            elif "jharkhand municipal" in q_lower:
                client = "Jharkhand Municipal Corporation"
            elif "maharashtra municipal" in q_lower:
                client = "Maharashtra Municipal Corporation"
            elif "lakshya" in q_lower:
                client = "Lakshya Engineering & Construction"
            elif "national expressway" in q_lower:
                client = "National Expressway Development Authority"
            elif "pwd" in q_lower and "maharashtra" in q_lower:
                client = "Public Works Department, Govt of Maharashtra"
            elif "pwd" in q_lower and "gujarat" in q_lower:
                client = "Public Works Department, Govt of Gujarat"

        # If client not in prompt, resolve from anchor project package
        if not client and pkg_num:
            try:
                r_c = self.db.fetchall("SELECT canonical_client FROM projects WHERE package_number = ?", [pkg_num])
                if r_c:
                    client = r_c[0][0]
            except Exception:
                pass

        # 5. Extract Anchor Date (if explicitly in question)
        anchor_date = None
        m_date = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', question)
        if m_date:
            anchor_date = m_date.group(1)
        else:
            m_text_date = re.search(r'\b(March\s+\d+,\s+\d{4}|\d+\s+March\s+\d{4})\b', question, re.I)
            if m_text_date:
                from dateutil import parser as dt_p
                try: anchor_date = dt_p.parse(m_text_date.group(1)).strftime('%Y-%m-%d')
                except: pass

        # 6. Classify Reasoning Pattern (P1 to P21)
        pattern = "unknown"
        subtasks = []

        if "no client reference" in q_lower or "lack a client reference" in q_lower or "no reference letter" in q_lower or "unreferenced" in q_lower:
            pattern = "absence"
            subtasks = [
                SubTask("T1", "fts_search", f"Search reference letters and client completion certificates for {client}", {"query": f"{client} reference letter"}),
                SubTask("T2", "sql_query", f"Retrieve all completed works for {client} and check reference letter status", {"sql_type": "absence", "client": client}, depends_on=["T1"]),
                SubTask("T3", "math_compute", "Count works with has_reference_letter = False", {"metric": "count_missing"}, depends_on=["T2"])
            ]

        elif "days passed" in q_lower or "exact interval" in q_lower or "number of days" in q_lower or "days between" in q_lower:
            pattern = "date_span"
            subtasks = [
                SubTask("T1", "sql_query", f"Get issue date of credential {cred or 'PMP'} for {person}", {"sql_type": "credential_date", "person": person, "cred": cred, "date": anchor_date}),
                SubTask("T2", "sql_query", f"Get completion date for project {proj or pkg_num}", {"sql_type": "project_date", "project": proj, "pkg_num": pkg_num}),
                SubTask("T3", "math_compute", "Calculate difference in days between project completion and credential issue date", {"metric": "date_diff_days"}, depends_on=["T1", "T2"])
            ]

        elif "categories of work" in q_lower or "distinct work classifications" in q_lower:
            pattern = "distinct_count"
            subtasks = [
                SubTask("T1", "sql_query", f"Get all projects led by {person}", {"sql_type": "engineer_projects", "person": person}),
                SubTask("T2", "math_compute", "Count distinct work categories led by engineer", {"metric": "count_distinct_categories"}, depends_on=["T1"])
            ]

        elif "average size" in q_lower or "mean size" in q_lower:
            pattern = "avg_work_size"
            subtasks = [
                SubTask("T1", "fts_search", f"Resolve project {proj} to commissioning client", {"query": f"{proj}"}),
                SubTask("T2", "sql_query", f"Retrieve all completed works for client {client}", {"sql_type": "client_portfolio", "client": client, "proj": proj, "pkg_num": pkg_num}),
                SubTask("T3", "math_compute", "Calculate exact average contract value in INR", {"metric": "average_inr"}, depends_on=["T2"])
            ]

        elif "wrapped up after that date" in q_lower or "completed after her pmp" in q_lower or "completed after his pmp" in q_lower or "after her pmp" in q_lower or "after his pmp" in q_lower or "after that date" in q_lower:
            pattern = "temporal_chain"
            subtasks = [
                SubTask("T1", "sql_query", f"Get issue date of {cred or 'PMP'} for {person}", {"sql_type": "credential_date", "person": person, "cred": cred, "date": anchor_date}),
                SubTask("T2", "sql_query", f"Retrieve projects led by {person} completed after certification date", {"sql_type": "projects_after_date", "person": person, "date": anchor_date}),
                SubTask("T3", "math_compute", "Sum contract values of qualifying projects in exact INR", {"metric": "sum_inr"}, depends_on=["T2"])
            ]

        elif "graded" in q_lower or "marked satisfactory" in q_lower or "marked excellent" in q_lower or "excellent on their" in q_lower or "satisfactory on their" in q_lower or "very good on their" in q_lower:
            pattern = "doc_filtered_aggregate"
            target_grade = "Satisfactory"
            if "excellent" in q_lower: target_grade = "Excellent"
            elif "very good" in q_lower: target_grade = "Very Good"
            elif "good" in q_lower: target_grade = "Good"
            elif "outstanding" in q_lower: target_grade = "Outstanding"
            
            subtasks = [
                SubTask("T1", "sql_query", f"Retrieve all projects for client {client} filtered by grading {target_grade}", {"sql_type": "client_graded_projects", "client": client, "grade": target_grade}),
                SubTask("T2", "math_compute", f"Sum contract values for {target_grade} graded projects in exact INR", {"metric": "sum_inr"}, depends_on=["T1"])
            ]

        elif "excluding" in q_lower or "except" in q_lower:
            pattern = "exclusion_aggregate"
            m_ex = re.search(r'excluding\s+([A-Za-z\s]+?)(?:,|$|\?|what)', question, re.I)
            excluded = m_ex.group(1).strip() if m_ex else ""
            subtasks = [
                SubTask("T1", "sql_query", f"Retrieve all projects for client {client} excluding {excluded}", {"sql_type": "client_excluded_projects", "client": client, "exclude": excluded}),
                SubTask("T2", "math_compute", "Sum contract values of remaining projects in exact INR", {"metric": "sum_inr"}, depends_on=["T1"])
            ]

        elif "reach our credential target" in q_lower or "gap to" in q_lower or "additional work must we secure" in q_lower:
            pattern = "gap_to_threshold"
            m_thresh = re.search(r'(?:INR|Rs\.?)?\s*([\d.]+)\s*Cr', question, re.I)
            thresh_cr = float(m_thresh.group(1)) if m_thresh else 20.0
            thresh_inr = int(round(thresh_cr * 10_000_000))
            subtasks = [
                SubTask("T1", "sql_query", f"Retrieve total delivered contract value for client {client}", {"sql_type": "client_portfolio_sum", "client": client}),
                SubTask("T2", "math_compute", f"Calculate gap: {thresh_inr} - portfolio_sum", {"metric": "gap_inr", "target_inr": thresh_inr}, depends_on=["T1"])
            ]

        elif "exceed the second largest" in q_lower or "difference between the largest" in q_lower or "second largest" in q_lower:
            pattern = "rank_value"
            subtasks = [
                SubTask("T1", "sql_query", f"Retrieve and rank projects for client {client} by contract value DESC", {"sql_type": "client_ranked_projects", "client": client}),
                SubTask("T2", "math_compute", "Calculate difference: Value(Rank 1) - Value(Rank 2)", {"metric": "rank_diff_inr"}, depends_on=["T1"])
            ]

        elif "share of completed assignments that carry formal verification" in q_lower or "count of assignments for that client that carry a reference letter divided by the total" in q_lower or ("share" in q_lower and "reference" in q_lower):
            pattern = "referenced_share"
            subtasks = [
                SubTask("T1", "sql_query", f"Retrieve count of total works and referenced works for {client}", {"sql_type": "referenced_share", "client": client}),
                SubTask("T2", "math_compute", "Calculate percentage: (referenced_count / total_count) * 100", {"metric": "percentage"}, depends_on=["T1"])
            ]

        elif "as prime" in q_lower or "as subcontractor" in q_lower or "as jv" in q_lower:
            pattern = "role_split"
            subtasks = [
                SubTask("T1", "sql_query", f"Retrieve projects for client {client} where role = 'Prime'", {"sql_type": "client_role_projects", "client": client, "role": "Prime"}),
                SubTask("T2", "math_compute", "Sum contract values of Prime projects in exact INR", {"metric": "sum_inr"}, depends_on=["T1"])
            ]

        elif "crossing the" in q_lower or "hitting the" in q_lower or "above" in q_lower or "mark" in q_lower or "line" in q_lower:
            pattern = "threshold_aggregate"
            thresh_inr = 60_000_000
            if "seventy-three" in q_lower or "73" in q_lower:
                thresh_inr = 730_000_000
            elif "six crore" in q_lower or "6 crore" in q_lower:
                thresh_inr = 60_000_000
            subtasks = [
                SubTask("T1", "sql_query", f"Retrieve projects for client {client} with value >= {thresh_inr}", {"sql_type": "client_threshold_projects", "client": client, "threshold_inr": thresh_inr}),
                SubTask("T2", "math_compute", "Sum qualifying contract values in exact INR", {"metric": "sum_inr"}, depends_on=["T1"])
            ]

        elif ("combined value" in q_lower or "total value" in q_lower) and (client or person):
            pattern = "hop_aggregate"
            subtasks = [
                SubTask("T1", "sql_query", f"Find all projects delivered for client {client}", {"sql_type": "client_portfolio_sum", "client": client, "person": person, "proj": proj}),
                SubTask("T2", "math_compute", "Sum contract values of all projects for client in exact INR", {"metric": "sum_inr"}, depends_on=["T1"])
            ]

        else:
            pattern = "generic_multi_hop"
            subtasks = [
                SubTask("T1", "fts_search", f"FTS BM25 search across document estate for: {question[:80]}", {"query": question}),
                SubTask("T2", "sql_query", "Execute relational search for identified entities", {"person": person, "client": client, "proj": proj}),
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
            subtasks=subtasks
        )
