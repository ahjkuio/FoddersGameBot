from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def games_keyboard(games):
    # games = list[(id,name)]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"price_game:{gid}")]
        for gid, name in games
    ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Назад", callback_data="price_back")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🏠 Меню", callback_data="price_cancel")])
    return kb


def offers_keyboard(game_id):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Назад", callback_data="price_back")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="price_cancel")]
    ])
    return kb


def cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Меню", callback_data="price_cancel")]
    ])


# ---------- Платформы / Регионы ----------

PLATFORMS = [
    ("pc", "ПК"),
    ("ps4", "PlayStation 4"),
    ("ps5", "PlayStation 5"),
    ("xbox_one", "Xbox One"),
    ("xbox_series", "Xbox Series S|X"),
    ("switch", "Switch"),
    ("switch2", "Switch 2"),
]

REGIONS = [
    ("RU", "🇷🇺 Россия"),
    ("TR", "��🇷 Турция"),
    ("AR", "🇦🇷 Аргентина"),
    ("BR", "🇧�� Бразилия"),
    ("US", "🇺🇸 США"),
]


def platforms_keyboard(selected: set[str]):
    """Клавиатура множественного выбора платформ."""

    rows = []
    for code, title in PLATFORMS:
        prefix = "✅ " if code in selected else ""
        rows.append([InlineKeyboardButton(text=prefix + title, callback_data=f"plat_toggle:{code}")])

    # подтверждение выбора
    rows.append([InlineKeyboardButton(text="✔️ Готово", callback_data="plat_ok")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    return kb


def regions_keyboard():
    rows = []
    for code, title in REGIONS:
        rows.append([InlineKeyboardButton(text=title, callback_data=f"region:{code}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    return kb 