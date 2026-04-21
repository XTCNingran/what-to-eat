# 今天吃什么 — 功能扩展设计文档

**日期：** 2026-04-21  
**范围：** 补齐缺失功能（单人模式、房间黑名单、结果自由选择）+ 扩展数据能力（餐厅 CRUD、自定义标签、重新爬取）+ 公网访问支持

---

## 一、数据层

### 餐厅数据格式

将现有 Excel 文件一次性转换为 `data/restaurants.json`，之后 Excel 不再使用。

```json
[
  {
    "name": "某某餐厅",
    "address": "长泰广场B1",
    "rating": 4.5,
    "avg_spend": 45,
    "tags": ["中餐", "辣", "快速"],
    "phone": "",
    "vendor": 0,
    "deleted": false
  }
]
```

字段说明：
- `tags`：菜系、口味、服务特征等标签数组，可由用户自定义
- `vendor`：0 = 普通餐厅，1 = 合作供应商/特定类型，默认 0，预留给后续业务逻辑
- `deleted`：软删除标记，`true` 时不参与任何结果计算，也不显示在餐厅列表中
- 爬虫转换时所有新餐厅默认 `vendor: 0`、`deleted: false`

### 写入安全

所有写入操作：先写 `restaurants.json.tmp` → 成功后原子替换为 `restaurants.json`，防止写入中途崩溃损坏文件。

### 重新爬取合并策略

爬虫产出新数据后，按餐厅名匹配：
- 已存在的餐厅：更新 `rating`、`avg_spend`、`address`、`phone`；保留用户修改过的 `tags`、`vendor`、`deleted`
- 新增的餐厅：直接追加，`vendor: 0`、`deleted: false`
- 爬虫中已消失的餐厅：保留原记录不删除（用户可手动软删除）

---

## 二、新功能

### 2.1 单人模式

主页新增"一个人也能吃饭 🙋"按钮。点击后：
1. 后端自动创建房间
2. 以固定名称"我"加入该房间
3. 直接跳转到答题页 `/q/{room_id}`

复用全部现有房间/答题/结果逻辑，无需新路由。

### 2.2 房间黑名单（每房间独立）

**创建房间流程变更：** 主页"创建房间"后，在等待页面顶部新增"排除餐厅"区域：
- 支持按名称搜索餐厅
- 可多选，选中后显示为标签
- 不强制要求填写，可跳过

**数据模型变更：**
```python
class Room:
    ...
    blacklist: list[str] = []   # 餐厅名列表
```

**评分引擎变更：** `rank_restaurants` 新增 `blacklist` 参数，打分前过滤掉名称在黑名单中的餐厅。

黑名单随房间存在于内存中，房间关闭后不再保留（与现有房间生命周期一致）。

### 2.3 结果页自由选择

**现有行为：** 只有第一名可点击，"确认"按钮只能确认第一名。

**新行为：**
- 所有结果条目均可点击，点击后高亮选中（绿色边框）
- "我们去这里"按钮显示当前选中餐厅名，默认预选第一名
- 点击其他条目会切换选中，按钮文案实时更新
- 确认逻辑不变，写入 history.json 的是实际选中项

### 2.4 餐厅管理页

**入口：** 主页底部新增"管理餐厅 ⚙️"折叠面板，点击展开。

**功能列表：**

| 功能 | 说明 |
|------|------|
| 搜索/筛选 | 按名称关键词、标签、vendor 状态筛选 |
| 编辑餐厅 | 点击任意条目，弹出编辑表单：名称、地址、标签、avg_spend、vendor |
| 软删除 | 编辑表单内可将餐厅标记为删除，不再参与推荐 |
| 新增餐厅 | 表单手动添加，字段同上，vendor 默认 0 |
| 刷新数据 | 触发爬虫重新爬取，完成后按合并策略更新 restaurants.json，页面自动刷新列表 |

所有写操作通过 `/api/restaurants` REST API 完成。

---

## 三、架构

### 新增文件

