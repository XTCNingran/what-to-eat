# 修复计划：「今天吃什么」Bug Fix

## Context

首轮代码审查发现 8 处问题，用户要求全部修复。重点在历史记录（保存/删除），同时补齐趣味题功能、修正校验逻辑和 XSS 风险。

---

## 数据库 Schema 变更

`history` 表新增 `user_name` 列（text），用于按用户过滤历史记录。

---

## 修复清单（10 项）

---

### Fix 1 & 2 — history 记录：date 缺失 + 重复记录 + 自动记录 + 按用户保存
**文件**: `docs/results.html`

**问题**:
- `confirmChoice()` 插入时未写 `date` 字段
- 结果页刷新后可再次点击，同一房间产生多条重复记录
- 主持人未手动选择时，没有任何记录
- history 只记录一条，无法按用户过滤

**新逻辑**:

history 表每条记录增加 `user_name` 字段，每次确认结果时为**该房间每位参与者**各写一条记录（人人都有自己的历史）。

统一用 `upsertHistory(name)` 处理写入：
- 若该 `room_id` 已有记录 → **UPDATE** 所有该房间的记录（保留最新选择）
- 若无记录 → 查出该房间所有 participants，**每人 INSERT 一条**
- 结果页加载完成后（host 视图）**自动写入第一名**，主持人点选时再覆盖

```js
async function upsertHistory(name) {
  const date = new Date().toISOString().split('T')[0];

  const { data: existing } = await sb.from('history')
    .select('id').eq('room_id', ROOM_ID).limit(1);

  if (existing && existing.length > 0) {
    // 已有记录，更新整个房间的餐厅选择
    await sb.from('history')
      .update({ restaurant_name: name, date })
      .eq('room_id', ROOM_ID);
  } else {
    // 首次写入：为每位参与者插入一条
    const { data: participantsList } = await sb.from('participants')
      .select('name').eq('room_id', ROOM_ID);
    const rows = (participantsList || []).map(p => ({
      restaurant_name: name,
      room_id: ROOM_ID,
      date,
      user_name: p.name,
    }));
    if (rows.length > 0) {
      await sb.from('history').insert(rows);
    }
  }
}
```

调用时机：
1. `loadResults()` 完成、排名渲染后，若 `HOST_TOKEN` 存在，自动调用 `upsertHistory(results[0].name)`
2. `confirmChoice()` 改为调用 `upsertHistory(btn.dataset.name)`，完成后更新按钮文案

> **注意**：`upsertHistory()` 必须在 Fix 10a（删除 participants）之前执行，因为它需要读取 participants 列表。

---

### Fix 3 — 首页历史记录：按用户过滤 + 删除按钮
**文件**: `docs/index.html`

**问题**: 展示全局历史，无法删除。

#### 3a — 用户名持久化
创建/加入房间时，将名字同时写入 `localStorage`（现在只写 sessionStorage，关浏览器就丢失）：

- `createRoom()`：`localStorage.setItem('user_name', hostName)`
- `startSolo()`：`localStorage.setItem('user_name', '我')`

`join.html` 的 `joinRoom()` 同样加：`localStorage.setItem('user_name', name)`

#### 3b — loadHistory 改为按用户过滤
```js
async function loadHistory() {
  const userName = localStorage.getItem('user_name');
  if (!userName) return;

  const { data } = await sb.from('history')
    .select('id, restaurant_name, date')
    .eq('user_name', userName)
    .order('created_at', { ascending: false })
    .limit(5);

  if (data && data.length > 0) {
    document.getElementById('historyCard').style.display = 'block';
    const list = document.getElementById('historyList');
    data.forEach(r => {
      const item = document.createElement('div');
      item.className = 'history-item';
      item.style.cssText = 'display:flex; justify-content:space-between; align-items:center;';
      item.innerHTML = `
        <span><strong>${r.date}</strong> · ${r.restaurant_name}</span>
        <button data-id="${r.id}" style="background:none;border:none;color:#aaa;cursor:pointer;font-size:16px;">×</button>
      `;
      item.querySelector('button').onclick = () => deleteHistory(r.id);
      list.appendChild(item);
    });
  }
}
```

