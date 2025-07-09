"""Функции для взаимодействия с GOG.com API."""

import aiohttp
from typing import List, Tuple, Dict, Any
from cachetools import TTLCache
from loguru import logger
from fuzzywuzzy import fuzz

# --- Constants ---
SEARCH_URL = "https://embed.gog.com/games/ajax/filtered"
PRODUCT_API_URL_TEMPLATE = "https://api.gog.com/products/{id}"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; GameBot/1.0)",
}

# --- Caches ---
# Кэшируем полные объекты продуктов, чтобы не делать повторных запросов
PRODUCT_CACHE: TTLCache[str, Dict[str, Any]] = TTLCache(maxsize=1024, ttl=30 * 60)  # 30m

# --- Functions ---

async def search_games(query: str, region: str = "RU") -> List[Tuple[str, str]]:
    """
    Ищет игры в GOG.com по названию.
    Добавлено кодирование запроса для поддержки кириллицы.

    Args:
        query: Поисковый запрос (название игры).
        region: Код страны для региональных цен.

    Returns:
        Список кортежей (game_id, title), где game_id - "gog:{id}".
    """
    params = {
        "mediaType": "game",
        "search": query,
        "country": region.upper(),
    }
    
    games = []
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(SEARCH_URL, params=params, timeout=10) as resp:
                if resp.status != 200:
                    logger.warning(f"GOG search API failed with status {resp.status} for query: '{query}'")
                    return []
                data = await resp.json()
    except Exception as e:
        logger.error(f"Error during GOG search API request: {e}")
        return []

    if not data or not data.get("products"):
        logger.info(f"No games found on GOG for query: '{query}'")
        return []

    for product in data["products"]:
        # Фильтруем неигровой контент: фильмы, саундтреки, DLC
        title_lower = product.get("title", "").lower()
        if product.get("movie") or "soundtrack" in title_lower or " ost" in title_lower or title_lower.endswith(" ost"):
            continue

        gog_id = product.get("id")
        title = product.get("title")
        if not gog_id or not title:
            continue
        
        game_id = f"gog:{gog_id}"
        games.append((game_id, title))
        
        # Кэшируем весь объект продукта для get_offers
        PRODUCT_CACHE[game_id] = product

    return games


async def get_offers(game_id: str, region: str = "RU") -> List[Tuple[str, float, str, str]]:
    """
    Получает предложения (цену) для конкретной игры из GOG.com.
    Данные в основном берутся из кэша, заполненного при поиске.
    """
    if game_id not in PRODUCT_CACHE:
        # Обычно данные должны быть в кэше после поиска.
        logger.warning(f"Игра {game_id} не найдена в кэше GOG. Цена может отсутствовать.")
        return []

    product_data = PRODUCT_CACHE[game_id]
    
    # --- URL ---
    slug = product_data.get("slug")
    if not slug:
        logger.warning(f"Не найден slug для GOG игры {game_id}, ссылка может быть неверной.")
        # Фоллбэк на старое поле 'url'
        url_path = product_data.get('url', '')
        slug = url_path.split('/')[-1]

    if not slug:
        return [] # Не можем построить URL

    url = f"https://www.gog.com/game/{slug}"

    # --- Price ---
    try:
        price_info = product_data.get("price", {})

        # Если нет цены и игра не бесплатная, пробуем fallback
        if not price_info.get("isFree") and not price_info.get("finalAmount"):
            # Здесь цена действительно отсутствует в данном регионе
            if region.upper() == "RU":
                logger.warning(
                    f"GOG игра {game_id} недоступна в RU (нет цены), пробую US регион."
                )
                original_title = product_data.get("title", "")
                us_games = await search_games(original_title, "US")
                if us_games:
                    # выбираем наиболее похожий ID
                    best_match_id, _ = max(
                        us_games,
                        key=lambda t: fuzz.ratio(original_title, t[1])
                    )
                    return await get_offers(best_match_id, "US")
            return []

        if price_info.get("isFree"):
            return [("GOG.com", 0.0, "FREE", url)]

        price_str = price_info.get("finalAmount")
        if not price_str:
            return []

        price = float(price_str)
        currency = price_info.get("currency", "RUB").upper()
        label = "GOG.com" if region.upper() == "RU" else f"GOG.com {region.upper()}"

        return [(label, price, currency, url)]

    except (ValueError, TypeError, KeyError) as e:
        logger.error(f"Ошибка парсинга данных о цене GOG для {game_id}: {e}")
        return [] 