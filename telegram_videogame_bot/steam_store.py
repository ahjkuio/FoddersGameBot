import aiohttp
from typing import List, Tuple
from loguru import logger
from cachetools import TTLCache

_SEARCH_CACHE: TTLCache[str, List[Tuple[str, str]]] = TTLCache(maxsize=1024, ttl=12 * 60 * 60)  # 12h
_PRICE_CACHE: TTLCache[str, Tuple[float, str, str]] = TTLCache(maxsize=4096, ttl=30 * 60)  # 30m

STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"

HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "ru,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; GameBot/1.0)"
}


async def search_games(query: str, limit: int = 20) -> List[Tuple[str, str]]:
    """Поиск игр в Steam. Возвращает [("steam:{appid}", name)]"""

    if query in _SEARCH_CACHE:
        return _SEARCH_CACHE[query][:limit]

    params = {
        "term": query,
        "cc": "ru",
        "l": "russian",
    }
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            async with session.get(STEAM_SEARCH_URL, params=params, timeout=10) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception:
            return []

    results: List[Tuple[str, str]] = []
    for item in data.get("items", [])[:limit]:
        appid = item.get("id")
        name = item.get("name")
        if appid and name:
            results.append((f"steam:{appid}", name))

    if results:
        _SEARCH_CACHE[query] = results
    return results


async def get_offers(game_id: str, region: str = "RU") -> List[Tuple[str, float, str, str]]:
    """Получить цену для игры из Steam. Возвращает [(store, price, currency, url)]."""
    if not game_id.startswith("steam:"):
        return []

    appid = game_id.split(":")[1]
    url = f"https://store.steampowered.com/app/{appid}"
    
    # --- Check Cache ---
    cache_key = f"{game_id}:{region}"
    if cache_key in _PRICE_CACHE:
        store, price, cur = _PRICE_CACHE[cache_key]
        if cur == "FREE":
             return [(store, price, cur, url)]
        return [(store, price, cur, url)]

    # --- API Request ---
    lang = "russian" if region.upper() == "RU" else "english"
    params = {
        "appids": appid,
        "cc": region.upper(),
        "l": lang,
        "filters": "price_overview"
    }
    
    label = "Steam" if region.upper() == "RU" else f"Steam {region.upper()}"

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            async with session.get(STEAM_APPDETAILS_URL, params=params, timeout=10) as resp:
                if resp.status != 200:
                    logger.warning(f"Steam appdetails HTTP {resp.status} for {appid} region={region}")
                    return []
                data = await resp.json()
        except Exception as e:
            logger.error(f"Steam appdetails request error for {appid}: {e}")
            return []

    details = data.get(appid, {}).get("data")

    # --- Process Response ---
    if not details:
        if region.upper() != "US":
            logger.warning(f"No details data for {appid} in {region}. Trying fallback to US.")
            return await get_offers(game_id, "US")
        return []

    # Handle free games
    if details.get("is_free", False):
        offer = (label, 0.0, "FREE")
        _PRICE_CACHE[cache_key] = offer
        return [(offer[0], offer[1], offer[2], url)]

    # Handle paid games
    price_info = details.get("price_overview")
    if not price_info:
        if region.upper() != "US":
            logger.warning(f"No price_overview for {appid} in {region}. Trying fallback to US.")
            return await get_offers(game_id, "US")
        return []

    final_int = price_info.get("final")
    currency = price_info.get("currency", "USD")
    if final_int is None:
        return []

    price = round(final_int / 100, 2)
    offer_tuple = (label, price, currency)
    _PRICE_CACHE[cache_key] = offer_tuple
    return [(offer_tuple[0], offer_tuple[1], offer_tuple[2], url)] 