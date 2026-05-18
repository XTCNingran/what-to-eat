from __future__ import annotations
from app.models.restaurant import Restaurant
from app.services import restaurant_store

# 细分类别 → 权重标签 映射（供迁移脚本和爬虫使用）
CATEGORY_TAG_MAP: dict[str, list[str]] = {
    "火锅": ["spicy", "warm_food", "filling", "meat"],
    "烤肉": ["meat", "filling", "premium"],
    "烧烤": ["meat", "spicy"],
    "川菜": ["spicy", "cuisine_chinese"],
    "湘菜": ["spicy", "cuisine_chinese"],
    "贵州菜": ["spicy", "cuisine_chinese"],
    "云南菜": ["spicy", "cuisine_chinese"],
    "中餐厅": ["cuisine_chinese"],
    "本帮江浙菜": ["cuisine_chinese"],
    "东北菜": ["cuisine_chinese", "filling", "meat"],
    "粤菜": ["cuisine_chinese", "light_meal"],
    "日本料理": ["cuisine_japanese", "light_meal"],
    "寿司": ["cuisine_japanese", "light_meal"],
    "拉面": ["cuisine_japanese", "warm_food", "filling"],
    "韩国料理": ["cuisine_korean", "spicy", "filling"],
    "西餐厅": ["cuisine_western"],
    "披萨": ["cuisine_western", "filling"],
    "汉堡": ["cuisine_western", "fast_service", "filling"],
    "意大利菜": ["cuisine_western"],
    "东南亚菜": ["spicy"],
    "泰国菜": ["spicy"],
    "快餐": ["fast_service", "budget_friendly"],
    "小吃快餐": ["fast_service", "budget_friendly"],
    "面馆": ["noodles", "warm_food", "filling"],
    "米粉": ["noodles", "warm_food", "filling"],
    "粉面": ["noodles", "warm_food"],
    "粥店": ["warm_food", "light_meal", "healthy"],
    "沙拉": ["healthy", "light_meal"],
    "素食": ["healthy", "light_meal"],
    "轻食": ["healthy", "light_meal"],
    "冷饮店": ["cold_food", "light_meal"],
    "甜品": ["cold_food", "light_meal"],
    "咖啡厅": ["light_meal", "premium"],
    "饺子": ["cuisine_chinese", "filling"],
    "面包": ["light_meal"],
}


def _parse_float(val) -> float | None:
    if val is None or val == "" or val == "暂无":
        return None
    try:
        return float(str(val).replace("元", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_tags(category_raw: str) -> list[str]:
    tags: list[str] = []
    for part in category_raw.split(";"):
        part = part.strip()
        if part in CATEGORY_TAG_MAP:
            tags.extend(CATEGORY_TAG_MAP[part])
    return list(dict.fromkeys(tags))  # 去重并保留插入顺序


def get_restaurants(force_reload: bool = False) -> list[Restaurant]:
    if force_reload:
        restaurant_store.invalidate_cache()
    return restaurant_store.get_all()
