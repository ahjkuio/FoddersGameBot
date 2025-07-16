import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from fuzzywuzzy import fuzz

logger = logging.getLogger(__name__)

EU_SEARCH_URL = "https://search.nintendo-europe.com/en/select"
PRICE_API_URL = "https://api.ec.nintendo.com/v1/price"

@dataclass
class NintendoGame:
    nsuid: str
    title: str
    platform: str
    image_url: Optional[str] = None

class NintendoEshopAPI:
    def __init__(self):
        self.regions = ["US", "TR", "BR", "AR", "IN", "KZ", "PL", "RU", "UA"]

    async def search_games(self, query: str, limit: int = 50) -> List[NintendoGame]:
        try:
            params = {
                "q": query,
                "rows": limit,
                "start": 0,
                "fq": "type:GAME",
                "wt": "json"
            }
            logger.info(f"Nintendo search_games: отправляем запрос к {EU_SEARCH_URL} с параметрами {params}")
            async with aiohttp.ClientSession() as session:
                async with session.get(EU_SEARCH_URL, params=params) as resp:
                    logger.info(f"Nintendo search_games: HTTP статус {resp.status}")
                    if resp.status != 200:
                        logger.error(f"Nintendo search_games: HTTP ошибка {resp.status}")
                        return []
                    data = await resp.json()
                    logger.info(f"Nintendo search_games: получен ответ, ключи: {list(data.keys())}")
                    docs = data.get("response", {}).get("docs", [])
                    logger.info(f"Nintendo search_games: найдено {len(docs)} документов")
                    games = []
                    for doc in docs:
                        nsuid_list = doc.get("nsuid_txt", [])
                        title = doc.get("title", "")
                        logger.info(f"Nintendo search_games: документ - title: '{title}', nsuid: {nsuid_list}")
                        if nsuid_list and nsuid_list[0]:
                            games.append(NintendoGame(
                                nsuid=nsuid_list[0],
                                title=title,
                                platform=doc.get("system_names_txt", [""])[0],
                                image_url=doc.get("image_url", None)
                            ))
                    logger.info(f"Nintendo search_games: возвращаем {len(games)} игр")
                    return games
        except Exception as e:
            logger.error(f"Nintendo search_games exception: {e}")
            import traceback; traceback.print_exc()
            return []

    async def get_prices(self, nsuid: str, regions: List[str]) -> Dict[str, dict]:
        results = {}
        async with aiohttp.ClientSession() as session:
            # Сначала пробуем все выбранные регионы
            for region in regions:
                url = f"{PRICE_API_URL}?country={region}&ids={nsuid}&lang=en"
                try:
                    async with session.get(url) as resp:
                        if resp.content_type != "application/json":
                            logger.error(f"Ошибка получения цены для {region}: mimetype={resp.content_type}, url={url}")
                            results[region] = None
                            continue
                        data = await resp.json()
                        logger.info(f"Nintendo get_prices: регион={region}, nsuid={nsuid}, ответ: {data}")
                        results[region] = data
                except Exception as e:
                    logger.error(f"Ошибка получения цены для {region}: {e}")
                    results[region] = None
            # Если ни для одного региона не получили цену — fallback на DE
            if all(v is None or not (isinstance(v, dict) and v.get("prices")) for v in results.values()):
                url = f"{PRICE_API_URL}?country=DE&ids={nsuid}&lang=en"
                try:
                    async with session.get(url) as resp:
                        if resp.content_type != "application/json":
                            logger.error(f"Fallback: mimetype={resp.content_type}, url={url}")
                            results["DE"] = None
                        else:
                            data = await resp.json()
                            logger.info(f"Nintendo get_prices: fallback DE, nsuid={nsuid}, ответ: {data}")
                            results["DE"] = data
                except Exception as e:
                    logger.error(f"Ошибка fallback DE: {e}")
                    results["DE"] = None
            return results

    def parse_price(self, price_data: dict, fallback_data: dict = None) -> Optional[dict]:
        if not price_data or not isinstance(price_data, dict):
            logger.warning("Nintendo parse_price: price_data is None или не dict")
            return None
        logger.info(f"Nintendo parse_price: price_data={price_data}, fallback_data={fallback_data}")
        prices = price_data.get("prices", [])
        if not prices or prices[0].get("sales_status") != "onsale":
            if fallback_data:
                prices = fallback_data.get("prices", [])
                logger.info(f"Nintendo parse_price: fallback prices={prices}")
                if not prices or prices[0].get("sales_status") != "onsale":
                    logger.warning("Nintendo parse_price: нет актуальных цен даже в fallback")
                    return None
            else:
                logger.warning("Nintendo parse_price: нет актуальных цен")
                return None
        price_info = prices[0]
        result = {
            "regular": price_info["regular_price"]["amount"],
            "currency": price_info["regular_price"]["currency"],
            "raw_value": price_info["regular_price"]["raw_value"],
            "discount": None,
            "discount_end": None,
            "nso": False
        }
        if price_info.get("discount_price"):
            result["discount"] = price_info["discount_price"]["amount"]
            result["discount_end"] = price_info["discount_price"].get("end_datetime")
        logger.info(f"Nintendo parse_price: возвращаем результат {result}")
        return result

nintendo_api = NintendoEshopAPI() 