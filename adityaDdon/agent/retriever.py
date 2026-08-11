"""
retriever.py — Subtask Retriever Node
Executes DAG subtasks against DuckDB via Full-Text Search (BM25) and Relational SQL across all 21 reasoning patterns.
"""

import re
import sys
import statistics
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from dateutil import parser as dt_p

sys.path.append(str(Path(__file__).resolve().parent.parent / "db"))
from database import get_db, DEFAULT_DB_PATH
from intent_planner import ExecutionPlan, SubTask

@dataclass
class SubTaskResult:
    task_id: str
    action: str
    description: str
    fts_snippets: List[Dict[str, Any]] = field(default_factory=list)
    sql_rows: List[Dict[str, Any]] = field(default_factory=list)
    computed_value: Optional[Any] = None
    summary: str = ""
    error: Optional[str] = None

@dataclass
class RetrievalContext:
    plan: ExecutionPlan
    task_results: List[SubTaskResult] = field(default_factory=list)
    evidence_text: str = ""
    candidate_answer: Optional[Any] = None
    confidence: float = 0.0
    is_complete: bool = False
    warnings: List[str] = field(default_factory=list)

class SubtaskRetriever:
    def __init__(self, db_path: Optional[Path] = None):
        self.db = get_db(db_path or DEFAULT_DB_PATH)

    def _resolve_client(self, client: Optional[str], pkg_num: Optional[int], person: Optional[str]) -> str:
        if client:
            cleaned = client.strip(' ,.')
            rows = self.db.fetchall(
                "SELECT canonical_client FROM clients WHERE lower(canonical_client) = lower(?)",
                [cleaned],
            )
            if len(rows) == 1:
                return rows[0][0]
            raise ValueError(f"Unknown or non-canonical client anchor: {client!r}")
        if pkg_num:
            try:
                r_c = self.db.fetchall("SELECT canonical_client FROM projects WHERE package_number = ?", [pkg_num])
                if r_c and r_c[0][0]:
                    return r_c[0][0].strip(' ,.')
            except Exception:
                pass
        if person:
            r_c = self.db.fetchall(
                "SELECT DISTINCT canonical_client FROM projects WHERE lower(project_lead) = lower(?)",
                [person],
            )
            if len(r_c) == 1 and r_c[0][0]:
                return r_c[0][0].strip(' ,.')
        raise ValueError(
            "Client resolution failed; refusing to execute a client-scoped query "
            "because an empty client would match the entire database."
        )

    def execute_plan(self, plan: ExecutionPlan) -> RetrievalContext:
        results = []
        result_by_id = {}
        warnings = []

        for task in plan.subtasks:
            res = SubTaskResult(task_id=task.task_id, action=task.action, description=task.description)
            missing_dependencies = [dep for dep in task.depends_on if dep not in result_by_id]
            if missing_dependencies:
                raise ValueError(f"Task {task.task_id} has unresolved dependencies: {missing_dependencies}")

            # 1. Full-Text Search (BM25)
            if task.action == "fts_search":
                q_text = task.query_params.get("query", plan.question)
                doc_type = task.query_params.get("doc_type")
                fts_hits = self.db.search_fts(q_text, limit=5, doc_type=doc_type)
                res.fts_snippets = fts_hits
                res.summary = f"FTS retrieved {len(fts_hits)} matching documents."

            # 2. Relational SQL Queries
            elif task.action == "sql_query":
                sql_type = task.query_params.get("sql_type", "")
                rows = []

                if sql_type == "ar_outstanding":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    sql = """
                        SELECT SUM(outstanding_inr), SUM(invoiced_inr), SUM(received_inr), COUNT(*)
                        FROM workbooks_receivables
                        WHERE canonical_client = ?
                    """
                    df = self.db.fetchall(sql, [client])
                    out_inr = df[0][0] if df and df[0][0] is not None else 0
                    res.computed_value = out_inr
                    res.sql_rows = [{"client": client, "outstanding_inr": out_inr}]
                    res.summary = f"Client '{client}' outstanding balance from receivables: {out_inr} INR."

                elif sql_type == "collection_rate":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    sql = """
                        SELECT SUM(received_inr), SUM(invoiced_inr), SUM(outstanding_inr), COUNT(*)
                        FROM workbooks_receivables
                        WHERE canonical_client = ?
                    """
                    df = self.db.fetchall(sql, [client])
                    rcv, inv, out, cnt = df[0] if df and df[0][1] else (0, 0, 0, 0)
                    pct = round((rcv / inv) * 100, 2) if inv and inv > 0 else 0.0
                    res.computed_value = pct
                    res.sql_rows = [{"client": client, "received_inr": rcv, "invoiced_inr": inv, "collection_pct": pct}]
                    res.summary = f"Client '{client}' received {rcv} / {inv} billed -> {pct}% collected."

                elif sql_type == "unbilled_gap":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    # Awarded total from projects
                    sql_awarded = "SELECT SUM(contract_value_inr) FROM projects WHERE canonical_client = ?"
                    df_awarded = self.db.fetchall(sql_awarded, [client])
                    awarded = df_awarded[0][0] or 0

                    # Invoiced total from workbooks_receivables
                    sql_inv = "SELECT SUM(invoiced_inr) FROM workbooks_receivables WHERE canonical_client = ?"
                    df_inv = self.db.fetchall(sql_inv, [client])
                    invoiced = df_inv[0][0] or 0

                    gap = abs(awarded - invoiced)
                    res.computed_value = gap
                    res.sql_rows = [{"client": client, "awarded_inr": awarded, "invoiced_inr": invoiced, "unbilled_gap": gap}]
                    res.summary = f"Client '{client}' Awarded: {awarded} vs Invoiced: {invoiced} = Gap: {gap} INR."

                elif sql_type == "client_portfolio_values":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    sql = "SELECT contract_value_inr FROM projects WHERE canonical_client = ?"
                    df = self.db.fetchall(sql, [client])
                    vals = [r[0] for r in df if r[0] is not None]
                    if vals:
                        mean_val = sum(vals) / len(vals)
                        med_val = statistics.median(vals)
                        diff = int(round(mean_val - med_val))
                        res.computed_value = diff
                        res.sql_rows = [{"client": client, "count": len(vals), "mean": mean_val, "median": med_val, "mean_minus_median": diff}]
                        res.summary = f"Client '{client}' ({len(vals)} works): Mean ({mean_val:.1f}) - Median ({med_val:.1f}) = {diff} INR."

                elif sql_type == "category_diff":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    cats = task.query_params.get("categories", [])
                    if len(cats) >= 2:
                        cat1, cat2 = cats[0], cats[1]
                        if client:
                            df1 = self.db.fetchall("SELECT SUM(contract_value_inr) FROM projects WHERE canonical_client = ? AND lower(category) = lower(?)", [client, cat1])
                            df2 = self.db.fetchall("SELECT SUM(contract_value_inr) FROM projects WHERE canonical_client = ? AND lower(category) = lower(?)", [client, cat2])
                        else:
                            df1 = self.db.fetchall("SELECT SUM(contract_value_inr) FROM projects WHERE category ILIKE ?", [f"%{cat1}%"])
                            df2 = self.db.fetchall("SELECT SUM(contract_value_inr) FROM projects WHERE category ILIKE ?", [f"%{cat2}%"])
                        
                        v1 = df1[0][0] or 0
                        v2 = df2[0][0] or 0
                        diff = abs(v1 - v2)
                        res.computed_value = diff
                        res.sql_rows = [{"client": client, "category_1": cat1, "value_1": v1, "category_2": cat2, "value_2": v2, "difference": diff}]
                        res.summary = f"Client '{client}': {cat1} ({v1}) vs {cat2} ({v2}) diff = {diff} INR."

                elif sql_type == "category_aggregate":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person,
                    )
                    categories = task.query_params.get("categories", [])
                    placeholders = ", ".join("?" for _ in categories)
                    if not placeholders:
                        raise ValueError("Category aggregate requires at least one category")
                    df = self.db.fetchall(
                        f"""
                        SELECT project_id, title, category, contract_value_inr
                        FROM projects
                        WHERE canonical_client = ? AND category IN ({placeholders})
                        """,
                        [client, *categories],
                    )
                    rows = [
                        {"project_id": r[0], "title": r[1], "category": r[2], "val_inr": r[3]}
                        for r in df
                    ]
                    res.sql_rows = rows
                    res.computed_value = sum(r["val_inr"] for r in rows)
                    res.summary = f"Client '{client}' requested category subset totals {res.computed_value} INR."

                elif sql_type == "yoy_movement":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    y1 = task.query_params.get("year1", 2020)
                    y2 = task.query_params.get("year2", 2022)

                    if client:
                        sql_y1 = "SELECT SUM(contract_value_inr) FROM projects WHERE canonical_client = ? AND completion_year = ?"
                        df_y1 = self.db.fetchall(sql_y1, [client, y1])
                        sql_y2 = "SELECT SUM(contract_value_inr) FROM projects WHERE canonical_client = ? AND completion_year = ?"
                        df_y2 = self.db.fetchall(sql_y2, [client, y2])
                    else:
                        sql_y1 = "SELECT SUM(contract_value_inr) FROM projects WHERE completion_year = ?"
                        df_y1 = self.db.fetchall(sql_y1, [y1])
                        sql_y2 = "SELECT SUM(contract_value_inr) FROM projects WHERE completion_year = ?"
                        df_y2 = self.db.fetchall(sql_y2, [y2])

                    val1 = df_y1[0][0] or 0
                    val2 = df_y2[0][0] or 0

                    diff = abs(val2 - val1)
                    res.computed_value = diff
                    res.sql_rows = [{"client": client, f"val_{y1}": val1, f"val_{y2}": val2, "movement_inr": diff}]
                    res.summary = f"Client '{client}' {y1} ({val1}) to {y2} ({val2}) movement = {diff} INR."

                elif sql_type == "absence":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    sql = """
                        SELECT project_id, title, canonical_client, contract_value_inr, 
                               has_reference_letter, ref_doc_id
                        FROM projects
                        WHERE canonical_client = ?
                        ORDER BY work_no
                    """
                    df = self.db.fetchall(sql, [client])
                    rows = [{"project_id": r[0], "title": r[1], "client": r[2], "val_inr": r[3], "has_ref": r[4], "ref_doc": r[5]} for r in df]
                    res.sql_rows = rows
                    unref_count = sum(1 for r in rows if not r["has_ref"])
                    res.computed_value = unref_count
                    res.summary = f"Client '{client}' has {len(rows)} works total; {unref_count} unreferenced works."

                elif sql_type == "credential_date":
                    explicit_date = task.query_params.get("date") or plan.anchor_date
                    if explicit_date:
                        res.computed_value = explicit_date
                        res.summary = f"Anchor date specified: {explicit_date}."
                    else:
                        person = task.query_params.get("person") or plan.anchor_person
                        cred = task.query_params.get("cred") or plan.anchor_credential or "PMP"
                        if not person:
                            raise ValueError("Credential-date query has no resolved engineer")
                        if re.fullmatch(r"(?:PMI|SSBB|6S)-\d+", str(cred), re.I):
                            df = self.db.fetchall(
                                """
                                SELECT credential_id, engineer_name, credential_type, issue_date, valid_through, doc_id
                                FROM credentials WHERE upper(credential_id) = upper(?)
                                """,
                                [cred],
                            )
                        else:
                            df = self.db.fetchall(
                                """
                                SELECT credential_id, engineer_name, credential_type, issue_date, valid_through, doc_id
                                FROM credentials
                                WHERE lower(engineer_name) = lower(?) AND lower(credential_type) = lower(?)
                                ORDER BY issue_date DESC
                                """,
                                [person, cred],
                            )
                        
                        rows = [{"cred_id": r[0], "engineer": r[1], "type": r[2], "issue_date": r[3], "valid_through": r[4], "doc": r[5]} for r in df]
                        res.sql_rows = rows
                        if rows:
                            res.computed_value = rows[0]["issue_date"]
                            res.summary = f"Credential {rows[0]['cred_id']} for {rows[0]['engineer']} issued on {rows[0]['issue_date']}."
                        else:
                            res.summary = f"No exact credential record found for {person!r} / {cred!r}."

                elif sql_type == "project_date":
                    proj = task.query_params.get("project") or plan.anchor_project
                    pkg_num = task.query_params.get("pkg_num") or plan.anchor_package_num
                    person = task.query_params.get("person") or plan.anchor_person
                    
                    if not pkg_num and proj:
                        m_pkg = re.search(r'Pkg-(\d+)|pkg\s*(\d+)|Package\s*(\d+)', proj, re.I)
                        if m_pkg: pkg_num = int(m_pkg.group(1) or m_pkg.group(2) or m_pkg.group(3))

                    if pkg_num:
                        sql = "SELECT project_id, title, completion_date, contract_value_inr, project_lead, canonical_client FROM projects WHERE package_number = ?"
                        df = self.db.fetchall(sql, [pkg_num])
                    elif proj:
                        sql = "SELECT project_id, title, completion_date, contract_value_inr, project_lead, canonical_client FROM projects WHERE lower(title) = lower(?)"
                        df = self.db.fetchall(sql, [proj])
                    elif person:
                        sql = "SELECT project_id, title, completion_date, contract_value_inr, project_lead, canonical_client FROM projects WHERE lower(project_lead) = lower(?) ORDER BY completion_date DESC"
                        df = self.db.fetchall(sql, [person])
                    else:
                        df = []
                        
                    rows = [{"project_id": r[0], "title": r[1], "comp_date": r[2], "val_inr": r[3], "lead": r[4], "client": r[5]} for r in df]
                    res.sql_rows = rows
                    if rows:
                        res.computed_value = rows[0]["comp_date"]
                        res.summary = f"Project '{rows[0]['title']}' completed on {rows[0]['comp_date']}."

                elif sql_type == "engineer_projects":
                    person = task.query_params.get("person") or plan.anchor_person
                    sql = """
                        SELECT project_id, title, category, contract_value_inr, completion_date, canonical_client
                        FROM projects
                        WHERE lower(project_lead) = lower(?)
                        ORDER BY completion_date
                    """
                    if not person:
                        raise ValueError("Distinct-category query has no resolved engineer")
                    df = self.db.fetchall(sql, [person])
                    rows = [{"project_id": r[0], "title": r[1], "category": r[2], "val_inr": r[3], "comp_date": r[4], "client": r[5]} for r in df]
                    res.sql_rows = rows
                    cats = set(r["category"] for r in rows)
                    res.computed_value = len(cats)
                    res.summary = f"Engineer '{person}' led {len(rows)} projects across {len(cats)} distinct categories: {cats}."

                elif sql_type == "client_portfolio" or sql_type == "client_portfolio_sum":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    sql = """
                        SELECT project_id, title, contract_value_inr, completion_date, performance_grading, category, role
                        FROM projects
                        WHERE canonical_client = ?
                        ORDER BY work_no
                    """
                    df = self.db.fetchall(sql, [client])
                    rows = [{"project_id": r[0], "title": r[1], "val_inr": r[2], "comp_date": r[3], "grade": r[4], "category": r[5], "role": r[6]} for r in df]
                    res.sql_rows = rows
                    total_val = sum(r["val_inr"] for r in rows)
                    avg_val = int(round(total_val / len(rows))) if rows else 0
                    res.computed_value = total_val
                    res.summary = f"Client '{client}' has {len(rows)} works, total: {total_val} INR (avg: {avg_val} INR)."

                elif sql_type == "projects_after_date":
                    person = task.query_params.get("person") or plan.anchor_person
                    explicit_date = task.query_params.get("date") or plan.anchor_date
                    dependency_date = next(
                        (
                            result_by_id[dep].computed_value
                            for dep in task.depends_on
                            if result_by_id[dep].computed_value
                        ),
                        None,
                    )
                    anchor_d = explicit_date or dependency_date
                    if not anchor_d:
                        raise ValueError("Temporal query has no resolved credential date")
                    if not person:
                        raise ValueError("Temporal query has no resolved engineer")

                    sql = """
                        SELECT project_id, title, contract_value_inr, completion_date, canonical_client
                        FROM projects
                        WHERE lower(project_lead) = lower(?) AND completion_date > ?
                        ORDER BY completion_date
                    """
                    df = self.db.fetchall(sql, [person, anchor_d])
                    rows = [{"project_id": r[0], "title": r[1], "val_inr": r[2], "comp_date": r[3], "client": r[4]} for r in df]
                    res.sql_rows = rows
                    total_val = sum(r["val_inr"] for r in rows)
                    res.computed_value = total_val
                    res.summary = f"Engineer '{person}' led {len(rows)} works completed after {anchor_d}, sum: {total_val} INR."

                elif sql_type == "client_excluded_projects":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    exclude_term = task.query_params.get("exclude", "")
                    sql = """
                        SELECT project_id, title, category, contract_value_inr
                        FROM projects
                        WHERE canonical_client = ?
                        AND NOT (lower(category) = lower(?))
                    """
                    df = self.db.fetchall(sql, [client, exclude_term])
                    rows = [{"project_id": r[0], "title": r[1], "category": r[2], "val_inr": r[3]} for r in df]
                    res.sql_rows = rows
                    total_val = sum(r["val_inr"] for r in rows)
                    res.computed_value = total_val
                    res.summary = f"Client '{client}' has {len(rows)} works excluding '{exclude_term}', sum: {total_val} INR."

                elif sql_type == "client_ranked_projects":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    sql = """
                        SELECT project_id, title, contract_value_inr
                        FROM projects
                        WHERE canonical_client = ?
                        ORDER BY contract_value_inr DESC
                    """
                    df = self.db.fetchall(sql, [client])
                    rows = [{"project_id": r[0], "title": r[1], "val_inr": r[2]} for r in df]
                    res.sql_rows = rows
                    if len(rows) >= 2:
                        diff = rows[0]["val_inr"] - rows[1]["val_inr"]
                        res.computed_value = diff
                        res.summary = f"Client '{client}' Rank 1: {rows[0]['val_inr']}, Rank 2: {rows[1]['val_inr']}, Diff: {diff} INR."

                elif sql_type == "referenced_share":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    sql = """
                        SELECT total_works, referenced_works, unreferenced_works
                        FROM clients
                        WHERE canonical_client = ?
                    """
                    df = self.db.fetchall(sql, [client])
                    if df and df[0][0]:
                        tot, ref, unref = df[0]
                        pct = round((ref / tot) * 100, 2) if tot > 0 else 0.0
                        res.computed_value = pct
                        res.sql_rows = [{"total": tot, "referenced": ref, "unreferenced": unref, "share_pct": pct}]
                        res.summary = f"Client '{client}': {ref}/{tot} works referenced -> {pct}%."
                    else:
                        # Fallback to projects table
                        df_p = self.db.fetchall("SELECT COUNT(*), SUM(CASE WHEN has_reference_letter THEN 1 ELSE 0 END) FROM projects WHERE canonical_client = ?", [client])
                        if df_p and df_p[0][0]:
                            tot, ref = df_p[0]
                            pct = round((ref / tot) * 100, 2) if tot > 0 else 0.0
                            res.computed_value = pct
                            res.summary = f"Client '{client}': {ref}/{tot} works referenced -> {pct}%."

                elif sql_type == "client_role_projects":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    role = task.query_params.get("role", "Prime")
                    sql = """
                        SELECT project_id, title, role, contract_value_inr
                        FROM projects
                        WHERE canonical_client = ? AND lower(role) = lower(?)
                    """
                    df = self.db.fetchall(sql, [client, role])
                    rows = [{"project_id": r[0], "title": r[1], "role": r[2], "val_inr": r[3]} for r in df]
                    res.sql_rows = rows
                    total_val = sum(r["val_inr"] for r in rows)
                    res.computed_value = total_val
                    res.summary = f"Client '{client}' has {len(rows)} works as '{role}', sum: {total_val} INR."

                elif sql_type == "client_threshold_projects":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    thresh = task.query_params.get("threshold_inr", 0)
                    sql = """
                        SELECT project_id, title, contract_value_inr
                        FROM projects
                        WHERE canonical_client = ? AND contract_value_inr >= ?
                    """
                    df = self.db.fetchall(sql, [client, thresh])
                    rows = [{"project_id": r[0], "title": r[1], "val_inr": r[2]} for r in df]
                    res.sql_rows = rows
                    total_val = sum(r["val_inr"] for r in rows)
                    res.computed_value = total_val
                    res.summary = f"Client '{client}' has {len(rows)} works >= {thresh} INR, sum: {total_val} INR."

                elif sql_type == "turnover_growth":
                    year1 = int(task.query_params["year1"])
                    year2 = int(task.query_params["year2"])
                    metric_name = task.query_params.get("metric", "total_revenue")
                    df = self.db.fetchall(
                        """
                        SELECT fiscal_year_start, fiscal_year, amount_inr, doc_id
                        FROM financial_metrics
                        WHERE fiscal_year_start IN (?, ?) AND metric = ?
                        ORDER BY fiscal_year_start
                        """,
                        [year1, year2, metric_name],
                    )
                    values = {int(row[0]): int(row[2]) for row in df}
                    if year1 not in values or year2 not in values:
                        raise ValueError(f"Missing audited {metric_name} for {year1}/{year2}")
                    growth = round(((values[year2] - values[year1]) / values[year1]) * 100, 2)
                    res.sql_rows = [
                        {"fiscal_year_start": row[0], "fiscal_year": row[1], "amount_inr": row[2], "doc_id": row[3]}
                        for row in df
                    ]
                    res.computed_value = growth
                    res.summary = f"{metric_name} moved from {values[year1]} to {values[year2]}: {growth}%."

                elif sql_type == "plant_asset_valuation":
                    clauses = []
                    parameters = []
                    for column, value in (
                        ("location_state", task.query_params.get("state")),
                        ("ownership", task.query_params.get("ownership")),
                        ("condition", task.query_params.get("condition")),
                    ):
                        if value:
                            clauses.append(f"lower({column}) = lower(?)")
                            parameters.append(value)
                    safety = task.query_params.get("safety_certified")
                    if safety is not None:
                        clauses.append("safety_certified = ?")
                        parameters.append(bool(safety))
                    where = " WHERE " + " AND ".join(clauses) if clauses else ""
                    df = self.db.fetchall(
                        """
                        SELECT asset_id, asset_type, cost_inr, condition,
                               location_state, ownership, safety_certified
                        FROM workbooks_assets
                        """ + where,
                        parameters,
                    )
                    rows = [
                        {"asset_id": r[0], "type": r[1], "cost_inr": r[2], "condition": r[3], "state": r[4], "ownership": r[5], "safety": r[6]}
                        for r in df
                    ]
                    res.sql_rows = rows
                    res.computed_value = sum(row["cost_inr"] for row in rows)
                    res.summary = f"{len(rows)} qualifying assets total {res.computed_value} INR."

                elif sql_type == "boq_quantity_variance":
                    contract_id = task.query_params.get("contract_id")
                    item_no = task.query_params.get("item_no")
                    if contract_id is None:
                        raise ValueError("BOQ variance requires a contract number")
                    boq_rows = self.db.fetchall(
                        """
                        SELECT item_no, description, unit, quantity
                        FROM workbooks_boq WHERE contract_id = ?
                        """,
                        [contract_id],
                    )
                    if item_no is not None:
                        matches = [row for row in boq_rows if str(row[0]).lower() == str(item_no).lower()]
                    else:
                        question_tokens = set(re.findall(r"[a-z]+", task.query_params.get("question", "").lower()))
                        scored = []
                        for row in boq_rows:
                            description_tokens = set(re.findall(r"[a-z]+", (row[1] or "").lower()))
                            scored.append((len(question_tokens & description_tokens), row))
                        scored.sort(key=lambda item: item[0], reverse=True)
                        matches = [scored[0][1]] if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]) else []
                    if len(matches) != 1:
                        raise ValueError(f"Could not uniquely resolve BOQ item for contract {contract_id}")
                    selected_item, description, unit, tender_quantity = matches[0]
                    measured = self.db.fetchall(
                        """
                        SELECT COALESCE(SUM(quantity_measured), 0)
                        FROM workbooks_boq_measurements
                        WHERE contract_id = ? AND lower(item_no) = lower(?)
                        """,
                        [contract_id, selected_item],
                    )[0][0]
                    variance = float(measured) - float(tender_quantity)
                    res.sql_rows = [{"contract_id": contract_id, "item_no": selected_item, "description": description, "unit": unit, "tender_quantity": tender_quantity, "measured_quantity": measured}]
                    res.computed_value = round(variance, 3)
                    res.summary = f"Contract {contract_id} item {selected_item}: measured {measured} - tender {tender_quantity} = {res.computed_value} {unit}."

            # 3. Math Computation
            elif task.action == "math_compute":
                metric = task.query_params.get("metric", "")
                dependency_results = [result_by_id[dep] for dep in task.depends_on]
                if metric == "date_diff_days":
                    t1_val = dependency_results[0].computed_value if len(dependency_results) > 0 else None
                    t2_val = dependency_results[1].computed_value if len(dependency_results) > 1 else None
                    if t1_val and t2_val:
                        d1 = dt_p.parse(t1_val)
                        d2 = dt_p.parse(t2_val)
                        days = abs((d2 - d1).days)
                        res.computed_value = days
                        res.summary = f"Difference between {t2_val} and {t1_val} is {days} days."
                elif metric == "average_inr":
                    source_rows = dependency_results[0].sql_rows if dependency_results else []
                    if source_rows:
                        tot = sum(r["val_inr"] for r in source_rows)
                        avg = int(round(tot / len(source_rows)))
                        res.computed_value = avg
                        res.summary = f"Average across {len(source_rows)} works: {avg} INR."
                elif metric == "gap_inr":
                    target = task.query_params.get("target_inr")
                    if target is None:
                        raise ValueError("Gap computation requires an explicit target")
                    t1_sum = dependency_results[0].computed_value if dependency_results else None
                    if t1_sum is None:
                        raise ValueError("Gap computation has no portfolio total")
                    mode = task.query_params.get("gap_mode", "absolute")
                    # "Amount still needed" is directional; a generic
                    # difference/gap is absolute.  Do not infer semantics from
                    # the magnitudes themselves.
                    gap = max(target - t1_sum, 0) if mode == "shortfall" else abs(target - t1_sum)
                    res.computed_value = gap
                    res.summary = f"Gap: |{target} - {t1_sum}| = {gap} INR."
                elif metric == "passthrough":
                    prev = [r.computed_value for r in dependency_results if r.computed_value is not None]
                    res.computed_value = prev[-1] if prev else None
                    res.summary = f"Using the deterministic result from the previous task: {res.computed_value}."
                else:
                    prev = [r.computed_value for r in dependency_results if r.computed_value is not None]
                    res.computed_value = prev[-1] if prev else None

            results.append(res)
            result_by_id[task.task_id] = res

        # Build evidence text
        evidence_lines = [f"Pattern: {plan.pattern} (planner confidence {plan.confidence:.3f})"]
        evidence_lines.extend(f"Planner: {diagnostic}" for diagnostic in plan.diagnostics)
        for r in results:
            evidence_lines.append(f"[{r.task_id}] {r.description} -> {r.summary}")
            if r.sql_rows:
                for row in r.sql_rows[:8]:
                    evidence_lines.append(f"   Row: {row}")
            if r.fts_snippets:
                for snip in r.fts_snippets[:3]:
                    evidence_lines.append(f"   FTS [{snip['doc_id']}]: {snip['content'][:250]}...")

        candidate = results[-1].computed_value if results and results[-1].computed_value is not None else None
        complete = candidate is not None
        confidence = plan.confidence if complete else min(plan.confidence, 0.2)
        if not complete:
            warnings.append("terminal task did not produce a deterministic candidate")
        return RetrievalContext(
            plan=plan,
            task_results=results,
            evidence_text="\n".join(evidence_lines),
            candidate_answer=candidate,
            confidence=confidence,
            is_complete=complete,
            warnings=warnings,
        )
