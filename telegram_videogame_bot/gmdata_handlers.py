from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from aiogram.utils.markdown import hlink

import base_keyboards

async def cmd_gmdata(message: types.Message):
    gmdata_text = f"( ◉о◉)⊃━☆ " + hlink('VideoGames DB (RU)', 'https://fodderxd.notion.site/Video-Games-DB-RU-3dba7bcc4dbc4bbe8dcb89bcdf34576f?pvs=4') + "\n" \
                   "Мы ждем всех желающих помочь проекту! 💃"
    try:
        if isinstance(message, types.Message):
            await message.answer(gmdata_text, parse_mode='HTML', reply_markup = base_keyboards.inline_main_menu_keyboard)
        elif isinstance(message, types.CallbackQuery):
            await message.message.edit_text(gmdata_text, parse_mode='HTML', reply_markup = base_keyboards.inline_main_menu_keyboard)
    except Exception as e:
        print(f"Ошибка при обработке колбэк-запроса: {e}")

