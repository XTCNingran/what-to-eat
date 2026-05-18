from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.restaurant import Restaurant
from app.services import restaurant_store

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])


class RestaurantUpdate(BaseModel):
    category_raw: str = ""
    address: str = ""
    rating: float | None = None
    avg_spend: float | None = None
    tags: list[str] = []
    phone: str = ""
    vendor: int = 0
    deleted: bool = False


@router.get("")
async def list_restaurants(include_deleted: bool = False):
    restaurants = restaurant_store.get_all(include_deleted=include_deleted)
    return {"restaurants": [r.model_dump() for r in restaurants]}


@router.post("")
async def add_restaurant(body: Restaurant):
    existing = restaurant_store.get_all(include_deleted=True)
    if any(r.name == body.name for r in existing):
        raise HTTPException(status_code=409, detail=f"餐厅「{body.name}」已存在")
    restaurant_store.upsert(body)
    return {"ok": True}


@router.post("/refresh")
async def refresh_restaurants():
    """触发重新爬取并合并数据（调用爬虫脚本）。"""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parent.parent.parent / "scraper" / "scrape_changtai_amap.py"
    if not script.exists():
        raise HTTPException(status_code=404, detail="爬虫脚本不存在")

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=f"爬虫失败: {result.stderr[:500]}")

    restaurant_store.invalidate_cache()
    count = len(restaurant_store.get_all())
    return {"ok": True, "count": count, "message": f"刷新完成，共 {count} 家餐厅"}


@router.put("/{name}")
async def update_restaurant(name: str, body: RestaurantUpdate):
    all_restaurants = restaurant_store.get_all(include_deleted=True)
    target = next((r for r in all_restaurants if r.name == name), None)
    if target is None:
        raise HTTPException(status_code=404, detail="餐厅不存在")
    updated = target.model_copy(update=body.model_dump(exclude_unset=True))
    restaurant_store.upsert(updated)
    return {"ok": True}
