import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
VIEWER_IDS = [int(x) for x in os.getenv("VIEWER_IDS", "").split(",") if x.strip()]

# Channel where automatic backups (every 2 hours) are posted. Bot must be an
# admin/member of this channel. Leave empty to disable auto-backup.
_backup_raw = os.getenv("BACKUP_CHANNEL_ID", "").strip()
BACKUP_CHANNEL_ID = int(_backup_raw) if _backup_raw else None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

ALLOWED_IDS_FILE = os.path.join(DATA_DIR, "allowed_ids.json")
TRACKED_MEMBERS_FILE = os.path.join(DATA_DIR, "tracked_members.json")
REMOVED_LOG_FILE = os.path.join(DATA_DIR, "removed_log.json")
KNOWN_GROUPS_FILE = os.path.join(DATA_DIR, "known_groups.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
MANAGED_ADMINS_FILE = os.path.join(DATA_DIR, "managed_admins.json")
CATEGORIES_FILE = os.path.join(DATA_DIR, "categories.json")
USER_LANG_FILE = os.path.join(DATA_DIR, "user_lang.json")

SUPPORT_USERNAME = "@KEERIKADAN_SIR"
