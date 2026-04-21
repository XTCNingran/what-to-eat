# 今天吃什么 功能扩展 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐单人模式、房间黑名单、结果自由选择、餐厅 CRUD 管理、公网访问支持，并将数据源从 Excel 迁移至 JSON。

**Architecture:** 餐厅数据一次性从 Excel 转为 `data/restaurants.json`，通过新增的 `restaurant_store.py` 服务读写；所有新功能在现有 FastAPI 框架上新增路由和修改现有文件；公网访问通过 `--tunnel` 参数和 `BASE_URL` 环境变量支持。

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Jinja2, qrcode, openpyxl (仅转换用), pyngrok (可选)

---

## Task 1: 数据迁移 — Excel 转 JSON

**Files:**
- Create: `what-to-eat/scripts/migrate_excel_to_json.py`
- Modify: `what-to-eat/app/models/restaurant.py`
- Modify: `what-to-eat/app/config.py`

### 1.1 更新 Restaurant 模型，加入新字段

- [ ] **修改 `app/models/restaurant.py`**

将文件内容替换为：

```python
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
```

### 1.2 更新 config.py，指向 JSON 文件

- [ ] **修改 `app/config.py`**

```python
import os
import socket
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RESTAURANT_DIR = DATA_DIR / "restaurants"
RESTAURANT_JSON = DATA_DIR / "restaurants.json"
HISTORY_FILE = DATA_DIR / "history.json"
QUESTION_BANK = BASE_DIR / "app" / "questions" / "bank.json"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

PORT = 8000
ROOM_TTL_SECONDS = 3600
REAL_QUESTIONS_COUNT = 6
FUN_QUESTIONS_COUNT = 2

# 公网访问：通过环境变量覆盖，默认使用局域网 IP
BASE_URL: str | None = os.environ.get("BASE_URL")


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


LAN_IP: str = get_lan_ip()


def get_base_url() -> str:
    """返回对外可访问的 base URL（优先环境变量，其次局域网 IP）。"""
    if BASE_URL:
        return BASE_URL.rstrip("/")
    return f"http://{LAN_IP}:{PORT}"
```

### 1.3 编写迁移脚本

- [ ] **创建 `scripts/migrate_excel_to_json.py`**

```python
"""将 data/restaurants/ 下最新 xlsx 转换为 data/restaurants.json。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl
from app.config import RESTAURANT_DIR, RESTAURANT_JSON
from app.services.data_loader import CATEGORY_TAG_MAP, _parse_float, _parse_tags


def migrate():
    files = list(RESTAURANT_DIR.glob("*.xlsx"))
    if not files:
        print("ERROR: data/restaurants/ 下没有找到 xlsx 文件")
        sys.exit(1)

    xlsx_path = max(files, key=lambda p: p.stat().st_mtime)
    print(f"读取: {xlsx_path}")

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    headers = [str(h) if h is not None else "" for h in rows[0]]
    col = {h: i for i, h in enumerate(headers)}

    restaurants = []
    for row in rows[1:]:
        name = row[col.get("商户名称", 0)]
        if not name:
            continue
        cat_raw = str(row[col.get("细分类别", 1)] or "")
        restaurants.append({
            "name": str(name),
            "category_raw": cat_raw,
            "address": str(row[col.get("地址", 2)] or ""),
            "rating": _parse_float(row[col.get("评分", 3)]),
            "avg_spend": _parse_float(row[col.get("人均消费(元)", 4)]),
            "lng": _parse_float(row[col.get("经度", 5)]),
            "lat": _parse_float(row[col.get("纬度", 6)]),
            "district": str(row[col.get("区域", 7)] or ""),
            "poi_id": str(row[col.get("POI ID", 8)] or ""),
            "tags": _parse_tags(cat_raw),
            "phone": "",
            "vendor": 0,
            "deleted": False,
        })

    tmp = RESTAURANT_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(restaurants, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(RESTAURANT_JSON)
    print(f"完成：写入 {len(restaurants)} 家餐厅 → {RESTAURANT_JSON}")


if __name__ == "__main__":
    migrate()
```

- [ ] **运行迁移脚本**

```bash
cd "what-to-eat"
python scripts/migrate_excel_to_json.py
```

预期输出：`完成：写入 178 家餐厅 → .../data/restaurants.json`

---

## Task 2: restaurant_store 服务（JSON 读写）

**Files:**
- Create: `what-to-eat/app/services/restaurant_store.py`
- Modify: `what-to-eat/app/services/data_loader.py`

### 2.1 创建 restaurant_store.py

- [ ] **创建 `app/services/restaurant_store.py`**

