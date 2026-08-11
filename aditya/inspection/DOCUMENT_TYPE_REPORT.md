# Document Type Deep Inspection Report
**Corpus**: National Infrastructure Corp. Ltd. Document Estate
**Total Documents**: 687 files | **Document Types**: 20 distinct types (17 subdirectories) | **Format Distribution**: 678 PDFs, 9 XLSX Workbooks

---

## Executive Summary of Document Estate Types

| Type Identifier | Total Docs | File Format | Avg Pages | Layout Paradigm | Text Source | Extraction Complexity | Primary Role in Reasoning |
|---|---|---|---|---|---|---|---|
| `completion_certificate` | 155 | PDF | 1.9 | Hybrid Key-Value / Prose / Grid | Digital Vector | High (Prose Judgments) | Client sign-off, final value, completion date, qualitative grading |
| `company_completion_certificate` | 155 | PDF | 1.5 | Structured Key-Value Table | Digital Vector | Low-Medium | Internal project record, project lead engineer, category |
| `reference_letter` | 132 | PDF | 1.3 | Formal Recommendation Letter | Digital Vector | Medium | Client testimonial, positive verification (missingness detection) |
| `performance_bond` | 60 | PDF | 1.9 | Legal Stamp Paper / Guarantee Form | Digital Vector | Medium | Bank guarantees, bond numbers, issuing banks, RFP links |
| `personnel_certificate` | 48 | PDF | 1.0 | Formal Credential Certificate | Digital Vector | Low | PMP / Six Sigma credentials, credential IDs, issue dates |
| `cv` | 39 | PDF | 2.0 | Standardized Technical Resume | Digital Vector | Medium | Project lead history, experience, business unit, designations |
| `compliance_matrix` | 40 | PDF | 1.5 | Tender Checklist Grid | Digital Vector | Low | ISO mappings, turnover compliance, key personnel counts |
| `general_ledger_book` | 8 | PDF | 47.4 | Multi-page Financial Journal Grid | Digital Vector | High | Double-entry journal lines, voucher narrations, bank reconciliation |
| `bank_statement` | 8 | PDF | 4.5 | Bank Account Ledger Table | Digital Vector | Medium | Monthly cash flows, deposit receipts, withdrawal tracking |
| `financial_statement` | 7 | PDF | 3.0 | Statutory P&L and Balance Sheet | Digital Vector | High (Era Shifts) | Annual turnover, profit before tax, revenue breakdown |
| `ra_bill` | 6 | PDF | 1.0 | Running Account Abstract Table | Digital Vector | Medium | Interim billing line items, GST, retention money |
| `final_ra_bill` | 6 | PDF | 19.2 | Multi-page BOQ Executed Table | Digital Vector | High | Final contract abstract, executed quantities, line item amounts |
| `tender_dossier` | 6 | PDF | 48.0 | Comprehensive Bid Submission Book | Digital Vector | High | Past performance annexures, key personnel lists, bid security |
| `iso_certificate` | 5 | PDF | 2.0 | Accredited Quality Certificate | Digital Vector | Low | ISO 9001/14001/45001 registration numbers, audit schedules |
| `annual_report` | 2 | PDF | 18.0 | Corporate Directors' Report | Digital Vector | High | Board members, corporate governance, financial schedules |
| `past_performance_portfolio` | 1 | PDF | 64.0 | Master 155-Work Portfolio Book | Digital Vector | High | Complete roster of 155 works, categories, clients, values |
| `boq_workbook` | 6 | XLSX | 3.0 | Multi-sheet Measurement Sheets | Spreadsheet | Medium | Live formulas, BOQ rate analysis, measured quantities |
| `ageing_workbook` | 1 | XLSX | 2.0 | Receivables Ageing Ledger | Spreadsheet | Low | Invoice payment statuses, outstanding dues, client accounts |
| `asset_register_workbook` | 1 | XLSX | 2.0 | Plant & Machinery Asset Schedule | Spreadsheet | Low | Asset acquisition costs, equipment conditions, state locations |
| `trial_balance_workbook` | 1 | XLSX | 8.0 | Multi-year Trial Balance Schedule | Spreadsheet | Medium | Account-wise debit/credit closing balances by fiscal year |

