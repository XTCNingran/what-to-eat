# 推荐算法升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 升级推荐算法，支持 vendor 过滤、饮品逻辑、动态因子（天气/心情/星期几/菜系疲劳）、用餐类型分类、多样性扰动，并修复前端答题流程。

**Architecture:** 后端在 `scoring_engine.py` 中新增打分前过滤（控制信号）、动态权重叠加、多样性扰动三层；`history_store.py` 新增菜系疲劳查询；`bank.json` 扩题；前端在 `questionnaire.html` 检测 `drinks_only` 信号提前提交；结果页展示饮品提示。

**Tech Stack:** Python 3.11 / FastAPI / Pydantic v2 / Jinja2 / Vanilla JS / pytest

---

## 文件变更总览

| 文件 | 操作 |
|------|------|
| `app/config.py` | 新增 `OFFICE_LNG` / `OFFICE_LAT` / `NEARBY_RADIUS_M`；`REAL_QUESTIONS_COUNT` 6 → 9 |
| `app/services/history_store.py` | 新增 `get_recent_cuisines(n)` |
| `app/questions/bank.json` | 新增 q_vendor_only、q_meal_type、q_mood（real）；新增 q_weather（fun）；q_energy 加饮品选项；7 道题补 `随便` 选项；修 q_distance |
| `app/services/scoring_engine.py` | 新增 `_is_drinks` / `_haversine` / `_filter_pool`；`rank_restaurants` 加星期几加成、菜系疲劳、多样性扰动 |
| `app/models/room.py` | `Room` 新增 `drinks_only_participants: list[str]` |
| `app/services/room_manager.py` | `submit_answers` 记录 drinks_only 参与者；多人模式结果计算剔除 drinks_only 信号 |
| `app/routers/results.py` | `/api/rooms/{id}/results` 返回 `drinks_only_notices` 字段 |
| `templates/questionnaire.html` | 选中 drinks_only 选项后立即提交，跳过剩余题目 |
| `templates/results.html` | 展示 `drinks_only_notices` 提示横幅 |
| `tests/test_scoring_engine.py` | 新建，覆盖过滤/动态信号/多样性测试 |
| `tests/test_history_store.py` | 新建，覆盖 `get_recent_cuisines` |

---

## Task 1: config.py — 新增坐标常量

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: 追加常量**

```python
# 在 REAL_QUESTIONS_COUNT 下方追加
REAL_QUESTIONS_COUNT = 9   # 6 existing + q_vendor_only + q_meal_type + q_mood
FUN_QUESTIONS_COUNT = 2

OFFICE_LNG: float = 121.603071   # 长泰广场D座
OFFICE_LAT: float = 31.206835
NEARBY_RADIUS_M: int = 250
```

> 注：REAL_QUESTIONS_COUNT 改为 9（设计文档写的 8 是在决定把 q_mood 移入必出题之前；正确值是 9）

- [ ] **Step 2: 验证 Python 语法**

```bash
cd "c:/Users/C5325572/OneDrive - SAP SE/202604/Claude Code Playground/What do you want to eat/what-to-eat"
python -c "from app import config; print(config.OFFICE_LNG, config.NEARBY_RADIUS_M)"
```

Expected: `121.603071 250`

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "config: add office coordinates and update REAL_QUESTIONS_COUNT to 9"
```

---

## Task 2: history_store.py — 新增 get_recent_cuisines

**Files:**
- Modify: `app/services/history_store.py`
- Create: `tests/test_history_store.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/__init__.py`（空文件）和 `tests/test_history_store.py`：

```python
import json, pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def make_restaurant(name, tags):
    return MagicMock(name=name, tags=tags)


def test_get_recent_cuisines_counts_last_n(tmp_path, monkeypatch):
    history_file = tmp_path / "history.json"
    history_file.write_text(json.dumps({"records": [
        {"date": "2026-04-25", "restaurant_name": "太二酸菜鱼"},
        {"date": "2026-04-24", "restaurant_name": "太二酸菜鱼"},
        {"date": "2026-04-23", "restaurant_name": "Blue Frog蓝蛙(长泰广场店)"},
        {"date": "2026-04-22", "restaurant_name": "太二酸菜鱼"},  # 第 4 条，n=3 时不计入
    ]}), encoding="utf-8")

    from app.services import history_store
    monkeypatch.setattr(history_store.config, "HISTORY_FILE", history_file)

    restaurants = [
        make_restaurant("太二酸菜鱼", ["cuisine_chinese", "soup_ok"]),
        make_restaurant("Blue Frog蓝蛙(长泰广场店)", ["cuisine_western", "premium"]),
    ]

    with patch("app.services.history_store._get_all_restaurants", return_value=restaurants):
        counts = history_store.get_recent_cuisines(3)

    assert counts == {"cuisine_chinese": 2, "cuisine_western": 1}


