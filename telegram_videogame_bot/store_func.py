import aiohttp
import asyncio
import logging
from config import STEAM_API_KEY

logger = logging.getLogger(__name__)

async def get_app_details(app_id, retries=3, timeout=20):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=russian"
    for attempt in range(retries):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    if data and str(app_id) in data and data[str(app_id)]['success']:
                        app_data = data[str(app_id)]['data']
                        app_data['url'] = f"https://store.steampowered.com/app/{app_id}"
                        
                        # Проверка наличия русского описания
                        description = app_data.get('short_description', '')
                        if not description:
                            # Если русского описания нет
                            fallback_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=english"
                            async with session.get(fallback_url) as fallback_response:
                                fallback_response.raise_for_status()
                                fallback_data = await fallback_response.json()
                                if fallback_data and str(app_id) in fallback_data and fallback_data[str(app_id)]['success']:
                                    fallback_app_data = fallback_data[str(app_id)]['data']
                                    description = fallback_app_data.get('short_description', '')
                                    description += "\n\n*Русского описания нет*"

                        app_data['short_description'] = description
                        return app_data
                    else:
                        logger.error(f"Не удалось получить данные для app_id={app_id}: {data}")
                        return None
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Ошибка при запросе к {url}: {e}")
                if attempt == retries - 1:
                    return None
                logger.info(f"Повторная попытка {attempt + 1} из {retries}")

async def search_games(query, page, page_size=5, retries=3, timeout=20):
    url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
    logger.info(f"Поиск игр по запросу: {query}")

    for attempt in range(retries):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    logger.info(f"Получено данных: {len(data.get('applist', {}).get('apps', []))} игр")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Ошибка при запросе к {url}: {e}")
                if attempt == retries - 1:
                    return [], 0
                logger.info(f"Повторная попытка {attempt + 1} из {retries}")
                continue
            break

    games_matching_query = [game for game in data['applist']['apps'] if query.lower() in game['name'].lower()]
    logger.info(f"Найдено {len(games_matching_query)} игр по запросу: {query}")

    selected_games = games_matching_query[(page - 1) * page_size:page * page_size]

    games = []
    for game in selected_games:
        app_id = game['appid']
        try:
            game_data = await get_app_details(app_id)
            if game_data:
                game_info = {
                    'name': game_data['name'],
                    'price': game_data.get('price_overview', {}).get('final_formatted', 'N/A'),
                    'rating': game_data.get('metacritic', {}).get('score', 'N/A'),
                    'steam_appid': app_id,
                    'release_date': game_data.get('release_date', {}).get('date', 'N/A'),
                    'url': f"https://store.steampowered.com/app/{app_id}"
                }
                games.append(game_info)
        except Exception as e:
            logger.error(f"Ошибка при получении данных для игры с app_id={app_id}: {e}")

    logger.info(f"Возвращено игр: {len(games)}")
    return games, len(games_matching_query)

async def get_popular_games(page, page_size=5, retries=3, timeout=20):
    url = f"https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/?key={STEAM_API_KEY}&format=json"
    for attempt in range(retries):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Ошибка при запросе к {url}: {e}")
                if attempt == retries - 1:
                    return [], 0
                logger.info(f"Повторная попытка {attempt + 1} из {retries}")
                continue
            break

    ranks = data['response']['ranks']
    total_games = len(ranks)

    start_index = (page - 1) * page_size
    end_index = min(start_index + page_size, total_games)
    selected_games = ranks[start_index:end_index]
    games = []

    for game in selected_games:
        app_id = game['appid']
        game_data = await get_app_details(app_id)
        if game_data:
            game_info = {
                'name': game_data['name'],
                'price': game_data.get('price_overview', {}).get('final_formatted', 'N/A'),
                'rating': game_data.get('metacritic', {}).get('score', 'N/A'),
                'steam_appid': app_id,
                'release_date': game_data.get('release_date', {}).get('date', 'N/A'),
                'url': f"https://store.steampowered.com/app/{app_id}"
            }
            games.append(game_info)

    return games, total_games

async def get_discounted_games(sort_option, page, page_size=5, retries=3, timeout=20):
    url = "https://store.steampowered.com/api/featuredcategories/"
    logger.info(f"Получение игр со скидками, сортировка: {sort_option}, страница: {page}")

    for attempt in range(retries):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    discounts = data.get('specials', {}).get('items', [])
                    logger.info(f"Получено данных: {len(discounts)} игр со скидками")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Ошибка при запросе к {url}: {e}")
                if attempt == retries - 1:
                    return [], 0
                logger.info(f"Повторная попытка {attempt + 1} из {retries}")
                continue
            break

    # Сортировка данных
    if sort_option == "rating":
        discounts.sort(key=lambda x: x.get('metacritic', {}).get('score', 0), reverse=True)
    elif sort_option == "price_asc":
        discounts.sort(key=lambda x: x.get('price_overview', {}).get('final', float('inf')))
    elif sort_option == "new":
        discounts.sort(key=lambda x: x.get('release_date', ''), reverse=True)
    elif sort_option == "discount":
        discounts.sort(key=lambda x: x.get('discount_percent', 0), reverse=True)

    total_games = len(discounts)
    selected_games = discounts[(page - 1) * page_size:page * page_size]

    games = []
    for game in selected_games:
        app_id = game['id']
        try:
            game_data = await get_app_details(app_id)
            if game_data:
                game_info = {
                    'name': game_data['name'],
                    'price': game_data.get('price_overview', {}).get('final_formatted', 'N/A'),
                    'rating': game_data.get('metacritic', {}).get('score', 'N/A'),
                    'steam_appid': app_id,
                    'release_date': game_data.get('release_date', {}).get('date', 'N/A'),
                    'url': f"https://store.steampowered.com/app/{app_id}"
                }
                games.append(game_info)
        except Exception as e:
            logger.error(f"Ошибка при запросе к https://store.steampowered.com/api/appdetails?appids={app_id}&l=russian: {e}")

    logger.info(f"Возвращено игр: {len(games)}")
    return games, total_games

async def search_games(query, page, page_size=5, retries=3, timeout=20):
    url = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
    logger.info(f"Поиск игр по запросу: {query}")

    for attempt in range(retries):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json()
                    logger.info(f"Получено данных: {len(data.get('applist', {}).get('apps', []))} игр")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Ошибка при запросе к {url}: {e}")
                if attempt == retries - 1:
                    return [], 0
                logger.info(f"Повторная попытка {attempt + 1} из {retries}")
                continue
            break

    games_matching_query = [game for game in data['applist']['apps'] if query.lower() in game['name'].lower()]
    logger.info(f"Найдено {len(games_matching_query)} игр по запросу: {query}")

    selected_games = games_matching_query[(page - 1) * page_size:page * page_size]

    games = []
    for game in selected_games:
        app_id = game['appid']
        try:
            game_data = await get_app_details(app_id)
            if game_data:
                game_info = {
                    'name': game_data['name'],
                    'price': game_data.get('price_overview', {}).get('final_formatted', 'N/A'),
                    'rating': game_data.get('metacritic', {}).get('score', 'N/A'),
                    'steam_appid': app_id,
                    'release_date': game_data.get('release_date', {}).get('date', 'N/A'),
                    'url': f"https://store.steampowered.com/app/{app_id}"
                }
                games.append(game_info)
        except Exception as e:
            logger.error(f"Ошибка при получении данных для игры с app_id={app_id}: {e}")

    logger.info(f"Возвращено игр: {len(games)}")
    return games, len(games_matching_query)