| 文件 | 职责 |
|------|------|
| `app/routers/restaurants.py` | 餐厅 CRUD REST API (`GET /api/restaurants`, `POST`, `PUT /{name}`, `DELETE /{name}`, `POST /api/restaurants/refresh`) |
| `app/services/restaurant_store.py` | 读写 `restaurants.json`，含原子写入；爬虫合并逻辑 |
| `templates/manage.html` 或内嵌 `index.html` | 管理页前端 |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `app/models/restaurant.py` | 新增 `vendor: int = 0`、`deleted: bool = False` 字段 |
| `app/services/data_loader.py` | 从 `restaurants.json` 读取，过滤 `deleted: true` |
| `app/services/scoring_engine.py` | `rank_restaurants` 新增 `blacklist: list[str]` 参数 |
| `app/models/room.py` | `Room` 新增 `blacklist: list[str] = []` 字段 |
| `app/services/room_manager.py` | `create_room` 接受可选 `blacklist` 参数；`close_room` 传入 blacklist 给评分引擎 |
| `app/routers/rooms.py` | 创建房间 API 接受 `blacklist` 字段 |
| `app/main.py` | 注册 `restaurants` 路由 |
| `templates/index.html` | 加"单人模式"按钮、"管理餐厅"折叠入口 |
| `templates/room.html` | 等待页加黑名单选择区域 |
| `templates/results.html` | 所有结果项可点击选中，按钮跟随更新 |
| `scraper/scrape_changtai_*.py` | 输出 JSON 格式，调用 restaurant_store 合并写入 |

### 数据流（创建房间）

```
POST /api/rooms  {blacklist: ["xx饭馆"]}
  → room_manager.create_room(blacklist)
  → Room(blacklist=["xx饭馆"])
  → 答题完成后 close_room
  → scoring_engine.rank_restaurants(..., blacklist=room.blacklist)
  → 结果不含黑名单餐厅
```

---

## 四、错误处理

- `restaurants.json` 不存在：启动时报错提示，明确告知需要先运行数据转换脚本
- `restaurants.json` 格式损坏：启动时报错，不静默失败
- 写入失败：API 返回 500，原文件保持不变（原子写入保证）
- 爬虫失败：`/api/restaurants/refresh` 返回错误信息，不覆盖现有数据

---

## 五、公网访问

当团队成员不在同一局域网时（如居家办公、跨楼层不同网段），需要通过公网地址访问。提供两个层次的支持：

### 5.1 快速临时方案：ngrok 一键穿透

在 `run.py` 中新增 `--tunnel` 启动参数：

```bash
python run.py --tunnel
```

启动后：
1. 正常启动 FastAPI 服务（本地 8000 端口）
2. 调用 `pyngrok` 库自动创建 ngrok 隧道
3. 获取公网 HTTPS 地址，用该地址生成 QR 码（替代局域网 IP）
4. 终端打印公网地址和 QR 码

依赖：`pyngrok` 加入 `requirements.txt`（可选依赖，不影响局域网模式）。  
限制：ngrok 免费版每次启动地址变化；连接数有上限（适合小团队偶尔使用）。

### 5.2 长期部署方案：配置外部 BASE_URL

在 `config.py` 新增 `BASE_URL` 配置项，支持通过环境变量覆盖：

```bash
BASE_URL=https://my-app.railway.app python run.py
```

QR 码生成逻辑统一使用 `config.BASE_URL`（默认回退到局域网 IP）。这样无论是 ngrok、Railway、Render 还是自有服务器，只需设置环境变量即可，代码无需修改。

### 变更文件

| 文件 | 变更内容 |
|------|---------|
| `app/config.py` | 新增 `BASE_URL` 环境变量配置，默认 `None`（自动检测局域网 IP）|
| `run.py` | 新增 `--tunnel` 参数；QR 码生成使用 `BASE_URL` |
| `requirements.txt` | 新增可选依赖 `pyngrok` |

---

## 六、测试重点

手动端到端测试为主，覆盖以下场景：

1. Excel → JSON 转换后，178 家餐厅全部加载成功
2. 单人模式：点击按钮 → 直接到答题页 → 看到结果
3. 黑名单：创建房间时排除 2 家店 → 结果页确认这 2 家不出现
4. 结果页：点击第 3 名 → 确认 → history.json 记录的是第 3 名
5. 管理页：新增餐厅 → 重启服务 → 新餐厅出现在结果中
6. 管理页：软删除一家 → 该店不再出现在结果和黑名单选择列表中
7. 管理页：修改标签 → 评分结果相应变化
8. 刷新数据：爬取后用户自定义的 vendor=1 标记被保留
9. `--tunnel` 模式：QR 码显示 ngrok 公网地址，手机扫码可访问
10. `BASE_URL` 环境变量：设置后 QR 码使用该地址
