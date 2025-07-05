from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def gender_keyboard():
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Мужской", callback_data="gender:male"),
            InlineKeyboardButton(text="Женский", callback_data="gender:female")
        ],
        [
            InlineKeyboardButton(text="Другой", callback_data="gender:custom")
        ]
    ])
    return markup

def edit_gender_keyboard():
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Мужской", callback_data="edit_gender:male"),
            InlineKeyboardButton(text="Женский", callback_data="edit_gender:female")
        ],
        [
            InlineKeyboardButton(text="Другой", callback_data="edit_gender:custom")
        ]
    ])
    return markup

def confirm_profile_keyboard():
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Подтвердить", callback_data="confirm_profile"),
            InlineKeyboardButton(text="Изменить", callback_data="edit_profile")
        ]
    ])
    return markup

def edit_profile_keyboard():
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Имя", callback_data="edit:name"),
            InlineKeyboardButton(text="Пол", callback_data="edit:gender")
        ],
        [
            InlineKeyboardButton(text="Возраст", callback_data="edit:age"),
            InlineKeyboardButton(text="Город", callback_data="edit:city")
        ],
        [
            InlineKeyboardButton(text="Фотографии", callback_data="edit:photos"),
            InlineKeyboardButton(text="Игры", callback_data="edit:games")
        ],
        [
            InlineKeyboardButton(text="Описание", callback_data="edit:description")
        ],
        [
            InlineKeyboardButton(text="Завершить", callback_data="confirm_profile")
        ]
    ])
    return markup

def personal_account_keyboard(display_status, preferred_gender):
    display_status_emoji = "✅" if display_status == "да" else "❌"
    gender_emoji = {
        "нейтральный": "⚪️",
        "женский": "🚺",
        "мужской": "🚹"
    }.get(preferred_gender, "⚪️")
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Отображать меня в GDate {display_status_emoji}", callback_data="toggle_display_status")],
        [InlineKeyboardButton(text="Изменить аккаунт", callback_data="edit_account")],
        [InlineKeyboardButton(text="Подписка/Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="Посмотреть мои GDate'ы", callback_data="view_gdates")],
        [InlineKeyboardButton(text=f"Отображать Гендер: {gender_emoji}", callback_data="toggle_preferred_gender")],
        [InlineKeyboardButton(text="Вернуться в Меню", callback_data="main_menu")]
    ])