import json
from pathlib import Path
from unittest.mock import patch, MagicMock


def make_restaurant(name, tags):
    m = MagicMock()
    m.name = name
    m.tags = tags
    return m


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
