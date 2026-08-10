"""
Canonical date parser.

The corpus spans 15 years and multiple issuing bodies / reporting eras,
so date rendering is not uniform. This tries a fixed list of explicit
formats first (fast, unambiguous) and falls back to a permissive parser
only if none match.
"""
import re
from datetime import date, datetime

_EXPLICIT_FORMATS = [
    "%Y-%m-%d",       # 2021-03-10
    "%d-%m-%Y",       # 10-03-2021
    "%d/%m/%Y",       # 10/03/2021
    "%d.%m.%Y",       # 10.03.2021
    "%d %B %Y",        # 10 March 2021
    "%d %b %Y",        # 10 Mar 2021
    "%B %d, %Y",       # March 10, 2021
    "%b %d, %Y",       # Mar 10, 2021
    "%d-%b-%Y",        # 10-Mar-2021
    "%d-%B-%Y",        # 10-March-2021
]

_DATE_LIKE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b"
)


def parse_date(text: str):
    """Return a datetime.date, or None if no date could be parsed.

    `text` can be a full sentence (the function extracts the date-like
    substring itself) or just the date string.
    """
    if not text:
        return None
    text = text.strip()

    for fmt in _EXPLICIT_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    m = _DATE_LIKE_RE.search(text)
    if m:
        candidate = m.group(1)
        for fmt in _EXPLICIT_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
        try:
            from dateutil import parser as _dateutil_parser  # optional dep
            return _dateutil_parser.parse(candidate, dayfirst=True).date()
        except ImportError:
            pass

    return None


def date_diff_days(d1, d2) -> int:
    """Absolute number of days between two dates (or parseable date strings)."""
    if isinstance(d1, str):
        d1 = parse_date(d1)
    if isinstance(d2, str):
        d2 = parse_date(d2)
    if d1 is None or d2 is None:
        raise ValueError("both dates must be parseable")
    return abs((d2 - d1).days)
