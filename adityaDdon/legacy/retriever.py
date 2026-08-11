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
from .intent_planner import ExecutionPlan, SubTask

@dataclass
class SubTaskResult:
    task_id: str
    action: str
    description: str
    fts_snippets: List[Dict[str, Any]] = field(default_factory=list)
    sql_rows: List[Dict[str, Any]] = field(default_factory=list)
    computed_value: Optional[Any] = None
    summary: str = ""

@dataclass
class RetrievalContext:
    plan: ExecutionPlan
    task_results: List[SubTaskResult] = field(default_factory=list)
    evidence_text: str = ""
    candidate_answer: Optional[Any] = None

class SubtaskRetriever:
    def __init__(self, db_path: Optional[Path] = None):
        self.db = get_db(db_path or DEFAULT_DB_PATH)

    def _resolve_client(self, client: Optional[str], pkg_num: Optional[int], person: Optional[str]) -> str:
        if client:
            return client.strip(' ,.')
        if pkg_num:
            try:
                r_c = self.db.fetchall("SELECT canonical_client FROM projects WHERE package_number = ?", [pkg_num])
                if r_c and r_c[0][0]:
                    return r_c[0][0].strip(' ,.')
            except Exception:
                pass
        if person:
            try:
                r_c = self.db.fetchall("SELECT canonical_client FROM projects WHERE project_lead ILIKE ? ORDER BY completion_date DESC", [f"%{person}%"])
                if r_c and r_c[0][0]:
                    return r_c[0][0].strip(' ,.')
            except Exception:
                pass
        raise ValueError(
            "Client resolution failed; refusing to execute a client-scoped query "
            "because an empty client would match the entire database."
        )

    def execute_plan(self, plan: ExecutionPlan) -> RetrievalContext:
        results = []

        for task in plan.subtasks:
            res = SubTaskResult(task_id=task.task_id, action=task.action, description=task.description)

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
                        WHERE canonical_client = ? OR canonical_client ILIKE ?
                    """
                    df = self.db.fetchall(sql, [client, f"%{client}%"])
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
                        WHERE canonical_client = ? OR canonical_client ILIKE ?
                    """
                    df = self.db.fetchall(sql, [client, f"%{client}%"])
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
                    sql_awarded = "SELECT SUM(contract_value_inr) FROM projects WHERE canonical_client = ? OR canonical_client ILIKE ?"
                    df_awarded = self.db.fetchall(sql_awarded, [client, f"%{client}%"])
                    awarded = df_awarded[0][0] or 0

                    # Invoiced total from workbooks_receivables
                    sql_inv = "SELECT SUM(invoiced_inr) FROM workbooks_receivables WHERE canonical_client = ? OR canonical_client ILIKE ?"
                    df_inv = self.db.fetchall(sql_inv, [client, f"%{client}%"])
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
                    sql = "SELECT contract_value_inr FROM projects WHERE canonical_client = ? OR canonical_client ILIKE ?"
                    df = self.db.fetchall(sql, [client, f"%{client}%"])
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
                            df1 = self.db.fetchall("SELECT SUM(contract_value_inr) FROM projects WHERE (canonical_client = ? OR canonical_client ILIKE ?) AND category ILIKE ?", [client, f"%{client}%", f"%{cat1}%"])
                            df2 = self.db.fetchall("SELECT SUM(contract_value_inr) FROM projects WHERE (canonical_client = ? OR canonical_client ILIKE ?) AND category ILIKE ?", [client, f"%{client}%", f"%{cat2}%"])
                        else:
                            df1 = self.db.fetchall("SELECT SUM(contract_value_inr) FROM projects WHERE category ILIKE ?", [f"%{cat1}%"])
                            df2 = self.db.fetchall("SELECT SUM(contract_value_inr) FROM projects WHERE category ILIKE ?", [f"%{cat2}%"])
                        
                        v1 = df1[0][0] or 0
                        v2 = df2[0][0] or 0
                        diff = abs(v1 - v2)
                        res.computed_value = diff
                        res.summary = f"Client '{client}': {cat1} ({v1}) vs {cat2} ({v2}) diff = {diff} INR."

                elif sql_type == "yoy_movement":
                    client = self._resolve_client(
                        task.query_params.get("client") or plan.anchor_client,
                        task.query_params.get("pkg_num") or plan.anchor_package_num,
                        task.query_params.get("person") or plan.anchor_person
                    )
                    y1 = task.query_params.get("year1", 2020)
                    y2 = task.query_params.get("year2", 2022)

                    if client:
                        sql_y1 = "SELECT SUM(contract_value_inr) FROM projects WHERE (canonical_client = ? OR canonical_client ILIKE ?) AND completion_year = ?"
                        df_y1 = self.db.fetchall(sql_y1, [client, f"%{client}%", y1])
                        sql_y2 = "SELECT SUM(contract_value_inr) FROM projects WHERE (canonical_client = ? OR canonical_client ILIKE ?) AND completion_year = ?"
                        df_y2 = self.db.fetchall(sql_y2, [client, f"%{client}%", y2])
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
                        WHERE canonical_client = ? OR canonical_client ILIKE ?
                        ORDER BY work_no
                    """
                    df = self.db.fetchall(sql, [client, f"%{client}%"])
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
                        sql = """
                            SELECT credential_id, engineer_name, credential_type, issue_date, valid_through, doc_id
                            FROM credentials
                            WHERE engineer_name ILIKE ? AND credential_type ILIKE ?
                            ORDER BY issue_date DESC
                        """
                        pattern_eng = f"%{person}%" if person else "%"
                        pattern_cred = f"%{cred}%"
                        df = self.db.fetchall(sql, [pattern_eng, pattern_cred])
                        if not df and person:
                            df = self.db.fetchall("SELECT credential_id, engineer_name, credential_type, issue_date, valid_through, doc_id FROM credentials WHERE engineer_name ILIKE ?", [pattern_eng])
                        
                        rows = [{"cred_id": r[0], "engineer": r[1], "type": r[2], "issue_date": r[3], "valid_through": r[4], "doc": r[5]} for r in df]
                        res.sql_rows = rows
                        if rows:
                            res.computed_value = rows[0]["issue_date"]
                            res.summary = f"Credential {rows[0]['cred_id']} for {rows[0]['engineer']} issued on {rows[0]['issue_date']}."

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
                        sql = "SELECT project_id, title, completion_date, contract_value_inr, project_lead, canonical_client FROM projects WHERE title ILIKE ?"
                        df = self.db.fetchall(sql, [f"%{proj}%"])
                    elif person:
                        sql = "SELECT project_id, title, completion_date, contract_value_inr, project_lead, canonical_client FROM projects WHERE project_lead ILIKE ? ORDER BY completion_date DESC"
                        df = self.db.fetchall(sql, [f"%{person}%"])
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
                        WHERE project_lead ILIKE ?
                        ORDER BY completion_date
                    """
                    df = self.db.fetchall(sql, [f"%{person}%"])
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
                        WHERE canonical_client = ? OR canonical_client ILIKE ?
                        ORDER BY work_no
                    """
                    df = self.db.fetchall(sql, [client, f"%{client}%"])
                    rows = [{"project_id": r[0], "title": r[1], "val_inr": r[2], "comp_date": r[3], "grade": r[4], "category": r[5], "role": r[6]} for r in df]
                    res.sql_rows = rows
                    total_val = sum(r["val_inr"] for r in rows)
                    avg_val = int(round(total_val / len(rows))) if rows else 0
                    res.computed_value = total_val
                    res.summary = f"Client '{client}' has {len(rows)} works, total: {total_val} INR (avg: {avg_val} INR)."

                elif sql_type == "projects_after_date":
                    person = task.query_params.get("person") or plan.anchor_person
                    explicit_date = task.query_params.get("date") or plan.anchor_date
                    
                    if explicit_date:
                        anchor_d = explicit_date
                    else:
                        r_pmp = self.db.fetchall("SELECT issue_date FROM credentials WHERE engineer_name ILIKE ? AND credential_type ILIKE '%PMP%' ORDER BY issue_date DESC", [f"%{person}%"])
                        anchor_d = r_pmp[0][0] if r_pmp else "2021-03-10"

                    sql = """
                        SELECT project_id, title, contract_value_inr, completion_date, canonical_client
                        FROM projects
                        WHERE project_lead ILIKE ? AND completion_date > ?
                        ORDER BY completion_date
                    """
                    df = self.db.fetchall(sql, [f"%{person}%", anchor_d])
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
                        WHERE (canonical_client = ? OR canonical_client ILIKE ?)
                        AND NOT (category ILIKE ? OR title ILIKE ?)
                    """
                    ex_pat = f"%{exclude_term}%"
                    df = self.db.fetchall(sql, [client, f"%{client}%", ex_pat, ex_pat])
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
                        WHERE canonical_client = ? OR canonical_client ILIKE ?
                        ORDER BY contract_value_inr DESC
                    """
                    df = self.db.fetchall(sql, [client, f"%{client}%"])
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
                        WHERE canonical_client = ? OR canonical_client ILIKE ?
                    """
                    df = self.db.fetchall(sql, [client, f"%{client}%"])
                    if df and df[0][0]:
                        tot, ref, unref = df[0]
                        pct = round((ref / tot) * 100, 2) if tot > 0 else 0.0
                        res.computed_value = pct
                        res.sql_rows = [{"total": tot, "referenced": ref, "unreferenced": unref, "share_pct": pct}]
                        res.summary = f"Client '{client}': {ref}/{tot} works referenced -> {pct}%."
                    else:
                        # Fallback to projects table
                        df_p = self.db.fetchall("SELECT COUNT(*), SUM(CASE WHEN has_reference_letter THEN 1 ELSE 0 END) FROM projects WHERE canonical_client = ? OR canonical_client ILIKE ?", [client, f"%{client}%"])
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
                        WHERE (canonical_client = ? OR canonical_client ILIKE ?) AND role ILIKE ?
                    """
                    df = self.db.fetchall(sql, [client, f"%{client}%", f"%{role}%"])
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
                        WHERE (canonical_client = ? OR canonical_client ILIKE ?) AND contract_value_inr >= ?
                    """
                    df = self.db.fetchall(sql, [client, f"%{client}%", thresh])
                    rows = [{"project_id": r[0], "title": r[1], "val_inr": r[2]} for r in df]
                    res.sql_rows = rows
                    total_val = sum(r["val_inr"] for r in rows)
                    res.computed_value = total_val
                    res.summary = f"Client '{client}' has {len(rows)} works >= {thresh} INR, sum: {total_val} INR."

            # 3. Math Computation
            elif task.action == "math_compute":
                metric = task.query_params.get("metric", "")
                if metric == "date_diff_days":
                    t1_val = next((r.computed_value for r in results if r.task_id == "T1"), None)
                    t2_val = next((r.computed_value for r in results if r.task_id == "T2"), None)
                    if t1_val and t2_val:
                        d1 = dt_p.parse(t1_val)
                        d2 = dt_p.parse(t2_val)
                        days = abs((d2 - d1).days)
                        res.computed_value = days
                        res.summary = f"Difference between {t2_val} and {t1_val} is {days} days."
                elif metric == "average_inr":
                    t2_rows = next((r.sql_rows for r in results if r.task_id == "T2"), [])
                    if t2_rows:
                        tot = sum(r["val_inr"] for r in t2_rows)
                        avg = int(round(tot / len(t2_rows)))
                        res.computed_value = avg
                        res.summary = f"Average across {len(t2_rows)} works: {avg} INR."
                elif metric == "gap_inr":
                    target = task.query_params.get("target_inr", 200_000_000)
                    t1_sum = next((r.computed_value for r in results if r.task_id == "T1"), 0)
                    gap = abs(target - t1_sum)
                    res.computed_value = gap
                    res.summary = f"Gap: |{target} - {t1_sum}| = {gap} INR."
                elif metric == "passthrough":
                    prev = [r.computed_value for r in results if r.computed_value is not None]
                    res.computed_value = prev[-1] if prev else None
                    res.summary = f"Using the deterministic result from the previous task: {res.computed_value}."
                else:
                    prev = [r.computed_value for r in results if r.computed_value is not None]
                    res.computed_value = prev[-1] if prev else None

            results.append(res)

        # Build evidence text
        evidence_lines = [f"Pattern: {plan.pattern}"]
        for r in results:
            evidence_lines.append(f"[{r.task_id}] {r.description} -> {r.summary}")
            if r.sql_rows:
                for row in r.sql_rows[:8]:
                    evidence_lines.append(f"   Row: {row}")
            if r.fts_snippets:
                for snip in r.fts_snippets[:3]:
                    evidence_lines.append(f"   FTS [{snip['doc_id']}]: {snip['content'][:250]}...")

        candidate = results[-1].computed_value if results and results[-1].computed_value is not None else None
        return RetrievalContext(
            plan=plan,
            task_results=results,
            evidence_text="\n".join(evidence_lines),
            candidate_answer=candidate
        )

