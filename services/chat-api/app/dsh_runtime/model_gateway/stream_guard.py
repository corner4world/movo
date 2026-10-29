"""Retry a provider stream only when it completed without any useful output."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import logging
from typing import Any

from app.llm.base import BaseLLMClient
from app.llm.types import LLMResponse, Message


LOG = logging.getLogger(__name__)


class EmptyModelStreamError(RuntimeError):
    pass


async def nonempty_model_stream(
    client: BaseLLMClient,
    messages: list[Message],
    kwargs: dict[str, Any],
    *,
    model: str,
) -> AsyncIterator[LLMResponse]:
    for attempt in range(2):
        received_output = False
        async for chunk in client.astream(messages, **kwargs):
            if chunk.content or chunk.tool_calls:
                received_output = True
            yield chunk
        if received_output:
            return
        LOG.warning("Model stream contained no text or tool calls", extra={"model": model, "attempt": attempt + 1})
        if attempt == 0:
            await asyncio.sleep(0.25)
    raise EmptyModelStreamError("Model returned no text or tool calls after retry")
