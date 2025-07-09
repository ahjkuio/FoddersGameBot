import math

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

GAMES_PER_PAGE = 15

def build_games_keyboard(game_groups: list, page: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура для выбора игры из найденных с пагинацией."""
    builder = InlineKeyboardBuilder()

    start_index = page * GAMES_PER_PAGE
    end_index = start_index + GAMES_PER_PAGE
    
    for i, game_group in enumerate(game_groups[start_index:end_index]):
        original_index = start_index + i
        builder.row(InlineKeyboardButton(text=game_group["title"], callback_data=f"price_game_{original_index}"))

    total_pages = math.ceil(len(game_groups) / GAMES_PER_PAGE)
    if total_pages > 1:
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton(text="« Назад", callback_data=f"price_page_{page - 1}"))
        pagination_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            pagination_buttons.append(InlineKeyboardButton(text="Вперёд »", callback_data=f"price_page_{page + 1}"))
        builder.row(*pagination_buttons)

    builder.row(InlineKeyboardButton(text="↩️ Назад в меню", callback_data="main_menu"))
    return builder.as_markup()

def back_to_games_list_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="↩️ Назад к списку", callback_data="back_to_games_list"))
    builder.row(InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"))
    return builder.as_markup()

def offers_keyboard(game_id_idx: str):
    return back_to_games_list_keyboard()

def cancel_keyboard():
    return InlineKeyboardBuilder().row(InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")).as_markup()

# --- Платформы и Регионы ---

PLATFORMS = [
    ("pc", "ПК"),
    ("ps5", "PlayStation 5"),
    ("ps4", "PlayStation 4"),
    ("xbox_series", "Xbox Series S|X"),
    ("xbox_one", "Xbox One"),
    ("switch", "Nintendo Switch"),
]

REGIONS = [
    ("RU", "🇷🇺 Россия"),
    ("TR", "🇹🇷 Турция"),
    ("AR", "🇦🇷 Аргентина"),
    ("BR", "🇧🇷 Бразилия"),
    ("US", "🇺🇸 США"),
]

def build_platform_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, title in PLATFORMS:
        prefix = "✅ " if code in selected else "☑️"
        builder.row(InlineKeyboardButton(text=f"{prefix} {title}", callback_data=f"plat_toggle:{code}"))

    if selected:
        builder.row(InlineKeyboardButton(text="✔️ Далее", callback_data="plat_ok"))
    builder.row(InlineKeyboardButton(text="↩️ Назад в меню", callback_data="main_menu"))
    return builder.as_markup()

def build_regions_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    row = []
    for code, title in REGIONS:
        prefix = "✅" if code in selected else "☑️"
        btn = InlineKeyboardButton(text=f"{prefix} {title}", callback_data=f"region_toggle:{code}")
        row.append(btn)
        if len(row) >= 2:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)

    if selected and len(selected) == len(REGIONS):
        builder.row(InlineKeyboardButton(text="❌ Снять всё", callback_data="region_select_all"))
    else:
        builder.row(InlineKeyboardButton(text="✅ Выделить всё", callback_data="region_select_all"))

    if selected:
        builder.row(InlineKeyboardButton(text="✔️ Далее", callback_data="region_ok"))

    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data="price_back"))
    return builder.as_markup() 