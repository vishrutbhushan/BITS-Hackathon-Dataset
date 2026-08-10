"""
Integration test: runs answer_question() end-to-end with a FAKE
understanding layer (no Ollama/OpenRouter needed) to prove the wiring
between Stage 4's output shape and Stage 5's dispatcher kwargs is
correct. Real local_llm.parse_question is swapped out via monkeypatch.
"""
import unittest
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.schema import get_connection, upsert_client, upsert_engineer
import pipeline
from understanding.entity_match import Gazetteer
from understanding import local_llm


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return {"response": json.dumps(self._payload)}


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
        self.gazetteer = Gazetteer(self.con)

    def test_absence_shape_end_to_end(self):
        fake_parsed = {
            "shape": "absence", "client_name": "Jal Nigam, Jharkhand",
            "engineer_name": None, "project_name": None,
            "threshold_rupees": None, "grading": None, "role": None,
            "category_to_exclude": None,
        }
        original = local_llm.parse_question
        local_llm.parse_question = lambda q, g: fake_parsed
        try:
            answer, meta = pipeline.answer_question(
                self.con, self.gazetteer, "how many works have no reference letter?"
            )
            self.assertEqual(answer, 2)
            self.assertEqual(meta["path"], "local")
        finally:
            local_llm.parse_question = original

    def test_referenced_share_end_to_end(self):
        fake_parsed = {
            "shape": "referenced_share", "client_name": "Jal Nigam, Jharkhand",
            "engineer_name": None, "project_name": None,
            "threshold_rupees": None, "grading": None, "role": None,
            "category_to_exclude": None,
        }
        original = local_llm.parse_question
        local_llm.parse_question = lambda q, g: fake_parsed
        try:
            answer, meta = pipeline.answer_question(
                self.con, self.gazetteer, "what percent have a reference letter?"
            )
            self.assertEqual(answer, 33.33)
        finally:
            local_llm.parse_question = original

    def test_invalid_client_triggers_fallback_path(self):
        # local model proposes a client name NOT in the gazetteer ->
        # must escalate rather than silently proceed with garbage.
        bad_parsed = {
            "shape": "absence", "client_name": "Not A Real Client",
            "engineer_name": None, "project_name": None,
            "threshold_rupees": None, "grading": None, "role": None,
            "category_to_exclude": None,
        }
        good_parsed = {
            "shape": "absence", "client_name": "Jal Nigam, Jharkhand",
            "engineer_name": None, "project_name": None,
            "threshold_rupees": None, "grading": None, "role": None,
            "category_to_exclude": None,
        }
        orig_local = local_llm.parse_question
        local_llm.parse_question = lambda q, g: bad_parsed

        import understanding.fallback as fallback_module
        orig_fallback = fallback_module.parse_question
        fallback_module.parse_question = lambda q, g: good_parsed

        try:
            answer, meta = pipeline.answer_question(
                self.con, self.gazetteer, "how many works have no reference letter?"
            )
            self.assertEqual(answer, 2)
            self.assertEqual(meta["path"], "fallback")
        finally:
            local_llm.parse_question = orig_local
            fallback_module.parse_question = orig_fallback


if __name__ == "__main__":
    unittest.main()
