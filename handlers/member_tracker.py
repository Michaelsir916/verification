from telegram import Update
from telegram.ext import ContextTypes
from services import storage
from services.group_service import kick_single_member
from services.notify import send_alert
from services.mdutils import escape_md
from handlers.jobs import grace_kick_callback, auto_whitelist_callback

ACTIVE_STATUSES = ("member", "administrator", "creator", "restricted")
INACTIVE_STATUSES = ("left", "kicked")

BOT_ACTIVE_STATUSES = ("member", "administrator", "creator")
BOT_INACTIVE_STATUSES = ("left", "kicked")


async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Triggered whenever a REGULAR USER joins/leaves a group the bot is in.
    Also applies auto-kick / grace-period / welcome-message settings.
    """
    cmu = update.chat_member
    if not cmu:
        return

    chat = cmu.chat
    old_status = cmu.old_chat_member.status
    new_status = cmu.new_chat_member.status
    user = cmu.new_chat_member.user

    if user.is_bot:
        return

    # Opportunistically register this group too, but ONLY if it's not already
    # known - re-writing an existing entry here risked a race that could wipe
    # out a just-assigned category (owner/category_id are preserved by
    # add_known_group, but avoiding the extra write entirely is safer).
    if str(chat.id) not in storage.get_known_groups():
        storage.add_known_group(chat.id, chat.title)

    if new_status in ACTIVE_STATUSES:
        just_joined = old_status not in ACTIVE_STATUSES

        invite_link = None
        if cmu.invite_link:
            invite_link = cmu.invite_link.invite_link

        # Store the RAW UTC ISO timestamp - converted to IST only when displayed
        join_time = cmu.date.isoformat() if cmu.date else ""

        storage.add_tracked_member(chat.id, user.id, user.username, join_time, invite_link)

        if not just_joined:
            return

        settings = storage.get_group_settings(chat.id)
        allowed = storage.get_allowed_ids(chat.id)
        is_allowed = user.id in allowed

        if is_allowed:
            if settings.get("welcome_message"):
                try:
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=f"👋 Welcome, {user.mention_html()}!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            return

        mode = settings.get("auto_kick", "off")

        aw_minutes = settings.get("auto_whitelist_minutes", -1)
        if aw_minutes >= 0:
            if aw_minutes == 0:
                # Instant: whitelist right away, no need to schedule a job.
                storage.add_allowed_ids(chat.id, [user.id])
                is_allowed = True
            elif context.job_queue:
                context.job_queue.run_once(
                    auto_whitelist_callback,
                    when=aw_minutes * 60,
                    data={"chat_id": chat.id, "user_id": user.id},
                    name=f"autowhitelist_{chat.id}_{user.id}"
                )

        if mode == "instant" and not is_allowed:
            await kick_single_member(context.bot, chat.id, user.id, user.username or "")

        elif mode == "grace" and not is_allowed:
            grace_minutes = settings.get("grace_minutes", 60)
            if context.job_queue:
                context.job_queue.run_once(
                    grace_kick_callback,
                    when=grace_minutes * 60,
                    data={"chat_id": chat.id, "user_id": user.id, "username": user.username or ""},
                    name=f"grace_{chat.id}_{user.id}"
                )
            try:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=(
                        f"⚠️ {user.mention_html()} please get verified within "
                        f"{grace_minutes} minute(s) or you will be removed."
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass

    elif new_status in INACTIVE_STATUSES:
        storage.remove_tracked_member(chat.id, user.id)

        settings = storage.get_group_settings(chat.id)
        if settings.get("leave_notification"):
            uname = f"@{escape_md(user.username)}" if user.username else escape_md(user.first_name or "Someone")
            title = escape_md(storage.get_group_title(chat.id))
            await send_alert(
                context.bot,
                f"🚶 *{title}*\n{uname} (`{user.id}`) has left the group."
            )


async def track_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Triggered whenever the BOT ITSELF is added to / removed from a chat.
    The user who performed the action becomes the "owner" of that group -
    only they (and super admins) will be able to see/manage it.
    """
    cmu = update.my_chat_member
    if not cmu:
        return

    chat = cmu.chat
    new_status = cmu.new_chat_member.status
    adder = cmu.from_user

    if new_status in BOT_ACTIVE_STATUSES:
        owner_id = adder.id if adder else None
        storage.add_known_group(chat.id, chat.title, owner_id=owner_id)
    elif new_status in BOT_INACTIVE_STATUSES:
        storage.remove_known_group(chat.id)