#### 3c — deleteHistory 函数
```js
async function deleteHistory(id) {
  await sb.from('history').delete().eq('id', id);
  document.getElementById('historyList').innerHTML = '';
  document.getElementById('historyCard').style.display = 'none';
  await loadHistory();
}
```

---

### Fix 4 — 房间码校验过松（`< 4` → `!== 6`）
**文件**: `docs/index.html:184`、`docs/join.html:49`

```js
// 原
if (code.length < 4) return;
// 改
if (code.length !== 6) return;
```

---

### Fix 5 — history 近期避雷逻辑：limit(7) → 按日期过滤
**文件**: `docs/results.html`

**问题**: 查询用 `.limit(7)` 取条数，业务语义是"最近 3 天"，两者可能不一致。

**修改**: 改为按 `date` 字段过滤（不按 user_name 过滤，评分参考整组的历史）：
```js
const recentCutoff = new Date();
recentCutoff.setDate(recentCutoff.getDate() - 3);
const cutoffStr = recentCutoff.toISOString().split('T')[0];

// Promise.all 里改为：
sb.from('history')
  .select('restaurant_name, date')
  .gte('date', cutoffStr)
  .order('created_at', { ascending: false }),
```

同时删除 `results.html` 中已定义但未使用的 `threeDaysAgo` 变量。

`yesterdayRows` 的单独查询保持不变（仍按 `date` 过滤昨天）。

---

### Fix 6 — manage.html XSS 风险
**文件**: `docs/manage.html`

在 `renderList` 函数顶部加转义工具函数：
```js
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
```

将 `renderList` 和 edit form 中所有 `r.name`、`r.address`、`r.tags` 的 innerHTML 插入全部改为 `esc(...)` 包裹。

---

### Fix 7 — answers 重复提交保护
**文件**: `docs/questionnaire.html`

`submitAnswers` 开头加检查：
```js
const { data: existingAnswers } = await sb.from('answers')
  .select('id').eq('participant_id', participantId).eq('room_id', ROOM_ID).limit(1);
if (existingAnswers && existingAnswers.length > 0) {
  document.getElementById('questionView').style.display = 'none';
  document.getElementById('confirmView').style.display = 'none';
  document.getElementById('submittedView').style.display = 'block';
  return;
}
```

---

### Fix 8 — fun_questions 混入问卷
**文件**: `docs/questionnaire.html`

在 `init()` 加载 bank.json 后，随机抽 2–3 道趣味题插入 `questions` 数组（第 0 题 `q_drinks_only` 始终在首位）：

```js
const funPool = [...(bank.fun_questions || [])].sort(() => Math.random() - 0.5);
const pickCount = 2 + Math.floor(Math.random() * 2);
const pickedFun = funPool.slice(0, pickCount);

const real = bank.real_questions;
const rest = [...real.slice(1)];
pickedFun.forEach(q => {
  const pos = 1 + Math.floor(Math.random() * rest.length);
  rest.splice(pos, 0, q);
});
questions = [real[0], ...rest];
```

`drinksQuestions` 流程（drinks_only 分支）保持不变。`results.html` 的 `choiceWeightMap` 已包含 fun_questions，无需修改。

---

### Fix 9 — 删除菜系疲劳扣分逻辑
**文件**: `docs/results.html`、`docs/js/scoring.js`

**results.html 删除**（cuisineCounts 计算 + 写入 weights）:
```js
const cuisineCounts = {};
const recentRestaurants = (restaurants || []).filter(r => recentNames.has(r.name));
recentRestaurants.forEach(r => {
  (r.tags || []).filter(t => t.startsWith('cuisine_')).forEach(t => {
    cuisineCounts[t] = (cuisineCounts[t] || 0) + 1;
  });
});
weights._cuisineCounts = cuisineCounts;
```

