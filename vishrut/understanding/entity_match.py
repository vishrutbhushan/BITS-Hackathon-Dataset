"""
Fuzzy entity matching against a gazetteer, used both to narrow candidates
BEFORE the LLM sees a question (so it selects rather than generates) and
to validate whatever the LLM proposes.

Uses difflib (stdlib) so this has zero install dependency. Swap in
`rapidfuzz` for speed if your gazetteer grows large -- same interface,
much faster on big candidate lists, but not necessary at this corpus
size (dozens of clients/engineers, not thousands).
"""
from difflib import SequenceMatcher


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def best_matches(query: str, candidates, top_n: int = 5, min_score: float = 0.5):
    """Return up to top_n (candidate, score) pairs sorted by descending
    similarity to `query`, filtered to score >= min_score.
    """
    scored = [(c, _similarity(query, c)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [(c, s) for c, s in scored[:top_n] if s >= min_score]


class Gazetteer:
    """Loads canonical names from the built graph (db/schema.py tables)
    and exposes fuzzy lookup + hard validation.
    """

    def __init__(self, con):
        self.clients = [r["name"] for r in con.execute("SELECT name FROM clients").fetchall()]
        self.engineers = [r["name"] for r in con.execute("SELECT name FROM engineers").fetchall()]
        self.projects = [r["name"] for r in con.execute("SELECT name FROM projects").fetchall()]

    def resolve_client(self, mention: str):
        matches = best_matches(mention, self.clients, top_n=1)
        return matches[0][0] if matches else None

    def resolve_engineer(self, mention: str):
        matches = best_matches(mention, self.engineers, top_n=1)
        return matches[0][0] if matches else None

    def resolve_project(self, mention: str):
        matches = best_matches(mention, self.projects, top_n=1)
        return matches[0][0] if matches else None

    def candidates_for_prompt(self, mention: str, entity_type: str, top_n: int = 15):
        """What to hand the LLM as the *only* valid choices for a given
        mention -- keeps it selecting rather than generating names."""
        pool = {"client": self.clients, "engineer": self.engineers, "project": self.projects}[entity_type]
        import re
        
        matches = []
        q_low = mention.lower()
        q_clean = re.sub(r'[^\w\s]', '', q_low)
        
        # 1. Exact or substring match (case-insensitive)
        for c in pool:
            c_low = c.lower()
            c_clean = re.sub(r'[^\w\s]', '', c_low)
            if c_low in q_low or c_clean in q_clean:
                matches.append((c, 1.0))
                
        # 2. Token overlap fallback
        if len(matches) < top_n:
            q_tokens = set(re.findall(r'\w+', q_low))
            for c in pool:
                if any(c == m[0] for m in matches):
                    continue
                c_tokens = set(re.findall(r'\w+', c.lower()))
                overlap = len(c_tokens.intersection(q_tokens))
                if overlap > 0:
                    score = overlap / len(c_tokens)
                    if score >= 0.2:
                        matches.append((c, score))
                        
        # 3. Fuzzy ratio fallback
        if len(matches) < top_n:
            scored = [(c, SequenceMatcher(None, mention.lower(), c.lower()).ratio()) for c in pool if not any(c == m[0] for m in matches)]
            scored.sort(key=lambda x: x[1], reverse=True)
            for c, s in scored:
                if s >= 0.1:
                    matches.append((c, s))
                    
        matches.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in matches[:top_n]]
