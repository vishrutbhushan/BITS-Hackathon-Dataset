# Table Extraction & Structural Analysis Report
**Corpus**: National Infrastructure Corp. Ltd. Document Estate
**Scope**: Identification of table structures across 678 PDFs and 9 Excel workbooks, merged cell handling, multi-page tables, and spreadsheet formula resolution.

---

## 1. Table Prevalence Across Document Types

| Document Type | Total Documents | Total Tables Found | Tables Per Doc | Merged Cells | Multi-Page Tables | Structure Type |
|---|---|---|---|---|---|---|
| `completion_certificate` | 155 | 234 | 1.5 | Low | No (1–2 pp) | Evaluation Parameter Grids |
| `company_completion_certificate` | 155 | 395 | 2.5 | None | No | 2-Column Key-Value Grids |
| `reference_letter` | 132 | 120 | 0.9 | None | No | Rating / Criterion Tables |
| `performance_bond` | 60 | 51 | 0.8 | None | No | Guarantee Summary Tables |
| `personnel_certificate` | 48 | 48 | 1.0 | None | No | Credential Attributes Table |
| `cv` | 39 | 156 | 4.0 | Medium | Yes (2 pp) | Competency & Track Record Grids |
| `compliance_matrix` | 40 | 40 | 1.0 | None | No | 4-Column Checklist Grid |
| `general_ledger_book` | 8 | 371 | 46.4 | Low | **Yes (up to 72 pp)** | 5-Column High-Density GL Table |
| `bank_statement` | 8 | 36 | 4.5 | None | Yes (2–7 pp) | 5-Column Account Statement Table |
| `financial_statement` | 7 | 20 | 2.9 | Medium | No (3 pp) | Multi-column P&L / Balance Sheet |
| `ra_bill` & `final_ra_bill` | 12 | 84 | 7.0 | High | **Yes (up to 24 pp)** | BOQ Measurement Schedule |
| `tender_dossier` | 6 | 288 | 48.0 | Medium | **Yes (48 pp)** | Annexure Schedules |
| `workbooks` (.xlsx) | 9 | 30 | 3.3 | High | Multi-sheet | Live Formulas & Measurements |

---

## 2. Table Parsing Strategy & Library Comparison

### Multi-Page High-Density Tables (`general_ledger_book`, `final_ra_bill`)
- **Challenge**: Ledger books span up to 72 consecutive pages with running account headers and repeating table headers (`DATE`, `VOUCHER / NARRATION`, `DEBIT`, `CREDIT`, `BALANCE`).
- **Solution**: Use `PyMuPDF.Page.find_tables()` with bounding box clipping or monospaced line parsing. Maintain account state across page transitions.

### Excel Workbooks with Live Formulas (`BOQ_and_Measurements_Contract_*.xlsx`)
- **Challenge**: 6 BOQ workbooks contain live formulas (`=SUM(F2:F20)`, `=D2*E2`) and `Notes` sheets.
- **Solution**: Load workbooks with `openpyxl.load_workbook(data_only=False)` to inspect formula definitions, and `data_only=True` to retrieve cached computed values.

---

## 3. Recommended Table Extraction Pipeline

```python
import fitz # PyMuPDF

def extract_tables_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    extracted_tables = []
    for pno, page in enumerate(doc):
        tabs = page.find_tables()
        for tab in tabs:
            df = tab.extract()
            if df and len(df) > 1:
                extracted_tables.append({
                    'page': pno + 1,
                    'headers': df[0],
                    'rows': df[1:]
                })
    doc.close()
    return extracted_tables
```
