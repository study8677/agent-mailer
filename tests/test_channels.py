"""Tests for the realtime chat channel feature (point-to-point MVP).

Covers the PRD §7 acceptance + the security points reviewer will scrutinise:
cross-tenant join, token invalidation on close, guardrail → pending_human →
continue/close, and per-owner de-duplicated close notifications.
"""

import uuid
from datetime import datetime, timezone

import pytest

from agent_mailer.auth import generate_api_key, hash_password
from agent_mailer.main import app
from agent_mailer.routes.channels import _TOKEN_ALPHABET, _TOKEN_LEN, _human_operator_address


async def _register(client, name, key=None):
    headers = {"X-API-Key": key} if key else None
    resp = await client.post(
        "/agents/register",
        json={"name": name, "role": "peer", "description": name, "system_prompt": f"You are {name}."},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    return {"id": d["id"], "address": d["address"]}


async def _make_tenant(db, username):
    """Insert a second user + API key directly; return (user_id, raw_key)."""
    uid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO users (id, username, password_hash, is_superadmin, created_at) VALUES (?, ?, ?, ?, ?)",
        (uid, username, hash_password("pw-123456"), 0, now),
    )
    raw, kh = generate_api_key()
    await db.execute(
        "INSERT INTO api_keys (id, user_id, key_hash, name, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), uid, kh, "k2", now),
    )
    await db.commit()
    return uid, raw


@pytest.fixture
async def alice(client):
    return await _register(client, "alice")


@pytest.fixture
async def bob(client):
    return await _register(client, "bob")


async def _create(client, agent, prompt="讨论 X"):
    resp = await client.post("/channels", json={"agent_id": agent["id"], "initial_prompt": prompt})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── basic flow ──────────────────────────────────────────────────────


async def test_create_returns_strong_base62_token(client, alice):
    ch = await _create(client, alice)
    token = ch["join_token"]
    assert len(token) == _TOKEN_LEN
    assert set(token) <= set(_TOKEN_ALPHABET)
    assert "-" not in token and "_" not in token


async def test_join_replays_initial_prompt_and_history(client, alice, bob):
    ch = await _create(client, alice, prompt="kickoff")
    token = ch["join_token"]
    # alice speaks first
    await client.post(f"/channels/{token}/messages", json={"agent_id": alice["id"], "body": "hello"})

    resp = await client.post(f"/channels/{token}/join", json={"agent_id": bob["id"]})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["channel"]["initial_prompt"] == "kickoff"
    assert {m["agent_address"] for m in data["channel"]["members"]} == {alice["address"], bob["address"]}
    assert [m["body"] for m in data["history"]] == ["hello"]


async def test_messages_are_seq_ordered_and_incremental(client, alice, bob):
    ch = await _create(client, alice)
    token = ch["join_token"]
    await client.post(f"/channels/{token}/join", json={"agent_id": bob["id"]})

    r1 = await client.post(f"/channels/{token}/messages", json={"agent_id": alice["id"], "body": "a1"})
    r2 = await client.post(f"/channels/{token}/messages", json={"agent_id": bob["id"], "body": "b1"})
    assert r1.json()["seq"] == 1
    assert r2.json()["seq"] == 2

    full = await client.get(f"/channels/{token}/messages", params={"agent_id": bob["id"], "since_seq": 0})
    assert [m["seq"] for m in full.json()["messages"]] == [1, 2]
    incr = await client.get(f"/channels/{token}/messages", params={"agent_id": bob["id"], "since_seq": 1})
    assert [m["body"] for m in incr.json()["messages"]] == ["b1"]


async def test_non_member_cannot_post_or_read(client, alice, bob):
    ch = await _create(client, alice)
    token = ch["join_token"]
    # bob never joined
    resp = await client.post(f"/channels/{token}/messages", json={"agent_id": bob["id"], "body": "x"})
    assert resp.status_code == 403


async def test_body_size_limit(client, alice):
    ch = await _create(client, alice)
    token = ch["join_token"]
    big = "x" * (8 * 1024 + 1)
    resp = await client.post(f"/channels/{token}/messages", json={"agent_id": alice["id"], "body": big})
    assert resp.status_code == 422


# ── cross-tenant ────────────────────────────────────────────────────


async def test_cross_tenant_agent_can_join(client, alice):
    _, key2 = await _make_tenant(app.state.db, "tenant2")
    carol = await _register(client, "carol", key=key2)
    ch = await _create(client, alice)
    token = ch["join_token"]

    resp = await client.post(
        f"/channels/{token}/join", json={"agent_id": carol["id"]}, headers={"X-API-Key": key2}
    )
    assert resp.status_code == 200, resp.text
    assert carol["address"] in {m["agent_address"] for m in resp.json()["channel"]["members"]}


async def test_channel_full_rejects_third(client, alice, bob):
    _, key2 = await _make_tenant(app.state.db, "tenant3")
    carol = await _register(client, "carol3", key=key2)
    ch = await _create(client, alice)
    token = ch["join_token"]
    await client.post(f"/channels/{token}/join", json={"agent_id": bob["id"]})
    resp = await client.post(
        f"/channels/{token}/join", json={"agent_id": carol["id"]}, headers={"X-API-Key": key2}
    )
    assert resp.status_code == 409


# ── close / token invalidation ──────────────────────────────────────


