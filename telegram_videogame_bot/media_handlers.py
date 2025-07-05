from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from aiogram.types import InputMediaPhoto

import media_keyboards
import media_func
import base_handlers  

class MediaChoice(StatesGroup):
    choosing_media = State()

async def cmd_media(message: types.Message, state: FSMContext):
    keyboard = media_keyboards.create_media_choice_keyboard()
    try:
        if isinstance(message, types.Message):
            await message.answer("Выберите категорию медиа ресурсов:", reply_markup=keyboard)
            await state.set_state(MediaChoice.choosing_media)
        elif isinstance(message, types.CallbackQuery):
            await message.message.edit_text("Выберите категорию медиа ресурсов:", reply_markup=keyboard)
            await state.set_state(MediaChoice.choosing_media)
    except Exception as e:
        print(f"Ошибка при обработке колбэк-запроса: {e}")

async def process_choice_media(callback_query: types.CallbackQuery, state: FSMContext):
    media = callback_query.data.split(':')[1]
    await state.update_data(media=media)

    if media == "sites":
        keyboard = media_keyboards.create_sites_choice_keyboard()
        await callback_query.message.edit_text("Выберите подходящий сайт:", reply_markup=keyboard)
    elif media == "channels":
        keyboard = media_keyboards.create_channels_choice_keyboard()
        await callback_query.message.edit_text("Выберите подходящий канал:", reply_markup=keyboard)
    elif media == "communities":
        keyboard = media_keyboards.create_communities_choice_keyboard()
        await callback_query.message.edit_text("Выберите подходящее VK-Сообщество", reply_markup=keyboard)
    elif media == "back":
        keyboard = media_keyboards.create_media_choice_keyboard()
        await callback_query.message.edit_text("Выберите категорию медиа ресурсов:", reply_markup=keyboard)
    elif media == "main_menu":
        await base_handlers.cmd_main_menu(callback_query.message)

import media_func  # Убедитесь, что импортируете media_func для доступа к функциям парсинга
from aiogram import types
from aiogram.types import InputMediaPhoto
import media_keyboards

async def process_site_choice(callback_query: types.CallbackQuery):
    # Удаление исходного сообщения
    await callback_query.bot.delete_message(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id
    )

    site = callback_query.data.split(':')[1]
    site_url = get_site_url(site)
    text_intro = f"Последние новости: ⤴️\n\nВот ссылка на сайт {site}: {site_url}\n"

    news_functions = {
        'kotaku': media_func.news_kotaku,
        'gamesradar': media_func.news_gamesradar,
        'polygon': media_func.news_polygon,
        'ixbt' : media_func.news_ixbt,
        'rockpapershotgun' : media_func.news_rockpapershotgun,
        'gamespot' : media_func.news_gamespot
    }

    keyboard = media_keyboards.create_sites_choice_keyboard()  # Добавляем клавиатуру с кнопкой "Назад"
    
    if site in news_functions:
        news_items = news_functions[site]()
        media_group = []
        if news_items:
            for title, link, image_url in news_items:
                if image_url and len(image_url) <= 1024:  # Проверяем длину URL изображения
                    text = f"<b>{title}</b>\n<a href='{link}'>Ссылка</a>"
                    media_group.append(InputMediaPhoto(media=image_url, caption=text, parse_mode='HTML'))
            if media_group:
                await callback_query.message.answer_media_group(media_group)
                await callback_query.message.answer(text_intro, parse_mode='HTML', reply_markup=keyboard)
            else:
                await callback_query.message.answer(text_intro + "Не удалось загрузить изображения новостей.", parse_mode='HTML', reply_markup=keyboard)
        else:
            await callback_query.message.answer(text_intro + "Не найдено новостей.", reply_markup=keyboard)
    else:
        await callback_query.message.answer(f"{text_intro}Новости для этого сайта не поддерживаются.", parse_mode='HTML', reply_markup=keyboard)

async def process_channel_choice(callback_query: types.CallbackQuery):
    channel = callback_query.data.split(':')[1]
    channel_url = get_channel_url(channel)
    keyboard = media_keyboards.create_channels_choice_keyboard()  # Добавляем клавиатуру с кнопкой "Назад"
    await callback_query.message.edit_text(f"Вот ссылка на канал {channel}: {channel_url}", reply_markup=keyboard)

async def process_communitie_choise(callback_query: types.CallbackQuery):
    communitie = callback_query.data.split(':')[1]
    communitie_url = get_communities_url(communitie)
    keyboard = media_keyboards.create_communities_choice_keyboard()  # Добавляем клавиатуру с кнопкой "Назад"
    await callback_query.message.edit_text(f"Вот ссылка на сообщество VK {communitie}: {communitie_url}", reply_markup=keyboard)

def get_site_url(site):
    site_urls = {
        "kotaku": "https://kotaku.com",
        "gamesradar": "https://www.gamesradar.com",
        "polygon": "https://www.polygon.com",
        "ixbt": "https://www.ixbt.games",
        "rockpapershotgun": "https://www.rockpapershotgun.com",
        "gamespot": "https://www.gamespot.com"
    }
    return site_urls.get(site, "Ссылка не найдена")

def get_channel_url(channel):
    channel_urls = {
        "fodders_games": "https://t.me/foddersgames",
        "kb_games": "https://t.me/cb_games",
        "nerds": "https://t.me/nerdsmedia"
    }
    return channel_urls.get(channel, "Ссылка не найдена")

def get_communities_url(communities):
    communities_url = {
        "fodders_island": "https://vk.com/fodders_island",
        "chistopoigrat": "https://vk.com/chistopoigrat",
        "gaming_deals": "https://vk.com/gaming_deals",
        "dendyforever": "https://vk.com/dendyforever",
        "retrotechsquad": "https://vk.com/retrotechsquad",
    }
    return communities_url.get(communities, "Ссылка не найдена")