"""
Canonical money parser.

Every monetary figure in the corpus is rendered the way Indian business
documents render it -- never assume a bare integer. This module converts
any of the known renderings into a canonical integer number of rupees.

Uses Decimal throughout so summing many crore/lakh-denominated values
never drifts from float rounding error.
"""
import re
from decimal import Decimal, InvalidOperation

_CR_RE = re.compile(r"(?:INR|Rs\.?|\u20b9)?\s*([\d,]+(?:\.\d+)?)\s*Cr\b", re.IGNORECASE)
_LAKH_RE = re.compile(r"(?:INR|Rs\.?|\u20b9)?\s*([\d,]+(?:\.\d+)?)\s*Lakh\b", re.IGNORECASE)
# Indian digit grouping: 33,38,00,000 -- groups of 2 after the first group of 3
_INDIAN_GROUPED_RE = re.compile(r"(?:INR|Rs\.?|\u20b9)?\s*(\d{1,2}(?:,\d{2})*,\d{3})\b")
_RAW_INT_RE = re.compile(r"(?:INR|Rs\.?|\u20b9)?\s*(\d{6,})\b")  # 6+ digits, unformatted

CRORE = Decimal("10000000")
LAKH = Decimal("100000")


def parse_money(text: str):
    """Return canonical integer rupees, or None if no money found.

    Tries the most specific / least ambiguous patterns first (Cr, Lakh --
    these carry an explicit unit and can't be confused with a plain
    count), then Indian-grouped digits, then a bare large integer as a
    last resort.
    """
    if not text:
        return None

    m = _CR_RE.search(text)
    if m:
        return _to_int(Decimal(m.group(1).replace(",", "")) * CRORE)

    m = _LAKH_RE.search(text)
    if m:
        return _to_int(Decimal(m.group(1).replace(",", "")) * LAKH)

    m = _INDIAN_GROUPED_RE.search(text)
    if m:
        try:
            return _to_int(Decimal(m.group(1).replace(",", "")))
        except InvalidOperation:
            pass

    m = _RAW_INT_RE.search(text)
    if m:
        return _to_int(Decimal(m.group(1)))

    return None


def _to_int(d: Decimal) -> int:
    return int(d.to_integral_value())


# --- spoken / question-embedded amounts -------------------------------
# Questions themselves sometimes state a threshold in words, e.g.
# "seventy-three crore", "six crore", or already-digit form "INR 20 Cr"
# (parse_money handles the latter). This handles the word-number case.

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

_SPOKEN_UNIT_RE = re.compile(r"([a-zA-Z\- ]+?)\s*(crore|lakh)\b", re.IGNORECASE)


def _words_to_int(phrase: str):
    """Parse a small English number phrase like 'seventy-three' or 'six'."""
    phrase = phrase.strip().lower().replace("-", " ")
    if not phrase:
        return None
    tokens = [t for t in phrase.split() if t]
    total = 0
    matched = False
    for tok in tokens:
        if tok in _TENS:
            total += _TENS[tok]
            matched = True
        elif tok in _ONES:
            total += _ONES[tok]
            matched = True
        elif tok == "hundred":
            total = (total or 1) * 100
            matched = True
    return total if matched else None


def parse_spoken_amount(text: str):
    """Find a word-number amount in question text, e.g.
    'crossing the seventy-three crore mark' -> 730000000.
    Falls back to parse_money for digit-based mentions in the same text.
    """
    if not text:
        return None
    m = _SPOKEN_UNIT_RE.search(text)
    if m:
        n = _words_to_int(m.group(1))
        if n is not None:
            unit = CRORE if m.group(2).lower() == "crore" else LAKH
            return _to_int(Decimal(n) * unit)
    return parse_money(text)
