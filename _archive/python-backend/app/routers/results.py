from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import room_manager, history_store
from app.models.question import Answer

router = APIRouter(tags=["results"])


def _build_summary_sentence(answers: list[Answer]) -> str:
    weights: dict[str, float] = {}
    for a in answers:
        for dim, val in a.weights.items():
            weights[dim] = weights.get(dim, 0) + val

    if weights.get("drinks_only", 0) > 0:
        parts = ["今天没什么胃口，只想喝点东西"]
        if weights.get("vendor_only", 0) > 0:
            parts.append("偏好认证供应商")
        budget = weights.get("budget_max", 0)
        if budget == 30:
            parts.append("预算30元以内")
        elif budget == 60:
            parts.append("预算30-60元")
        return "，".join(parts)

    parts = []

    cuisine_map = {
        "cuisine_chinese": "想吃中餐",
        "cuisine_japanese": "想吃日料",
        "cuisine_western": "想吃西式",
    }
    for dim, text in cuisine_map.items():
        if weights.get(dim, 0) > 0:
            parts.append(text)
            break

    if weights.get("vendor_only", 0) > 0:
        parts.append("偏好SAP认证餐厅")

    if weights.get("meal_fast", 0) > 0:
        parts.append("时间比较赶")
    elif weights.get("meal_proper", 0) > 0:
        parts.append("时间充裕想坐下来吃")

    budget = weights.get("budget_max", 0)
    if budget == 30:
        parts.append("预算30元以内")
    elif budget == 60:
        parts.append("预算在30-60元")
    elif budget == 999:
        parts.append("预算不限")

    if weights.get("nearby_only", 0) > 0:
        parts.append("希望离公司近一点")

    if weights.get("premium", 0) > 1:
        parts.append("想好好犒劳自己")
    elif weights.get("healthy", 0) > 1:
        parts.append("想吃健康一点")
    elif weights.get("filling", 0) > 1:
        parts.append("想吃得饱一点")

    if not parts:
        return "随遇而安，什么都行"

    return "，".join(parts)


@router.get("/api/rooms/{room_id}/results")
async def get_results(room_id: str):
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="房间不存在")
    if room.results is None:
        raise HTTPException(status_code=425, detail="结果还未生成")

    participant_names = [room.participants[pid].name for pid in room.participants]
    yesterday_names, two_days_names = history_store.get_recent_names(participant_names)

    summaries = [
        {
            "name": room.participants[pid].name,
            "summary": _build_summary_sentence(answers),
        }
        for pid, answers in room.answers.items()
        if pid in room.participants
    ]

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
        "recent_history": history_store.get_recent_all(5),
        "drinks_only_notices": room.drinks_only_participants,
        "participant_summaries": summaries,
    }


class RecordRequest(BaseModel):
    restaurant_name: str
    room_id: str = ""
    notes: str = ""


@router.get("/api/history")
async def get_history():
    return {"records": history_store.get_recent_all(10)}


@router.post("/api/history")
async def add_history(body: RecordRequest):
    room = room_manager.get_room(body.room_id) if body.room_id else None
    if room is not None:
        usernames = [p.name for p in room.participants.values()]
        history_store.add_record_for_users(body.restaurant_name, usernames, body.room_id)
    else:
        history_store.add_record(body.restaurant_name, username="", room_id=body.room_id)
    return {"ok": True}
