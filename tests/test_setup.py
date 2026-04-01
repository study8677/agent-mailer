async def test_setup_md_returns_markdown(client):
    resp = await client.get("/setup.md")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "# Agent Mailer" in body
    assert "/agents/register" in body
    assert "AGENT.md" in body
    assert "9800" in body


async def test_setup_md_contains_registration_fields(client):
    resp = await client.get("/setup.md")
    body = resp.text
    assert "name" in body
    assert "address" in body
    assert "role" in body
    assert "description" in body
    assert "system_prompt" in body


async def test_setup_md_contains_api_docs_link(client):
    resp = await client.get("/setup.md")
    body = resp.text
    assert "/docs" in body
    assert "/openapi.json" in body


async def test_setup_md_requires_human_interaction(client):
    """setup.md must instruct agent to ask human for role, task, and name."""
    resp = await client.get("/setup.md")
    body = resp.text
    # must ask human for role/task
    assert "请告诉我" in body
    assert "工作任务" in body
    assert "角色" in body
    # must ask human for name
    assert "名字" in body
    # must handle duplicate names
    assert "已被占用" in body
    assert "重新输入" in body
    # must instruct to wait for human
    assert "WAIT" in body or "MUST" in body
