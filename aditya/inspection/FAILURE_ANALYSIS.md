# Failure Mode & Hallucination Risk Analysis
**Corpus**: National Infrastructure Corp. Ltd. Enterprise Archive
**Objective**: Identify every potential point of failure, hallucination risk, and extraction ambiguity, with concrete mitigation strategies.

---

## 1. Critical Failure Modes & Mitigations

| # | Failure Mode / Pitfall | Root Cause | Impact on Answer | Mitigation Strategy |
|---|---|---|---|---|
| **1** | **Hallucinating Missing Reference Letters** | Retrieval system assumes retrieved docs represent full truth; cannot prove negative. | Answers "0" for missing count questions -> Score 0.0. | Maintain closed-world boundary of all 155 works; explicitly check `proj_id NOT IN (SELECT proj_id FROM ref_letters)`. |
| **2** | **Crore vs Lakh Unit Misinterpretation** | Financial statements use Lakhs; certificates use Crores; ledgers use raw INR. | 100x or 10,000,000x scaling error -> Score 0.0. | Strictly enforce unit conversion rules in normalization pipeline. |
| **3** | **Client Portfolio Truncation** | Matching only the document named in the question rather than traversing to all client works. | Returns value of single work instead of aggregate portfolio sum. | Question slot parser must identify client entity and execute portfolio query. |
| **4** | **Temporal Boundary Misalignment** | Including projects finished *before* an engineer's PMP certification date when question asks for *after*. | Overcounting contract value -> Score 0.0. | Strict SQL temporal filter: `WHERE completion_date > pmp_issue_date`. |
| **5** | **Prose Grading Extraction Failure** | Client performance grading is written in paragraphs rather than key-value tables. | Missing qualitative filters ("Satisfactory", "Excellent") -> Score 0.0. | Run regex and sentence sentiment classification on full certificate text. |
| **6** | **Percentage vs Fraction Output Format** | Returning `0.33` instead of `33.33` for share questions. | evaluate.py expects value out of 100 -> Score 0.0. | Answer formatter converts all proportions to percentage scale (0..100). |
| **7** | **Similar Project Name Collision** | Multiple projects named "Highway" or "Bridge" in same state. | Linking wrong package to engineer -> Score 0.0. | Always use composite key `(State, Package_Number)`. |
| **8** | **Excel Formula Ignoring** | Reading raw formula strings instead of evaluated cell values in `.xlsx`. | Unresolved cell strings in BOQ/Ageing calculations. | Use `openpyxl(data_only=True)` to read cached formula results. |
