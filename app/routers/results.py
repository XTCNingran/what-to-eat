from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import room_manager, history_store

router = APIRouter(tags=["results"])


@router.get("/api/rooms/{room_id}/results")
async def get_results(room_id: str):
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="房间不存在")
    if room.results is None:
        raise HTTPException(status_code=425, detail="结果还未生成")

    yesterday_names, two_days_names = history_store.get_recent_names()

    return {
        "results": [
            {
                "rank": i + 1,
                "name": r.restaurant.name,
                "category": r.restaurant.category_raw,
                "address": r.restaurant.address,
                "rating": r.restaurant.rating,
                "avg_spend": r.restaurant.avg_spend,
                "score": r.score,
                "reason": r.reason,
                "tags": r.restaurant.tags,
            }
            for i, r in enumerate(room.results)
        ],
        "recent_history": history_store.get_recent(5),
    }


class RecordRequest(BaseModel):
    restaurant_name: str
    room_id: str = ""
    notes: str = ""


@router.get("/api/history")
async def get_history():
    return {"records": history_store.get_recent(10)}


@router.post("/api/history")
async def add_history(body: RecordRequest):
    history_store.add_record(body.restaurant_name, body.room_id, body.notes)
    return {"ok": True}
