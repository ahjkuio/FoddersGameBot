#!/usr/bin/env python3
"""
Debug скрипт для тестирования получения цен Nintendo Switch по разным регионам.
Реализует стратегию:
- US/BR/AR: поиск NSUID через HTML парсинг Nintendo US + REST API
- RU/PL: попытка через европейский NSUID (если доступен)
- Остальные: показ блокировки
"""

import asyncio
import aiohttp
import json
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import sys
import os

# Добавляем путь к модулям бота
sys.path.append(os.path.join(os.path.dirname(__file__), 'telegram_videogame_bot'))

from nintendo_eshop_api import nintendo_api, NintendoGame

NINTENDO_COOKIES = ""  # Вставь сюда строку cookies из браузера, например: "ncom_session=...; _ga=..."


@dataclass
class PriceInfo:
    """Информация о цене игры"""
    region: str
    price: Optional[str] = None
    currency: Optional[str] = None
    status: str = "unknown"
    nsuid: Optional[str] = None
    error: Optional[str] = None


class NintendoPriceDebugger:
    """Отладчик цен Nintendo Switch"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.algolia_app_id = "U3B6Z4J8T8"
        self.algolia_api_key = "c4da8be7f29e4fb83b02d7ee5e9b115c"
        # Новый публичный индекс Nintendo Store
        self.store_algolia_app = "U3B6GR4UA3"
        self.store_algolia_key = "a29c6927638bfd8cee23993e51e721c9"
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def search_nsuid_us_html(self, game_name: str) -> Optional[str]:
        """Поиск NSUID через HTML парсинг Nintendo US сайта"""
        try:
            # Шаг 1: Поиск игры на сайте Nintendo US
            search_url = f"https://www.nintendo.com/store/search?q={aiohttp.helpers.quote(game_name)}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9"
            }
            
            async with self.session.get(search_url, headers=headers) as resp:
                if resp.status != 200:
                    print(f"[Nintendo US HTML] Поиск HTTP {resp.status}")
                    return None
                html = await resp.text()
                
                # Ищем ссылки на игры в результатах поиска
                # Паттерн: href="/store/products/[NSUID]"
                product_links = re.findall(r'href="/store/products/([^"]+)"', html)
                
                if product_links:
                    nsuid = product_links[0]  # Берем первый результат
                    print(f"[Nintendo US HTML] Найден NSUID: {nsuid}")
                    return nsuid
                else:
                    print(f"[Nintendo US HTML] Не найдено ссылок на продукты для: {game_name}")
                    return None
                    
        except Exception as e:
            print(f"Ошибка поиска NSUID US HTML: {e}")
            return None
    
    async def search_sku_algolia(self, game_name: str, algolia_index: str) -> Optional[str]:
        """Поиск SKU/NSUID через нужный индекс Algolia (по региону)"""
        try:
            url = f"https://{self.store_algolia_app}-dsn.algolia.net/1/indexes/store_game_{algolia_index}/query"
            headers = {
                "X-Algolia-API-Key": self.store_algolia_key,
                "X-Algolia-Application-Id": self.store_algolia_app,
                "Content-Type": "application/json"
            }
            data = {
                "query": game_name,
                "hitsPerPage": 5
            }
            async with self.session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    hits = result.get("hits", [])
                    if hits:
                        nsuid = hits[0].get("nsuid")
                        sku = hits[0].get("sku")
                        return nsuid or sku
                return None
        except Exception as e:
            print(f"Ошибка поиска SKU Algolia ({algolia_index}): {e}")
            return None

    async def get_price_by_nsuid_rest(self, nsuid: str, region: str) -> Tuple[Optional[str], Optional[str]]:
        """Получение цены по NSUID через REST API Nintendo"""
        try:
            url = f"https://api.ec.nintendo.com/v1/price?country={region}&ids={nsuid}&lang=en"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    prices = data.get("prices", [])
                    if prices and prices[0].get("sales_status") == "onsale":
                        price_info = prices[0]
                        price = price_info["regular_price"]["amount"]
                        currency = price_info["regular_price"]["currency"]
                        return str(price), currency
                return None, None
        except Exception as e:
            print(f"Ошибка получения цены для {region}: {e}")
            return None, None

    async def get_price_graphql(self, sku: str, locale: str) -> Tuple[Optional[float], Optional[float], str, bool]:
        """Получить (regular, final, currency, discounted) через GraphQL ProductsBySku с браузерными заголовками и поддержкой cookies"""
        try:
            params = {
                "operationName": "ProductsBySku",
                "variables": json.dumps({"locale": locale, "personalized": False, "skus": [sku]}),
                "extensions": json.dumps({"persistedQuery": {"version": 1, "sha256Hash": "d702c3b9cf486e5ab3f0159699d5d5d36c12513ca3c98ce99a4037c76bdc6d96"}})
            }
            query_string = "&".join(f"{k}={aiohttp.helpers.quote(v)}" for k, v in params.items())
            url = f"https://graph.nintendo.com/?{query_string}"
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "apollographql-client-name": "ncom",
                "apollographql-client-version": "1.0.0",
                "origin": "https://www.nintendo.com",
                "referer": "https://www.nintendo.com/",
                "content-type": "application/json"
            }
            cookies = {}
            if NINTENDO_COOKIES:
                for part in NINTENDO_COOKIES.split(';'):
                    if '=' in part:
                        k, v = part.strip().split('=', 1)
                        cookies[k] = v
            async with self.session.get(url, headers=headers, cookies=cookies if cookies else None) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    prod = data.get("data", {}).get("products", [])
                    if not prod:
                        print(f"[DEBUG][{locale}] Нет products в ответе: {data}")
                        return None, None, None, False
                    price_block = prod[0]["prices"]["minimum"]
                    print(f"[DEBUG][{locale}] price_block: {price_block}")
                    if price_block.get("finalPrice") is None:
                        print(f"[DEBUG][{locale}] Нет finalPrice! price_block: {price_block}")
                        return None, None, None, False
                    # Корректно обрабатываем int/float
                    regular = float(price_block["regularPrice"]) if price_block.get("regularPrice") is not None else None
                    final = float(price_block["finalPrice"]) if price_block.get("finalPrice") is not None else None
                    currency = price_block.get("currency")
                    discounted = price_block.get("discounted", False)
                    return regular, final, currency, discounted
                print(f"[DEBUG][{locale}] HTTP status: {resp.status}")
                return None, None, None, False
        except Exception as e:
            print(f"GraphQL price error: {e}")
            return None, None, None, False
    
    async def search_games_european(self, game_name: str) -> List[NintendoGame]:
        """Поиск игр через европейский API Nintendo"""
        try:
            return await nintendo_api.search_games(game_name, limit=5)
        except Exception as e:
            print(f"Ошибка поиска европейских игр: {e}")
            return []
    
    async def get_game_prices(self, game_name: str, regions: List[str]) -> Dict[str, PriceInfo]:
        """Получение цен игры для всех регионов"""
        results = {}
        
        # Группируем регионы по стратегии
        us_br_ar_regions = ["US", "BR", "AR"]
        ru_pl_regions = ["RU", "PL"]
        other_regions = [r for r in regions if r not in us_br_ar_regions + ru_pl_regions]
        
        # Стратегия 1: US/BR/AR - поиск через локальный индекс Algolia с fallback на US
        if any(r in regions for r in us_br_ar_regions):
            print(f"🔍 Поиск SKU/NSUID через локальный индекс Algolia для: {game_name}")
            locale_map = {"US": ("en_us", "en_US"), "BR": ("pt_br", "pt_BR"), "AR": ("es_ar", "es_AR")}
            for region in us_br_ar_regions:
                if region in regions:
                    algolia_index, gql_locale = locale_map.get(region, ("en_us", "en_US"))
                    sku = await self.search_sku_algolia(game_name, algolia_index)
                    if not sku:
                        print(f"⚠️ [{region}] SKU не найден в локальном индексе, ищу в US-индексе...")
                        sku = await self.search_sku_algolia(game_name, "en_us")
                    if sku:
                        print(f"✅ [{region}] Использую SKU/NSUID: {sku}")
                        regular, final, currency, discounted = await self.get_price_graphql(sku, gql_locale)
                        if final is not None:
                            price_val = final if discounted else regular
                            results[region] = PriceInfo(
                                region=region,
                                price=str(price_val),
                                currency=currency,
                                status="available",
                                nsuid=sku
                            )
                        else:
                            results[region] = PriceInfo(
                                region=region,
                                status="blocked",
                                nsuid=sku,
                                error="Нет данных"
                            )
                    else:
                        print(f"❌ [{region}] SKU/NSUID не найден для: {game_name}")
                        results[region] = PriceInfo(
                            region=region,
                            status="not_found",
                            error="Игра не найдена"
                        )
        
        # Стратегия 2: RU/PL - попытка через европейский NSUID
        if any(r in regions for r in ru_pl_regions):
            print(f"🔍 Поиск европейского NSUID для: {game_name}")
            european_games = await self.search_games_european(game_name)
            
            if european_games:
                eu_game = european_games[0]  # Берем первую найденную игру
                eu_nsuid = eu_game.nsuid
                print(f"✅ Найден EU NSUID: {eu_nsuid} для игры: {eu_game.title}")
                
                for region in ru_pl_regions:
                    if region in regions:
                        price, currency = await self.get_price_by_nsuid_rest(eu_nsuid, region)
                        if price:
                            results[region] = PriceInfo(
                                region=region,
                                price=price,
                                currency=currency,
                                status="available",
                                nsuid=eu_nsuid
                            )
                        else:
                            results[region] = PriceInfo(
                                region=region,
                                status="blocked",
                                nsuid=eu_nsuid,
                                error="Регион заблокирован"
                            )
            else:
                print(f"❌ Европейский NSUID не найден для: {game_name}")
                for region in ru_pl_regions:
                    if region in regions:
                        results[region] = PriceInfo(
                            region=region,
                            status="not_found",
                            error="Игра не найдена"
                        )
        
        # Стратегия 3: Остальные регионы - блокировка
        for region in other_regions:
            results[region] = PriceInfo(
                region=region,
                status="blocked",
                error="Регион не поддерживается"
            )
        
        return results
    
    def format_price_display(self, price_info: PriceInfo) -> str:
        """Форматирование цены для отображения"""
        if price_info.status == "available" and price_info.price:
            if price_info.currency == "USD":
                return f"${price_info.price}"
            elif price_info.currency == "BRL":
                return f"R$ {price_info.price}"
            elif price_info.currency == "ARS":
                return f"AR$ {price_info.price}"
            elif price_info.currency == "RUB":
                return f"₽ {price_info.price}"
            elif price_info.currency == "PLN":
                return f"zł {price_info.price}"
            else:
                return f"{price_info.price} {price_info.currency}"
        elif price_info.status == "blocked":
            return "🔒"
        elif price_info.status == "no_price":
            return "❌"
        else:
            return "❓"


async def main():
    """Основная функция для тестирования"""
    # Тестовые игры
    test_games = [
        "Super Mario Odyssey",
        "The Legend of Zelda: Breath of the Wild",
        "Animal Crossing: New Horizons",
        "Mario Kart 8 Deluxe"
    ]
    
    # Регионы для тестирования
    test_regions = ["US", "BR", "AR", "RU", "PL", "TR", "KZ", "UA", "IN", "DE"]
    
    async with NintendoPriceDebugger() as debugger:
        for game in test_games:
            print(f"\n{'='*60}")
            print(f"🎮 ИГРА: {game}")
            print(f"{'='*60}")
            
            results = await debugger.get_game_prices(game, test_regions)
            
            # Выводим результаты в виде таблицы
            print(f"{'Регион':<4} {'Цена':<15} {'Статус':<12} {'NSUID':<20} {'Ошибка':<30}")
            print("-" * 90)
            
            for region in test_regions:
                if region in results:
                    price_info = results[region]
                    price_display = debugger.format_price_display(price_info)
                    nsuid_display = price_info.nsuid or "N/A"
                    error_display = price_info.error or "N/A"
                    
                    print(f"{region:<4} {price_display:<15} {price_info.status:<12} {nsuid_display:<20} {error_display:<30}")
            
            print(f"\n⏱️  Время: {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*60}")


if __name__ == "__main__":
    print("🚀 Запуск debug-скрипта для тестирования цен Nintendo Switch")
    print("📋 Тестируем стратегии получения цен по регионам...")
    
    asyncio.run(main())

    # --- Автоматический тест по NSUID и регионам ---
    print("\n=== Автотест: получение цен по NSUID ===")
    nsuid = "70010000000963"  # Super Mario Odyssey US
    regions = ["US", "BR", "AR", "PL", "RU"]

    async def auto_price_test(nsuid, regions):
        async with aiohttp.ClientSession() as session:
            print(f"\nNSUID: {nsuid}")
            print(f"{'Регион':<4} {'Цена':<15} {'Статус':<12}")
            print("-" * 40)
            for region in regions:
                url = f"https://api.ec.nintendo.com/v1/price?country={region}&ids={nsuid}&lang=en"
                try:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            prices = data.get("prices", [])
                            if prices and prices[0].get("sales_status") == "onsale":
                                price_info = prices[0]
                                price = price_info["regular_price"]["amount"]
                                currency = price_info["regular_price"]["currency"]
                                print(f"{region:<4} {price} {currency:<10} available   ")
                            else:
                                print(f"{region:<4} ---           not available")
                        else:
                            print(f"{region:<4} ---           HTTP {resp.status}")
                except Exception as e:
                    print(f"{region:<4} ---           Ошибка: {e}")
    
    asyncio.run(auto_price_test(nsuid, regions)) 