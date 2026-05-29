"""Realtime chat channels — point-to-point MVP (PRD P0).

Two consumer surfaces share the channel tables:

* **Agents** (skills `agentstartchat` / `agentjoinchat`) hit the unprefixed
  ``/channels/*`` routes authenticated by ``X-API-Key`` (``get_api_key_user``).
  The acting agent is identified by an explicit ``agent_id`` in the body and
  verified to belong to the key's user — mirroring ``POST /messages/send``.

* **Human operators** hit ``/admin/channels/*`` (cookie session via
  ``get_current_user``) for the observability page + Close / Continue
  kill-switch. Scope = channels the operator participates in (a member agent
  they own, or they own the creator address).

Cross-tenant: any agent holding a valid ``join_token`` may join, regardless of
which owner created the channel. The joiner still authenticates with their own
key; we only verify the acting agent belongs to *that* caller — never that it
shares the creator's owner. Closing invalidates the token (join / post / etc.
all reject once ``status != 'open'``).
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agent_mailer.config import DOMAIN
from agent_mailer.db import db_transaction
from agent_mailer.dependencies import get_api_key_user, get_current_user
from agent_mailer.models import (
    AdminChannelCloseRequest,
    AdminChannelContinueRequest,
    ChannelCloseRequest,
    ChannelContinueRequest,
    ChannelCreateRequest,
    ChannelCreateResponse,
    ChannelInfo,
    ChannelJoinRequest,
    ChannelJoinResponse,
    ChannelMemberItem,
    ChannelMessageItem,
    ChannelMessagesResponse,
    ChannelPostMessageRequest,
    ChannelPostMessageResponse,
)
from agent_mailer.services.messaging import create_message

router = APIRouter()
admin_router = APIRouter(prefix="/admin")

# --- Guardrail defaults (PRD §2.5) ---
DEFAULT_MAX_TURNS = 10
DEFAULT_TTL_MINUTES = 30
DEFAULT_EXTEND_TURNS = 10
DEFAULT_EXTEND_MINUTES = 30
MAX_MEMBERS = 2  # point-to-point MVP

# base62 alphabet — unambiguous in `/agentjoinchat #<token>` (no -/_ like base64url).
_TOKEN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_TOKEN_LEN = 22  # 22 * log2(62) ≈ 131 bits ≫ 96-bit floor


# ── helpers ─────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_token() -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LEN))


def _human_operator_id(user_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, user_id))


def _human_operator_address(username: str) -> str:
    return f"human-operator@{username}.{DOMAIN}"


async def _resolve_acting_agent(db, agent_id: str, user_id: str) -> dict:
    """Verify ``agent_id`` exists and belongs to the calling user; return its row."""
    cursor = await db.execute(
        "SELECT id, address, user_id FROM agents WHERE id = ?", (agent_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    if row["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Agent does not belong to current user")
    return dict(row)


async def _channel_by_token(db, token: str) -> dict:
    cursor = await db.execute("SELECT * FROM channels WHERE join_token = ?", (token,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")
    return dict(row)


async def _members(db, channel_id: str) -> list[dict]:
    cursor = await db.execute(
        "SELECT agent_id, agent_address, role, joined_at FROM channel_members "
        "WHERE channel_id = ? ORDER BY joined_at",
        (channel_id,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def _require_member(db, channel_id: str, agent_id: str) -> dict:
    cursor = await db.execute(
        "SELECT * FROM channel_members WHERE channel_id = ? AND agent_id = ?",
        (channel_id, agent_id),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Acting agent is not a member of this channel")
    return dict(row)


async def _maybe_expire(db, channel: dict) -> dict:
    """Lazily flip an ``open`` channel to ``pending_human`` once its TTL passes.

    Returns the (possibly mutated) channel dict. Persisted immediately so the
    pause is visible to every consumer, not just this request.
    """
    if channel["status"] != "open":
        return channel
    if channel["ttl_expires_at"] and _now() > channel["ttl_expires_at"]:
        async with db_transaction(db):
            await db.execute(
                "UPDATE channels SET status = 'pending_human', close_reason = 'ttl' WHERE id = ?",
                (channel["id"],),
            )
        channel = {**channel, "status": "pending_human", "close_reason": "ttl"}
    return channel


async def _channel_info(db, channel: dict) -> ChannelInfo:
    members = await _members(db, channel["id"])
    return ChannelInfo(
        id=channel["id"],
        join_token=channel["join_token"],
        creator_agent=channel["creator_agent"],
        initial_prompt=channel["initial_prompt"],
        status=channel["status"],
        max_turns=channel["max_turns"],
        turn_count=channel["turn_count"],
        ttl_expires_at=channel["ttl_expires_at"],
        created_at=channel["created_at"],
        closed_at=channel["closed_at"],
        close_reason=channel["close_reason"],
        members=[
            ChannelMemberItem(
                agent_address=m["agent_address"], role=m["role"], joined_at=m["joined_at"]
            )
            for m in members
        ],
    )


async def _history(db, channel_id: str, since_seq: int = 0) -> list[ChannelMessageItem]:
    cursor = await db.execute(
        "SELECT seq, from_agent, body, created_at FROM channel_messages "
        "WHERE channel_id = ? AND seq > ? ORDER BY seq",
        (channel_id, since_seq),
    )
    return [
        ChannelMessageItem(
            seq=r["seq"], from_agent=r["from_agent"], body=r["body"], created_at=r["created_at"]
        )
        for r in await cursor.fetchall()
    ]


async def _ensure_human_operator(db, user_id: str, username: str) -> str:
    """Return the owner's human-operator inbox address, creating the agent if absent."""
    op_id = _human_operator_id(user_id)
    op_address = _human_operator_address(username)
    cursor = await db.execute(
        "SELECT id FROM agents WHERE id = ? OR address = ?", (op_id, op_address)
    )
    if not await cursor.fetchone():
        await db.execute(
            """INSERT INTO agents (id, name, address, role, description, system_prompt, user_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (op_id, "Human Operator", op_address, "operator",
             "Human operator via WebUI", "", user_id, _now()),
        )
        await db.commit()
    return op_address


async def _notify_owners_closed(db, channel: dict, members: list[dict]) -> None:
    """Best-effort station-internal close notice — one per distinct owner.

    Owner resolution: ``channel_members.agent_id → agents.user_id → users``;
    notice is delivered to that owner's ``human-operator@<username>.<DOMAIN>``
    inbox (the established per-owner station address, see admin._ensure_human_operator).
    De-duplicated by owner so an owner with both seats gets a single message.
    """
    seen: set[str] = set()
    for m in members:
        try:
            cursor = await db.execute(
                "SELECT a.user_id AS uid, u.username AS uname "
                "FROM agents a JOIN users u ON u.id = a.user_id WHERE a.id = ?",
                (m["agent_id"],),
            )
            row = await cursor.fetchone()
            if not row or not row["uid"] or row["uid"] in seen:
                continue
            seen.add(row["uid"])
            op_address = await _ensure_human_operator(db, row["uid"], row["uname"])
            body = (
                f"实时聊天 channel 已关闭。\n\n"
                f"- 发起方: `{channel['creator_agent']}`\n"
                f"- 关闭原因: `{channel.get('close_reason') or 'human'}`\n"
                f"- 轮次: {channel['turn_count']}/{channel['max_turns']}\n"
                f"- channel id: `{channel['id']}`\n\n"
                f"该 channel 的 join token 已失效，无法再加入或发消息。"
            )
            await create_message(
                db,
                from_agent=f"chat-channel@{DOMAIN}",
                to_agent=op_address,
                action="send",
                subject="实时聊天 channel 已关闭",
                body=body,
            )
            await db.commit()
        except Exception:
            # Notification is best-effort — never let it undo the close.
            continue


async def _close_channel(db, channel: dict, reason: str) -> dict:
    """Transition a channel to ``closed`` (idempotent) and fire owner notices once."""
    if channel["status"] == "closed":
        return channel
    members = await _members(db, channel["id"])
    async with db_transaction(db):
        await db.execute(
            "UPDATE channels SET status = 'closed', closed_at = ?, close_reason = ? WHERE id = ?",
            (_now(), reason, channel["id"]),
        )
    channel = {**channel, "status": "closed", "closed_at": _now(), "close_reason": reason}
    await _notify_owners_closed(db, channel, members)
    return channel


# ══════════════════════════════════════════════════════════════════════
# Agent-facing routes (X-API-Key)
# ══════════════════════════════════════════════════════════════════════


@router.post("/channels", response_model=ChannelCreateResponse)
async def create_channel(
    req: ChannelCreateRequest, request: Request, user: dict = Depends(get_api_key_user)
):
    db = request.app.state.db
    agent = await _resolve_acting_agent(db, req.agent_id, user["id"])

    channel_id = str(uuid.uuid4())
    token = _gen_token()
    now = _now()
    ttl = (datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_TTL_MINUTES)).isoformat()

    async with db_transaction(db):
        await db.execute(
            """INSERT INTO channels
                   (id, join_token, creator_agent, initial_prompt, status, max_turns, turn_count, ttl_expires_at, created_at)
               VALUES (?, ?, ?, ?, 'open', ?, 0, ?, ?)""",
            (channel_id, token, agent["address"], req.initial_prompt, DEFAULT_MAX_TURNS, ttl, now),
        )
        await db.execute(
            """INSERT INTO channel_members (channel_id, agent_id, agent_address, role, joined_at)
               VALUES (?, ?, ?, 'creator', ?)""",
            (channel_id, agent["id"], agent["address"], now),
        )
    return ChannelCreateResponse(id=channel_id, join_token=token)


@router.post("/channels/{token}/join", response_model=ChannelJoinResponse)
async def join_channel(
    token: str, req: ChannelJoinRequest, request: Request, user: dict = Depends(get_api_key_user)
):
    db = request.app.state.db
    agent = await _resolve_acting_agent(db, req.agent_id, user["id"])
    channel = await _channel_by_token(db, token)
    channel = await _maybe_expire(db, channel)

    # Already a member → idempotent replay (no status gate, so a creator can
    # re-fetch history even after the channel paused).
    existing = await db.execute(
        "SELECT 1 FROM channel_members WHERE channel_id = ? AND agent_id = ?",
        (channel["id"], req.agent_id),
    )
    if await existing.fetchone():
        return ChannelJoinResponse(
            channel=await _channel_info(db, channel),
            history=await _history(db, channel["id"]),
        )

    if channel["status"] != "open":
        raise HTTPException(status_code=409, detail=f"Channel is {channel['status']}, cannot join")

    members = await _members(db, channel["id"])
    if len(members) >= MAX_MEMBERS:
        raise HTTPException(status_code=409, detail="Channel is full (point-to-point MVP allows 2 members)")

    async with db_transaction(db):
        await db.execute(
            """INSERT INTO channel_members (channel_id, agent_id, agent_address, role, joined_at)
               VALUES (?, ?, ?, 'member', ?)""",
            (channel["id"], agent["id"], agent["address"], _now()),
        )
    return ChannelJoinResponse(
        channel=await _channel_info(db, channel),
        history=await _history(db, channel["id"]),
    )


@router.post("/channels/{token}/messages", response_model=ChannelPostMessageResponse)
async def post_channel_message(
    token: str, req: ChannelPostMessageRequest, request: Request,
    user: dict = Depends(get_api_key_user),
):
    db = request.app.state.db
    await _resolve_acting_agent(db, req.agent_id, user["id"])
    channel = await _channel_by_token(db, token)
    member = await _require_member(db, channel["id"], req.agent_id)
    channel = await _maybe_expire(db, channel)

    if channel["status"] != "open":
        raise HTTPException(
            status_code=409,
            detail=f"Channel is {channel['status']}; not accepting messages",
        )

    new_turn = channel["turn_count"] + 1
    cursor = await db.execute(
        "SELECT COALESCE(MAX(seq), 0) AS m FROM channel_messages WHERE channel_id = ?",
        (channel["id"],),
    )
    next_seq = (await cursor.fetchone())["m"] + 1

    hit_cap = new_turn >= channel["max_turns"]
    new_status = "pending_human" if hit_cap else "open"

    async with db_transaction(db):
        await db.execute(
            """INSERT INTO channel_messages (id, channel_id, seq, from_agent, body, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), channel["id"], next_seq, member["agent_address"], req.body, _now()),
        )
        if hit_cap:
            await db.execute(
                "UPDATE channels SET turn_count = ?, status = 'pending_human', close_reason = 'max_turns' WHERE id = ?",
                (new_turn, channel["id"]),
            )
        else:
            await db.execute(
                "UPDATE channels SET turn_count = ? WHERE id = ?",
                (new_turn, channel["id"]),
            )

    return ChannelPostMessageResponse(
        seq=next_seq, status=new_status, turn_count=new_turn, max_turns=channel["max_turns"]
    )


