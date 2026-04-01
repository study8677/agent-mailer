import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Request
from agent_mailer.models import SendRequest, MessageResponse

router = APIRouter()


def _row_to_response(row) -> MessageResponse:
    d = dict(row)
    d["attachments"] = json.loads(d["attachments"])
    d["is_read"] = bool(d["is_read"])
    return MessageResponse(**d)


async def _verify_identity(db, agent_id: str, address: str):
    """Verify that agent_id exists and its address matches the given address."""
    cursor = await db.execute("SELECT address FROM agents WHERE id = ?", (agent_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    if row["address"] != address:
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{agent_id}' does not own address '{address}'",
        )


@router.post("/messages/send", response_model=MessageResponse)
async def send_message(req: SendRequest, request: Request):
    db = request.app.state.db

    # verify sender identity: agent_id must own from_agent address
    await _verify_identity(db, req.agent_id, req.from_agent)

    # validate recipient address exists
    cursor = await db.execute("SELECT id FROM agents WHERE address = ?", (req.to_agent,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail=f"Recipient address '{req.to_agent}' not found")

    # reply/forward require parent_id
    if req.action in ("reply", "forward") and not req.parent_id:
        raise HTTPException(status_code=400, detail="parent_id is required for reply/forward")

    # resolve thread_id
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
    attachments_json = json.dumps(req.attachments)

    await db.execute(
        """INSERT INTO messages (id, thread_id, from_agent, to_agent, action, subject, body, attachments, is_read, parent_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (msg_id, thread_id, req.from_agent, req.to_agent, req.action,
         req.subject, req.body, attachments_json, req.parent_id, now),
    )
    await db.commit()

    return MessageResponse(
        id=msg_id, thread_id=thread_id, from_agent=req.from_agent,
        to_agent=req.to_agent, action=req.action, subject=req.subject,
        body=req.body, attachments=req.attachments, is_read=False,
        parent_id=req.parent_id, created_at=now,
    )


@router.get("/messages/inbox/{address}", response_model=list[MessageResponse])
async def inbox(address: str, request: Request, agent_id: str = Query(...), all: bool = False):
    db = request.app.state.db

    # verify caller identity: agent_id must own this address
    await _verify_identity(db, agent_id, address)

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


@router.get("/messages/thread/{thread_id}", response_model=list[MessageResponse])
async def thread(thread_id: str, request: Request):
    db = request.app.state.db
    cursor = await db.execute(
        "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at",
        (thread_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_response(row) for row in rows]


@router.patch("/messages/{message_id}/read", response_model=MessageResponse)
async def mark_read(message_id: str, request: Request):
    db = request.app.state.db
    await db.execute("UPDATE messages SET is_read = 1 WHERE id = ?", (message_id,))
    await db.commit()
    cursor = await db.execute("SELECT * FROM messages WHERE id = ?", (message_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    return _row_to_response(row)
