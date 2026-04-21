from __future__ import annotations
import json
from datetime import date, timedelta, datetime
from pathlib import Path

from app import config


_memory_records: list[dict] = []


def _read() -> list[dict]:
    if config.HISTORY_FILE.exists():
        try:
            with open(config.HISTORY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("records", [])
        except Exception:
            pass
    return list(_memory_records)


def _write(records: list[dict]) -> None:
    global _memory_records
    _memory_records = list(records)
    try:
        config.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(config.HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"records": records}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 云端只读文件系统，内存已保存


def get_recent(n: int = 10) -> list[dict]:
    records = _read()
    return sorted(records, key=lambda r: r["date"], reverse=True)[:n]


def add_record(restaurant_name: str, room_id: str = "", notes: str = "") -> None:
    records = _read()
    today_str = date.today().isoformat()
    # 同一天如果已有记录则更新
    records = [r for r in records if r.get("date") != today_str]
    records.append({
        "date": today_str,
        "restaurant_name": restaurant_name,
        "room_id": room_id,
        "notes": notes,
    })
    _write(records)


def get_recent_names(days: int = 2) -> tuple[set[str], set[str]]:
    """返回 (昨天的餐厅名集合, 前天的餐厅名集合)。"""
    records = _read()
    today = date.today()
    yesterday_str = (today - timedelta(days=1)).isoformat()
    two_days_str = (today - timedelta(days=2)).isoformat()

    yesterday_names: set[str] = set()
    two_days_names: set[str] = set()

    for r in records:
        if r.get("date") == yesterday_str:
            yesterday_names.add(r["restaurant_name"])
        elif r.get("date") == two_days_str:
            two_days_names.add(r["restaurant_name"])

    return yesterday_names, two_days_names