@router.get("/channels/{token}/messages", response_model=ChannelMessagesResponse)
async def get_channel_messages(
    token: str, request: Request, since_seq: int = Query(default=0, ge=0),
    agent_id: str = Query(...), user: dict = Depends(get_api_key_user),
):
    db = request.app.state.db
    await _resolve_acting_agent(db, agent_id, user["id"])
    channel = await _channel_by_token(db, token)
    await _require_member(db, channel["id"], agent_id)
    channel = await _maybe_expire(db, channel)
    return ChannelMessagesResponse(
        channel=await _channel_info(db, channel),
        messages=await _history(db, channel["id"], since_seq),
    )


@router.get("/channels/{token}", response_model=ChannelInfo)
async def get_channel(
    token: str, request: Request, agent_id: str = Query(...),
    user: dict = Depends(get_api_key_user),
):
    db = request.app.state.db
    await _resolve_acting_agent(db, agent_id, user["id"])
    channel = await _channel_by_token(db, token)
    await _require_member(db, channel["id"], agent_id)
    channel = await _maybe_expire(db, channel)
    return await _channel_info(db, channel)


@router.post("/channels/{token}/close", response_model=ChannelInfo)
async def close_channel(
    token: str, req: ChannelCloseRequest, request: Request,
    user: dict = Depends(get_api_key_user),
):
    db = request.app.state.db
    if not req.agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    await _resolve_acting_agent(db, req.agent_id, user["id"])
    channel = await _channel_by_token(db, token)
    await _require_member(db, channel["id"], req.agent_id)
    channel = await _close_channel(db, channel, reason=req.reason or "human")
    return await _channel_info(db, channel)


