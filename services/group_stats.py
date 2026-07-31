import logging
from telegram.error import TelegramError
from services import storage

logger = logging.getLogger(__name__)


async def get_group_stats(bot, chat_id):
    """
    Fetches a combined snapshot of a group's stats:
    - Live data from Telegram (actual total member count, chat title/type,
      description, invite link, admin list) via the Bot API.
    - Data the bot already tracks locally (whitelisted count, tracked/observed
      count, unverified count, category, owner).

    Returns a dict. Any Telegram-side field that fails to fetch (e.g. bot
    isn't admin, chat was deleted, rate-limited) is set to None instead of
    raising, so one failure doesn't break the whole report.
    """
    stats = {
        "chat_id": chat_id,
        "title": storage.get_group_title(chat_id),
        "category_id": storage.get_group_category(chat_id),
        "owner_id": storage.get_group_owner(chat_id),

        # Live Telegram data (filled in below, None if unavailable)
        "total_member_count": None,
        "chat_type": None,
        "description": None,
        "invite_link": None,
        "admins": [],

        # Locally tracked data
        "whitelisted_count": len(storage.get_allowed_ids(chat_id)),
        "tracked_count": len(storage.get_tracked_members(chat_id)),
        "unverified_count": len(storage.get_unverified_members(chat_id)),
        "removed_count": len(storage.get_removed_log(chat_id)),
    }

    # --- Actual total member count, straight from Telegram ---
    try:
        stats["total_member_count"] = await bot.get_chat_member_count(chat_id)
    except TelegramError as e:
        logger.warning(f"Couldn't fetch member count for {chat_id}: {e}")

    # --- Chat info (type, description, invite link) ---
    try:
        chat = await bot.get_chat(chat_id)
        stats["chat_type"] = chat.type
        stats["description"] = chat.description
        stats["invite_link"] = chat.invite_link
        if chat.title:
            stats["title"] = chat.title
    except TelegramError as e:
        logger.warning(f"Couldn't fetch chat info for {chat_id}: {e}")

    # --- Admin list ---
    try:
        admins = await bot.get_chat_administrators(chat_id)
        stats["admins"] = [
            {
                "user_id": a.user.id,
                "username": a.user.username or "",
                "full_name": a.user.full_name,
                "is_owner": a.status == "creator",
            }
            for a in admins
        ]
    except TelegramError as e:
        logger.warning(f"Couldn't fetch admins for {chat_id}: {e}")

    return stats


async def get_all_group_stats(bot, owner_id=None):
    """
    Same as get_group_stats, but for every known group (or only the ones
    owned by `owner_id`, for delegated admins/viewers scoped to their own
    groups). Returns a list of stat dicts.
    """
    groups = storage.get_known_groups()
    results = []
    for chat_id_str, info in groups.items():
        if owner_id is not None and info.get("owner_id") != owner_id:
            continue
        results.append(await get_group_stats(bot, int(chat_id_str)))
    return results


def format_group_stats(stats):
    """Renders a get_group_stats() dict as a Markdown message for the bot to send."""
    from services.mdutils import escape_md

    title = escape_md(stats["title"])
    lines = [f"📊 *{title}*", ""]

    if stats["total_member_count"] is not None:
        lines.append(f"👥 Total members (live): *{stats['total_member_count']}*")
    else:
        lines.append("👥 Total members (live): _unavailable_")

    lines.append(f"✅ Whitelisted: *{stats['whitelisted_count']}*")
    lines.append(f"👀 Tracked (observed by bot): *{stats['tracked_count']}*")
    lines.append(f"⚠️ Unverified: *{stats['unverified_count']}*")
    lines.append(f"🗑️ Removed (all-time): *{stats['removed_count']}*")

    if stats["chat_type"]:
        lines.append(f"🏷️ Type: `{stats['chat_type']}`")

    if stats["admins"]:
        lines.append("")
        lines.append(f"🛡️ Admins: *{len(stats['admins'])}*")
        for a in stats["admins"][:10]:
            uname = f"@{escape_md(a['username'])}" if a["username"] else escape_md(a["full_name"])
            crown = "👑 " if a["is_owner"] else ""
            lines.append(f"   {crown}{uname} (`{a['user_id']}`)")

    return "\n".join(lines)
