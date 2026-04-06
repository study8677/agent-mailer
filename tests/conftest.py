import os

os.environ.setdefault(
    "AGENT_MAILER_SECRET_KEY",
    "test-secret-key-that-is-at-least-32-bytes-long",
)

import pytest
from httpx import ASGITransport, AsyncClient
from agent_mailer.main import app
from agent_mailer.db import init_db, get_db
from agent_mailer.bootstrap import ensure_bootstrap_invite_code
from agent_mailer.auth import create_session_token, hash_password, generate_api_key


async def _setup_test_user(db) -> tuple[str, str, str]:
    """Create a test user with an API key, return (user_id, raw_api_key, session_token)."""
    import uuid
    from datetime import datetime, timezone

    # Bootstrap invite code
    code = await ensure_bootstrap_invite_code(db)

    # Create test user (first user = superadmin)
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO users (id, username, password_hash, is_superadmin, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "testuser", hash_password("test-password-123"), 1, now),
    )
    # Mark bootstrap invite code as used
    await db.execute(
        "UPDATE invite_codes SET used_by = ?, used_at = ? WHERE code = ? AND used_by IS NULL",
        (user_id, now, code),
    )
    # Create API key
    raw_key, key_hash = generate_api_key()
    key_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO api_keys (id, user_id, key_hash, name, created_at) VALUES (?, ?, ?, ?, ?)",
        (key_id, user_id, key_hash, "test-key", now),
    )
    await db.commit()

    token = create_session_token(user_id)
    return user_id, raw_key, token


@pytest.fixture
async def client():
    db = await get_db(":memory:")
    await init_db(db)
    user_id, raw_key, token = await _setup_test_user(db)
    app.state.db = db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": raw_key},
        cookies={"session_token": token},
    ) as c:
        yield c
    await db.close()
