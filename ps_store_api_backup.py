from __future__ import annotations

"""PlayStation Store (v2): быстрый доступ к ценам через GraphQL product/concept API.

Публичные функции:
    async search_games(query: str, *, region: str = "US", limit: int = 40) -> list[(game_id, title)]
    async get_offers(game_id: str, *, region: str = "US") -> list[tuple]

Формат кортежа оффера совместим с routers/prices.py:
(label, price_value, currency_code, url, ps_plus_flag, platforms, deposit_flag, [discount_val])
"""

import aiohttp
import json
import re
from typing import Any, Dict, List, Tuple
from cachetools import TTLCache
from loguru import logger
from urllib.parse import urlencode as _urlencode


# --------------------------------------------------------------------------------------
# Константы
# --------------------------------------------------------------------------------------

# Сопоставление регионов локалям
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

_PRODUCT_URL_TEMPLATE = "https://store.playstation.com/{locale}/product/{product_id}"

# Кэши: 12h для поиска и 30m для товаров
_SEARCH_CACHE: TTLCache[str, List[Tuple[str, str]]] = TTLCache(maxsize=1024, ttl=12 * 60 * 60)
_PRODUCT_CACHE: TTLCache[Tuple[str, str], List[Tuple]] = TTLCache(maxsize=4096, ttl=30 * 60)

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; GameBot/1.0)"
}

# --------------------------------------------------------------------------------------
# GraphQL - productRetrieveForCtasWithPrice
# --------------------------------------------------------------------------------------

_GQL_ENDPOINT = "https://web.np.playstation.com/api/graphql/v1/op"
_OP_PRODUCT_CTA = "productRetrieveForCtasWithPrice"
_HASH_PRODUCT_CTA = "8872b0419dcab2fea5916ef698544c237b1096f9e76acc6aacf629551adee8cd"


async def _fetch_price_product(product_id: str | None, region: str) -> List[Tuple]:
    """Возвращает список офферов через productRetrieveForCtasWithPrice."""
    if not product_id:
        return []

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
                    return []
                data = await resp.json()
    except Exception as e:
        logger.info(f"[PS_API] CTA HTTP error for {product_id} in {region}: {e}")
        return []

    offers = []
    try:
        product_data = data["data"]["productRetrieve"]
        web_ctas = product_data.get("webctas", [])
        product_url = _PRODUCT_URL_TEMPLATE.format(locale=locale, product_id=product_id)

        # Валюты, в которых цена не указывается в копейках/центах
        NO_DECIMALS_CURRENCIES = {"INR", "JPY"}

        for cta in web_ctas:
            price_info = cta.get("price")
            if not price_info or price_info.get("isFree"):
                continue

            currency = price_info.get("currencyCode")
            base_val_raw = price_info.get("basePriceValue")
            disc_val_raw = price_info.get("discountedValue")

            divisor = 1 if currency in NO_DECIMALS_CURRENCIES else 100

            base_price = round(base_val_raw / divisor, 2) if base_val_raw is not None else 0.0
            disc_price = round(disc_val_raw / divisor, 2) if disc_val_raw is not None else base_price

            is_plus_offer = "PS_PLUS" in cta.get("type", "") or "PS_PLUS" in "".join(price_info.get("serviceBranding", []))
            
            offer_type = cta.get("type", "ADD_TO_CART")
            label = "PlayStation Store"
            if offer_type == 'UPSELL_PS_PLUS_DISCOUNT':
                label += " (PS Plus)"

            # Формат: (label, price, currency, url, plus_flag, platforms, deposit_flag, [discount_val])
            # platform и deposit_flag пока не извлекаем из этого API, ставим заглушки
            platforms = ["PS4", "PS5"] 
            deposit_flag = False

            has_discount = base_price > disc_price
            
            price_to_show = disc_price if has_discount else base_price
            discount_value = disc_price if has_discount else None

            offers.append(
                (
                    label,
                    base_price, # Возвращаем базовую цену
                    currency,
                    product_url,
                    is_plus_offer,
                    platforms,
                    deposit_flag,
                    discount_value, # Цена со скидкой идет сюда
                )
            )

    except (KeyError, TypeError, AttributeError) as e:
        logger.warning(f"[PS_API] CTA parse error for {product_id} in {region}: {e} | Response: {data}")
        return []
    
    # Убираем дубликаты, предпочитая офферы с PS Plus
    # Сортируем так, чтобы офферы с PS Plus были первыми, и потом по цене
    unique_offers = {}
    for offer in sorted(offers, key=lambda x: (not x[4], x[1])):
         # Ключ - цена и валюта. Это поможет убрать дубликаты с одинаковой ценой.
        key = (offer[1], offer[2])
        if key not in unique_offers:
            unique_offers[key] = offer

    return list(unique_offers.values())


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

# --------------------------------------------------------------------------------------
# Поиск (оставлен без изменений, т.к. требует отдельной логики)
# --------------------------------------------------------------------------------------

def _extract_next_data(html: str) -> Dict[str, Any] | None:
    """Извлекает JSON из тега <script id="__NEXT_DATA__">...</script>."""
    m = re.search(r"<script id=\"__NEXT_DATA__\"[^>]*>(\{.*?\})</script>", html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception as e:
        logger.warning(f"[PS2] JSON decode error: {e}")
        return None

_SEARCH_URL_TEMPLATE = "https://store.playstation.com/{locale}/search/{query}"

async def search_games(query: str, *, region: str = "US", limit: int = 40) -> List[Tuple[str, str]]:
    """Поиск через HTML-страницу.

    Извлекает данные из __NEXT_DATA__ JSON-блока.
    """
    if not query:
        return []

    locale = _REGION_TO_LOCALE.get(region, "en-us")
    cache_key = f"{locale}:{query.lower()}"
    if cache_key in _SEARCH_CACHE:
        return _SEARCH_CACHE[cache_key][:limit]

    url = _SEARCH_URL_TEMPLATE.format(locale=locale, query=aiohttp.helpers.quote(query))
    try:
        async with aiohttp.ClientSession(headers={**HEADERS, "Accept-Language": locale}) as session:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.info(f"[PS2] search HTTP {resp.status}")
                    return []
                html = await resp.text()
    except Exception as e:
        logger.warning(f"[PS2] search HTTP error: {e}")
        return []

    data = _extract_next_data(html)
    if not data:
        logger.warning("[PS2] could not find __NEXT_DATA__ on search page")
        return []

    results = []
    try:
        page_props = data.get("props", {}).get("pageProps", {})
        
        # Новый, более надёжный путь к данным
        dehydrated_state = page_props.get("dehydratedState", {})
        queries = dehydrated_state.get("queries", [])

        if not queries:
            logger.warning(f"[PS2] 'queries' not found or empty in dehydratedState. Available keys in page_props: {list(page_props.keys())}")
            return []

        # Первый элемент массива queries обычно содержит результаты поиска
        search_results_data = queries[0].get("state", {}).get("data", {})
        
        # Обходим вложенные данные до списка продуктов
        concepts = search_results_data.get("searchRetrieve", {}).get("concepts", [])
        
        for concept_info in concepts:
            if not concept_info:
                continue

            name = concept_info.get("name")
            prod = concept_info.get("defaultProduct") or {}
            pid = prod.get("id")

            if name and pid:
                results.append((f"ps:{pid}", name))

            if len(results) >= limit:
                break
                
    except (KeyError, TypeError, IndexError) as e:
        logger.warning(f"[PS2] search parse error: {e}")

    _SEARCH_CACHE[cache_key] = results
    return results 