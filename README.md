# Telegram Multi-Group Member Control Bot

A bot that controls membership across **any number of** private groups/channels
based on User ID — with whitelisting, automatic protection, scheduling, search,
and reporting.

## Features

### Roles & Access Control
- **Super admins** (`ADMIN_IDS` in `.env`) — permanent, full control over
  everything, see **all groups** from all users, and can grant/revoke bot
  access to other people.
- **Delegated (managed) admins** — granted access **from inside the bot**
  by a super admin, via **👥 Manage Users**, either permanently or for a
  set number of days. They get full admin powers (add/remove/settings/etc)
  but **only for groups they personally added the bot to.**
- **Viewers** (`VIEWER_IDS` in `.env`, optional) — read-only access
  (reports, unverified list, search), scoped to their own groups only.
- **Group isolation** — whoever adds the bot to a group (or runs
  `/registergroup` inside it) becomes that group's "owner." Nobody else
  (except super admins) can see or manage that group.
- **👥 Manage Users panel** (super admin only) — shows every delegated
  admin, when their access started, when it expires (or "Permanent"), and
  lets you add or revoke access at any time.
- **All timestamps** shown anywhere in the bot (join time, removal time,
  access start/expiry, etc.) are displayed in **IST**, in **both 24-hour and
  12-hour format** at once, e.g.:
  `02-07-2026 21:15:03 (24h) / 02-07-2026 09:15:03 PM (12h) IST`
- **⬅️ Back button** — present on every input prompt (Add Members, Remove a
  Member, Bulk Import, Search, Add User), so you can always cancel and
  return to the menu without getting stuck.

### Organization
- **🏷️ Categories/Tags** — create your own custom folders (e.g. "VIP",
  "Trial", "Staff") to organize the groups you manage. Create, rename, and
  delete categories anytime via **🏷️ Manage Categories**; assign a group to
  one via **🏷️ Set Category** inside that group's menu. The group list is
  now shown as compact folders instead of one long list.
- **👥 Users panel (super admin only)** — shows each delegated admin by
  their `@username` (captured automatically the first time they use the
  bot). Tapping a user shows **only their own** access info + the list of
  groups **they personally** added — no other user's groups are ever shown
  there.

### Approval workflow
- **📝 Pending Approvals** — instead of only bulk-kicking, review each
  unauthorized joiner one at a time: username, ID, direct chat link, join
  time (IST), and invite link used — with **✅ Approve** (whitelist them) or
  **❌ Reject** (remove them) buttons right there.

### Notifications (posted to the backup/alerts channel)
- **🚶 Leave notification** (Settings toggle) — sends an alert to the backup
  channel (`BACKUP_CHANNEL_ID`) whenever someone leaves a group, naming
  which group it was.
- **⚠️ Error notifications** — if the bot fails to do something (e.g. can't
  kick a member, a scheduled job fails), it sends the error to the backup
  channel, with the group name included for context. Falls back to a DM to
  super admins if no backup channel is configured.

### Reporting
- **💤 Inactivity Report** — lists every whitelisted User ID that has never
  actually joined the group, with their username (best-effort lookup) — so
  you can see who's been given access but hasn't used it.

### Backup
- **🗄️ Auto-backup every 2 hours** — zips every data file and posts it as a
  document to a dedicated backup channel (`BACKUP_CHANNEL_ID` in `.env`).
  The bot must be an admin of that channel.

### Core
- **Multi-group support** — auto-detects every group/channel the bot is added
  to; the admin picks which one to manage from a list.
- **➕ Add Members** — whitelist User IDs one after another (loops until Done).
- **📥 Bulk Import** — upload a `.txt` file full of User IDs, all get whitelisted
  at once.
- **➖ Remove a Member** — remove a single ID from the whitelist.
- **📤 Export List** — download the current whitelist as a `.txt` file.
- **🚫 Remove Unauthorized Members** — kicks every tracked member not on the
  whitelist.
- **👀 Unverified Members** — full list of non-whitelisted tracked members:
  username, User ID, direct chat link, exact join date/time (with seconds),
  and which invite link they used.
- **📊 Removal Report** — full history of everyone ever removed, with the
  removal timestamp.
- **🔍 Search Member** — search by ID or username across **all** managed
  groups at once; shows which group(s) they're in, whitelist status, and
  join time.

