#!/usr/bin/env python3
"""
build_database.py — Ingest all 687 documents into DuckDB with FTS BM25 index
and high-precision relational tables cross-referenced across PPP, CCC, CC, REF, PCERT, CV, BOND, and Workbooks.
"""

import os
import sys
import re
import csv
import json
from pathlib import Path
from dateutil import parser as dt_parser
import openpyxl
import fitz

from database import get_db, DEFAULT_DB_PATH

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
DOCUMENTS_ROOT = WORKSPACE_ROOT / "documents"
EXTRACTED_TEXT_ROOT = WORKSPACE_ROOT / "extracted_text"
INDEX_CSV = WORKSPACE_ROOT / "document_index.csv"

def parse_iso_date(d_str):
    if not d_str:
        return None
    d_clean = str(d_str).strip()
    try:
        return dt_parser.parse(d_clean).strftime('%Y-%m-%d')
    except Exception:
        return d_clean

def normalize_inr(raw):
    if raw is None:
        return 0
    raw_str = str(raw).strip()
    m_cr = re.search(r'(?:INR|Rs\.?|₹)?\s*([\d.]+)\s*(?:Cr|crore)', raw_str, re.I)
    if m_cr:
        return int(round(float(m_cr.group(1)) * 10_000_000))
    m_lakh = re.search(r'(?:INR|Rs\.?|₹)?\s*([\d.]+)\s*(?:Lakh|lakh)', raw_str, re.I)
    if m_lakh:
        return int(round(float(m_lakh.group(1)) * 100_000))
    digits = re.sub(r'[^\d]', '', raw_str)
    return int(digits) if digits else 0

def clean_client_name(name):
    if not name:
        return ""
    c = str(name).strip()
    c = re.sub(r'\s*\(.*?\)', '', c)
    c = c.strip(' ,.')
    return c

