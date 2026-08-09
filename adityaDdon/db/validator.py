#!/usr/bin/env python3
"""
validator.py — Automated quality check suite for validating the extracted DuckDB database
against the 8 core dataset invariants.
"""

import sys
from pathlib import Path
from database import get_db, DEFAULT_DB_PATH

def run_validation():
    print("=" * 60)
    print("RUNNING 8 QUALITY INVARIANT CHECKS ON DUCKDB DATABASE")
    print("=" * 60)

    db = get_db(DEFAULT_DB_PATH)
    con = db.conn

    passed = 0
    total = 8

    # 1. Total Projects Count (Invariant: Exactly 155)
    row = con.execute("SELECT COUNT(*) FROM projects").fetchone()
    count_projects = row[0]
    print(f"[INV-01] Total Projects Count: {count_projects} / 155", end=" -> ")
    assert count_projects == 155, f"Expected 155 projects, got {count_projects}"
    print("PASSED ✅")
    passed += 1

    # 2. Reference Letters Present Count (Invariant: Exactly 132)
    row = con.execute("SELECT COUNT(*) FROM projects WHERE has_reference_letter = true").fetchone()
    count_ref = row[0]
    print(f"[INV-02] Reference Letters Present: {count_ref} / 132", end=" -> ")
    assert count_ref == 132, f"Expected 132 reference letters, got {count_ref}"
    print("PASSED ✅")
    passed += 1

    # 3. Missing Reference Letters Count (Invariant: Exactly 23)
    row = con.execute("SELECT COUNT(*) FROM projects WHERE has_reference_letter = false").fetchone()
    count_missing = row[0]
    print(f"[INV-03] Missing Reference Letters: {count_missing} / 23", end=" -> ")
    assert count_missing == 23, f"Expected 23 missing reference letters, got {count_missing}"
    print("PASSED ✅")
    passed += 1

    # 4. Total Portfolio Valuation (Invariant: ~5,530 Crore INR)
    row = con.execute("SELECT SUM(contract_value_inr) FROM projects").fetchone()
    total_val = row[0]
    total_cr = round(total_val / 10_000_000, 2)
    print(f"[INV-04] Total Portfolio Valuation: ₹{total_cr} Cr (~₹5,530 Cr)", end=" -> ")
    assert 50_000_000_000 <= total_val <= 60_000_000_000, f"Portfolio value out of range: {total_val}"
    print("PASSED ✅")
    passed += 1

    # 5. Total Personnel Credentials (Invariant: Exactly 48)
    row = con.execute("SELECT COUNT(*) FROM credentials").fetchone()
    count_certs = row[0]
    print(f"[INV-05] Total Credentials: {count_certs} / 48", end=" -> ")
    assert count_certs == 48, f"Expected 48 credentials, got {count_certs}"
    print("PASSED ✅")
    passed += 1

    # 6. Total Performance Bonds (Invariant: Exactly 60)
    row = con.execute("SELECT COUNT(*) FROM performance_bonds").fetchone()
    count_bonds = row[0]
    print(f"[INV-06] Total Performance Bonds: {count_bonds} / 60", end=" -> ")
    assert count_bonds == 60, f"Expected 60 bonds, got {count_bonds}"
    print("PASSED ✅")
    passed += 1

    # 7. Total Engineers on Record (Invariant: Exactly 39 from CVs)
    row = con.execute("SELECT COUNT(*) FROM engineers").fetchone()
    count_eng = row[0]
    print(f"[INV-07] Total Engineers from CVs: {count_eng} / 39", end=" -> ")
    assert count_eng == 39, f"Expected 39 engineers, got {count_eng}"
    print("PASSED ✅")
    passed += 1

    # 8. Full-Text Search BM25 Test
    fts_results = db.search_fts("Asha Nair Cable Stayed Bridge Pkg-115", limit=3)
    print(f"[INV-08] DuckDB FTS BM25 Retrieval: {len(fts_results)} matches", end=" -> ")
    assert len(fts_results) > 0, "FTS returned 0 results"
    print(f"PASSED ✅ (Top match: {fts_results[0]['doc_id']}, score: {fts_results[0]['score']:.2f})")
    passed += 1

    print("=" * 60)
    print(f"ALL {passed}/{total} QUALITY INVARIANT CHECKS PASSED WITH 100% INTEGRITY! 🏆")
    print("=" * 60)

if __name__ == "__main__":
    run_validation()
