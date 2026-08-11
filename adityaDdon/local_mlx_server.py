#!/usr/bin/env python3
"""Small production adapter around the MLX-VLM OpenAI-compatible server.

Qwen's default chat template enables long reasoning traces. The agent only
needs a typed routing decision, so this adapter disables thinking at template
render time. This cuts latency and prevents reasoning text from consuming the
JSON output budget without changing model weights or answer computation.
"""

from __future__ import annotations

import argparse
from functools import wraps

import uvicorn
import mlx_vlm.server as mlx_server
import mlx_vlm.prompt_utils as prompt_utils


_apply_chat_template = mlx_server.apply_chat_template
_get_chat_template = prompt_utils.get_chat_template


@wraps(_get_chat_template)
def _get_template_without_thinking(*args, **kwargs):
    kwargs["enable_thinking"] = False
    return _get_chat_template(*args, **kwargs)


@wraps(_apply_chat_template)
def _apply_without_thinking(*args, **kwargs):
    kwargs["enable_thinking"] = False
    return _apply_chat_template(*args, **kwargs)


mlx_server.apply_chat_template = _apply_without_thinking
prompt_utils.get_chat_template = _get_template_without_thinking


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Qwen MLX control-plane server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    uvicorn.run(mlx_server.app, host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
