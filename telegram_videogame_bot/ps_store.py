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
import os
from typing import List, Tuple, Dict, Any
from cachetools import TTLCache
from loguru import logger
from urllib.parse import urlencode as _urlencode
import asyncio

# Валюты, в которых PlayStation Store возвращает цены уже в целых единицах,
# поэтому делить на 100 не нужно (иначе получим ×0.01).
_NO_DECIMAL_CURRENCIES = {
    "INR",  # Indian Rupee
    "JPY",  # Japanese Yen
    "KRW",  # South Korean Won
    "HUF",  # Hungarian Forint
    "CLP",  # Chilean Peso
    "VND",  # Vietnamese Dong
}


# --- Caches ---
_SEARCH_CACHE: TTLCache[str, List[Tuple[str, str]]] = TTLCache(maxsize=1024, ttl=12 * 60 * 60)  # 12h
_PRODUCT_CACHE: TTLCache[Tuple[str, str], List[Tuple]] = TTLCache(maxsize=4096, ttl=30 * 60)  # 30m

# --- Region → locale mapping ---
_REGION_TO_LOCALE = {
    "RU": "ru-ru",
    "US": "en-us",
    "TR": "tr-tr",
    "BR": "pt-br",
    "AR": "es-ar",
    "IN": "en-in",
    "UA": "ru-ua",  # PlayStation Store для Украины, чтобы была гривна
    "KZ": "ru-ru",  # PlayStation Store для Казахстана использует русский язык и цены
    "PL": "pl-pl",
}

# Для удобства построения URL вида https://store.playstation.com/{lang}-{country.lower()}/product/{id}
# где lang – язык, а country – ISO-код страны.
PS_REGION_CONFIG = {
    "us": ("en", "US"),
    "ru": ("ru", "RU"),
    "tr": ("tr", "TR"),
    "br": ("pt", "BR"),
    "ar": ("es", "AR"),
    "in": ("en", "IN"),
    "ua": ("ru", "UA"),
    "kz": ("ru", "KZ"),
    "pl": ("pl", "PL"),
}

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; GameBot/1.0)"
}

# --- GraphQL (internal PSN API) settings ---
_GQL_ENDPOINT = "https://web.np.playstation.com/api/graphql/v1/op"
_OP_PRODUCT_CTA = "productRetrieveForCtasWithPrice"
_HASH_PRODUCT_CTA = "8872b0419dcab2fea5916ef698544c237b1096f9e76acc6aacf629551adee8cd"


_SEARCH_URL_TEMPLATE = "https://store.playstation.com/{locale}/search/{query}"
_PRODUCT_URL_TEMPLATE = "https://store.playstation.com/{locale}/product/{product_id}"


def _extract_next_data(html: str) -> Dict[str, Any] | None:
    """Извлекает JSON из тега <script id="__NEXT_DATA__">...</script>."""
    m = re.search(r"<script id=\"__NEXT_DATA__\"[^>]*>(\{.*?\})</script>", html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"[PS] JSON decode error: {e}")
        return None

# --------------------------------------------------------------------------------------
# Поиск
# --------------------------------------------------------------------------------------