---

## Exhaustive Per-Type Technical Profiles

### 1. `completion_certificate` (Client Completion Certificate)
- **Purpose**: Official sign-off issued by client government departments/authorities upon substantial completion and commissioning of contract works.
- **Typical Length**: 1 to 3 pages (Average: 1.9 pages).
- **Common Layouts**:
  - *Layout A (Tabular Grid)*: Parameter / Assessment / Remarks table.
  - *Layout B (Prose Certificate)*: 2–3 paragraphs of formal administrative prose embedding the value, date, and grading directly in the text body.
  - *Layout C (Form / Annexure)*: Key-value header block followed by formal officer attestation.
- **Text Density**: Medium-High (~430 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (TrueType fonts: Liberation-Serif, Liberation-Serif-Bold).
- **OCR Quality**: Pristine digital text stream (100% character recovery).
- **Important Fields**:
  - `Project Title / Name`: (e.g., *RCC Bridge — Gujarat Pkg-1*, *Cable Stayed Bridge — Jharkhand Pkg-115*)
  - `Client Name`: (e.g., *National Special Projects Office*, *Jal Nigam, Jharkhand*)
  - `Contract / Executed Value`: (e.g., *INR 33.38 Cr*, *INR 81.44 Cr*)
  - `Completion Date`: (e.g., *06 Feb 2011*, *2021-03-10*)
  - `Performance Grading`: (*Satisfactory*, *Good*, *Very Good*, *Excellent*, *Outstanding*)
- **Optional Fields**: `Defect Liability Period`, `Original Contract Amount`, `Time Overrun / Extension Reasons`, `Officer Designation`.
- **Repeated Phrases**: "has successfully completed the work", "commissioned without defect", "overall performance was found to be", "in accordance with technical specifications".
- **Headers & Footers**: Header has issuing department title, government seal badge; Footer contains issuing office contact, certificate reference ID, and page numbering.
- **Tables**: Present in ~54% of documents. 2-column or 3-column evaluation grids.
- **Signatures & Stamps**: Executive Engineer / Superintending Engineer signature block; official department circular seal.
- **Dates**: Formats include `DD/MM/YYYY`, `YYYY-MM-DD`, `Month DD, YYYY`, `DD Month YYYY`.
- **Money**: Formats include `INR XX.XX Cr`, `XX,XX,XX,XXX`, `XX.XX Lakh`.
- **Identifiers**: Certificate Ref (e.g. `CC/34/2011/001`), Package Number (e.g. `Pkg-115`).
- **Confidence of Extraction**: High (98.5% with regex + layout extractor).
- **Recommended Parser**: PyMuPDF / pdfplumber layout text extraction with sentence-level classification for qualitative grading.
- **Failure Modes**:
  - Client grading embedded in narrative prose (e.g., "...performance was satisfactory in all respects...") rather than a discrete key-value pair.
  - Indian digit formatting variations across 62 distinct client issuing templates.
- **Example Snippet**:
  ```text
  OFFICE OF THE EXECUTIVE ENGINEER
  PUBLIC WORKS DEPARTMENT, GOVT OF GUJARAT
  COMPLETION CERTIFICATE
  This is to certify that M/s National Infrastructure Corp. Ltd. has executed the work
  "Check Dam — Gujarat Pkg-62" against Agreement No. CE/GUJ/62/2014.
  Contract Value: INR 46.73 Cr | Actual Executed Value: INR 46.73 Cr
  Date of Start: 12-04-2014 | Date of Physical Completion: 18-09-2016
  The quality of work executed has been assessed as "Very Good".
  ```
- **Recommended Chunking Strategy**: Single document unit chunking (1–2 pages) with structured JSON metadata extraction.

---

### 2. `company_completion_certificate` (Internal Record of Completion)
- **Purpose**: National Infrastructure Corp. Ltd.'s internal certified project record generated for credential filing, tender submissions, and financial books.
- **Typical Length**: 1 to 2 pages (Average: 1.5 pages).
- **Common Layouts**: Clean, standardized corporate layout with a structured two-column key-value table and sign-off declaration.
- **Text Density**: Medium (~249 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (Liberation-Serif).
- **OCR Quality**: Flawless digital extraction.
- **Important Fields**:
  - `Work / Project Name`: Standardized format `{Title} — {State} Pkg-{N}`
  - `Client`: Client name with category suffix `(government)` or `(private)`
  - `Category`: Vertical domain (*Bridges Flyovers*, *Water Treatment*, *Highways*, *Tunnels*, *Buildings*, *Sewerage Drainage*)
  - `Executed Value`: Standardized INR notation (`INR XX.XX Cr`)
  - `Completion`: Date string
  - `Project Lead / Project Manager`: Name of internal engineer (e.g., *Suresh Desai*, *Meera Roy*, *Asha Nair*)
  - `Client Certificate Ref`: Direct cross-reference to issuing client document
- **Optional Fields**: `Scope of Work`, `Defect Liability Ends`, `Internal Ref` (`CCC/{N}`).
- **Repeated Phrases**: "RECORD OF WORK COMPLETED", "PROJECT COMPLETION CERTIFICATE", "Authorised Signatory", "National Infrastructure Corp. Ltd.".
- **Headers & Footers**: Header with corporate CIN (`U45201WB2005PLC904417`), GSTIN (`19NAICC4417O1Z1`), Salt Lake, Kolkata; Footer has document ID `DOC-CCC-{NNN}`.
- **Tables**: 100% contain structured 2-column key-value tables.
- **Signatures & Stamps**: Corporate seal and Authorised Signatory designation.
- **Dates**: `DD/MM/YYYY` and `YYYY-MM-DD`.
- **Money**: `INR XX.XX Cr` (lossless 2-decimal crore precision).
- **Identifiers**: `Ref: CCC/{N}`, `Client Certificate Ref`.
- **Confidence of Extraction**: Very High (99.9%).
- **Recommended Parser**: PyMuPDF table/text extraction.
- **Failure Modes**: Engineer name formatting variations (e.g., "Project Lead: Suresh Desai" vs "Project Manager: Suresh Desai").
- **Example Snippet**:
  ```text
  National Infrastructure Corp. Ltd.
  RECORD OF WORK COMPLETED
  Internal Ref: CCC/115
  Work: Cable Stayed Bridge — Jharkhand Pkg-115
  Client: Jal Nigam, Jharkhand (government)
  Category: Bridges Flyovers
  Executed Value: INR 81.44 Cr
  Completion: 10/03/2021
  Project Lead: Asha Nair
  Client Certificate Ref: CC/JN/JH/115/2021
  ```
- **Recommended Chunking Strategy**: Single entity record with relational attribute mapping.

---

### 3. `reference_letter` (Client Recommendation Letters)
- **Purpose**: Testimonial letters issued by client executive officers confirming satisfactory contractor performance, milestone adherence, and defects clearance.
- **Typical Length**: 1 to 2 pages (Average: 1.3 pages).
- **Common Layouts**: Formal client letterhead with reference block, project summary line, bulleted assessment criteria, and officer verification details.
- **Text Density**: Medium-Low (~172 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (DejaVu-Serif).
- **OCR Quality**: 100% accurate.
- **Important Fields**:
  - `Issuing Client Body`: Letterhead title
  - `Referenced Work`: Project name with package ID (e.g., *RCC Bridge — Gujarat Pkg-1*)
  - `Contract Value`: Monetary sum in Cr (e.g., *INR 33.38 Cr*)
  - `Completion Date`: (e.g., *06 Feb 2011*)
  - `Verification Contact`: Officer name, official email, telephone number
- **Optional Fields**: `Letter Ref Number`, `Specific Performance Comments`.
- **Repeated Phrases**: "Letter of Recommendation", "This office has engaged M/s National Infrastructure Corp. Ltd.", "commissioned without outstanding defects", "Verification:".
- **Headers & Footers**: Official client department header; footer contains `DOC-REF-{NNN}`.
- **Tables**: Found in ~64% of documents (rating grids: Criterion / Rating / Observation).
- **Signatures & Stamps**: Formal officer sign-off ("For [Client Department]").
- **Dates**: `DD Mon YYYY` (e.g., *31 Mar 2026*, *06 Feb 2011*).
- **Money**: `INR XX.XX Cr`.
- **Identifiers**: `Our ref: {N}`, `Package ID`.
- **Confidence of Extraction**: High (99.0%).
- **Recommended Parser**: Regex & Layout Parser.
- **Failure Modes**: Absence of letter is a key query signal (132 letters for 155 works = 23 missing). Missing letter must not be confused with unparsed document.
- **Example Snippet**:
  ```text
  National Special Projects Office
  Letter of Recommendation
  Our ref: 1 | Date: 31 Mar 2026
  This office has engaged M/s National Infrastructure Corp. Ltd. for the work
  "RCC Bridge — Gujarat Pkg-1" (INR 33.38 Cr), completed on 06 Feb 2011.
  On the basis of that engagement we record the following:
  Adherence to the sanctioned programme of work: Good
  Quality of workmanship: Accepted without material objection
  Verification: Meera Bose, ee@dept.gov.in, +91-9830000000.
  ```
- **Recommended Chunking Strategy**: Single document graph link.

---

### 4. `performance_bond` (Bank Guarantees)
- **Purpose**: Irrevocable performance bank guarantees issued by commercial banks on non-judicial stamp paper to secure contract execution.
- **Typical Length**: 1 to 3 pages (Average: 1.9 pages).
- **Common Layouts**: Bank letterhead with stamp paper header, guarantee covenant clauses, obligation formulas, and signatory execution block.
- **Text Density**: Medium (~314 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (Liberation-Sans-Narrow).
- **OCR Quality**: Clean digital text stream.
- **Important Fields**:
  - `Guarantor Bank`: (e.g., *Kalinga National Bank*, *Union Trust Bank of India*)
  - `Bond Number`: (e.g., *BND-00005*)
  - `Issue Date`: `YYYY-MM-DD`
  - `Tender Reference / RFP`: (e.g., *RFP-132000485*)
  - `Work Description`: Scope description
  - `Guarantee Percentage`: Typically *5%* or *10%* of contract value
  - `Guarantee Value / Stamp Value`: Non-Judicial Stamp Paper Value (INR 100/-)
- **Optional Fields**: `Expiry Date`, `Claim Expiry Date`, `Branch Code`.
- **Repeated Phrases**: "PERFORMANCE BANK GUARANTEE", "Non-Judicial Stamp Paper — Value: INR 100/-", "IRREVOCABLE AND UNCONDITIONAL", "WHEREAS National Infrastructure Corp. Ltd.".
- **Headers & Footers**: Bank Department header; footer has `DOC-BOND-{NNNNN}`.
- **Tables**: Present in 38% of documents (guarantee parameter summaries).
- **Signatures & Stamps**: Bank Officer / Manager signatures and bank seal.
- **Dates**: `YYYY-MM-DD`.
- **Money**: Guarantee amount, contract value percentage.
- **Identifiers**: `Bond No: BND-{N}`, `Tender Ref: RFP-{N}`.
- **Confidence of Extraction**: High (98.0%).
- **Recommended Parser**: Regex & Layout Parser.
- **Failure Modes**: Guarantee amount stated as percentage vs absolute currency number.

---

### 5. `personnel_certificate` (Staff Credentials)
- **Purpose**: Professional qualification certificates (PMP, Six Sigma Black Belt, etc.) issued by certification authorities to project engineers.
- **Typical Length**: Exactly 1 page.
- **Common Layouts**: Formal border certificate with central credential block and key-value attributes table.
- **Text Density**: Low-Medium (~97 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (Liberation-Sans-Narrow).
- **OCR Quality**: 100% precision.
- **Important Fields**:
  - `Credential Holder Name`: (e.g., *Asha Nair*, *Neha Chopra*, *Rahul Menon*, *Gautam Joshi*, *Naveen Roy*)
  - `Employee ID`: (e.g., *EMP-001*, *EMP-002*)
  - `Credential Type`: (*PMP*, *Six Sigma Black Belt*)
  - `Credential ID`: (e.g., *PMI-200006*, *PMI-200029*, *SSBB-100012*)
  - `Date of Issue`: `YYYY-MM-DD` (e.g., *2021-03-10*)
  - `Valid Through`: `YYYY-MM-DD`
  - `Highest Qualification`: (e.g., *Diploma Civil*, *B.Tech Civil*)
  - `Years of Experience`: (e.g., *28 years*)
- **Repeated Phrases**: "Professional Certification Authority", "This is to certify that", "Employment Status: Active — Project Manager".
- **Headers & Footers**: Issuing body logo/header (PMI / ISSC); footer has `DOC-PCERT-{NNN}`.
- **Tables**: Standardized 2-column key-value attribute table.
- **Signatures**: Registrar and Credential Holder signatures.
- **Dates**: `YYYY-MM-DD`.
- **Identifiers**: `Credential ID: PMI-{N}`, `Employee ID: EMP-{N}`.
- **Confidence of Extraction**: Very High (99.9%).
- **Recommended Parser**: Table & key-value parser.
- **Failure Modes**: Multiple certificates held by same employee with different issue dates (anchor date selection is crucial).
- **Example Snippet**:
  ```text
  PMI Professional Certification Authority
  PMP CERTIFICATION
  Credential ID: PMI-200006 | Issued: 2021-03-10
  This is to certify that Neha Chopra (EMP-001)
  Credential Type: PMP | Date of Issue: 2021-03-10 | Valid Through: 2027-08-31
  Employment Status: Active — Project Manager | Total Experience: 28 years
  ```

---

### 6. `cv` (Curriculum Vitae / Engineer Profiles)
- **Purpose**: Comprehensive technical resumes of key project managers detailing employment history, qualifications, business unit, and delivered works.
- **Typical Length**: Exactly 2 pages.
- **Common Layouts**: Corporate CV template with personal header, professional summary, core competencies matrix, education table, and project track record list.
- **Text Density**: Medium (~280 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (Gentium-Book-Basic).
- **OCR Quality**: Flawless.
- **Important Fields**:
  - `Name`: Engineer name
  - `Employee ID`: (e.g., *EMP-001*)
  - `Designation`: (*Project Manager*, *Senior Project Engineer*)
  - `Business Unit`: (*Civil Construction & Infrastructure*, *Specialized Technical Services*, etc.)
  - `Total Experience`: Years of experience
  - `Date of Joining`: `YYYY-MM-DD`
  - `Wage Group`: (*Group A*, *B*, *C*, *D*)
  - `Project History`: Table of projects led, roles, values, and completion years.
- **Repeated Phrases**: "Curriculum Vitae", "Key Personnel", "Core Competencies", "Site Execution".
- **Headers & Footers**: Header with corporate CIN; footer has `DOC-CV-{NNN}`.
- **Tables**: Present on both pages (Education, Competencies, Projects Led).
- **Confidence of Extraction**: High (99.0%).

---

### 7. `compliance_matrix` (Bid Compliance Matrices)
- **Purpose**: Tender submission checklists certifying company compliance against technical, financial, and statutory bid criteria.
- **Typical Length**: 1 to 2 pages (Average: 1.5 pages).
- **Common Layouts**: Structured multi-row checklist table with columns `#`, `Requirement`, `Status`, `Evidence`.
- **Text Density**: Medium (~230 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (Gentium-Book-Basic).
- **Important Fields**:
  - `Tender Reference`: (e.g., *Tender RFP-132000485*)
  - `Work Category`: (e.g., *Sewerage Drainage*, *Bridges Flyovers*)
  - `ISO Certification Evidence`: (*ORG-1001*, *ORG-1002*, *ORG-1003*)
  - `Minimum Turnover Complied`: (*Rs. 150 Cr*, *Rs. 180 Cr*)
  - `Key Staff On Roll`: (*486 personnel on rolls*)
  - `Plant & Machinery Deployed`: (*210 owned assets*)
  - `Earnest Money Deposit Ref`: (e.g., *EMD-0005*)
- **Confidence of Extraction**: Very High (99.5%).

---

### 8. `general_ledger_book` (Books of Account)
- **Purpose**: Complete statutory accounting journal containing double-entry debit, credit, and running balance postings across all fiscal years (2018–2025).
- **Typical Length**: 9 to 72 pages (Average: 47.4 pages).
- **Common Layouts**: High-density monospaced financial tables organized by Chart of Accounts (`ACCOUNT 1010 — BANK`, `ACCOUNT 2010 — ACCOUNTS PAYABLE`, `ACCOUNT 4010 — CONTRACT REVENUE`, etc.).
- **Text Density**: Very High (~6,635 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (Liberation-Mono).
- **Important Fields**:
  - `Fiscal Year`: (e.g., *FY 2019–20*, *FY 2024–25*)
  - `Account Number & Title`: (e.g., *ACCOUNT 1010 — BANK (ASSET)*)
  - `Date`: `YYYY-MM-DD`
  - `Voucher / Narration`: Transaction description (salaries, milestone receipts, vendor invoices)
  - `Debit / Credit Amounts`: Exact integer INR
  - `Running Balance`: Running balance with Dr/Cr indicator
- **Confidence of Extraction**: High (98.0% with tabular grid parser).

---

### 9. `bank_statement` (Bank Account Statements)
- **Purpose**: Current account transaction statements from financing banks tracking real cash inflows and outflows.
- **Typical Length**: 2 to 7 pages (Average: 4.5 pages).
- **Common Layouts**: 5-column financial statement table: `Date`, `Particulars`, `Withdrawal`, `Deposit`, `Balance`.
- **Text Density**: Medium-High (~942 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (Liberation-Sans-Narrow).
- **Important Fields**: `Bank Name`, `Account Number` (`00417 2210 9944`), `IFSC Code`, `Transaction Date`, `Particulars`, `Deposit`, `Withdrawal`, `Closing Balance`.
- **Reconciliation Note**: Directly reconciles 1:1 against General Ledger Account 1010.

---

### 10. `financial_statement` (Statutory Financial Results)
- **Purpose**: Audited annual financial statements presenting Profit & Loss extracts and Balance Sheet summaries.
- **Typical Length**: Exactly 3 pages.
- **Common Layouts**: Multi-column comparative tables comparing `Current Year` against `Previous Year` in Lakhs/Crores.
- **Text Density**: Medium (~548 words/doc).
- **Digital or Scanned**: 100% Digital Vector PDF (Liberation-Mono).
- **Important Fields**: `Contract Revenue (EPC)`, `Other Operating Revenue`, `Cost of Materials Consumed`, `Sub-contracting & Labour`, `Employee Benefit Expenses`, `Depreciation`, `Profit Before Tax (PBT)`, `Net Profit`.
- **Failure Modes**: Values are denominated in **Lakhs** (must be multiplied by 100,000 to convert to base INR).

---

### 11. `ra_bill` & `final_ra_bill` (Running Account Bills)
- **Purpose**: Detailed interim and final measurement bills submitted for payment under contract packages.
- **Typical Length**: `ra_bill`: 1 page; `final_ra_bill`: 14 to 24 pages (Average: 19.2 pages).
- **Common Layouts**: Contract abstract summary followed by multi-page BOQ measurement annexures.
- **Important Fields**: `Contract #`, `Client Name`, `Bill No`, `Date`, `Awarded Value`, `Total Value Billed`, `Retention @5%`, `GST @18%`, `BOQ Item Rates & Quantities`.

---

### 12. `tender_dossier` (Bid Submission Books)
- **Purpose**: Comprehensive 48-page bid submissions containing company profile, ISO certificates, financial standing, 48 relevant past performance works, key staff, and equipment schedules.
- **Typical Length**: Exactly 48 pages.
- **Text Density**: Very High (~8,293 words/doc).
- **Important Fields**: `Tender RFP #`, `Bid Value`, `Submission Date`, `Earnest Money Deposit`, `Annexures A through H`.

---

### 13. `iso_certificate` (Corporate Quality Accreditations)
- **Purpose**: Formal ISO quality, environmental, and safety management certificates.
- **Typical Length**: Exactly 2 pages (Page 1: Certificate; Page 2: Audit Schedule).
- **Important Fields**: `Certificate No` (*ORG-1001*, *ORG-1002*, *ORG-1003*), `Standard` (*ISO 9001:2015*, *ISO 14001:2015*, *ISO 45001:2018*), `Valid Until`, `Certification Body` (*TUV India*).

---

### 14. `annual_report` (Directors' Corporate Reports)
- **Purpose**: Annual corporate governance and financial narrative report.
- **Typical Length**: Exactly 18 pages.
- **Important Fields**: `Board of Directors roster`, `Project Manager appointment dates`, `Corporate Information`, `Statutory Auditors`.

---

### 15. `past_performance_portfolio` (Consolidated Credentials Pack)
- **Purpose**: Master index document registering all 155 completed works delivered by National Infrastructure Corp. Ltd. between 2010 and 2025.
- **Typical Length**: Exactly 64 pages.
- **Text Density**: Very High (~8,977 words/doc).
- **Important Fields**: Master table of all 155 works with `#`, `Work Title`, `Client`, `Category`, `Value (INR Cr)`, `Completion Date`.

---

### 16–20. `workbooks` (.xlsx Excel Files)
- **Files**:
  1. `Receivables_Ageing.xlsx`: Client-wise invoice ledger, invoice dates, invoiced amounts, payment status (`paid`/`due`), collected amount, outstanding balance.
  2. `Plant_and_Machinery_Register.xlsx`: Asset roster (Asset ID 1..N), equipment type, make, acquisition year, cost, condition (`new`/`good`/`fair`), deployment state, ownership (`owned`/`leased`), safety certification.
  3. `Trial_Balance_by_Year.xlsx`: Multi-sheet trial balance (FY 2018–19 to 2024–25) containing closing balances for all 16 chart of account heads.
  4. `BOQ_and_Measurements_Contract_{N}.xlsx` (6 workbooks): Live formula sheets (`=SUM(...)`, `=RATE*QTY`) detailing executed BOQ items and milestone measurements.

---

## Comparative Matrix: Recommended Extraction & Parsing Strategy

| Document Type | Primary Extraction Library | Key Regex / Extraction Hooks | Primary Chunking Strategy |
|---|---|---|---|
| `completion_certificate` | PyMuPDF (fitz) + regex | `Contract Value:\s*(INR\s*[\d.]+\s*Cr)`, `assessed as\s*["']?(\w+)["']?` | Document-level semantic entity graph |
| `company_completion_certificate` | PyMuPDF table extraction | `Work:\s*(.+)`, `Client:\s*(.+)`, `Project Lead:\s*(.+)` | Document-level semantic entity graph |
| `reference_letter` | PyMuPDF text parser | `for the work\s*["'](.+?)["']`, `\((INR\s*[\d.]+\s*Cr)\)` | Document-level entity link |
| `performance_bond` | PyMuPDF layout parser | `Bond No:\s*(BND-\d+)`, `Tender Ref:\s*(RFP-\d+)` | Document-level entity link |
| `personnel_certificate` | PyMuPDF text parser | `Credential ID:\s*([A-Z0-9-]+)`, `Date of Issue:\s*([\d-]+)` | Entity-attribute record |
| `cv` | PyMuPDF layout parser | `Name\s*
\s*(.+)`, `Employee ID\s*
\s*(EMP-\d+)` | Person-entity sub-graph |
| `compliance_matrix` | PyMuPDF table parser | Table extraction of `#`, `Requirement`, `Status`, `Evidence` | Tabular checklist record |
| `general_ledger_book` | PyMuPDF table extraction | `ACCOUNT\s*(\d{4})\s*—\s*(.+)`, Row regex `(\d{4}-\d{2}-\d{2})\s+(.+?)\s+([\d,]+)` | Page-by-page transaction record |
| `bank_statement` | PyMuPDF table extraction | Row regex `(\d{4}-\d{2}-\d{2})\s+(.+?)\s+([\d,]+)\s+([\d,]+)` | Page-by-page transaction record |
| `financial_statement` | PyMuPDF table extraction | Comparative grid extraction with Lakh-to-Rupee multiplier | Statement table record |
| `ra_bill` & `final_ra_bill` | PyMuPDF table extraction | Abstract + BOQ measurement tables | Section-based hierarchical record |
| `workbooks` (.xlsx) | `openpyxl` (data_only=False) | Read formulas + values across all named sheets | Sheet-level structured tables |
