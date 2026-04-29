# 今天吃什么 — 推荐算法升级设计文档

**日期：** 2026-04-27
**范围：** 推荐算法升级——vendor 过滤、饮品逻辑、动态因子、用餐类型、多样性优化

---

## 一、背景与目标

当前评分引擎基于题目权重 x 标签匹配打分，结果相对固定，缺乏动态感知。本次升级目标：

1. 支持 SAP 合作商家（vendor=1）筛选
2. 饮品类只在用户明确表达无食欲时出现
3. 引入天气、心情、星期几、菜系疲劳等动态信号
4. 区分正餐/快餐偏好
5. 提升结果多样性，避免总推同几家
6. 所有题目语气可爱，每题必有「随便」选项

---

## 二、题库变更

### 原则
- 语气轻松可爱，不严肃
- **每一道题必须包含「随便/不知道/无所谓」选项**，对应空权重 `{}`
- 新增趣味题进入随机池，新增实用题每次必出

---

### 2.1 新增实用题（每次必出）

#### q_vendor_only（置顶第一题）

```json
{
  "id": "q_vendor_only",
  "type": "real",
  "text": "今天想在 SAP 认证餐厅里选吗？",
  "choices": [
    {
      "text": "对，就在自己人圈子里挑～",
      "weights": { "vendor_only": 1 }
    },
    {
      "text": "不限，我有钱～",
      "weights": {}
    },
    {
      "text": "不知道，随便你",
      "weights": {}
    }
  ]
}
```

#### q_meal_type（新增必出实用题）

```json
{
  "id": "q_meal_type",
  "type": "real",
  "text": "今天吃饭时间宽裕吗？",
  "choices": [
    {
      "text": "赶时间！要快要快！",
      "weights": { "fast_service": 2.0, "meal_fast": 1 }
    },
    {
      "text": "时间够，想好好坐下来吃",
      "weights": { "meal_proper": 1 }
    },
    {
      "text": "吃饱就行，随便",
      "weights": {}
    }
  ]
}
```

---

### 2.2 新增趣味题（进入随机池）

#### q_weather

```json
{
  "id": "q_weather",
  "type": "fun",
  "text": "窗外天气怎么样？",
  "choices": [
    {
      "text": "下雨了，湿冷湿冷的",
      "weights": { "warm_food": 1.5, "soup_ok": 1.5 }
    },
    {
      "text": "阳光正好，温度舒服",
      "weights": {}
    },
    {
      "text": "好热好闷，快入夏啦",
      "weights": { "cold_food": 1.2, "spicy": -0.5 }
    },
    {
      "text": "风有点大，有点凉",
      "weights": { "warm_food": 1.0, "soup_ok": 1.0 }
    },
    {
      "text": "我在工位看不到窗户，随便",
      "weights": {}
    }
  ]
}
```

#### q_mood

```json
{
  "id": "q_mood",
  "type": "fun",
  "text": "今天的你是哪种状态？",
  "choices": [
    {
      "text": "累了累了，给我来点热乎的",
      "weights": { "filling": 1.2, "warm_food": 1.0 }
    },
    {
      "text": "今天心情超好，想犒劳自己！",
      "weights": { "premium": 1.3 }
    },
    {
      "text": "身体有点不对劲，吃点清淡的",
      "weights": { "healthy": 1.5, "spicy": -1.0 }
    },
    {
      "text": "困到不行，楼下解决就好",
      "weights": { "nearby_only": 1 }
    },
    {
      "text": "还行还行，随便吃点",
      "weights": {}
    }
  ]
}
```

---

### 2.3 现有题扩展

#### q_energy 新增选项

在现有 `q_energy` 题末尾（随便选项之前）插入：

```json
{
  "text": "完全没食欲，来杯饮料就好了",
  "weights": { "drinks_only": 1 }
}
```

#### 饮品选项的跳题逻辑

选择"来杯饮料"后，前端**立即提交当前已收集的权重，跳过剩余所有题目**，直接进入评分并跳转到结果页。

实现方式：在前端答题逻辑中，每次选择后检查是否有 `drinks_only` 信号——若存在，则触发与"全部答完"相同的提交流程，不再渲染后续题目。后端接口无需感知，对部分答题提交的处理与正常提交一致。

#### 现有题「随便」选项审查

检查所有实用题和趣味题，确保每题都有随便选项，格式统一：

```json
{ "text": "随便，都行", "weights": {} }
```

需检查并补充的题目：`q_spicy`、`q_distance`、`q_health`、`q_soup`、全部趣味题。

---

## 三、评分引擎变更

### 3.1 推荐池过滤（打分前执行，优先级从高到低）

| 触发条件 | 过滤逻辑 |
|---------|---------|
| `vendor_only > 0` | 仅保留 `vendor == 1` 的餐厅 |
| `drinks_only > 0` | 仅保留饮品类（`cold_food` 且无 `cuisine_*` 标签） |
| 默认（无 drinks_only）| 排除纯饮品类（`cold_food` 且无 `cuisine_*` 标签） |
| `meal_fast > 0` | 仅保留有 `fast_service` 标签的餐厅 |
| `meal_proper > 0` | 排除有 `fast_service` 标签的餐厅 |
| `nearby_only > 0` | 仅保留距长泰广场D座（121.603071, 31.206835）250m 以内的餐厅 |

