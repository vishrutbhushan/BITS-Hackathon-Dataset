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
    print("RUNNING QUALITY INVARIANT CHECKS ON DUCKDB DATABASE")
    print("=" * 60)

    db = get_db(DEFAULT_DB_PATH)
    con = db.conn

    passed = 0
    total = 18

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

    # 9. Every project has a positive exact value and parseable date.
    bad_projects = con.execute("""
        SELECT COUNT(*) FROM projects
        WHERE contract_value_inr <= 0 OR try_cast(completion_date AS DATE) IS NULL
    """).fetchone()[0]
    print(f"[INV-09] Complete project facts: {bad_projects} invalid", end=" -> ")
    assert bad_projects == 0
    print("PASSED ✅")
    passed += 1

    # 10. Materialized client aggregates agree with base project facts.
    bad_clients = con.execute("""
        SELECT COUNT(*) FROM clients c
        JOIN (
            SELECT canonical_client, COUNT(*) AS n, SUM(contract_value_inr) AS v,
                   SUM(has_reference_letter::INTEGER) AS r
            FROM projects GROUP BY canonical_client
        ) p USING (canonical_client)
        WHERE c.total_works <> p.n OR c.total_value_inr <> p.v OR c.referenced_works <> p.r
    """).fetchone()[0]
    print(f"[INV-10] Client aggregate reconciliation: {bad_clients} mismatches", end=" -> ")
    assert bad_clients == 0
    print("PASSED ✅")
    passed += 1

    # 11. Receivables workbook arithmetic is lossless, including overpayments.
    bad_ar = con.execute("""
        SELECT COUNT(*) FROM workbooks_receivables
        WHERE invoiced_inr - received_inr <> outstanding_inr
    """).fetchone()[0]
    print(f"[INV-11] Receivables arithmetic: {bad_ar} mismatches", end=" -> ")
    assert bad_ar == 0
    print("PASSED ✅")
    passed += 1

    # 12. All seven audited years expose both contract and total revenue.
    financial_facts = con.execute("SELECT COUNT(*) FROM financial_metrics").fetchone()[0]
    print(f"[INV-12] Audited financial metrics: {financial_facts} / 14", end=" -> ")
    assert financial_facts == 14
    print("PASSED ✅")
    passed += 1

    # 13. Measurement facts were not collapsed into tender BOQ rows.
    measurement_count = con.execute("SELECT COUNT(*) FROM workbooks_boq_measurements").fetchone()[0]
    print(f"[INV-13] BOQ measurement facts: {measurement_count}", end=" -> ")
    assert measurement_count > 0
    print("PASSED ✅")
    passed += 1

    # 14. A zero parsed bond must not hide a readable non-zero unit amount.
    zero_bond_texts = con.execute("""
        SELECT d.content FROM performance_bonds b
        JOIN documents d ON d.doc_id = b.doc_id
        WHERE b.guarantee_amount_inr = 0
    """).fetchall()
    import re
    missed_bonds = 0
    for (content,) in zero_bond_texts:
        amounts = re.findall(r"(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)\s*(?:Cr|Crore|Lakhs?)", content, re.I)
        if any(float(value.replace(',', '')) > 0 for value in amounts):
            missed_bonds += 1
    print(f"[INV-14] Readable bond amounts missed: {missed_bonds}", end=" -> ")
    assert missed_bonds == 0
    print("PASSED ✅")
    passed += 1

    # 15. Every project is represented by all three independent source
    # families in the provenance table.
    source_coverage = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT package_number
            FROM project_fact_evidence
            GROUP BY package_number
            HAVING COUNT(DISTINCT source_type) = 3
        )
    """).fetchone()[0]
    print(f"[INV-15] Three-source project coverage: {source_coverage} / 155", end=" -> ")
    assert source_coverage == 155
    print("PASSED ✅")
    passed += 1

    # 16. Dates must agree after explicit Indian day-first normalization.
    non_unanimous_dates = con.execute("""
        SELECT COUNT(DISTINCT package_number)
        FROM project_fact_evidence
        WHERE field_name = 'completion_date' AND consensus_status <> 'unanimous'
    """).fetchone()[0]
    print(f"[INV-16] Completion-date source conflicts: {non_unanimous_dates}", end=" -> ")
    assert non_unanimous_dates == 0
    print("PASSED ✅")
    passed += 1

    # 17. No delivery role may come from a silent default.
    bad_roles = con.execute("""
        SELECT COUNT(*) FROM projects
        WHERE role NOT IN ('Prime', 'JV Partner', 'Subcontractor')
    """).fetchone()[0]
    role_evidence = con.execute("""
        SELECT COUNT(DISTINCT package_number)
        FROM project_fact_evidence WHERE field_name = 'role'
    """).fetchone()[0]
    print(f"[INV-17] Proven delivery roles: {role_evidence} / 155", end=" -> ")
    assert bad_roles == 0 and role_evidence == 155
    print("PASSED ✅")
    passed += 1

    # 18. The online project table must exactly match every selected evidence
    # field that drives arithmetic or routing.
    project_evidence_mismatches = con.execute("""
        WITH selected AS (
            SELECT package_number,
                   MAX(CASE WHEN field_name='value_inr' AND agrees_with_selected THEN normalized_value END) AS value_inr,
                   MAX(CASE WHEN field_name='completion_date' AND agrees_with_selected THEN normalized_value END) AS completion_date,
                   MAX(CASE WHEN field_name='role' AND agrees_with_selected THEN normalized_value END) AS role
            FROM project_fact_evidence
            GROUP BY package_number
        )
        SELECT COUNT(*)
        FROM projects p JOIN selected s USING(package_number)
        WHERE CAST(p.contract_value_inr AS VARCHAR) <> s.value_inr
           OR p.completion_date <> s.completion_date
           OR p.role <> s.role
    """).fetchone()[0]
    print(f"[INV-18] Online/source selected fact mismatches: {project_evidence_mismatches}", end=" -> ")
    assert project_evidence_mismatches == 0
    print("PASSED ✅")
    passed += 1

    print("=" * 60)
    print(f"ALL {passed}/{total} QUALITY INVARIANT CHECKS PASSED WITH 100% INTEGRITY! 🏆")
    print("=" * 60)

if __name__ == "__main__":
    run_validation()
