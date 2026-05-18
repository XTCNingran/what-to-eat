from __future__ import annotations
import json
from app import config

_cache: list[str] | None = None


def _read() -> list[str]:
    global _cache
    if _cache is not None:
        return _cache
    if config.USERS_FILE.exists():
        try:
            _cache = json.loads(config.USERS_FILE.read_text(encoding="utf-8"))
            return _cache
        except Exception:
            pass
    _cache = []
    return _cache


def _write(users: list[str]) -> None:
    global _cache
    _cache = list(users)
    try:
        config.USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.USERS_FILE.write_text(
            json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def get_all() -> list[str]:
    return list(_read())


def exists(username: str) -> bool:
    return username in _read()


def register(username: str) -> bool:
    """注册用户名，已存在返回 False，成功返回 True。"""
    users = _read()
    if username in users:
        return False
    users.append(username)
    _write(users)
    return True
