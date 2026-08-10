"""
Shape library: one function per reasoning pattern, each a thin wrapper
around a deterministic SQL query against the schema in db/schema.py.

Every function takes the sqlite3 connection plus already-resolved
entities (client name, engineer name, a threshold, a date, ...) and
returns (answer, trace) where `trace` is the row-level data used to
compute the answer -- keep it, it's what lets you debug a wrong answer
without re-deriving it by hand.

Nothing here is probabilistic. Given the same facts and the same bound
entities, every function returns the same answer every time -- that's
the whole point.
"""
from parsers.dates import parse_date, date_diff_days


def _client_id(con, client_name):
    row = con.execute("SELECT client_id FROM clients WHERE name = ?", (client_name,)).fetchone()
    if row is None:
        raise ValueError(f"unknown client: {client_name!r}")
    return row["client_id"]


def _engineer_id(con, engineer_name):
    row = con.execute("SELECT engineer_id FROM engineers WHERE name = ?", (engineer_name,)).fetchone()
    if row is None:
        raise ValueError(f"unknown engineer: {engineer_name!r}")
    return row["engineer_id"]


def _portfolio(con, client_name):
    """All projects for a client. Returns list of sqlite3.Row."""
    cid = _client_id(con, client_name)
    return con.execute(
        "SELECT * FROM projects WHERE client_id = ?", (cid,)
    ).fetchall()


def _works_led(con, engineer_name):
    """All projects a given engineer led."""
    eid = _engineer_id(con, engineer_name)
    return con.execute(
        "SELECT * FROM projects WHERE engineer_id = ?", (eid,)
    ).fetchall()


# --- shapes -------------------------------------------------------------

def shape_absence(con, client_name):
    """Count of a client's completed works with no reference letter on file."""
    rows = _portfolio(con, client_name)
    missing = [r for r in rows if not r["has_reference_letter"]]
    return len(missing), {"portfolio_size": len(rows), "missing_ids": [r["project_id"] for r in missing]}


def shape_referenced_share(con, client_name):
    """Percent of a client's works that DO have a reference letter, 2dp."""
    rows = _portfolio(con, client_name)
    if not rows:
        raise ValueError("empty portfolio")
    referenced = sum(1 for r in rows if r["has_reference_letter"])
    pct = round(100 * referenced / len(rows), 2)
    return pct, {"referenced": referenced, "total": len(rows)}


def shape_date_span(con, engineer_name, cert_type, issue_date, project_name):
    """Days between a named cert's issue date and a named project's completion date."""
    eid = _engineer_id(con, engineer_name)
    if issue_date is None:
        cert_row = con.execute(
            "SELECT issue_date FROM engineer_certs WHERE engineer_id = ? AND cert_type = ?",
            (eid, cert_type),
        ).fetchone()
        if cert_row:
            issue_date = cert_row[0]
            
    cert = con.execute(
        "SELECT * FROM engineer_certs WHERE engineer_id = ? AND cert_type = ? AND issue_date = ?",
        (eid, cert_type, issue_date),
    ).fetchone()
    if cert is None:
        raise ValueError("cert not found")
    project = con.execute(
        "SELECT * FROM projects WHERE name = ?", (project_name,)
    ).fetchone()
    if project is None:
        raise ValueError("project not found")
    days = date_diff_days(issue_date, project["completion_date"])
    return days, {"issue_date": issue_date, "completion_date": project["completion_date"]}


def shape_distinct_count(con, engineer_name, cert_type=None):
    """Distinct project categories among an engineer's led works."""
    rows = _works_led(con, engineer_name)
    categories = {r["category"] for r in rows}
    return len(categories), {"categories": sorted(categories)}


def shape_hop_aggregate(con, engineer_name, client_name):
    """Sum of all client works (the contractor's portfolio for this client)."""
    rows = _portfolio(con, client_name)
    total = sum(r["value_rupees"] for r in rows)
    return total, {"values": [r["value_rupees"] for r in rows]}


def shape_temporal_chain(con, engineer_name, issue_date):
    """Sum of an engineer's works completed after a given date."""
    rows = _works_led(con, engineer_name)
    if issue_date is None:
        eid = _engineer_id(con, engineer_name)
        cert_row = con.execute(
            "SELECT issue_date FROM engineer_certs WHERE engineer_id = ? AND cert_type = 'PMP'",
            (eid,),
        ).fetchone()
        if cert_row:
            issue_date = cert_row[0]
            
    issue = parse_date(issue_date)
    if not issue:
        raise ValueError(f"invalid issue_date: {issue_date}")
    after = []
    for r in rows:
        comp_date = parse_date(r["completion_date"]) if r["completion_date"] else None
        if comp_date and comp_date > issue:
            after.append(r)
    total = sum(r["value_rupees"] for r in after)
    return total, {"values": [r["value_rupees"] for r in after]}


