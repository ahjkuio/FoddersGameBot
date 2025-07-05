from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def gamingdate_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать поиск", callback_data="start_search")],
        [InlineKeyboardButton(text="Вернуться в меню", callback_data="main_menu")]
    ])

def search_navigation_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👾"), KeyboardButton(text="⏭️"), KeyboardButton(text="Хватит")]
        ], 
        resize_keyboard=True
    )

def likes_keyboard(likes, current_page, total_likes):
    buttons = []
    for index, like in enumerate(likes, start=1):
        buttons.append([InlineKeyboardButton(text=str(index), callback_data=f"view_like_{index + current_page * 6}")])

    navigation_buttons = []
    if current_page > 0:
        navigation_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"view_likes_{current_page - 1}"))
    if (current_page + 1) * 6 < total_likes:
        navigation_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"view_likes_{current_page + 1}"))

    if navigation_buttons:
        buttons.append(navigation_buttons)
    buttons.append([InlineKeyboardButton(text="Вернуться в Меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def like_action_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👾", callback_data="like_user")],
        [InlineKeyboardButton(text="🥱", callback_data="skip_user")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_likes")]
    ])

def back_to_likes_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_to_likes")]
    ])