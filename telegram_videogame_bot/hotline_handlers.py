from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from aiogram.utils.markdown import hlink

import base_keyboards

async def cmd_hotline(message: types.Message):
    hotline_text = f"Товарищ! Вы вызвали сообщение тех. поддержки!\n" \
                   "Извините, но тут мы никого не тех. поддерживаем!\n" \
                   "И все ваши претензии на счет этого вы можете передать товарищу - @sonicsuperhedgehog!\n" \
                   "А также встретить таких же людей, нуждающихся в тех. поддержке - " + hlink('Отчаянные', 'https://t.me/+VLcF3K4axF01ZTNi') + "\n" \
                   "Всего вам наилучшего!"
    try:
        if isinstance(message, types.Message):
            await message.answer(hotline_text, parse_mode='HTML', reply_markup = base_keyboards.inline_main_menu_keyboard)
        elif isinstance(message, types.CallbackQuery):
            await message.message.edit_text(hotline_text, parse_mode='HTML', reply_markup = base_keyboards.inline_main_menu_keyboard)
    except Exception as e:
        print(f"Ошибка при обработке колбэк-запроса: {e}")

