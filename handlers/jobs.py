import os
import io
import zipfile
import logging
from datetime import datetime, timezone
from telegram.ext import ContextTypes

from config import ADMIN_IDS, BACKUP_CHANNEL_ID, DATA_DIR
from services import storage, timeutils
from services.group_service import kick_single_member, remove_unauthorized_members
from services.notify import send_alert
from services.mdutils import escape_md

logger = logging.getLogger(__name__)


async def _notify_admins(bot, text):
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")


async def grace_kick_callback(context: ContextTypes.DEFAULT_TYPE):
    """Runs once, after the grace period, for a single user who joined unverified."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    username = job.data.get("username", "")

    allowed = storage.get_allowed_ids(chat_id)
    if user_id in allowed:
        return  # they were whitelisted in time - nothing to do

    ok = await kick_single_member(context.bot, chat_id, user_id, username)
    if ok:
        title = escape_md(storage.get_group_title(chat_id))
        await send_alert(
            context.bot,
            f"🚨 Grace period expired — removed unverified user `{user_id}` from *{title}*."
        )


async def auto_whitelist_callback(context: ContextTypes.DEFAULT_TYPE):
    """Runs once, N minutes after a new member joins (if auto-whitelist is
    enabled for that group). Whitelists them automatically unless they've
    already left or an admin already handled them."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]

    tracked = storage.get_tracked_members(chat_id)
    if str(user_id) not in tracked:
        return  # they already left / were removed - nothing to do

    allowed = storage.get_allowed_ids(chat_id)
    if user_id in allowed:
        return  # already whitelisted (e.g. admin did it manually)

    storage.add_allowed_ids(chat_id, [user_id])
    title = escape_md(storage.get_group_title(chat_id))
    await send_alert(
        context.bot,
        f"🆕 Auto-whitelisted user `{user_id}` in *{title}* (auto-whitelist timer)."
    )


async def daily_summary_callback(context: ContextTypes.DEFAULT_TYPE):
    """Runs once a day. Sends a summary for every group with daily_summary enabled."""
    groups = storage.get_known_groups()

    for chat_id_str, ginfo in groups.items():
        chat_id = int(chat_id_str)
        settings = storage.get_group_settings(chat_id)
        if not settings.get("daily_summary"):
            continue

        try:
            allowed = storage.get_allowed_ids(chat_id)
            tracked = storage.get_tracked_members(chat_id)
            unverified = storage.get_unverified_members(chat_id)
            title = escape_md(ginfo.get("title", chat_id_str))

            text = (
                f"📆 *Daily Summary — {title}*\n\n"
                f"Tracked members: {len(tracked)}\n"
                f"Allowed (whitelisted): {len(allowed)}\n"
                f"Unverified: {len(unverified)}"
            )
            await _notify_admins(context.bot, text)
        except Exception as e:
            logger.warning(f"Daily summary failed for group {chat_id}: {e}")
            await send_alert(context.bot, f"⚠️ Daily summary failed for group `{chat_id}`: {e}")


async def auto_cleanup_callback(context: ContextTypes.DEFAULT_TYPE):
    """Runs once a day. Removes unauthorized members from every group with auto_cleanup enabled."""
    groups = storage.get_known_groups()

    for chat_id_str, ginfo in groups.items():
        chat_id = int(chat_id_str)
        settings = storage.get_group_settings(chat_id)
        if not settings.get("auto_cleanup"):
            continue

        try:
            removed = await remove_unauthorized_members(context.bot, chat_id)
            if not removed:
                continue
            title = escape_md(ginfo.get("title", chat_id_str))
            await send_alert(
                context.bot,
                f"🧹 Auto-cleanup removed {len(removed)} unauthorized member(s) from *{title}*."
            )
        except Exception as e:
            logger.warning(f"Auto-cleanup failed for group {chat_id}: {e}")
            await send_alert(context.bot, f"⚠️ Auto-cleanup failed for group `{chat_id}`: {e}")


def build_backup_zip():
    """Zips every data file in DATA_DIR and returns (BytesIO buffer, filename)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(DATA_DIR):
            fpath = os.path.join(DATA_DIR, fname)
            if os.path.isfile(fpath) and fname.endswith(".json"):
                zf.write(fpath, arcname=fname)
    buf.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return buf, f"backup_{stamp}.zip"


async def auto_backup_callback(context: ContextTypes.DEFAULT_TYPE):
    """Runs every 2 hours. Zips every data file and posts it to the backup channel."""
    if not BACKUP_CHANNEL_ID:
        return

    try:
        buf, filename = build_backup_zip()

        await context.bot.send_document(
            chat_id=BACKUP_CHANNEL_ID,
            document=buf,
            filename=filename,
            caption=f"🗄️ Automatic backup\n🕒 {timeutils.to_ist_dual(timeutils.now_utc_iso())}"
        )
    except Exception as e:
        logger.warning(f"Auto-backup failed: {e}")
        await _notify_admins(context.bot, f"⚠️ Auto-backup failed: {e}")
