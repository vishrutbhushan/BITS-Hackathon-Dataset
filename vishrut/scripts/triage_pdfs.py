#!/usr/bin/env python3
"""
Triage script: for every PDF in the corpus, classify each page as
"native" (text layer extractable) or "image" (needs OCR).

Usage:
    pip install pdfplumber --break-system-packages   # if not already installed
    python triage_pdfs.py --index document_index.csv --root /path/to/documents_parent
"""
import argparse
import csv
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("Missing dependency. Run: pip install pdfplumber --break-system-packages")

MIN_CHARS_FOR_NATIVE = 40


def classify_pdf(path: Path):
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
    ap.add_argument("--index", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", default="triage_report.csv")
    args = ap.parse_args()

    root = Path(args.root)
    rows = []
    with open(args.index, newline="", encoding="utf-8") as f:
        entries = list(csv.DictReader(f))

    print(f"Triaging {len(entries)} documents...")
    for i, row in enumerate(entries, 1):
        doc_id, doc_type, filename = row["doc_id"], row["doc_type"], row["filename"]
        if filename.lower().endswith((".xlsx", ".xls")):
            rows.append({"doc_id": doc_id, "doc_type": doc_type, "filename": filename,
                         "total_pages": "", "native_pages": "", "image_pages": "",
                         "classification": "workbook_skip", "error": ""})
            continue
        pdf_path = root / filename
        if not pdf_path.exists():
            rows.append({"doc_id": doc_id, "doc_type": doc_type, "filename": filename,
                         "total_pages": "", "native_pages": "", "image_pages": "",
                         "classification": "file_not_found", "error": ""})
            continue
        total, native, image, err = classify_pdf(pdf_path)
        rows.append({"doc_id": doc_id, "doc_type": doc_type, "filename": filename,
                     "total_pages": total, "native_pages": native, "image_pages": image,
                     "classification": doc_classification(total, native, image), "error": err or ""})
        if i % 50 == 0:
            print(f"  ...{i}/{len(entries)}")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["doc_id", "doc_type", "filename", "total_pages",
                                                 "native_pages", "image_pages", "classification", "error"])
        writer.writeheader()
        writer.writerows(rows)

    by_class = {}
    total_pages_all = native_pages_all = image_pages_all = 0
    for r in rows:
        by_class[r["classification"]] = by_class.get(r["classification"], 0) + 1
        if isinstance(r["total_pages"], int):
            total_pages_all += r["total_pages"]
            native_pages_all += r["native_pages"]
            image_pages_all += r["image_pages"]

    print("\n=== Document-level classification ===")
    for cls, count in sorted(by_class.items(), key=lambda x: -x[1]):
        print(f"  {cls:16s} {count}")
    print(f"\n=== Page-level totals ===")
    print(f"  total pages:  {total_pages_all}")
    print(f"  native pages: {native_pages_all}")
    print(f"  image pages:  {image_pages_all}")
    if total_pages_all:
        print(f"  -> {100 * image_pages_all / total_pages_all:.1f}% of pages need OCR")
    print(f"\nFull report written to {args.out}")


if __name__ == "__main__":
    main()