```python
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
```

### 2.2 修改 data_loader.py，从 JSON 读取

- [ ] **修改 `app/services/data_loader.py`**

将整个文件替换为以下内容（保留 `CATEGORY_TAG_MAP` 和辅助函数，供迁移脚本使用）：

```python
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
    return list(dict.fromkeys(tags))


def get_restaurants(force_reload: bool = False) -> list[Restaurant]:
    if force_reload:
        restaurant_store.invalidate_cache()
    return restaurant_store.get_all()
```

- [ ] **验证服务启动正常**

```bash
cd "what-to-eat"
python -c "from app.services.data_loader import get_restaurants; rs = get_restaurants(); print(f'加载 {len(rs)} 家餐厅')"
```

预期输出：`加载 178 家餐厅`

---

## Task 3: 餐厅 CRUD API

**Files:**
- Create: `what-to-eat/app/routers/restaurants.py`
- Modify: `what-to-eat/app/main.py`

- [ ] **创建 `app/routers/restaurants.py`**

```python
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


@router.put("/{name}")
async def update_restaurant(name: str, body: RestaurantUpdate):
    all_restaurants = restaurant_store.get_all(include_deleted=True)
    target = next((r for r in all_restaurants if r.name == name), None)
    if target is None:
        raise HTTPException(status_code=404, detail="餐厅不存在")
    updated = target.model_copy(update=body.model_dump(exclude_unset=True))
    restaurant_store.upsert(updated)
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
```

- [ ] **修改 `app/main.py`，注册 restaurants 路由**

在 `from app.routers import rooms, questionnaire, results` 一行改为：

```python
from app.routers import rooms, questionnaire, results, restaurants
```

在 `app.include_router(results.router)` 后新增：

```python
app.include_router(restaurants.router)
```

- [ ] **验证 API 可访问**

启动服务后访问 `http://localhost:8000/docs`，确认 `/api/restaurants` 相关端点出现在文档中。

---

## Task 4: 评分引擎支持黑名单

**Files:**
- Modify: `what-to-eat/app/services/scoring_engine.py`
- Modify: `what-to-eat/app/models/room.py`
- Modify: `what-to-eat/app/services/room_manager.py`
- Modify: `what-to-eat/app/routers/rooms.py`

### 4.1 scoring_engine.py 加 blacklist 参数

- [ ] **修改 `app/services/scoring_engine.py`**，`rank_restaurants` 函数签名改为：

```python
def rank_restaurants(
    restaurants: list[Restaurant],
    weights: dict[str, float],
    recent_names: set[str],
    yesterday_names: set[str],
    top_n: int = 20,
    blacklist: list[str] | None = None,
) -> list[ScoredRestaurant]:
    """对全部餐厅打分，过滤黑名单和软删除后排序，返回前 top_n 名。"""
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
```

### 4.2 Room 模型加 blacklist 字段

- [ ] **修改 `app/models/room.py`**，在 `Room` 类中新增：

```python
blacklist: list[str] = []
```

完整 Room 类：

```python
class Room(BaseModel):
    id: str
    host_token: str
    state: RoomState = RoomState.WAITING
    participants: dict[str, Participant] = {}
    questions: list[Question] = []
    answers: dict[str, list[Answer]] = {}
    results: Optional[list[ScoredRestaurant]] = None
    aggregated_weights: Optional[dict[str, float]] = None
    blacklist: list[str] = []

    class Config:
        use_enum_values = True
```

### 4.3 room_manager.py 传入 blacklist

- [ ] **修改 `app/services/room_manager.py`**，`create_room` 函数改为接受 blacklist：

```python
def create_room(blacklist: list[str] | None = None) -> Room:
    room_id = _gen_room_id()
    host_token = str(uuid.uuid4())
    questions = _select_questions()
    room = Room(id=room_id, host_token=host_token, questions=questions, blacklist=blacklist or [])
    _rooms[room_id] = room
    _sse_queues[room_id] = []
    return room
```

- [ ] **修改 `close_room` 函数**，传入 blacklist 给 rank_restaurants（约第 137 行）：

```python
results = scoring_engine.rank_restaurants(
    restaurants, weights, two_days, yesterday,
    blacklist=room.blacklist
)
```

### 4.4 创建房间 API 接受 blacklist

- [ ] **修改 `app/routers/rooms.py`**，新增请求体模型并更新 `create_room` 端点：

在文件顶部已有的 import 后新增：

```python
class CreateRoomRequest(BaseModel):
    blacklist: list[str] = []
```

将 `create_room` 端点改为：

