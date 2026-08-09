# Data Normalization & Canonicalization Guide
**Corpus**: National Infrastructure Corp. Ltd. Enterprise Archive
**Objective**: Comprehensive normalization specifications for monetary sums, Indian numbering, dates, entity names, percentages, and units.

---

## 1. Monetary Normalization Rules

In Indian corporate and government archives, monetary figures appear in four distinct rendering formats. All monetary values must be converted to **exact lossless integer Indian Rupees (INR)**.

### Formula & Conversion Matrix:

| Rendering Format | Example in Corpus | Conversion Formula | Normalized Integer (INR) |
|---|---|---|---|
| **Crore (Cr)** | `INR 33.38 Cr` | $	ext{Round}(	ext{float} 	imes 10,000,000)$ | `333800000` |
| **Lakh** | `3,338.00 Lakh` | $	ext{Round}(	ext{float} 	imes 100,000)$ | `333800000` |
| **Indian Comma Grouping** | `33,38,00,000` | $	ext{int}(	ext{strip\_commas})$ | `333800000` |
| **Standard / Raw Integer** | `333800000` | $	ext{int}(	ext{value})$ | `333800000` |
| **Financial Statements (in Lakhs)** | `4,817` | $	ext{Round}(4817 	imes 100,000)$ | `481700000` |

### Python Reference Normalizer:
```python
def normalize_inr(val_str: str) -> int:
    val_str = str(val_str).strip().replace(',', '')
    
    # Match Crore
    m = re.search(r'(?:INR|Rs\.?|₹)?\s*([\d.]+)\s*(?:Cr|crore|Crore)', val_str, re.IGNORECASE)
    if m:
        return int(round(float(m.group(1)) * 10_000_000))
        
    # Match Lakh
    m = re.search(r'(?:INR|Rs\.?|₹)?\s*([\d.]+)\s*(?:Lakh|lakh|Lakhs|lac)', val_str, re.IGNORECASE)
    if m:
        return int(round(float(m.group(1)) * 100_000))
        
    # Match plain number
    m = re.search(r'(?:INR|Rs\.?|₹)?\s*([\d]+(?:\.\d+)?)', val_str)
    if m:
        return int(round(float(m.group(1))))
    raise ValueError(f"Cannot normalize monetary value: {val_str}")
```

---

## 2. Date & Time Normalization Rules

All dates must be parsed into ISO 8601 `YYYY-MM-DD` standard format for arithmetic operations (e.g. date span calculation).

| Raw Date Format | Example in Corpus | Normalized ISO Format |
|---|---|---|
| `DD/MM/YYYY` | `06/02/2011` | `2011-02-06` |
| `YYYY-MM-DD` | `2021-03-10` | `2021-03-10` |
| `Month DD, YYYY` | `March 10, 2021` | `2021-03-10` |
| `DD Month YYYY` | `06 Feb 2011` | `2011-02-06` |
| `DD-MM-YYYY` | `18-09-2016` | `2016-09-18` |

### Date Span Calculation Rule:
$$	ext{Days} = (	ext{Date}_{	ext{completion}} - 	ext{Date}_{	ext{certification}}).	ext{days}$$

---

## 3. Client & Entity Name Normalization

Client organizations must be canonicalized to prevent fragmentation during portfolio queries:

| Surface Client String | Canonical Client Name | Category |
|---|---|---|
| `Public Works Department, Govt of Maharashtra` / `PWD Maharashtra` | `Public Works Department, Govt of Maharashtra` | State Department |
| `Jal Nigam, Jharkhand` / `Jharkhand Jal Nigam` | `Jal Nigam, Jharkhand` | State Water Board |
| `Public Health Engineering Dept, Gujarat` / `PHED Gujarat` | `Public Health Engineering Dept, Gujarat` | State Department |
| `Irrigation & Waterways Dept, Govt of Uttar Pradesh` | `Irrigation & Waterways Dept, Govt of Uttar Pradesh` | State Department |
| `Lakshya Engineering & Construction` / `Lakshya Engg` | `Lakshya Engineering & Construction` | Private Enterprise |
| `National Special Projects Office` | `National Special Projects Office` | Central Agency |

---

## 4. Percentage & Ratio Normalization

- **Rule**: Hackathon evaluation questions require percentages expressed **out of 100** rounded to 2 decimal places (e.g. `33.33` or `66.67`), **NOT as fractions** (e.g. `0.3333` scores 0.0 per evaluate.py).
- **Formula**:
$$	ext{Share} = 	ext{round}\left(rac{	ext{Count}_{	ext{referenced}}}{	ext{Count}_{	ext{total}}} 	imes 100, 2ight)$$