### Automation (via ⚙️ Settings, per group)
- **🚨 Auto-kick** — cycles through 3 modes:
  - `OFF` — manual only (use the button yourself).
  - `INSTANT` — kicks unwhitelisted joiners immediately.
  - `GRACE` — gives a joiner a grace period (default 60 min) to get
    whitelisted before being auto-kicked.
- **👋 Welcome message** — greets whitelisted members when they join.
- **🧹 Daily auto-cleanup** — automatically runs "Remove Unauthorized
  Members" once a day (21:15 UTC).
- **📆 Daily summary** — sends admins a daily message with member counts
  (21:00 UTC).

### Roles
- **Full admins** (`ADMIN_IDS`) — full control: add/remove, cleanup, settings.
- **Viewers** (`VIEWER_IDS`, optional) — can view reports, unverified list,
  and search, but cannot change anything.

## ⚠️ Important limitation

The Telegram Bot API cannot fetch a full list of group members directly. The
bot can only know about members who join/leave **after** it has been added
to that group. Use **➕ Add Members** / **📥 Bulk Import** to whitelist
members who were already in the group before the bot joined.

## Setup

### 1. Create the bot
Talk to **@BotFather**, use `/newbot`, get the token.

### 2. Install dependencies
```bash
cd telegram_group_bot
pip install -r requirements.txt
```
(On Termux, if `pip install` for job-queue fails, run:
`pip install "python-telegram-bot[job-queue]"` separately.)

### 3. Create the `.env` file
```bash
cp .env.example .env
```
Fill in `BOT_TOKEN`, `ADMIN_IDS`, and optionally `VIEWER_IDS`.

### 4. Add the bot to each group
Make it an **Admin** with the **"Ban users"** permission.

### 5. Register pre-existing groups (one-time)
If the bot was already in a group before, send `/registergroup` inside that
group's chat (as a full admin). Newly added groups are detected automatically.

### 6. Run it
```bash
python bot.py
```

## Usage

1. Send `/start` to the bot in a **private chat**.
2. You'll see only the groups **you** added the bot to (super admins see all
   groups from everyone).
3. Pick a group, then use the menu:
   - **➕ Add Members** / **📥 Bulk Import** / **➖ Remove a Member** / **📤 Export List**
   - **🚫 Remove Unauthorized Members**
   - **👀 Unverified Members** — with ID, direct link, join time (IST), invite link
   - **📊 Removal Report** — with removal time (IST)
   - **🔍 Search Member** — across your own groups (or all groups, for super admins)
   - **⚙️ Settings** — auto-kick mode, welcome message, daily cleanup, daily summary
   - **🔄 Change Group** — go back to your group list

### Granting access to other people (super admin only)
1. From the group list screen, tap **👥 Manage Users**.
2. Tap **➕ Add User**, send their Telegram User ID, then send how many days
   of access to give them (`0` = permanent).
3. That person can now send `/start` to the bot and manage any group **they**
   add the bot to.
4. Tap any user in the list to see when their access started/expires, or to
   **🗑️ Remove Access** early.

> 💡 Restricted actions (Add/Remove/Bulk Import/Export/Cleanup/Settings) need
> full-admin status (super admin or an active delegated admin). Viewers get
> a read-only menu. The Manage Users panel is visible only to super admins.

## Folder structure

```
telegram_group_bot/
├── bot.py                    # Entry point, registers handlers + daily jobs
├── config.py                  # Settings (reads .env)
├── requirements.txt
├── .env.example
├── handlers/
│   ├── commands.py            # /start, /myid, /registergroup, menus, text-flow states
│   ├── buttons.py             # All inline-button callbacks
│   ├── documents.py           # Bulk .txt ID import
│   ├── member_tracker.py      # Join/leave tracking + auto-kick/grace/welcome
│   └── jobs.py                # Scheduled jobs: grace kick, daily summary, auto-cleanup
├── services/
│   ├── storage.py             # JSON file read/write (per-group data, settings, roles)
│   ├── timeutils.py           # IST dual-format (12h+24h) time display
│   └── group_service.py       # Kick logic (single + bulk)
└── data/
    ├── known_groups.json      # Groups the bot is in (with owner_id)
    ├── allowed_ids.json       # Whitelisted IDs, per group
    ├── tracked_members.json   # Observed members, per group (with join info)
    ├── removed_log.json       # Removal history, per group
    ├── settings.json          # Per-group automation settings
    └── managed_admins.json    # Delegated admin access (start/expiry)
```
