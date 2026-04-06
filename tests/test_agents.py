DOMAIN_SUFFIX = "@testuser.amp.linkyun.co"


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
    assert data["address"] == f"coder{DOMAIN_SUFFIX}"
    assert data["role"] == "coder"
    assert data["system_prompt"] == "你是一个专业的软件开发者。"


async def test_register_agent_custom_address(client):
    resp = await client.post("/agents/register", json={
        "name": "coder",
        "address": f"dev-coder{DOMAIN_SUFFIX}",
        "role": "coder",
        "system_prompt": "你是一个开发者。",
    })
    assert resp.status_code == 200
    assert resp.json()["address"] == f"dev-coder{DOMAIN_SUFFIX}"


async def test_register_agent_custom_address_wrong_domain(client):
    resp = await client.post("/agents/register", json={
        "name": "coder",
        "address": "coder@other.domain",
        "role": "coder",
        "system_prompt": "你是一个开发者。",
    })
    assert resp.status_code == 400


async def test_register_agent_duplicate_address(client):
    await client.post("/agents/register", json={
        "name": "coder1",
        "address": f"coder{DOMAIN_SUFFIX}",
        "role": "coder",
        "system_prompt": "A",
    })
    resp = await client.post("/agents/register", json={
        "name": "coder2",
        "address": f"coder{DOMAIN_SUFFIX}",
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
    assert agents[0]["address"] == f"planner{DOMAIN_SUFFIX}"
    assert agents[1]["address"] == f"coder{DOMAIN_SUFFIX}"


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
    assert resp.json()["address"] == f"reviewer{DOMAIN_SUFFIX}"


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
        "address": f"senior-coder{DOMAIN_SUFFIX}",
    })
    assert resp.status_code == 200
    assert resp.json()["address"] == f"senior-coder{DOMAIN_SUFFIX}"

    # verify persisted
    resp = await client.get(f"/agents/{agent_id}")
    assert resp.json()["address"] == f"senior-coder{DOMAIN_SUFFIX}"


async def test_update_address_wrong_domain(client):
    create_resp = await client.post("/agents/register", json={
        "name": "coder", "role": "coder",
        "system_prompt": "你是一个开发者。",
    })
    agent_id = create_resp.json()["id"]
    resp = await client.patch(f"/agents/{agent_id}/address", json={
        "address": "coder@wrong.domain",
    })
    assert resp.status_code == 400


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
        "address": f"coder{DOMAIN_SUFFIX}",
    })
    assert resp.status_code == 409


async def test_update_address_not_found(client):
    resp = await client.patch("/agents/nonexistent/address", json={
        "address": f"new{DOMAIN_SUFFIX}",
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
    planner = r1.json()
    coder = r2.json()

    # send a message
    await client.post("/messages/send", json={
        "agent_id": planner["id"],
        "from_agent": planner["address"],
        "to_agent": coder["address"],
        "action": "send",
        "subject": "Task",
        "body": "Do this",
    })

    # change planner's address
    new_addr = f"lead-planner{DOMAIN_SUFFIX}"
    await client.patch(f"/agents/{planner['id']}/address", json={
        "address": new_addr,
    })

    # inbox should still work for coder
    resp = await client.get(
        f"/messages/inbox/{coder['address']}",
        params={"agent_id": coder["id"]},
    )
    msgs = resp.json()
    assert len(msgs) == 1
    assert msgs[0]["from_agent"] == new_addr


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
    assert f"coder{DOMAIN_SUFFIX}" in data["agent_md"]
    # AGENT.md should mention X-API-Key
    assert "X-API-Key" in data["agent_md"]
    # CLAUDE.md should reference AGENT.md
    assert "AGENT.md" in data["claude_md"]


async def test_get_agent_setup_not_found(client):
    resp = await client.get("/agents/nonexistent-id/setup")
    assert resp.status_code == 404
