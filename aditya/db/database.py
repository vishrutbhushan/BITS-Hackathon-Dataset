import duckdb
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_DIR = Path(__file__).parent
DEFAULT_DB_PATH = DB_DIR / "estate.duckdb"

class EstateDatabase:
    def __init__(self, db_path: Optional[Path] = None, read_only: bool = True):
        self.db_path = str(Path(db_path or DEFAULT_DB_PATH).resolve())
        self.read_only = read_only
        self.conn = duckdb.connect(self.db_path, read_only=read_only)
        self._init_extensions()

    def _init_extensions(self):
        try:
            # Runtime processes only need to load the already-installed
            # extension.  INSTALL takes a write lock (and can attempt network
            # access), which made concurrent submission workers contend even
            # though all online queries are read-only.
            self.conn.execute("LOAD fts;")
        except Exception:
            # Relational execution remains available and search_fts has a
            # deterministic ILIKE fallback when the optional extension is not
            # installed in a fresh environment.
            return

    def execute(self, query: str, parameters: Optional[list] = None):
        if parameters:
            return self.conn.execute(query, parameters)
        return self.conn.execute(query)

    def fetchall(self, query: str, parameters: Optional[list] = None, use_cache: bool = True) -> List[tuple]:
        params = tuple(parameters or ())
        if use_cache and self.read_only and query.lstrip().lower().startswith(("select", "with")):
            return list(self._cached_fetchall(query, params))
        return self.execute(query, list(params)).fetchall()

    @lru_cache(maxsize=1024)
    def _cached_fetchall(self, query: str, parameters: tuple) -> tuple:
        """Cache immutable online query results within a worker process."""
        return tuple(self.conn.execute(query, list(parameters)).fetchall())

    def fetchdf(self, query: str, parameters: Optional[list] = None):
        return self.execute(query, parameters).fetchdf()

    def search_fts(self, query_text: str, limit: int = 10, doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Execute BM25 full-text search over indexed documents table.
        """
        # Clean query for BM25
        clean_q = " ".join([w for w in query_text.replace("'", " ").replace('"', ' ').split() if len(w) > 1])
        if not clean_q:
            return []

        try:
            filter_clause = "AND doc_type = ?" if doc_type else ""
            sql = f"""
                SELECT doc_id, doc_type, filename, score, content
                FROM (
                    SELECT doc_id, doc_type, filename, content,
                           fts_main_documents.match_bm25(doc_id, ?) AS score
                    FROM documents
                )
                WHERE score IS NOT NULL {filter_clause}
                ORDER BY score DESC
                LIMIT ?
            """
            params = [clean_q]
            if doc_type:
                params.append(doc_type)
            params.append(limit)
            # FTS rows include complete document text and are question-specific;
            # retaining hundreds of them in the scalar-query LRU wastes memory.
            rows = self.fetchall(sql, params, use_cache=False)
            results = []
            for r in rows:
                results.append({
                    "doc_id": r[0],
                    "doc_type": r[1],
                    "filename": r[2],
                    "score": float(r[3]),
                    "content": r[4]
                })
            return results
        except Exception as e:
            # Fallback to ILIKE if FTS error
            like_terms = [f"%{term}%" for term in clean_q.split()[:4]]
            conditions = " OR ".join(["content ILIKE ?" for _ in like_terms])
            type_cond = "AND doc_type = ?" if doc_type else ""
            sql = f"""
                SELECT doc_id, doc_type, filename, 1.0 AS score, content
                FROM documents
                WHERE ({conditions}) {type_cond}
                LIMIT ?
            """
            params = like_terms + ([doc_type] if doc_type else []) + [limit]
            rows = self.fetchall(sql, params, use_cache=False)
            return [{"doc_id": r[0], "doc_type": r[1], "filename": r[2], "score": 1.0, "content": r[4]} for r in rows]

    def close(self):
        self.conn.close()

_db_instances = {}

def get_db(db_path: Optional[Path] = None, read_only: bool = True) -> EstateDatabase:
    """Return one connection per resolved database path and access mode.

    Online planner/retriever instances share a read-only connection.  Separate
    processes can therefore read the estate concurrently without taking a
    conflicting writer lock.  The offline builder explicitly requests the
    sole read-write connection.
    """
    path = str(Path(db_path or DEFAULT_DB_PATH).resolve())
    key = (path, read_only)
    if key not in _db_instances:
        _db_instances[key] = EstateDatabase(Path(path), read_only=read_only)
    return _db_instances[key]
