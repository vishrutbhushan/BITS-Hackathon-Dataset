"""
Relational schema for the extracted knowledge graph.

Uses sqlite3 (stdlib, zero install) so this runs anywhere with no setup.
DuckDB is a drop-in alternative if you want faster analytical queries
over a larger corpus -- the SQL below is plain ANSI SQL and should port
with little to no change (swap sqlite3.connect for duckdb.connect and
adjust the AUTOINCREMENT/PRIMARY KEY syntax slightly).
"""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS engineers (
    engineer_id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS engineer_certs (
    cert_id INTEGER PRIMARY KEY,
    engineer_id INTEGER NOT NULL REFERENCES engineers(engineer_id),
    cert_type TEXT NOT NULL,          -- e.g. 'PMP', 'Six Sigma Black Belt'
    cert_number TEXT,
    issue_date TEXT NOT NULL,          -- ISO 'YYYY-MM-DD'
    source_doc_id TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    project_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,               -- e.g. 'Cable Stayed Bridge \u2014 Jharkhand Pkg-115'
    client_id INTEGER NOT NULL REFERENCES clients(client_id),
    engineer_id INTEGER REFERENCES engineers(engineer_id),
    category TEXT NOT NULL,            -- from parsers.category.categorize
    value_rupees INTEGER NOT NULL,     -- canonical, from parsers.money.parse_money
    completion_date TEXT,              -- ISO date
    grading TEXT,                      -- from parsers.grading.normalize_grading
    role TEXT,                         -- 'Prime' / other
    has_reference_letter INTEGER NOT NULL DEFAULT 0,  -- 0/1
    source_doc_id TEXT                 -- completion_certificate doc_id this came from
);
"""


def get_connection(db_path: str = ":memory:") -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert_client(con, name: str) -> int:
    con.execute("INSERT OR IGNORE INTO clients(name) VALUES (?)", (name,))
    return con.execute("SELECT client_id FROM clients WHERE name = ?", (name,)).fetchone()[0]


def upsert_engineer(con, name: str) -> int:
    con.execute("INSERT OR IGNORE INTO engineers(name) VALUES (?)", (name,))
    return con.execute("SELECT engineer_id FROM engineers WHERE name = ?", (name,)).fetchone()[0]
