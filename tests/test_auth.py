import os

# Set required env var before importing auth/config modules
os.environ.setdefault(
    "AGENT_MAILER_SECRET_KEY",
    "test-secret-key-that-is-at-least-32-bytes-long",
)

import time

import pytest
from agent_mailer.auth import (
    create_session_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
    verify_session_token,
)
from agent_mailer.db import get_db, init_db


# --- Password hashing ---


def test_hash_password_returns_string():
    hashed = hash_password("my-password")
    assert isinstance(hashed, str)
    assert hashed != "my-password"


def test_verify_password_correct():
    hashed = hash_password("secret")
    assert verify_password("secret", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("secret")
    assert verify_password("wrong", hashed) is False


def test_hash_password_different_salts():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2  # bcrypt uses random salt


# --- API Key ---


def test_generate_api_key_format():
    raw, key_hash = generate_api_key()
    assert raw.startswith("amk_")
    assert len(raw) == 4 + 64  # "amk_" + 64 hex chars (32 bytes)
    assert isinstance(key_hash, str)
    assert len(key_hash) == 64  # SHA-256 hex


def test_generate_api_key_unique():
    raw1, _ = generate_api_key()
    raw2, _ = generate_api_key()
    assert raw1 != raw2


def test_hash_api_key_deterministic():
    raw = "amk_abc123"
    h1 = hash_api_key(raw)
    h2 = hash_api_key(raw)
    assert h1 == h2


def test_hash_api_key_matches_generate():
    raw, key_hash = generate_api_key()
    assert hash_api_key(raw) == key_hash


# --- JWT Session Token ---


def test_create_and_verify_session_token():
    token = create_session_token("user-123")
    payload = verify_session_token(token)
    assert payload is not None
    assert payload["user_id"] == "user-123"
    assert "exp" in payload
    assert "iat" in payload
    assert "impersonated_by" not in payload


def test_session_token_with_impersonation():
    token = create_session_token("user-456", impersonated_by="admin-1")
    payload = verify_session_token(token)
    assert payload is not None
    assert payload["user_id"] == "user-456"
    assert payload["impersonated_by"] == "admin-1"
    assert "iat" in payload


def test_verify_session_token_invalid():
    result = verify_session_token("not-a-valid-token")
    assert result is None


def test_verify_session_token_expired():
    import jwt as pyjwt
    from datetime import datetime, timedelta, timezone
    from agent_mailer.config import get_secret_key

    payload = {
        "user_id": "user-old",
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = pyjwt.encode(payload, get_secret_key(), algorithm="HS256")
    result = verify_session_token(token)
    assert result is None


def test_verify_session_token_wrong_key():
    import jwt as pyjwt

    payload = {"user_id": "user-x", "exp": time.time() + 3600}
    token = pyjwt.encode(
        payload,
        "wrong-key-that-is-also-at-least-32-bytes",
        algorithm="HS256",
    )
    result = verify_session_token(token)
    assert result is None


# --- Database tables ---


@pytest.fixture
async def db():
    conn = await get_db(":memory:")
    await init_db(conn)
    yield conn
    await conn.close()


async def test_users_table_exists(db):
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    )
    row = await cursor.fetchone()
    assert row is not None


async def test_invite_codes_table_exists(db):
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='invite_codes'"
    )
    row = await cursor.fetchone()
    assert row is not None


async def test_api_keys_table_exists(db):
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'"
    )
    row = await cursor.fetchone()
    assert row is not None


async def test_agents_user_id_column(db):
    cursor = await db.execute("PRAGMA table_info(agents)")
    columns = [row[1] for row in await cursor.fetchall()]
    assert "user_id" in columns
