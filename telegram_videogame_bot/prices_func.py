"""Утилиты конвертации валют (ITAD удалён)."""

from typing import List, Tuple, Dict, Any

import aiohttp
from cachetools import TTLCache

# ⚡️ Кэш курсов валют (12 ч)
_RATE_CACHE: TTLCache[str, float] = TTLCache(maxsize=128, ttl=12 * 60 * 60)

_EXCHANGE_API = "https://api.exchangerate.host/latest"

# Фиксированные курсы на случай, если API недоступен
# Курсы обновлены 05.07.2025. При первой удачной загрузке из API они будут перебиты.
_STATIC_RATES = {
    "USD": 91.0,
    "EUR": 99.0,
    "GBP": 115.0,
    "TRY": 2.8,
    "BRL": 18.5,
    "ARS": 0.08,
    "INR": 1.07,
    "UAH": 2.4,
    "KZT": 0.2,
    "PLN": 23.0,
}

# ------------------------------------------------
# Конвертация валюты в рубли
# ------------------------------------------------


async def _fetch_rate_to_rub(cur: str) -> float | None:
    """Получить курс <cur>→RUB. Кэшируется."""

    if cur == "RUB":
        return 1.0
    if cur in _RATE_CACHE:
        return _RATE_CACHE[cur]

    params = {"base": cur, "symbols": "RUB"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
        try:
            async with session.get(_EXCHANGE_API, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                rate = data.get("rates", {}).get("RUB")
                if rate:
                    _RATE_CACHE[cur] = rate
                    return rate
        except Exception:
            return None


async def convert_to_rub(amount: float, currency: str) -> float | None:
    """Переводит сумму в RUB (с округлением до 2 знаков)."""

    rate = await _fetch_rate_to_rub(currency)
    if rate:
        return round(amount * rate, 2)

    # Фолбэк на статический курс
    static = _STATIC_RATES.get(currency.upper())
    if static:
        return round(amount * static, 2)

    return None 