from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

import utils
import media_handlers

router = Router()

# Команда /media
@router.message(Command("media"))
async def cmd_media(message: types.Message, state: FSMContext):
    if await utils.check_subscription(message, message.bot):
        await media_handlers.cmd_media(message, state)

# callbacks
router.callback_query.register(media_handlers.cmd_media, lambda c: c.data == 'choice_media')
router.callback_query.register(media_handlers.process_choice_media, lambda c: c.data.startswith('media_choice:'))
router.callback_query.register(media_handlers.process_site_choice, lambda c: c.data.startswith('site_choice:'))
router.callback_query.register(media_handlers.process_channel_choice, lambda c: c.data.startswith('channel_choice:'))
router.callback_query.register(media_handlers.process_communitie_choise, lambda c: c.data.startswith('communitie_choice'))
router.callback_query.register(media_handlers.process_choice_media, lambda c: c.data == 'media_choice:back') 