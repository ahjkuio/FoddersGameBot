from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest  # Добавьте правильный импорт

import store_keyboards as kb
import store_func as sf

class SteamStates(StatesGroup):
    search_query = State()

async def cmd_stores(message: types.Message, state: FSMContext):
    try:
        if isinstance(message, types.Message):
            await message.answer("Выберите цифровой магазин:", reply_markup=kb.get_stores_keyboard())
        elif isinstance(message, types.CallbackQuery):
            await message.message.edit_text("Выберите цифровой магазин:", reply_markup=kb.get_stores_keyboard())
    except Exception as e:
        print(f"Ошибка при обработке колбэк-запроса: {e}")

async def process_store_choice(callback_query: types.CallbackQuery, state: FSMContext):
    store = callback_query.data.split(":")[1]
    await state.update_data(store=store, page=1)
    
    if store == "steam":
        await callback_query.message.edit_text("Выберите опцию для Steam:", reply_markup=kb.get_steam_options_keyboard())
    elif store == "back":
        keyboard = kb.get_stores_keyboard()
        await callback_query.message.edit_text("Выберите цифровой магазин:", reply_markup=keyboard)


async def process_steam_option(callback_query: types.CallbackQuery, state: FSMContext):
    option = callback_query.data.split(":")[1]
    await state.update_data(option=option, page=1)

    if option == "search":
        await callback_query.message.edit_text("Введите ключевое слово для поиска игр в Steam:")
        await state.set_state(SteamStates.search_query)
    elif option == "popular":
        games, total_games = await sf.get_popular_games(page=1, page_size=5)
        await show_games(callback_query.message, games, state, total_games, page_size=5)
    elif option == "discounts":
        await callback_query.message.edit_text("Выберите вариант сортировки игр со скидкой:", reply_markup=kb.get_sort_options_keyboard())

async def process_sort_option(callback_query: types.CallbackQuery, state: FSMContext):
    sort_option = callback_query.data.split(":")[1]
    await state.update_data(sort_option=sort_option, page=1)
    games, total_games = await sf.get_discounted_games(sort_option, page=1, page_size=5)
    await show_games(callback_query.message, games, state, total_games, page_size=5)

async def process_search_query(message: types.Message, state: FSMContext):
    query = message.text
    await state.update_data(query=query, page=1)
    games, total_games = await sf.search_games(query, page=1, page_size=5)

    if not games:
        await message.answer("Игры не найдены.")
    else:
        await show_games(message, games, state, total_games, page_size=5)

async def show_games(message: types.Message, games, state: FSMContext, total_games, page_size=5):
    data = await state.get_data()
    page = data.get("page", 1)
    start_index = (page - 1) * page_size + 1

    # Фильтрация игр без необходимой информации
    games = [game for game in games if game.get('name') and game.get('url')]

    if not games:
        await message.answer("Игры не найдены.")
    else:
        # Убедиться, что всегда выводится ровно 5 игр
        games_to_display = games[:page_size]
        game_list = [
            f"[{i+1}] {start_index+i}. {game['name']} ({game['release_date']})\nРейтинг: {game['rating']}\nЦена: {game['price']} - [Ссылка]({game['url']})"
            for i, game in enumerate(games_to_display)
        ]

        message_text = "\n\n".join(game_list)

        keyboard_markup = kb.get_games_page_keyboard(page, total_games, page_size)
        keyboard_markup.inline_keyboard.extend(kb.get_game_buttons(games_to_display, page, page_size))

        try:
            await message.edit_text(message_text, parse_mode='MARKDOWN', reply_markup=keyboard_markup)
        except TelegramBadRequest as e:
            if "message can't be edited" in str(e):
                await message.answer(message_text, parse_mode='MARKDOWN', reply_markup=keyboard_markup)
            else:
                raise

async def process_page(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page_data = callback_query.data.split(":")[1]

    if page_data == "current":
        page = data.get("page", 1)
    else:
        page = int(page_data)

    store = data.get("store")
    option = data.get("option")
    query = data.get("query")
    sort_option = data.get("sort_option")

    if store == "steam":
        if option == "popular":
            games, total_games = await sf.get_popular_games(page, page_size=5)
        elif option == "discounts":
            games, total_games = await sf.get_discounted_games(sort_option, page, page_size=5)
        elif option == "search" and query:
            games, total_games = await sf.search_games(query, page, page_size=5)

    await state.update_data(page=page)
    await show_games(callback_query.message, games, state, total_games, page_size=5)

async def process_game_info(callback_query: types.CallbackQuery, state: FSMContext):
    game_id = int(callback_query.data.split(":")[1])
    game_data = await sf.get_app_details(game_id)
    if not game_data:
        await callback_query.message.answer("Информация об игре не найдена.")
        return

    game_details = (
        f"**{game_data['name']}**\n\n"
        f"**Описание:**\n{game_data.get('short_description', 'N/A')}\n\n"
        f"**Цена:** {game_data.get('price_overview', {}).get('final_formatted', 'N/A')}\n"
        f"**Рейтинг:** {game_data.get('metacritic', {}).get('score', 'N/A')}\n"
        f"**Дата выхода:** {game_data.get('release_date', {}).get('date', 'N/A')}\n"
        f"**Ссылка:** [Steam Page]({game_data['url']})"
    )

    data = await state.get_data()
    favorites = data.get('favorites', set())
    notifications = data.get('notifications', set())

    in_favorites = game_id in favorites
    notifications_enabled = game_id in notifications

    await callback_query.message.edit_text(
        game_details,
        parse_mode='MARKDOWN',
        reply_markup=kb.get_game_details_keyboard(game_id, in_favorites, notifications_enabled)
    )

async def toggle_favorite(callback_query: types.CallbackQuery, state: FSMContext):
    game_id = int(callback_query.data.split(":")[1])
    data = await state.get_data()
    favorites = data.get('favorites', set())

    if game_id in favorites:
        favorites.remove(game_id)
        in_favorites = False
    else:
        favorites.add(game_id)
        in_favorites = True

    await state.update_data(favorites=favorites)

    button_text = "Убрать из избранного" if in_favorites else "Добавить в избранное"
    keyboard = callback_query.message.reply_markup
    for button_row in keyboard.inline_keyboard:
        for button in button_row:
            if button.callback_data == f"toggle_favorite:{game_id}":
                button.text = button_text
                break

    await callback_query.message.edit_reply_markup(reply_markup=keyboard)

async def toggle_notifications(callback_query: types.CallbackQuery, state: FSMContext):
    game_id = int(callback_query.data.split(":")[1])
    data = await state.get_data()
    notifications = data.get('notifications', set())

    if game_id in notifications:
        notifications.remove(game_id)
        notifications_enabled = False
    else:
        notifications.add(game_id)
        notifications_enabled = True

    await state.update_data(notifications=notifications)

    button_text = "Выкл. увед. о скидках" if notifications_enabled else "Вкл. увед. о скидках"
    keyboard = callback_query.message.reply_markup
    for button_row in keyboard.inline_keyboard:
        for button in button_row:
            if button.callback_data == f"toggle_notifications:{game_id}":
                button.text = button_text
                break

    await callback_query.message.edit_reply_markup(reply_markup=keyboard)