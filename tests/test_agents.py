async def test_register_agent(client):
    resp = await client.post("/agents/register", json={
        "name": "coder",
        "role": "coder",
        "description": "Writes code based on specs",
        "system_prompt": "你是一个专业的软件开发者。",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["name"] == "coder"
    assert data["address"] == "coder@local"  # default address
    assert data["role"] == "coder"
    assert data["system_prompt"] == "你是一个专业的软件开发者。"


async def test_register_agent_custom_address(client):
    resp = await client.post("/agents/register", json={
        "name": "coder",
        "address": "dev-coder@myteam",
        "role": "coder",
        "system_prompt": "你是一个开发者。",
    })
    assert resp.status_code == 200
    assert resp.json()["address"] == "dev-coder@myteam"


async def test_register_agent_duplicate_address(client):
    await client.post("/agents/register", json={
        "name": "coder1",
        "address": "coder@local",
        "role": "coder",
        "system_prompt": "A",
    })
    resp = await client.post("/agents/register", json={
        "name": "coder2",
        "address": "coder@local",
        "role": "coder",
        "system_prompt": "B",
    })
    assert resp.status_code == 409


async def test_register_agent_requires_system_prompt(client):
    resp = await client.post("/agents/register", json={
        "name": "coder",
        "role": "coder",
        "description": "Writes code",
    })
    assert resp.status_code == 422  # validation error


async def test_list_agents(client):
    await client.post("/agents/register", json={
        "name": "planner", "role": "planner", "description": "Plans tasks",
        "system_prompt": "你是一个需求分析专家。",
    })
    await client.post("/agents/register", json={
        "name": "coder", "role": "coder", "description": "Writes code",
        "system_prompt": "你是一个开发者。",
    })
    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 2
    assert agents[0]["address"] == "planner@local"
    assert agents[1]["address"] == "coder@local"


async def test_get_agent_by_id(client):
    create_resp = await client.post("/agents/register", json={
        "name": "reviewer", "role": "reviewer", "description": "Reviews code",
        "system_prompt": "你是一个代码审查专家。",
    })
    agent_id = create_resp.json()["id"]
    resp = await client.get(f"/agents/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == agent_id
    assert resp.json()["role"] == "reviewer"
    assert resp.json()["address"] == "reviewer@local"


async def test_get_agent_not_found(client):
    resp = await client.get("/agents/nonexistent-id")
    assert resp.status_code == 404


async def test_update_address(client):
    create_resp = await client.post("/agents/register", json={
        "name": "coder", "role": "coder",
        "system_prompt": "你是一个开发者。",
    })
    agent_id = create_resp.json()["id"]
    resp = await client.patch(f"/agents/{agent_id}/address", json={
        "address": "senior-coder@local",
    })
    assert resp.status_code == 200
    assert resp.json()["address"] == "senior-coder@local"

    # verify persisted
    resp = await client.get(f"/agents/{agent_id}")
    assert resp.json()["address"] == "senior-coder@local"


async def test_update_address_duplicate(client):
    await client.post("/agents/register", json={
        "name": "coder", "role": "coder",
        "system_prompt": "A",
    })
    create_resp = await client.post("/agents/register", json={
        "name": "reviewer", "role": "reviewer",
        "system_prompt": "B",
    })
    reviewer_id = create_resp.json()["id"]
    resp = await client.patch(f"/agents/{reviewer_id}/address", json={
        "address": "coder@local",
    })
    assert resp.status_code == 409


async def test_update_address_not_found(client):
    resp = await client.patch("/agents/nonexistent/address", json={
        "address": "new@local",
    })
    assert resp.status_code == 404


async def test_update_address_updates_messages(client):
    """Changing address should update from_agent/to_agent in existing messages."""
    # register two agents
    r1 = await client.post("/agents/register", json={
        "name": "planner", "role": "planner", "system_prompt": "A",
    })
    r2 = await client.post("/agents/register", json={
        "name": "coder", "role": "coder", "system_prompt": "B",
    })
    planner_id = r1.json()["id"]
    coder_id = r2.json()["id"]

    # send a message
    await client.post("/messages/send", json={
        "agent_id": planner_id,
        "from_agent": "planner@local",
        "to_agent": "coder@local",
        "action": "send",
        "subject": "Task",
        "body": "Do this",
    })

    # change planner's address
    await client.patch(f"/agents/{planner_id}/address", json={
        "address": "lead-planner@local",
    })

    # inbox should still work for coder
    resp = await client.get(
        "/messages/inbox/coder@local",
        params={"agent_id": coder_id},
    )
    msgs = resp.json()
    assert len(msgs) == 1
    assert msgs[0]["from_agent"] == "lead-planner@local"


async def test_get_agent_setup(client):
    create_resp = await client.post("/agents/register", json={
        "name": "coder", "role": "coder", "description": "Writes code",
        "system_prompt": "你是一个专业的软件开发者。",
    })
    agent_id = create_resp.json()["id"]
    resp = await client.get(f"/agents/{agent_id}/setup")
    assert resp.status_code == 200
    data = resp.json()
    assert "agent_md" in data
    assert "claude_md" in data
    assert "instructions" in data
    # AGENT.md should contain the system_prompt
    assert "你是一个专业的软件开发者。" in data["agent_md"]
    # AGENT.md should contain the address
    assert "coder@local" in data["agent_md"]
    # CLAUDE.md should reference AGENT.md
    assert "AGENT.md" in data["claude_md"]


async def test_get_agent_setup_not_found(client):
    resp = await client.get("/agents/nonexistent-id/setup")
    assert resp.status_code == 404
