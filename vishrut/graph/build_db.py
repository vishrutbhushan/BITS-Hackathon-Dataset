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
        
    completion_certificates = []
    reference_letters = []
    personnel_certs = []
    cvs = []
    
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
        
        if doc_type == "completion_certificate":
            # Map client_raw to client_name as expected by build_graph
            extracted["client_name"] = extracted.get("client_raw")
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
