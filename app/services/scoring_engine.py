from __future__ import annotations
import math
import random
from collections import defaultdict
from datetime import datetime

from app import config
from app.models.restaurant import Restaurant, ScoredRestaurant
from app.models.question import Answer
from app.services import history_store

SPICY_TAGS    = {"spicy"}
WARM_TAGS     = {"warm_food"}
MEAT_TAGS     = {"meat"}
LIGHT_TAGS    = {"light_meal"}
FILLING_TAGS  = {"filling"}
HEALTHY_TAGS  = {"healthy"}
FAST_TAGS     = {"fast_service"}
NOODLE_TAGS   = {"noodles"}
CUISINE_TAGS  = {"cuisine_chinese", "cuisine_japanese", "cuisine_western", "cuisine_korean"}

_MONDAY_BUDGET_BOOST    = 0.10
_WEEKEND_PREMIUM_BOOST  = 0.15
_FATIGUE_2X_MULTIPLIER  = 0.7
_FATIGUE_3X_MULTIPLIER  = 0.4
_DIVERSITY_JITTER_RANGE = 0.10


def aggregate_weights(all_participant_answers: list[list[Answer]]) -> dict[str, float]:
    """将所有参与者的答案权重聚合为一个权重字典。budget_max 取最小值，其余求和。"""
    totals: dict[str, float] = defaultdict(float)
    budget_votes: list[float] = []

    for participant_answers in all_participant_answers:
        for answer in participant_answers:
            for dim, val in answer.weights.items():
                if dim == "budget_max":
                    budget_votes.append(val)
                else:
                    totals[dim] += val

    if budget_votes:
        totals["budget_max"] = min(budget_votes)

    return dict(totals)