async def search_games(query: str, *, region: str = "US", limit: int = 40) -> List[Tuple[str, str, str | None, str | None]]:
    """Поиск игр в PS Store через __NEXT_DATA__ на странице поиска.

    Возвращает список кортежей (game_id, title, concept_id, invariant_name),
    """
    if not query:
        return []

    locale = _REGION_TO_LOCALE.get(region, "en-us")
    # v3 кэша с invariantName
    cache_key = f"{locale}:{query.lower()}:v3"
    if cache_key in _SEARCH_CACHE:
        cached_item = _SEARCH_CACHE[cache_key]
        if len(cached_item) > 0 and len(cached_item[0]) == 4:
             return cached_item[:limit]

    url = _SEARCH_URL_TEMPLATE.format(locale=locale, query=aiohttp.helpers.quote(query))
    try:
        async with aiohttp.ClientSession(headers={**HEADERS, "Accept-Language": locale}) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.info(f"[PS] search HTTP {resp.status}")
                    return []
                html = await resp.text()
    except Exception as e:
        logger.warning(f"[PS] search HTTP error: {e}")
        return []

    data = _extract_next_data(html)
    if not data:
        logger.warning("[PS] could not find __NEXT_DATA__ on search page")
        return []

    apollo = data.get("props", {}).get("apolloState", {})
    if not apollo:
        return []

    results: List[Tuple[str, str, str | None, str | None]] = []
    for key, item in apollo.items():
        if not key.startswith("Product:"):
            continue
        title = item.get("name")
        pid = item.get("id") or key.split(":", 1)[1]
        invariant_name = item.get("invariantName")
        
        concept_ref = item.get("concept", {}).get("__ref")
        concept_id = None
        if concept_ref:
            raw_id = concept_ref.split(":", 1)[1]
            # Иногда в concept находится productId, а не числовой conceptId.
            # Настоящие conceptId - это числа.
            if raw_id and raw_id.isdigit():
                concept_id = raw_id
            else:
                 # Если это не число, скорее всего, это productId, и реального conceptId нет.
                 logger.debug(f"Concept ref '{raw_id}' is not a digit, likely a productId. Skipping concept_id.")


        if not title or not pid:
            continue
        
        game_id = f"ps:{pid}"
        results.append((game_id, title, concept_id, invariant_name))

    if not results:
        logger.info(f"[PS] No products found in apolloState for '{query}'")
        return []

    def relevance_key(game_title: str) -> tuple:
        title_norm = game_title.lower()
        query_norm = query.lower().strip()
        
        # Score based on match type
        if title_norm == query_norm:
            match_score = 0
        elif title_norm.startswith(query_norm):
            match_score = 1
        elif query_norm in title_norm:
            match_score = 2
        else:
            match_score = 3
            
        # Penalize common non-game words unless they were part of the search
        penalty = 0
        non_game_terms = ["dlc", "add-on", "pack", "set", "pass", "points", "credits", "currency", "silver", "bundle", "edition", "demo", "trial"]
        for term in non_game_terms:
            if term in title_norm and term not in query_norm:
                penalty += 1
        
        # Lower score is better. Shorter titles are preferred as a tie-breaker.
        return (match_score, penalty, len(game_title))

    results.sort(key=lambda x: relevance_key(x[1]))
    
    results = results[:limit]
    
    _SEARCH_CACHE[cache_key] = results
    return results

async def search_ps_store_games_for_country(session, query: str, lang: str, country_code: str, invariant_name: str, limit: int = 40) -> List[Dict[str, str]]:
    """Ищет игру в PS Store для конкретного региона и возвращает подходящие результаты как список словарей.

    • `query` – исходный запрос пользователя, используется для локального поиска.
    • `lang` и `country_code` – служебные, чтобы можно было в будущем задавать Accept-Language, если понадобится.
    • `invariant_name` – каноничное английское название, по которому фильтруем результаты.
    """
    # Используем уже существующую функцию search_games, игнорируя session (она там не нужна)
    region = country_code.upper()
    try:
        results = await search_games(query, region=region, limit=limit)
    except Exception as e:
        logger.error(f"[PS] Ошибка поиска игры '{query}' в регионе {region}: {e}")
        return []

    # Конвертируем результаты в словари и фильтруем по invariant_name
    filtered = []
    for game_id, title, concept_id, inv_name in results:
        pid = game_id.split(":", 1)[1] if ":" in game_id else game_id
        if inv_name and invariant_name and inv_name.lower() == invariant_name.lower():
            filtered.append({"id": pid, "title": title})
        elif not invariant_name:
            # Если нет invariant_name для фильтрации, берем как есть (fallback)
            filtered.append({"id": pid, "title": title})

    # Если после фильтрации ничего не осталось, вернем оригинальные результаты (хотя бы один)
    if not filtered:
        filtered = [{"id": game_id.split(":", 1)[1] if ":" in game_id else game_id, "title": title} for game_id, title, *_ in results]

    return filtered


# --------------------------------------------------------------------------------------
# Получение цен
# --------------------------------------------------------------------------------------

