from aiogram import Router, types
from aiogram.filters import Command

import utils
import hotline_handlers

router = Router()

@router.message(Command("hotline"))
async def cmd_hotline(message: types.Message):
    if await utils.check_subscription(message, message.bot):
        await hotline_handlers.cmd_hotline(message)

router.callback_query.register(hotline_handlers.cmd_hotline, lambda c: c.data == 'call_hotline')

# Быстрый ярлык из меню
@router.message(lambda m: m.text == "Тех. Поддержка")
async def quick_hotline(message: types.Message):
    await cmd_hotline(message) 