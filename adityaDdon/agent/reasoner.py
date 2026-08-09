"""
reasoner.py — LLM & Deterministic Computation Node
Combines LLM multi-hop reasoning (via OpenRouter) with deterministic mathematical verification.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv
from openai import OpenAI

from retriever import RetrievalContext

# Load environment variables
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")

class ReasonerNode:
    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm and bool(OPENROUTER_API_KEY)
        if self.use_llm:
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=OPENROUTER_API_KEY
            )
        else:
            self.client = None

    def reason(self, context: RetrievalContext) -> Union[int, float]:
        """
        Derives the exact numeric answer from question + DAG execution context.
        """
        candidate = context.candidate_answer

        # If we have a deterministic candidate from relational execution, prioritize/verify it
        if candidate is not None:
            # Format candidate according to expected metric type
            if isinstance(candidate, float):
                return round(candidate, 2)
            if isinstance(candidate, (int, float)):
                return candidate

        # If candidate is None or we need LLM reasoning on complex unstructured queries
        if self.use_llm and self.client:
            try:
                llm_ans = self._query_llm(context)
                if llm_ans is not None:
                    return llm_ans
            except Exception as e:
                print(f"[Reasoner] LLM call error: {e}, falling back to candidate math")

        # Fallback to candidate or 0
        if candidate is not None:
            return candidate
        return 0

    def _query_llm(self, context: RetrievalContext) -> Optional[Union[int, float]]:
        prompt = f"""You are an expert bid intelligence and financial auditor answering questions on an infrastructure construction document estate.

QUESTION:
{context.plan.question}

EXECUTION PLAN & RETRIEVED EVIDENCE FROM DUCKDB:
{context.evidence_text}

INSTRUCTIONS:
1. Read the retrieved facts and evidence carefully.
2. Carry out any required arithmetic (lossless integer Indian Rupees, days difference, or percentage out of 100).
3. If money, output plain integer rupees (e.g. 537933333, not in Cr or Lakh).
4. If percentage, output number out of 100 (e.g. 33.33 or 66.67, NOT 0.3333).
5. If days, output integer number of days.
6. If count, output integer count.
7. Return ONLY a valid JSON object with key "answer" containing the single plain number. Example: {{"answer": 537933333}}
"""
        response = self.client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        
        # Extract JSON object
        m_json = re.search(r'\{.*?"answer"\s*:\s*([-\d.]+).*?\}', content, re.S)
        if m_json:
            ans_val = float(m_json.group(1))
            return int(ans_val) if ans_val.is_integer() else round(ans_val, 2)

        # Fallback number regex
        m_num = re.search(r'([-\d]+(?:\.\d+)?)', content)
        if m_num:
            ans_val = float(m_num.group(1))
            return int(ans_val) if ans_val.is_integer() else round(ans_val, 2)

        return None
