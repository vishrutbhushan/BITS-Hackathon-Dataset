#!/usr/bin/env python3
import os
import sys
import csv
from pathlib import Path

# Add the parent directory of this script to the python path so imports work
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir.parent))

from db.schema import get_connection
from graph.build_graph import build_graph
from extraction import field_extractors

WORKSPACE_ROOT = current_dir.parent.parent
EXTRACTED_TEXT_ROOT = WORKSPACE_ROOT / "extracted_text"
INDEX_CSV = WORKSPACE_ROOT / "document_index.csv"

import re

def run_build(db_path="graph.sqlite"):
    print(f"Building SQLite database at: {db_path}")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    con = get_connection(db_path)
    
    # Read the document index to map doc_id to doc_type
    if not INDEX_CSV.exists():
        print(f"Error: document_index.csv not found at {INDEX_CSV}")
        return
        
    with open(INDEX_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        doc_entries = list(reader)
        
    # 1. Parse past performance portfolio to get project roles
    print("Extracting project roles from past_performance_portfolio...")
    ppp_path = WORKSPACE_ROOT / "documents" / "past_performance_portfolio" / "DOC-PPP-001.pdf"
    role_by_pkg = {}
    if ppp_path.exists():
        import fitz
        try:
            doc = fitz.open(ppp_path)
            pages_text = []
            for idx in range(12, len(doc)):
                pages_text.append(doc[idx].get_text())
            text = '\n' + '\n'.join(pages_text)
            doc.close()
            
            parts = re.split(r'\n\d+\.\s+', text)
            for p in parts[1:]:
                lines = [line.strip() for line in p.split('\n') if line.strip()]
                if len(lines) < 5:
                    continue
                proj_name = lines[0]
                pkg_match = re.search(r'\b[Pp][Kk][Gg]-(\d+)\b', proj_name)
                if not pkg_match:
                    continue
                pkg_num = int(pkg_match.group(1))
                
                client = ""
                for i, line in enumerate(lines):
                    if line.lower() == "client" and i + 1 < len(lines):
                        client = lines[i+1]
                        break
                
                m_role = re.search(r'\((Prime|Subcontractor|JV|Joint Venture|JV Partner)\)', client, re.I)
                role = "Prime"
                if m_role:
                    r_matched = m_role.group(1).lower()
                    if "prime" in r_matched:
                        role = "Prime"
                    elif "subcontractor" in r_matched:
                        role = "Subcontractor"
                    elif "jv" in r_matched or "joint" in r_matched:
                        role = "JV Partner"
                role_by_pkg[pkg_num] = role
        except Exception as e:
            print(f"Error parsing PPP: {e}")

    # 2. Parse client completion certificates to get grading by package number
    print("Extracting gradings from completion_certificates...")
    grading_by_pkg = {}
    for entry in doc_entries:
        if entry["doc_type"] == "completion_certificate":
            doc_id = entry["doc_id"]
            m_file = re.search(r'DOC-CC-(\d+)', doc_id)
            if not m_file:
                continue
            pkg_num = int(m_file.group(1))
            
            pdf_path = WORKSPACE_ROOT / "documents" / entry["filename"]
            text = ""
            if pdf_path.exists():
                import fitz
                try:
                    doc = fitz.open(pdf_path)
                    text = "\n".join([page.get_text() for page in doc])
                    doc.close()
                except Exception as e:
                    pass
            if not text:
                txt_path = EXTRACTED_TEXT_ROOT / "completion_certificate" / f"{doc_id}.txt"
                if txt_path.exists():
                    text = txt_path.read_text(encoding="utf-8")
            if text:
                from parsers.grading import normalize_grading
                grading_by_pkg[pkg_num] = normalize_grading(text)

    completion_certificates = []
    reference_letters = []
    personnel_certs = []
    cvs = []
    
    print("Processing all documents...")
    for entry in doc_entries:
        doc_id = entry["doc_id"]
        doc_type = entry["doc_type"]
        
        # We only process types that have extractors
        if doc_type not in field_extractors.EXTRACTORS:
            continue
            
        pdf_path = WORKSPACE_ROOT / "documents" / entry["filename"]
        text = ""
        if pdf_path.exists():
            import fitz
            try:
                doc = fitz.open(pdf_path)
                text = "\n".join([page.get_text() for page in doc])
                doc.close()
            except Exception as e:
                print(f"Error reading PDF {pdf_path}: {e}")
        
        if not text:
            txt_path = EXTRACTED_TEXT_ROOT / doc_type / f"{doc_id}.txt"
            if txt_path.exists():
                text = txt_path.read_text(encoding="utf-8")
            else:
                continue
                
        extracted = field_extractors.extract(doc_type, text)
        extracted["doc_id"] = doc_id
        
        if doc_type == "company_completion_certificate":
            m_file = re.search(r'DOC-CCC-(\d+)', doc_id)
            if not m_file:
                continue
            pkg_num = int(m_file.group(1))
            
            # Enrich with pre-computed roles and gradings
            extracted["role"] = role_by_pkg.get(pkg_num, "Prime")
            extracted["grading"] = grading_by_pkg.get(pkg_num)
            completion_certificates.append(extracted)
        elif doc_type == "reference_letter":
            reference_letters.append(extracted)
        elif doc_type == "personnel_certificate":
            personnel_certs.append(extracted)
        elif doc_type == "cv":
            cvs.append(extracted)
            
    build_graph(con, completion_certificates, reference_letters, personnel_certs, cvs)
    con.close()
    print("Database built successfully!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="graph.sqlite", help="Output database file path")
    args = parser.parse_args()
    run_build(args.db)
