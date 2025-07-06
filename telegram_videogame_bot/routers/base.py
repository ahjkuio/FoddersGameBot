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


@router.message(Command("lk"))
async def cmd_lk(message: types.Message, state: FSMContext):
    if await utils.check_subscription(message, message.bot):
        await personalAccount_handlers.cmd_lk(message, state, message.bot)


@router.message(lambda m: m.text == "Личный Кабинет")
async def lk_quick(message: types.Message, state: FSMContext):
    await cmd_lk(message, state)


@router.callback_query(lambda c: c.data == 'personal_account')
async def lk_button(call: types.CallbackQuery, state: FSMContext):
    await personalAccount_handlers.cmd_lk(call, state, call.bot)


# Возврат в меню — редактируем текущее сообщение, не создавая новое
@router.callback_query(lambda c: c.data == 'main_menu')
async def back_to_main_menu(call: types.CallbackQuery):
    await base_handlers.cmd_main_menu(call)
    await call.answer()


# Краткое содержание – показывает /help
@router.callback_query(lambda c: c.data == 'show_commands')
async def show_commands(call: types.CallbackQuery):
    await base_handlers.cmd_help(call) 