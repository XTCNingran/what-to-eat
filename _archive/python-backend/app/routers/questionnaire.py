from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import room_manager, user_store
from app.models.room import RoomState

router = APIRouter(prefix="/api/rooms", tags=["questionnaire"])


class JoinRequest(BaseModel):
    name: str


class JoinResponse(BaseModel):
    participant_id: str
    name: str
    is_new_user: bool = False


class AnswerItem(BaseModel):
    question_id: str
    choice_id: str


class SubmitRequest(BaseModel):
    participant_id: str
    answers: list[AnswerItem]


@router.post("/{room_id}/participants", response_model=JoinResponse)
async def join_room(room_id: str, body: JoinRequest):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="名字不能为空")
    name = body.name.strip()
    is_new = user_store.register(name)  # 已存在则 False，新用户则 True
    p = room_manager.add_participant(room_id, name)
    if p is None:
        raise HTTPException(status_code=404, detail="房间不存在或已关闭")
    return JoinResponse(participant_id=p.id, name=p.name, is_new_user=is_new)


@router.get("/{room_id}/questions")
async def get_questions(room_id: str):
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="房间不存在")
    return {
        "questions": [q.model_dump() for q in room.questions],
        "drinks_questions": [q.model_dump() for q in room.drinks_questions],
    }


@router.post("/{room_id}/answers")
async def submit_answers(room_id: str, body: SubmitRequest):
    raw = [{"question_id": a.question_id, "choice_id": a.choice_id} for a in body.answers]
    ok = room_manager.submit_answers(room_id, body.participant_id, raw)
    if not ok:
        raise HTTPException(status_code=400, detail="提交失败，请检查房间状态或参与者ID")
    return {"ok": True}


@router.post("/{room_id}/solo")
async def solo_join(room_id: str):
    """单人模式：自动以「我」加入房间并立即开始答题。"""
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="房间不存在")
    p = room_manager.add_participant(room_id, "我")
    if p is None:
        raise HTTPException(status_code=400, detail="无法加入房间")
    room_manager.start_questioning(room_id, room.host_token)
    return {"participant_id": p.id}
