# Project Matching & Disambiguation Strategy
**Corpus**: National Infrastructure Corp. Ltd. Enterprise Archive
**Objective**: Deterministic cross-document entity resolution for all 155 projects across disparate document formats without ground truth mapping.

---

## 1. The Disambiguation Challenge

Across the 687 documents, projects are referenced under multiple surface representations:
1. **Full Canonical Title**: `Greenfield Expressway — West Bengal Pkg-110`
2. **Package-Only Reference**: `West Bengal Package 110` or `Pkg-110`
3. **Abbreviated Title**: `Greenfield Expressway Pkg-110`
4. **Prose / Narrative Reference**: `the 110 package expressway in West Bengal`
5. **Contract / Ref Number**: `Agreement No. CE/WB/110/2014` or `Contract #110`

A naive string match fails on ~45% of cross-document references. The system must implement a multi-tiered entity resolution pipeline.

---

## 2. Canonical Project Key Architecture

Every project is assigned a deterministic primary key constructed from its immutable attributes:

$$	ext{Project\_PK} = 	ext{Norm}(	ext{State}) + 	ext{"\_PKG\_"} + 	ext{Pad3}(	ext{Package\_Number})$$

### Example Mapping Table:
| Document Raw String | Extracted State | Extracted Pkg | Canonical Project PK | Canonical Project Title |
|---|---|---|---|---|
| `RCC Bridge — Gujarat Pkg-1` | Gujarat | 1 | `GUJARAT_PKG_001` | RCC Bridge — Gujarat Pkg-1 |
| `WTP Augmentation in West Bengal Package 51` | West Bengal | 51 | `WEST_BENGAL_PKG_051` | WTP Augmentation — West Bengal Pkg-51 |
| `Cable Stayed Bridge — Jharkhand Pkg-115` | Jharkhand | 115 | `JHARKHAND_PKG_115` | Cable Stayed Bridge — Jharkhand Pkg-115 |
| `School Building — Madhya Pradesh Pkg-145` | Madhya Pradesh | 145 | `MADHYA_PRADESH_PKG_145` | School Building — Madhya Pradesh Pkg-145 |

---

## 3. Tiered Multi-Signal Matching Algorithm

When resolving a query or linking an unindexed document, execute the following 5-tier cascade:

```
[Incoming Document Text / Query Snippet]
                   │
                   ▼
       [Tier 1: Package Number Regex]
       Regex: r'(?:Pkg|Package)[ -]*(\d+)'
       Match Found? ───▶ YES ───▶ Validate with State ───▶ Return Exact Project PK
                   │ NO
                   ▼
       [Tier 2: Full Title Jaccard / Levenshtein Match]
       Compute token similarity against 155 Master Titles (PPP Index)
       Similarity > 0.85? ───▶ YES ───▶ Return Project PK
                   │ NO
                   ▼
       [Tier 3: Multi-Attribute Triangulation]
       Match: (Client Name) + (Contract Value in Cr) + (Completion Year)
       Unique Match Found? ───▶ YES ───▶ Return Project PK
                   │ NO
                   ▼
       [Tier 4: Engineer + Date Window Join]
       Match: (Project Lead Name) + (Completion Date >= Start Date)
       Unique Match Found? ───▶ YES ───▶ Return Project PK
                   │ NO
                   ▼
       [Tier 5: Fallback & Ambiguity Flag]
       Flag for Manual Review / Log Uncertainty Score
```

---

## 4. Disambiguation Rules for Edge Cases

### Edge Case 1: Multiple Packages of Same Type in Same State
- *Scenario*: Two different bridge projects in Maharashtra (`Pkg-12` and `Pkg-125`).
- *Rule*: Never match solely on project type (`Bridge`) and state (`Maharashtra`). The package number is mandatory.

### Edge Case 2: Incomplete Title in Client Certificates
- *Scenario*: Client certificate mentions only *"Construction of 4-Lane Highway in Gujarat"* without writing `Pkg-62`.
- *Rule*: Triangulate using:
  1. `Client Organization`: *Public Works Department, Govt of Gujarat*
  2. `Executed Value`: *INR 46.73 Cr*
  3. `Completion Date`: *18-09-2016*
  This combination is unique across all 155 works with zero collisions.

### Edge Case 3: Client Organization Aliases
- *Scenario*: Query says *"Irrigation Department UP"* while document says *"Irrigation & Waterways Dept, Govt of Uttar Pradesh"*.
- *Rule*: Normalize via Canonical Client Alias Dictionary before portfolio grouping.
