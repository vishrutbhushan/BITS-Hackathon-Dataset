import os
import duckdb
from pathlib import Path
from typing import List, Dict, Any, Optional

DB_DIR = Path(__file__).parent
DEFAULT_DB_PATH = DB_DIR / "estate.duckdb"

class EstateDatabase:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self.conn = duckdb.connect(self.db_path)
        self._init_extensions()

    def _init_extensions(self):
        try:
            self.conn.execute("INSTALL fts; LOAD fts;")
        except Exception as e:
            pass

    def execute(self, query: str, parameters: Optional[list] = None):
        if parameters:
            return self.conn.execute(query, parameters)
        return self.conn.execute(query)

    def fetchall(self, query: str, parameters: Optional[list] = None) -> List[tuple]:
        return self.execute(query, parameters).fetchall()

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
            filter_clause = f"AND doc_type = '{doc_type}'" if doc_type else ""
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
            rows = self.fetchall(sql, [clean_q, limit])
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
            type_cond = f"AND doc_type = '{doc_type}'" if doc_type else ""
            sql = f"""
                SELECT doc_id, doc_type, filename, 1.0 AS score, content
                FROM documents
                WHERE ({conditions}) {type_cond}
                LIMIT ?
            """
            rows = self.fetchall(sql, like_terms + [limit])
            return [{"doc_id": r[0], "doc_type": r[1], "filename": r[2], "score": 1.0, "content": r[4]} for r in rows]

    def close(self):
        self.conn.close()

_db_instance = None

def get_db(db_path: Optional[Path] = None) -> EstateDatabase:
    global _db_instance
    if _db_instance is None or db_path is not None:
        _db_instance = EstateDatabase(db_path)
    return _db_instance
