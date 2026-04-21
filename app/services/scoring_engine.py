from __future__ import annotations
import random
from collections import defaultdict
from datetime import date

from app.models.restaurant import Restaurant, ScoredRestaurant
from app.models.question import Answer

# 标签集合，用于餐厅特征判断
SPICY_TAGS = {"spicy"}
WARM_TAGS = {"warm_food"}
MEAT_TAGS = {"meat"}
LIGHT_TAGS = {"light_meal"}
FILLING_TAGS = {"filling"}
HEALTHY_TAGS = {"healthy"}
FAST_TAGS = {"fast_service"}
NOODLE_TAGS = {"noodles"}
CUISINE_TAGS = {"cuisine_chinese", "cuisine_japanese", "cuisine_western", "cuisine_korean"}


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


def score_restaurant(
    restaurant: Restaurant,
    weights: dict[str, float],
    recent_names: set[str],
    yesterday_names: set[str],
) -> ScoredRestaurant | None:
    """对单个餐厅打分，返回 None 表示被过滤（预算超限）。"""
    reasons: list[str] = []

    # 预算硬过滤
    budget_max = weights.get("budget_max", 999)
    if restaurant.avg_spend and restaurant.avg_spend > budget_max:
        return None

    # 基础分：评分 × 2（0–10 分）
    score = (restaurant.rating or 3.5) * 2.0

    tags = set(restaurant.tags)

    # 口味匹配
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

    # 菜系匹配
    for cuisine_tag in CUISINE_TAGS:
        if cuisine_tag in tags:
            delta = weights.get(cuisine_tag, 0)
            score += delta

    # 性价比
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

    # 历史惩罚
    name = restaurant.name
    if name in yesterday_names:
        score -= 3.0
        reasons.append("⚠️ 昨天刚去过")
    elif name in recent_names:
        score -= 1.5
        reasons.append("⚠️ 前天去过")

    # 随机小加成，打破平局
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
    """对全部餐厅打分，过滤黑名单后排序，返回前 top_n 名。"""
    blacklist_set = set(blacklist or [])
    scored = []
    for r in restaurants:
        if r.name in blacklist_set:
            continue
        result = score_restaurant(r, weights, recent_names, yesterday_names)
        if result is not None:
            scored.append(result)
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:top_n]
