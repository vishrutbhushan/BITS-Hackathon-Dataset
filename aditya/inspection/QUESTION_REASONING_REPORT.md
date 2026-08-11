# Question Reasoning Patterns & Derivation Templates Report
**Corpus Analysis**: `sample_questions.json` (25 worked questions) + Technical Briefing Evaluation Rules
**Scope**: Taxonomy of all 21 reasoning patterns, computational templates, multi-hop traversal paths, and difficulty rankings.

---

## 1. Taxonomy of All 21 Reasoning Patterns

| ID | Pattern Name | Hops | Sample Questions | Derivation Template | Difficulty |
|---|---|---|---|---|---|
| **P1** | `absence` | 3 | HS-IC-0001, 0002 | Count works commissioned by Client where Reference Letter is ABSENT | Medium |
| **P2** | `date_span` | 4 | HS-IC-0003, 0004 | $(	ext{Project Completion Date}) - (	ext{Engineer PMP Issue Date})$ in Days | Low-Medium |
| **P3** | `distinct_count` | 4 | HS-IC-0005, 0006 | $	ext{Count}(	ext{Distinct Work Categories led by Engineer under PMP})$ | Medium |
| **P4** | `hop_aggregate` | 4 | HS-IC-0007, 0008 | $\sum 	ext{Contract Value of all works by Client for Engineer's anchor project}$ | High |
| **P5** | `temporal_chain` | 4 | HS-IC-0009, 0010 | $\sum 	ext{Contract Value of works led by Engineer finished AFTER PMP date}$ | High |
| **P6** | `avg_work_size` | 5 | HS-IC-0011, 0012 | $rac{1}{N} \sum 	ext{Contract Values for Client of anchor project}$ (in exact INR) | High |
| **P7** | `doc_filtered_aggregate` | 5 | HS-IC-0013, 0014 | $\sum 	ext{Contract Values for Client where Performance Grade} = 	ext{"Satisfactory" / "Excellent"}$ | Very High |
| **P8** | `exclusion_aggregate` | 5 | HS-IC-0015, 0016 | $\sum 	ext{Contract Values for Client excluding specific category (e.g. Buildings / Roads)}$ | High |
| **P9** | `gap_to_threshold` | 5 | HS-IC-0017 | $	ext{Threshold Value} - \sum 	ext{Contract Values for Client}$ | High |
| **P10** | `rank_value` | 5 | HS-IC-0018, 0019 | $	ext{Value}(	ext{Rank 1 Project}) - 	ext{Value}(	ext{Rank 2 Project})$ for Client | High |
| **P11** | `referenced_share` | 5 | HS-IC-0020, 0021 | $rac{	ext{Count}(	ext{Works with Ref Letter})}{	ext{Count}(	ext{Total Works for Client})} 	imes 100$ | Very High |
| **P12** | `role_split` | 5 | HS-IC-0022, 0023 | $\sum 	ext{Contract Values for Client where Role} = 	ext{"Prime"}$ | High |
| **P13** | `threshold_aggregate` | 5 | HS-IC-0024, 0025 | $\sum 	ext{Contract Values for Client where Value} \ge 	ext{Threshold (e.g. 73 Cr)}$ | High |
| **P14** | `bank_guarantee_ratio` | 4 | Hidden Set | $rac{\sum 	ext{PBG Guarantee Amounts}}{\sum 	ext{Contract Values}}$ for active tenders | High |
| **P15** | `receivables_due_share` | 4 | Hidden Set | $\sum 	ext{Outstanding Receivables for Client from Ageing Workbook}$ | Medium |
| **P16** | `plant_asset_valuation` | 4 | Hidden Set | $\sum 	ext{Cost of Owned / Safety-Certified Plant in specific State}$ | Medium |
| **P17** | `turnover_growth_rate` | 5 | Hidden Set | $rac{	ext{Turnover}_{t} - 	ext{Turnover}_{t-1}}{	ext{Turnover}_{t-1}} 	imes 100$ from Financial Statements | High |
| **P18** | `ledger_cash_reconciliation`| 5 | Hidden Set | Sum of Debit entries in Account 1010 matching Bank Deposits for FY | Very High |
| **P19** | `boq_quantity_variance` | 4 | Hidden Set | $	ext{Executed Qty} - 	ext{BOQ Tender Qty}$ for specific BOQ item | High |
| **P20** | `iso_turnover_compliance` | 4 | Hidden Set | Check Turnover $\ge 150 	ext{ Cr}$ and ISO 9001 validity for RFP | High |
| **P21** | `multi_hop_engineer_client`| 6 | Hidden Set | Total value across multiple engineers sharing the same Business Unit | Extreme |

---

## 2. Worked Step-by-Step Derivation Breakdown

### Example 1: `HS-IC-0011` (`avg_work_size`)
- **Question**: "Regarding Asha Nair’s PMP work on the Cable Stayed Bridge — Jharkhand Pkg-115, what is the defensible average size across all completed projects for the commissioning client?"
- **Hop 1**: Locate `DOC-PCERT-xxx` for *Asha Nair* -> confirms PMP holder.
- **Hop 2**: Locate `DOC-CCC-115.pdf` for *Cable Stayed Bridge — Jharkhand Pkg-115* -> Client is *Jal Nigam, Jharkhand*.
- **Hop 3**: Query all projects commissioned by *Jal Nigam, Jharkhand* across the 155-work portfolio:
  1. *Water Treatment Plant — Jharkhand Pkg-14* (INR 73.02 Cr = `730,200,000`)
  2. *Cable Stayed Bridge — Jharkhand Pkg-115* (INR 81.44 Cr = `814,400,000`)
  3. *Drainage Network — Jharkhand Pkg-88* (INR 6.92 Cr = `69,200,000`)
- **Hop 4**: Sum values: $730,200,000 + 814,400,000 + 69,200,000 = 1,613,800,000	ext{ INR}$.
- **Hop 5**: Average: $rac{1,613,800,000}{3} = \mathbf{537,933,333	ext{ INR}}$.
