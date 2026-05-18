from __future__ import annotations
import asyncio
import json
from io import BytesIO

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import config
from app.services import room_manager

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class CreateRoomRequest(BaseModel):
    blacklist: list[str] = []
    host_username: str = ""


class CreateRoomResponse(BaseModel):
    room_id: str
    host_token: str
    join_url: str
    qr_url: str


class RoomStatusResponse(BaseModel):
    room_id: str
    state: str
    participant_count: int
    submitted_count: int
    has_results: bool


class StartRequest(BaseModel):
    host_token: str


@router.post("", response_model=CreateRoomResponse)
async def create_room(body: CreateRoomRequest = CreateRoomRequest()):
    room = room_manager.create_room(blacklist=body.blacklist, host_username=body.host_username)
    base = config.get_base_url()
    join_url = f"{base}/join/{room.id}"
    qr_url = f"/api/rooms/{room.id}/qr"
    return CreateRoomResponse(
        room_id=room.id,
        host_token=room.host_token,
        join_url=join_url,
        qr_url=qr_url,
    )


@router.get("/{room_id}", response_model=RoomStatusResponse)
async def get_room_status(room_id: str):
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="房间不存在")
    submitted = sum(1 for p in room.participants.values() if p.submitted)
    return RoomStatusResponse(
        room_id=room.id,
        state=room.state,
        participant_count=len(room.participants),
        submitted_count=submitted,
        has_results=room.results is not None,
    )


@router.post("/{room_id}/start")
async def start_questioning(room_id: str, body: StartRequest):
    ok = room_manager.start_questioning(room_id, body.host_token)
    if not ok:
        raise HTTPException(status_code=403, detail="无权限或状态错误")
    return {"ok": True}


@router.post("/{room_id}/close")
async def close_room(room_id: str, body: StartRequest):
    ok = room_manager.close_room(room_id, body.host_token)
    if not ok:
        raise HTTPException(status_code=403, detail="无权限或状态错误")
    return {"ok": True}


@router.get("/{room_id}/qr")
async def get_qr(room_id: str):
    try:
        import qrcode
    except ImportError:
        raise HTTPException(status_code=500, detail="qrcode 未安装")
    join_url = f"{config.get_base_url()}/join/{room_id}"
    qr = qrcode.make(join_url)
    buf = BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.read(), media_type="image/png")


@router.get("/{room_id}/events")
async def sse_events(room_id: str):
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="房间不存在")

    q = room_manager.register_sse_queue(room_id)

    async def event_generator():
        try:
            yield "data: {\"event\": \"connected\"}\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            room_manager.unregister_sse_queue(room_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
