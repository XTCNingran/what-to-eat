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
