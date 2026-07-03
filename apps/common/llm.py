from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from apps.common.config import get_config
from apps.common.logging import get_logger

logger = get_logger("apps.common.llm")


def get_llm_client() -> anthropic.Anthropic:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY is required for LLM calls")
    return anthropic.Anthropic()


def complete_json(
    system: str,
    user: str,
    schema: dict[str, Any],
    max_tokens: int = 16000,
) -> dict[str, Any]:
    """One-shot LLM call with a guaranteed-JSON response (structured outputs)."""
    config = get_config()
    client = get_llm_client()

    response = client.messages.create(
        model=config.llm_model,
        max_tokens=max_tokens,
        system=system,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": user}],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("LLM refused the request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("LLM response truncated: increase max_tokens")

    logger.info(
        "llm call completed",
        extra={
            "model": config.llm_model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    )

    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)