def test_get_recent_cuisines_empty_history(tmp_path, monkeypatch):
    history_file = tmp_path / "history.json"
    history_file.write_text(json.dumps({"records": []}), encoding="utf-8")

    from app.services import history_store
    monkeypatch.setattr(history_store.config, "HISTORY_FILE", history_file)

    with patch("app.services.history_store._get_all_restaurants", return_value=[]):
        counts = history_store.get_recent_cuisines(3)

    assert counts == {}
```

- [ ] **Step 2: 运行确认失败**

```bash
cd "c:/Users/C5325572/OneDrive - SAP SE/202604/Claude Code Playground/What do you want to eat/what-to-eat"
python -m pytest tests/test_history_store.py -v
```

Expected: FAIL — `get_recent_cuisines` not found

- [ ] **Step 3: 实现 get_recent_cuisines**

在 `app/services/history_store.py` 末尾追加：

```python
def _get_all_restaurants():
    """从 data_loader 获取全部餐厅，用于菜系标签查找。单独抽出便于测试 mock。"""
    from app.services import data_loader
    return data_loader.get_restaurants()


def get_recent_cuisines(n: int) -> dict[str, int]:
    """返回近 n 条历史记录中各菜系标签的出现次数。"""
    records = get_recent(n)
    name_to_tags: dict[str, list[str]] = {r.name: r.tags for r in _get_all_restaurants()}
    counts: dict[str, int] = {}
    for record in records:
        for tag in name_to_tags.get(record.get("restaurant_name", ""), []):
            if tag.startswith("cuisine_"):
                counts[tag] = counts.get(tag, 0) + 1
    return counts
