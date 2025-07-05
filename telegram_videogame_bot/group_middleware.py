from aiogram import BaseMiddleware
from aiogram.types import Update
import logging

logger = logging.getLogger(__name__)

class GroupPhotosMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.processing_groups = {}

    async def __call__(self, handler, event, data):
        logger.info("Middleware called")
        
        if isinstance(event, Update) and event.message and event.message.photo:
            message = event.message
            logger.info(f"Processing a photo: {message.photo[-1].file_id}, Media group ID: {message.media_group_id}")
            
            if message.media_group_id:
                if message.media_group_id in self.processing_groups:
                    logger.info("Skipping processing for photo as it's already in a group being processed.")
                    return
                else:
                    self.processing_groups[message.media_group_id] = True
                    logger.info("Marking this media group as being processed.")

        response = await handler(event, data)
        
        if isinstance(event, Update) and event.message and event.message.photo:
            if event.message.media_group_id and event.message.media_group_id in self.processing_groups:
                del self.processing_groups[event.message.media_group_id]
                logger.info("Marking media group as processed.")

        return response