from __future__ import annotations
import json
from app import config
from app.models.restaurant import Restaurant

_cache: list[Restaurant] | None = None


def _load() -> list[Restaurant]:
    global _cache
    if not config.RESTAURANT_JSON.exists():
        raise FileNotFoundError(
            f"找不到 {config.RESTAURANT_JSON}，请先运行 scripts/migrate_excel_to_json.py"
        )
    data = json.loads(config.RESTAURANT_JSON.read_text(encoding="utf-8"))
    _cache = [Restaurant(**r) for r in data]
    return _cache


def get_all(include_deleted: bool = False) -> list[Restaurant]:
    """返回所有餐厅，默认过滤软删除的条目。"""
    restaurants = _load()
    if include_deleted:
        return restaurants
    return [r for r in restaurants if not r.deleted]


def _save(restaurants: list[Restaurant]) -> None:
    """原子写入：先写 .tmp，成功后替换。"""
    global _cache
    data = [r.model_dump() for r in restaurants]
    tmp = config.RESTAURANT_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(config.RESTAURANT_JSON)
    _cache = restaurants


def upsert(restaurant: Restaurant) -> None:
    """按名称更新（存在则覆盖，否则追加）。"""
    restaurants = _load()
    for i, r in enumerate(restaurants):
        if r.name == restaurant.name:
            restaurants[i] = restaurant
            _save(restaurants)
            return
    restaurants.append(restaurant)
    _save(restaurants)


def soft_delete(name: str) -> bool:
    """将指定餐厅标记为 deleted=True，返回是否找到该餐厅。"""
    restaurants = _load()
    for r in restaurants:
        if r.name == name:
            r.deleted = True
            _save(restaurants)
            return True
    return False


def invalidate_cache() -> None:
    global _cache
    _cache = None