多个过滤条件取交集（AND 逻辑）。

### 3.2 动态权重信号（打分时叠加）

#### 自动信号（无需用户输入）

**星期几加成**，在 `rank_restaurants` 入口处根据 `datetime.now().weekday()` 计算：

| 星期 | 逻辑 |
|------|------|
| 周一（0） | `budget_friendly` 标签餐厅基础分 x 1.10 |
| 周五（4）/ 周六（5）/ 周日（6） | `premium` 标签餐厅基础分 x 1.15 |
| 其他 | 不调整 |

**菜系疲劳**，读取 `history.json` 近 3 条记录，统计 `cuisine_*` 标签出现次数：

| 近 3 次出现次数 | 该菜系餐厅基础分乘数 |
|--------------|-------------------|
| 2 次 | x 0.7 |
| 3 次 | x 0.4 |
| 0-1 次 | x 1.0（不调整）|

#### 问卷信号（权重合并后处理）

`q_weather` 和 `q_mood` 产生的权重通过现有 `aggregate_weights` 机制合并，进入现有标签匹配流程，无需特殊处理。

`nearby_only`、`vendor_only`、`drinks_only`、`meal_fast`、`meal_proper` 为**控制信号**，不参与标签打分，仅用于过滤。

### 3.3 品牌去重

同品牌多门店在数据层处理：`restaurants.json` 中每个品牌只保留距长泰广场D座最近的门店，其余已删除。输出逻辑无需处理此问题。

### 3.4 多样性优化

在得到排序结果后，对**第 4 名至第 20 名**施加轻微随机扰动：

```python
import random
for i, r in enumerate(scored[3:], start=3):
    jitter = 1.0 + random.uniform(-0.10, 0.10) * (r.restaurant.rating or 4.0) / 5.0
    scored[i] = r.model_copy(update={"score": r.score * jitter})
# 重新排序第 4-20 名，前 3 名不动
scored[3:] = sorted(scored[3:], key=lambda x: x.score, reverse=True)
```

前 3 名锁定，保证结果质量下限；第 4 名以后每次有小幅变化。

---

## 四、数据变更

### 4.1 办公室坐标常量

在 `app/config.py` 新增：

```python
OFFICE_LNG: float = 121.603071   # 长泰广场D座
OFFICE_LAT: float = 31.206835
NEARBY_RADIUS_M: int = 250
```

### 4.2 fast_service 标签补充

`fast_service` 标签标记柜台式/快出品餐厅，不区分菜系。需全面覆盖所有快餐式服务的餐厅，包括但不限于：
- 赛百味 SUBWAY(上海浦东软件园店)
- 麦当劳(长泰广场店)（如存在）
- 肯德基相关门店（如存在）
- 重庆小面、陈香贵、老碗会、嘻小北、喜家德等柜台面食类
- 巴黎贝甜、果之满满等快取轻食类
- 秦小乖、兢杰冰室等快出品小吃类

具体哪些餐厅需要打标由人工确认后在 `restaurants.json` 中批量更新。

---

## 五、修改文件清单

| 文件 | 变更内容 |
|------|---------|
| `app/questions/bank.json` | 新增 `q_vendor_only`、`q_meal_type`、`q_weather`、`q_mood`；`q_energy` 新增饮品选项；现有题补充随便选项 |
| `app/config.py` | 新增 `OFFICE_LNG`、`OFFICE_LAT`、`NEARBY_RADIUS_M` 常量；`REAL_QUESTIONS_COUNT` 从 6 更新为 8 |
| `app/services/scoring_engine.py` | 新增推荐池过滤逻辑；新增星期几/菜系疲劳自动信号；新增多样性扰动 |
| `app/services/history_store.py` | 新增 `get_recent_cuisines(n)` 方法，返回近 n 条记录的菜系标签统计 |
| `data/restaurants.json` | 补充快餐类 `fast_service` 标签 |
| 答题前端模板（`quiz.html` 或对应 JS） | 检测 `drinks_only` 信号时跳过剩余题目，直接提交 |

---

## 六、测试重点

1. **Vendor 过滤**：选"只看合作商家"→ 结果全部为 vendor=1 的餐厅
2. **饮品逻辑**：默认发起投票 → 结果中无纯饮品店；选"来杯饮料" → 立即跳过剩余题目直接出结果，且结果全为饮品
3. **快餐过滤**：选"赶时间"→ 无火锅/日料/正餐类；选"坐下来吃"→ 无快餐类
4. **距离过滤**：选"困到不行，楼下解决" → 所有结果坐标在 250m 内
5. **星期五效果**：周五运行 → premium 餐厅排名明显高于周一
6. **菜系疲劳**：手动在 history.json 写入 3 条同菜系记录 → 该菜系明显降权
7. **多样性**：同样答题内容运行 3 次 → 第 4 名以后排列有变化
8. **随便选项**：每道题选随便 → 权重为空，不影响推荐结果
9. **品牌去重**：结果页不出现同品牌多门店（已在数据层保证，回归测试确认无重复品牌）