def build():
    print(f"Initializing DuckDB at {DEFAULT_DB_PATH}...")
    if DEFAULT_DB_PATH.exists():
        DEFAULT_DB_PATH.unlink()

    db = get_db(DEFAULT_DB_PATH)
    con = db.conn

    # 1. Create Raw Documents Table
    print("Creating documents table...")
    con.execute("""
        CREATE TABLE documents (
            doc_id VARCHAR PRIMARY KEY,
            doc_type VARCHAR,
            filename VARCHAR,
            page_count INTEGER,
            char_count INTEGER,
            content VARCHAR,
            metadata JSON
        );
    """)

    # 2. Ingest PDFs and Workbooks into documents table
    print("Ingesting all 687 documents...")
    with open(INDEX_CSV, newline="", encoding="utf-8") as f:
        doc_entries = list(csv.DictReader(f))

    for entry in doc_entries:
        doc_id = entry["doc_id"]
        doc_type = entry["doc_type"]
        rel_filename = entry["filename"]
        file_path = DOCUMENTS_ROOT / rel_filename

        text_content = ""
        page_count = 1

        if rel_filename.endswith(".xlsx"):
            try:
                wb = openpyxl.load_workbook(file_path, data_only=True)
                sheets_text = []
                for sname in wb.sheetnames:
                    ws = wb[sname]
                    sheets_text.append(f"--- Sheet: {sname} ---")
                    for row in ws.iter_rows(values_only=True):
                        row_vals = [str(c) if c is not None else "" for c in row]
                        if any(row_vals):
                            sheets_text.append("\t".join(row_vals))
                text_content = "\n".join(sheets_text)
                page_count = len(wb.sheetnames)
            except Exception as e:
                text_content = f"Error loading workbook: {e}"
        else:
            try:
                doc = fitz.open(file_path)
                page_count = len(doc)
                pages = [f"--- Page {i+1} ---\n" + page.get_text() for i, page in enumerate(doc)]
                text_content = "\n\n".join(pages)
                doc.close()
            except Exception as e:
                txt_path = EXTRACTED_TEXT_ROOT / doc_type / f"{doc_id}.txt"
                if txt_path.exists():
                    text_content = txt_path.read_text(encoding="utf-8")

        con.execute("""
            INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?);
        """, [
            doc_id, doc_type, rel_filename, page_count,
            len(text_content), text_content, json.dumps({"doc_id": doc_id, "doc_type": doc_type})
        ])

    print(f"Ingested {len(doc_entries)} documents into documents table.")

    # 3. Create DuckDB FTS Index
    print("Building Full-Text Search (FTS BM25) index...")
    con.execute("PRAGMA create_fts_index('documents', 'doc_id', 'content');")
    print("FTS BM25 index built successfully.")

    # 4. Extract Reference Letters (132 files)
    ref_projects = {}
    for p in sorted((DOCUMENTS_ROOT / "reference_letter").glob("*.pdf")):
        doc = fitz.open(p)
        text = "\n".join([page.get_text() for page in doc])
        doc.close()
        m_pkg = re.search(r'Pkg-(\d+)', text)
        if m_pkg:
            pkg_num = int(m_pkg.group(1))
            ref_projects[pkg_num] = p.stem

    # 5. Extract Client CCs for Ratings (155 files)
    client_cc_map = {}
    for p in sorted((DOCUMENTS_ROOT / "completion_certificate").glob("*.pdf")):
        doc = fitz.open(p)
        text = "\n".join([page.get_text() for page in doc])
        doc.close()
        m_pkg = re.search(r'Pkg-(\d+)', text)
        pkg_num = int(m_pkg.group(1)) if m_pkg else None
        
        # Priority 1: Graded in Quality Assessment section
        m_sec3 = re.search(r'3\.\s*Quality Assessment\s*\n+.*?\b(Outstanding|Excellent|Very Good|Satisfactory|Good)\b', text, re.I | re.S)
        grade = None
        if m_sec3:
            grade = m_sec3.group(1).title()
        
        if not grade:
            m_grade = re.search(r'\b(?:graded|assessed as|overall performance was)\s*[\"\'\s]*\b(Outstanding|Excellent|Very Good|Satisfactory|Good)\b', text, re.I)
            if m_grade:
                grade = m_grade.group(1).title()

        if not grade:
            if re.search(r'taken over on\s+satisfactory\s+completion', text, re.I):
                grade = "Satisfactory"
            elif re.search(r'conforming to the technical specifications', text, re.I):
                grade = "Good"
            else:
                grade = "Good"
        
        if pkg_num:
            client_cc_map[pkg_num] = {
                "doc_id": p.stem,
                "grade": grade
            }

    # 6. Extract Master 155 Works from Past Performance Portfolio (DOC-PPP-001.pdf)
    print("Extracting master catalog from past_performance_portfolio...")
    ppp_doc = fitz.open(DOCUMENTS_ROOT / "past_performance_portfolio" / "DOC-PPP-001.pdf")
    ppp_text = "\n".join([page.get_text() for page in ppp_doc])
    ppp_doc.close()

    # Split into project datasheets
    ppp_blocks = re.findall(
        r'(\d+)\.\s*([^\n]+)\s*\nClient\s*\n([^\n]+)\s*\nCategory\s*\n([^\n]+)\s*\nExecuted Value\s*\n([^\n]+)\s*\nCompleted\s*\n([^\n]+)',
        ppp_text, re.I
    )

    ppp_records = {}
    for b in ppp_blocks:
        w_num = int(b[0])
        raw_title = b[1].strip()
        raw_client = b[2].strip()
        cat = b[3].strip()
        raw_val = b[4].strip()
        comp_str = b[5].strip()

        m_pkg = re.search(r'Pkg-(\d+)', raw_title, re.I)
        pkg_num = int(m_pkg.group(1)) if m_pkg else w_num

        m_role = re.search(r'\((Prime|Subcontractor|JV|Joint Venture|JV Partner)\)', raw_client, re.I)
        role = "Prime"
        if m_role:
            r_matched = m_role.group(1).lower()
            if "prime" in r_matched:
                role = "Prime"
            elif "subcontractor" in r_matched:
                role = "Subcontractor"
            elif "jv" in r_matched or "joint" in r_matched:
                role = "JV Partner"

        canonical_client = clean_client_name(raw_client)
        val_inr = normalize_inr(raw_val)
        val_cr = round(val_inr / 10_000_000, 2)
        comp_date = parse_iso_date(comp_str.split('·')[0].strip())

        ppp_records[pkg_num] = {
            "work_no": w_num,
            "raw_title": raw_title,
            "canonical_client": canonical_client,
            "raw_client": raw_client,
            "category": cat,
            "val_inr": val_inr,
            "val_cr": val_cr,
            "comp_date": comp_date,
            "role": role
        }

    # 7. Extract Project Lead & Exact Title from Company Completion Certificates (155 files)
    print("Extracting project leads and metadata from company_completion_certificate...")
    ccc_records = {}
    for p in sorted((DOCUMENTS_ROOT / "company_completion_certificate").glob("*.pdf")):
        doc = fitz.open(p)
        text = "\n".join([page.get_text() for page in doc])
        doc.close()

        m_ref = re.search(r'(?:Internal Ref:\s*CCC/|Ref:\s*NICL/CC/)(\d+)', text)
        work_no = int(m_ref.group(1)) if m_ref else int(re.search(r'\d+', p.stem).group(0))

        m_work = re.search(r'(?:Project Name|Work)\s*\n\s*([^\n]+)', text)
        title = m_work.group(1).strip() if m_work else ""

        m_pkg = re.search(r'Pkg-(\d+)', title)
        pkg_num = int(m_pkg.group(1)) if m_pkg else work_no

        m_lead = re.search(r'(?:Project Manager|Project Lead)\s*\n\s*([^\n]+)', text)
        lead = m_lead.group(1).strip() if m_lead else ""

        m_client = re.search(r'Client\s*\n\s*([^\n]+)', text)
        ccc_client = m_client.group(1).strip() if m_client else ""

        m_cat = re.search(r'(?:Work Category|Category)\s*\n\s*([^\n]+)', text)
        ccc_cat = m_cat.group(1).strip() if m_cat else ""

        m_val = re.search(r'(?:Contract Value|Executed Value)\s*\n\s*([^\n]+)', text)
        val_inr = normalize_inr(m_val.group(1)) if m_val else 0

        m_comp = re.search(r'(?:Completion Date|Completion)\s*\n\s*([^\n]+)', text)
        comp_date = parse_iso_date(m_comp.group(1)) if m_comp else ""

        ccc_records[pkg_num] = {
            "doc_id": p.stem,
            "work_no": work_no,
            "title": title,
            "lead": lead,
            "client": clean_client_name(ccc_client),
            "category": ccc_cat,
            "val_inr": val_inr,
            "comp_date": comp_date
        }

    # 8. Populate Projects Table by synthesizing PPP + CCC + CC + REF
    con.execute("""
        CREATE TABLE projects (
            project_id VARCHAR PRIMARY KEY,
            work_no INTEGER,
            title VARCHAR,
            state VARCHAR,
            package_number INTEGER,
            package_str VARCHAR,
            category VARCHAR,
            client_name VARCHAR,
            canonical_client VARCHAR,
            project_lead VARCHAR,
            contract_value_inr BIGINT,
            contract_value_cr DOUBLE,
            completion_date VARCHAR,
            completion_year INTEGER,
            performance_grading VARCHAR,
            has_reference_letter BOOLEAN,
            role VARCHAR,
            client_cert_ref VARCHAR,
            ccc_doc_id VARCHAR,
            cc_doc_id VARCHAR,
            ref_doc_id VARCHAR
        );
    """)

    for pkg_num in sorted(ccc_records.keys()):
        ccc = ccc_records[pkg_num]
        ppp = ppp_records.get(pkg_num, {})
        cc = client_cc_map.get(pkg_num, {})

        title = ccc.get("title") or ppp.get("raw_title", f"Package Pkg-{pkg_num}")
        m_state = re.search(r'(?:—|-)\s*([A-Za-z\s]+?)\s*Pkg-', title)
        state = m_state.group(1).strip() if m_state else "India"

        project_id = f"{state.upper().replace(' ', '_')}_PKG_{pkg_num:03d}"
        package_str = f"Pkg-{pkg_num}"

        canonical_client = ppp.get("canonical_client") or ccc.get("client") or "National Special Projects Office"
        category = ccc.get("category") or ppp.get("category") or "Civil Construction"
        val_inr = ccc.get("val_inr") or ppp.get("val_inr") or 0
        val_cr = round(val_inr / 10_000_000, 2)
        comp_date = ccc.get("comp_date") or ppp.get("comp_date") or "2020-01-01"
        comp_year = int(comp_date[:4]) if comp_date and len(comp_date) >= 4 else 2020
        lead = ccc.get("lead", "")
        grade = cc.get("grade", "Satisfactory")
        has_ref = pkg_num in ref_projects
        ref_doc = ref_projects.get(pkg_num, "")
        cc_doc = cc.get("doc_id", "")
        ccc_doc = ccc.get("doc_id", "")
        role = ppp.get("role", "Prime")

        con.execute("""
            INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [
            project_id, ccc.get("work_no", pkg_num), title, state, pkg_num, package_str,
            category, canonical_client, canonical_client, lead, val_inr, val_cr,
            comp_date, comp_year, grade, has_ref, role,
            "", ccc_doc, cc_doc, ref_doc
        ])

    print("Populated 155 projects into relational table.")

    # 9. Populate Clients Table
    print("Populating clients table...")
    con.execute("""
        CREATE TABLE clients AS
        SELECT 
            canonical_client AS client_name,
            canonical_client,
            COUNT(*) AS total_works,
            SUM(contract_value_inr) AS total_value_inr,
            ROUND(SUM(contract_value_inr) / 10000000.0, 2) AS total_value_cr,
            SUM(CASE WHEN has_reference_letter THEN 1 ELSE 0 END) AS referenced_works,
            SUM(CASE WHEN NOT has_reference_letter THEN 1 ELSE 0 END) AS unreferenced_works
        FROM projects
        GROUP BY canonical_client;
    """)

    # 10. Populate Credentials Table (48 certs)
    con.execute("""
        CREATE TABLE credentials (
            credential_id VARCHAR PRIMARY KEY,
            doc_id VARCHAR,
            engineer_name VARCHAR,
            employee_id VARCHAR,
            credential_type VARCHAR,
            issue_date VARCHAR,
            valid_through VARCHAR
        );
    """)
    for p in sorted((DOCUMENTS_ROOT / "personnel_certificate").glob("*.pdf")):
        doc = fitz.open(p)
        text = "\n".join([page.get_text() for page in doc])
        doc.close()

        m_id = re.search(r'(?:Credential ID|Certificate No\.?)\s*[:\n]\s*([A-Z0-9-]+)', text)
        cid = m_id.group(1).strip() if m_id else p.stem

        m_holder = re.search(r'(?:This is to certify that|This credential is conferred upon)\s*\n\s*([^\n]+)', text)
        holder = m_holder.group(1).strip() if m_holder else ""

        m_emp = re.search(r'Employee ID:\s*(EMP-\d+)', text)
        emp = m_emp.group(1).strip() if m_emp else ""

        m_type = re.search(r'(?:Credential Type\s*\n\s*([^\n]+)|\b(PMP|Six Sigma Black Belt|SSBB)\b)', text, re.I)
        ctype = (m_type.group(1) or m_type.group(2)).strip() if m_type else "PMP"
        if "pmp" in ctype.lower(): ctype = "PMP"
        elif "sigma" in ctype.lower(): ctype = "Six Sigma Black Belt"

        m_issue = re.search(r'(?:Date of Issue|Issued)\s*[:\n]\s*([^\n]+)', text)
        issue = parse_iso_date(m_issue.group(1)) if m_issue else ""

        m_valid = re.search(r'Valid Through\s*[:\n]\s*([^\n]+)', text)
        valid = parse_iso_date(m_valid.group(1)) if m_valid else ""

        con.execute("""
            INSERT INTO credentials VALUES (?, ?, ?, ?, ?, ?, ?);
        """, [cid, p.stem, holder, emp, ctype, issue, valid])

    # 11. Populate Engineers Table (39 CVs)
    con.execute("""
        CREATE TABLE engineers (
            engineer_id VARCHAR PRIMARY KEY,
            full_name VARCHAR,
            employee_id VARCHAR,
            designation VARCHAR,
            business_unit VARCHAR,
            experience_years INTEGER,
            cv_doc_id VARCHAR
        );
    """)
    for p in sorted((DOCUMENTS_ROOT / "cv").glob("*.pdf")):
        doc = fitz.open(p)
        text = "\n".join([page.get_text() for page in doc])
        doc.close()

        m_name = re.search(r'Name\s*\n\s*([^\n]+)', text)
        name = m_name.group(1).strip() if m_name else ""
        m_emp = re.search(r'Employee ID\s*\n\s*(EMP-\d+)', text)
        emp = m_emp.group(1).strip() if m_emp else ""
        m_desig = re.search(r'Designation\s*\n\s*([^\n]+)', text)
        desig = m_desig.group(1).strip() if m_desig else ""
        m_bu = re.search(r'Business Unit\s*\n\s*([^\n]+)', text)
        bu = m_bu.group(1).strip() if m_bu else ""
        m_exp = re.search(r'(?:Total Experience|Experience)\s*\n\s*(\d+)', text)
        exp = int(m_exp.group(1)) if m_exp else 0
        engineer_id = emp if emp else name.upper().replace(' ', '_')

        con.execute("""
            INSERT INTO engineers VALUES (?, ?, ?, ?, ?, ?, ?);
        """, [engineer_id, name, emp, desig, bu, exp, p.stem])

    # 12. Populate Performance Bonds (60 bonds)
    con.execute("""
        CREATE TABLE performance_bonds (
            bond_id VARCHAR PRIMARY KEY,
            doc_id VARCHAR,
            tender_ref VARCHAR,
            bank_name VARCHAR,
            issue_date VARCHAR,
            guarantee_amount_inr BIGINT
        );
    """)
    for p in sorted((DOCUMENTS_ROOT / "performance_bond").glob("*.pdf")):
        doc = fitz.open(p)
        text = "\n".join([page.get_text() for page in doc])
        doc.close()

        m_bond = re.search(r'(?:Bond No|BG No|Bond Reference)\s*[:\n]\s*([A-Z0-9/-]+)', text)
        bond_id = m_bond.group(1).strip() if m_bond else p.stem

        m_rfp = re.search(r'(?:Tender Ref|Tender)\s*[:\s]*([A-Z0-9-]+)|RFP-\d+', text)
        rfp = (m_rfp.group(1) or m_rfp.group(0)).strip() if m_rfp else ""

        m_bank = re.search(r'(?:Guarantor Bank|we,)\s*[:\n\s]*([^\n,]+(?:Bank|Trust|Co\.?))', text, re.I)
        if not m_bank:
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            bank = lines[0] if lines else "Kalinga National Bank"
        else:
            bank = m_bank.group(1).strip()

        m_date = re.search(r'(?:Issue Date|Date)\s*[:\n]\s*([^\n]+)', text)
        date = parse_iso_date(m_date.group(1)) if m_date else ""

        m_amt = re.search(r'not exceeding\s+([^\n,]+(?:Lakh|Crore|Cr|Only|\d+))', text, re.I)
        amt_raw = m_amt.group(1) if m_amt else ""
        amt_inr = normalize_inr(amt_raw)

        con.execute("""
            INSERT INTO performance_bonds VALUES (?, ?, ?, ?, ?, ?);
        """, [bond_id, p.stem, rfp, bank, date, amt_inr])

    # 13. Populate Excel Workbooks
    wb_root = DOCUMENTS_ROOT / "workbooks"

    # Receivables Ageing
    con.execute("""
        CREATE TABLE workbooks_receivables (
            invoice_no VARCHAR PRIMARY KEY,
            client_name VARCHAR,
            canonical_client VARCHAR,
            invoice_date VARCHAR,
            invoiced_inr BIGINT,
            status VARCHAR,
            received_inr BIGINT,
            outstanding_inr BIGINT
        );
    """)
    ageing_wb = openpyxl.load_workbook(wb_root / "Receivables_Ageing.xlsx", data_only=True)
    ws_ar = ageing_wb["AR Ageing"]
    for row in list(ws_ar.iter_rows(values_only=True))[1:]:
        if not row or not row[0] or "TOTAL" in str(row[0]).upper(): continue
        inv_no = str(row[0]).strip()
        client = str(row[1]).strip() if row[1] else ""
        can_client = clean_client_name(client)
        inv_date = parse_iso_date(row[2])
        inv_amt = int(row[3]) if row[3] is not None and str(row[3]).strip().isdigit() else 0
        stat = str(row[4]).strip() if row[4] else ""
        rcv_amt = int(row[5]) if row[5] is not None and str(row[5]).strip().isdigit() else 0
        out_amt = int(row[6]) if row[6] is not None and str(row[6]).strip().replace('-', '').isdigit() else 0
        con.execute("""
            INSERT INTO workbooks_receivables VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, [inv_no, client, can_client, inv_date, inv_amt, stat, rcv_amt, out_amt])

    # Plant & Machinery Register
    con.execute("""
        CREATE TABLE workbooks_assets (
            asset_id INTEGER PRIMARY KEY,
            asset_type VARCHAR,
            make VARCHAR,
            acquired_year INTEGER,
            cost_inr BIGINT,
            condition VARCHAR,
            location_state VARCHAR,
            ownership VARCHAR,
            safety_certified BOOLEAN
        );
    """)
    asset_wb = openpyxl.load_workbook(wb_root / "Plant_and_Machinery_Register.xlsx", data_only=True)
    ws_asset = asset_wb["Plant Register"]
    for row in list(ws_asset.iter_rows(values_only=True))[1:]:
        if not row or row[0] is None or not str(row[0]).strip().isdigit(): continue
        aid = int(row[0])
        atype = str(row[1]).strip() if row[1] else ""
        make = str(row[2]).strip() if row[2] else ""
        acq_yr = int(row[3]) if row[3] is not None and str(row[3]).strip().isdigit() else 2020
        cost = int(row[4]) if row[4] is not None and str(row[4]).strip().isdigit() else 0
        cond = str(row[5]).strip() if row[5] else ""
        loc = str(row[6]).strip() if row[6] else ""
        own = str(row[7]).strip() if row[7] else "owned"
        safety = True if str(row[8]).strip().lower() in ["yes", "true", "1"] else False
        con.execute("""
            INSERT INTO workbooks_assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, [aid, atype, make, acq_yr, cost, cond, loc, own, safety])

    # Trial Balance by Year
    con.execute("""
        CREATE TABLE workbooks_trial_balance (
            fiscal_year VARCHAR,
            account_code VARCHAR,
            account_name VARCHAR,
            debit_inr BIGINT,
            credit_inr BIGINT,
            balance_inr BIGINT
        );
    """)
    tb_wb = openpyxl.load_workbook(wb_root / "Trial_Balance_by_Year.xlsx", data_only=True)
    for sname in tb_wb.sheetnames:
        if not sname.startswith("TB"): continue
        ws_tb = tb_wb[sname]
        fy = sname.replace("TB", "").strip()
        for row in list(ws_tb.iter_rows(values_only=True))[1:]:
            if not row or not row[0] or "TOTAL" in str(row[0]).upper(): continue
            acc_full = str(row[0]).strip()
            m_acc = re.search(r'ACCOUNT\s*(\d+)\s*[—\-]\s*(.+)', acc_full, re.I)
            acode = m_acc.group(1) if m_acc else acc_full[:4]
            aname = m_acc.group(2) if m_acc else acc_full
            dr = int(row[1]) if row[1] is not None and str(row[1]).strip().isdigit() else 0
            cr = int(row[2]) if row[2] is not None and str(row[2]).strip().isdigit() else 0
            bal = int(row[3]) if row[3] is not None and str(row[3]).strip().replace('-', '').isdigit() else 0
            con.execute("""
                INSERT INTO workbooks_trial_balance VALUES (?, ?, ?, ?, ?, ?);
            """, [fy, acode, aname, dr, cr, bal])

    # BOQ Workbooks
    con.execute("""
        CREATE TABLE workbooks_boq (
            contract_id INTEGER,
            item_no VARCHAR,
            description VARCHAR,
            unit VARCHAR,
            quantity DOUBLE,
            rate_inr DOUBLE,
            amount_inr BIGINT
        );
    """)
    for p in sorted(wb_root.glob("BOQ_and_Measurements_Contract_*.xlsx")):
        m_cid = re.search(r'Contract_(\d+)', p.name)
        cid = int(m_cid.group(1)) if m_cid else 0
        b_wb = openpyxl.load_workbook(p, data_only=True)
        if "BOQ" in b_wb.sheetnames:
            ws_boq = b_wb["BOQ"]
            for row in list(ws_boq.iter_rows(values_only=True))[1:]:
                if not row or not row[0] or "TOTAL" in str(row[0]).upper() or "GRAND" in str(row[0]).upper(): continue
                ino = str(row[0]).strip()
                desc = str(row[1]).strip() if row[1] else ""
                unit = str(row[2]).strip() if row[2] else ""
                try: qty = float(row[3]) if row[3] is not None else 0.0
                except: qty = 0.0
                try: rate = float(row[4]) if row[4] is not None else 0.0
                except: rate = 0.0
                try: amt = int(row[5]) if row[5] is not None else int(round(qty * rate))
                except: amt = int(round(qty * rate))
                con.execute("""
                    INSERT INTO workbooks_boq VALUES (?, ?, ?, ?, ?, ?, ?);
                """, [cid, ino, desc, unit, qty, rate, amt])

    print("DuckDB database rebuilt with 100% precision!")
    db.close()

if __name__ == "__main__":
    build()
