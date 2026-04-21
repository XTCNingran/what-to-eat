from __future__ import annotations
import json
import random
import uuid
from asyncio import Queue
from typing import Optional

from app.models.room import Room, RoomState, Participant
from app.models.question import Question, Choice, Answer
from app import config

# 全局房间存储（内存）
_rooms: dict[str, Room] = {}
# 每个房间的 SSE 队列列表
_sse_queues: dict[str, list[Queue]] = {}


def _load_question_bank() -> tuple[list[Question], list[Question]]:
    with open(config.QUESTION_BANK, encoding="utf-8") as f:
        bank = json.load(f)

    def parse_questions(raw_list) -> list[Question]:
        result = []
        for q in raw_list:
            choices = [Choice(**c) for c in q["choices"]]
            result.append(Question(
                id=q["id"],
                type=q["type"],
                text=q["text"],
                emoji=q["emoji"],
                choices=choices,
            ))
        return result

    return (
        parse_questions(bank["real_questions"]),
        parse_questions(bank["fun_questions"]),
    )


def _select_questions() -> list[Question]:
    real_qs, fun_qs = _load_question_bank()
    selected_fun = random.sample(fun_qs, min(config.FUN_QUESTIONS_COUNT, len(fun_qs)))
    return real_qs + selected_fun


def _gen_room_id() -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        rid = "".join(random.choices(chars, k=6))
        if rid not in _rooms:
            return rid


def create_room(blacklist: list[str] | None = None) -> Room:
    room_id = _gen_room_id()
    host_token = str(uuid.uuid4())
    questions = _select_questions()
    room = Room(id=room_id, host_token=host_token, questions=questions, blacklist=blacklist or [])
    _rooms[room_id] = room
    _sse_queues[room_id] = []
    return room


def get_room(room_id: str) -> Optional[Room]:
    return _rooms.get(room_id)


def add_participant(room_id: str, name: str) -> Optional[Participant]:
    room = get_room(room_id)
    if room is None or room.state == RoomState.CLOSED:
        return None
    participant_id = str(uuid.uuid4())
    p = Participant(id=participant_id, name=name)
    room.participants[participant_id] = p
    _broadcast(room_id, {"event": "participant_joined", "name": name, "count": len(room.participants)})
    return p


def start_questioning(room_id: str, host_token: str) -> bool:
    room = get_room(room_id)
    if room is None or room.host_token != host_token:
        return False
    if room.state != RoomState.WAITING:
        return False
    room.state = RoomState.QUESTIONING
    _broadcast(room_id, {"event": "questioning_started"})
    return True


def submit_answers(room_id: str, participant_id: str, raw_answers: list[dict]) -> bool:
    room = get_room(room_id)
    if room is None or room.state != RoomState.QUESTIONING:
        return False
    if participant_id not in room.participants:
        return False

    # 将答案与题目权重合并
    q_map = {q.id: q for q in room.questions}
    answers: list[Answer] = []
    for a in raw_answers:
        q = q_map.get(a["question_id"])
        if q is None:
            continue
        choice = next((c for c in q.choices if c.id == a["choice_id"]), None)
        if choice is None:
            continue
        answers.append(Answer(
            question_id=a["question_id"],
            choice_id=a["choice_id"],
            weights=choice.weights,
        ))

    room.answers[participant_id] = answers
    room.participants[participant_id].submitted = True
    submitted = sum(1 for p in room.participants.values() if p.submitted)
    total = len(room.participants)
    _broadcast(room_id, {"event": "answer_submitted", "submitted": submitted, "total": total})
    return True


def close_room(room_id: str, host_token: str) -> bool:
    room = get_room(room_id)
    if room is None or room.host_token != host_token:
        return False
    if room.state == RoomState.CLOSED:
        return True

    from app.services import scoring_engine, history_store, data_loader

    all_answers = list(room.answers.values())
    weights = scoring_engine.aggregate_weights(all_answers)
    room.aggregated_weights = weights

    restaurants = data_loader.get_restaurants()
    yesterday, two_days = history_store.get_recent_names(days=2)
    results = scoring_engine.rank_restaurants(
        restaurants, weights, two_days, yesterday,
        blacklist=room.blacklist
    )

    room.results = results
    room.state = RoomState.CLOSED
    _broadcast(room_id, {"event": "results_ready", "room_id": room_id})
    return True


def register_sse_queue(room_id: str) -> Queue:
    q: Queue = Queue()
    if room_id not in _sse_queues:
        _sse_queues[room_id] = []
    _sse_queues[room_id].append(q)
    return q


def unregister_sse_queue(room_id: str, q: Queue) -> None:
    if room_id in _sse_queues:
        try:
            _sse_queues[room_id].remove(q)
        except ValueError:
            pass


def _broadcast(room_id: str, data: dict) -> None:
    for q in _sse_queues.get(room_id, []):
        q.put_nowait(data)
