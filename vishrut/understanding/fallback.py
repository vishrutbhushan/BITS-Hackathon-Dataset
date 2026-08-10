"""
Stage 4 escalation path: only called when the local model's output fails
validation (understanding/local_llm.py::validate returns False).

Uses OpenRouter's OpenAI-compatible /chat/completions endpoint so you can
point MODEL at whatever's currently cheap/good there. Requires
OPENROUTER_API_KEY to be set in the environment -- never hardcode a key
in source.

This module is not runnable inside this sandbox (no network egress to
openrouter.ai here, and no key), but is a complete, ready-to-run client
for your laptop. Every call is logged by the caller (pipeline.py), which
is what lets you track escalation rate and cost, and mine failures to
improve the local prompt over time instead of paying for the same
mistake twice.
"""
import json
import os
import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-3.5-haiku"  # swap for whatever's cheap/current on OpenRouter

from understanding.local_llm import PROMPT_TEMPLATE, SHAPE_NAMES


def parse_question(question: str, gazetteer, timeout: int = 30) -> dict:
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
    raw_text = raw_text.strip("`").removeprefix("json").strip()
    return json.loads(raw_text)
