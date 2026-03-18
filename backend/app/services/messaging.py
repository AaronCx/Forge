"""Inter-agent messaging service."""

from typing import Literal

from app.db import get_db

MessageType = Literal["info", "request", "response", "error", "handoff"]


def _validate_index(value: int) -> int:
    """Validate that an agent index is a safe integer."""
    if not isinstance(value, int) or value < 0 or value > 999:
        raise ValueError(f"Invalid agent index: {value}")
    return value


class MessagingService:
    """Handles message passing between agents within a task group."""

    def send(
        self,
        *,
        group_id: str,
        sender_index: int,
        receiver_index: int | None = None,
        message_type: MessageType = "info",
        content: str,
        metadata: dict | None = None,
    ) -> dict:
        """Send a message from one agent to another (or broadcast if receiver is None)."""
        row = {
            "group_id": group_id,
            "sender_index": sender_index,
            "message_type": message_type,
            "content": content,
            "metadata": metadata or {},
        }
        if receiver_index is not None:
            row["receiver_index"] = receiver_index

        result = get_db().table("agent_messages").insert(row).execute()
        return result.data[0] if result.data else row

    def get_messages(
        self,
        group_id: str,
        *,
        receiver_index: int | None = None,
        message_type: MessageType | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get messages for a group, optionally filtered by receiver or type."""
        query = (
            get_db().table("agent_messages")
            .select("*")
            .eq("group_id", group_id)
            .order("created_at")
            .limit(limit)
        )
        if receiver_index is not None:
            idx = _validate_index(receiver_index)
            query = query.or_(f"receiver_index.eq.{idx},receiver_index.is.null")
        if message_type:
            query = query.eq("message_type", message_type)

        result = query.execute()
        return result.data or []

    def get_conversation(
        self,
        group_id: str,
        agent_a: int,
        agent_b: int,
        limit: int = 50,
    ) -> list[dict]:
        """Get messages exchanged between two specific agents."""
        a, b = _validate_index(agent_a), _validate_index(agent_b)
        result = (
            get_db().table("agent_messages")
            .select("*")
            .eq("group_id", group_id)
            .or_(
                f"and(sender_index.eq.{a},receiver_index.eq.{b}),"
                f"and(sender_index.eq.{b},receiver_index.eq.{a})"
            )
            .order("created_at")
            .limit(limit)
            .execute()
        )
        return result.data or []

    def broadcast(
        self,
        *,
        group_id: str,
        sender_index: int,
        content: str,
        message_type: MessageType = "info",
    ) -> dict:
        """Send a broadcast message (no specific receiver)."""
        return self.send(
            group_id=group_id,
            sender_index=sender_index,
            receiver_index=None,
            message_type=message_type,
            content=content,
        )


messaging_service = MessagingService()
