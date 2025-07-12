"""Утилиты конвертации валют (ITAD удалён)."""

from typing import List, Tuple, Dict, Any

import aiohttp
from cachetools import TTLCache

# ⚡️ Кэш курсов валют (12 ч)
_RATE_CACHE: TTLCache[Tuple[str, str], float] = TTLCache(maxsize=128, ttl=12 * 60 * 60)

_EXCHANGE_API = "https://api.exchangerate.host/latest"

# Фиксированные курсы на случай, если API недоступен
# Курсы обновлены 05.07.2025. При первой удачной загрузке из API они будут перебиты.
_STATIC_RATES_TO_RUB = {
    "USD": 91.0,
    "EUR": 99.0,
    "GBP": 115.0,
    "TRY": 2.0,
    "BRL": 17.0,
    "ARS": 0.08,
    "INR": 1.07,
    "UAH": 2.4,
    "KZT": 0.2,
    "PLN": 23.0,
}

# ------------------------------------------------
# Конвертация валют
# ------------------------------------------------


async def _fetch_rate(from_cur: str, to_cur: str) -> float | None:
    """Получить курс from_cur→to_cur. Кэшируется."""
    if from_cur.upper() == to_cur.upper():
        return 1.0
    
    cache_key = (from_cur.upper(), to_cur.upper())
    if cache_key in _RATE_CACHE:
        return _RATE_CACHE[cache_key]

    params = {"base": from_cur, "symbols": to_cur}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
        try:
            async with session.get(_EXCHANGE_API, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                rate = data.get("rates", {}).get(to_cur.upper())
                if rate:
                    _RATE_CACHE[cache_key] = rate
                    return rate
        except Exception:
            return None


async def convert_currency(amount: float, from_cur: str, to_cur: str) -> float | None:
    """Переводит сумму из from_cur в to_cur."""
    if from_cur.upper() == to_cur.upper():
        return amount

    rate = await _fetch_rate(from_cur, to_cur)
    if rate:
        return round(amount * rate, 2)

    # Фолбэк на статический курс (только для RUB)
    if to_cur.upper() == "RUB":
        static_rate = _STATIC_RATES_TO_RUB.get(from_cur.upper())
        if static_rate:
            return round(amount * static_rate, 2)

    return None 