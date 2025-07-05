from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

reply_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Меню"),
            KeyboardButton(text="Тех. Поддержка")
        ],
        [
            KeyboardButton(text="Личный Кабинет"),
            KeyboardButton(text="Настройки")
        ]
    ],
    resize_keyboard=True
)


inline_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📕Краткое содержание📕", callback_data="show_commands")],
    [InlineKeyboardButton(text="📃Игровые Mедиа📃", callback_data="choice_media")],
    [InlineKeyboardButton(text="🛍Магазины с играми🛍 (только Steam)", callback_data="choice_store")],
    [InlineKeyboardButton(text="👾Наша ДатаБаза Игр👾", callback_data="call_gmdata")],
    [InlineKeyboardButton(text="🎲GamingDate🎲", callback_data="call_gamingdate")],
    [InlineKeyboardButton(text="🦮Гид-Экскурсии по Играм🦮 !В разработке!", callback_data="choice_guide_game")],
    [InlineKeyboardButton(text="🔧Тех. поддержка🔧", callback_data="call_hotline")],
    [InlineKeyboardButton(text="✔️Подписка✔️ !В разработке!", callback_data="choice_sub")],
    [InlineKeyboardButton(text="🎴Личный Кабинет🎴", callback_data="personal_account")]
     ])

inline_main_menu_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Вернуться в Меню", callback_data="main_menu")]])

