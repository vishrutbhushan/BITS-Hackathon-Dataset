"""Deterministic terminal result selector.

Model inference belongs to ``agentic_controller.py`` and can select only typed
plans/tools.  Keeping the answer node deterministic prevents an otherwise
plausible language-model response from bypassing exact database arithmetic.
"""

from typing import Union

from retriever import RetrievalContext

class ReasonerNode:
    def __init__(self, use_llm: bool = True):
        # Retained for call-site compatibility.  Direct answer generation is
        # intentionally disabled even when callers pass ``use_llm=True``.
        self.use_llm = False

    def reason(self, context: RetrievalContext) -> Union[int, float]:
        """
        Derives the exact numeric answer from question + DAG execution context.
        """
        candidate = context.candidate_answer

        if candidate is not None and isinstance(candidate, (int, float)):
            # Precision is operator/type-specific.  The pipeline owns the
            # output boundary (percent=2 places, BOQ quantity=3, integer INR),
            # so this node must not silently collapse every float to 2 places.
            return candidate
        return 0
