import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from agent_mailer.models import AdminSendRequest, AgentStats, MessageResponse

router = APIRouter(prefix="/admin")

HUMAN_OPERATOR_ID = "00000000-0000-0000-0000-000000000000"
HUMAN_OPERATOR_ADDRESS = "human-operator@local"

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _row_to_response(row) -> MessageResponse:
    d = dict(row)
    d["attachments"] = json.loads(d["attachments"])
    d["is_read"] = bool(d["is_read"])
    return MessageResponse(**d)


async def _ensure_human_operator(db):
    """Lazily register the human-operator agent if it doesn't exist."""
    await db.execute(
        """INSERT OR IGNORE INTO agents (id, name, address, role, description, system_prompt, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            HUMAN_OPERATOR_ID,
            "Human Operator",
            HUMAN_OPERATOR_ADDRESS,
            "operator",
            "Human operator via WebUI",
            "",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await db.commit()


@router.get("/agents/stats", response_model=list[AgentStats])
async def agents_stats(request: Request):
    db = request.app.state.db
    cursor = await db.execute("""
        SELECT
            a.id AS agent_id,
            a.name,
            a.address,
            a.role,
            COALESCE(recv.total, 0) AS messages_received,
            COALESCE(recv.read_count, 0) AS messages_read,
            COALESCE(recv.total, 0) - COALESCE(recv.read_count, 0) AS messages_unread,
            COALESCE(sent.total, 0) AS messages_sent,
            COALESCE(sent.reply_count, 0) AS messages_replied,
            COALESCE(sent.forward_count, 0) AS messages_forwarded
        FROM agents a
        LEFT JOIN (
            SELECT to_agent,
                   COUNT(*) AS total,
                   SUM(CASE WHEN is_read = 1 THEN 1 ELSE 0 END) AS read_count
            FROM messages GROUP BY to_agent
        ) recv ON recv.to_agent = a.address
        LEFT JOIN (
            SELECT from_agent,
                   COUNT(*) AS total,
                   SUM(CASE WHEN action = 'reply' THEN 1 ELSE 0 END) AS reply_count,
                   SUM(CASE WHEN action = 'forward' THEN 1 ELSE 0 END) AS forward_count
            FROM messages GROUP BY from_agent
        ) sent ON sent.from_agent = a.address
        ORDER BY a.created_at
    """)
    rows = await cursor.fetchall()
    return [AgentStats(**dict(row)) for row in rows]


@router.get("/messages/inbox/{address}", response_model=list[MessageResponse])
async def admin_inbox(address: str, request: Request, all: bool = False):
    """Peek at any agent's inbox without identity verification."""
    db = request.app.state.db
    if all:
        cursor = await db.execute(
            "SELECT * FROM messages WHERE to_agent = ? ORDER BY created_at",
            (address,),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM messages WHERE to_agent = ? AND is_read = 0 ORDER BY created_at",
            (address,),
        )
    rows = await cursor.fetchall()
    return [_row_to_response(row) for row in rows]


@router.post("/messages/send", response_model=MessageResponse)
async def admin_send(req: AdminSendRequest, request: Request):
    """Send a message as the human operator."""
    db = request.app.state.db

    await _ensure_human_operator(db)

    # validate recipient address exists
    cursor = await db.execute("SELECT id FROM agents WHERE address = ?", (req.to_agent,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail=f"Recipient address '{req.to_agent}' not found")

    if req.action in ("reply", "forward") and not req.parent_id:
        raise HTTPException(status_code=400, detail="parent_id is required for reply/forward")

    if req.action == "send":
        thread_id = str(uuid.uuid4())
    else:
        cursor = await db.execute("SELECT thread_id FROM messages WHERE id = ?", (req.parent_id,))
        parent = await cursor.fetchone()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent message not found")
        thread_id = parent["thread_id"]

    msg_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO messages (id, thread_id, from_agent, to_agent, action, subject, body, attachments, is_read, parent_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (msg_id, thread_id, HUMAN_OPERATOR_ADDRESS, req.to_agent, req.action,
         req.subject, req.body, "[]", req.parent_id, now),
    )
    await db.commit()

    return MessageResponse(
        id=msg_id, thread_id=thread_id, from_agent=HUMAN_OPERATOR_ADDRESS,
        to_agent=req.to_agent, action=req.action, subject=req.subject,
        body=req.body, attachments=[], is_read=False,
        parent_id=req.parent_id, created_at=now,
    )


@router.get("/ui", response_class=HTMLResponse)
async def ui():
    html_path = STATIC_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
