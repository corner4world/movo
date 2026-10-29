from __future__ import annotations

import asyncio

from app.dsh_runtime.model_gateway.service import ModelGatewayRequest, ModelGatewayService
from app.dsh_runtime.model_gateway.token import ModelGatewayClaims
from app.llm.types import LLMResponse, Message, Role


class SequenceClient:
    def __init__(self, attempts: list[list[LLMResponse]]) -> None:
        self.attempts = attempts
        self.calls = 0

    async def astream(self, _messages, **_kwargs):
        response = self.attempts[self.calls]
        self.calls += 1
        for chunk in response:
            yield chunk


def _chunk(text: str = "", tool_calls=None) -> LLMResponse:
    return LLMResponse(message=Message(role=Role.ASSISTANT, content=text, tool_calls=tool_calls))


async def _events(client: SequenceClient) -> list[dict]:
    async def factory(*_args):
        return client

    request = ModelGatewayRequest(
        profileVersion="profile-a", modelInstanceId="model-a",
        provider="askai-model-gateway", model="test-model",
        messages=[{"role": "user", "content": "test"}],
    )
    claims = ModelGatewayClaims(
        tenant_id="tenant-a", profile_version="profile-a", model_instance_id="model-a",
        issued_at=1, expires_at=2,
    )
    stream = await ModelGatewayService(factory).stream(request, claims)
    return [event async for event in stream]


def test_empty_attempt_retries_then_delivers_text():
    client = SequenceClient([[], [_chunk("answer")]])
    events = asyncio.run(_events(client))
    assert client.calls == 2
    assert [event["type"] for event in events] == ["text-delta", "finish"]
    assert events[0]["text"] == "answer"


def test_repeated_empty_attempt_is_an_error_not_a_success():
    client = SequenceClient([[], []])
    events = asyncio.run(_events(client))
    assert client.calls == 2
    assert [event["type"] for event in events] == ["error"]
    assert events[0]["error"]["code"] == "empty_model_response"
    assert events[0]["error"]["retryable"] is True


def test_existing_text_or_tool_call_is_not_retried():
    text_client = SequenceClient([[_chunk("answer")]])
    assert [event["type"] for event in asyncio.run(_events(text_client))] == ["text-delta", "finish"]
    assert text_client.calls == 1

    tool_client = SequenceClient([[_chunk(tool_calls=[{
        "index": 0, "id": "call-1", "name": "lookup", "arguments": "{}",
    }])]])
    assert [event["type"] for event in asyncio.run(_events(tool_client))] == ["tool-call", "finish"]
    assert tool_client.calls == 1


def test_provider_error_after_text_does_not_retry():
    class InterruptedClient(SequenceClient):
        async def astream(self, _messages, **_kwargs):
            self.calls += 1
            yield _chunk("partial")
            raise RuntimeError("provider stream interrupted")

    client = InterruptedClient([])
    events = asyncio.run(_events(client))
    assert client.calls == 1
    assert [event["type"] for event in events] == ["text-delta", "error"]
