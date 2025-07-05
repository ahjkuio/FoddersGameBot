# utils.py содержит вспомогательные функции.
from aiogram import Bot
from aiogram.types import Message
from aiogram.enums.chat_member_status import ChatMemberStatus
import config

async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=config.CHANNEL_USERNAME, user_id=user_id)
        print(member.status)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR]
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False

async def check_subscription(message: Message, bot: Bot):
    if not await is_subscribed(bot, message.from_user.id):
        await message.answer(
            f"Привет! ой, чтобы использовать этого бота, тебе нужно подписаться на этот канал ^_^ {config.CHANNEL_USERNAME}.",
            disable_web_page_preview=True
        )
        return False
    return True