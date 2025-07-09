from __future__ import annotations

import asyncio
import re
from typing import List, Tuple
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from loguru import logger
from playwright.async_api import async_playwright

# --- EA Store Constants ---
BASE_URL = "https://www.ea.com"
SEARCH_URL_TPL = "https://www.ea.com/en-us/games/library?search={query}"

REGION_MAP = {"RU": "ru-ru", "US": "en-us", "TR": "tr-tr", "BR": "pt-br", "AR": "es-ar"}
LANGUAGE_MAP = {"RU": "ru-RU", "US": "en-US", "TR": "tr-TR", "BR": "pt-BR", "AR": "es-AR"}


async def search_games(query: str, region: str = "US") -> List[Tuple[str, str, str]]:
    """
    Ищет игры на сайте EA и возвращает список совпадений с помощью Playwright.
    Возвращает список кортежей (game_id, title, store_page_url).
    """
    results = []
    search_url = SEARCH_URL_TPL.format(query=query)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            logger.info(f"EA Playwright: Navigating to search URL {search_url}")
            await page.goto(search_url, wait_until="load", timeout=30000)

            search_results_selector = 'div[data-testid="search-results-grid"]'
            card_selector = 'div[data-testid="game-card"]'

            try:
                await page.wait_for_selector(search_results_selector, timeout=15000)
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                game_grid = soup.find("div", attrs={"data-testid": "search-results-grid"})
                if not game_grid:
                    logger.warning(f"EA Playwright search could not find results grid for '{query}'.")
                    await browser.close()
                    return []
                
                game_cards = game_grid.find_all("div", attrs={"data-testid": "game-card"})

                if not game_cards:
                    logger.warning(f"EA Playwright search found no game cards for '{query}'.")

                for card in game_cards:
                    title_tag = card.find("h3", attrs={"data-testid": "game-title"})
                    link_tag = card.find("a")

                    if title_tag and link_tag and link_tag.has_attr("href"):
                        title = title_tag.text.strip()
                        href = link_tag["href"]
                        page_url = urljoin(BASE_URL, href)

                        path_parts = [part for part in href.split("/") if part]
                        if len(path_parts) >= 3 and path_parts[0] == 'games':
                            game_id = "/".join(path_parts[1:])
                            results.append((game_id, title, page_url))
                            logger.info(f"Found game on EA via Playwright: {title} ({game_id})")

            except asyncio.TimeoutError:
                logger.warning(f"EA Playwright: Timed out waiting for search results on {search_url}")
            except Exception as e:
                logger.error(f"EA Playwright: Error parsing search results on {search_url}: {e}")

            await browser.close()

    except Exception as e:
        logger.error(f"An error occurred during Playwright search execution for '{query}': {e}")

    if not results:
        logger.warning(f"EA search_games for '{query}' found no results.")

    return results


async def get_offers(game_id: str, region: str = "US") -> List[Tuple[str, float, str, str]]:
    """
    Получает цену для конкретной игры, парся ее страницу с помощью Playwright.
    Возвращает список кортежей (store_name, price, currency, url).
    """
    locale = REGION_MAP.get(region, "en-us")
    lang = LANGUAGE_MAP.get(region, "en-US")
    
    # game_id здесь это что-то вроде 'crysis/crysis'
    game_url = f"{BASE_URL}/{locale}/games/{game_id}"
    
    results = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(locale=lang)
            
            logger.info(f"EA Playwright: Navigating to {game_url}")
            await page.goto(game_url, wait_until="load", timeout=30000)

            # Ищем блок с ценой. Селектор может потребовать уточнения.
            # Пример: <span class="price-info">...</span> или что-то похожее.
            # Мы будем искать элемент, содержащий символ валюты или число.
            # Это более общий подход.
            price_selector = 'h2:has-text("$"), h2:has-text("₽"), h2:has-text("₺"), h3:has-text("$"), h3:has-text("₽"), h3:has-text("₺")'

            try:
                await page.wait_for_selector(price_selector, timeout=15000)
                price_element = await page.query_selector(price_selector)
                price_text = await price_element.inner_text() if price_element else "N/A"

                logger.info(f"EA Playwright: Found price text for '{game_id}' in {region}: '{price_text}'")

                # Извлекаем число и валюту
                price_match = re.search(r'([\d,.]+)', price_text)
                if price_match:
                    price_str = price_match.group(1).replace(",", "")
                    price = float(price_str)
                    
                    currency = "USD" # Default
                    if "₽" in price_text:
                        currency = "RUB"
                    elif "₺" in price_text:
                        currency = "TRY"
                    elif "$" in price_text:
                        currency = "USD"
                    # Добавить другие валюты по необходимости

                    results.append(("origin", price, currency, game_url))
                else:
                    logger.warning(f"Could not parse price from '{price_text}' for {game_id} in {region}")

            except asyncio.TimeoutError:
                logger.warning(f"EA Playwright: Timed out waiting for price element on {game_url}")
            except Exception as e:
                logger.error(f"EA Playwright: Error parsing price on {game_url}: {e}")

            await browser.close()

    except Exception as e:
        logger.error(f"An error occurred during Playwright execution for {game_id} in {region}: {e}")

    if not results:
        logger.warning(f"EA get_offers for '{game_id}' in {region} found no offers.")
        
    return results 