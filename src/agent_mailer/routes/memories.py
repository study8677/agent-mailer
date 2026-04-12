import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from agent_mailer.dependencies import get_api_key_user, get_current_user
from agent_mailer.models import MemoryCreateRequest, MemoryResponse, MemoryUpdateRequest

router = APIRouter()

MAX_MEMORIES_PER_TEAM = 5


# ── Admin API (Session/Bearer auth) ──────────────────────────────────


@router.post("/admin/teams/{team_id}/memories", response_model=MemoryResponse, status_code=201)
async def create_memory(
    team_id: str, req: MemoryCreateRequest, request: Request, user: dict = Depends(get_current_user)
):
    db = request.app.state.db

    # Verify team exists and belongs to user
    cursor = await db.execute(
        "SELECT id FROM teams WHERE id = ? AND user_id = ?", (team_id, user["id"])
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Team not found")

    # Check memory count limit
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM team_memories WHERE team_id = ?", (team_id,)
    )
    row = await cursor.fetchone()
    if row["cnt"] >= MAX_MEMORIES_PER_TEAM:
        raise HTTPException(status_code=400, detail=f"Each team can have at most {MAX_MEMORIES_PER_TEAM} memories")

    # Check title uniqueness within team
    cursor = await db.execute(
        "SELECT id FROM team_memories WHERE team_id = ? AND title = ?", (team_id, req.title)
    )
    if await cursor.fetchone():
        raise HTTPException(status_code=409, detail=f"Memory title '{req.title}' already exists in this team")

    memory_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        "INSERT INTO team_memories (id, team_id, title, content, user_id, created_at, updated_at, updated_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (memory_id, team_id, req.title, req.content, user["id"], now, now, user["username"]),
    )
    await db.commit()

    return MemoryResponse(
        id=memory_id, team_id=team_id, title=req.title, content=req.content,
        user_id=user["id"], created_at=now, updated_at=now, updated_by=user["username"],
    )


@router.get("/admin/teams/{team_id}/memories", response_model=list[MemoryResponse])
async def list_memories(
    team_id: str, request: Request, user: dict = Depends(get_current_user)
):
    db = request.app.state.db

    # Verify team exists and belongs to user
    cursor = await db.execute(
        "SELECT id FROM teams WHERE id = ? AND user_id = ?", (team_id, user["id"])
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Team not found")

    cursor = await db.execute(
        "SELECT * FROM team_memories WHERE team_id = ? AND user_id = ? ORDER BY created_at",
        (team_id, user["id"]),
    )
    rows = await cursor.fetchall()
    return [MemoryResponse(**dict(r)) for r in rows]


@router.get("/admin/teams/{team_id}/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    team_id: str, memory_id: str, request: Request, user: dict = Depends(get_current_user)
):
    db = request.app.state.db

    # Verify team exists and belongs to user
    cursor = await db.execute(
        "SELECT id FROM teams WHERE id = ? AND user_id = ?", (team_id, user["id"])
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Team not found")

    cursor = await db.execute(
        "SELECT * FROM team_memories WHERE id = ? AND team_id = ? AND user_id = ?",
        (memory_id, team_id, user["id"]),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")

    return MemoryResponse(**dict(row))


@router.put("/admin/teams/{team_id}/memories/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    team_id: str, memory_id: str, req: MemoryUpdateRequest, request: Request,
    user: dict = Depends(get_current_user),
):
    db = request.app.state.db

    # Verify team exists and belongs to user
    cursor = await db.execute(
        "SELECT id FROM teams WHERE id = ? AND user_id = ?", (team_id, user["id"])
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Team not found")

    cursor = await db.execute(
        "SELECT * FROM team_memories WHERE id = ? AND team_id = ? AND user_id = ?",
        (memory_id, team_id, user["id"]),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")

    title = req.title if req.title is not None else row["title"]
    content = req.content if req.content is not None else row["content"]

    # Check title uniqueness if changed
    if req.title is not None and req.title != row["title"]:
        cursor = await db.execute(
            "SELECT id FROM team_memories WHERE team_id = ? AND title = ? AND id != ?",
            (team_id, req.title, memory_id),
        )
        if await cursor.fetchone():
            raise HTTPException(status_code=409, detail=f"Memory title '{req.title}' already exists in this team")

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE team_memories SET title = ?, content = ?, updated_at = ?, updated_by = ? WHERE id = ?",
        (title, content, now, user["username"], memory_id),
    )
    await db.commit()

    return MemoryResponse(
        id=memory_id, team_id=team_id, title=title, content=content,
        user_id=user["id"], created_at=row["created_at"], updated_at=now,
        updated_by=user["username"],
    )


@router.delete("/admin/teams/{team_id}/memories/{memory_id}")
async def delete_memory(
    team_id: str, memory_id: str, request: Request, user: dict = Depends(get_current_user)
):
    db = request.app.state.db

    # Verify team exists and belongs to user
    cursor = await db.execute(
        "SELECT id FROM teams WHERE id = ? AND user_id = ?", (team_id, user["id"])
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Team not found")

    cursor = await db.execute(
        "SELECT id FROM team_memories WHERE id = ? AND team_id = ? AND user_id = ?",
        (memory_id, team_id, user["id"]),
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Memory not found")

    await db.execute("DELETE FROM team_memories WHERE id = ?", (memory_id,))
    await db.commit()
    return {"detail": "Memory deleted", "memory_id": memory_id}


# ── Agent API (X-API-Key auth) ───────────────────────────────────────


@router.get("/memories/{memory_id}", response_model=MemoryResponse)
async def get_memory_by_agent(
    memory_id: str, request: Request, _user: dict = Depends(get_api_key_user)
):
    db = request.app.state.db

    cursor = await db.execute(
        "SELECT * FROM team_memories WHERE id = ?", (memory_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found")

    return MemoryResponse(**dict(row))
