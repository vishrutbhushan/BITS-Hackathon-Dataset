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


def categorize(project_title: str) -> str:
    """Map a project title to a fixed category label. Returns 'other' if
    nothing matches -- log these during a real run so the taxonomy above
    can be extended to cover them.
    """
    if not project_title:
        return "other"
    t = project_title.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in t:
                return category
    return "other"