async def test_close_invalidates_token(client, alice, bob):
    _, key2 = await _make_tenant(app.state.db, "tenant4")
    carol = await _register(client, "carol4", key=key2)
    ch = await _create(client, alice)
    token = ch["join_token"]
    await client.post(f"/channels/{token}/join", json={"agent_id": bob["id"]})

    closed = await client.post(f"/channels/{token}/close", json={"agent_id": alice["id"]})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["close_reason"] == "human"

    # member can no longer post
    post = await client.post(f"/channels/{token}/messages", json={"agent_id": bob["id"], "body": "late"})
    assert post.status_code == 409
    # a brand-new agent can no longer join
    join = await client.post(
        f"/channels/{token}/join", json={"agent_id": carol["id"]}, headers={"X-API-Key": key2}
    )
    assert join.status_code == 409


async def test_close_notifies_each_owner_once(client, alice, bob):
    """Same-owner channel → exactly one station-internal close notice (dedup)."""
    ch = await _create(client, alice)
    token = ch["join_token"]
    await client.post(f"/channels/{token}/join", json={"agent_id": bob["id"]})
    await client.post(f"/channels/{token}/close", json={"agent_id": alice["id"]})

    op_addr = _human_operator_address("testuser")
    cursor = await app.state.db.execute(
        "SELECT COUNT(*) AS c FROM messages WHERE to_agent = ?", (op_addr,)
    )
    assert (await cursor.fetchone())["c"] == 1


async def test_close_notifies_both_owners_cross_tenant(client, alice):
    uid2, key2 = await _make_tenant(app.state.db, "tenant5")
    carol = await _register(client, "carol5", key=key2)
    ch = await _create(client, alice)
    token = ch["join_token"]
    await client.post(
        f"/channels/{token}/join", json={"agent_id": carol["id"]}, headers={"X-API-Key": key2}
    )
    await client.post(f"/channels/{token}/close", json={"agent_id": alice["id"]})

    for username in ("testuser", "tenant5"):
        op_addr = _human_operator_address(username)
        cursor = await app.state.db.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE to_agent = ?", (op_addr,)
        )
        assert (await cursor.fetchone())["c"] == 1, username


# ── guardrails ──────────────────────────────────────────────────────


async def test_max_turns_pauses_then_continue_reopens(client, alice, bob):
    ch = await _create(client, alice)
    token = ch["join_token"]
    await client.post(f"/channels/{token}/join", json={"agent_id": bob["id"]})

    last = None
    for i in range(10):  # default max_turns = 10
        last = await client.post(
            f"/channels/{token}/messages", json={"agent_id": alice["id"], "body": f"m{i}"}
        )
    assert last.json()["status"] == "pending_human"

    blocked = await client.post(f"/channels/{token}/messages", json={"agent_id": alice["id"], "body": "n"})
    assert blocked.status_code == 409

    cont = await client.post(f"/admin/channels/{token}/continue", json={"extend_turns": 5})
    assert cont.status_code == 200
    assert cont.json()["status"] == "open"
    assert cont.json()["max_turns"] == 15

    ok = await client.post(f"/channels/{token}/messages", json={"agent_id": alice["id"], "body": "again"})
    assert ok.status_code == 200
    assert ok.json()["seq"] == 11


async def test_ttl_expiry_pauses_channel(client, alice):
    ch = await _create(client, alice)
    token = ch["join_token"]
    # force TTL into the past
    past = "2000-01-01T00:00:00+00:00"
    await app.state.db.execute(
        "UPDATE channels SET ttl_expires_at = ? WHERE join_token = ?", (past, token)
    )
    await app.state.db.commit()

    info = await client.get(f"/channels/{token}", params={"agent_id": alice["id"]})
    assert info.json()["status"] == "pending_human"
    assert info.json()["close_reason"] == "ttl"

    post = await client.post(f"/channels/{token}/messages", json={"agent_id": alice["id"], "body": "x"})
    assert post.status_code == 409

    cont = await client.post(f"/admin/channels/{token}/continue", json={"extend_minutes": 30})
    assert cont.json()["status"] == "open"


# ── operator console scoping ────────────────────────────────────────


async def test_admin_list_and_scope(client, alice):
    uid2, key2 = await _make_tenant(app.state.db, "tenant6")
    carol = await _register(client, "carol6", key=key2)

    mine = await _create(client, alice)
    # carol's own channel (different owner, not shared)
    other = await client.post(
        "/channels", json={"agent_id": carol["id"], "initial_prompt": "p"}, headers={"X-API-Key": key2}
    )
    other_token = other.json()["join_token"]

    listing = await client.get("/admin/channels")
    tokens = {c["join_token"] for c in listing.json()}
    assert mine["join_token"] in tokens
    assert other_token not in tokens

    # user1 cannot view a channel they don't participate in
    forbidden = await client.get(f"/admin/channels/{other_token}")
    assert forbidden.status_code == 404


async def test_admin_human_can_close(client, alice, bob):
    """Operator console kill-switch: human closes via /admin and token dies."""
    ch = await _create(client, alice)
    token = ch["join_token"]
    await client.post(f"/channels/{token}/join", json={"agent_id": bob["id"]})

    closed = await client.post(f"/admin/channels/{token}/close", json={"reason": "human"})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    post = await client.post(f"/channels/{token}/messages", json={"agent_id": alice["id"], "body": "x"})
    assert post.status_code == 409
