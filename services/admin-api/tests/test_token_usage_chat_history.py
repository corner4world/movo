import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bson import ObjectId

from app.services.token_usage_chat_history import load_visible_turn


def test_dsh_call_displays_persisted_turn_without_internal_prompt() -> None:
    conversation_id = ObjectId()
    user = {
        "_id": ObjectId(), "role": "user", "content": "请继续", "seq": 3,
        "created_at": datetime(2026, 9, 28, 8, 0),
    }
    assistant = {
        "_id": ObjectId(), "role": "assistant", "content": "好的", "seq": 4,
        "created_at": datetime(2026, 9, 28, 8, 1),
    }
    db = SimpleNamespace(
        agent_kernel_bindings=SimpleNamespace(find_one=AsyncMock(return_value={"conversation_id": str(conversation_id)})),
        chat_sessions=SimpleNamespace(find_one=AsyncMock(return_value={"title": "真实标题"})),
        chat_messages=SimpleNamespace(find_one=AsyncMock(side_effect=[user, assistant, user])),
    )
    row = {
        "session_id": "dsh-kernel", "created_at": datetime(2026, 9, 28, 8, 2),
        "prompt": "INTERNAL SYSTEM PROMPT", "response_payload": {"output": "RAW MODEL OUTPUT"},
    }

    result = asyncio.run(load_visible_turn(db, row, "tenant-a"))

    assert result["sessionId"] == str(conversation_id)
    assert result["title"] == "真实标题"
    assert [message["content"] for message in result["messages"]] == ["请继续", "好的"]
    assert db.agent_kernel_bindings.find_one.await_args.args[0]["tenant_id"] == "tenant-a"
    assert db.chat_sessions.find_one.await_args.args[0]["main_id"] == "tenant-a"


def test_unlinked_call_does_not_turn_prompt_into_user_message() -> None:
    db = SimpleNamespace(
        agent_kernel_bindings=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        chat_messages=SimpleNamespace(find_one=AsyncMock()),
    )

    result = asyncio.run(load_visible_turn(
        db, {"session_id": "dsh-other", "prompt": "SECRET SYSTEM PROMPT"}, "tenant-a"
    ))

    assert result["messages"] == []
    db.chat_messages.find_one.assert_not_awaited()


def test_unlinked_call_uses_english_fallback_title() -> None:
    db = SimpleNamespace(
        agent_kernel_bindings=SimpleNamespace(find_one=AsyncMock(return_value=None)),
    )
    result = asyncio.run(load_visible_turn(
        db, {"session_id": "dsh-other"}, "tenant-a", language="en-US",
    ))
    assert result["title"] == "Conversation details"


def test_legacy_request_uses_saved_assistant_and_previous_user() -> None:
    conversation_id = ObjectId()
    assistant = {"_id": ObjectId(), "role": "assistant", "content": "回答", "seq": 2}
    user = {"_id": ObjectId(), "role": "user", "content": "问题", "seq": 1}
    db = SimpleNamespace(
        chat_sessions=SimpleNamespace(find_one=AsyncMock(return_value={"title": "会话"})),
        chat_messages=SimpleNamespace(find_one=AsyncMock(side_effect=[
            {**assistant, "session_id": conversation_id}, user,
        ])),
    )

    result = asyncio.run(load_visible_turn(
        db, {"user_request_id": "msg-1", "prompt": "INTERNAL"}, "tenant-a"
    ))

    assert [message["content"] for message in result["messages"]] == ["问题", "回答"]
    first_query = db.chat_messages.find_one.await_args_list[0].args[0]
    assert first_query["main_id"] == "tenant-a"
    assert first_query["role"] == "assistant"