```python
@router.post("", response_model=CreateRoomResponse)
async def create_room(body: CreateRoomRequest = CreateRoomRequest()):
    room = room_manager.create_room(blacklist=body.blacklist)
    base = config.get_base_url()
    join_url = f"{base}/join/{room.id}"
    qr_url = f"/api/rooms/{room.id}/qr"
    return CreateRoomResponse(
        room_id=room.id,
        host_token=room.host_token,
        join_url=join_url,
        qr_url=qr_url,
    )
```

同时更新 QR 码生成端点，使用 `get_base_url()`：

```python
@router.get("/{room_id}/qr")
async def get_qr(room_id: str):
    try:
        import qrcode
    except ImportError:
        raise HTTPException(status_code=500, detail="qrcode 未安装")
    join_url = f"{config.get_base_url()}/join/{room_id}"
    qr = qrcode.make(join_url)
    from io import BytesIO
    buf = BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    from fastapi import Response
    return Response(content=buf.read(), media_type="image/png")
```

---

## Task 5: 单人模式

**Files:**
- Modify: `what-to-eat/templates/index.html`
- Modify: `what-to-eat/app/routers/questionnaire.py`

### 5.1 后端：单人快速加入端点

- [ ] **修改 `app/routers/questionnaire.py`**，新增端点：

在文件末尾追加：

```python
@router.post("/{room_id}/solo")
async def solo_join(room_id: str):
    """单人模式：自动以「我」加入房间并立即开始答题。"""
    room = room_manager.get_room(room_id)
    if room is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="房间不存在")
    p = room_manager.add_participant(room_id, "我")
    if p is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="无法加入房间")
    room_manager.start_questioning(room_id, room.host_token)
    return {"participant_id": p.id}
```

### 5.2 前端：主页加单人模式按钮

- [ ] **修改 `templates/index.html`**，在"创建房间"卡片内，`createBtn` 按钮后新增：

```html
<div style="margin-top: 10px;">
  <button class="btn btn-ghost" id="soloBtn" onclick="startSolo()">🙋 一个人也能吃饭</button>
</div>
```

在 `<script>` 中新增函数：

```javascript
async function startSolo() {
  const btn = document.getElementById('soloBtn');
  btn.disabled = true;
  btn.textContent = '准备中…';
  try {
    // 1. 创建房间
    const res = await fetch('/api/rooms', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({blacklist: []})
    });
    const data = await res.json();
    // 2. 自动加入并开始
    const soloRes = await fetch(`/api/rooms/${data.room_id}/solo`, {method: 'POST'});
    const soloData = await soloRes.json();
    sessionStorage.setItem('participant_id', soloData.participant_id);
    window.location.href = `/q/${data.room_id}`;
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '🙋 一个人也能吃饭';
    alert('启动失败，请重试');
  }
}
```

---

## Task 6: 结果页自由选择

**Files:**
- Modify: `what-to-eat/templates/results.html`

- [ ] **修改 `templates/results.html`**，将 `renderRanking` 函数中 `item.onclick` 和 `item.style.cursor` 的逻辑提取为所有条目通用：

将现有 `renderRanking` 函数中创建 `item` 的部分改为：

```javascript
function renderRanking(results) {
  const list = document.getElementById('rankList');
  list.innerHTML = '';
  results.forEach((r, i) => {
    if (i === 0) topRestaurant = r.name;

    const item = document.createElement('div');
    item.className = 'result-item' + (i === 0 ? ' top1' : '');
    item.style.cursor = 'pointer';
    item.dataset.name = r.name;

    const rankIcon = i < 3 ? RANK_ICONS[i] : `${i + 1}`;
    const ratingStars = r.rating ? '⭐'.repeat(Math.round(r.rating)) : '';
    const spend = r.avg_spend ? `¥${r.avg_spend}/人` : '';
    const tags = (r.tags || []).slice(0, 3).map(t => `<span class="tag">${t}</span>`).join('');

    item.innerHTML = `
      <div class="result-rank">${rankIcon}</div>
      <div class="result-info">
        <div class="result-name">${r.name}</div>
        <div class="result-meta">${ratingStars} ${spend} · ${r.address ? r.address.substring(0, 20) : ''}</div>
        <div>${tags}</div>
        <div class="result-reason">${r.reason}</div>
      </div>
    `;

    item.onclick = () => selectRestaurant(r.name, item);
    list.appendChild(item);
  });

  // 预设第一名
  if (topRestaurant) selectRestaurant(topRestaurant, list.firstChild);
}

function selectRestaurant(name, el) {
  // 清除所有高亮
  document.querySelectorAll('.result-item').forEach(i => i.style.border = '');
  // 高亮选中项
  if (el) el.style.border = '2px solid var(--green)';
  // 更新确认按钮
  const btn = document.getElementById('confirmBtn');
  btn.dataset.name = name;
  btn.textContent = `我们去：${name}！✓`;
}
```