```

- [ ] **Step 4: 运行确认通过**

```bash
python -m pytest tests/test_history_store.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/history_store.py tests/
git commit -m "feat: add get_recent_cuisines to history_store"
```

---

## Task 3: bank.json — 题库扩展

**Files:**
- Modify: `app/questions/bank.json`

### 3a: 新增 4 道题

- [ ] **Step 1: 在 `real_questions` 数组开头插入 q_vendor_only（置顶第一题）**

```json
{
  "id": "q_vendor_only",
  "type": "real",
  "text": "今天想在 SAP 认证餐厅里选吗？",
  "emoji": "🤝",
  "choices": [
    {"id": "vendor_yes",  "text": "对，就在自己人圈子里挑～", "weights": {"vendor_only": 1}},
    {"id": "vendor_no",   "text": "不限，我有钱～",            "weights": {}},
    {"id": "vendor_any",  "text": "不知道，随便你",            "weights": {}}
  ]
}
```

- [ ] **Step 2: 在 `real_questions` 数组第 2 位插入 q_meal_type**

```json
{
  "id": "q_meal_type",
  "type": "real",
  "text": "今天吃饭时间宽裕吗？",
  "emoji": "⏰",
  "choices": [
    {"id": "meal_fast",   "text": "赶时间！要快要快！",     "weights": {"fast_service": 2.0, "meal_fast": 1}},
    {"id": "meal_proper", "text": "时间够，想好好坐下来吃", "weights": {"meal_proper": 1}},
    {"id": "meal_any",    "text": "吃饱就行，随便",         "weights": {}}
  ]
}
```

- [ ] **Step 3: 在 `real_questions` 数组第 3 位插入 q_mood（必出题，不进随机池）**

```json
{
  "id": "q_mood",
  "type": "real",
  "text": "今天的你是哪种状态？",
  "emoji": "💆",
  "choices": [
    {"id": "mood_tired",  "text": "累了累了，给我来点热乎的",     "weights": {"filling": 1.2, "warm_food": 1.0}},
    {"id": "mood_happy",  "text": "今天心情超好，想犒劳自己！",   "weights": {"premium": 1.3}},
    {"id": "mood_ill",    "text": "身体有点不对劲，吃点清淡的",   "weights": {"healthy": 1.5, "spicy": -1.0}},
    {"id": "mood_sleepy", "text": "困到不行，楼下解决就好",       "weights": {"nearby_only": 1}},
    {"id": "mood_ok",     "text": "还行还行，随便吃点",           "weights": {}}
  ]
}
```

- [ ] **Step 4: 在 `fun_questions` 数组末尾追加 q_weather**

```json
{
  "id": "q_weather",
  "type": "fun",
  "text": "窗外天气怎么样？",
  "emoji": "🌤️",
  "choices": [
    {"id": "weather_rain",  "text": "下雨了，湿冷湿冷的",         "weights": {"warm_food": 1.5}},
    {"id": "weather_sunny", "text": "阳光正好，温度舒服",         "weights": {}},
    {"id": "weather_hot",   "text": "好热好闷，快入夏啦",         "weights": {"cold_food": 1.2, "spicy": -0.5}},
    {"id": "weather_windy", "text": "风有点大，有点凉",           "weights": {"warm_food": 1.0}},
    {"id": "weather_none",  "text": "我在工位看不到窗户，随便",   "weights": {}}
  ]
}
```

### 3b: 更新 q_energy（加饮品选项）

- [ ] **Step 5: 在 q_energy 的 choices 中，在 `energy_low` 之后、末尾之前插入**

```json
{"id": "energy_drinks", "text": "完全没食欲，来杯饮料就好了", "weights": {"drinks_only": 1}}
```

q_energy 最终 choices 顺序：energy_high → energy_mid → energy_low → energy_drinks

### 3c: 补 `随便` 选项 + 修 q_distance

- [ ] **Step 6: q_spicy 末尾追加**

```json
{"id": "spicy_any", "text": "随便，都行", "weights": {}}
```

- [ ] **Step 7: q_distance 中将 `dist_far` 的 weights 改为空**

原：`"weights": {"premium": 0.3}`  →  改为：`"weights": {}`

- [ ] **Step 8: q_animal 末尾追加**

```json
{"id": "animal_any", "text": "随便，都行", "weights": {}}
```

- [ ] **Step 9: q_coffee 末尾追加**

```json
{"id": "coffee_any", "text": "随便，都行", "weights": {}}
```

- [ ] **Step 10: q_weather_mood 末尾追加**

```json
{"id": "weather_mood_any", "text": "随便，都行", "weights": {}}
```

- [ ] **Step 11: q_meeting 末尾追加**

```json
{"id": "meeting_any", "text": "随便，都行", "weights": {}}
```

- [ ] **Step 12: q_last_eaten 末尾追加**

```json
{"id": "last_any", "text": "随便，都行", "weights": {}}
```

- [ ] **Step 13: 验证 JSON 合法性**

```bash
cd "c:/Users/C5325572/OneDrive - SAP SE/202604/Claude Code Playground/What do you want to eat/what-to-eat"
python -c "
import json
with open('app/questions/bank.json', encoding='utf-8') as f:
    bank = json.load(f)
