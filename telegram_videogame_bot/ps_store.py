"""PlayStation Store integration: поиск игр и получение цен через HTML JSON (__NEXT_DATA__).

search_games(query, region="US") -> [("ps:{productId}", title), ...]
get_offers(game_id, region="US") -> [(label, price, currency, url, ps_plus, platforms)]

ps_plus – True, если предложение связано с PS Plus (serviceBranding или upsellServiceBranding содержит PS_PLUS).
platforms – список строк, например ["PS4", "PS5"].
"""

from __future__ import annotations

import aiohttp
import json
import re
from typing import List, Tuple, Dict, Any
from cachetools import TTLCache
from loguru import logger

# --- Caches ---
_SEARCH_CACHE: TTLCache[str, List[Tuple[str, str]]] = TTLCache(maxsize=1024, ttl=12 * 60 * 60)  # 12h
_PRODUCT_CACHE: TTLCache[Tuple[str, str], Dict[str, Any]] = TTLCache(maxsize=4096, ttl=30 * 60)  # 30m

# --- Region → locale mapping ---
_REGION_TO_LOCALE = {
    "RU": "ru-ru",
    "US": "en-us",
    "TR": "tr-tr",
    "BR": "pt-br",
    "AR": "es-ar",
    "IN": "en-in",   # India
    "UA": "uk-ua",  # Ukraine
    "KZ": "ru-ru",  # Kazakhstan (ru locale подходит)
    "PL": "pl-pl",  # Poland
}

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; GameBot/1.0)"
}

_SEARCH_URL_TEMPLATE = "https://store.playstation.com/{locale}/search/{query}"
_PRODUCT_URL_TEMPLATE = "https://store.playstation.com/{locale}/product/{product_id}"

_CURRENCY_SYMBOL_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₺": "TRY",
    "R$": "BRL",
    "¥": "CNY",
    "₽": "RUB",
    "₹": "INR",
    "₴": "UAH",
    "₸": "KZT",
    "zł": "PLN",
}

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _extract_next_data(html: str) -> Dict[str, Any] | None:
    """Извлекает JSON из тега <script id="__NEXT_DATA__">...</script>."""
    m = re.search(r"<script id=\"__NEXT_DATA__\"[^>]*>(\{.*?\})</script>", html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception as e:
        logger.warning(f"[PS] JSON decode error: {e}")
        return None


def _currency_from_price(price_str: str, region: str) -> str:
    for symbol, cur in _CURRENCY_SYMBOL_MAP.items():
        if symbol in price_str:
            return cur
    # fallback by region
    return {
        "RU": "RUB",
        "TR": "TRY",
        "BR": "BRL",
        "AR": "ARS",
        "IN": "INR",
        "UA": "UAH",
        "KZ": "KZT",
        "PL": "PLN",
    }.get(region, "USD")


async def search_games(query: str, *, region: str = "US", limit: int = 40) -> List[Tuple[str, str]]:
    """Поиск игр в PS Store через публичную HTML-страницу search/QUERY."""
    if not query:
        return []
    region = region.upper()
    locale = _REGION_TO_LOCALE.get(region, "en-us")
    cache_key = f"{locale}:{query.lower()}"
    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key][:limit]

    url = _SEARCH_URL_TEMPLATE.format(locale=locale, query=aiohttp.helpers.quote(query))
    try:
        async with aiohttp.ClientSession(headers={**HEADERS, "Accept-Language": locale}) as session:
            async with session.get(url, timeout=20) as resp:
                if resp.status != 200:
                    logger.info(f"[PS] search HTTP {resp.status}")
                    _SEARCH_CACHE[cache_key] = []
                    return []
                html = await resp.text()
    except Exception as e:
        logger.warning(f"[PS] search error: {e}")
        _SEARCH_CACHE[cache_key] = []
        return []

    data = _extract_next_data(html)
    if not data:
        _SEARCH_CACHE[cache_key] = []
        return []

    apollo = data.get("props", {}).get("apolloState", {})

    results: List[Tuple[str, str]] = []
    for key, item in apollo.items():
        if not key.startswith("Product:"):
            continue
        title = item.get("name")
        pid = item.get("id") or key.split(":", 1)[1]
        if not title or not pid:
            continue
        game_id = f"ps:{pid}"
        results.append((game_id, title))
        # сохраняем объект продукта для зоны региона
        _PRODUCT_CACHE[(region, game_id)] = item

        if len(results) >= limit:
            break

    _SEARCH_CACHE[cache_key] = results
    return results


