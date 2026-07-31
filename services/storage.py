import json
import os
import logging
from datetime import datetime, timezone, timedelta
from config import (
    ALLOWED_IDS_FILE,
    TRACKED_MEMBERS_FILE,
    REMOVED_LOG_FILE,
    KNOWN_GROUPS_FILE,
    SETTINGS_FILE,
    MANAGED_ADMINS_FILE,
    CATEGORIES_FILE,
    USER_LANG_FILE,
)

logger = logging.getLogger(__name__)


def _load(path, default):
    """
    Load JSON from `path`. If the file is missing, return `default`.
    If the file exists but is corrupt (e.g. a write got interrupted by a
    Termux/Android process kill during a network drop), try to recover from
    the `<path>.bak` file that `_save` keeps around, instead of silently
    returning an empty default (which used to make whole groups/whitelists
    "disappear" even though nothing was actually removed).
    """
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        bak_path = path + ".bak"
        if os.path.exists(bak_path):
            try:
                with open(bak_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.warning(
                    "%s was corrupted - recovered from backup %s", path, bak_path
                )
                return data
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        logger.error(
            "%s is corrupted and no valid backup was found - returning empty data",
            path,
        )
        return default


def _save(path, data):
    """
    Atomic, crash-safe save:
    1. Keep a copy of the last good file as `<path>.bak` (best-effort).
    2. Write the new data to a temp file in the same directory.
    3. fsync + os.replace() the temp file over the real file.
    os.replace() is atomic on both Linux/Termux and Android, so a process
    getting killed mid-write (e.g. Android killing Termux when network
    toggles) can never leave a half-written/corrupt JSON file behind - the
    original file stays intact until the new one is fully written.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    bak_path = path + ".bak"
    if os.path.exists(path):
        try:
            with open(path, "rb") as src, open(bak_path, "wb") as dst:
                dst.write(src.read())
        except OSError:
            pass  # best-effort backup; don't block the real save on this

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


# ---------- Known groups (every group/channel the bot is currently in) ----------
# Structure: { "<chat_id>": {"title": "...", "owner_id": <user_id or null>} }
# owner_id = the user who added the bot to this group (or who ran /registergroup).
# Only super admins can see groups with no owner / other people's groups.

def get_known_groups():
    return _load(KNOWN_GROUPS_FILE, {})


def add_known_group(chat_id, title, owner_id=None):
    data = _load(KNOWN_GROUPS_FILE, {})
    key = str(chat_id)
    existing = data.get(key, {})
    entry = {"title": title or str(chat_id)}
    # Preserve the existing owner/category unless a new one is explicitly given
    entry["owner_id"] = owner_id if owner_id is not None else existing.get("owner_id")
    entry["category_id"] = existing.get("category_id")
    data[key] = entry
    _save(KNOWN_GROUPS_FILE, data)


def set_group_category(chat_id, category_id):
    data = _load(KNOWN_GROUPS_FILE, {})
    key = str(chat_id)
    if key in data:
        data[key]["category_id"] = category_id
        _save(KNOWN_GROUPS_FILE, data)


def remove_known_group(chat_id):
    data = _load(KNOWN_GROUPS_FILE, {})
    key = str(chat_id)
    if key in data:
        del data[key]
        _save(KNOWN_GROUPS_FILE, data)


def get_group_title(chat_id):
    data = _load(KNOWN_GROUPS_FILE, {})
    info = data.get(str(chat_id))
    return info.get("title") if info else str(chat_id)


def get_group_owner(chat_id):
    data = _load(KNOWN_GROUPS_FILE, {})
    info = data.get(str(chat_id))
    return info.get("owner_id") if info else None


def get_group_category(chat_id):
    data = _load(KNOWN_GROUPS_FILE, {})
    info = data.get(str(chat_id))
    return info.get("category_id") if info else None


def get_groups_by_category(owner_id, category_id):
    """
    All chat_ids owned by `owner_id` that share `category_id`
    (category_id can be None, meaning the "Uncategorized" bucket).
    """
    data = _load(KNOWN_GROUPS_FILE, {})
    return [
        int(cid) for cid, info in data.items()
        if info.get("owner_id") == owner_id and info.get("category_id") == category_id
    ]


def get_groups_by_owner(owner_id):
    data = _load(KNOWN_GROUPS_FILE, {})
    return [int(cid) for cid, info in data.items() if info.get("owner_id") == owner_id]


# ---------- Managed (delegated) admins ----------
# Structure: { "<user_id>": {"added_by":..., "started_at": iso, "expires_at": iso|null, "days": int|null} }

def get_managed_admins():
    return _load(MANAGED_ADMINS_FILE, {})


def add_managed_admin(user_id, added_by, days):
    """days = None or 0 means permanent access."""
    data = _load(MANAGED_ADMINS_FILE, {})
    now = datetime.now(timezone.utc)
    expires = None
    if days:
        expires = (now + timedelta(days=days)).isoformat()
    data[str(user_id)] = {
        "added_by": added_by,
        "started_at": now.isoformat(),
        "expires_at": expires,
        "days": days or None,
    }
    _save(MANAGED_ADMINS_FILE, data)


def remove_managed_admin(user_id):
    data = _load(MANAGED_ADMINS_FILE, {})
    key = str(user_id)
    if key in data:
        del data[key]
        _save(MANAGED_ADMINS_FILE, data)
        return True
    return False


def get_managed_admin_info(user_id):
    data = _load(MANAGED_ADMINS_FILE, {})
    return data.get(str(user_id))


def set_managed_admin_username(user_id, username):
    """Called on /start so the Manage Users panel can show @username instead of a raw ID."""
    data = _load(MANAGED_ADMINS_FILE, {})
    key = str(user_id)
    if key in data:
        data[key]["username"] = username or ""
        _save(MANAGED_ADMINS_FILE, data)


def is_managed_admin_active(user_id):
    info = get_managed_admin_info(user_id)
    if not info:
        return False
    expires = info.get("expires_at")
    if expires:
        try:
            if datetime.fromisoformat(expires) <= datetime.now(timezone.utc):
                return False
        except ValueError:
            pass
    return True


# ---------- Per-group settings ----------
_DEFAULT_SETTINGS = {
    "auto_kick": "off",
    "grace_minutes": 60,
    "welcome_message": False,
    "daily_summary": False,
    "auto_cleanup": False,
    "leave_notification": False,
    "auto_whitelist_minutes": -1,  # -1 = disabled, 0 = instant, N = auto-whitelist N minutes after joining
}


def get_group_settings(chat_id):
    data = _load(SETTINGS_FILE, {})
    saved = data.get(str(chat_id), {})
    return {**_DEFAULT_SETTINGS, **saved}


def set_group_setting(chat_id, key, value):
    data = _load(SETTINGS_FILE, {})
    ckey = str(chat_id)
    data.setdefault(ckey, {})
    data[ckey][key] = value
    _save(SETTINGS_FILE, data)


# ---------- Allowed IDs (whitelisted by the admin, per group) ----------
# Structure: { "<chat_id>": { "<user_id>": {"added_at": iso, "expires_at": iso|null} } }

def get_allowed_ids(chat_id):
    """Returns a set of currently-allowed user IDs (expired temp-access IDs excluded)."""
    data = _load(ALLOWED_IDS_FILE, {})
    chat_data = data.get(str(chat_id), {})
    now = datetime.now(timezone.utc)
    allowed = set()
    for uid_str, info in chat_data.items():
        if not isinstance(info, dict):
            allowed.add(int(uid_str))
            continue
        expires = info.get("expires_at")
        if expires:
            try:
                if datetime.fromisoformat(expires) <= now:
                    continue
            except (ValueError, TypeError):
                pass
        allowed.add(int(uid_str))
    return allowed


def add_allowed_ids(chat_id, ids, expires_at=None):
    data = _load(ALLOWED_IDS_FILE, {})
    key = str(chat_id)
    data.setdefault(key, {})
    for uid in ids:
        data[key][str(uid)] = {
            "added_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at,
        }
    _save(ALLOWED_IDS_FILE, data)
    return get_allowed_ids(chat_id)


def remove_allowed_id(chat_id, user_id):
    data = _load(ALLOWED_IDS_FILE, {})
    key = str(chat_id)
    if key in data and str(user_id) in data[key]:
        del data[key][str(user_id)]
        _save(ALLOWED_IDS_FILE, data)
        return True
    return False


# ---------- Tracked members (members the bot has observed in each group) ----------
# Structure:
# { "<chat_id>": { "<user_id>": {"username": "...", "join_time": iso, "invite_link": "..."} } }

def get_tracked_members(chat_id):
    data = _load(TRACKED_MEMBERS_FILE, {})
    return data.get(str(chat_id), {})


def add_tracked_member(chat_id, user_id, username, join_time=None, invite_link=None):
    data = _load(TRACKED_MEMBERS_FILE, {})
    key = str(chat_id)
    data.setdefault(key, {})
    data[key][str(user_id)] = {
        "username": username or "",
        "join_time": join_time or "",
        "invite_link": invite_link or "",
    }
    _save(TRACKED_MEMBERS_FILE, data)


def remove_tracked_member(chat_id, user_id):
    data = _load(TRACKED_MEMBERS_FILE, {})
    key = str(chat_id)
    if key in data and str(user_id) in data[key]:
        del data[key][str(user_id)]
        _save(TRACKED_MEMBERS_FILE, data)


def get_unverified_members(chat_id):
    allowed = get_allowed_ids(chat_id)
    tracked = get_tracked_members(chat_id)
    return {uid: info for uid, info in tracked.items() if int(uid) not in allowed}


# ---------- Removed log (append-only history of removed members, per group) ----------
# Structure: { "<chat_id>": [ {"user_id":..., "username":..., "removed_at": iso}, ... ] }

def append_removed(chat_id, entry):
    data = _load(REMOVED_LOG_FILE, {})
    key = str(chat_id)
    data.setdefault(key, [])
    data[key].append(entry)
    _save(REMOVED_LOG_FILE, data)


def get_removed_log(chat_id):
    data = _load(REMOVED_LOG_FILE, {})
    return data.get(str(chat_id), [])


# ---------- Cross-group search ----------

def search_member(query, owner_id=None):
    """
    query: a numeric User ID (as string) or a username (without @).
    owner_id: if given, only searches groups owned by this user (used to
    isolate delegated admins/viewers to their own groups). None = search all.
    """
    results = []
    groups = get_known_groups()

    is_numeric = query.lstrip("-").isdigit()
    q_id = int(query) if is_numeric else None
    q_username = query.lower().lstrip("@") if not is_numeric else None

    for chat_id_str, ginfo in groups.items():
        if owner_id is not None and ginfo.get("owner_id") != owner_id:
            continue

        chat_id = int(chat_id_str)
        allowed = get_allowed_ids(chat_id)
        tracked = get_tracked_members(chat_id)

        found_uid = None
        info = {}

        if q_id is not None:
            if str(q_id) in tracked:
                found_uid = q_id
                info = tracked[str(q_id)]
            elif q_id in allowed:
                found_uid = q_id
        elif q_username:
            for uid, tinfo in tracked.items():
                if (tinfo.get("username") or "").lower() == q_username:
                    found_uid = int(uid)
                    info = tinfo
                    break

        if found_uid is not None:
            results.append({
                "chat_id": chat_id,
                "group_title": ginfo.get("title", chat_id_str),
                "user_id": found_uid,
                "allowed": found_uid in allowed,
                "username": info.get("username", ""),
                "join_time": info.get("join_time") or "",
                "invite_link": info.get("invite_link", ""),
            })

    return results


# ---------- Per-user language preference (menu display language) ----------
# Structure: { "<user_id>": "en" | "ml" }

def get_user_lang(user_id):
    data = _load(USER_LANG_FILE, {})
    return data.get(str(user_id), "en")


def set_user_lang(user_id, lang):
    data = _load(USER_LANG_FILE, {})
    data[str(user_id)] = lang
    _save(USER_LANG_FILE, data)


def toggle_user_lang(user_id):
    current = get_user_lang(user_id)
    new_lang = "ml" if current == "en" else "en"
    set_user_lang(user_id, new_lang)
    return new_lang


# ---------- Custom group categories/tags (per owner, editable/deletable) ----------
# Structure: { "<owner_id>": { "<category_id>": "Category Name" } }

def get_categories(owner_id):
    data = _load(CATEGORIES_FILE, {})
    return data.get(str(owner_id), {})


def add_category(owner_id, name):
    import uuid
    data = _load(CATEGORIES_FILE, {})
    key = str(owner_id)
    data.setdefault(key, {})
    cat_id = uuid.uuid4().hex[:8]
    data[key][cat_id] = name
    _save(CATEGORIES_FILE, data)
    return cat_id


def rename_category(owner_id, category_id, new_name):
    data = _load(CATEGORIES_FILE, {})
    key = str(owner_id)
    if key in data and category_id in data[key]:
        data[key][category_id] = new_name
        _save(CATEGORIES_FILE, data)
        return True
    return False


def delete_category(owner_id, category_id):
    data = _load(CATEGORIES_FILE, {})
    key = str(owner_id)
    if key in data and category_id in data[key]:
        del data[key][category_id]
        _save(CATEGORIES_FILE, data)

        # Unassign this category from any groups that were using it
        groups = _load(KNOWN_GROUPS_FILE, {})
        changed = False
        for chat_id, ginfo in groups.items():
            if ginfo.get("category_id") == category_id:
                ginfo["category_id"] = None
                changed = True
        if changed:
            _save(KNOWN_GROUPS_FILE, groups)
        return True
    return False
