"""Функции для взаимодействия с Epic Games Store API с обходом Cloudflare."""

import asyncio
import json
from functools import partial
from typing import Any, Dict, List, Tuple, Tuple as _Tuple

import cloudscraper
from cachetools import TTLCache
from loguru import logger

# --- Constants ---
GRAPHQL_URL = "https://store.epicgames.com/graphql"
PRODUCT_URL_TEMPLATE = "https://store.epicgames.com/ru/p/{slug}"

# Запрос для поиска игр
SEARCH_QUERY = """
query searchStoreQuery($keywords: String!, $country: String!, $locale: String, $count: Int) {
  Catalog {
    searchStore(keywords: $keywords, country: $country, locale: $locale, count: $count) {
      elements {
        title
        id
        namespace
        productSlug
        urlSlug
        price(country: $country) {
          totalPrice {
            discountPrice
            originalPrice
            currencyCode
          }
        }
      }
    }
  }
}
"""

# --- Scraper Instance ---
scraper = cloudscraper.create_scraper(
    browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
)

# --- Caches ---
# Ключ кэша: (REGION, game_id) – чтобы цены не путались между странами
PRODUCT_CACHE: TTLCache[_Tuple[str, str], Dict[str, Any]] = TTLCache(maxsize=2048, ttl=30 * 60)

# --- Functions ---

