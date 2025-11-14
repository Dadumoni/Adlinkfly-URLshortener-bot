import json
import logging
from telegram import Update
from bot import handler

logger = logging.getLogger(__name__)

async def webhook(request):
    """Vercel webhook handler"""
    try:
        body = await request.json()
        
        # Create an Update object from the received data
        update = Update.de_json(body, None)
        
        # Process the update
        await handler(update)
        
        return {"statusCode": 200, "body": "OK"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"statusCode": 500, "body": str(e)}
