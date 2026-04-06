"""Exhaustive multi-tenancy isolation tests."""
import os

os.environ.setdefault(
    "AGENT_MAILER_SECRET_KEY",
    "test-secret-key-that-is-at-least-32-bytes-long",
)

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_mailer.auth import generate_api_key, hash_password
from agent_mailer.bootstrap import ensure_bootstrap_invite_code
from agent_mailer.db import get_db, init_db
from agent_mailer.main import app


async def _create_user_with_key(db, username: str, is_superadmin: bool = False) -> tuple[str, str]:
    """Create a user and API key, return (user_id, raw_api_key)."""
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO users (id, username, password_hash, is_superadmin, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, hash_password("password123"), int(is_superadmin), now),
    )
    raw_key, key_hash = generate_api_key()
    key_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO api_keys (id, user_id, key_hash, name, created_at) VALUES (?, ?, ?, ?, ?)",
        (key_id, user_id, key_hash, "key", now),
    )
    await db.commit()
    return user_id, raw_key


@pytest.fixture
async def two_users():
    """Set up two isolated users (alice & bob), each with their own API key and client."""
    db = await get_db(":memory:")
    await init_db(db)
    app.state.db = db

    _, alice_key = await _create_user_with_key(db, "alice")
    _, bob_key = await _create_user_with_key(db, "bob")

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        headers={"X-API-Key": alice_key},
    ) as alice_client, AsyncClient(
        transport=transport, base_url="http://test",
        headers={"X-API-Key": bob_key},
    ) as bob_client:
        yield alice_client, bob_client
    await db.close()


@pytest.fixture
async def alice_bob_agents(two_users):
    """Register same-named agents for both users, return agent info."""
    alice, bob = two_users

    a_resp = await alice.post("/agents/register", json={
        "name": "coder", "role": "coder", "system_prompt": "Alice's coder",
    })
    assert a_resp.status_code == 200
    alice_agent = a_resp.json()

    b_resp = await bob.post("/agents/register", json={
        "name": "coder", "role": "coder", "system_prompt": "Bob's coder",
    })
    assert b_resp.status_code == 200
    bob_agent = b_resp.json()

    return {
        "alice": {"client": alice, "agent": alice_agent},
        "bob": {"client": bob, "agent": bob_agent},
    }


# --- Address format ---


async def test_address_format(alice_bob_agents):
    alice_agent = alice_bob_agents["alice"]["agent"]
    bob_agent = alice_bob_agents["bob"]["agent"]

    assert alice_agent["address"] == "coder@alice.amp.linkyun.co"
    assert bob_agent["address"] == "coder@bob.amp.linkyun.co"
    # Same name, different addresses
    assert alice_agent["address"] != bob_agent["address"]


# --- Agent list isolation ---


async def test_alice_cannot_see_bob_agents(alice_bob_agents):
    alice = alice_bob_agents["alice"]["client"]
    bob_agent = alice_bob_agents["bob"]["agent"]

    resp = await alice.get("/agents")
    agents = resp.json()
    addresses = {a["address"] for a in agents}
    assert bob_agent["address"] not in addresses
    assert len(agents) == 1  # only Alice's agent


async def test_bob_cannot_see_alice_agents(alice_bob_agents):
    bob = alice_bob_agents["bob"]["client"]
    alice_agent = alice_bob_agents["alice"]["agent"]

    resp = await bob.get("/agents")
    agents = resp.json()
    addresses = {a["address"] for a in agents}
    assert alice_agent["address"] not in addresses
    assert len(agents) == 1


# --- Agent detail isolation ---


async def test_alice_cannot_get_bob_agent_detail(alice_bob_agents):
    alice = alice_bob_agents["alice"]["client"]
    bob_agent = alice_bob_agents["bob"]["agent"]

    resp = await alice.get(f"/agents/{bob_agent['id']}")
    assert resp.status_code == 404


async def test_bob_cannot_get_alice_agent_detail(alice_bob_agents):
    bob = alice_bob_agents["bob"]["client"]
    alice_agent = alice_bob_agents["alice"]["agent"]

    resp = await bob.get(f"/agents/{alice_agent['id']}")
    assert resp.status_code == 404


# --- Cross-tenant messaging blocked ---


