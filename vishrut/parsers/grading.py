"""
Client written-grading normalizer.

The client's assessment of a completed work ("Excellent", "Very Good",
"Satisfactory", ...) lives only in prose on the completion certificate --
there's no dedicated field. Since the corpus is synthetic, the vocabulary
is almost certainly a small fixed set; this is keyword matching, not
free-text sentiment analysis.

Extend GRADING_VOCAB once you see the real vocabulary in the documents.
"""
import re

# Ordered longest-phrase-first so "very good" matches before a bare "good".
GRADING_VOCAB = [
    "Excellent",
    "Very Good",
    "Good",
    "Satisfactory",
    "Below Average",
    "Poor",
]

_GRADING_PATTERNS = [
    (g, re.compile(re.escape(g), re.IGNORECASE)) for g in GRADING_VOCAB
]


def normalize_grading(text: str):
    """Return the canonical grading label found in `text`, or None."""
    if not text:
        return None
    for canonical, pattern in _GRADING_PATTERNS:
        if pattern.search(text):
            return canonical
    return None
