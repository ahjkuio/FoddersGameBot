from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_stores_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Steam", callback_data="store:steam")],
        [InlineKeyboardButton(text="Epic Games", callback_data="store:epic")],
        [InlineKeyboardButton(text="Xbox", callback_data="store:xbox")],
        [InlineKeyboardButton(text="PlayStation", callback_data="store:ps")],
        [InlineKeyboardButton(text="Вернуться в Меню", callback_data="main_menu")]
    ])
    return keyboard

def get_steam_options_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Поиск по ключевому слову", callback_data="steam:search")],
        [InlineKeyboardButton(text="Популярные игры", callback_data="steam:popular")],
        [InlineKeyboardButton(text="Игры со скидкой", callback_data="steam:discounts")],
        [InlineKeyboardButton(text="Назад", callback_data="store:back")]
    ])
    return keyboard

def get_sort_options_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Высокий рейтинг", callback_data="sort:rating")],
        [InlineKeyboardButton(text="Сначала дешевые", callback_data="sort:price_asc")],
        [InlineKeyboardButton(text="Новинки", callback_data="sort:new")],
        [InlineKeyboardButton(text="По размеру скидки", callback_data="sort:discount")],
        [InlineKeyboardButton(text="Назад", callback_data="store:back")]
    ])
    return keyboard

def get_game_details_keyboard(game_id, in_favorites=False, notifications_enabled=False):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться к списку", callback_data="page:current")],
        [InlineKeyboardButton(
            text="Убрать из избранного" if in_favorites else "Добавить в избранное",
            callback_data=f"toggle_favorite:{game_id}"
        )],
        [InlineKeyboardButton(
            text="Выкл. увед. о скидках" if notifications_enabled else "Вкл. увед. о скидках",
            callback_data=f"toggle_notifications:{game_id}"
        )]
    ])
    return keyboard

def get_games_page_keyboard(page, total_games, page_size=5):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    # Добавляем кнопку "Назад" в самый верх
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="Назад", callback_data="store:back")])

    # Кнопки для навигации по страницам
    if page > 1:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"page:{page - 1}")])

    keyboard.inline_keyboard.append([InlineKeyboardButton(text=f"Стр. {page}", callback_data="page:current")])

    if page * page_size < total_games:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="След. ➡️", callback_data=f"page:{page + 1}")])

    return keyboard

def get_game_buttons(games, page, page_size=5):
    start_index = (page - 1) * page_size + 1
    buttons = [
    InlineKeyboardButton(text=f"{i+1}", callback_data=f"game_info:{game['steam_appid']}")
    for i, game in enumerate(games)

] 
    return [buttons]  # Возвращаем в