async def _epic_graphql_request(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """
    Асинхронно выполняет GraphQL-запрос к Epic Games с использованием cloudscraper.
    """
    payload = {"query": query, "variables": variables}
    logger.debug(f"Отправка GraphQL-запроса в Epic Games через Cloudscraper с переменными: {variables}")

    loop = asyncio.get_running_loop()
    try:
        # scraper.post - синхронная функция, запускаем ее в отдельном потоке
        request_func = partial(scraper.post, GRAPHQL_URL, json=payload, timeout=25)
        resp = await loop.run_in_executor(None, request_func)
        
        logger.debug(f"Ответ от Epic GraphQL (Cloudscraper). Статус: {resp.status_code}")

        if resp.status_code != 200:
            logger.warning(
                f"GraphQL-запрос к Epic (Cloudscraper) провалился со статусом {resp.status_code}. "
                f"Ответ: {resp.text[:400]}"
            )
            return {}
            
        return resp.json()

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON от Epic GraphQL (Cloudscraper): {e}. Ответ: {resp.text[:200]}")
        return {}
    except Exception as e:
        logger.error(f"Неожиданная ошибка при запросе к Epic GraphQL (Cloudscraper): {e}", exc_info=True)
        return {}


async def search_games(query: str, region: str = "RU") -> List[Tuple[str, str]]:
    """Ищет игры в Epic Games Store, используя GraphQL и Cloudscraper."""
    variables = {
        "keywords": query,
        "country": region.upper(),
        "locale": "ru-RU" if region.upper() == "RU" else "en-US",
        "count": 40,
    }
    data = await _epic_graphql_request(SEARCH_QUERY, variables)

    if not data or not data.get("data"):
        return []

    elements = data["data"].get("Catalog", {}).get("searchStore", {}).get("elements", [])
    if not elements:
        logger.info(f"Не найдено игр в Epic Games по запросу: '{query}'")
        return []

    games = []
    for item in elements:
        title = item.get("title")
        slug = item.get("productSlug") or item.get("urlSlug")
        namespace = item.get("namespace") or "_nons"  # Fortnite и др. могут не иметь namespace

        # Пропускаем, если нет обязательных полей или это "загадочная игра"
        if not all([title, slug]) or title == "Mystery Game":
            continue

        game_id = f"epic:{namespace}/{slug.replace('/home', '')}"
        games.append((game_id, title))
        PRODUCT_CACHE[(region.upper(), game_id)] = item

    return games


async def get_offers(game_id: str, region: str = "RU") -> List[Tuple[str, float, str, str]]:
    """Возвращает цену (или информацию о бесплатности) для игры Epic Games по её game_id.

    Мы пытаемся сначала взять данные из кэша, сформированного при поиске. Если их нет
    (например, bot только что перезапустился), пробуем выполнить одиночный поиск по slug.
    """

    # Пытаемся достать из кэша
    cache_key = (region.upper(), game_id)
    game = PRODUCT_CACHE.get(cache_key)

    # Если в кэше нет — пробуем найти по slug из game_id
    if game is None:
        try:
            # game_id имеет форму epic:{namespace}/{slug}
            _, composite = game_id.split(":", 1)
            _, slug = composite.split("/", 1)
            logger.debug(f"Epic get_offers: кэш пуст, выполняю одиночный поиск по slug '{slug}'.")
            data = await _epic_graphql_request(
                SEARCH_QUERY,
                {
                    "keywords": slug,
                    "country": region.upper(),
                    "locale": "ru-RU" if region.upper() == "RU" else "en-US",
                    "count": 1,
                },
            )
            elements = (
                data.get("data", {})
                .get("Catalog", {})
                .get("searchStore", {})
                .get("elements", [])
            )
            if not elements:
                return []
            game = elements[0]
            PRODUCT_CACHE[cache_key] = game
        except Exception as e:
            logger.error(f"Epic get_offers: ошибка одиночного поиска для {game_id}: {e}")
            return []

    title = game.get("title")
    
    # --- Цена и флаг «бесплатно» ---
    price_data = game.get("price", {})
    total_price = price_data.get("totalPrice", {})
    is_free = total_price.get("discountPrice", -1) == 0

    # --- URL ---
    try:
        _, composite_id = game_id.split(":", 1)
        _, slug = composite_id.split("/", 1)
    except ValueError:
        slug = game.get("productSlug", game.get("urlSlug", ""))
    url = PRODUCT_URL_TEMPLATE.format(slug=slug)
    
    # --- Цена ---
    if total_price.get("discountPrice", 0) == 0:
        price = 0.0
        currency = "FREE"
    else:
        price = total_price.get("discountPrice") / 100
        currency = total_price.get("currencyCode", "USD")

    # Если запрашиваем RU-цену, но GraphQL вернул валюту отличную от RUB (чаще всего USD)
    # пытаемся вытащить цену из HTML-страницы продукта. У Epic она обычно уже отрисована
    # сервером и содержит символ «₽». При успехе подменяем price/currency на RUB.
    # Если вытащить цену не получилось, больше не отбрасываем игру целиком – оставим
    # цену в той валюте, что пришла из GraphQL, чтобы у пользователя всё-таки была
    # хоть какая-то информация.

    if region.upper() == "RU" and currency != "RUB" and not is_free:
        try:
            html_headers = {
                "Accept-Language": "ru,en;q=0.8",
                "User-Agent": "Mozilla/5.0 (compatible; GameBot/1.0)"
            }
            # Пробуем сначала региональный URL (с /ru/). Cloudflare иногда даёт 403.
            html_resp = scraper.get(url, headers=html_headers, timeout=20)
            if html_resp.status_code == 403:
                alt_url = url.replace("/ru/p/", "/p/")
                logger.info(f"Epic HTML fallback got 403, retry with generic path {alt_url}")
                html_resp = scraper.get(alt_url, headers=html_headers, timeout=20)
                if html_resp.status_code == 200:
                    url = alt_url  # обновляем url для ссылке в ответе
                else:
                    logger.warning(f"Epic HTML fallback status {html_resp.status_code} for {alt_url}")
            if html_resp.status_code == 200:
                import re
                # Ищем число (может содержать пробелы или NBSP) перед знаком ₽, допускаем дробные цены
                m = re.search(r"(?P<rub>[\d\s\u00A0]+(?:[.,]\d{1,2})?)\s*₽", html_resp.text)
                if m:
                    rub_str = m.group("rub").replace("\u00A0", " ").replace(" ", "").replace(",", ".")
                    try:
                        price = float(rub_str)
                        currency = "RUB"
                        logger.info(f"Epic HTML fallback succeeded for {title}: {price} RUB")
                    except ValueError:
                        logger.warning(f"Epic HTML fallback: cannot convert '{rub_str}' to float for {url}")
                else:
                    logger.info(f"Epic HTML fallback: ₽ not found in page for {url}")
            else:
                logger.warning(f"Epic HTML fallback status {html_resp.status_code} for {url}")
        except Exception as e:
            logger.warning(f"Epic HTML fallback error for {url}: {e}")

    label = "Epic Games" if region.upper() == "RU" else f"Epic Games {region.upper()}"
    
    return [(label, price, currency, url)] 