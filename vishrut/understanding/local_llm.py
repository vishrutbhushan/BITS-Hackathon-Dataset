"""
Stage 4 primary path: a small local LLM turns a raw question into
{shape, entities} JSON, selecting entities from gazetteer candidates
rather than generating names freehand.

Runs against Ollama's local HTTP API (http://localhost:11434) -- install
Ollama and `ollama pull qwen2.5:3b` on your machine first. This module
is not runnable inside this sandbox (no local Ollama server here), but
is a complete, ready-to-run client for your laptop.

Kept deliberately dumb: one call, temperature 0, strict JSON, validated
by the caller (pipeline.py) against the gazetteer -- this module doesn't
retry or loop itself, see understanding/fallback.py for escalation.
"""
import json
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the vishrut directory's .env file
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")


SHAPE_NAMES = [
    "absence", "referenced_share", "date_span", "distinct_count",
    "hop_aggregate", "temporal_chain", "avg_work_size",
    "doc_filtered_aggregate", "exclusion_aggregate", "gap_to_threshold",
    "rank_value", "role_split", "threshold_aggregate",
    # extend as you identify the remaining ~8 shapes from the hidden set
]

PROMPT_TEMPLATE = """You are extracting structured intent from a bid-desk question. \
Return ONLY a JSON object, no prose, no markdown fences.

Known reasoning shapes: {shapes}

Candidate client names (pick from this list only, or null if none apply): {client_candidates}
Candidate engineer names (pick from this list only, or null if none apply): {engineer_candidates}
Candidate project names (pick from this list only, or null if none apply): {project_candidates}

Question: {question}

Return JSON with exactly these keys:
{{
  "shape": "<one of the known shapes>",
  "client_name": "<exact string from the candidate list, or null>",
  "engineer_name": "<exact string from the candidate list, or null>",
  "project_name": "<exact string from the candidate list, or null>",
  "threshold_rupees": <number or null, if the question states a target/threshold amount>,
  "grading": "<Excellent|Very Good|Good|Satisfactory|Below Average|Poor, or null>",
  "role": "<Prime|Subcontractor|Joint Venture, or null>",
  "category_to_exclude": "<category string, or null>"
}}
"""


def parse_question(question: str, gazetteer, timeout: int = 30) -> dict:
    """Call the OpenRouter model and return its raw parsed JSON."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    prompt = PROMPT_TEMPLATE.format(
        shapes=", ".join(SHAPE_NAMES),
        client_candidates=gazetteer.candidates_for_prompt(question, "client"),
        engineer_candidates=gazetteer.candidates_for_prompt(question, "engineer"),
        project_candidates=gazetteer.candidates_for_prompt(question, "project"),
        question=question,
    )
    resp = requests.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    raw_text = resp.json()["choices"][0]["message"]["content"].strip()
    # Models sometimes wrap JSON in fences despite instructions -- strip defensively.
    raw_text = raw_text.strip("`").removeprefix("json").strip()
    return json.loads(raw_text)



def validate(parsed: dict, gazetteer) -> bool:
    """Hard validation: shape must be known, any named entity must
    resolve exactly to something in the gazetteer. Returns False (not an
    exception) so the caller can decide to escalate rather than crash.
    """
    if parsed.get("shape") not in SHAPE_NAMES:
        return False
    if parsed.get("client_name") and parsed["client_name"] not in gazetteer.clients:
        return False
    if parsed.get("engineer_name") and parsed["engineer_name"] not in gazetteer.engineers:
        return False
    if parsed.get("project_name") and parsed["project_name"] not in gazetteer.projects:
        return False
    return True
