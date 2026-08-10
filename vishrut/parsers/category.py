"""
Project category taxonomy.

There's no explicit "category" field in the documents -- it has to be
derived from the project title itself (e.g. "School Building" -> building,
"Ring Road" -> road). This is a small fixed keyword taxonomy, checked in
order of specificity so a more specific keyword wins over a generic one.

Extend CATEGORY_KEYWORDS as you read real project titles -- this is the
kind of thing that's much easier to get right by looking at the actual
corpus than by guessing up front.
"""

# Ordered: more specific terms first, so e.g. "flyover" wins over a
# generic "road" match if both could apply.
CATEGORY_KEYWORDS = [
    ("flyover", ["flyover"]),
    ("bridge", ["bridge", "cable stayed", "cable-stayed"]),
    ("tunnel", ["tunnel"]),
    ("road", ["road", "highway", "expressway"]),
    ("water_treatment", ["wtp", "water treatment", "water supply", "pipeline"]),
    ("drainage", ["drainage", "sewage", "sewer"]),
    ("dam", ["dam", "check dam", "barrage"]),
    ("power", ["power", "substation", "transmission line", "grid"]),
    ("building", ["building", "residential", "school", "hospital", "quarters", "office"]),
    ("roads_maintenance", ["road maintenance", "roads maintenance", "resurfacing"]),
]


def categorize(raw_category: str) -> str:
    """Map a raw category string from completion certificates to question format."""
    if not raw_category:
        return "other"
    c = raw_category.strip().lower()
    if c == "bridges flyovers":
        return "bridges and flyovers"
    return c
