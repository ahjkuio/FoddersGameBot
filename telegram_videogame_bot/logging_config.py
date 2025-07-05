from loguru import logger
import sys
from typing import Optional
from aiogram import Bot
import asyncio
import os


def configure_logging(bot: Optional[Bot] = None):
    """Настраивает Loguru.

    1. Консоль
    2. Файл с ротацией 10 МБ (хранить 10 файлов)
    3. При уровне ERROR отправляет сообщение админу (если ADMIN_CHAT_ID указан)
    """

    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        colorize=True,
    )
    logger.add(
        "bot.log",
        level="INFO",
        rotation="10 MB",
        retention="10 days",
        compression="zip",
        enqueue=True,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )

    admin_chat_id = os.getenv("449066726")

    if bot and admin_chat_id:

        async def _send_to_admin(message: str):
            try:
                await bot.send_message(int(admin_chat_id), f"🚨 {message}")
            except Exception:
                # avoid infinite loop of logging
                pass

        def _telegram_sink(log_message):
            record = log_message.record
            if record["level"].no >= 40:  # Error and above
                asyncio.create_task(_send_to_admin(record["message"]))

        logger.add(_telegram_sink, level="ERROR", enqueue=True) 