**scoring.js 删除**（菜系疲劳打折代码块 + 无用常量）:
```js
const FATIGUE_2X_MULTIPLIER = 0.7;   // 删除
const FATIGUE_3X_MULTIPLIER = 0.4;   // 删除

// 删除整个 cuisineCounts 判断块（约 200–211 行）
const cuisineCounts = weights._cuisineCounts || {};
if (Object.keys(cuisineCounts).length > 0) { ... }
```

---

### Fix 10 — 清理投票房间数据（即时 + 兜底）
**文件**: `docs/results.html`、`docs/index.html`

**背景**：`rooms`、`participants`、`answers` 三张表是投票会话的临时数据，投票结束后无任何用途，应当清理。`history` 表（吃饭记录）与本 Fix 无关，不做任何修改。

#### 10a — 即时清理（results.html）
`upsertHistory()` 成功后立即删除（需在 upsertHistory 写完、participants 已读取之后执行）：
```js
await sb.from('answers').delete().eq('room_id', ROOM_ID);
await sb.from('participants').delete().eq('room_id', ROOM_ID);
await sb.from('rooms').delete().eq('id', ROOM_ID);
```

#### 10b — 兜底清理（index.html）
首页加载时静默清理 3 天前仍残留的废弃房间：
```js
async function cleanupAbandonedRooms() {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 3);
  const { data: oldRooms } = await sb.from('rooms')
    .select('id').lt('created_at', cutoff.toISOString());
  if (!oldRooms || oldRooms.length === 0) return;
  const ids = oldRooms.map(r => r.id);
  await sb.from('answers').delete().in('room_id', ids);
  await sb.from('participants').delete().in('room_id', ids);
  await sb.from('rooms').delete().in('id', ids);
}

// 底部：
loadHistory();
cleanupAbandonedRooms();
```

---

## 文件改动清单

| 文件 | 涉及 Fix |
|---|---|
| `docs/results.html` | Fix 1&2, Fix 5, Fix 9, Fix 10a |
| `docs/index.html` | Fix 3, Fix 4, Fix 10b |
| `docs/join.html` | Fix 3a（localStorage）, Fix 4 |
| `docs/manage.html` | Fix 6 |
| `docs/questionnaire.html` | Fix 7, Fix 8 |
| `docs/js/scoring.js` | Fix 9 |

---

## 执行顺序依赖

```
Fix 1&2（写 date + user_name）
    ↓ 必须先于 Fix 10a（upsertHistory 需要读 participants）
Fix 10a（删除 participants/answers/rooms）
    ↓
Fix 5（按 date 过滤，依赖 date 字段已正确写入）
```

---

## 验证方式

1. **Fix 1&2 + Fix 3**: 以「小王」身份完成投票 → 不点确认直接回首页 → 首页显示自动记录的第一名且 date 正确 → 再进结果页点选其他餐厅 → 记录被覆盖而非新增 → 换名字「小李」重走流程 → 首页各自只看到自己的历史
2. **Fix 3c**: 点击 × 按钮 → 条目消失，无记录时卡片隐藏
3. **Fix 4**: 输入 4 位、5 位码 → 直接 return，不跳转
4. **Fix 5**: 确认 history 查询改为 date 过滤，`threeDaysAgo` 变量已移除
5. **Fix 6**: manage.html 中餐厅名含 `<script>` 不执行
6. **Fix 7**: 提交后回退重试 → 直接跳入已提交状态，不重复插入
7. **Fix 8**: 问卷中随机混有 2–3 道趣味题
8. **Fix 9**: scoring.js 菜系疲劳块已删除，results.html cuisineCounts 块已删除
9. **Fix 10**: 完成一轮投票后检查 Supabase → rooms/participants/answers 已删，history 保留；首页加载后废弃房间被清理
