import pytest


@pytest.fixture
async def agents(client):
    """Register planner, coder, reviewer and return {name: {id, address}}."""
    result = {}
    for name in ("planner", "coder", "reviewer"):
        resp = await client.post("/agents/register", json={
            "name": name, "role": name, "description": f"{name} agent",
            "system_prompt": f"你是一个{name}。",
        })
        data = resp.json()
        result[name] = {"id": data["id"], "address": data["address"]}
    return result


async def test_send_creates_thread(client, agents):
    resp = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send",
        "subject": "Build feature X",
        "body": "Please implement feature X",
    })
    assert resp.status_code == 200
    msg = resp.json()
    assert msg["thread_id"]
    assert msg["from_agent"] == agents["planner"]["address"]
    assert msg["to_agent"] == agents["coder"]["address"]
    assert msg["action"] == "send"
    assert msg["parent_id"] is None


async def test_send_validates_sender_identity(client, agents):
    """agent_id must own from_agent address."""
    resp = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["coder"]["address"],  # mismatch
        "to_agent": agents["reviewer"]["address"],
        "action": "send",
        "subject": "Test",
        "body": "Test",
    })
    assert resp.status_code == 403


async def test_send_validates_sender_agent_id(client, agents):
    """agent_id must exist."""
    resp = await client.post("/messages/send", json={
        "agent_id": "nonexistent-id",
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send",
        "subject": "Test",
        "body": "Test",
    })
    assert resp.status_code == 404


async def test_send_validates_recipient_address(client, agents):
    resp = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": "nonexistent@local",
        "action": "send",
        "subject": "Test",
        "body": "Test",
    })
    assert resp.status_code == 404


async def test_reply_inherits_thread(client, agents):
    send_resp = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send",
        "subject": "Task",
        "body": "Do this",
    })
    original = send_resp.json()

    reply_resp = await client.post("/messages/send", json={
        "agent_id": agents["coder"]["id"],
        "from_agent": agents["coder"]["address"],
        "to_agent": agents["planner"]["address"],
        "action": "reply",
        "subject": "Re: Task",
        "body": "Done",
        "parent_id": original["id"],
    })
    assert reply_resp.status_code == 200
    reply = reply_resp.json()
    assert reply["thread_id"] == original["thread_id"]
    assert reply["parent_id"] == original["id"]


async def test_forward_inherits_thread(client, agents):
    send_resp = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send",
        "subject": "Task",
        "body": "Implement this",
    })
    original = send_resp.json()

    fwd_resp = await client.post("/messages/send", json={
        "agent_id": agents["coder"]["id"],
        "from_agent": agents["coder"]["address"],
        "to_agent": agents["reviewer"]["address"],
        "action": "forward",
        "subject": "Fwd: Task",
        "body": "Please review",
        "parent_id": original["id"],
    })
    assert fwd_resp.status_code == 200
    fwd = fwd_resp.json()
    assert fwd["thread_id"] == original["thread_id"]
    assert fwd["to_agent"] == agents["reviewer"]["address"]


async def test_reply_requires_parent_id(client, agents):
    resp = await client.post("/messages/send", json={
        "agent_id": agents["coder"]["id"],
        "from_agent": agents["coder"]["address"],
        "to_agent": agents["planner"]["address"],
        "action": "reply",
        "body": "Replying without parent",
    })
    assert resp.status_code == 400


async def test_reply_with_invalid_parent_id(client, agents):
    resp = await client.post("/messages/send", json={
        "agent_id": agents["coder"]["id"],
        "from_agent": agents["coder"]["address"],
        "to_agent": agents["planner"]["address"],
        "action": "reply",
        "body": "Bad parent",
        "parent_id": "nonexistent",
    })
    assert resp.status_code == 404


async def test_inbox_returns_unread(client, agents):
    await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send", "subject": "Task 1", "body": "Do 1",
    })
    await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send", "subject": "Task 2", "body": "Do 2",
    })
    resp = await client.get(
        f"/messages/inbox/{agents['coder']['address']}",
        params={"agent_id": agents["coder"]["id"]},
    )
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) == 2
    assert all(not m["is_read"] for m in msgs)


async def test_inbox_validates_identity(client, agents):
    """agent_id must own the inbox address."""
    resp = await client.get(
        f"/messages/inbox/{agents['coder']['address']}",
        params={"agent_id": agents["planner"]["id"]},  # mismatch
    )
    assert resp.status_code == 403


async def test_inbox_validates_agent_id(client, agents):
    """agent_id must exist."""
    resp = await client.get(
        f"/messages/inbox/{agents['coder']['address']}",
        params={"agent_id": "nonexistent-id"},
    )
    assert resp.status_code == 404


async def test_inbox_requires_agent_id(client, agents):
    """agent_id query param is required."""
    resp = await client.get(f"/messages/inbox/{agents['coder']['address']}")
    assert resp.status_code == 422


async def test_inbox_all_includes_read(client, agents):
    send_resp = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send", "subject": "Task", "body": "Do",
    })
    msg_id = send_resp.json()["id"]
    await client.patch(f"/messages/{msg_id}/read")

    resp = await client.get(
        f"/messages/inbox/{agents['coder']['address']}",
        params={"agent_id": agents["coder"]["id"]},
    )
    assert len(resp.json()) == 0

    resp_all = await client.get(
        f"/messages/inbox/{agents['coder']['address']}",
        params={"agent_id": agents["coder"]["id"], "all": "true"},
    )
    assert len(resp_all.json()) == 1


async def test_mark_read(client, agents):
    send_resp = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send", "subject": "Task", "body": "Do",
    })
    msg_id = send_resp.json()["id"]
    resp = await client.patch(f"/messages/{msg_id}/read")
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True


async def test_mark_read_not_found(client, agents):
    resp = await client.patch("/messages/nonexistent/read")
    assert resp.status_code == 404


async def test_thread_returns_ordered_messages(client, agents):
    s = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send", "subject": "Task", "body": "Do this",
    })
    original = s.json()

    r1 = await client.post("/messages/send", json={
        "agent_id": agents["coder"]["id"],
        "from_agent": agents["coder"]["address"],
        "to_agent": agents["planner"]["address"],
        "action": "reply", "body": "Done", "parent_id": original["id"],
    })
    reply1 = r1.json()

    await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "reply", "body": "LGTM", "parent_id": reply1["id"],
    })

    resp = await client.get(f"/messages/thread/{original['thread_id']}")
    assert resp.status_code == 200
    thread = resp.json()
    assert len(thread) == 3
    assert thread[0]["id"] == original["id"]
    assert thread[1]["id"] == reply1["id"]


async def test_send_with_attachments(client, agents):
    resp = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send",
        "subject": "With files",
        "body": "See attached",
        "attachments": ["/path/to/spec.md", "/path/to/design.png"],
    })
    assert resp.status_code == 200
    msg = resp.json()
    assert msg["attachments"] == ["/path/to/spec.md", "/path/to/design.png"]