def shape_avg_work_size(con, client_name):
    """Mean project value across a client's whole portfolio."""
    rows = _portfolio(con, client_name)
    if not rows:
        raise ValueError("empty portfolio")
    total = sum(r["value_rupees"] for r in rows)
    avg = total // len(rows) if total % len(rows) == 0 else round(total / len(rows))
    return avg, {"values": [r["value_rupees"] for r in rows], "count": len(rows)}


def shape_doc_filtered_aggregate(con, client_name, grading):
    """Sum of a client's works filtered by written grading."""
    rows = _portfolio(con, client_name)
    matched = [r for r in rows if r["grading"] == grading]
    total = sum(r["value_rupees"] for r in matched)
    return total, {"values": [r["value_rupees"] for r in matched]}


def shape_exclusion_aggregate(con, client_name, exclude_category):
    """Sum of a client's works, excluding one category."""
    rows = _portfolio(con, client_name)
    if exclude_category is None:
        exclude_category = ""
    matched = [r for r in rows if r["category"] != exclude_category]
    total = sum(r["value_rupees"] for r in matched)
    return total, {"values": [r["value_rupees"] for r in matched]}


def shape_gap_to_threshold(con, client_name, threshold_rupees):
    """How much more value is needed to reach a target, given current total."""
    rows = _portfolio(con, client_name)
    total = sum(r["value_rupees"] for r in rows)
    if threshold_rupees is None:
        threshold_rupees = 0
    gap = threshold_rupees - total
    return gap, {"current_total": total, "threshold": threshold_rupees}


def shape_rank_value(con, client_name):
    """Difference in value between the largest and second-largest completed work for a client."""
    rows = _portfolio(con, client_name)
    values = sorted((r["value_rupees"] for r in rows), reverse=True)
    if len(values) < 2:
        raise ValueError("need at least 2 works to rank")
    diff = values[0] - values[1]
    return diff, {"sorted_values": values}



def shape_role_split(con, client_name, role):
    """Sum of a client's works filtered by contracting role."""
    rows = _portfolio(con, client_name)
    matched = [r for r in rows if r["role"] == role]
    total = sum(r["value_rupees"] for r in matched)
    return total, {"values": [r["value_rupees"] for r in matched]}


def shape_threshold_aggregate(con, client_name, threshold_rupees):
    """Sum of a client's works whose value exceeds a threshold."""
    rows = _portfolio(con, client_name)
    if threshold_rupees is None:
        threshold_rupees = 0
    matched = [r for r in rows if r["value_rupees"] > threshold_rupees]
    total = sum(r["value_rupees"] for r in matched)
    return total, {"values": [r["value_rupees"] for r in matched]}
def shape_category_diff(con, client_name, category_a, category_b):
    """Absolute value difference between two category totals for a client.

    Returns abs(sum(cat_a) - sum(cat_b)) so the answer is always positive
    regardless of which category the question happens to mention first.
    """
    rows = _portfolio(con, client_name)
    total_a = sum(r["value_rupees"] for r in rows if r["category"] == category_a)
    total_b = sum(r["value_rupees"] for r in rows if r["category"] == category_b)
    diff = abs(total_a - total_b)
    return diff, {"category_a": category_a, "total_a": total_a, "category_b": category_b, "total_b": total_b}


# Question-understanding (Stage 4) resolves a question to one of these
# names plus a kwargs dict; the pipeline just does REGISTRY[shape](con, **kwargs).
REGISTRY = {
    "absence": shape_absence,
    "referenced_share": shape_referenced_share,
    "date_span": shape_date_span,
    "distinct_count": shape_distinct_count,
    "hop_aggregate": shape_hop_aggregate,
    "temporal_chain": shape_temporal_chain,
    "avg_work_size": shape_avg_work_size,
    "doc_filtered_aggregate": shape_doc_filtered_aggregate,
    "exclusion_aggregate": shape_exclusion_aggregate,
    "gap_to_threshold": shape_gap_to_threshold,
    "rank_value": shape_rank_value,
    "role_split": shape_role_split,
    "threshold_aggregate": shape_threshold_aggregate,
    "category_diff": shape_category_diff,
}

