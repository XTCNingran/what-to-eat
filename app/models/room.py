from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel

from app.models.question import Question, Answer
from app.models.restaurant import ScoredRestaurant


class RoomState(str, Enum):
    WAITING = "waiting"
    QUESTIONING = "questioning"
    CLOSED = "closed"


class Participant(BaseModel):
    id: str
    name: str
    submitted: bool = False


class Room(BaseModel):
    id: str
    host_token: str
    state: RoomState = RoomState.WAITING
    participants: dict[str, Participant] = {}
    questions: list[Question] = []
    answers: dict[str, list[Answer]] = {}  # participant_id -> answers
    results: Optional[list[ScoredRestaurant]] = None
    aggregated_weights: Optional[dict[str, float]] = None
    blacklist: list[str] = []
    drinks_only_participants: list[str] = []

    class Config:
        use_enum_values = True
