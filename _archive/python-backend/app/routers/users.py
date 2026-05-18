from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services import user_store

router = APIRouter(prefix="/api/users", tags=["users"])


class UserRequest(BaseModel):
    username: str


@router.post("")
async def register_or_check(body: UserRequest):
    name = body.username.strip()
    if not name:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if user_store.exists(name):
        return {"exists": True, "registered": False}
    user_store.register(name)
    return {"exists": False, "registered": True}


@router.get("")
async def list_users():
    return {"users": user_store.get_all()}
