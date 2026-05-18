from __future__ import annotations
from pydantic import BaseModel


class Choice(BaseModel):
    id: str
    text: str
    weights: dict[str, float] = {}


class Question(BaseModel):
    id: str
    type: str  # "real" or "fun"
    text: str
    emoji: str
    choices: list[Choice]
    multi_select: bool = False


class Answer(BaseModel):
    question_id: str
    choice_id: str
    weights: dict[str, float] = {}
