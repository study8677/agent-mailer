import pytest
from httpx import ASGITransport, AsyncClient
from agent_mailer.main import app
from agent_mailer.db import init_db, get_db


@pytest.fixture
async def client():
    db = await get_db(":memory:")
    await init_db(db)
    app.state.db = db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.close()