async def test_alice_cannot_send_to_bob(alice_bob_agents):
    alice = alice_bob_agents["alice"]["client"]
    alice_agent = alice_bob_agents["alice"]["agent"]
    bob_agent = alice_bob_agents["bob"]["agent"]

    resp = await alice.post("/messages/send", json={
        "agent_id": alice_agent["id"],
        "from_agent": alice_agent["address"],
        "to_agent": bob_agent["address"],
        "action": "send",
        "subject": "Cross-tenant",
        "body": "Should fail",
    })
    assert resp.status_code == 403
    assert "cross-tenant" in resp.json()["detail"].lower()


async def test_bob_cannot_send_to_alice(alice_bob_agents):
    bob = alice_bob_agents["bob"]["client"]
    bob_agent = alice_bob_agents["bob"]["agent"]
    alice_agent = alice_bob_agents["alice"]["agent"]

    resp = await bob.post("/messages/send", json={
        "agent_id": bob_agent["id"],
        "from_agent": bob_agent["address"],
        "to_agent": alice_agent["address"],
        "action": "send",
        "subject": "Cross-tenant",
        "body": "Should fail",
    })
    assert resp.status_code == 403


# --- Inbox isolation ---


async def test_alice_cannot_view_bob_inbox(alice_bob_agents):
    alice = alice_bob_agents["alice"]["client"]
    bob_agent = alice_bob_agents["bob"]["agent"]

    # Alice cannot use Bob's agent_id to check Bob's inbox
    resp = await alice.get(
        f"/messages/inbox/{bob_agent['address']}",
        params={"agent_id": bob_agent["id"]},
    )
    # Should fail because Bob's agent doesn't belong to Alice
    assert resp.status_code == 403


# --- Thread isolation ---


async def test_alice_cannot_view_bob_thread(two_users):
    alice, bob = two_users

    # Bob registers two agents and sends a message between them
    a1 = (await bob.post("/agents/register", json={
        "name": "planner", "role": "planner", "system_prompt": "B planner",
    })).json()
    a2 = (await bob.post("/agents/register", json={
        "name": "coder", "role": "coder", "system_prompt": "B coder",
    })).json()

    msg = (await bob.post("/messages/send", json={
        "agent_id": a1["id"],
        "from_agent": a1["address"],
        "to_agent": a2["address"],
        "action": "send",
        "subject": "Bob internal",
        "body": "Secret",
    })).json()

    # Alice cannot view Bob's thread
    resp = await alice.get(f"/messages/thread/{msg['thread_id']}")
    assert resp.status_code == 404


# --- Mark read/unread isolation ---


async def test_alice_cannot_mark_bob_message_read(two_users):
    alice, bob = two_users

    a1 = (await bob.post("/agents/register", json={
        "name": "sender", "role": "sender", "system_prompt": "S",
    })).json()
    a2 = (await bob.post("/agents/register", json={
        "name": "receiver", "role": "receiver", "system_prompt": "R",
    })).json()

    msg = (await bob.post("/messages/send", json={
        "agent_id": a1["id"],
        "from_agent": a1["address"],
        "to_agent": a2["address"],
        "action": "send",
        "subject": "For Bob",
        "body": "Secret",
    })).json()

    # Alice tries to mark Bob's message as read
    resp = await alice.patch(f"/messages/{msg['id']}/read")
    assert resp.status_code == 403


# --- Intra-tenant messaging works ---


async def test_same_tenant_messaging_works(two_users):
    alice, _ = two_users

    a1 = (await alice.post("/agents/register", json={
        "name": "planner", "role": "planner", "system_prompt": "A planner",
    })).json()
    a2 = (await alice.post("/agents/register", json={
        "name": "coder", "role": "coder", "system_prompt": "A coder",
    })).json()

    resp = await alice.post("/messages/send", json={
        "agent_id": a1["id"],
        "from_agent": a1["address"],
        "to_agent": a2["address"],
        "action": "send",
        "subject": "Internal task",
        "body": "Do this",
    })
    assert resp.status_code == 200

    inbox = await alice.get(
        f"/messages/inbox/{a2['address']}",
        params={"agent_id": a2["id"]},
    )
    assert len(inbox.json()) == 1
    assert inbox.json()[0]["subject"] == "Internal task"