def _haversine(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _is_drinks(r: Restaurant) -> bool:
    """饮品/轻食店：有 drinks_shop 标签，或有 cold_food 且无 cuisine_* 标签。"""
    tags = set(r.tags)
    if "drinks_shop" in tags:
        return True
    return "cold_food" in tags and not any(t.startswith("cuisine_") for t in tags)


def _filter_pool(
    restaurants: list[Restaurant],
    weights: dict[str, float],
) -> list[Restaurant]:
    """根据控制信号过滤候选池，返回符合条件的餐厅列表。"""
    pool = [r for r in restaurants if not r.deleted]

    if weights.get("drinks_only", 0) > 0:
        pool = [r for r in pool if _is_drinks(r)]
    else:
        pool = [r for r in pool if not _is_drinks(r)]

    if weights.get("vendor_only", 0) > 0:
        pool = [r for r in pool if r.vendor == 1]

    if weights.get("meal_fast", 0) > 0:
        pool = [r for r in pool if "fast_service" in r.tags]
    elif weights.get("meal_proper", 0) > 0:
        pool = [r for r in pool if "fast_service" not in r.tags]

    if weights.get("nearby_only", 0) > 0:
        pool = [
            r for r in pool
            if r.lng and r.lat
            and _haversine(r.lng, r.lat, config.OFFICE_LNG, config.OFFICE_LAT) <= config.NEARBY_RADIUS_M
        ]

    return pool


def score_restaurant(
    restaurant: Restaurant,
    weights: dict[str, float],
    recent_names: set[str],
    yesterday_names: set[str],
) -> ScoredRestaurant | None:
    """对单个餐厅打分，返回 None 表示被过滤（预算超限）。"""
    reasons: list[str] = []

    budget_max = weights.get("budget_max", 999)
    if restaurant.avg_spend and restaurant.avg_spend > budget_max:
        return None

    score = (restaurant.rating or 3.5) * 2.0

    tags = set(restaurant.tags)

    if tags & SPICY_TAGS:
        delta = weights.get("spicy", 0)
        score += delta
        if delta > 0:
            reasons.append("合口味辣度")

    if tags & WARM_TAGS:
        delta = weights.get("warm_food", 0)
        score += delta
        if delta > 0:
            reasons.append("有热汤热食")

    if tags & MEAT_TAGS:
        delta = weights.get("meat", 0)
        score += delta
        if delta > 0:
            reasons.append("肉食爱好者加分")

    if tags & LIGHT_TAGS:
        delta = weights.get("healthy", 0) * 0.5 + weights.get("light_meal", 0) * 0.5
        score += delta

    if tags & FILLING_TAGS:
        delta = weights.get("filling", 0)
        score += delta

    if tags & HEALTHY_TAGS:
        delta = weights.get("healthy", 0)
        score += delta
        if delta > 0:
            reasons.append("健康选择")

    if tags & FAST_TAGS:
        delta = weights.get("fast_service", 0)
        score += delta
        if delta > 0:
            reasons.append("快速上菜")

    if tags & NOODLE_TAGS:
        score -= weights.get("avoid_noodles", 0)

    for cuisine_tag in CUISINE_TAGS:
        if cuisine_tag in tags:
            delta = weights.get(cuisine_tag, 0)
            score += delta

    if restaurant.avg_spend and restaurant.avg_spend < 25:
        delta = weights.get("budget_friendly", 0)
        score += delta
        if delta > 0:
            reasons.append("超划算")

    if restaurant.rating and restaurant.rating >= 4.5:
        delta = weights.get("premium", 0)
        score += delta
        if delta > 0:
            reasons.append("高分好评")

    name = restaurant.name
    if name in yesterday_names:
        score -= 3.0
        reasons.append("⚠️ 昨天刚去过")
    elif name in recent_names:
        score -= 1.5
        reasons.append("⚠️ 前天去过")

    score += weights.get("random_bonus", 0) * random.uniform(0, 1)

    reason_str = "、".join(reasons) if reasons else "综合评分推荐"
    return ScoredRestaurant(restaurant=restaurant, score=round(score, 3), reason=reason_str)


def rank_restaurants(
    restaurants: list[Restaurant],
    weights: dict[str, float],
    recent_names: set[str],
    yesterday_names: set[str],
    top_n: int = 20,
    blacklist: list[str] | None = None,
) -> list[ScoredRestaurant]:
    """过滤、打分、叠加动态信号、多样性扰动，返回前 top_n 名。"""
    blacklist_set = set(blacklist or [])

    # 1. 控制信号过滤
    pool = _filter_pool(restaurants, weights)
    pool = [r for r in pool if r.name not in blacklist_set]

    # 2. 打分
    scored: list[ScoredRestaurant] = []
    for r in pool:
        result = score_restaurant(r, weights, recent_names, yesterday_names)
        if result is not None:
            scored.append(result)

    # 3. 星期几加成（作用于基础分增量）
    weekday = datetime.now().weekday()
    for i, r in enumerate(scored):
        tags = set(r.restaurant.tags)
        base = (r.restaurant.rating or 3.5) * 2.0
        if weekday == 0 and "budget_friendly" in tags:          # 周一
            scored[i] = r.model_copy(update={"score": r.score + base * _MONDAY_BUDGET_BOOST})
        elif weekday in (4, 5, 6) and "premium" in tags:       # 周五/六/日
            scored[i] = r.model_copy(update={"score": r.score + base * _WEEKEND_PREMIUM_BOOST})

    # 4. 菜系疲劳（乘以衰减系数）
    cuisine_counts = history_store.get_recent_cuisines(3)
    if cuisine_counts:
        for i, r in enumerate(scored):
            tags = set(r.restaurant.tags)
            max_count = max(
                (cuisine_counts.get(t, 0) for t in tags if t.startswith("cuisine_")),
                default=0,
            )
            if max_count == 2:
                scored[i] = r.model_copy(update={"score": r.score * _FATIGUE_2X_MULTIPLIER})
            elif max_count >= 3:
                scored[i] = r.model_copy(update={"score": r.score * _FATIGUE_3X_MULTIPLIER})

    # 5. 排序
    scored.sort(key=lambda x: x.score, reverse=True)

    # 6. 多样性扰动（第 4–20 名）
    if len(scored) > 3:
        for i, r in enumerate(scored[3:], start=3):
            jitter = 1.0 + random.uniform(-_DIVERSITY_JITTER_RANGE, _DIVERSITY_JITTER_RANGE) * (r.restaurant.rating or 4.0) / 5.0  # scale by rating so lower-quality options get smaller variance
            scored[i] = r.model_copy(update={"score": r.score * jitter})
        scored[3:] = sorted(scored[3:], key=lambda x: x.score, reverse=True)

    return scored[:top_n]
