#!/usr/bin/env python3
"""Быстрый скрипт для проверки get_offers PlayStation Store по разным регионам.
Запуск:
    python debug_ps_prices.py CUSA08519_00-REDEMPTIONFULL02
По умолчанию использует productId Red Dead Redemption 2, если аргумент не передан.
"""
import asyncio
import sys
from typing import List

import aiohttp
import asyncio
import json
import re

# Европейский eShop API для поиска игр
EU_SEARCH_URL = "https://search.nintendo-europe.com/en/select"

async def search_eu_games(query, limit=10):
    params = {
        "q": query,
        "rows": limit,
        "start": 0,
        "fq": "type:GAME",
        "wt": "json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(EU_SEARCH_URL, params=params) as resp:
            data = await resp.json()
            return data

async def get_nintendo_price(nsuid, region="US"):
    url = f"https://api.ec.nintendo.com/v1/price?country={region}&ids={nsuid}&lang=en"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def get_game_info(nsuid):
    """Получить информацию об игре по NSUID"""
    url = f"https://api.ec.nintendo.com/v1/price?country=US&ids={nsuid}&lang=en"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if data and "prices" in data:
                price_info = data["prices"][0]
                return {
                    "title": price_info.get("title", "Unknown"),
                    "price": price_info.get("regular_price", {}).get("amount", "Unknown"),
                    "status": price_info.get("sales_status", "Unknown")
                }
            return None

REGIONS: List[str] = [
    "RU", "KZ", "PL", "UA", "TR", "IN", "BR", "AR", "US"
]

def game_id_from_pid(pid: str) -> str:
    if not pid.startswith("ps:"):
        return f"ps:{pid}"
    return pid

import asyncio
from telegram_videogame_bot.nintendo_eshop_api import nintendo_api

# --- Новая функция: поиск NSUID через GraphQL Nintendo US ---
async def search_us_nsuid(query, limit=10):
    url = "https://www.nintendo.com/graphql"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.nintendo.com/store/games/",
        "Origin": "https://www.nintendo.com"
    }
    gql_query = {
        "query": "query SearchGames($query: String!) { searchGames(query: $query, filters: {system: \"nintendo-switch\"}, limit: 20) { games { nsuid title } } }",
        "variables": {"query": query}
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=gql_query, headers=headers) as resp:
            try:
                data = await resp.json()
                games = data.get("data", {}).get("searchGames", {}).get("games", [])
                return games[:limit]
            except Exception:
                text = await resp.text()
                print("[GraphQL Nintendo US] Ответ не JSON! Вот первые 500 символов:")
                print(text[:500])
                return []

# --- Новая функция: парсинг NSUID из HTML Nintendo US ---
async def search_us_nsuid_html(query, limit=5):
    # Шаг 1: Поиск игры на сайте Nintendo US
    search_url = f"https://www.nintendo.com/store/search?q={aiohttp.helpers.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    games = []
    async with aiohttp.ClientSession() as session:
        try:
            # Поиск игр
            async with session.get(search_url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"[Nintendo US] Поиск HTTP {resp.status}")
                    return []
                html = await resp.text()
                
                # Ищем ссылки на игры в результатах поиска
                # Паттерн: href="/store/products/[NSUID]"
                product_links = re.findall(r'href="/store/products/([^"]+)"', html)
                
                for nsuid in product_links[:limit]:
                    # Шаг 2: Получаем страницу товара для извлечения названия
                    product_url = f"https://www.nintendo.com/store/products/{nsuid}"
                    async with session.get(product_url, headers=headers) as product_resp:
                        if product_resp.status == 200:
                            product_html = await product_resp.text()
                            
                            # Ищем название игры в HTML
                            title_match = re.search(r'<title>([^<]+)</title>', product_html)
                            title = title_match.group(1) if title_match else f"Game {nsuid}"
                            
                            # Убираем "Nintendo Switch | Nintendo" из названия
                            title = title.replace(" | Nintendo", "").replace("Nintendo Switch | ", "")
                            
                            games.append({"nsuid": nsuid, "title": title})
                            print(f"[Nintendo US] Найдена игра: {title} (NSUID: {nsuid})")
                        else:
                            print(f"[Nintendo US] Ошибка получения страницы {nsuid}: HTTP {product_resp.status}")
                            
        except Exception as e:
            print(f"[Nintendo US] Ошибка поиска: {e}")
            return []
    
    return games

