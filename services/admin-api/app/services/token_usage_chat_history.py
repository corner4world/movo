"""Resolve a model call to persisted, user-visible conversation messages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId


def _format_time(value: Any) -> str | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _payload(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(message.get("_id")),
        "role": str(message.get("role") or ""),
        "content": str(message.get("content") or ""),
        "plan": message.get("plan") or None,
        "progress": message.get("progress") or None,
        "documents": message.get("documents") or [],
        "images": message.get("images") or [],
        "createdAt": _format_time(message.get("created_at")),
    }


async def load_visible_turn(db: Any, row: dict[str, Any], main_id: str, *, language: str = "zh") -> dict[str, Any]:
    """Return the real turn when a call can be tied to a tenant's conversation.

    Model prompts and raw responses are deliberately excluded: they can contain
    system instructions, tool results, or provider-specific payloads.
    """
    session_id = str(row.get("session_id") or "").strip()
    fallback_title = "Conversation details" if language.lower().startswith("en") else "对话详情"
    request_id = str(row.get("user_request_id") or "").strip()
    assistant = None
    session_oid = None

    if session_id.startswith("dsh-"):
        binding = await db.agent_kernel_bindings.find_one(
            {"kernel_session_id": session_id, "tenant_id": main_id},
            {"conversation_id": 1},
        )
        conversation_id = str((binding or {}).get("conversation_id") or "")
        if ObjectId.is_valid(conversation_id):
            session_oid = ObjectId(conversation_id)

    if request_id:
        query: dict[str, Any] = {
            "main_id": main_id,
            "message_id": request_id,
            "role": "assistant",
            "message_type": {"$ne": "context_summary"},
        }
        if session_oid:
            query["session_id"] = session_oid
        assistant = await db.chat_messages.find_one(query)
        if assistant and session_oid is None:
            session_oid = assistant.get("session_id")

    if session_oid is None:
        return {"sessionId": "", "title": fallback_title, "messages": []}

    session = await db.chat_sessions.find_one(
        {"_id": session_oid, "main_id": main_id}, {"title": 1}
    )
    if not session:
        return {"sessionId": "", "title": fallback_title, "messages": []}

    if assistant is None and session_id.startswith("dsh-"):
        call_time = row.get("created_at")
        if isinstance(call_time, datetime):
            user = await db.chat_messages.find_one(
                {
                    "main_id": main_id,
                    "session_id": session_oid,
                    "role": "user",
                    "runtime_owner": "dsh",
                    "created_at": {"$lte": call_time},
                },
                sort=[("seq", -1)],
            )
            if user:
                assistant = await db.chat_messages.find_one(
                    {
                        "main_id": main_id,
                        "session_id": session_oid,
                        "role": "assistant",
                        "runtime_owner": "dsh",
                        "seq": int(user.get("seq") or 0) + 1,
                    }
                )

    messages = []
    if assistant:
        user = await db.chat_messages.find_one(
            {
                "main_id": main_id,
                "session_id": session_oid,
                "role": "user",
                "message_type": {"$ne": "context_summary"},
                "seq": {"$lt": int(assistant.get("seq") or 0)},
            },
            sort=[("seq", -1)],
        )
        if user:
            messages.append(_payload(user))
        messages.append(_payload(assistant))

    return {
        "sessionId": str(session_oid),
        "title": str(session.get("title") or fallback_title),
        "messages": messages,
    }