@router.post("/channels/{token}/continue", response_model=ChannelInfo)
async def continue_channel(
    token: str, req: ChannelContinueRequest, request: Request,
    user: dict = Depends(get_api_key_user),
):
    db = request.app.state.db
    if not req.agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    await _resolve_acting_agent(db, req.agent_id, user["id"])
    channel = await _channel_by_token(db, token)
    await _require_member(db, channel["id"], req.agent_id)
    channel = await _do_continue(db, channel, req.extend_turns, req.extend_minutes)
    return await _channel_info(db, channel)


async def _do_continue(db, channel: dict, extend_turns: int | None, extend_minutes: int | None) -> dict:
    if channel["status"] != "pending_human":
        raise HTTPException(
            status_code=409,
            detail=f"Channel is {channel['status']}; only pending_human channels can continue",
        )
    et, em = extend_turns, extend_minutes
    if et is None and em is None:
        et, em = DEFAULT_EXTEND_TURNS, DEFAULT_EXTEND_MINUTES

    new_max = channel["max_turns"] + (et or 0)
    # Guarantee head-room so a max_turns-paused channel actually reopens.
    if new_max <= channel["turn_count"]:
        new_max = channel["turn_count"] + DEFAULT_EXTEND_TURNS

    now_dt = datetime.now(timezone.utc)
    if em:
        new_ttl = (now_dt + timedelta(minutes=em)).isoformat()
    else:
        new_ttl = channel["ttl_expires_at"]
    # Guarantee a future TTL so a ttl-paused channel actually reopens.
    if new_ttl <= now_dt.isoformat():
        new_ttl = (now_dt + timedelta(minutes=DEFAULT_EXTEND_MINUTES)).isoformat()

    async with db_transaction(db):
        await db.execute(
            "UPDATE channels SET status = 'open', close_reason = NULL, max_turns = ?, ttl_expires_at = ? WHERE id = ?",
            (new_max, new_ttl, channel["id"]),
        )
    return {**channel, "status": "open", "close_reason": None, "max_turns": new_max, "ttl_expires_at": new_ttl}