# --- Поиск и получение цены через GraphQL Nintendo US ---
async def search_us_graphql(query, limit=5):
    url = "https://graph.nintendo.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.nintendo.com"
    }
    # GraphQL query для поиска по названию
    gql_query = {
        "operationName": "Search",
        "variables": {"locale": "en_US", "query": query, "limit": limit},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "b2e6e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2"}}
    }
    # Хэш выше — пример, его нужно будет заменить на актуальный, если не сработает
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=gql_query, headers=headers) as resp:
            try:
                data = await resp.json()
                return data
            except Exception:
                text = await resp.text()
                print("[GraphQL Nintendo US] Ответ не JSON! Вот первые 500 символов:")
                print(text[:500])
                return None

# --- Получение информации о товаре через GraphQL ProductsBySku ---
async def get_product_info_by_nsuid(nsuid, locale="en_US"):
    import urllib.parse
    url = "https://graph.nintendo.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.nintendo.com"
    }
    variables = {"locale": locale, "personalized": False, "skus": [str(nsuid)]}
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": "d702c3b9cf486e5ab3f0159699d5d5d36c12513ca3c98ce99a4037c76bdc6d96"}}
    params = {
        "operationName": "ProductsBySku",
        "variables": urllib.parse.quote(json.dumps(variables)),
        "extensions": urllib.parse.quote(json.dumps(extensions))
    }
    # Собираем GET-запрос
    full_url = f"https://graph.nintendo.com/?operationName=ProductsBySku&variables={params['variables']}&extensions={params['extensions']}"
    async with aiohttp.ClientSession() as session:
        async with session.get(full_url, headers=headers) as resp:
            try:
                data = await resp.json()
                return data
            except Exception:
                text = await resp.text()
                print("[GraphQL ProductsBySku] Ответ не JSON! Вот первые 500 символов:")
                print(text[:500])
                return None

# --- Поиск SKU по названию через GraphQL Nintendo ---
async def search_skus_by_name(query, locale="en_US", limit=5):
    import urllib.parse
    url = "https://graph.nintendo.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://www.nintendo.com"
    }
    # persistQuery hash для поиска (актуальный на июль 2025)
    hash_search = "b2e6e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2e2"  # заменить на актуальный, если не сработает
    gql_query = {
        "operationName": "Search",
        "variables": {"locale": locale, "query": query, "limit": limit},
        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": hash_search}}
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=gql_query, headers=headers) as resp:
            try:
                data = await resp.json()
                return data
            except Exception:
                text = await resp.text()
                print("[GraphQL Search] Ответ не JSON! Вот первые 500 символов:")
                print(text[:500])
                return None

# --- Поиск по названию через Algolia (Nintendo) ---
async def algolia_search_game(query, locale="en_us", hits_per_page=5):
    import aiohttp
    ALGOLIA_API_KEY = "a29c6927638bfd8cee23993e51e721c9"
    ALGOLIA_APP_ID = "U3B6GR4UA3"
    index = f"store_game_{locale.lower()}"
    url = f"https://u3b6gr4ua3-dsn.algolia.net/1/indexes/{index}/query"
    headers = {
        "x-algolia-api-key": ALGOLIA_API_KEY,
        "x-algolia-application-id": ALGOLIA_APP_ID,
        "Content-Type": "application/json"
    }
    body = {"params": f"query={query}&hitsPerPage={hits_per_page}"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=body) as resp:
            try:
                data = await resp.json()
                return data
            except Exception:
                text = await resp.text()
                print("[Algolia Search] Ответ не JSON! Вот первые 500 символов:")
                print(text[:500])
                return None

