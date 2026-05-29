"""Reusable message-creation service.

Extracted from the inline INSERT in ``routes/messages.py`` so that internal
callers (e.g. the chat-channel close notification) can persist a broker
message without making a self HTTP call back into ``POST /messages/send``.

``create_message`` performs a single row INSERT and returns a plain dict; it
does **not** commit — the caller owns the transaction boundary (commit, or
wrap in ``db.db_transaction(...)``). This mirrors the previous behaviour where
``send_message`` committed once after its recipient loop.
"""

import json
import uuid
from datetime import datetime, timezone


async def create_message(
    db,
    *,
    from_agent: str,
    to_agent: str,
    action: str = "send",
    subject: str = "",
    body: str = "",
    parent_id: str | None = None,
    thread_id: str | None = None,
    attachments: list | None = None,
) -> dict:
    """Insert one ``messages`` row and return its field dict (no commit).

    ``thread_id`` defaults to a fresh UUID (a new thread) when not supplied.
    Identity / cross-tenant validation is the caller's responsibility — this
    helper is a thin persistence primitive.
    """
    msg_id = str(uuid.uuid4())
    resolved_thread_id = thread_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    attachments_list = attachments or []
    attachments_json = json.dumps(attachments_list)

    await db.execute(
        """INSERT INTO messages
               (id, thread_id, from_agent, to_agent, action, subject, body, attachments, is_read, parent_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (msg_id, resolved_thread_id, from_agent, to_agent, action,
         subject, body, attachments_json, parent_id, now),
    )

    return {
        "id": msg_id,
        "thread_id": resolved_thread_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "action": action,
        "subject": subject,
        "body": body,
        "attachments": attachments_list,
        "is_read": False,
        "parent_id": parent_id,
        "created_at": now,
    }