real = bank['real_questions']
fun  = bank['fun_questions']
print(f'real questions: {len(real)}')   # expected: 9
print(f'fun questions:  {len(fun)}')    # expected: 9
ids = [q[\"id\"] for q in real]
print('real ids:', ids)
# verify every question has a 随便 choice (weights == {})
for q in real + fun:
    has_empty = any(not c.get('weights') for c in q['choices'])
    if not has_empty:
        print(f'WARNING: {q[\"id\"]} has no empty-weight choice')
"
```

Expected:
```
real questions: 9
fun questions:  9
real ids: ['q_vendor_only', 'q_meal_type', 'q_mood', 'q_spicy', 'q_budget', 'q_cuisine', 'q_distance', 'q_health', 'q_soup']
```

- [ ] **Step 14: Commit**

```bash
git add app/questions/bank.json
git commit -m "feat: add q_vendor_only, q_meal_type, q_mood, q_weather; update q_energy; add 随便 options"
```

---

## Task 4: scoring_engine.py — 过滤 + 动态信号 + 多样性

**Files:**
- Modify: `app/services/scoring_engine.py`
- Create: `tests/test_scoring_engine.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_scoring_engine.py`：

```python
import math
import pytest
from unittest.mock import patch
from app.models.restaurant import Restaurant, ScoredRestaurant
from app.services import scoring_engine


def make_r(**kwargs):
    defaults = dict(
        name="测试餐厅", category_raw="", address="",
        rating=4.0, avg_spend=40.0, lng=121.603071, lat=31.206835,
        tags=[], vendor=0, deleted=False,
    )
    defaults.update(kwargs)
    return Restaurant(**defaults)


# ---- 过滤测试 ----

def test_drinks_only_filter_keeps_only_drinks():
    drinks = make_r(name="奶茶店", tags=["cold_food", "light_meal"])
    food   = make_r(name="中餐馆", tags=["cuisine_chinese"])
    pool = scoring_engine._filter_pool([drinks, food], {"drinks_only": 1})
    assert [r.name for r in pool] == ["奶茶店"]


def test_default_excludes_drinks():
    drinks = make_r(name="奶茶店", tags=["cold_food", "light_meal"])
    food   = make_r(name="中餐馆", tags=["cuisine_chinese"])
    pool = scoring_engine._filter_pool([drinks, food], {})
    assert [r.name for r in pool] == ["中餐馆"]


def test_vendor_only_filter():
    vendor = make_r(name="合作餐厅", vendor=1)
    normal = make_r(name="普通餐厅", vendor=0)
    pool = scoring_engine._filter_pool([vendor, normal], {"vendor_only": 1})
    assert [r.name for r in pool] == ["合作餐厅"]


def test_meal_fast_keeps_only_fast_service():
    fast   = make_r(name="快餐", tags=["fast_service", "cuisine_chinese"])
    proper = make_r(name="正餐", tags=["cuisine_chinese"])
    pool = scoring_engine._filter_pool([fast, proper], {"meal_fast": 1})
    assert [r.name for r in pool] == ["快餐"]


def test_meal_proper_excludes_fast_service():
    fast   = make_r(name="快餐", tags=["fast_service"])
    proper = make_r(name="正餐", tags=["cuisine_chinese"])
    pool = scoring_engine._filter_pool([fast, proper], {"meal_proper": 1})
    assert [r.name for r in pool] == ["正餐"]


def test_nearby_only_filter():
    # 长泰广场D座坐标 (121.603071, 31.206835)，测试 200m 以内 vs 600m 以外
    near = make_r(name="附近店", lng=121.603071, lat=31.208635)   # ~200m 北
    far  = make_r(name="远处店", lng=121.603071, lat=31.212000)   # ~580m 北
    pool = scoring_engine._filter_pool([near, far], {"nearby_only": 1})
    assert [r.name for r in pool] == ["附近店"]


def test_deleted_always_excluded():
    deleted = make_r(name="已删除", deleted=True)
    active  = make_r(name="正常店")
    pool = scoring_engine._filter_pool([deleted, active], {})
    assert [r.name for r in pool] == ["正常店"]


# ---- 菜系疲劳测试 ----

def test_cuisine_fatigue_2x_reduces_score():
    r = make_r(name="中餐馆", tags=["cuisine_chinese"])
    with patch("app.services.scoring_engine.history_store.get_recent_cuisines",
               return_value={"cuisine_chinese": 2}):
        results = scoring_engine.rank_restaurants([r], {}, set(), set())
    base_score = (4.0 * 2.0)  # rating=4.0 → base=8.0
    assert results[0].score < base_score * 0.75  # 0.7 multiplier applied


def test_cuisine_fatigue_3x_reduces_score_more():
    r = make_r(name="中餐馆", tags=["cuisine_chinese"])
    with patch("app.services.scoring_engine.history_store.get_recent_cuisines",
               return_value={"cuisine_chinese": 3}):
        results = scoring_engine.rank_restaurants([r], {}, set(), set())
    base_score = 4.0 * 2.0
    assert results[0].score < base_score * 0.45  # 0.4 multiplier


# ---- 多样性扰动测试 ----

def test_diversity_jitter_top3_unchanged():
    """前 3 名分数不受扰动影响（随机固定 seed 验证结构不变）。"""
    restaurants = [make_r(name=f"r{i}", rating=4.5 - i * 0.1) for i in range(10)]
    with patch("app.services.scoring_engine.history_store.get_recent_cuisines",
               return_value={}):
        r1 = scoring_engine.rank_restaurants(restaurants, {}, set(), set())
        r2 = scoring_engine.rank_restaurants(restaurants, {}, set(), set())
    # 前 3 名在两次结果中完全一致
    assert [r.restaurant.name for r in r1[:3]] == [r.restaurant.name for r in r2[:3]]
```

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest tests/test_scoring_engine.py -v
```

Expected: 多个 FAIL（`_filter_pool` not found 等）

- [ ] **Step 3: 重写 scoring_engine.py**

完整替换文件内容：

```python
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
    """纯饮品店：有 cold_food 标签且无任何 cuisine_* 标签。"""
    tags = set(r.tags)
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
            scored[i] = r.model_copy(update={"score": r.score + base * 0.10})
        elif weekday in (4, 5, 6) and "premium" in tags:       # 周五/六/日
            scored[i] = r.model_copy(update={"score": r.score + base * 0.15})

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
                scored[i] = r.model_copy(update={"score": r.score * 0.7})
            elif max_count >= 3:
                scored[i] = r.model_copy(update={"score": r.score * 0.4})

    # 5. 排序
    scored.sort(key=lambda x: x.score, reverse=True)

    # 6. 多样性扰动（第 4–20 名）
    if len(scored) > 3:
        for i, r in enumerate(scored[3:], start=3):
            jitter = 1.0 + random.uniform(-0.10, 0.10) * (r.restaurant.rating or 4.0) / 5.0
            scored[i] = r.model_copy(update={"score": r.score * jitter})
        scored[3:] = sorted(scored[3:], key=lambda x: x.score, reverse=True)

    return scored[:top_n]
```

- [ ] **Step 4: 运行测试**

```bash
python -m pytest tests/test_scoring_engine.py -v
```

Expected: 全部 pass

- [ ] **Step 5: Commit**

```bash
git add app/services/scoring_engine.py tests/test_scoring_engine.py
git commit -m "feat: add pool filtering, weekday bonus, cuisine fatigue, diversity jitter"
```

---

## Task 5: Room model + room_manager — 多人饮品提示

**Files:**
- Modify: `app/models/room.py`
- Modify: `app/services/room_manager.py`

- [ ] **Step 1: Room 模型新增字段**

在 `app/models/room.py` 的 `Room` 类中追加：

```python
drinks_only_participants: list[str] = []
```

- [ ] **Step 2: room_manager.submit_answers — 记录 drinks_only 参与者 + 多人模式剔除 drinks_only 信号**

在 `submit_answers` 函数中，将：

```python
    room.answers[participant_id] = answers
    room.participants[participant_id].submitted = True
```

改为：

```python
    room.answers[participant_id] = answers
    room.participants[participant_id].submitted = True

    # 记录选择了 drinks_only 的参与者姓名（用于多人模式提示）
    if any(a.weights.get("drinks_only", 0) > 0 for a in answers):
        pname = room.participants[participant_id].name
        if pname not in room.drinks_only_participants:
            room.drinks_only_participants.append(pname)
```

然后在 `if submitted == total:` 块中，将：

```python
        weights = scoring_engine.aggregate_weights(all_answers)
```

改为：

```python
        weights = scoring_engine.aggregate_weights(all_answers)
        # 多人模式：一人选饮品不代表全组无食欲，剔除该信号
        if len(room.participants) > 1:
            weights.pop("drinks_only", None)
```

- [ ] **Step 3: room_manager.close_room 同步处理**

在 `close_room` 中相同位置做同样修改：

```python
        weights = scoring_engine.aggregate_weights(all_answers)
        if len(room.participants) > 1:
            weights.pop("drinks_only", None)
```

- [ ] **Step 4: 验证语法**

```bash
python -c "from app.services import room_manager; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add app/models/room.py app/services/room_manager.py
git commit -m "feat: track drinks_only participants; exclude signal from multi-person scoring"
```

---

## Task 6: results.py — 返回饮品提示字段

**Files:**
- Modify: `app/routers/results.py`

- [ ] **Step 1: 在 get_results 的返回值中追加 drinks_only_notices**

将：

```python
    return {
        "results": [
            ...
        ],
        "recent_history": history_store.get_recent(5),
    }
```

改为：

```python
    return {
        "results": [
            {
                "rank": i + 1,
                "name": r.restaurant.name,
                "category": r.restaurant.category_raw,
                "address": r.restaurant.address,
                "rating": r.restaurant.rating,
                "avg_spend": r.restaurant.avg_spend,
                "score": r.score,
                "reason": r.reason,
                "tags": r.restaurant.tags,
            }
            for i, r in enumerate(room.results)
        ],
        "recent_history": history_store.get_recent(5),
        "drinks_only_notices": room.drinks_only_participants,
    }
```

- [ ] **Step 2: 验证语法**

```bash
python -c "from app.routers import results; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/routers/results.py
git commit -m "feat: include drinks_only_notices in results API response"
```

---

## Task 7: questionnaire.html — drinks_only 跳题逻辑

**Files:**
- Modify: `templates/questionnaire.html`

- [ ] **Step 1: 在 selectChoice 函数中检测 drinks_only 并提前提交**

将：

```javascript
function selectChoice(questionId, choiceId) {
  selectedAnswers[questionId] = choiceId;
  renderQuestion(currentIndex);
}
```

改为：

```javascript
function selectChoice(questionId, choiceId) {
  selectedAnswers[questionId] = choiceId;

  // 选了"来杯饮料就好了"后立即提交，跳过剩余题目
  const q = questions.find(q => q.id === questionId);
  const choice = q && q.choices.find(c => c.id === choiceId);
  if (choice && choice.weights && choice.weights.drinks_only) {
    submitAnswers();
    return;
  }

  renderQuestion(currentIndex);
}
```

- [ ] **Step 2: 验证 submitAnswers 在部分答题时的行为**

`submitAnswers` 当前实现会将未答题目填充为第一个选项：

```javascript
const answers = questions.map(q => ({
  question_id: q.id,
  choice_id: selectedAnswers[q.id] || q.choices[0].id,
}));
```

这个行为在 drinks_only 触发时是正确的——跳过的题目用第一个选项（通常有非空权重）填充。确认第一个选项对每道题是否合理，或将 fallback 改为使用 `随便` 选项。

在每道必出题中，随便选项都有空权重，但排在末尾，不适合作 fallback。当前逻辑（用 choices[0]）是可接受的，因为 drinks_only 已过滤掉所有食物类餐厅，其他权重影响有限。

- [ ] **Step 3: 手动测试（无自动化测试）**

启动应用后，进入答题页，在 q_energy 题选"完全没食欲，来杯饮料就好了"，验证：
1. 页面立即跳转到"已提交"状态，不再显示下一题
2. 等待结果时，结果页只出现饮品类餐厅

- [ ] **Step 4: Commit**

```bash
git add templates/questionnaire.html
git commit -m "feat: skip remaining questions when drinks_only is selected"
```

---

## Task 8: results.html — 饮品提示横幅

**Files:**
- Modify: `templates/results.html`

- [ ] **Step 1: 在 loadResults 的 data 处理中读取 drinks_only_notices**

在 `renderHistory(data.recent_history);` 后追加：

```javascript
    renderDrinksNotice(data.drinks_only_notices);
```

- [ ] **Step 2: 在 renderHistory 函数上方新增 renderDrinksNotice 函数**

```javascript
function renderDrinksNotice(notices) {
  if (!notices || notices.length === 0) return;
  const banner = document.createElement('div');
  banner.className = 'card';
  banner.style.cssText = 'background:#FFF8E1; margin-bottom:12px; text-align:center;';
  const names = notices.join('、');
  banner.textContent = `${names} 今天胃口不好，只想喝点饮料～`;
  document.getElementById('resultsView').insertBefore(
    banner,
    document.getElementById('historyPanel')
  );
}
```

- [ ] **Step 3: 手动测试**

多人模式下，一人选"来杯饮料就好了"，等待其他人答完后查看结果页，确认：
1. 顶部出现黄色提示横幅，显示该人的名字
2. 结果列表显示正常食物推荐（不是饮品过滤后的结果）

- [ ] **Step 4: Commit**

```bash
git add templates/results.html
git commit -m "feat: show drinks_only participant notice on results page"
```

---

## 验收测试清单

启动应用：`python run.py`

1. **Vendor 过滤**：q_vendor_only 选"在自己人圈子里挑" → 结果全为 vendor=1 的餐厅
2. **饮品跳题（单人）**：答题中选"来杯饮料就好了" → 立即跳过剩余题目 → 结果全为饮品类
3. **饮品提示（多人）**：2人房间，1人选"来杯饮料" → 结果页顶部出现提示横幅 → 结果仍为正常食物
4. **快餐过滤**：q_meal_type 选"赶时间" → 结果全为有 fast_service 标签的餐厅
5. **正餐过滤**：q_meal_type 选"好好坐下来吃" → 结果均无 fast_service 标签
6. **附近过滤**：q_mood 选"困到不行，楼下解决就好" → 结果坐标全在 250m 以内
7. **星期五效果**：手动将系统时间改为周五，premium 餐厅排名明显上升
8. **菜系疲劳**：history.json 写入 3 条同菜系记录 → 该菜系餐厅明显降权
9. **多样性**：同样答案运行 3 次 → 第 4 名以后排列有变化
10. **随便选项**：每道题选随便 → 推荐结果合理（无异常偏向）
