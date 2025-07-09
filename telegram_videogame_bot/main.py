import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корневую папку проекта в sys.path
# Это нужно, чтобы работали абсолютные импорты из любой точки проекта
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from aiogram import types, Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import ContentType
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

# Импорт наших внутренних модулей
import base_handlers
import media_handlers
import hotline_handlers
import gmdata_handlers
import gamingdate_handlers
import personalAccount_handlers
import store_handlers
import utils
import config

from personalAccount_DB import init_db
from personalAccount_keyboards import (
    gender_keyboard, edit_gender_keyboard, personal_account_keyboard,
    confirm_profile_keyboard, edit_profile_keyboard
)
from gamingdate_handlers import register_handlers_gamingdate
import logging_config
from loguru import logger
from routers import base as base_router, media as media_router, hotline as hotline_router, gmdata as gmdata_router, store as store_router

# Настройка Loguru
logging_config.configure_logging()

# Инициализация бота и диспетчера
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(base_router.router)
dp.include_router(media_router.router)
dp.include_router(hotline_router.router)
dp.include_router(gmdata_router.router)
dp.include_router(store_router.router)

# Состояния личного кабинета
from aiogram.filters.state import State, StatesGroup

class PersonalAccount(StatesGroup):
    waiting_for_name = State()
    waiting_for_gender = State()
    waiting_for_custom_gender = State()
    waiting_for_age = State()
    waiting_for_city = State()
    waiting_for_photos = State()
    waiting_for_games = State()
    waiting_for_description = State()
    waiting_for_edit_choice = State()
    editing_name = State()
    editing_gender = State()
    editing_for_custom_gender = State()
    editing_age = State()
    editing_city = State()
    editing_photos = State()
    editing_games = State()
    editing_description = State()

# -------------------------------------
# Системные события
# -------------------------------------
@dp.startup()
async def on_startup():
    logger.info("Игровой Бот запущен и готов к работе!")
    await init_db()

# -------------------------------------
# Обёртки-проверки подписки
# -------------------------------------
async def check_start_command(message: types.Message, state: FSMContext):
    if await utils.check_subscription(message, bot):
        await personalAccount_handlers.personal_account_start(message, state)

async def check_main_menu_command(message: types.Message):
    if await utils.check_subscription(message, bot):
        await base_handlers.cmd_main_menu(message)

async def check_help_command(message: types.Message):
    if await utils.check_subscription(message, bot):
        await base_handlers.cmd_help(message)

async def check_media_command(message: types.Message, state: FSMContext):
    if await utils.check_subscription(message, bot):
        await media_handlers.cmd_media(message, state)

async def check_hotline_command(message: types.Message):
    if await utils.check_subscription(message, bot):
        await hotline_handlers.cmd_hotline(message)

async def check_store_command(message: types.Message, state: FSMContext):
    if await utils.check_subscription(message, bot):
        await store_handlers.cmd_stores(message, state)

async def check_gmdata_command(message: types.Message):
    if await utils.check_subscription(message, bot):
        await gmdata_handlers.cmd_gmdata(message)

async def check_gamingdate_command(message: types.Message):
    if await utils.check_subscription(message, bot):
        await gamingdate_handlers.cmd_gmdate(message)

async def check_lk_command(message: types.Message, state: FSMContext):
    if await utils.check_subscription(message, bot):
        await personalAccount_handlers.cmd_lk(message, state, bot)

# -------------------------------------
# Регистрация команд
# -------------------------------------

# dp.message.register(check_media_command, Command('media'))
# dp.message.register(check_hotline_command, Command('hotline'))
# dp.message.register(check_store_command, Command('stores'))
# dp.message.register(check_gmdata_command, Command('gmdata'))
dp.message.register(check_gamingdate_command, Command('gmdate'))
dp.message.register(check_lk_command, Command('lk'))

# Ярлыки «Быстрого меню»
from base_keyboards import reply_menu_keyboard

dp.message.register(check_main_menu_command, lambda m: m.text == "Меню")
# dp.message.register(check_hotline_command, lambda m: m.text == "Тех. Поддержка")
dp.message.register(check_lk_command, lambda m: m.text == "Личный Кабинет")
dp.message.register(check_help_command, lambda m: m.text == "Настройки")

# -------------------------------------
# Callback Query регистрации
# -------------------------------------

# dp.callback_query.register(base_handlers.cmd_help, lambda c: c.data == 'show_commands')
# dp.callback_query.register(media_handlers.cmd_media, lambda c: c.data == 'choice_media')
# dp.callback_query.register(hotline_handlers.cmd_hotline, lambda c: c.data == 'call_hotline')
# dp.callback_query.register(store_handlers.cmd_stores, lambda c: c.data == 'choice_store')
# dp.callback_query.register(gmdata_handlers.cmd_gmdata, lambda c: c.data == 'call_gmdata')
dp.callback_query.register(gamingdate_handlers.cmd_gmdate, lambda c: c.data == 'call_gamingdate')
# dp.callback_query.register(check_lk_command, lambda c: c.data == 'personal_account')
# dp.callback_query.register(base_handlers.cmd_main_menu, lambda c: c.data == 'main_menu')

# media

# dp.callback_query.register(media_handlers.process_choice_media, lambda c: c.data.startswith('media_choice:'))
# dp.callback_query.register(media_handlers.process_site_choice, lambda c: c.data.startswith('site_choice:'))
# dp.callback_query.register(media_handlers.process_channel_choice, lambda c: c.data.startswith('channel_choice:'))
# dp.callback_query.register(media_handlers.process_communitie_choise, lambda c: c.data.startswith('communitie_choice'))
# dp.callback_query.register(media_handlers.process_choice_media, lambda c: c.data == 'media_choice:back')

# store

# dp.callback_query.register(store_handlers.process_store_choice, lambda c: c.data.startswith('store:'))
# dp.callback_query.register(store_handlers.process_steam_option, lambda c: c.data.startswith('steam:'))
# dp.message.register(store_handlers.process_search_query, store_handlers.SteamStates.search_query)
# dp.callback_query.register(store_handlers.process_sort_option, lambda c: c.data.startswith('sort:'))
# dp.callback_query.register(store_handlers.process_store_choice, lambda c: c.data.startswith('store:back'))

# dp.callback_query.register(store_handlers.process_page, lambda c: c.data.startswith("page:"))
# dp.callback_query.register(store_handlers.process_game_info, lambda c: c.data.startswith("game_info:"))
# dp.callback_query.register(store_handlers.toggle_favorite, lambda c: c.data.startswith("toggle_favorite:"))
# dp.callback_query.register(store_handlers.toggle_notifications, lambda c: c.data.startswith("toggle_notifications:"))

# Регистрация обработчиков GamingDate
register_handlers_gamingdate(dp)

# -------------------------------------
# Точка входа
# -------------------------------------
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    logger.info("Запуск бота...")
    asyncio.run(main())
    