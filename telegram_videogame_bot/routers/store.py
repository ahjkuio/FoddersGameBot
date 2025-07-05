from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

import utils
import store_handlers

router = Router()

@router.message(Command("stores"))
async def cmd_stores(message: types.Message, state: FSMContext):
    if await utils.check_subscription(message, message.bot):
        await store_handlers.cmd_stores(message, state)

# callbacks for store interactions
router.callback_query.register(store_handlers.cmd_stores, lambda c: c.data == 'choice_store')
router.callback_query.register(store_handlers.process_store_choice, lambda c: c.data.startswith('store:'))
router.callback_query.register(store_handlers.process_steam_option, lambda c: c.data.startswith('steam:'))
router.message.register(store_handlers.process_search_query, store_handlers.SteamStates.search_query)
router.callback_query.register(store_handlers.process_sort_option, lambda c: c.data.startswith('sort:'))
router.callback_query.register(store_handlers.process_store_choice, lambda c: c.data.startswith('store:back'))
router.callback_query.register(store_handlers.process_page, lambda c: c.data.startswith('page:'))
router.callback_query.register(store_handlers.process_game_info, lambda c: c.data.startswith('game_info:'))
router.callback_query.register(store_handlers.toggle_favorite, lambda c: c.data.startswith('toggle_favorite:'))
router.callback_query.register(store_handlers.toggle_notifications, lambda c: c.data.startswith('toggle_notifications:')) 