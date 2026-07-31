import logging
from config import BACKUP_CHANNEL_ID, ADMIN_IDS

logger = logging.getLogger(__name__)


async def send_alert(bot, text):
    """
    Sends operational alerts (leave notifications, error notifications) to
    the dedicated backup/alerts channel (BACKUP_CHANNEL_ID). Falls back to
    DM-ing every super admin if no backup channel is configured, or if
    sending to it fails for any reason.
    """
    if BACKUP_CHANNEL_ID:
        try:
            await bot.send_message(chat_id=BACKUP_CHANNEL_ID, text=text, parse_mode="Markdown")
            return
        except Exception as e:
            logger.warning(f"Could not send alert to backup channel: {e}")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")