async def get_price_rest_api(nsuid, region):
    url = f"https://api.ec.nintendo.com/v1/price?country={region}&ids={nsuid}&lang=en"
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            try:
                data = await resp.json()
                return data
            except Exception:
                text = await resp.text()
                print(f"[REST API] Ответ не JSON! Вот первые 500 символов:")
                print(text[:500])
                return None

async def main():
    games = await nintendo_api.search_games("Super Mario", limit=50)
    print(f"Найдено игр (EU): {len(games)}")
    for idx, g in enumerate(games):
        print(f"[EU {idx}] {g.title} | NSUID: {g.nsuid} | Platform: {g.platform}")
    
    us_games = await search_us_nsuid_html("Super Mario", limit=10)
    print(f"\nНайдено игр (US): {len(us_games)}")
    for idx, g in enumerate(us_games):
        print(f"[US {idx}] {g['title']} | NSUID: {g['nsuid']}")
    
    # Тест возможных NSUID для Super Mario Odyssey в US
    print(f"\n=== Тест NSUID для Super Mario Odyssey в US ===")
    eu_nsuid = "70010000000127"  # Европейский NSUID
    possible_us_nsuids = [
        "70010000000126",  # -1
        "70010000000128",  # +1
        "70010000000125",  # -2
        "70010000000129",  # +2
        "70010000000120",  # -7
        "70010000000130",  # +3
    ]
    
    for us_nsuid in possible_us_nsuids:
        print(f"\n--- Тестируем NSUID: {us_nsuid} ---")
        try:
            price_data = await get_nintendo_price(us_nsuid, "US")
            if price_data and "prices" in price_data:
                price_info = price_data["prices"][0]
                if price_info.get("sales_status") == "onsale":
                    regular = price_info["regular_price"]["amount"]
                    currency = price_data["prices"][0]["regular_price"]["currency"]
                    title = price_info.get("title", "Unknown")
                    print(f"✅ НАЙДЕНА ЦЕНА: {regular} {currency}")
                    print(f"📝 Название игры: {title}")
                    print(f"🔍 Полный ответ API: {price_data}")
                    break
                else:
                    print(f"❌ Статус: {price_info.get('sales_status')}")
            else:
                print(f"❌ Нет данных или ошибка")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    print("\n=== Поиск и цена через GraphQL Nintendo US ===")
    gql_data = await search_us_graphql("Super Mario Odyssey", limit=3)
    print(f"GraphQL ответ: {gql_data}")

    print("\n=== Получение информации о товаре через ProductsBySku (GraphQL) ===")
    sku = "7100001130"  # SKU для Super Mario Odyssey US
    prod_data = await get_product_info_by_nsuid(sku)
    print(f"GraphQL ProductsBySku ответ: {prod_data}")
    if prod_data and 'data' in prod_data and 'products' in prod_data['data']:
        prod = prod_data['data']['products'][0]
        print(f"Название: {prod.get('name')}")
        price = prod.get('prices', {}).get('minimum', {})
        print(f"Цена: {price.get('finalPrice')} {price.get('currency')}")
        print(f"Скидка: {price.get('discounted')}")
        print(f"Ссылка: https://www.nintendo.com/us/store/products/super-mario-odyssey-switch/")

    print("\n=== Универсальный поиск SKU и цен по регионам через GraphQL Nintendo ===")
    regions = [
        ("US", "en_US"),
        ("RU", "ru_RU"),
        ("PL", "pl_PL"),
        ("TR", "tr_TR"),
        ("BR", "pt_BR"),
        ("AR", "es_AR"),
        ("IN", "en_IN"),
        ("KZ", "ru_RU"),
        ("UA", "uk_UA"),
        ("DE", "de_DE")
    ]
    search_name = "Super Mario Odyssey"
    # Поиск по US (или en_US) — получаем список SKU
    search_data = await search_skus_by_name(search_name, locale="en_US", limit=3)
    print(f"Результат поиска: {search_data}")
    # Здесь нужно распарсить search_data и получить SKU (или urlKey) для дальнейших запросов
    # ... (оставляю для доработки, если hash поиска будет найден) ...

    print("\n=== Поиск и цены через Algolia (локальный индекс) + ProductsBySku/REST API по регионам ===")
    regions = [
        ("US", "en_us"),
        ("RU", "ru_ru"),
        ("PL", "pl_pl"),
        ("TR", "tr_tr"),
        ("BR", "pt_br"),
        ("AR", "es_ar"),
        ("IN", "en_in"),
        ("KZ", "ru_ru"),
        ("UA", "uk_ua"),
        ("DE", "de_de")
    ]
    search_name = "Super Mario Odyssey"
    for reg, loc in regions:
        print(f"\n=== {reg} ===")
        algolia_data = await algolia_search_game(search_name, locale=loc, hits_per_page=3)
        if algolia_data and 'hits' in algolia_data and algolia_data['hits']:
            sku = algolia_data['hits'][0].get('sku')
            nsuid = algolia_data['hits'][0].get('nsuid')
            print(f"Найден SKU: {sku}, NSUID: {nsuid}")
            # ProductsBySku
            prod_data = await get_product_info_by_nsuid(sku, locale=loc.upper())
            if prod_data and 'data' in prod_data and 'products' in prod_data['data'] and prod_data['data']['products']:
                prod = prod_data['data']['products'][0]
                name = prod.get('name')
                price = prod.get('prices', {}).get('minimum', {})
                print(f"Название: {name}")
                print(f"Цена: {price.get('finalPrice')} {price.get('currency')}")
                print(f"Скидка: {price.get('discounted')}")
                url_key = prod.get('urlKey')
                if url_key:
                    print(f"Ссылка: https://www.nintendo.com/store/products/{url_key}/")
            else:
                print("Нет данных по этому региону через ProductsBySku. Пробую REST API...")
                if nsuid:
                    rest_data = await get_price_rest_api(nsuid, reg)
                    if rest_data and 'prices' in rest_data and rest_data['prices']:
                        price_info = rest_data['prices'][0]
                        if price_info.get('sales_status') == 'onsale':
                            regular = price_info['regular_price']['amount']
                            currency = price_info['regular_price']['currency']
                            print(f"[REST API] Цена: {regular} {currency}")
                        else:
                            print(f"[REST API] Нет актуальной цены (sales_status: {price_info.get('sales_status')})")
                    else:
                        print("[REST API] Нет данных или ошибка")
                else:
                    print("Нет NSUID для REST API!")
        else:
            print("Игра не найдена через Algolia для этого региона!")

    idx = input("\nВведите номер игры для теста (EU idx или US idx через 'us:'): ")
    use_us = False
    try:
        if idx.startswith('us:'):
            use_us = True
            idx = int(idx[3:])
        else:
            idx = int(idx)
    except Exception:
        idx = 0
    if use_us:
        game = us_games[idx]
        nsuid = game['nsuid']
        title = game['title']
        region = 'US'
    else:
        game = games[idx]
        nsuid = game.nsuid
        title = game.title
        region = 'RU'  # Можно менять на нужный регион
    print(f"\nТестируем получение цен для: {title} (NSUID: {nsuid}) по регионам: {REGIONS}")
    prices = await nintendo_api.get_prices(nsuid, REGIONS)
    for reg, data in prices.items():
        print(f"\n=== Регион: {reg} ===")
        if not data or not isinstance(data, dict):
            print("Нет данных или не dict")
            continue
        if "error" in data:
            print(f"Ошибка: {data['error']}")
            continue
        price_list = data.get("prices", [])
        if not price_list:
            print("Нет цен (prices пуст)")
            continue
        price_info = price_list[0]
        status = price_info.get("sales_status")
        if status != "onsale":
            print(f"Нет актуальной цены (sales_status: {status})")
            continue
        regular = price_info["regular_price"]["amount"]
        currency = price_info["regular_price"]["currency"]
        discount = price_info.get("discount_price", {}).get("amount")
        if discount:
            print(f"Цена: {regular} {currency} (Скидка: {discount})")
        else:
            print(f"Цена: {regular} {currency}")

if __name__ == "__main__":
    asyncio.run(main()) 