# ══════════════════════════════════════════════════════════════════════
# Operator-facing routes (cookie session) — observability + kill-switch
# ══════════════════════════════════════════════════════════════════════


async def _user_addresses(db, user_id: str) -> set[str]:
    cursor = await db.execute("SELECT address FROM agents WHERE user_id = ?", (user_id,))
    return {r["address"] for r in await cursor.fetchall()}


async def _require_participation(db, channel: dict, user_id: str) -> None:
    """Operator may view/control a channel only if they own a seat or the creator address."""
    addrs = await _user_addresses(db, user_id)
    if channel["creator_agent"] in addrs:
        return
    cursor = await db.execute(
        "SELECT a.user_id AS uid FROM channel_members m JOIN agents a ON a.id = m.agent_id "
        "WHERE m.channel_id = ?",
        (channel["id"],),
    )
    for r in await cursor.fetchall():
        if r["uid"] == user_id:
            return
    raise HTTPException(status_code=404, detail="Channel not found")


@admin_router.get("/channels", response_model=list[ChannelInfo])
async def admin_list_channels(request: Request, user: dict = Depends(get_current_user)):
    db = request.app.state.db
    addrs = await _user_addresses(db, user["id"])
    # channels where the user owns a member agent …
    cursor = await db.execute(
        "SELECT DISTINCT m.channel_id AS cid FROM channel_members m "
        "JOIN agents a ON a.id = m.agent_id WHERE a.user_id = ?",
        (user["id"],),
    )
    channel_ids = {r["cid"] for r in await cursor.fetchall()}

    cursor = await db.execute("SELECT * FROM channels ORDER BY created_at DESC")
    rows = [dict(r) for r in await cursor.fetchall()]
    out: list[ChannelInfo] = []
    for ch in rows:
        if ch["id"] in channel_ids or ch["creator_agent"] in addrs:
            ch = await _maybe_expire(db, ch)
            out.append(await _channel_info(db, ch))
    return out


