from aiogram import types
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from aiogram.exceptions import TelegramAPIError

from base_keyboards import (inline_menu_keyboard, reply_menu_keyboard, inline_main_menu_keyboard)
import stores

# Счетчк уникальных юзеров
users = set()

class SearchQuery(StatesGroup):
    waiting_for_query = State()

class StoreChoice(StatesGroup):
    choosing_search_option = State()

async def cmd_start(message: types.Message): #НЕ НУЖНА
    user_id = message.from_user.id
    if user_id not in users:
        users.add(user_id)
        print(f"Новый пользователь: {user_id}")
    else:
        print(f"Существующий пользователь: {user_id}")

    # Отправляем сообщение с клавиатурой "Быстрого меню"
    await message.answer("Спасибо за подписку на FG :)", reply_markup = reply_menu_keyboard)
    
    # Отправляем отдельное сообщение с inline клавиатурой
    await message.answer("Основные Разделы:", reply_markup = inline_menu_keyboard)
    ''' 
    Обратите внимание, что при использовании reply_markup с 
    клавиатурой ReplyKeyboardMarkup, эта клавиатура будет отображаться постоянно, 
    пока вы явно не замените ее другой клавиатурой или не удалите ее с помощью
    reply_markup=types.ReplyKeyboardRemove().
    '''

async def cmd_main_menu(message: types.Message):
    try:
        if isinstance(message, types.Message):
            await message.answer("Основные Разделы:", reply_markup = inline_menu_keyboard)
        elif isinstance(message, types.CallbackQuery):
            await message.message.edit_text("Основные Разделы:", reply_markup = inline_menu_keyboard)
    except Exception as e:
        print(f"Ошибка при обработке колбэк-запроса: {e}")

async def cmd_help(message: types.Message):
    help_text = "Доступные команды:\n" \
            "/start - Начать работу с ботом\n" \
            "/menu - Меню с основными разделами\n" \
            "/media - Получение новостных сводок\n" \
            "/stores - Поиск игр в цифровых магазинах\n" \
            "/gmdata - Собственная датабаза с описание, скринами, мануалом и списком достижений\n" \
            "/gmdate - Сервис знакомств для совместной игры !В разработке!\n" \
            "/guide - Список обширных экскурсий по какой-ниубдь игре (путеводитель по миру. Расскажет от и до про уровни. Интересный факты. Секреты. И Помощь в прохождении)    !В разработке!\n" \
            "/hotline - \"Тех.поддержка\"\n" \
            "/sub - Подписка! (убирает рекламу, поддерживает проект) !В разработке!\n" \
            "/lk - Личный кабинет (Добавление любимых игр,экскурсий. Выбор языка. Настройка Уведомлений (например о скидке на любимую игру или о распрадаже) и т.п) !В разработке!\n" \
            "/help - Показать список команд"
    try:
        if isinstance(message, types.Message):
            await message.answer(help_text, reply_markup = inline_main_menu_keyboard)
        elif isinstance(message, types.CallbackQuery):
            await message.message.edit_text(help_text, reply_markup = inline_main_menu_keyboard)
    except Exception as e:
        print(f"Ошибка при обработке колбэк-запроса: {e}")


