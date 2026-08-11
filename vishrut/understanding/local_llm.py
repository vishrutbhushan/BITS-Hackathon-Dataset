"""
LLM interface for the bid-desk pipeline.

Two entry points:
  - text_to_sql(question, con)  → SQLite SELECT string
  - query_llm_direct(prompt)    → raw text (used by RAG fallback)

All calls go to the local proxy on port 8001.
Temperature is 0 throughout for deterministic answers.
"""
import json
import re
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Schema given to the LLM verbatim ──────────────────────────────────────────

_SCHEMA = """\
Tables (SQLite):

  clients(client_id INTEGER PK, name TEXT UNIQUE)
  engineers(engineer_id INTEGER PK, name TEXT UNIQUE)
  engineer_certs(cert_id INTEGER PK,
                 engineer_id INTEGER FK→engineers,
                 cert_type TEXT,      -- 'PMP' | 'Six Sigma Black Belt'
                 cert_number TEXT,
                 issue_date TEXT)     -- ISO YYYY-MM-DD
  projects(project_id INTEGER PK,
           name TEXT,
           client_id INTEGER FK→clients,
           engineer_id INTEGER FK→engineers,  -- may be NULL
           category TEXT,
           value_rupees INTEGER,
           completion_date TEXT,              -- ISO YYYY-MM-DD
           grading TEXT,                      -- 'Excellent'|'Very Good'|'Good'|'Satisfactory'|'Poor'|NULL
           role TEXT,                         -- 'Prime' | 'JV Partner'
           has_reference_letter INTEGER)      -- 1=yes, 0=no
"""

_CATEGORY_NOTE = """\
Exact category values in projects.category:
  'bridges and flyovers', 'bridge', 'building', 'drainage',
  'road', 'tunnel', 'water_treatment', 'other'
Note: 'drainage' covers sewerage/STP/drainage works.
      'water_treatment' covers WTP/water supply/water treatment plants.
      'road' covers roads, highways, pavements, expressways.
      'tunnel' covers tunnels and hydro tunnels.
      'bridges and flyovers' and 'bridge' both refer to bridge/flyover work.
"""

_TEXT_TO_SQL_PROMPT = """\
You are a SQLite expert. Answer a construction bid-desk question by writing a \
single SQL SELECT statement that returns exactly one numeric value.

{schema}

{category_note}

VALID CLIENT NAMES (use exact spelling):
{clients}

VALID ENGINEER NAMES (use exact spelling):
{engineers}

VALID CERT TYPES: 'PMP', 'Six Sigma Black Belt'
VALID ROLES: 'Prime', 'JV Partner'

RULES:
- Output ONLY the SQL statement. No explanation, no markdown fences, no prose.
- The query must return exactly ONE row with ONE column.
- Use LIKE for fuzzy client/engineer name matching in case of slight variations.
- For percentage of projects with reference letters: \
  ROUND(100.0 * SUM(has_reference_letter) / COUNT(*), 2)
- For date differences, use JULIANDAY(date2) - JULIANDAY(date1) and CAST to INTEGER.
- For "gap between awarded and invoiced" or similar two-bucket differences, \
  compute abs(SUM(bucket_a) - SUM(bucket_b)) unless the question explicitly \
  says "negative if lower".
- For year-on-year changes, filter by strftime('%Y', completion_date).
- For average/mean: ROUND(AVG(value_rupees)).
- For median: use the SQLite median trick \
  (ORDER BY value_rupees LIMIT 1 OFFSET (COUNT(*)-1)/2) in a subquery.

QUESTION: {question}

SQL:"""


def text_to_sql(question: str, con, timeout: int = 45) -> str:
    """Ask the LLM to write a SQL query for this question.

    Returns the raw SQL string. Raises on network/parse error.
    """
    # Build entity context from the live DB
    clients = [r[0] for r in con.execute("SELECT name FROM clients ORDER BY name").fetchall()]
    engineers = [r[0] for r in con.execute("SELECT name FROM engineers ORDER BY name").fetchall()]

    prompt = _TEXT_TO_SQL_PROMPT.format(
        schema=_SCHEMA,
        category_note=_CATEGORY_NOTE,
        clients="\n  ".join(clients),
        engineers="\n  ".join(engineers),
        question=question,
    )

    resp = requests.post(
        "http://127.0.0.1:8001/ask",
        headers={"Content-Type": "application/json"},
        json={"prompt": prompt},
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = resp.json()["response"].strip()

    # Strip markdown fences if model ignores instructions
    raw = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    # Take only the first statement if model outputs multiple
    sql = raw.split(";")[0].strip()
    if not sql.upper().startswith("SELECT"):
        raise ValueError(f"LLM did not return a SELECT statement: {sql[:200]!r}")
    return sql


def execute_sql(con, sql: str):
    """Execute a SQL query and return the single scalar result.

    Returns None if the query returns no rows.
    Raises on SQL error.
    """
    row = con.execute(sql).fetchone()
    if row is None:
        return None
    return row[0]


def query_llm_direct(prompt: str, timeout: int = 60) -> str:
    """Send a raw prompt to the LLM and return the text response.
    Used by the RAG fallback.
    """
    resp = requests.post(
        "http://127.0.0.1:8001/ask",
        headers={"Content-Type": "application/json"},
        json={"prompt": prompt},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()
