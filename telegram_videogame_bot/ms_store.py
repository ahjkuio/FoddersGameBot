"""Microsoft Store (Xbox / PC) helper.

Минимальная заглушка. Будет доработана для работы с DisplayCatalog API.
Поддерживает флаг game_pass в ответах get_offers, который позже будет отображаться ботом.

search_games(query) -> [("ms:{productId}", title), ...]
get_offers(game_id, region) -> [(store_label, price, currency, url, game_pass)]
На первых порах, чтобы не ломать существующий формат, game_pass просто
добавляется в label («Microsoft Store (Game Pass)»).
"""
from __future__ import annotations

import aiohttp
import re, json
from typing import List, Tuple
from loguru import logger
from cachetools import TTLCache

_SEARCH_CACHE: TTLCache[str, List[Tuple[str, str]]] = TTLCache(maxsize=1024, ttl=12 * 60 * 60)  # 12h
_PRICE_CACHE: TTLCache[str, Tuple[str, float, str, str]] = TTLCache(maxsize=4096, ttl=30 * 60)  # 30m

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; GameBot/1.0)"
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_XBOX_SEARCH_URL = "https://www.xbox.com/{locale}/search?q={query}&cat=games"

# Сопоставление регионов Xbox локациям
_REGION_TO_LOCALE = {
    "RU": "ru-ru",
    "US": "en-us",
    "TR": "tr-tr",
    "BR": "pt-br",
    "AR": "es-ar",
}


def _extract_product_summaries(html: str) -> dict[str, dict]:
    """Извлекает объект productSummaries из скрипта на странице xbox.com.

    Структура HTML одинакова как для результатов поиска, так и для страниц
    конкретных игр: внутри большого JSON-объекта присутствует ключ
    "productSummaries". Мы ищем начало этого объекта и затем счётчиком фигурных
    скобок находим его конец, чтобы безопасно вырезать корректную подстроку
    и распарсить её через json.loads().
    """

    start_key = '"productSummaries":'
    start = html.find(start_key)
    if start == -1:
        return {}

    # позиция первой открывающей скобки
    brace_open = html.find('{', start)
    if brace_open == -1:
        return {}

    depth = 1
    i = brace_open + 1
    length = len(html)
    while i < length and depth:
        ch = html[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        i += 1

    if depth != 0:
        return {}

    json_str = html[brace_open:i]
    try:
        return json.loads(json_str)
    except Exception:
        return {}


async def search_games(query: str, limit: int = 20, *, region: str = "US") -> List[Tuple[str, str]]:
    """Поиск через публичную HTML-страницу xbox.com/search."""

    if not query:
        return []

    locale = _REGION_TO_LOCALE.get(region.upper(), "en-us")
    cache_key = f"{locale}:{region}:{query.lower()}"
    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key][:limit]

    url = _XBOX_SEARCH_URL.format(locale=locale, query=aiohttp.helpers.quote(query))
    headers = {**HEADERS, "Accept-Language": locale, "x-market": region}

    results: List[Tuple[str, str]] = []
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"[MS] search HTTP {resp.status}")
                    _SEARCH_CACHE[cache_key] = []
                    return []
                html = await resp.text()
    except Exception as e:
        logger.warning(f"[MS] search error: {e}")
        _SEARCH_CACHE[cache_key] = []
        return []

    summaries = _extract_product_summaries(html)
    for pid, info in summaries.items():
        title = info.get("title") or info.get("productTitle")
        if not title:
            continue
        # Если игра доступна хотя бы на одной платформе (PC или Xbox), оставляем
        results.append((f"ms:{pid}", title))
        if len(results) >= limit:
            break

    _SEARCH_CACHE[cache_key] = results
    return results


async def get_offers(game_id: str, region: str = "US") -> List[Tuple[str, float, str, str]]:
    """Парсит ту же выдачу Xbox для получения цены и флага Game Pass."""

    if not game_id.startswith("ms:"):
        return []

    pid = game_id.split(":", 1)[1]
    locale = _REGION_TO_LOCALE.get(region.upper(), "en-us")
    url = f"https://www.xbox.com/{locale}/games/store/x/{pid}"
    headers = {**HEADERS, "Accept-Language": locale, "x-market": region}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.info(f"[MS] price HTTP {resp.status} for {pid}")
                    return []
                html = await resp.text()
    except Exception as e:
        logger.warning(f"[MS] price error: {e}")
        return []

    summaries = _extract_product_summaries(html)
    info = summaries.get(pid)
    if not info:
        return []

    # цена
    price = None
    currency = "USD"
    try:
        purch = info["specificPrices"].get("purchaseable")
        if purch:
            purch = purch[0]
            price = purch.get("listPrice") or purch.get("msrp")
            currency = purch.get("currency", currency)
    except Exception:
        pass

    if price is None:
        return []

    game_pass = bool(info.get("includedWithPassesProductIds"))
    hardware = info.get("availableOn") or []  # например ["XboxOne", "XboxSeriesX"]
    label = "Xbox Store" if region.upper() == "RU" else f"Xbox Store {region.upper()}"
    return [(label, float(price), currency, url, game_pass, hardware)] 