---

## Task 7: 房间黑名单 UI

**Files:**
- Modify: `what-to-eat/templates/room.html`

- [ ] **修改 `templates/room.html`**，在"已加入 N 人"卡片之前新增黑名单选择区域：

在 `<div class="card">` （"已加入"那个）前插入：

```html
<div class="card" id="blacklistCard">
  <h2>🚫 本次排除餐厅（可选）</h2>
  <p class="subtitle" style="font-size:13px;">选中的餐厅不会出现在今天的结果里</p>
  <input type="text" id="blacklistSearch" placeholder="搜索餐厅名…"
         style="margin-bottom:10px;"
         oninput="filterBlacklist(this.value)">
  <div id="blacklistOptions" style="max-height:200px; overflow-y:auto;"></div>
  <div id="blacklistSelected" style="margin-top:10px; display:flex; flex-wrap:wrap; gap:6px;"></div>
</div>
```

在 `<script>` 中新增黑名单逻辑（在 `const ROOM_ID` 后）：

```javascript
let blacklist = [];
let allRestaurants = [];

async function loadRestaurants() {
  try {
    const res = await fetch('/api/restaurants');
    const data = await res.json();
    allRestaurants = data.restaurants.map(r => r.name);
    renderBlacklistOptions(allRestaurants);
  } catch(e) {}
}

function renderBlacklistOptions(names) {
  const container = document.getElementById('blacklistOptions');
  container.innerHTML = '';
  names.slice(0, 50).forEach(name => {
    const div = document.createElement('div');
    div.style.cssText = 'padding:6px 10px; cursor:pointer; border-radius:6px; font-size:14px;';
    div.textContent = name;
    if (blacklist.includes(name)) div.style.background = '#FFE0E0';
    div.onclick = () => toggleBlacklist(name);
    container.appendChild(div);
  });
}

function filterBlacklist(query) {
  const filtered = allRestaurants.filter(n => n.includes(query));
  renderBlacklistOptions(filtered);
}

function toggleBlacklist(name) {
  if (blacklist.includes(name)) {
    blacklist = blacklist.filter(n => n !== name);
  } else {
    blacklist.push(name);
  }
  renderBlacklistSelected();
  filterBlacklist(document.getElementById('blacklistSearch').value);
}

function renderBlacklistSelected() {
  const container = document.getElementById('blacklistSelected');
  container.innerHTML = '';
  blacklist.forEach(name => {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.style.background = '#FFE0E0';
    tag.textContent = `${name} ×`;
    tag.style.cursor = 'pointer';
    tag.onclick = () => toggleBlacklist(name);
    container.appendChild(tag);
  });
}

loadRestaurants();
```

将 `startQuestioning` 函数改为传入 blacklist（创建房间时已含 blacklist，这里是主持人在等待页面操作已有房间的情况，不适用；实际上黑名单应在创建房间时传入）。

> **注意：** 当前架构中黑名单在创建房间时传入。将 `index.html` 的 `createRoom()` 函数改为传入黑名单，流程变为：主页点"开始"→ 先弹出黑名单选择 → 再创建房间。

- [ ] **修改 `templates/index.html`**，将"发起今日投票"卡片改为两步流程：

```html
<div class="card">
  <h2>🎲 发起今日投票</h2>
  <p class="subtitle">创建一个投票间，分享给同事扫码参与</p>

  <!-- 步骤1：主按钮 -->
  <div id="step1">
    <button class="btn btn-primary" id="createBtn" onclick="showBlacklistStep()">开始！</button>
    <div style="margin-top: 10px;">
      <button class="btn btn-ghost" id="soloBtn" onclick="startSolo()">🙋 一个人也能吃饭</button>
    </div>
  </div>

  <!-- 步骤2：黑名单选择 -->
  <div id="step2" style="display:none;">
    <p style="font-size:13px; color:var(--muted); margin-bottom:8px;">🚫 排除今天不想去的餐厅（可跳过）</p>
    <input type="text" id="blSearch" placeholder="搜索餐厅…" oninput="filterBl(this.value)"
           style="margin-bottom:8px;">
    <div id="blOptions" style="max-height:160px; overflow-y:auto; border:1px solid #eee; border-radius:8px; padding:4px;"></div>
    <div id="blSelected" style="margin-top:8px; display:flex; flex-wrap:wrap; gap:4px;"></div>
    <div style="display:flex; gap:8px; margin-top:12px;">
      <button class="btn btn-ghost" style="width:auto; padding:12px 16px;" onclick="hideBlacklistStep()">← 返回</button>
      <button class="btn btn-primary" id="confirmCreateBtn" onclick="createRoom()">创建房间 🚀</button>
    </div>
  </div>
</div>
```

