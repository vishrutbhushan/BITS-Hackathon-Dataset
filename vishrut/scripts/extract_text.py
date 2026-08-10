#!/usr/bin/env python3
"""
Stage 0: extract raw plain text from every PDF. No OCR (assumes native
text layers, per your triage). No normalization of any kind.

Usage:
    pip install pdfplumber --break-system-packages
    python extract_text.py --index document_index.csv --root /path/to/parent/of/documents --out extracted_text
"""
import argparse
import csv
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("Missing dependency. Run: pip install pdfplumber --break-system-packages")


def extract_pdf_text(pdf_path: Path) -> str:
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text(layout=True) or ""
            pages_text.append(f"--- page {i} ---\n{text}")
    return "\n\n".join(pages_text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", default="extracted_text")
    ap.add_argument("--log", default="extraction_log.csv")
    args = ap.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(args.index, newline="", encoding="utf-8") as f:
        entries = list(csv.DictReader(f))

    print(f"Extracting text from {len(entries)} indexed documents...")
    log_rows = []
    for i, row in enumerate(entries, 1):
        doc_id, doc_type, filename = row["doc_id"], row["doc_type"], row["filename"]
        if filename.lower().endswith((".xlsx", ".xls")):
            log_rows.append({"doc_id": doc_id, "doc_type": doc_type, "filename": filename,
                             "status": "skipped_workbook", "chars": 0})
            continue
        pdf_path = root / filename
        if not pdf_path.exists():
            log_rows.append({"doc_id": doc_id, "doc_type": doc_type, "filename": filename,
                             "status": "file_not_found", "chars": 0})
            continue
        try:
            text = extract_pdf_text(pdf_path)
        except Exception as e:
            log_rows.append({"doc_id": doc_id, "doc_type": doc_type, "filename": filename,
                             "status": f"error: {e}", "chars": 0})
            continue
        type_dir = out_dir / doc_type
        type_dir.mkdir(parents=True, exist_ok=True)
        out_path = type_dir / f"{doc_id}.txt"
        out_path.write_text(text, encoding="utf-8")
        stripped_len = len(text.strip())
        status = "ok" if stripped_len >= 40 else "near_empty"
        log_rows.append({"doc_id": doc_id, "doc_type": doc_type, "filename": filename,
                         "status": status, "chars": stripped_len})
        if i % 50 == 0:
            print(f"  ...{i}/{len(entries)}")

    with open(args.log, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["doc_id", "doc_type", "filename", "status", "chars"])
        writer.writeheader()
        writer.writerows(log_rows)

    by_status = {}
    for r in log_rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print("\n=== Extraction summary ===")
    for status, count in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  {status:20s} {count}")
    print(f"\nText files written under: {out_dir}/<doc_type>/<doc_id>.txt")
    print(f"Log written to: {args.log}")


if __name__ == "__main__":
    main()
