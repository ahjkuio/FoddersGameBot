"""Простейший пул бесплатных HTTP(S)-прокси.

• _PROXY_POOL – вручную подобранные IP:port, желательно живые.
• get_proxy(region) -> str | None – возвращает URL прокси для указанного региона.
• ban_proxy(url, timeout=600) – помечает прокси как «нерабочий» на *timeout* секунд.

Реализация максимально лёгкая, без сторонних зависимостей; при желании
список можно редактировать вручную или обновлять скриптом.
"""
from __future__ import annotations

import random
import time
from typing import Dict, List

# --- Сырой список. Можно дополнять в runtime.
# Формат: {REGION: ["http://ip:port", ...]}
_PROXY_POOL: Dict[str, List[str]] = {
    "TR": [
        "http://188.132.221.44:8080",
        "http://45.10.208.86:8080",
    ],
    "BR": [
        "http://191.252.103.131:8080",
        "http://170.83.242.250:999",
    ],
    "AR": [
        "http://190.104.2.190:1080",
        "http://45.235.46.90:8080",
    ],
    "PL": [
        "http://89.64.13.202:80",
    ],
    "KZ": [
        "http://89.218.5.106:8080",
    ],
}

# --- Временные блокировки плохих узлов ---
# proxy_url -> unblock_timestamp
_BAD_MAP: Dict[str, float] = {}
_BLOCK_SECS = 600  # 10 минут


def _now() -> float:
    return time.time()


def get_proxy(region: str) -> str | None:
    """Возвращает случайный прокси для региона или None, если нет/все забанены."""
    region = region.upper()
    pool = _PROXY_POOL.get(region)
    if not pool:
        return None

    random.shuffle(pool)
    now = _now()
    for url in pool:
        if _BAD_MAP.get(url, 0) < now:
            return url
    return None


def ban_proxy(url: str, timeout: int = _BLOCK_SECS) -> None:
    """Помечает прокси как нерабочий на *timeout* секунд."""
    _BAD_MAP[url] = _now() + timeout 