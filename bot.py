import asyncio
import logging
from datetime import time as dtime, timezone, timedelta

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    filters,
)

from config import BOT_TOKEN
from handlers.commands import start, myid, register_group, handle_admin_message, find_command
from handlers.buttons import button_callback
from handlers.member_tracker import track_chat_member, track_my_chat_member
from handlers.documents import handle_bulk_document, handle_restore_document
from handlers.jobs import daily_summary_callback, auto_cleanup_callback, auto_backup_callback
from handlers.error_handler import error_handler
from keep_alive import keep_alive

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set in the .env file!")

    keep_alive()  # opens $PORT so Render's web service health check passes

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("registergroup", register_group))
    app.add_handler(CommandHandler("find", find_command))

    # Bulk .txt import - private chat only
    app.add_handler(MessageHandler(
        filters.Document.TXT & filters.ChatType.PRIVATE,
        handle_bulk_document
    ))

    # Restore-from-backup .zip upload - private chat only
    app.add_handler(MessageHandler(
        filters.Document.FileExtension("zip") & filters.ChatType.PRIVATE,
        handle_restore_document
    ))

    # Admin/viewer text messages (add/remove IDs, search) - private chat only
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_admin_message
    ))

    # Inline button presses
    app.add_handler(CallbackQueryHandler(button_callback))

    # Track the bot's own membership (which groups it's in)
    app.add_handler(ChatMemberHandler(track_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Track regular members joining/leaving groups (+ auto-kick/grace/welcome)
    app.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.CHAT_MEMBER))

    # Global error handler - notifies the relevant group first, falls back to admin DM
    app.add_error_handler(error_handler)

    # Scheduled jobs (require: pip install "python-telegram-bot[job-queue]")
    if app.job_queue:
        # Daily summary at 21:00 UTC
        app.job_queue.run_daily(daily_summary_callback, time=dtime(hour=21, minute=0, tzinfo=timezone.utc))
        # Daily auto-cleanup at 21:15 UTC
        app.job_queue.run_daily(auto_cleanup_callback, time=dtime(hour=21, minute=15, tzinfo=timezone.utc))
        # Auto-backup every 2 hours
        app.job_queue.run_repeating(auto_backup_callback, interval=timedelta(hours=2), first=60)
    else:
        print("⚠️ JobQueue not available - daily summary / auto-cleanup / grace-period kicks / auto-backup won't run.")
        print("   Install with: pip install \"python-telegram-bot[job-queue]\"")

    print("Bot is running...")

    # Python 3.14 no longer auto-creates an event loop on the main thread,
    # which makes python-telegram-bot's run_polling() crash with
    # "There is no current event loop in thread 'MainThread'." This creates
    # one explicitly if needed.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app.run_polling(allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"])


if __name__ == "__main__":
    main()
