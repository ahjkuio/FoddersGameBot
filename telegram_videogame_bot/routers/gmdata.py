from aiogram import Router, types
from aiogram.filters import Command

import utils
import gmdata_handlers

router = Router()

@router.message(Command("gmdata"))
async def cmd_gmdata(message: types.Message):
    if await utils.check_subscription(message, message.bot):
        await gmdata_handlers.cmd_gmdata(message)

router.callback_query.register(gmdata_handlers.cmd_gmdata, lambda c: c.data == 'call_gmdata') 