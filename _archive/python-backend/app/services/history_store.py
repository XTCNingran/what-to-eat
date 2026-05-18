from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path

from app import config

# 内存回退（文件系统只读时使用）
_memory_records: dict[str, list[dict]] = {}


def _read() -> dict[str, list[dict]]:
    if config.HISTORY_FILE.exists():
        try:
            data = json.loads(config.HISTORY_FILE.read_text(encoding="utf-8"))
            records = data.get("records", {})
            # 兼容旧格式（records 为 list）
            if isinstance(records, list):
                return {}
            return records
        except Exception:
            pass
    return dict(_memory_records)


def _write(records: dict[str, list[dict]]) -> None:
    global _memory_records
    _memory_records = dict(records)
    try:
        config.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.HISTORY_FILE.write_text(
            json.dumps({"records": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass  # 云端只读文件系统，内存已保存


def add_record(restaurant_name: str, username: str, room_id: str = "", notes: str = "") -> None:
    records = _read()
    today_str = date.today().isoformat()
    user_records = records.get(username, [])
    # 同一用户同一天已有记录则更新
    user_records = [r for r in user_records if r.get("date") != today_str]
    user_records.append({
        "date": today_str,
        "restaurant_name": restaurant_name,
        "room_id": room_id,
        "notes": notes,
    })
    records[username] = user_records
    _write(records)


def add_record_for_users(restaurant_name: str, usernames: list[str], room_id: str = "") -> None:
    """主持人确认餐厅后，为所有参与者批量写入历史记录。"""
    records = _read()
    today_str = date.today().isoformat()
    for username in usernames:
        user_records = records.get(username, [])
        user_records = [r for r in user_records if r.get("date") != today_str]
        user_records.append({
            "date": today_str,
            "restaurant_name": restaurant_name,
            "room_id": room_id,
            "notes": "",
        })
        records[username] = user_records
    _write(records)


def get_recent(n: int, username: str) -> list[dict]:
    records = _read()
    user_records = records.get(username, [])
    return sorted(user_records, key=lambda r: r["date"], reverse=True)[:n]


def get_recent_all(n: int) -> list[dict]:
    """全局最近 n 条记录，用于首页展示（按日期排序，去重）。"""
    records = _read()
    all_records: list[dict] = []
    for user_records in records.values():
        all_records.extend(user_records)
    seen_dates: set[str] = set()
    deduped: list[dict] = []
    for r in sorted(all_records, key=lambda r: r["date"], reverse=True):
        if r["date"] not in seen_dates:
            seen_dates.add(r["date"])
            deduped.append(r)
        if len(deduped) >= n:
            break
    return deduped


def get_recent_names(usernames: list[str], days: int = 2) -> tuple[set[str], set[str]]:
    """返回所有参与者的 (昨天的餐厅名并集, 前天的餐厅名并集)。"""
    records = _read()
    today = date.today()
    yesterday_str = (today - timedelta(days=1)).isoformat()
    two_days_str = (today - timedelta(days=2)).isoformat()

    yesterday_names: set[str] = set()
    two_days_names: set[str] = set()
    for username in usernames:
        for r in records.get(username, []):
            if r.get("date") == yesterday_str:
                yesterday_names.add(r["restaurant_name"])
            elif r.get("date") == two_days_str:
                two_days_names.add(r["restaurant_name"])
    return yesterday_names, two_days_names
