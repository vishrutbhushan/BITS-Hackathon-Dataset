#!/usr/bin/env python3
"""Audit project fact coverage and agreement without consulting questions."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import DEFAULT_DB_PATH, get_db
from source_consensus import (
    parse_client_certificate,
    parse_company_certificate,
    parse_portfolio,
    reconcile_project,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_ROOT = WORKSPACE_ROOT / "documents"


def pdf_text(path: Path) -> str:
    with pymupdf.open(path) as document:
        return "\n".join(page.get_text() for page in document)


def load_sources():
    portfolio_path = DOCUMENTS_ROOT / "past_performance_portfolio" / "DOC-PPP-001.pdf"
    portfolio = parse_portfolio(pdf_text(portfolio_path))
    company = {}
    for path in sorted((DOCUMENTS_ROOT / "company_completion_certificate").glob("*.pdf")):
        record = parse_company_certificate(pdf_text(path), path.stem)
        if record["package_number"] is not None:
            company[record["package_number"]] = record
    client = {}
    for path in sorted((DOCUMENTS_ROOT / "completion_certificate").glob("*.pdf")):
        record = parse_client_certificate(pdf_text(path), path.stem)
        if record["package_number"] is not None:
            client[record["package_number"]] = record
    return portfolio, company, client


def audit() -> int:
    portfolio, company, client = load_sources()
    expected = set(range(1, 156))
    print(
        "source coverage:",
        {"portfolio": len(portfolio), "company": len(company), "client": len(client)},
    )
    for name, records in (("portfolio", portfolio), ("company", company), ("client", client)):
        missing = sorted(expected - set(records))
        if missing:
            print(f"{name} missing packages: {missing}")

    statuses = Counter()
    selected = {}
    for package in sorted(expected):
        sources = {
            name: records[package]
            for name, records in (("portfolio", portfolio), ("company_certificate", company), ("client_certificate", client))
            if package in records
        }
        consensus = reconcile_project(sources)
        selected[package] = consensus
        statuses.update((field, fact.status) for field, fact in consensus.items())

    print("consensus statuses:")
    for (field, status), count in sorted(statuses.items()):
        print(f"  {field:18s} {status:20s} {count:3d}")

    db = get_db(DEFAULT_DB_PATH)
    rows = db.fetchall(
        """
        SELECT package_number, title, canonical_client, category,
               contract_value_inr, completion_date, project_lead, role
        FROM projects ORDER BY package_number
        """
    )
    columns = (
        "title",
        "client",
        "category",
        "value_inr",
        "completion_date",
        "project_lead",
        "role",
    )
    mismatches = []
    for row in rows:
        package = int(row[0])
        for field, current in zip(columns, row[1:]):
            proposed = selected[package][field].value
            if proposed is not None and proposed != current:
                mismatches.append((package, field, current, proposed, selected[package][field].status))
    print(f"database differences: {len(mismatches)}")
    for mismatch in mismatches:
        print(" ", mismatch)
    return 1 if any(set(records) != expected for records in (portfolio, company, client)) else 0


if __name__ == "__main__":
    raise SystemExit(audit())