在 `<script>` 中替换整个脚本为：

```javascript
let blList = [];
let allRests = [];

async function showBlacklistStep() {
  document.getElementById('step1').style.display = 'none';
  document.getElementById('step2').style.display = 'block';
  if (allRests.length === 0) {
    try {
      const res = await fetch('/api/restaurants');
      const data = await res.json();
      allRests = data.restaurants.map(r => r.name);
    } catch(e) {}
  }
  renderBlOptions(allRests);
}

function hideBlacklistStep() {
  document.getElementById('step2').style.display = 'none';
  document.getElementById('step1').style.display = 'block';
}

function renderBlOptions(names) {
  const c = document.getElementById('blOptions');
  c.innerHTML = '';
  names.slice(0, 60).forEach(name => {
    const div = document.createElement('div');
    div.style.cssText = 'padding:5px 8px; cursor:pointer; border-radius:4px; font-size:13px;';
    div.textContent = name;
    if (blList.includes(name)) div.style.background = '#FFE0E0';
    div.onclick = () => { toggleBl(name); renderBlOptions(names); };
    c.appendChild(div);
  });
}

function filterBl(q) { renderBlOptions(allRests.filter(n => n.includes(q))); }

function toggleBl(name) {
  blList = blList.includes(name) ? blList.filter(n => n !== name) : [...blList, name];
  const c = document.getElementById('blSelected');
  c.innerHTML = '';
  blList.forEach(n => {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.style.cssText = 'background:#FFE0E0; cursor:pointer;';
    tag.textContent = n + ' ×';
    tag.onclick = () => { toggleBl(n); filterBl(document.getElementById('blSearch').value); };
    c.appendChild(tag);
  });
}

async function createRoom() {
  const btn = document.getElementById('confirmCreateBtn');
  btn.disabled = true;
  btn.textContent = '创建中…';
  try {
    const res = await fetch('/api/rooms', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({blacklist: blList})
    });
    const data = await res.json();
    window.location.href = `/room/${data.room_id}?token=${data.host_token}`;
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '创建房间 🚀';
    alert('创建失败，请重试');
  }
}

async function startSolo() {
  const btn = document.getElementById('soloBtn');
  btn.disabled = true;
  btn.textContent = '准备中…';
  try {
    const res = await fetch('/api/rooms', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({blacklist: []})
    });
    const data = await res.json();
    const soloRes = await fetch(`/api/rooms/${data.room_id}/solo`, {method: 'POST'});
    const soloData = await soloRes.json();
    sessionStorage.setItem('participant_id', soloData.participant_id);
    window.location.href = `/q/${data.room_id}`;
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '🙋 一个人也能吃饭';
    alert('启动失败，请重试');
  }
}

function joinByCode() {
  const code = document.getElementById('codeInput').value.trim().toUpperCase();
  if (code.length < 4) return;
  window.location.href = `/join/${code}`;
}
```

---

## Task 8: 餐厅管理页 UI

**Files:**
- Modify: `what-to-eat/templates/index.html`（在现有脚本底部追加管理页逻辑）
- Create: `what-to-eat/templates/manage.html`（新页面，主页底部链接过去）
- Modify: `what-to-eat/app/main.py`（新增管理页路由）

### 8.1 管理页后端路由

- [ ] **修改 `app/main.py`**，新增管理页路由（在 `results_page` 函数后追加）：

```python
@app.get("/manage", response_class=HTMLResponse)
async def manage_page(request: Request):
    return templates.TemplateResponse(request, "manage.html", {})
```

### 8.2 创建 manage.html

