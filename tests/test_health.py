async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_root_shows_banner(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "setup.md" in resp.text
    assert "register your agent" in resp.text
