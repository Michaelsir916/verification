import io
import os
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import SUPPORT_USERNAME, DATA_DIR
from services import storage, timeutils, i18n
from services.mdutils import escape_md
from services.group_service import remove_unauthorized_members, kick_single_member
from services.group_stats import get_group_stats, format_group_stats
from handlers.jobs import build_backup_zip
from handlers.commands import (
    main_menu_keyboard,
    done_keyboard,
    back_only_keyboard,
    group_list_keyboard,
    category_groups_keyboard,
    categories_keyboard,
    category_detail_keyboard,
    set_category_keyboard,
    settings_keyboard,
    manage_users_keyboard,
    user_detail_keyboard,
    expiry_keyboard,
    auto_remove_keyboard,
    restore_confirm_keyboard,
    is_super_admin,
    is_full_admin,
    is_authorized,
)

MAX_MSG_LEN = 3500

RESTRICTED_EXACT = {
    "add_members_start", "add_done", "remove_member_start",
    "remove_unauthorized", "bulk_import_start", "export_allowed",
    "settings_menu", "settings_cycle_autokick", "settings_toggle_welcome",
    "settings_toggle_cleanup", "settings_toggle_summary", "settings_toggle_leave",
    "cat_add_start", "set_category_start", "pending_approvals",
    "autoremove_menu", "autoremove_enable", "autoremove_disable", "autoremove_analyze",
    "settings_cycle_autowhitelist", "remove_unauthorized_cancel",
}
RESTRICTED_PREFIXES = (
    "cat_rename_start:", "cat_delete:", "assign_category:", "pending_approve:", "pending_reject:",
    "expiry:", "autoremove_mode:", "autoremove_grace:", "remove_unauthorized_confirm:", "pending_approve_all:",
)

SUPER_ONLY_PREFIXES = (
    "manage_users_menu", "add_user_start", "user_info:", "remove_user:",
    "backup_now", "restore_backup_start", "restore_confirm", "restore_cancel",
)


def _is_restricted(data):
    return data in RESTRICTED_EXACT or any(data.startswith(p) for p in RESTRICTED_PREFIXES)


async def safe_edit(query, text, **kwargs):
    """
    Wraps query.edit_message_text, silently ignoring Telegram's harmless
    "Message is not modified" error (happens when the new content/keyboard
    is identical to what's already shown - e.g. pressing the same folder
    twice in a row).
    """
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise


def build_direct_link(user_id, username):
    if username:
        return f"https://t.me/{escape_md(username)}"
    return f"tg://user?id={user_id}"