- [ ] **创建 `templates/manage.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>餐厅管理 · 今天吃什么</title>
  <link rel="stylesheet" href="/static/css/style.css">
  <style>
    .mgmt-row { display:flex; justify-content:space-between; align-items:center;
                padding:10px 12px; border-bottom:1px solid #F0F0F0; font-size:14px; }
    .mgmt-row:last-child { border-bottom:none; }
    .mgmt-row.deleted { opacity:0.4; }
    .mgmt-meta { font-size:12px; color:var(--muted); }
    .edit-form { background:#F9F9F9; border-radius:10px; padding:16px; margin-top:8px; }
    .edit-form label { display:block; font-size:12px; color:var(--muted); margin-top:10px; margin-bottom:4px; }
    .filter-bar { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
  </style>
</head>
<body>
<div class="container">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
    <a href="/" style="color:var(--muted); text-decoration:none; font-size:14px;">← 返回首页</a>
    <span style="font-size:13px; color:var(--muted)">餐厅管理</span>
  </div>

  <div class="card">
    <h2>🏪 餐厅列表 <span id="countBadge" style="font-size:14px; color:var(--muted);"></span></h2>
    <div class="filter-bar">
      <input type="text" id="searchInput" placeholder="搜索餐厅名…" oninput="applyFilters()"
             style="flex:1; min-width:120px;">
      <select id="vendorFilter" onchange="applyFilters()" style="width:auto; padding:10px;">
        <option value="">全部</option>
        <option value="0">普通餐厅</option>
        <option value="1">合作供应商</option>
      </select>
      <label style="display:flex; align-items:center; gap:4px; font-size:13px; cursor:pointer;">
        <input type="checkbox" id="showDeleted" onchange="applyFilters()"> 显示已删除
      </label>
    </div>
    <div id="restaurantList"></div>
  </div>

  <div class="card">
    <h2>➕ 新增餐厅</h2>
    <div class="edit-form">
      <label>餐厅名称 *</label>
      <input type="text" id="newName" placeholder="必填">
      <label>地址</label>
      <input type="text" id="newAddress" placeholder="">
      <label>标签（逗号分隔）</label>
      <input type="text" id="newTags" placeholder="如：中餐,快速,辣">
      <label>人均消费（元）</label>
      <input type="number" id="newSpend" placeholder="">
      <label>评分</label>
      <input type="number" id="newRating" step="0.1" min="0" max="5" placeholder="0-5">
      <label>类型</label>
      <select id="newVendor" style="width:100%; padding:10px; border-radius:8px; border:1px solid #E0E0E0;">
        <option value="0">普通餐厅</option>
        <option value="1">合作供应商</option>
      </select>
      <button class="btn btn-primary" style="margin-top:16px;" onclick="addRestaurant()">添加</button>
    </div>
  </div>

  <div class="card">
    <h2>🔄 刷新餐厅数据</h2>
    <p class="subtitle" style="font-size:13px;">重新爬取长泰广场餐厅信息，保留你的自定义标签和 vendor 设置</p>
    <button class="btn btn-secondary" id="refreshBtn" onclick="refreshData()">开始刷新</button>
    <p id="refreshResult" style="font-size:13px; margin-top:8px; color:var(--muted);"></p>
  </div>
</div>

<script>
let allRestaurants = [];

async function loadRestaurants() {
  const showDeleted = document.getElementById('showDeleted').checked;
  const res = await fetch(`/api/restaurants?include_deleted=${showDeleted}`);
  const data = await res.json();
  allRestaurants = data.restaurants;
  applyFilters();
}

function applyFilters() {
  const q = document.getElementById('searchInput').value.toLowerCase();
  const vendor = document.getElementById('vendorFilter').value;
  const showDeleted = document.getElementById('showDeleted').checked;

  let filtered = allRestaurants.filter(r => {
    if (!showDeleted && r.deleted) return false;
    if (q && !r.name.toLowerCase().includes(q)) return false;
    if (vendor !== '' && String(r.vendor) !== vendor) return false;
    return true;
  });

  document.getElementById('countBadge').textContent = `(${filtered.length})`;
  renderList(filtered);
}

function renderList(restaurants) {
  const list = document.getElementById('restaurantList');
  list.innerHTML = '';
  if (restaurants.length === 0) {
    list.innerHTML = '<p style="text-align:center; color:var(--muted); padding:20px;">没有找到餐厅</p>';
    return;
  }
  restaurants.forEach(r => {
    const row = document.createElement('div');
    row.className = 'mgmt-row' + (r.deleted ? ' deleted' : '');
    row.innerHTML = `
      <div>
        <div><strong>${r.name}</strong> ${r.vendor ? '<span class="tag" style="background:#E8F4FD;">供应商</span>' : ''} ${r.deleted ? '<span class="tag" style="background:#FFE0E0;">已删除</span>' : ''}</div>
        <div class="mgmt-meta">${r.address || ''} ${r.avg_spend ? '· ¥'+r.avg_spend : ''} ${r.rating ? '· ⭐'+r.rating : ''}</div>
        <div>${(r.tags||[]).slice(0,4).map(t=>`<span class="tag">${t}</span>`).join('')}</div>
      </div>
      <button class="btn btn-ghost" style="width:auto; padding:8px 14px; font-size:13px;"
              onclick="openEdit('${r.name.replace(/'/g, "\\'")}')">编辑</button>
    `;
    list.appendChild(row);

    // 编辑表单（隐藏）
    const form = document.createElement('div');
    form.id = `edit-${r.name}`;
    form.style.display = 'none';
    form.className = 'edit-form';
    form.innerHTML = `
      <label>标签（逗号分隔）</label>
      <input type="text" id="et-${r.name}" value="${(r.tags||[]).join(',')}">
      <label>地址</label>
      <input type="text" id="ea-${r.name}" value="${r.address||''}">
      <label>人均消费（元）</label>
      <input type="number" id="es-${r.name}" value="${r.avg_spend||''}">
      <label>评分</label>
      <input type="number" id="er-${r.name}" step="0.1" min="0" max="5" value="${r.rating||''}">
      <label>类型</label>
      <select id="ev-${r.name}" style="width:100%; padding:10px; border-radius:8px; border:1px solid #E0E0E0;">
        <option value="0" ${r.vendor===0?'selected':''}>普通餐厅</option>
        <option value="1" ${r.vendor===1?'selected':''}>合作供应商</option>
      </select>
      <div style="display:flex; gap:8px; margin-top:12px;">
        <button class="btn btn-primary" style="font-size:13px;" onclick="saveEdit('${r.name.replace(/'/g, "\\'")}')">保存</button>
        ${!r.deleted
          ? `<button class="btn btn-ghost" style="font-size:13px; color:#CC3333;" onclick="deleteRestaurant('${r.name.replace(/'/g, "\\'")}')">删除</button>`
          : `<button class="btn btn-ghost" style="font-size:13px;" onclick="restoreRestaurant('${r.name.replace(/'/g, "\\'")}')">恢复</button>`
        }
        <button class="btn btn-ghost" style="font-size:13px; width:auto; padding:10px 14px;" onclick="closeEdit('${r.name.replace(/'/g, "\\'")}')">取消</button>
      </div>
    `;
    list.appendChild(form);
  });
}

function openEdit(name) {
  document.querySelectorAll('.edit-form').forEach(f => f.style.display = 'none');
  const form = document.getElementById(`edit-${name}`);
  if (form) form.style.display = 'block';
}

function closeEdit(name) {
  const form = document.getElementById(`edit-${name}`);
  if (form) form.style.display = 'none';
}

async function saveEdit(name) {
  const tags = document.getElementById(`et-${name}`).value.split(',').map(t=>t.trim()).filter(Boolean);
  const address = document.getElementById(`ea-${name}`).value;
  const avg_spend = parseFloat(document.getElementById(`es-${name}`).value) || null;
  const rating = parseFloat(document.getElementById(`er-${name}`).value) || null;
  const vendor = parseInt(document.getElementById(`ev-${name}`).value);

  const res = await fetch(`/api/restaurants/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tags, address, avg_spend, rating, vendor})
  });
  if (res.ok) { await loadRestaurants(); }
  else { alert('保存失败'); }
}

