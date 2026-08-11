# Document Format Variability & Layout Diversity Report
**Corpus**: National Infrastructure Corp. Ltd. Enterprise Estate (687 documents, 20 types)
**Objective**: Comprehensive quantification of layout diversity, header polymorphism, field label aliases, page count variances, and formatting shifts across all 20 document types.

---

## 1. Executive Summary & Variability Taxonomy

Across the 687 documents, formatting diversity follows three distinct architectural tiers:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 ESTATE VARIABILITY CLASSIFICATION                                │
├────────────────────────────────┬────────────────────────────────┬────────────────────────────────┤
│ 🔴 HIGH VARIABILITY (3 Types)  │ 🟡 MEDIUM VARIABILITY (5 Types)│ 🟢 LOW / STANDARDIZED (12 Types│
│ (Multi-Client / Shifting Eras) │ (Dual-Template / Multi-Bank)   │ (Strict Corporate Schemas)     │
├────────────────────────────────┼────────────────────────────────┼────────────────────────────────┤
│ • completion_certificate       │ • company_completion_cert      │ • past_performance_portfolio  │
│   (117 distinct client headers)│   (2 internal template styles) │ • cv (Uniform 2-page template) │
│ • financial_statement          │ • reference_letter             │ • personnel_certificate        │
│   (Shifting accounting eras)   │   (101 client letterheads)     │ • compliance_matrix            │
│ • general_ledger_book          │ • performance_bond             │ • tender_dossier (48-page book)│
│   (9 to 72 pages per volume)   │   (36 bank header styles)      │ • iso_certificate              │
│                                │ • final_ra_bill                │ • annual_report (18-page book) │
│                                │   (14 to 24 multi-page BOQs)   │ • ra_bill (1-page abstract)    │
│                                │ • annual_report                │ • 4 Excel Workbooks (.xlsx)    │
└────────────────────────────────┴────────────────────────────────┴────────────────────────────────┘
```

---

## 2. Exhaustive Per-Document-Type Format Variability Matrix

| Document Type | Total Files | Variability Tier | Page Count Range | Word Count Range | Distinct Header Templates | Primary Structural Variants | Field Label Polymorphism | Conflicting Currency Formats | Date Formats Observed |
|---|---|---|---|---|---|---|---|---|---|
| `completion_certificate` | 155 | **High** | 1 – 3 pp (avg 1.9) | 133 – 704 w (avg 430.0) | **117** | 3 Layouts: Tabular Grid, Prose Narrative, Mixed Form | `Work`, `Name of Work`, `Scope of Work`, `Contract Value`, `Gross Executed Value` | `INR XX.XX Cr` (57), `XX.XX Lakh` (53), `INR XX,XX,XX,XXX/-` (37) | `YYYY-MM-DD` (102), `DD/MM/YYYY` (54), `DD Mon YYYY` (41), `Month DD, YYYY` (24) |
| `company_completion_certificate` | 155 | **Medium** | 1 – 2 pp (avg 1.5) | 72 – 431 w (avg 249.1) | 4 | **2 Core Templates**: Variant 1 (1-page table), Variant 2 (2-page multi-section) | `Work`, `Project Name`, `Project Particulars`, `Executed Value`, `Contract Value` | `INR XX.XX Cr` (111), `Raw Integer` (44) | `DD/MM/YYYY` (155), `YYYY-MM-DD` (80) |
| `reference_letter` | 132 | **Medium** | 1 – 2 pp (avg 1.3) | 82 – 307 w (avg 172.0) | **101** | 2 Layouts: Client Letterhead Narrative vs 3-Column Criterion Rating Grid | `Work`, `Project Name`, `Scope of Work`, `Contract Value`, `Assessment` | `INR XX.XX Cr` (51), `XX.XX Lakh` (44), `INR XX,XX,XX,XXX/-` (29) | `YYYY-MM-DD` (63), `DD/MM/YYYY` (48), `DD Mon YYYY` (36), `Month DD, YYYY` (19) |
| `performance_bond` | 60 | **Medium** | 1 – 3 pp (avg 1.9) | 132 – 527 w (avg 313.7) | 36 | Bank-specific covenant layouts (Kalinga Bank vs Union Trust Bank) | `Employer`, `Department`, `Work`, `Contract Value`, `Guarantee Value` | `Raw Integer` (60), `XX.XX Lakh` (19), `INR XX.XX Cr` (9) | `DD Mon YYYY` (50), `YYYY-MM-DD` (28), `Month DD, YYYY` (10) |
| `financial_statement` | 7 | **High** | Exactly 3 pp | 548 – 549 w (avg 548.4) | 3 | **3 Era Layouts**: FY18-20, FY21-23, FY24-25 shifting schedule rows | `Contract Revenue (EPC)`, `PBT`, `Materials Consumed`, `Turnover` | **Denominated in Lakhs** (Requires $	imes 100,000$ multiplier) | `DD/MM/YYYY` (5), `YYYY-MM-DD` (2) |
| `general_ledger_book` | 8 | **High** | **9 – 72 pp** (avg 47.4) | 964 – 10,909 w (avg 6,635.8) | 8 | Monospaced multi-page journal tables; page volume scales with transaction count | `ACCOUNT XXXX`, `VOUCHER / NARRATION`, `DEBIT`, `CREDIT`, `BALANCE` | Exact Lossless Integer INR | `YYYY-MM-DD` (100%) |
| `final_ra_bill` | 6 | **Medium** | **14 – 24 pp** (avg 19.2) | 2,770 – 5,425 w (avg 4,106.5) | 1 | Part I Contract Abstract + Part II Multi-page BOQ Executed Table | `Awarded Value`, `Executed Value`, `Item No`, `Description`, `Executed Qty` | `INR XX.XX Cr` (6), `Table INR` (6) | `YYYY-MM-DD` (6), `Month DD, YYYY` (6) |
| `personnel_certificate` | 48 | **Low** | Exactly 1 pp | 46 – 141 w (avg 97.3) | 4 | Authority-specific certificate borders (PMI PMP vs Six Sigma ISSC) | `Credential Type`, `Credential ID`, `Date of Issue`, `Valid Through`, `Holder` | N/A (Non-monetary) | `YYYY-MM-DD` (28), `DD Mon YYYY` (16), `DD/MM/YYYY` (4) |
| `cv` | 39 | **Low** | Exactly 2 pp | 277 – 282 w (avg 280.1) | 1 | **100% Uniform Corporate Template**: Personal Header, Competencies, Projects Led | `Name`, `Employee ID`, `Designation`, `Business Unit`, `Experience`, `Projects` | N/A | `YYYY-MM-DD` (39), `Month DD, YYYY` (39) |
| `compliance_matrix` | 40 | **Low** | 1 – 2 pp (avg 1.5) | 131 – 346 w (avg 229.5) | 2 | Standard 4-Column Table (`#`, `Requirement`, `Status`, `Evidence`) | `ISO 9001:2015`, `Turnover Requirement`, `Key Technical Staff`, `EMD` | `Rs. 150 Cr`, `Rs. 180 Cr` | `Month DD, YYYY` (40), `YYYY-MM-DD` (19) |
| `ra_bill` | 6 | **Low** | Exactly 1 pp | 148 – 163 w (avg 153.8) | 2 | 1-page interim billing abstract with GST @18% and Retention @5% | `Bill No`, `Contract #`, `Value of work done`, `Net claimed` | Table Integer INR | `Month DD, YYYY` (6) |
| `tender_dossier` | 6 | **Low** | Exactly 48 pp | 8,267 – 8,317 w (avg 8,293.7) | 6 | Standard 48-page tender book with Annexures A through H | `Bid Value`, `Tender Ref`, `Annexures A-H`, `48 Past Works` | `INR XX.XX Cr` | `Month DD, YYYY` (6) |
| `iso_certificate` | 5 | **Low** | Exactly 2 pp | 252 – 257 w (avg 255.4) | 4 | Page 1 Certificate + Page 2 Audit Schedule | `Certificate No`, `ISO Standard`, `Valid Until`, `Certification Body` | N/A | `YYYY-MM-DD` (5) |
| `annual_report` | 2 | **Low** | Exactly 18 pp | 3,570 – 3,581 w (avg 3,575.5) | 2 | Standard Corporate Report: Directors' Report, Governance, Accounts | `Directors`, `Corporate Info`, `Auditors`, `Financial Extracts` | Denominated in Lakhs | `DD/MM/YYYY`, `YYYY-MM-DD` |
| `past_performance_portfolio`| 1 | **Low** | Exactly 64 pp | 8,977 w | 1 | Master 155-work catalog with numbered blocks #1 through #155 | `Work`, `Client`, `Category`, `Executed Value`, `Completed Date` | `INR XX.XX Cr` (155 works) | `Month DD, YYYY` (155 works) |
| `boq_workbook` (.xlsx) | 6 | **Low** | Exactly 3 sheets | ~1,000 w | 1 | Standard 3-sheet schema: `BOQ`, `Measurements`, `Notes` | `Item No`, `Description`, `Unit`, `Quantity`, `Rate (INR)`, `Amount (INR)` | Unformatted Integer INR | `YYYY-MM-DD` |
| `ageing_workbook` (.xlsx) | 1 | **Low** | Exactly 2 sheets | ~5,178 w | 1 | Standard 2-sheet schema: `AR Ageing`, `Notes` | `Invoice No`, `Client`, `Invoice Date`, `Invoiced (INR)`, `Status`, `Received` | Unformatted Integer INR | `YYYY-MM-DD` |
| `asset_register_workbook` (.xlsx)| 1 | **Low** | Exactly 2 sheets | ~2,596 w | 1 | Standard 2-sheet schema: `Plant Register`, `Notes` | `Asset ID`, `Type`, `Make`, `Acquired`, `Cost (INR)`, `Condition`, `Location` | Unformatted Integer INR | `YYYY` (Year) |
| `trial_balance_workbook` (.xlsx)| 1 | **Low** | Exactly 8 sheets | ~1,334 w | 1 | 8 FY sheets (`TB 2018-19` to `TB 2024-25`) | `Account`, `Debit (INR)`, `Credit (INR)`, `Balance (INR)` | Unformatted Integer INR | `YYYY-YY` (Fiscal Year) |

---

## 3. Deep Dive into High-Variability Document Types

### 1. `completion_certificate` (Highest Variability in Corpus)
- **Why It Varies**: Issued by **62 different client organizations** over a 15-year span (2010–2025). Each government department or private developer used its own localized letterhead, section ordering, field labels, and currency notation.
- **Header Polymorphism**: **117 distinct header variations** found across 155 files.
- **Field Name Diversity**:
  * Project Name: `Work`, `Name of Work`, `Project Name`, `Scope of Work`, `Captioned Work`
  * Contract Value: `Contract Value`, `Gross Executed Value`, `Contract Value (Original)`, `Final Executed Amount`, `Awarded Value`
  * Completion Date: `Date of Physical Completion`, `Completion Date`, `Completed in all respects on`, `Finished on`
- **Monetary Notation Co-existence**:
  * 57 certificates use `INR XX.XX Cr`
  * 53 certificates use `XX.XX Lakh`
  * 37 certificates use Indian comma format `INR XX,XX,XX,XXX/-`
- **Prose Rating Extraction Strategy**:
  Because there is no standard "Grading" box, ratings are parsed via regular expression sentiment scanning across the body sentences:
  $$	ext{Grade} \in \{	ext{"Outstanding"}, 	ext{"Excellent"}, 	ext{"Very Good"}, 	ext{"Satisfactory"}, 	ext{"Good"}, 	ext{"Fair"}, 	ext{"Poor"}\}$$

---

### 2. `company_completion_certificate` (Dual Internal Templates)
- **Why It Varies**: National Infrastructure Corp. Ltd. modernized its internal certificate template in mid-stream:
  * **Template 1: "RECORD OF WORK COMPLETED" (75 files)**:
    * Compact 1-page format (72–100 words).
    * Single 2-column key-value table: `Work`, `Client`, `Category`, `Executed Value`, `Completion`, `Project Lead`, `Client Certificate Ref`.
  * **Template 2: "PROJECT COMPLETION CERTIFICATE" (80 files)**:
    * Comprehensive 2-page multi-tier format (400–431 words).
    * 5 distinct sections: `1. PROJECT PARTICULARS`, `2. DECLARATION OF COMPLETION` (contains prose rating), `3. COMPLIANCE SUMMARY`, `4. MILESTONE SUMMARY`, `5. DEFECT LIABILITY PERIOD`.

---

### 3. `financial_statement` (Era-Shifted Reporting Templates)
- **Why It Varies**: Corporate reporting layouts evolved across three distinct accounting eras:
  * **Era 1 (FY 2018–19 to FY 2019–20)**: Condensed 3-part layout (`A. Revenue from Operations`, `B. Expenses`, `C. Profit Before Tax`).
  * **Era 2 (FY 2020–21 to FY 2022–23)**: Expanded schedule layout including sub-contracting and separate depreciation schedules.
  * **Era 3 (FY 2023–24 to FY 2024–25)**: Modernized statutory format with explicit note references and tax adjustments.
- **Critical Scaling Factor**: In all 7 statements, values are denominated in **Lakhs** (must be multiplied by $100,000$ to obtain base INR).

---

## 4. Extraction Architecture Strategy for Format Variability

To achieve **100% extraction resilience** across all variability levels, the extraction engine utilizes a **Multi-Anchor Triangulation Pattern**:

```python
def extract_project_fields_with_fallback(text: str) -> dict:
    # 1. Title Extraction with 4-way Anchor Fallback
    m_title = re.search(r'(?:Work|Project Name|Name of Work|Captioned Work)\s*[:
]\s*([^
]+)', text, re.IGNORECASE)
    
    # 2. Package Extraction via Universal Regex
    m_pkg = re.search(r'Pkg-(\d+)|Package (\d+)', text, re.IGNORECASE)
    
    # 3. Monetary Extraction with 4-Format Support
    val_inr = None
    m_cr = re.search(r'(?:INR|Rs\.?|₹)?\s*([\d.]+)\s*(?:Cr|crore)', text, re.IGNORECASE)
    if m_cr:
        val_inr = int(round(float(m_cr.group(1)) * 10_000_000))
    else:
        m_lakh = re.search(r'(?:INR|Rs\.?|₹)?\s*([\d.]+)\s*(?:Lakh|lakhs)', text, re.IGNORECASE)
        if m_lakh:
            val_inr = int(round(float(m_lakh.group(1)) * 100_000))
        else:
            m_inr = re.search(r'INR\s*([\d,]{8,})', text)
            if m_inr:
                val_inr = int(m_inr.group(1).replace(',', ''))
                
    # 4. Date Extraction with Multi-Pattern Parser
    comp_date = parse_multi_format_date(text)
    
    # 5. Prose Judgment Extraction
    grade = extract_prose_grade(text)
    
    return {
        "title": m_title.group(1).strip() if m_title else None,
        "pkg_id": int(m_pkg.group(1) or m_pkg.group(2)) if m_pkg else None,
        "contract_value_inr": val_inr,
        "completion_date": comp_date,
        "grading": grade
    }
```
