import logging
from telegram.ext import ContextTypes

from services.notify import send_alert

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Catches any otherwise-unhandled exception and sends it to the backup/
    alerts channel (BACKUP_CHANNEL_ID), falling back to a DM to super
    admins if no backup channel is configured.
    """
    logger.error("Unhandled exception while processing an update:", exc_info=context.error)
    await send_alert(context.bot, f"⚠️ Bot error occurred:\n`{context.error}`")
