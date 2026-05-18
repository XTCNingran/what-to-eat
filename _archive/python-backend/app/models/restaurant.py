from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class Restaurant(BaseModel):
    name: str
    category_raw: str
    address: str
    rating: Optional[float] = None
    avg_spend: Optional[float] = None
    lng: Optional[float] = None
    lat: Optional[float] = None
    district: str = ""
    poi_id: str = ""
    tags: list[str] = []
    phone: str = ""
    vendor: int = 0        # 0=普通餐厅, 1=合作供应商
    deleted: bool = False  # 软删除标记


class ScoredRestaurant(BaseModel):
    restaurant: Restaurant
    score: float
    reason: str