async function deleteRestaurant(name) {
  if (!confirm(`确定删除「${name}」？（可以在"显示已删除"中恢复）`)) return;
  const res = await fetch(`/api/restaurants/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({deleted: true})
  });
  if (res.ok) { await loadRestaurants(); }
}

async function restoreRestaurant(name) {
  const res = await fetch(`/api/restaurants/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({deleted: false})
  });
  if (res.ok) { await loadRestaurants(); }
}

async function addRestaurant() {
  const name = document.getElementById('newName').value.trim();
  if (!name) { alert('餐厅名称不能为空'); return; }
  const tags = document.getElementById('newTags').value.split(',').map(t=>t.trim()).filter(Boolean);
  const body = {
    name,
    category_raw: '',
    address: document.getElementById('newAddress').value,
    rating: parseFloat(document.getElementById('newRating').value) || null,
    avg_spend: parseFloat(document.getElementById('newSpend').value) || null,
    tags,
    phone: '',
    vendor: parseInt(document.getElementById('newVendor').value),
    deleted: false,
    district: '',
    poi_id: '',
    lng: null,
    lat: null,
  };
  const res = await fetch('/api/restaurants', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  if (res.ok) {
    ['newName','newAddress','newTags','newSpend','newRating'].forEach(id => document.getElementById(id).value = '');
    await loadRestaurants();
  } else {
    const err = await res.json();
    alert(err.detail || '添加失败');
  }
}

async function refreshData() {
  const btn = document.getElementById('refreshBtn');
  const result = document.getElementById('refreshResult');
  btn.disabled = true;
  btn.textContent = '爬取中…';
  result.textContent = '正在重新爬取，请稍候（约1分钟）…';
  try {
    const res = await fetch('/api/restaurants/refresh', {method: 'POST'});
    const data = await res.json();
    result.textContent = data.message || '刷新完成';
    await loadRestaurants();
  } catch(e) {
    result.textContent = '刷新失败，请检查爬虫脚本';
  }
  btn.disabled = false;
  btn.textContent = '开始刷新';
}

loadRestaurants();
</script>
</body>
</html>
```

### 8.3 主页添加管理入口

- [ ] **修改 `templates/index.html`**，在"已有投票间？"卡片后、`</div>` 前追加：

```html
  <div style="text-align:center; margin-top:16px;">
    <a href="/manage" style="font-size:13px; color:var(--muted); text-decoration:none;">⚙️ 管理餐厅</a>
  </div>
```

---

## Task 9: 公网访问 — ngrok tunnel 支持

**Files:**
- Modify: `what-to-eat/run.py`
- Modify: `what-to-eat/requirements.txt`

- [ ] **修改 `requirements.txt`**，追加：

```
pyngrok>=7.0.0
```

- [ ] **修改 `run.py`**，支持 `--tunnel` 参数：

```python
import sys
import socket
import argparse
import uvicorn

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tunnel", action="store_true", help="通过 ngrok 创建公网隧道")
    args = parser.parse_args()

    port = 8000
    display_url = f"http://{get_lan_ip()}:{port}"

    if args.tunnel:
        try:
            from pyngrok import ngrok
            tunnel = ngrok.connect(port)
            public_url = tunnel.public_url
            import os
            os.environ["BASE_URL"] = public_url
            display_url = public_url
            print(f"\n  🌐 公网地址（ngrok）：{public_url}")
        except ImportError:
            print("  ⚠️  pyngrok 未安装，使用局域网模式 (pip install pyngrok)")
        except Exception as e:
            print(f"  ⚠️  ngrok 启动失败：{e}，使用局域网模式")

    print("\n" + "=" * 50)
    print(f"  今天吃什么 🍜")
    print(f"  访问地址：{display_url}")
    print("=" * 50)

    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(display_url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        print("  (安装 qrcode 可显示二维码: pip install qrcode[pil])")

    mode = "公网（ngrok）" if args.tunnel else "局域网"
    print(f"\n  模式：{mode}\n")

    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
```

> **说明：** `BASE_URL` 在 `run.py` 里设置为 `os.environ["BASE_URL"]`，而 `config.py` 在模块加载时读取此环境变量。由于 FastAPI 在 uvicorn 启动时才导入路由模块，`config.get_base_url()` 会在请求时调用，能正确取到 ngrok 地址。

---

## Task 10: 端到端测试

- [ ] **安装依赖**

```bash
cd "what-to-eat"
pip install -r requirements.txt
```

- [ ] **运行迁移（如 Task 1 未运行）**

```bash
python scripts/migrate_excel_to_json.py
```

预期：`完成：写入 178 家餐厅`

- [ ] **启动服务，验证局域网模式**

```bash
python run.py
```

访问 `http://localhost:8000`，确认页面正常显示。

- [ ] **测试单人模式**

点击"一个人也能吃饭"→ 直接进入答题页 → 完成所有题目 → 看到结果页。

- [ ] **测试黑名单**

点击"开始！"→ 在黑名单选择中搜索并选择 2 家餐厅 → 创建房间 → 完成投票 → 确认结果页中这 2 家不出现。

- [ ] **测试结果页自由选择**

在结果页点击第 3 名 → 确认按钮文案变为该餐厅 → 点击确认 → 查看 `data/history.json`，确认记录的是第 3 名。

- [ ] **测试餐厅管理页**

访问 `http://localhost:8000/manage` → 确认 178 家餐厅显示 → 编辑一家餐厅的标签 → 保存 → 重启服务 → 确认标签保留。

- [ ] **测试软删除**

管理页删除一家餐厅 → 勾选"显示已删除"确认该店显示为已删除 → 发起投票 → 确认该店不出现在结果中。

- [ ] **测试新增餐厅**

管理页新增一家餐厅（填写名称和标签）→ 发起投票 → 确认新餐厅出现在候选列表中。

- [ ] **测试 ngrok 模式（可选，需安装 pyngrok 和配置 ngrok authtoken）**

```bash
python run.py --tunnel
```

确认终端打印公网地址，手机扫码可访问。

- [ ] **测试 BASE_URL 环境变量**

```bash
BASE_URL=https://example.com python run.py
```

创建房间后查看 QR 码图片，确认链接域名为 `example.com`。