async def _fetch_price_product(product_id: str | None, region: str) -> dict | None:
    """Возвращает необработанные данные о продукте из GraphQL."""
    if not product_id:
        return None

    cache_key = (product_id, region)
    if cache_key in _PRODUCT_CACHE:
        return _PRODUCT_CACHE[cache_key]

    locale = _REGION_TO_LOCALE.get(region.upper(), "en-us")
    variables = {"productId": product_id}
    params = {
        "operationName": _OP_PRODUCT_CTA,
        "variables": json.dumps(variables, separators=(",", ":")),
        "extensions": json.dumps(
            {"persistedQuery": {"version": 1, "sha256Hash": _HASH_PRODUCT_CTA}},
            separators=(",", ":"),
        ),
    }
    url = f"{_GQL_ENDPOINT}?{_urlencode(params)}"
    headers = {
        "x-apollo-operation-name": _OP_PRODUCT_CTA,
        "Accept": "application/json",
        "Accept-Language": locale,
        "User-Agent": HEADERS["User-Agent"],
        "x-ps-country-code": region.upper(),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    logger.info(f"[PS_API] CTA HTTP {resp.status} for {product_id} in {region}")
                    return None
                data = await resp.json()
                product_data = data.get("data", {}).get("productRetrieve")
                if product_data:
                    _PRODUCT_CACHE[cache_key] = product_data
                return product_data
    except Exception as e:
        logger.info(f"[PS_API] CTA HTTP error for {product_id} in {region}: {e}")
        return None


async def get_product_id_from_concept(concept_id: str, region: str) -> str | None:
    """Получает региональный product_id со страницы концепта."""
    locale = _REGION_TO_LOCALE.get(region, "en-us")
    url = f"https://store.playstation.com/{locale}/concept/{concept_id}"
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to fetch concept page {url}, status: {resp.status}")
                    return None
                html = await resp.text()
    except Exception as e:
        logger.warning(f"Error fetching concept page {url}: {e}")
        return None
    
    data = _extract_next_data(html)
    if not data:
        logger.warning(f"Could not find __NEXT_DATA__ on concept page {url}")
        return None
        
    try:
        # Ищем ID продукта в `apolloState` по ключу, начинающемуся с `Product:`
        apollo_state = data.get("props", {}).get("apolloState", {})
        for key, value in apollo_state.items():
            if key.startswith("Product:") and value.get("id"):
                product_id = value.get("id")
                logger.info(f"Found product_id '{product_id}' for concept '{concept_id}' in region '{region}'")
                return product_id
    except Exception as e:
        logger.error(f"Error parsing __NEXT_DATA__ from concept page {url}: {e}")

    logger.warning(f"Could not find product_id for concept {concept_id} on page {url}")
    return None


async def get_product_price(product_id: str, country_code: str) -> dict | None:
    """
    Извлекает и обрабатывает информацию о цене для заданного продукта.
    """
    if product_id.startswith("ps:"):
        product_id = product_id[3:]

    product_data = await _fetch_price_product(product_id, country_code)

    if not product_data or not product_data.get("webctas"):
        logger.warning(
            f"Не найдены CTA для product_id: {product_id} в регионе {country_code}"
        )
        return None

    purchase_cta = None
    catalog_cta = None
    download_cta = None
    
    # 1. Ищем основные типы предложений
    for cta in product_data["webctas"]:
        cta_type = cta.get("type")
        if cta_type in ["ADD_TO_CART", "PRE_ORDER"]:
            purchase_cta = cta
        elif cta_type == "UPSELL_PS_PLUS_GAME_CATALOG":
            catalog_cta = cta
        elif cta_type == "DOWNLOAD":
            download_cta = cta
    
    # 2. Выбираем основной оффер для определения цены
    main_cta = purchase_cta or catalog_cta or download_cta
    
    if not main_cta or not main_cta.get("price"):
        logger.warning(
            f"Не удалось найти основной оффер с ценой для {product_id} в {country_code}. CTAs: {product_data['webctas']}"
        )
        return None
        
    price_info = main_cta.get("price")
    
    # Если есть и покупка, и каталог, цена покупки приоритетнее
    if purchase_cta and purchase_cta.get("price"):
        price_info = purchase_cta.get("price")

    # 3. Парсим информацию о цене
    try:
        currency_code = price_info.get("currencyCode") or ""
        divisor = 1 if currency_code in _NO_DECIMAL_CURRENCIES else 100

        base_price_value = price_info.get("basePriceValue", 0)
        discounted_value = price_info.get("discountedValue", 0)
        
        # Для игр из каталога цена покупки может быть в basePrice, а discounted - 0 ("Included")
        if catalog_cta and not purchase_cta:
             # Если игра только в каталоге, ее цена покупки - это basePrice, а цена по подписке - 0
             final_price = 0.0
             old_price = base_price_value / divisor if base_price_value else 0.0
        else:
            final_price = discounted_value / divisor
            old_price = base_price_value / divisor
        
        discount = 0
        if old_price > 0 and final_price < old_price:
            discount = round(100 - (final_price * 100 / old_price))
        
        # Определяем, включена ли игра в PS Plus
        is_included_in_plus = catalog_cta is not None and (final_price == 0.0 or "Included" in (price_info.get("discountText") or ""))

        # Ищем отдельную скидку для подписчиков PS Plus
        ps_plus_price = None
        is_ps_plus_special = False
        plus_discount_cta = next((c for c in product_data["webctas"] if c.get("type") == "UPSELL_PS_PLUS_DISCOUNT" and c.get("price")), None)
        if plus_discount_cta:
            plus_price_info = plus_discount_cta["price"]
            plus_discounted_value = plus_price_info.get("discountedValue")
            if plus_discounted_value is not None:
                ps_plus_price = plus_discounted_value / 100
                is_ps_plus_special = True


        return {
            "price": final_price,
            "currency": price_info.get("currencyCode"),
            "discount": discount,
            "old_price": old_price if discount > 0 and old_price > final_price else None,
            "ps_plus_price": ps_plus_price,
            "is_ps_plus_special": is_ps_plus_special,
            "is_free": final_price == 0.0 and not is_included_in_plus,
            "included_in_ps_plus": is_included_in_plus,
        }
    except (ValueError, TypeError, KeyError) as e:
        logger.error(
            f"Ошибка при обработке цены для {product_id}: {e}. Price data: {price_info}"
        )
        return None


async def get_offers(game_id: str, *, region: str = "US") -> List[Tuple]:
    """Получение офферов для игры через GraphQL.

    Args:
        game_id: ID игры, например 'ps:EP1004-CUSA08519_00-REDEMPTIONFULL02'
        region: Двухбуквенный код региона (RU, US, TR, etc.)

    Returns:
        Список кортежей с офферами.
    """
    if not game_id or not game_id.startswith("ps:"):
        return []
    
    product_id = game_id.split(":", 1)[1]
    cache_key = (product_id, region.upper())

    if cache_key in _PRODUCT_CACHE:
        cached = _PRODUCT_CACHE.get(cache_key)
        if cached is not None:
            return cached

    offers = await _fetch_price_product(product_id, region.upper())

    if offers:
        _PRODUCT_CACHE[cache_key] = offers
    
    return offers

async def get_ps_store_prices(session, game_details, country_codes):
    logger.info(f"Начало получения цен из PS Store для '{game_details.get('name', 'Unknown Game')}'.")
    country_codes = [code for code in country_codes if code not in ['ru', 'kz']]
    
    ps_prices = {}

    base_product_id = game_details.get('ps_store_id')
    invariant_name = game_details.get('invariant_name')

    if not base_product_id:
        logger.warning(f"Отсутствует ps_store_id для '{game_details.get('name', 'Unknown Game')}', пропускаем PS Store.")
        return ps_prices

    async def fetch_price(country_code, product_id):
        lang, country = PS_REGION_CONFIG[country_code]
        try:
            price_info = await get_ps_price(session, product_id, country_code)
            if price_info:
                price_info['url'] = f"https://store.playstation.com/{lang}-{country.lower()}/product/{product_id}"
                return price_info
        except Exception as e:
            logger.error(f"Ошибка при получении цены для {country_code} (ID: {product_id}): {e}")
        return None

    tasks = {}
    
    # Создаем задачи для всех стран, включая США
    # Для США и других стран логика теперь едина: найти ID и получить цену
    # Но для США у нас уже есть ID, а для других его нужно найти
    
    # Сначала для США
    if 'us' in country_codes:
        tasks['us'] = asyncio.create_task(fetch_price('us', base_product_id))
        country_codes.remove('us')

    # Затем для остальных стран
    search_tasks = {}
    for code in country_codes:
        lang, country = PS_REGION_CONFIG[code]
        search_tasks[code] = asyncio.create_task(
            search_ps_store_games_for_country(session, game_details['name'], lang, country, invariant_name or "")
        )

    # Запускаем поиск региональных ID
    search_results = await asyncio.gather(*search_tasks.values())
    
    # Создаем задачи на получение цен по найденным региональным ID
    for (code, _), country_results in zip(search_tasks.items(), search_results):
        if country_results and country_results[0].get('id'):
            regional_product_id = country_results[0]['id']
            tasks[code] = asyncio.create_task(fetch_price(code, regional_product_id))
        else:
            logger.warning(f"Не удалось найти игру '{game_details['name']}' в регионе {code}.")
 
    # Ожидаем выполнения всех задач по получению цен
    # asyncio.gather сохраняет порядок, поэтому мы можем сопоставить результаты
    # с кодами стран.
    if tasks:
        task_codes = list(tasks.keys())
        results = await asyncio.gather(*tasks.values())

        for code, result in zip(task_codes, results):
            if result:
                ps_prices[code] = result
 
    logger.info(f"Завершено получение цен из PS Store. Найдено цен для {len(ps_prices)} регионов.")
    return ps_prices


async def get_ps_price(session, product_id, country_code):
    lang, country = PS_REGION_CONFIG[country_code]
    product_data = await _fetch_price_product(product_id, country_code)

    if not product_data or not product_data.get("webctas"):
        logger.warning(
            f"Не найдены CTA для product_id: {product_id} в регионе {country_code}"
        )
        return None

    purchase_cta = None
    catalog_cta = None
    download_cta = None
    
    # 1. Ищем основные типы предложений
    for cta in product_data["webctas"]:
        cta_type = cta.get("type")
        if cta_type in ["ADD_TO_CART", "PRE_ORDER"]:
            purchase_cta = cta
        elif cta_type == "UPSELL_PS_PLUS_GAME_CATALOG":
            catalog_cta = cta
        elif cta_type == "DOWNLOAD":
            download_cta = cta
    
    # 2. Выбираем основной оффер для определения цены
    main_cta = purchase_cta or catalog_cta or download_cta
    
    if not main_cta or not main_cta.get("price"):
        logger.warning(
            f"Не удалось найти основной оффер с ценой для {product_id} в {country_code}. CTAs: {product_data['webctas']}"
        )
        return None
        
    price_info = main_cta.get("price")
    
    # Если есть и покупка, и каталог, цена покупки приоритетнее
    if purchase_cta and purchase_cta.get("price"):
        price_info = purchase_cta.get("price")

    # 3. Парсим информацию о цене
    try:
        currency_code = price_info.get("currencyCode") or ""
        divisor = 1 if currency_code in _NO_DECIMAL_CURRENCIES else 100

        base_price_value = price_info.get("basePriceValue", 0)
        discounted_value = price_info.get("discountedValue", 0)
        
        # Для игр из каталога цена покупки может быть в basePrice, а discounted - 0 ("Included")
        if catalog_cta and not purchase_cta:
             # Если игра только в каталоге, ее цена покупки - это basePrice, а цена по подписке - 0
             final_price = 0.0
             old_price = base_price_value / divisor if base_price_value else 0.0
        else:
            final_price = discounted_value / divisor
            old_price = base_price_value / divisor
        
        discount = 0
        if old_price > 0 and final_price < old_price:
            discount = round(100 - (final_price * 100 / old_price))
        
        # Определяем, включена ли игра в PS Plus
        is_included_in_plus = catalog_cta is not None and (final_price == 0.0 or "Included" in (price_info.get("discountText") or ""))

        # Ищем отдельную скидку для подписчиков PS Plus
        ps_plus_price = None
        is_ps_plus_special = False
        plus_discount_cta = next((c for c in product_data["webctas"] if c.get("type") == "UPSELL_PS_PLUS_DISCOUNT" and c.get("price")), None)
        if plus_discount_cta:
            plus_price_info = plus_discount_cta["price"]
            plus_discounted_value = plus_price_info.get("discountedValue")
            if plus_discounted_value is not None:
                ps_plus_price = plus_discounted_value / 100
                is_ps_plus_special = True


        return {
            "price": final_price,
            "currency": price_info.get("currencyCode"),
            "discount": discount,
            "old_price": old_price if discount > 0 and old_price > final_price else None,
            "ps_plus_price": ps_plus_price,
            "is_ps_plus_special": is_ps_plus_special,
            "is_free": final_price == 0.0 and not is_included_in_plus,
            "included_in_ps_plus": is_included_in_plus,
        }
    except (ValueError, TypeError, KeyError) as e:
        logger.error(
            f"Ошибка при обработке цены для {product_id}: {e}. Price data: {price_info}"
        )
        return None 