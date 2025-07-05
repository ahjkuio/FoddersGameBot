from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

import utils
import base_handlers
import personalAccount_handlers

router = Router()


@router.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    if await utils.check_subscription(message, message.bot):
        await personalAccount_handlers.personal_account_start(message, state)


@router.message(Command("menu"))
async def main_menu(message: types.Message):
    if await utils.check_subscription(message, message.bot):
        await base_handlers.cmd_main_menu(message)


@router.message(Command("help"))
async def help_cmd(message: types.Message):
    if await utils.check_subscription(message, message.bot):
        await base_handlers.cmd_help(message) 