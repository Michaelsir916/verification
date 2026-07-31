"""
Lightweight i18n layer for the bot's main menu + a few key messages.
Not a full translation of every screen — just the parts a user looks at
most often (main menu buttons, nav buttons, welcome text). Falls back to
English for any key that hasn't been translated yet, so nothing breaks.
"""

LANGS = {"en": "🇬🇧 English", "ml": "🇮🇳 മലയാളം"}

STRINGS = {
    "add_members": {"en": "➕ Add Members", "ml": "➕ അംഗങ്ങളെ ചേർക്കുക"},
    "remove_member": {"en": "➖ Remove a Member", "ml": "➖ ഒരാളെ നീക്കം ചെയ്യുക"},
    "bulk_import": {"en": "📥 Bulk Import", "ml": "📥 ബൾക്ക് ഇംപോർട്ട്"},
    "export_list": {"en": "📤 Export List", "ml": "📤 ലിസ്റ്റ് എക്സ്പോർട്ട്"},
    "remove_unauthorized": {"en": "🚫 Remove Unauthorized Members", "ml": "🚫 അനധികൃത അംഗങ്ങളെ നീക്കുക"},
    "pending_approvals": {"en": "📝 Pending Approvals", "ml": "📝 അംഗീകാരം കാത്തിരിക്കുന്നവ"},
    "unverified_members": {"en": "👀 Unverified Members", "ml": "👀 പരിശോധിക്കാത്ത അംഗങ്ങൾ"},
    "search_member": {"en": "🔍 Search Member", "ml": "🔍 അംഗത്തെ തിരയുക"},
    "inactivity_report": {"en": "💤 Inactivity Report", "ml": "💤 നിഷ്ക്രിയ റിപ്പോർട്ട്"},
    "removal_report": {"en": "📊 Removal Report", "ml": "📊 നീക്കം ചെയ്ത റിപ്പോർട്ട്"},
    "group_stats": {"en": "📈 Group Stats", "ml": "📈 ഗ്രൂപ്പ് സ്ഥിതിവിവരം"},
    "set_category": {"en": "🏷️ Set Category", "ml": "🏷️ വിഭാഗം സെറ്റ് ചെയ്യുക"},
    "settings": {"en": "⚙️ Settings", "ml": "⚙️ സെറ്റിംഗ്സ്"},
    "main_menu": {"en": "🏠 Main Menu", "ml": "🏠 പ്രധാന മെനു"},
    "support": {"en": "🆘 Support", "ml": "🆘 സഹായം"},
    "language": {"en": "🌐 Language: English", "ml": "🌐 ഭാഷ: മലയാളം"},
    "approve_all": {"en": "✅ Approve All", "ml": "✅ എല്ലാം അംഗീകരിക്കുക"},
    "confirm": {"en": "✅ Yes, confirm", "ml": "✅ അതെ, ഉറപ്പാക്കുക"},
    "cancel": {"en": "❌ Cancel", "ml": "❌ റദ്ദാക്കുക"},
    "welcome": {
        "en": "👋 *Welcome to the Group Guardian Bot!* 🛡️",
        "ml": "👋 *ഗ്രൂപ്പ് ഗാർഡിയൻ ബോട്ടിലേക്ക് സ്വാഗതം!* 🛡️",
    },
}


def t(key, lang="en"):
    """Translate `key` into `lang`. Falls back to English, then the key itself."""
    entry = STRINGS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key
