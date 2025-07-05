from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def create_media_choice_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сайты", callback_data="media_choice:sites")],
        [InlineKeyboardButton(text="Telegram-каналы", callback_data="media_choice:channels")],
        [InlineKeyboardButton(text="VK-Сообщества", callback_data="media_choice:communities")],
        [InlineKeyboardButton(text="Вернуться в Меню", callback_data="main_menu")] 
    ])
    return keyboard

def create_sites_choice_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Kotaku", callback_data="site_choice:kotaku")],
        [InlineKeyboardButton(text="Gamesradar", callback_data="site_choice:gamesradar")],
        [InlineKeyboardButton(text="Polygon", callback_data="site_choice:polygon")],
        [InlineKeyboardButton(text="IXbt", callback_data="site_choice:ixbt")],
        [InlineKeyboardButton(text="Rock Paper Shotgun", callback_data="site_choice:rockpapershotgun")],
        [InlineKeyboardButton(text="Gamespot", callback_data="site_choice:gamespot")],
        [InlineKeyboardButton(text="Назад", callback_data="media_choice:back")]
    ])
    return keyboard

def create_channels_choice_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Fodder's Games", callback_data="channel_choice:fodders_games")],
        [InlineKeyboardButton(text="КБ.Игры", callback_data="channel_choice:kb_games")],
        [InlineKeyboardButton(text="Nerds", callback_data="channel_choice:nerds")],
        [InlineKeyboardButton(text="Назад", callback_data="media_choice:back")]
    ])
    return keyboard

def create_communities_choice_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Fodder's Island", callback_data="communitie_choice:fodders_island")],
        [InlineKeyboardButton(text="Чисто Поиграть", callback_data="communitie_choice:chistopoigrat")],
        [InlineKeyboardButton(text="GamingDeals - аукцион", callback_data="communitie_choice:gaming_deals")],
        [InlineKeyboardButton(text="DENDY FOREVER!", callback_data="communitie_choice:dendyforever")],
        [InlineKeyboardButton(text="RetroTech Squad", callback_data="communitie_choice:retrotechsquad")],
        [InlineKeyboardButton(text="Назад", callback_data="media_choice:back")]
    ])
    return keyboard