def _chunk_and_send(lines):
    chunks = []
    current = ""
    for block in lines:
        if len(current) + len(block) > MAX_MSG_LEN:
            chunks.append(current)
            current = ""
        current += block
    if current:
        chunks.append(current)
    return chunks


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not is_authorized(user.id):
        await query.answer("You are not authorized to do this.", show_alert=True)
        return

    is_super = is_super_admin(user.id)
    is_full = is_full_admin(user.id)

    if _is_restricted(data) and not is_full:
        await query.answer("This action is for full admins only.", show_alert=True)
        return

    if any(data == p or data.startswith(p) for p in SUPER_ONLY_PREFIXES) and not is_super:
        await query.answer("This action is for the main admin only.", show_alert=True)
        return

    if data == "show_support":
        await query.answer(f"🆘 Support: {SUPPORT_USERNAME}", show_alert=True)
        return

    if data == "toggle_language":
        new_lang = storage.toggle_user_lang(user.id)
        await query.answer(f"🌐 {i18n.LANGS.get(new_lang)}", show_alert=False)
        group_id = context.user_data.get("selected_group")
        title = escape_md(storage.get_group_title(group_id)) if group_id else ""
        text = f"📌 Managing: *{title}*\n\nChoose an option:" if group_id else "Choose an option:"
        try:
            await safe_edit(query, text, parse_mode="Markdown", reply_markup=main_menu_keyboard(is_full, is_super, user.id))
        except Exception:
            pass
        return

    await query.answer()

    # ---------- Universal cancel / back ----------
    if data == "cancel_state":
        context.user_data["state"] = None
        context.user_data["pending_add_ids"] = []
        context.user_data["added_count"] = 0
        context.user_data.pop("restore_files", None)
        group_id = context.user_data.get("selected_group")
        if group_id:
            title = storage.get_group_title(group_id)
            await safe_edit(query, 
                f"📌 Managing: *{escape_md(title)}*\n\nChoose an option:",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
        else:
            await safe_edit(query, 
                "Select a group to manage:",
                reply_markup=group_list_keyboard(user.id)
            )
        return

    # ---------- Group / category navigation ----------
    if data == "noop":
        return

    if data == "refresh_groups":
        await safe_edit(query, 
            "Select a group to manage:",
            reply_markup=group_list_keyboard(user.id)
        )
        return

    if data.startswith("open_category:"):
        bucket = data.split(":", 1)[1]
        await safe_edit(query, 
            "📂 Groups in this category:",
            reply_markup=category_groups_keyboard(user.id, bucket)
        )
        return

    if data == "manage_categories":
        await safe_edit(query, 
            "🏷️ *Your categories*\n\nTap to rename/delete, or add a new one:",
            parse_mode="Markdown",
            reply_markup=categories_keyboard(user.id)
        )
        return

    if data == "cat_add_start":
        context.user_data["state"] = "adding_category"
        await safe_edit(query, 
            "➕ Send a name for the new category (e.g. VIP, Trial, Staff).",
            reply_markup=back_only_keyboard()
        )
        return

    if data.startswith("cat_edit:"):
        cat_id = data.split(":", 1)[1]
        categories = storage.get_categories(user.id)
        name = categories.get(cat_id, "Unknown")
        await safe_edit(query, 
            f"🏷️ Category: *{escape_md(name)}*",
            parse_mode="Markdown",
            reply_markup=category_detail_keyboard(cat_id)
        )
        return

    if data.startswith("cat_rename_start:"):
        cat_id = data.split(":", 1)[1]
        context.user_data["state"] = "renaming_category"
        context.user_data["editing_category_id"] = cat_id
        await safe_edit(query, 
            "✏️ Send the new name for this category.",
            reply_markup=back_only_keyboard()
        )
        return

    if data.startswith("cat_delete:"):
        cat_id = data.split(":", 1)[1]
        storage.delete_category(user.id, cat_id)
        await safe_edit(query, 
            "🗑️ Category deleted. Groups that were in it are now Uncategorized.",
            reply_markup=categories_keyboard(user.id)
        )
        return

    if data.startswith("select_group:"):
        chat_id = int(data.split(":", 1)[1])
        ginfo = storage.get_known_groups().get(str(chat_id), {})
        if not is_super and ginfo.get("owner_id") != user.id:
            await query.answer("You don't have access to this group.", show_alert=True)
            return

        context.user_data["selected_group"] = chat_id
        context.user_data["state"] = None
        title = storage.get_group_title(chat_id)
        await safe_edit(query, 
            f"📌 Managing: *{escape_md(title)}*\n\nChoose an option:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )
        return

    if data == "change_group":
        context.user_data["selected_group"] = None
        context.user_data["state"] = None
        await safe_edit(query, 
            "Select a group to manage:",
            reply_markup=group_list_keyboard(user.id)
        )
        return

    # ---------- Manage Users (super admin only) ----------
    if data == "manage_users_menu":
        count = len(storage.get_managed_admins())
        await safe_edit(query, 
            f"👥 *Delegated users: {count}*\n\nTap a user to view their access & groups, or add a new one:",
            parse_mode="Markdown",
            reply_markup=manage_users_keyboard()
        )
        return

    if data == "add_user_start":
        context.user_data["state"] = "adding_user_id"
        await safe_edit(query, 
            "➕ Send the Telegram User ID of the person you want to grant access to.",
            reply_markup=back_only_keyboard()
        )
        return

    if data.startswith("user_info:"):
        uid = data.split(":", 1)[1]
        info = storage.get_managed_admin_info(int(uid))
        if not info:
            await safe_edit(query, "User not found.", reply_markup=manage_users_keyboard())
            return

        active = storage.is_managed_admin_active(int(uid))
        started = timeutils.to_ist_dual(info.get("started_at"))
        expires = timeutils.to_ist_dual(info.get("expires_at")) if info.get("expires_at") else "Permanent (no expiry)"
        uname = info.get("username")
        uname_display = f"@{escape_md(uname)}" if uname else "_no username_"

        owned = [g for g in storage.get_known_groups().values() if g.get("owner_id") == int(uid)]
        if owned:
            groups_text = "\n".join(f"• {escape_md(g.get('title', ''))}" for g in owned)
        else:
            groups_text = "_No groups added yet_"

        text = (
            f"👤 *User* `{uid}` ({uname_display})\n\n"
            f"Status: {'🟢 Active' if active else '🔴 Expired'}\n"
            f"Started: {started}\n"
            f"Expires: {expires}\n"
            f"Added by: `{info.get('added_by')}`\n\n"
            f"📂 *Groups added by this user ({len(owned)}):*\n{groups_text}"
        )
        await safe_edit(query, text, parse_mode="Markdown", reply_markup=user_detail_keyboard(uid))
        return

    if data.startswith("remove_user:"):
        uid = data.split(":", 1)[1]
        storage.remove_managed_admin(int(uid))
        count = len(storage.get_managed_admins())
        await safe_edit(query, 
            f"✅ Access revoked for user `{uid}`.\n\n👥 *Delegated users: {count}*",
            parse_mode="Markdown",
            reply_markup=manage_users_keyboard()
        )
        return

    # ---------- Backup / Restore (super admin only) ----------
    if data == "backup_now":
        await query.answer("Building backup...")
        try:
            buf, filename = build_backup_zip()
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=buf,
                filename=filename,
                caption=f"🗄️ Manual backup\n🕒 {timeutils.to_ist_dual(timeutils.now_utc_iso())}"
            )
        except Exception as e:
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"⚠️ Backup failed: {e}")
        return

    if data == "restore_backup_start":
        context.user_data["state"] = "restoring_backup"
        await safe_edit(query, 
            "♻️ Send the backup *.zip* file to restore.\n\n"
            "⚠️ This will *overwrite* all current data (members, settings, categories, etc.) "
            "once you confirm.",
            parse_mode="Markdown",
            reply_markup=back_only_keyboard()
        )
        return

    if data == "restore_confirm":
        pending = context.user_data.get("restore_files")
        if not pending:
            await safe_edit(query, "⚠️ No backup file pending. Please send the .zip again.", reply_markup=back_only_keyboard())
            return

        try:
            for fname, content in pending.items():
                with open(os.path.join(DATA_DIR, fname), "wb") as f:
                    f.write(content)
            context.user_data.pop("restore_files", None)
            context.user_data["state"] = None
            await safe_edit(query, 
                f"✅ Restore complete. {len(pending)} file(s) restored.",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
        except Exception as e:
            await safe_edit(query, f"⚠️ Restore failed: {e}", reply_markup=back_only_keyboard())
        return

    if data == "restore_cancel":
        context.user_data.pop("restore_files", None)
        context.user_data["state"] = None
        await safe_edit(query, 
            "❌ Restore cancelled. No data was changed.",
            reply_markup=group_list_keyboard(user.id)
        )
        return

    # ---------- Search (scoped to user's own groups unless super admin) ----------
    if data == "search_start":
        context.user_data["state"] = "searching"
        scope = "all groups" if is_super else "your groups"
        await safe_edit(query, 
            f"🔍 Send a User ID or username (without @) to search across {scope}.",
            reply_markup=back_only_keyboard()
        )
        return

    # All actions below require a selected group
    group_id = context.user_data.get("selected_group")
    if not group_id:
        await safe_edit(query, 
            "Please select a group first:",
            reply_markup=group_list_keyboard(user.id)
        )
        return

    ginfo = storage.get_known_groups().get(str(group_id), {})
    if not is_super and ginfo.get("owner_id") != user.id:
        await query.answer("You don't have access to this group.", show_alert=True)
        return

    title = storage.get_group_title(group_id)
    title_md = escape_md(title)

    if data == "back_to_menu":
        await safe_edit(query, 
            f"📌 Managing: *{title_md}*\n\nChoose an option:",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )
        return

    # ---------- Set Category ----------
    if data == "set_category_start":
        await safe_edit(query, 
            f"🏷️ Choose a category for *{title_md}*:",
            parse_mode="Markdown",
            reply_markup=set_category_keyboard(group_id)
        )
        return

    if data.startswith("assign_category:"):
        _, gid, cat_id = data.split(":")
        gid = int(gid)
        storage.set_group_category(gid, None if cat_id == "none" else cat_id)
        gtitle = escape_md(storage.get_group_title(gid))
        await safe_edit(query, 
            f"✅ *{gtitle}* category updated.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )
        return

    # ---------- Start "Add Members" flow ----------
    if data == "add_members_start":
        context.user_data["state"] = "adding"
        context.user_data["added_count"] = 0
        context.user_data["pending_add_ids"] = []
        await safe_edit(query, 
            f"➕ [{title}] Send the User ID you want to add.\n"
            "(e.g.: 5970917123)\n\n"
            "Each ID will be queued. Press Done once you've sent them all, "
            "then choose how long they should stay whitelisted.",
            reply_markup=done_keyboard()
        )

    elif data == "add_done":
        context.user_data["state"] = None
        pending = context.user_data.get("pending_add_ids", [])
        if not pending:
            await safe_edit(query, 
                "ℹ️ No new IDs were queued.",
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Choose an option to continue:",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
            return
        await safe_edit(query, 
            f"📥 {len(pending)} ID(s) queued for *{title_md}*.\n\n"
            "Choose how long they should stay whitelisted:",
            parse_mode="Markdown",
            reply_markup=expiry_keyboard()
        )

    elif data.startswith("expiry:"):
        choice = data.split(":", 1)[1]
        pending = context.user_data.get("pending_add_ids", [])

        if choice == "discard":
            context.user_data["pending_add_ids"] = []
            context.user_data["added_count"] = 0
            await safe_edit(query, "🗑️ Discarded — nothing was added.")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Choose an option to continue:",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
            return

        if choice == "custom":
            context.user_data["state"] = "adding_custom_expiry"
            await safe_edit(query, 
                "🗓️ Send the expiry date/time in IST, e.g.:\n"
                "`25-12-2026` or `25-12-2026 23:59`",
                parse_mode="Markdown",
                reply_markup=back_only_keyboard()
            )
            return

        if not pending:
            await safe_edit(query, "ℹ️ No new IDs were queued.")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Choose an option to continue:",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
            return

        if choice == "lifetime":
            expires_at = None
            expiry_label = "♾️ Lifetime (no expiry)"
        else:
            days = int(choice)
            expires_at = timeutils.now_utc_iso_plus_days(days)
            expiry_label = f"📅 {days} days"

        storage.add_allowed_ids(group_id, pending, expires_at=expires_at)
        context.user_data["pending_add_ids"] = []
        context.user_data["added_count"] = 0

        await safe_edit(query, 
            f"🎉 Added {len(pending)} ID(s) for *{title_md}*.\n"
            f"⏳ Expiry: {expiry_label}",
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Choose an option to continue:",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    elif data == "bulk_import_start":
        context.user_data["state"] = "bulk_import"
        await safe_edit(query, 
            f"📥 [{title}] Upload a .txt file containing User IDs "
            "(one per line, or separated by spaces/commas).",
            reply_markup=back_only_keyboard()
        )

    elif data == "export_allowed":
        allowed = storage.get_allowed_ids(group_id)
        if not allowed:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"📭 No allowed IDs saved yet for *{title_md}*.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
            return

        content = "\n".join(str(i) for i in sorted(allowed))
        bio = io.BytesIO(content.encode("utf-8"))
        bio.name = f"allowed_ids_{group_id}.txt"

        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=bio,
            filename=bio.name,
            caption=f"📤 {len(allowed)} allowed ID(s) for {title}"
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Choose an option to continue:",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    elif data == "remove_member_start":
        context.user_data["state"] = "removing"
        await safe_edit(query, 
            f"➖ [{title}] Send the User ID you want to remove from the allowed list.",
            reply_markup=back_only_keyboard()
        )

    elif data == "remove_unauthorized":
        allowed = storage.get_allowed_ids(group_id)
        tracked = storage.get_tracked_members(group_id)
        at_risk = [uid for uid in tracked if uid not in allowed]

        if not at_risk:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"😌 No unauthorized members found in *{title_md}*.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
            return

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes, remove them", callback_data=f"remove_unauthorized_confirm:{group_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="remove_unauthorized_cancel"),
        ]])
        await safe_edit(
            query,
            f"⚠️ This will remove *{len(at_risk)}* unauthorized member(s) from *{title_md}*.\n\n"
            f"This can't be undone. Continue?",
            parse_mode="Markdown",
            reply_markup=kb
        )

    elif data.startswith("remove_unauthorized_confirm:"):
        gid = int(data.split(":")[1])
        title2 = escape_md(storage.get_group_title(gid))
        await safe_edit(query, f"⏳ [{title2}] Working on it, please wait...")

        removed = await remove_unauthorized_members(context.bot, gid)

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"🧹✨ Cleanup done!\n\n*{len(removed)}* member(s) removed from *{title2}*.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    elif data == "remove_unauthorized_cancel":
        await safe_edit(
            query,
            f"👍 Cancelled. No members were removed from *{title_md}*.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    # ---------- Pending Approvals (one message per user, with Approve/Reject) ----------
    elif data == "pending_approvals":
        unverified = storage.get_unverified_members(group_id)

        if not unverified:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"😌 No pending approvals for *{title_md}*.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
            return

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"📝 *{title_md} — Pending approvals: {len(unverified)}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"✅ Approve All ({len(unverified)})", callback_data=f"pending_approve_all:{group_id}")
            ]])
        )

        for uid, info in unverified.items():
            username = info.get("username") or ""
            full_name = info.get("full_name") or ""
            uname_display = f"@{escape_md(username)}" if username else "No username"
            name_display = escape_md(full_name) if full_name else "Unknown"
            link = build_direct_link(uid, username)
            join_display = timeutils.to_ist_dual(info.get("join_time"))
            invite_link = info.get("invite_link") or "Not available"

            detail = (
                f"👤 {name_display} ({uname_display})\n"
                f"🆔 ID: `{uid}`\n"
                f"🔗 Chat: {link}\n"
                f"🕒 Joined: {join_display}\n"
                f"📨 Invite link: `{invite_link}`"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"pending_approve:{group_id}:{uid}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"pending_reject:{group_id}:{uid}"),
            ]])
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=detail, parse_mode="Markdown",
                reply_markup=kb, disable_web_page_preview=True
            )

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⬆️ Review each pending member above.",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    elif data == "removal_report":
        removed = storage.get_removed_log(group_id)

        if not removed:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"😌 No one has been removed yet from *{title_md}*.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
            return

        blocks = [f"📊 *{title_md} — Total removed: {len(removed)}*\n\n"]
        for i, r in enumerate(removed, 1):
            username = r.get("username") or ""
            uname_display = f"@{escape_md(username)}" if username else "_no username_"
            removed_display = timeutils.to_ist_dual(r.get("removed_at"))
            blocks.append(f"{i}. {uname_display} — `{r['user_id']}`\n   Removed: {removed_display}\n")

        for chunk in _chunk_and_send(blocks):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk, parse_mode="Markdown")

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⬆️ End of report.",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    elif data == "unverified_members":
        unverified = storage.get_unverified_members(group_id)

        if not unverified:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🎊 All clear! No unverified members in *{title_md}* — everyone tracked is verified.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
            return

        blocks = [f"👀 *{title_md} — Unverified members: {len(unverified)}*\n\n"]

        for i, (uid, info) in enumerate(unverified.items(), 1):
            username = info.get("username") or ""
            full_name = info.get("full_name") or ""
            uname_display = f"@{escape_md(username)}" if username else "No username"
            name_display = escape_md(full_name) if full_name else "Unknown"
            link = build_direct_link(uid, username)
            join_display = timeutils.to_ist_dual(info.get("join_time"))
            invite_link = info.get("invite_link") or "Not available (direct add / already in group)"

            blocks.append(
                f"{i}. {name_display} ({uname_display})\n"
                f"   ID: `{uid}`\n"
                f"   Chat: {link}\n"
                f"   Joined: {join_display}\n"
                f"   Invite link: `{invite_link}`\n\n"
            )

        for chunk in _chunk_and_send(blocks):
            await context.bot.send_message(
                chat_id=query.message.chat_id, text=chunk, parse_mode="Markdown", disable_web_page_preview=True
            )

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⬆️ End of list.",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    # ---------- Inactivity report (allowed but never joined) ----------
    elif data == "inactivity_report":
        allowed = storage.get_allowed_ids(group_id)
        tracked_ids = {int(uid) for uid in storage.get_tracked_members(group_id).keys()}
        never_joined = sorted(allowed - tracked_ids)

        if not never_joined:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ Everyone whitelisted in *{title_md}* has joined at least once.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(is_full, is_super, user.id)
            )
            return

        blocks = [f"💤 *{title_md} — Whitelisted but never joined: {len(never_joined)}*\n\n"]
        for i, uid in enumerate(never_joined, 1):
            uname_display = "_Unknown username_"
            try:
                chat_info = await context.bot.get_chat(uid)
                if chat_info.username:
                    uname_display = f"@{escape_md(chat_info.username)}"
                elif chat_info.first_name:
                    uname_display = escape_md(chat_info.first_name)
            except Exception:
                pass
            blocks.append(f"{i}. {uname_display} — `{uid}`\n")

        for chunk in _chunk_and_send(blocks):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk, parse_mode="Markdown")

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⬆️ End of report.",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    # ---------- Live group stats (real Telegram member count + admins + local data) ----------
    elif data == "group_stats":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⏳ Fetching live stats from Telegram…"
        )
        try:
            stats = await get_group_stats(context.bot, group_id)
            text = format_group_stats(stats)
        except Exception as e:
            text = f"⚠️ Couldn't fetch stats for *{title_md}* — {escape_md(str(e))}"

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    elif data == "settings_menu":
        await safe_edit(query, 
            f"⚙️ Settings for *{title_md}*", parse_mode="Markdown", reply_markup=settings_keyboard(group_id)
        )

    elif data == "settings_cycle_autowhitelist":
        s = storage.get_group_settings(group_id)
        order = [-1, 0, 10, 30, 60, 360, 1440]  # OFF, Instant, 10m, 30m, 1h, 6h, 24h
        current = s["auto_whitelist_minutes"]
        idx = order.index(current) if current in order else 0
        storage.set_group_setting(group_id, "auto_whitelist_minutes", order[(idx + 1) % len(order)])
        await safe_edit(query, 
            f"⚙️ Settings for *{title_md}*", parse_mode="Markdown", reply_markup=settings_keyboard(group_id)
        )

    elif data == "autoremove_menu":
        s = storage.get_group_settings(group_id)
        await safe_edit(query, 
            f"🚨 *Auto-Remove* settings for *{title_md}*\n\n"
            "Members not on the whitelist get removed automatically according to this.",
            parse_mode="Markdown",
            reply_markup=auto_remove_keyboard(group_id)
        )

    elif data == "autoremove_enable":
        s = storage.get_group_settings(group_id)
        # Turning it on for the first time defaults to Instant; if they'd
        # previously used Grace mode, restore that instead of losing it.
        storage.set_group_setting(group_id, "auto_kick", "instant")
        await safe_edit(query, 
            f"🚨 *Auto-Remove* settings for *{title_md}*", parse_mode="Markdown",
            reply_markup=auto_remove_keyboard(group_id)
        )

    elif data == "autoremove_disable":
        storage.set_group_setting(group_id, "auto_kick", "off")
        await safe_edit(query, 
            f"🔴 Auto-Remove fully turned *OFF* for *{title_md}*. No members will be auto-removed.",
            parse_mode="Markdown",
            reply_markup=auto_remove_keyboard(group_id)
        )

    elif data.startswith("autoremove_mode:"):
        mode = data.split(":", 1)[1]
        storage.set_group_setting(group_id, "auto_kick", mode)
        await safe_edit(query, 
            f"🚨 *Auto-Remove* settings for *{title_md}*", parse_mode="Markdown",
            reply_markup=auto_remove_keyboard(group_id)
        )

    elif data.startswith("autoremove_grace:"):
        minutes = int(data.split(":", 1)[1])
        storage.set_group_setting(group_id, "grace_minutes", minutes)
        storage.set_group_setting(group_id, "auto_kick", "grace")
        await safe_edit(query, 
            f"🚨 *Auto-Remove* settings for *{title_md}*", parse_mode="Markdown",
            reply_markup=auto_remove_keyboard(group_id)
        )

    elif data == "autoremove_analyze":
        s = storage.get_group_settings(group_id)
        tracked = storage.get_tracked_members(group_id)
        allowed = storage.get_allowed_ids(group_id)
        unverified = storage.get_unverified_members(group_id)
        log = storage.get_removed_log(group_id)

        now = datetime.now(timezone.utc)
        last_7d = 0
        for entry in log:
            try:
                ts = datetime.fromisoformat(entry.get("removed_at", ""))
                if (now - ts).days <= 7:
                    last_7d += 1
            except (ValueError, TypeError):
                continue

        mode_label = {"off": "OFF", "instant": "INSTANT", "grace": f"GRACE ({s['grace_minutes']}m)"}[s["auto_kick"]]

        text = (
            f"📊 *Auto-Remove analysis — {title_md}*\n\n"
            f"• Current mode: {mode_label}\n"
            f"• Tracked members: {len(tracked)}\n"
            f"• Whitelisted: {len(allowed)}\n"
            f"• ⚠️ Currently unauthorized (not whitelisted): {len(unverified)}\n"
            f"• 🗑️ Total removed (all-time): {len(log)}\n"
            f"• 🗑️ Removed in last 7 days: {last_7d}\n"
        )
        await safe_edit(query, text, parse_mode="Markdown", reply_markup=auto_remove_keyboard(group_id))

    elif data == "settings_toggle_welcome":
        s = storage.get_group_settings(group_id)
        storage.set_group_setting(group_id, "welcome_message", not s["welcome_message"])
        await safe_edit(query, 
            f"⚙️ Settings for *{title_md}*", parse_mode="Markdown", reply_markup=settings_keyboard(group_id)
        )

    elif data == "settings_toggle_leave":
        s = storage.get_group_settings(group_id)
        storage.set_group_setting(group_id, "leave_notification", not s["leave_notification"])
        await safe_edit(query, 
            f"⚙️ Settings for *{title_md}*", parse_mode="Markdown", reply_markup=settings_keyboard(group_id)
        )

    elif data == "settings_toggle_cleanup":
        s = storage.get_group_settings(group_id)
        storage.set_group_setting(group_id, "auto_cleanup", not s["auto_cleanup"])
        await safe_edit(query, 
            f"⚙️ Settings for *{title_md}*", parse_mode="Markdown", reply_markup=settings_keyboard(group_id)
        )

    elif data == "settings_toggle_summary":
        s = storage.get_group_settings(group_id)
        storage.set_group_setting(group_id, "daily_summary", not s["daily_summary"])
        await safe_edit(query, 
            f"⚙️ Settings for *{title_md}*", parse_mode="Markdown", reply_markup=settings_keyboard(group_id)
        )

    # ---------- Approve All pending members at once ----------
    elif data.startswith("pending_approve_all:"):
        gid = int(data.split(":")[1])
        unverified = storage.get_unverified_members(gid)

        if not unverified:
            await context.bot.send_message(chat_id=query.message.chat_id, text="😌 Nothing to approve — list is already empty.")
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        uids = list(unverified.keys())
        storage.add_allowed_ids(gid, uids)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"✅ Approved and whitelisted *{len(uids)}* member(s).\n\n"
                 f"_(The individual Approve/Reject buttons above are now redundant — safe to ignore.)_",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(is_full, is_super, user.id)
        )

    # ---------- Pending approve/reject (dynamic group id in callback_data) ----------
    elif data.startswith("pending_approve:"):
        _, gid, uid = data.split(":")
        gid, uid = int(gid), int(uid)
        storage.add_allowed_ids(gid, [uid])
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ User `{uid}` approved and whitelisted.", parse_mode="Markdown")

    elif data.startswith("pending_reject:"):
        _, gid, uid = data.split(":")
        gid, uid = int(gid), int(uid)
        await kick_single_member(context.bot, gid, uid)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ User `{uid}` rejected and removed.", parse_mode="Markdown")
