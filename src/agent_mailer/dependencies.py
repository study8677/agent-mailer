from fastapi import Depends, HTTPException, Request

from agent_mailer.auth import hash_api_key, verify_session_token


async def get_current_user(request: Request) -> dict:
    token = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_session_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    db = request.app.state.db
    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (payload["user_id"],))
    user = await cursor.fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(user)


async def get_api_key_user(request: Request) -> dict:
    raw_key = request.headers.get("x-api-key")
    if not raw_key:
        raise HTTPException(status_code=401, detail="API key required")
    key_hash = hash_api_key(raw_key)
    db = request.app.state.db
    cursor = await db.execute(
        "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1", (key_hash,)
    )
    key_row = await cursor.fetchone()
    if key_row is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    from datetime import datetime, timezone

    await db.execute(
        "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), key_row["id"]),
    )
    await db.commit()
    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (key_row["user_id"],))
    user = await cursor.fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(user)


async def require_superadmin(user: dict = Depends(get_current_user)) -> dict:
    if not user["is_superadmin"]:
        raise HTTPException(status_code=403, detail="Superadmin required")
    return user
