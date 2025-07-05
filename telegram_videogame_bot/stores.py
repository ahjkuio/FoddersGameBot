from config import STEAM_API_KEY
import aiohttp
import requests

async def parse_steam(search_type, filters, page, page_size):
    base_url = "https://api.steampowered.com/path/to/endpoint"
    params = {
        'format': 'json',
        'page': page,
        'page_size': page_size
    }

    # Добавление фильтров в параметры запроса
    if search_type == 'sales':
        params['sale_filter'] = 'true'
    if 'price' in filters:
        params['sort_by'] = 'price'
    if 'rating' in filters:
        params['sort_by'] = 'rating'

    response = requests.get(base_url, params=params)
    response_data = response.json()

    # Предполагаем, что API возвращает данные игр в нужном формате
    games = [
        {
            'name': game['name'],
            'price': game.get('price', 'N/A'),
            'rating': game.get('rating', 'No rating'),
            'link': f"https://store.steampowered.com/app/{game['appid']}"
        }
        for game in response_data.get('games', [])
    ]

    return games

async def get_steam_games_on_sale(query, page, page_size):
    url = f"https://api.steampowered.com/ISteamApps/GetAppList/v2/?key={STEAM_API_KEY}&format=json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    games_matching_query = [game for game in data['applist']['apps'] if query.lower() in game['name'].lower()]
    selected_games = games_matching_query[(page - 1) * page_size:page * page_size]

    games_on_sale = []
    for game in selected_games:
        app_id = game['appid']
        game_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(game_url) as game_response:
                game_data = await game_response.json()

        if game_data is not None and str(app_id) in game_data and game_data[str(app_id)]['success']:
            price_overview = game_data[str(app_id)]['data'].get('price_overview')
            if price_overview:
                price = price_overview['final_formatted']
                store_url = f"https://store.steampowered.com/app/{app_id}"
                game_info = {
                    'name': game['name'],
                    'price': price,
                    'url': store_url
                }
                games_on_sale.append(game_info)

    return games_on_sale

async def get_epic_games_on_sale(query, page, page_size):
    # Здесь должен быть ваш код для получения игр со скидками в Epic Games Store
    return []