@admin_router.get("/channels/{token}", response_model=ChannelMessagesResponse)
async def admin_get_channel(
    token: str, request: Request, since_seq: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    channel = await _channel_by_token(db, token)
    await _require_participation(db, channel, user["id"])
    channel = await _maybe_expire(db, channel)
    return ChannelMessagesResponse(
        channel=await _channel_info(db, channel),
        messages=await _history(db, channel["id"], since_seq),
    )


@admin_router.post("/channels/{token}/close", response_model=ChannelInfo)
async def admin_close_channel(
    token: str, request: Request, req: AdminChannelCloseRequest | None = None,
    user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    channel = await _channel_by_token(db, token)
    await _require_participation(db, channel, user["id"])
    reason = (req.reason if req else None) or "human"
    channel = await _close_channel(db, channel, reason=reason)
    return await _channel_info(db, channel)


@admin_router.post("/channels/{token}/continue", response_model=ChannelInfo)
async def admin_continue_channel(
    token: str, request: Request, req: AdminChannelContinueRequest | None = None,
    user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    channel = await _channel_by_token(db, token)
    await _require_participation(db, channel, user["id"])
    et = req.extend_turns if req else None
    em = req.extend_minutes if req else None
    channel = await _do_continue(db, channel, et, em)
    return await _channel_info(db, channel)
