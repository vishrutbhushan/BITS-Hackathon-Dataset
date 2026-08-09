#!/usr/bin/env python3
"""
Triage script: for every PDF in the corpus, classify each page as
"native" (text layer extractable) or "image" (needs OCR).

Usage:
    pip install pdfplumber --break-system-packages   # if not already installed
    python triage_pdfs.py --index document_index.csv --root /path/to/documents_parent

Notes:
- `document_index.csv` has a `filename` column like
  "annual_report/DOC-AR-2024.pdf" — this is relative to wherever your
  `documents/` folder's *parent* lives. Point --root at that parent dir,
  or just --root the `documents/` folder directly and drop the leading
  segment if your paths already include it. Adjust ROOT_JOIN below if
  your layout differs.
- Threshold-based classification, not perfect. The goal is triage, not
  ground truth: run this, skim the borderline docs by hand, then decide
  whether the threshold needs tightening for your corpus.
"""

import argparse
import csv
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("Missing dependency. Run: pip install pdfplumber --break-system-packages")

# A page with fewer than this many non-whitespace characters of extracted
# text is treated as having no usable text layer (i.e. image-based).
# Certificates/letters are usually a few hundred+ chars per page even when
# sparse, so this catches genuinely blank/scanned pages without flagging
# short-but-real pages. Tune after eyeballing your own results.
MIN_CHARS_FOR_NATIVE = 40


def classify_pdf(path: Path):
    """Return (total_pages, native_pages, image_pages, error_or_None)."""
    try:
        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
            native = 0
            image = 0
            for page in pdf.pages:
                text = page.extract_text() or ""
                if len(text.strip()) >= MIN_CHARS_FOR_NATIVE:
                    native += 1
                else:
                    image += 1
            return total, native, image, None
    except Exception as e:
        return 0, 0, 0, str(e)


def doc_classification(total, native, image):
    if total == 0:
        return "error"
    if image == 0:
        return "native"
    if native == 0:
        return "image"
    return "mixed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, help="path to document_index.csv")
    ap.add_argument("--root", required=True, help="parent directory containing the documents/ tree")
    ap.add_argument("--out", default="triage_report.csv", help="output CSV path")
    args = ap.parse_args()

    root = Path(args.root)
    rows = []
    with open(args.index, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        entries = list(reader)

    print(f"Triaging {len(entries)} documents...")
    for i, row in enumerate(entries, 1):
        doc_id = row["doc_id"]
        doc_type = row["doc_type"]
        filename = row["filename"]

        if filename.lower().endswith((".xlsx", ".xls")):
            rows.append({
                "doc_id": doc_id, "doc_type": doc_type, "filename": filename,
                "total_pages": "", "native_pages": "", "image_pages": "",
                "classification": "workbook_skip", "error": "",
            })
            continue

        pdf_path = root / filename
        if not pdf_path.exists():
            rows.append({
                "doc_id": doc_id, "doc_type": doc_type, "filename": filename,
                "total_pages": "", "native_pages": "", "image_pages": "",
                "classification": "file_not_found", "error": "",
            })
            continue

        total, native, image, err = classify_pdf(pdf_path)
        rows.append({
            "doc_id": doc_id, "doc_type": doc_type, "filename": filename,
            "total_pages": total, "native_pages": native, "image_pages": image,
            "classification": doc_classification(total, native, image),
            "error": err or "",
        })

        if i % 50 == 0:
            print(f"  ...{i}/{len(entries)}")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "doc_id", "doc_type", "filename", "total_pages",
            "native_pages", "image_pages", "classification", "error",
        ])
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    by_class = {}
    by_type_image_pages = {}
    total_pages_all = native_pages_all = image_pages_all = 0
    for r in rows:
        by_class[r["classification"]] = by_class.get(r["classification"], 0) + 1
        if isinstance(r["total_pages"], int):
            total_pages_all += r["total_pages"]
            native_pages_all += r["native_pages"]
            image_pages_all += r["image_pages"]
        if r["image_pages"] and isinstance(r["image_pages"], int) and r["image_pages"] > 0:
            by_type_image_pages[r["doc_type"]] = by_type_image_pages.get(r["doc_type"], 0) + r["image_pages"]

    print("\n=== Document-level classification ===")
    for cls, count in sorted(by_class.items(), key=lambda x: -x[1]):
        print(f"  {cls:16s} {count}")

    print(f"\n=== Page-level totals ===")
    print(f"  total pages:  {total_pages_all}")
    print(f"  native pages: {native_pages_all}")
    print(f"  image pages:  {image_pages_all}")
    if total_pages_all:
        pct = 100 * image_pages_all / total_pages_all
        print(f"  -> {pct:.1f}% of pages need OCR")

    if by_type_image_pages:
        print(f"\n=== Image pages by doc_type (where OCR effort concentrates) ===")
        for dt, cnt in sorted(by_type_image_pages.items(), key=lambda x: -x[1]):
            print(f"  {dt:32s} {cnt}")

    print(f"\nFull report written to {args.out}")


if __name__ == "__main__":
    main()