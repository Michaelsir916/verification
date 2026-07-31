import re
import io
import zipfile
from collections import Counter
from telegram import Update
from telegram.ext import ContextTypes

from services import storage
from handlers.commands import (
    is_full_admin, is_super_admin, main_menu_keyboard, expiry_keyboard,
    restore_confirm_keyboard,
)

# Only these exact filenames may be written during a restore - blocks zip-slip /
# path traversal and stops an unrelated .zip from clobbering unexpected files.
ALLOWED_RESTORE_FILES = {
    "allowed_ids.json", "tracked_members.json", "removed_log.json",
    "known_groups.json", "settings.json", "managed_admins.json", "categories.json",
}


async def handle_bulk_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_full_admin(user.id):
        return

    if update.effective_chat.type != "private":
        return

    if context.user_data.get("state") != "bulk_import":
        return

    group_id = context.user_data.get("selected_group")
    if not group_id:
        await update.message.reply_text("Please select a group first.")
        return

    doc = update.message.document
    if not doc:
        return

    tg_file = await doc.get_file()
    file_bytes = await tg_file.download_as_bytearray()
    text = file_bytes.decode("utf-8", errors="ignore")

    all_matches = [int(x) for x in re.findall(r"-?\d{4,}", text)]
    context.user_data["state"] = None
    is_super = is_super_admin(user.id)

    if not all_matches:
        await update.message.reply_text(
            "⚠️ No valid User IDs found in that file.",
            reply_markup=main_menu_keyboard(True, is_super, user.id)
        )
        return

    # ---- Analyze: how many times each ID repeats *within the file itself* ----
    counts = Counter(all_matches)
    found_ids = list(counts.keys())
    repeated_in_file = {uid: c for uid, c in counts.items() if c > 1}

    # ---- Check against what's already whitelisted for this group ----
    existing = set(storage.get_allowed_ids(group_id))
    new_ids = [i for i in found_ids if i not in existing]
    already_whitelisted = len(found_ids) - len(new_ids)

    # ---- Build the analysis report ----
    report_lines = [
        f"📊 *Import analysis*",
        f"• Total ID lines read: {len(all_matches)}",
        f"• Unique IDs found: {len(found_ids)}",
    ]
    if repeated_in_file:
        dup_list = ", ".join(f"`{uid}`×{c}" for uid, c in list(repeated_in_file.items())[:15])
        more = f" (+{len(repeated_in_file) - 15} more)" if len(repeated_in_file) > 15 else ""
        report_lines.append(f"• ⚠️ Duplicate lines in file (auto-merged to 1 each): {len(repeated_in_file)}\n   {dup_list}{more}")
    else:
        report_lines.append("• ✅ No duplicate lines found in the file.")
    if already_whitelisted:
        report_lines.append(f"• ℹ️ Already on the whitelist (will be skipped): {already_whitelisted}")

    report = "\n".join(report_lines)

    if not new_ids:
        await update.message.reply_text(
            report + "\n\nNothing new to import.",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(True, is_super, user.id)
        )
        return

    context.user_data["pending_add_ids"] = new_ids

    await update.message.reply_text(
        report + f"\n\n📥 Ready to import {len(new_ids)} new ID(s).\n"
        "Choose how long they should stay whitelisted:",
        parse_mode="Markdown",
        reply_markup=expiry_keyboard()
    )


async def handle_restore_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_super_admin(user.id):
        return

    if update.effective_chat.type != "private":
        return

    if context.user_data.get("state") != "restoring_backup":
        return

    doc = update.message.document
    if not doc:
        return

    tg_file = await doc.get_file()
    file_bytes = await tg_file.download_as_bytearray()

    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        await update.message.reply_text("⚠️ That doesn't look like a valid .zip file. Please send the backup zip again.")
        return

    found = {}
    skipped = []
    for name in zf.namelist():
        base = name.rsplit("/", 1)[-1]  # ignore any folder structure inside the zip
        if base in ALLOWED_RESTORE_FILES:
            found[base] = zf.read(name)
        elif not name.endswith("/"):
            skipped.append(base)

    if not found:
        await update.message.reply_text(
            "⚠️ No recognizable backup data files (allowed_ids.json, settings.json, etc.) "
            "were found in that zip. Restore cancelled."
        )
        return

    context.user_data["restore_files"] = found

    lines = [f"📦 Found {len(found)} data file(s) in the backup:"]
    lines += [f"  • {name}" for name in sorted(found.keys())]
    if skipped:
        lines.append(f"\n(Ignored {len(skipped)} unrelated file(s) in the zip.)")
    lines.append("\n⚠️ Confirm to *overwrite* current data with this backup.")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=restore_confirm_keyboard()
    )
