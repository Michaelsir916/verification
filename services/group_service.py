import logging
from datetime import datetime, timezone
from services import storage
from services.notify import send_alert
from services.mdutils import escape_md

logger = logging.getLogger(__name__)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _kick(bot, chat_id, user_id):
    try:
        await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
        return True
    except Exception as e:
        logger.warning(f"Failed to kick user {user_id} from {chat_id}: {e}")
        title = escape_md(storage.get_group_title(chat_id))
        await send_alert(bot, f"⚠️ *{title}*\nFailed to remove user `{user_id}` — {e}")
        return False


async def kick_single_member(bot, chat_id, user_id, username=""):
    """Kicks one member immediately (used by auto-kick / grace period / manual remove)."""
    ok = await _kick(bot, chat_id, user_id)
    if ok:
        storage.remove_tracked_member(chat_id, user_id)
        storage.append_removed(chat_id, {
            "user_id": user_id,
            "username": username,
            "removed_at": _now_iso(),
        })
    return ok


async def remove_unauthorized_members(bot, chat_id):
    """
    Removes every tracked member who is NOT in the allowed ID list
    (kick, not a permanent ban — they can rejoin later if re-invited).
    """
    allowed = storage.get_allowed_ids(chat_id)
    tracked = storage.get_tracked_members(chat_id)

    removed = []

    for user_id_str, info in list(tracked.items()):
        user_id = int(user_id_str)

        if user_id in allowed:
            continue

        ok = await _kick(bot, chat_id, user_id)
        if ok:
            username = info.get("username", "")
            storage.remove_tracked_member(chat_id, user_id)
            entry = {
                "user_id": user_id,
                "username": username,
                "removed_at": _now_iso(),
            }
            storage.append_removed(chat_id, entry)
            removed.append(entry)

    return removed
