"""
Integration test: runs answer_question() end-to-end with a FAKE LLM
(no Ollama needed) to verify the Text-to-SQL wiring is correct.

We monkeypatch local_llm.text_to_sql to return a hand-written SQL query,
then verify the pipeline executes it correctly against the in-memory DB
and formats the answer.
"""
import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.schema import get_connection, upsert_client, upsert_engineer
import pipeline
from understanding import local_llm


class TestPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.con = get_connection()
        cid = upsert_client(self.con, "Jal Nigam, Jharkhand")
        for v, ref in [(730200000, 1), (814400000, 0), (69200000, 0)]:
            self.con.execute(
                """INSERT INTO projects
                   (name, client_id, category, value_rupees, has_reference_letter, source_doc_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f"project-{v}", cid, "other", v, ref, "test"),
            )
        self.con.commit()

    def _patch_sql(self, sql):
        """Monkeypatch text_to_sql to return a fixed SQL string."""
        orig = local_llm.text_to_sql
        local_llm.text_to_sql = lambda q, c, **kw: sql
        return orig

    def test_absence_count_via_sql(self):
        """Pipeline correctly counts projects with no reference letter."""
        sql = ("SELECT COUNT(*) FROM projects p "
               "JOIN clients c ON p.client_id=c.client_id "
               "WHERE c.name='Jal Nigam, Jharkhand' AND p.has_reference_letter=0")
        orig = self._patch_sql(sql)
        try:
            answer, meta = pipeline.answer_question(
                self.con, "how many works have no reference letter?", answer_type="count"
            )
            self.assertEqual(answer, 2)
            self.assertEqual(meta["shape"], "text_to_sql")
        finally:
            local_llm.text_to_sql = orig

    def test_referenced_share_via_sql(self):
        """Pipeline correctly computes percent with reference letter."""
        sql = ("SELECT ROUND(100.0 * SUM(p.has_reference_letter) / COUNT(*), 2) "
               "FROM projects p JOIN clients c ON p.client_id=c.client_id "
               "WHERE c.name='Jal Nigam, Jharkhand'")
        orig = self._patch_sql(sql)
        try:
            answer, meta = pipeline.answer_question(
                self.con, "what percent have a reference letter?", answer_type="percent"
            )
            self.assertEqual(answer, 33.33)
        finally:
            local_llm.text_to_sql = orig

    def test_sql_error_triggers_rag_fallback(self):
        """A broken SQL query must trigger the RAG fallback."""
        orig_sql = local_llm.text_to_sql
        orig_rag = pipeline._rag_fallback
        called_rag = []

        local_llm.text_to_sql = lambda q, c, **kw: "SELECT * FROM nonexistent_table"
        pipeline._rag_fallback = lambda q, atype, log: (
            called_rag.append(q), (999, {"shape": "rag_fallback", "path": "rag"})
        )[1]

        try:
            answer, meta = pipeline.answer_question(
                self.con, "how many works have no reference letter?", answer_type="count"
            )
            self.assertEqual(answer, 999)
            self.assertEqual(meta["shape"], "rag_fallback")
            self.assertEqual(len(called_rag), 1)
        finally:
            local_llm.text_to_sql = orig_sql
            pipeline._rag_fallback = orig_rag

    def test_null_sql_result_triggers_rag_fallback(self):
        """An empty SQL result (no rows) must trigger the RAG fallback."""
        orig_sql = local_llm.text_to_sql
        orig_rag = pipeline._rag_fallback
        called_rag = []

        # Query returns no rows
        local_llm.text_to_sql = lambda q, c, **kw: (
            "SELECT COUNT(*) FROM projects WHERE 1=0 AND 1=1"
        )
        pipeline._rag_fallback = lambda q, atype, log: (
            called_rag.append(q), (0, {"shape": "rag_fallback", "path": "rag"})
        )[1]

        try:
            # COUNT(*) on empty set returns 0, not NULL — so test with None-returning query
            local_llm.text_to_sql = lambda q, c, **kw: (
                "SELECT value_rupees FROM projects WHERE name='DOES_NOT_EXIST'"
            )
            answer, meta = pipeline.answer_question(
                self.con, "some question", answer_type="money"
            )
            self.assertEqual(meta["shape"], "rag_fallback")
        finally:
            local_llm.text_to_sql = orig_sql
            pipeline._rag_fallback = orig_rag


if __name__ == "__main__":
    unittest.main()
