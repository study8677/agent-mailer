import os
import tempfile

os.environ.setdefault(
    "AGENT_MAILER_SECRET_KEY",
    "test-secret-key-that-is-at-least-32-bytes-long",
)

import asyncio
import shutil
from pathlib import Path

import pytest

from agent_mailer.auth import hash_password, verify_password
from agent_mailer.cli import _bootstrap_admin, _generate_invite_code, _migrate_db
from agent_mailer.db import get_db, init_db


class Args:
    """Simple namespace to mimic argparse output."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
async def tmp_db(tmp_path):
    """Create a temp DB file, init schema, return path string."""
    db_file = str(tmp_path / "test.db")
    db = await get_db(db_file)
    await init_db(db)
    await db.close()
    return db_file


# --- bootstrap-admin ---


async def test_bootstrap_admin_success(tmp_db):
    args = Args(db=tmp_db, username="myadmin", password="password12345678")
    await _bootstrap_admin(args)

    db = await get_db(tmp_db)
    cursor = await db.execute("SELECT * FROM users WHERE username = 'myadmin'")
    user = await cursor.fetchone()
    assert user is not None
    assert user["is_superadmin"] == 1
    assert verify_password("password12345678", user["password_hash"])
    await db.close()


async def test_bootstrap_admin_fails_when_users_exist(tmp_db):
    # Create first admin
    args = Args(db=tmp_db, username="admin1", password="password12345678")
    await _bootstrap_admin(args)

    # Try to create second — should exit
    args2 = Args(db=tmp_db, username="admin2", password="password12345678")
    with pytest.raises(SystemExit) as exc_info:
        await _bootstrap_admin(args2)
    assert exc_info.value.code == 1


# --- generate-invite-code ---


async def test_generate_invite_code_success(tmp_db, capsys):
    # Create superadmin first
    args_ba = Args(db=tmp_db, username="admin", password="adminpass1234")
    await _bootstrap_admin(args_ba)

    args = Args(db=tmp_db, username="admin", password="adminpass1234")
    await _generate_invite_code(args)

    captured = capsys.readouterr()
    assert "Invite code:" in captured.out
    # Find the line with the invite code
    for line in captured.out.strip().split("\n"):
        if line.startswith("Invite code:"):
            code = line.split(": ", 1)[1].strip()
            break
    assert len(code) == 8

    # Verify code exists in DB
    db = await get_db(tmp_db)
    cursor = await db.execute("SELECT * FROM invite_codes WHERE code = ?", (code,))
    row = await cursor.fetchone()
    assert row is not None
    assert row["used_by"] is None
    await db.close()


async def test_generate_invite_code_wrong_password(tmp_db):
    args_ba = Args(db=tmp_db, username="admin", password="adminpass1234")
    await _bootstrap_admin(args_ba)

    args = Args(db=tmp_db, username="admin", password="wrongpass")
    with pytest.raises(SystemExit) as exc_info:
        await _generate_invite_code(args)
    assert exc_info.value.code == 1


async def test_generate_invite_code_non_superadmin(tmp_db):
    # Create superadmin
    args_ba = Args(db=tmp_db, username="admin", password="adminpass1234")
    await _bootstrap_admin(args_ba)

    # Create regular user directly in DB
    db = await get_db(tmp_db)
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO users (id, username, password_hash, is_superadmin, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), "regular", hash_password("regularpass12"), 0, now),
    )
    await db.commit()
    await db.close()

    args = Args(db=tmp_db, username="regular", password="regularpass12")
    with pytest.raises(SystemExit) as exc_info:
        await _generate_invite_code(args)
    assert exc_info.value.code == 1


# --- migrate-db ---


async def test_migrate_db(tmp_db, capsys):
    # Set up legacy data: agents with @local addresses, no user_id
    db = await get_db(tmp_db)
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    # Create legacy agents (no user_id)
    agent1_id = str(uuid.uuid4())
    agent2_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO agents (id, name, address, role, system_prompt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (agent1_id, "coder", "coder@local", "coder", "A coder", now),
    )
    await db.execute(
        "INSERT INTO agents (id, name, address, role, system_prompt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (agent2_id, "planner", "planner@local", "planner", "A planner", now),
    )

    # Create a message between them
    msg_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO messages (id, thread_id, from_agent, to_agent, action, subject, body, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (msg_id, thread_id, "planner@local", "coder@local", "send", "Task", "Do this", now),
    )

    # Create human operator (legacy)
    await db.execute(
        "INSERT INTO agents (id, name, address, role, system_prompt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("00000000-0000-0000-0000-000000000000", "Human Operator", "human-operator@local", "operator", "", now),
    )
    await db.commit()
    await db.close()

    # Run migration
    args = Args(db=tmp_db, password="migrate-pass-123")
    await _migrate_db(args)

    captured = capsys.readouterr()
    assert "Migration complete" in captured.out
    assert "Backup created" in captured.out

    # Verify
    db = await get_db(tmp_db)

    # Admin user created
    cursor = await db.execute("SELECT * FROM users WHERE username = 'admin'")
    admin = await cursor.fetchone()
    assert admin is not None
    assert admin["is_superadmin"] == 1

    # All agents have user_id
    cursor = await db.execute("SELECT * FROM agents WHERE user_id IS NULL")
    orphans = await cursor.fetchall()
    assert len(orphans) == 0

    # Addresses updated
    cursor = await db.execute("SELECT address FROM agents WHERE id = ?", (agent1_id,))
    assert (await cursor.fetchone())["address"] == "coder@admin.amp.linkyun.co"

    cursor = await db.execute("SELECT address FROM agents WHERE id = ?", (agent2_id,))
    assert (await cursor.fetchone())["address"] == "planner@admin.amp.linkyun.co"

    # Human operator address updated
    cursor = await db.execute("SELECT address FROM agents WHERE name = 'Human Operator'")
    assert (await cursor.fetchone())["address"] == "human-operator@admin.amp.linkyun.co"

    # Messages updated
    cursor = await db.execute("SELECT * FROM messages WHERE id = ?", (msg_id,))
    msg = await cursor.fetchone()
    assert msg["from_agent"] == "planner@admin.amp.linkyun.co"
    assert msg["to_agent"] == "coder@admin.amp.linkyun.co"

    # Backup exists
    backups = list(Path(tmp_db).parent.glob("*.bak.*"))
    assert len(backups) == 1

    await db.close()
