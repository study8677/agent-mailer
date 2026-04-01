async def test_full_workflow(client):
    """Simulate: planner -> coder -> reviewer -> coder (fix) -> reviewer (approve)"""

    # 1. Register three agents
    agents = {}
    for name in ("planner", "coder", "reviewer"):
        resp = await client.post("/agents/register", json={
            "name": name, "role": name, "description": f"{name} agent",
            "system_prompt": f"你是一个{name}。",
        })
        assert resp.status_code == 200
        data = resp.json()
        agents[name] = {"id": data["id"], "address": data["address"]}

    # 2. Planner sends task to coder
    resp = await client.post("/messages/send", json={
        "agent_id": agents["planner"]["id"],
        "from_agent": agents["planner"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "send",
        "subject": "Implement user auth",
        "body": "Please implement JWT-based auth module",
    })
    assert resp.status_code == 200
    task_msg = resp.json()
    thread_id = task_msg["thread_id"]

    # 3. Coder checks inbox, gets the task
    resp = await client.get(
        f"/messages/inbox/{agents['coder']['address']}",
        params={"agent_id": agents["coder"]["id"]},
    )
    inbox = resp.json()
    assert len(inbox) == 1
    assert inbox[0]["subject"] == "Implement user auth"

    # Mark as read
    await client.patch(f"/messages/{inbox[0]['id']}/read")

    # 4. Coder forwards to reviewer for review
    resp = await client.post("/messages/send", json={
        "agent_id": agents["coder"]["id"],
        "from_agent": agents["coder"]["address"],
        "to_agent": agents["reviewer"]["address"],
        "action": "forward",
        "subject": "Review: user auth",
        "body": "Implementation done, please review",
        "parent_id": task_msg["id"],
    })
    assert resp.status_code == 200
    review_request = resp.json()
    assert review_request["thread_id"] == thread_id

    # 5. Reviewer checks inbox
    resp = await client.get(
        f"/messages/inbox/{agents['reviewer']['address']}",
        params={"agent_id": agents["reviewer"]["id"]},
    )
    reviewer_inbox = resp.json()
    assert len(reviewer_inbox) == 1

    # 6. Reviewer rejects with feedback
    resp = await client.post("/messages/send", json={
        "agent_id": agents["reviewer"]["id"],
        "from_agent": agents["reviewer"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "reply",
        "subject": "Re: Review: user auth",
        "body": "Memory leak in token refresh. Please fix.",
        "parent_id": review_request["id"],
    })
    assert resp.status_code == 200
    rejection = resp.json()
    assert rejection["thread_id"] == thread_id

    # 7. Coder gets the rejection in inbox
    resp = await client.get(
        f"/messages/inbox/{agents['coder']['address']}",
        params={"agent_id": agents["coder"]["id"]},
    )
    coder_inbox = resp.json()
    assert len(coder_inbox) == 1
    assert "Memory leak" in coder_inbox[0]["body"]

    # 8. Coder fixes and replies
    resp = await client.post("/messages/send", json={
        "agent_id": agents["coder"]["id"],
        "from_agent": agents["coder"]["address"],
        "to_agent": agents["reviewer"]["address"],
        "action": "reply",
        "subject": "Re: Review: user auth",
        "body": "Fixed the memory leak. Please re-review.",
        "parent_id": rejection["id"],
    })
    assert resp.status_code == 200

    # 9. Reviewer approves
    resp = await client.post("/messages/send", json={
        "agent_id": agents["reviewer"]["id"],
        "from_agent": agents["reviewer"]["address"],
        "to_agent": agents["coder"]["address"],
        "action": "reply",
        "subject": "Re: Review: user auth",
        "body": "LGTM. Approved.",
        "parent_id": resp.json()["id"],
    })
    assert resp.status_code == 200

    # 10. Verify the full thread
    resp = await client.get(f"/messages/thread/{thread_id}")
    thread = resp.json()
    assert len(thread) == 5  # send, forward, reject, fix, approve
    assert thread[0]["action"] == "send"
    assert thread[1]["action"] == "forward"
    assert thread[2]["action"] == "reply"
    assert thread[3]["action"] == "reply"
    assert thread[4]["action"] == "reply"
    assert "LGTM" in thread[4]["body"]