async def _fetch_product(pid: str, region: str) -> Dict[str, Any] | None:
    """Запрос HTML страницы продукта для получения JSON."""
    locale = _REGION_TO_LOCALE.get(region, "en-us")
    url = _PRODUCT_URL_TEMPLATE.format(locale=locale, product_id=pid)
    try:
        async with aiohttp.ClientSession(headers={**HEADERS, "Accept-Language": locale}) as session:
            async with session.get(url, timeout=20) as resp:
                if resp.status != 200:
                    logger.info(f"[PS] product HTTP {resp.status} for {pid}")
                    return None
                html = await resp.text()
    except Exception as e:
        logger.warning(f"[PS] product fetch error: {e}")
        return None

    data = _extract_next_data(html)
    if not data:
        return None

    apollo = data.get("props", {}).get("apolloState", {})
    for key, item in apollo.items():
        if key.startswith("Product:") and item.get("id") == pid:
            return item
    return None


async def get_offers(game_id: str, region: str = "US", _depth: int = 0) -> List[Tuple[str, float, str, str]]:
    """Возвращает [(store_label, price, currency, url, ps_plus, platforms)]."""
    if not game_id.startswith("ps:"):
        return []

    region = region.upper()
    cache_key = (region, game_id)
    product = _PRODUCT_CACHE.get(cache_key)

    if product is None:
        pid = game_id.split(":", 1)[1]
        product = await _fetch_product(pid, region)
        if product is None:
            # Фоллбэк: попытаться найти продукт по имени (если глубина 0)
            if _depth == 0:
                # Берём название из любого кэша, если есть
                title_guess = None
                for (_r, gid), obj in _PRODUCT_CACHE.items():
                    if gid == game_id:
                        title_guess = obj.get("name")
                        break
                if not title_guess:
                    # как крайний случай – по id без префикса
                    title_guess = pid.split("_", 1)[0]
                candidates = await search_games(title_guess, region=region, limit=1)
                if candidates:
                    return await get_offers(candidates[0][0], region, _depth=1)
            return []
        _PRODUCT_CACHE[cache_key] = product

    # --- Platforms ---
    platforms = product.get("platforms") or []

    # --- Price ---
    price_info = product.get("price") or {}
    is_free = price_info.get("isFree", False)

    if is_free:
        price_val = 0.0
        currency = "FREE"
    else:
        price_str: str = price_info.get("discountedPrice") or price_info.get("basePrice") or ""
        if not price_str:
            return []
        currency = _currency_from_price(price_str, region)
        # оставляем только числа, запятую меняем на точку
        num_m = re.search(r"[\d.,]+", price_str)
        if not num_m:
            return []
        raw = re.sub(r"[\s\u00A0]", "", num_m.group(0))  # убираем пробелы/NBSP

        if "," in raw and "." in raw:
            # Определяем, какой символ – десятичный: обычно последний встреченный
            if raw.rfind(',') > raw.rfind('.'):
                # Формат 1.234,56  (тысячи '.' , десятичная ',')
                raw = raw.replace('.', '').replace(',', '.')
            else:
                # Формат 1,234.56  (тысячи ',' , десятичная '.') – достаточно убрать ','
                raw = raw.replace(',', '')
        elif "," in raw:
            # Формат 123,45  (запятая – десятичная)
            raw = raw.replace(',', '.')
        # else: только точка – ничего делать не нужно
        num_raw = raw
        try:
            price_val = float(num_raw)
        except ValueError:
            logger.warning(f"[PS] cannot parse price '{price_str}' for {game_id}")
            return []

    # --- PS Plus flag ---
    plus_flag = False
    for arr in (price_info.get("serviceBranding"), price_info.get("upsellServiceBranding")):
        if arr and any("PLUS" in s for s in arr):
            plus_flag = True
            break

    locale = _REGION_TO_LOCALE.get(region, "en-us")
    url = _PRODUCT_URL_TEMPLATE.format(locale=locale, product_id=product.get("id"))

    label = "PlayStation Store" if region == "RU" else f"PlayStation Store {region}"
    return [(label, price_val, currency, url, plus_flag, platforms)] 