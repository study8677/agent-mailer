"""Admin route multi-tenancy isolation tests."""
import os

os.environ.setdefault(
    "AGENT_MAILER_SECRET_KEY",
    "test-secret-key-that-is-at-least-32-bytes-long",
)

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from agent_mailer.auth import create_session_token, generate_api_key, hash_password
from agent_mailer.db import get_db, init_db
from agent_mailer.main import app
from agent_mailer.routes.admin import _human_operator_address


async def _create_user_with_auth(db, username: str) -> tuple[str, str, str]:
    """Create user with API key and JWT token, return (user_id, raw_key, token)."""
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO users (id, username, password_hash, is_superadmin, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, hash_password("password123"), 0, now),
    )
    raw_key, key_hash = generate_api_key()
    key_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO api_keys (id, user_id, key_hash, name, created_at) VALUES (?, ?, ?, ?, ?)",
        (key_id, user_id, key_hash, "key", now),
    )
    await db.commit()
    token = create_session_token(user_id)
    return user_id, raw_key, token


@pytest.fixture
async def admin_two_users():
    db = await get_db(":memory:")
    await init_db(db)
    app.state.db = db

    _, alice_key, alice_token = await _create_user_with_auth(db, "alice")
    _, bob_key, bob_token = await _create_user_with_auth(db, "bob")

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        headers={"X-API-Key": alice_key},
        cookies={"session_token": alice_token},
    ) as alice, AsyncClient(
        transport=transport, base_url="http://test",
        headers={"X-API-Key": bob_key},
        cookies={"session_token": bob_token},
    ) as bob:
        # Register agents for each user
        a_agent = (await alice.post("/agents/register", json={
            "name": "coder", "role": "coder", "system_prompt": "Alice coder",
        })).json()
        b_agent = (await bob.post("/agents/register", json={
            "name": "coder", "role": "coder", "system_prompt": "Bob coder",
        })).json()

        yield {
            "alice": {"client": alice, "agent": a_agent},
            "bob": {"client": bob, "agent": b_agent},
        }
    await db.close()


async def test_human_operator_per_user(admin_two_users):
    alice = admin_two_users["alice"]["client"]
    alice_agent = admin_two_users["alice"]["agent"]

    # Send via admin endpoint creates user-specific human operator
    resp = await alice.post("/admin/messages/send", json={
        "to_agent": alice_agent["address"],
        "subject": "Test",
        "body": "Hello",
    })
    assert resp.status_code == 200
    assert resp.json()["from_agent"] == _human_operator_address("alice")


async def test_admin_stats_isolation(admin_two_users):
    alice = admin_two_users["alice"]["client"]
    bob = admin_two_users["bob"]["client"]

    resp_a = await alice.get("/admin/agents/stats")
    resp_b = await bob.get("/admin/agents/stats")

    a_addresses = {s["address"] for s in resp_a.json()}
    b_addresses = {s["address"] for s in resp_b.json()}

    assert "coder@alice.amp.linkyun.co" in a_addresses
    assert "coder@bob.amp.linkyun.co" not in a_addresses
    assert "coder@bob.amp.linkyun.co" in b_addresses
    assert "coder@alice.amp.linkyun.co" not in b_addresses


async def test_admin_threads_isolation(admin_two_users):
    alice = admin_two_users["alice"]["client"]
    alice_agent = admin_two_users["alice"]["agent"]
    bob = admin_two_users["bob"]["client"]

    # Alice sends a message (creates a thread)
    await alice.post("/admin/messages/send", json={
        "to_agent": alice_agent["address"],
        "subject": "Alice thread",
        "body": "Hello",
    })

    # Alice sees the thread
    resp_a = await alice.get("/admin/threads/summary")
    assert len(resp_a.json()) == 1

    # Bob does not
    resp_b = await bob.get("/admin/threads/summary")
    assert len(resp_b.json()) == 0


async def test_admin_inbox_isolation(admin_two_users):
    alice = admin_two_users["alice"]["client"]
    bob = admin_two_users["bob"]["client"]
    bob_agent = admin_two_users["bob"]["agent"]

    # Alice cannot peek at Bob's inbox
    resp = await alice.get(f"/admin/messages/inbox/{bob_agent['address']}")
    assert resp.status_code == 404


async def test_admin_delete_agent_isolation(admin_two_users):
    alice = admin_two_users["alice"]["client"]
    bob_agent = admin_two_users["bob"]["agent"]

    # Alice cannot delete Bob's agent
    resp = await alice.delete(f"/admin/agents/{bob_agent['id']}")
    assert resp.status_code == 404


async def test_admin_tags_isolation(admin_two_users):
    alice = admin_two_users["alice"]["client"]
    bob_agent = admin_two_users["bob"]["agent"]

    # Alice cannot update Bob's agent tags
    resp = await alice.put(
        f"/admin/agents/{bob_agent['id']}/tags",
        json={"tags": ["hacked"]},
    )
    assert resp.status_code == 404
